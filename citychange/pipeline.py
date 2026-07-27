"""End-to-end analysis orchestrator.

One function — run_analysis() — takes a RegionConfig and produces a
persistent *analysis bundle* on disk:

    data/outputs/<region>/
        summary.json      full machine-readable analysis (frontend contract)
        summary.md        grounded human-readable story
        figures/*.png     static figures (reports, papers)
        rasters/*.tif     georeferenced analysis rasters
        overlays/*.png    EPSG:4326 RGBA overlays + overlays.json manifest

The CLI and the web API both call this function; neither contains analysis
logic of its own. Re-runs with an unchanged fingerprint (bbox, years,
params) are no-ops unless force=True.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import rasterio

from citychange import __version__
from citychange.analysis import (
    fraction_trends,
    stable_change_mask,
    top_transitions,
    transition_matrix,
)
from citychange.config import RegionConfig, data_dir
from citychange.confidence import score_events, tier_events, tier_summary
from citychange.datasets.io_annual_lulc import AnnualStack, fetch_annual_stack
from citychange.events import change_volumes, extract_events, peak_change_period
from citychange.landstate import NODATA, STATE_NAMES, remap_to_states
from citychange.overlays import OverlayWriter
from citychange.params import DEFAULT_PARAMS, AnalysisParams
from citychange.report import build_summary, render_markdown
from citychange.trajectory import (
    ARCHETYPE_NAMES,
    block_features,
    classify_archetypes,
    cluster_blocks,
    encode_signatures,
    rarity,
    signature_stats,
)
from citychange import viz

log = logging.getLogger(__name__)


def bundle_dir(region_name: str) -> Path:
    return data_dir() / "outputs" / region_name


def _fingerprint(region: RegionConfig, params: AnalysisParams) -> str:
    payload = json.dumps(
        {"region": asdict(region), "params": asdict(params), "v": __version__},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_summary(region_name: str) -> dict | None:
    path = bundle_dir(region_name) / "summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _save_raster(
    path: Path, data: np.ndarray, stack: AnnualStack, nodata: int = 0
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=data.dtype.name,
        crs=stack.crs,
        transform=stack.transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)


def _hotspots(
    bf_features: np.ndarray,
    bf_rc: np.ndarray,
    changed_col: int,
    stack: AnnualStack,
    fields,
    scores: np.ndarray,
    params: AnalysisParams,
) -> list[dict]:
    """Top-N coarse blocks by change density, with grounded attributes."""
    order = np.argsort(-bf_features[:, changed_col])
    out: list[dict] = []
    bp = params.block_px
    for i in order[: params.n_hotspots]:
        frac = float(bf_features[i, changed_col])
        if frac <= 0:
            break
        br, bc = int(bf_rc[i][0]), int(bf_rc[i][1])
        sl = np.s_[br * bp : (br + 1) * bp, bc * bp : (bc + 1) * bp]
        ev = fields.event[sl]
        if not ev.any():
            continue
        fr = fields.from_state[sl][ev]
        to = fields.to_state[sl][ev]
        yi = fields.year_index[sl][ev]
        pair_keys = fr.astype(int) * 100 + to.astype(int)
        dom_pair = int(np.bincount(pair_keys).argmax())
        dom_year = int(fields.years[int(np.bincount(yi).argmax())])
        lon, lat = stack.pixel_center_lonlat(br * bp + bp / 2, bc * bp + bp / 2)
        out.append(
            {
                "rank": len(out) + 1,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "block_m": bp * 10,
                "change_fraction": round(frac, 4),
                "dominant_from": STATE_NAMES[dom_pair // 100],
                "dominant_to": STATE_NAMES[dom_pair % 100],
                "dominant_year": dom_year,
                "mean_confidence": round(float(scores[sl][ev].mean()), 3),
            }
        )
    return out


def run_analysis(
    region: RegionConfig,
    params: AnalysisParams = DEFAULT_PARAMS,
    force: bool = False,
    make_overlays: bool = True,
    make_evidence: bool = True,
) -> dict:
    """Run the full intelligence pipeline for one region; returns summary."""
    t0 = time.time()
    out_dir = bundle_dir(region.name)
    fp = _fingerprint(region, params)

    existing = load_summary(region.name)
    if existing and existing.get("fingerprint") == fp and not force:
        log.info("bundle for '%s' is current (fingerprint %s) — skipping", region.name, fp)
        return existing

    # --- acquire + canonical states -------------------------------------
    stack = fetch_annual_stack(region)
    states = {y: remap_to_states(g) for y, g in stack.grids.items()}
    y0, y1 = region.years[0], region.years[-1]
    log.info("grid %s px (%s)", stack.shape, stack.tile)

    # --- baseline analysis (kept as evaluation baselines) ----------------
    trends = fraction_trends(states)
    matrix = transition_matrix(states[y0], states[y1])
    transitions = top_transitions(matrix, k=5)
    raw_change = sum(v for (f, t), v in matrix.items() if f != t)
    b2_mask = stable_change_mask(states, persistence=params.persistence)

    # --- events, trajectories, confidence --------------------------------
    fields = extract_events(states, params)
    volumes = change_volumes(fields)
    peak = peak_change_period(volumes)

    sig = encode_signatures(states)
    analysed = fields.observed_years >= params.min_observed_years
    archetypes = classify_archetypes(states, fields, params)
    anomaly_mask, rare_table = rarity(sig, analysed, params)
    sig_stats = signature_stats(sig, analysed)

    scores = score_events(fields, params)
    tiers = tier_events(scores, fields, params)

    bf = block_features(states, fields, params)
    changed_col = bf.feature_names.index("changed")
    labels, cluster_desc, silhouette = cluster_blocks(bf, params)
    hotspots = _hotspots(
        bf.features, bf.block_rc, changed_col, stack, fields, scores, params
    )

    observed_any = (states[y0] != NODATA) & (states[y1] != NODATA)
    denom = max(int(observed_any.sum()), 1)
    event_fraction = float(fields.event.sum()) / denom

    # --- persist rasters --------------------------------------------------
    rdir = out_dir / "rasters"
    yoc = fields.year_of_change
    _save_raster(rdir / "year_of_change.tif", yoc, stack)
    _save_raster(rdir / "from_state.tif", fields.from_state, stack)
    _save_raster(rdir / "to_state.tif", fields.to_state, stack)
    _save_raster(rdir / "confidence.tif", (scores * 100).astype(np.uint8), stack)
    _save_raster(rdir / "confidence_tier.tif", tiers, stack)
    _save_raster(rdir / "archetype.tif", archetypes, stack, nodata=0)
    _save_raster(rdir / "anomaly.tif", anomaly_mask.astype(np.uint8), stack)

    # --- summary ----------------------------------------------------------
    summary = build_summary(
        region=region,
        params=params,
        stack=stack,
        trends=trends,
        transitions=transitions,
        raw_change_fraction=raw_change,
        b2_change_fraction=float(b2_mask.sum()) / denom,
        event_change_fraction=event_fraction,
        volumes=volumes,
        peak=peak,
        archetypes=archetypes,
        analysed=analysed,
        sig_stats=sig_stats,
        rare_table=rare_table,
        anomaly_fraction=float(anomaly_mask.sum()) / denom,
        tier_counts=tier_summary(tiers),
        mean_confidence=float(scores[fields.event].mean()) if fields.event.any() else 0.0,
        hotspots=hotspots,
        clusters={"k": len(cluster_desc), "silhouette": round(silhouette, 3),
                  "descriptions": cluster_desc},
        fingerprint=fp,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out_dir / "summary.md").write_text(render_markdown(summary))

    # --- figures ----------------------------------------------------------
    fdir = out_dir / "figures"
    viz.plot_yearly_states(states, f"{region.display_name} — annual land states", fdir / "yearly_states.png")
    viz.plot_trends(trends, f"{region.display_name} — land-state trends {y0}–{y1}", fdir / "trends.png")
    viz.plot_change_events(states[y1], fields.event, fields.to_state, hotspots, stack,
                           f"{region.display_name} — persistent change {y0}–{y1}", fdir / "change_map.png")
    viz.plot_year_of_change(yoc, region.years, f"{region.display_name} — when change happened", fdir / "year_of_change.png")
    viz.plot_volumes(volumes, region.years, f"{region.display_name} — change volume by year", fdir / "volumes.png")
    viz.plot_archetypes(archetypes, f"{region.display_name} — trajectory archetypes", fdir / "archetypes.png")
    viz.plot_anomalies(states[y1], anomaly_mask, f"{region.display_name} — rare trajectories", fdir / "anomalies.png")

    # --- Sentinel-2 evidence chips (optional path, never fails the run) ---
    if make_evidence and hotspots:
        try:
            from citychange.datasets.sentinel2 import evidence_for_hotspot

            entries = []
            for h in hotspots[:3]:
                entry = evidence_for_hotspot(h, out_dir / "evidence")
                if entry:
                    entries.append(entry)
            if entries:
                (out_dir / "evidence" / "evidence.json").write_text(
                    json.dumps({"hotspots": entries}, indent=2)
                )
                log.info("evidence chips for %d hotspots", len(entries))
        except Exception:
            log.exception("evidence generation failed (non-fatal)")

    # --- web overlays -----------------------------------------------------
    if make_overlays:
        ow = OverlayWriter(out_dir / "overlays", region.bbox, stack.transform, stack.crs)
        for year in region.years:
            ow.add_states(year, states[year])
        ow.add_change(fields.event, fields.to_state)
        ow.add_year_of_change(yoc, region.years)
        ow.add_confidence(tiers)
        ow.add_anomalies(anomaly_mask)
        ow.add_clusters(labels.reshape(bf.grid_shape), params.block_px, stack.shape)
        ow.write_manifest()

    log.info("bundle for '%s' written to %s in %.1fs", region.name, out_dir, time.time() - t0)
    return summary
