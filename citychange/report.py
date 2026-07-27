"""Grounded summary generation.

Every sentence is instantiated from computed numbers; there is no free-text
generation. Language discipline (docs/DECISIONS.md D-007):

- OBSERVATION: what the land-cover product shows ("built-up rose from…").
- INFERENCE: explicitly hedged, bounded by cadence ("change appears
  between the 2020 and 2021 composites").
- No causal claims, no intent attribution, "rare" never "suspicious".
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import asdict
from typing import Any

import numpy as np

from citychange.config import RegionConfig
from citychange.datasets.io_annual_lulc import AnnualStack
from citychange.landstate import STATE_LABELS, STATE_NAMES
from citychange.params import AnalysisParams
from citychange.trajectory import ARCHETYPE_NAMES, CHANGE_ARCHETYPES

_NAME_TO_LABEL = {STATE_NAMES[s]: label for s, label in STATE_LABELS.items()}

SOURCE_CITATION = "Impact Observatory / Esri 10m Annual LULC v003 (CC BY 4.0)"


def _label(name: str) -> str:
    return _NAME_TO_LABEL.get(name, name)


def _pp(x: float) -> str:
    return f"{x * 100:+.1f}"


def build_summary(
    *,
    region: RegionConfig,
    params: AnalysisParams,
    stack: AnnualStack,
    trends: dict[str, dict[int, float]],
    transitions: list[tuple[str, str, float]],
    raw_change_fraction: float,
    b2_change_fraction: float,
    event_change_fraction: float,
    volumes: dict[int, dict[tuple[int, int], int]],
    peak: tuple[int, int] | None,
    archetypes: np.ndarray,
    analysed: np.ndarray,
    sig_stats: list[dict],
    rare_table: list[dict],
    anomaly_fraction: float,
    tier_counts: dict[str, int],
    mean_confidence: float,
    hotspots: list[dict],
    clusters: dict,
    fingerprint: str,
) -> dict[str, Any]:
    y0, y1 = region.years[0], region.years[-1]
    deltas = {
        name: series[y1] - series[y0]
        for name, series in trends.items()
        if y0 in series and y1 in series
    }
    n_analysed = max(int(analysed.sum()), 1)
    arch_fracs = {
        ARCHETYPE_NAMES[code]: round(float((archetypes == code).sum()) / n_analysed, 4)
        for code in ARCHETYPE_NAMES
        if code != 0 and (archetypes == code).any()
    }
    volumes_json = {
        str(year): [
            {
                "from": STATE_NAMES[f],
                "to": STATE_NAMES[t],
                "pixels": px,
            }
            for (f, t), px in sorted(pairs.items(), key=lambda kv: -kv[1])
        ]
        for year, pairs in sorted(volumes.items())
    }
    return {
        "citychange_version": _version(),
        "fingerprint": fingerprint,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "region": region.name,
        "display_name": region.display_name,
        "bbox": asdict(region.bbox),
        "utm_tile": stack.tile,
        "grid_shape": list(stack.shape),
        "pixel_meters": 10,
        "area_km2": round(stack.shape[0] * stack.shape[1] * 100 / 1e6, 1),
        "years": list(region.years),
        "source": SOURCE_CITATION,
        "params": asdict(params),
        "state_fractions_by_year": {
            name: {str(y): round(v, 4) for y, v in series.items()}
            for name, series in trends.items()
        },
        "fraction_deltas_first_to_last": {k: round(v, 4) for k, v in deltas.items()},
        "top_transitions_first_to_last": [
            {"from": f, "to": t, "fraction_of_area": round(v, 4)}
            for f, t, v in transitions
        ],
        "change_fractions": {
            "raw_two_date": round(raw_change_fraction, 4),
            "persistence_rule_b2": round(b2_change_fraction, 4),
            "event_based": round(event_change_fraction, 4),
        },
        "change_volumes_by_year": volumes_json,
        "peak_change_period": list(peak) if peak else None,
        "archetype_fractions": arch_fracs,
        "top_signatures": sig_stats[:10],
        "anomalies": {
            "fraction_of_area": round(anomaly_fraction, 5),
            "rarity_threshold": params.rarity_threshold,
            "top_rare_signatures": rare_table[:8],
        },
        "confidence": {
            "mean_event_score": round(mean_confidence, 3),
            "tier_counts": tier_counts,
            "note": (
                "Scores are documented evidence heuristics (persistence, "
                "pre-stability, sequence purity, spatial support), not "
                "calibrated probabilities."
            ),
        },
        "hotspots": hotspots,
        "clusters": clusters,
    }


def _version() -> str:
    from citychange import __version__

    return __version__


def render_markdown(s: dict[str, Any]) -> str:
    y0, y1 = s["years"][0], s["years"][-1]
    lines: list[str] = []
    ap = lines.append
    ap(f"# CityChange — {s['display_name']}")
    ap("")
    b = s["bbox"]
    ap(
        f"{b['west']:.3f}–{b['east']:.3f}°E, {b['south']:.3f}–{b['north']:.3f}°N · "
        f"{s['area_km2']} km² · {y0}–{y1} annual observations · {s['source']}."
    )
    ap("")

    ap("## What changed")
    ap("")
    for name, delta in sorted(
        s["fraction_deltas_first_to_last"].items(), key=lambda kv: -abs(kv[1])
    ):
        if abs(delta) < 0.001:
            continue
        series = s["state_fractions_by_year"][name]
        ap(
            f"- **{_label(name)}**: {series[str(y0)] * 100:.1f}% → "
            f"{series[str(y1)] * 100:.1f}% ({_pp(delta)} pp)."
        )
    cf = s["change_fractions"]
    ap("")
    ap(
        f"- A naive two-date comparison marks {cf['raw_two_date'] * 100:.1f}% of the "
        f"area as changed; {cf['event_based'] * 100:.1f}% meets the event "
        f"criterion (the new state persists {s['params']['persistence']}+ years "
        f"and replaces a stable predecessor)."
    )
    if s["top_transitions_first_to_last"]:
        ap("")
        ap("Largest transitions:")
        for t in s["top_transitions_first_to_last"]:
            ap(
                f"- {_label(t['from'])} → {_label(t['to'])}: "
                f"{t['fraction_of_area'] * 100:.1f}% of the area"
            )
    ap("")

    ap("## When change happened")
    ap("")
    if s["peak_change_period"]:
        p0, p1 = s["peak_change_period"]
        ap(
            f"Change volume peaked in the window between the {p0} and {p1} "
            f"composites (annual cadence bounds all timing to ±1 year)."
        )
        ap("")
        for year, items in s["change_volumes_by_year"].items():
            total = sum(i["pixels"] for i in items)
            top = items[0]
            ap(
                f"- {int(year) - 1}→{year}: {total * 100 / 1e6:.2f} km² changed; "
                f"largest: {_label(top['from'])} → {_label(top['to'])} "
                f"({top['pixels'] * 100 / 1e6:.2f} km²)."
            )
    else:
        ap("No persistent change events were detected in this period.")
    ap("")

    ap("## How places changed (trajectories)")
    ap("")
    af = s["archetype_fractions"]
    stable_frac = af.get("stable", 0) + af.get("stable_with_flicker", 0)
    change_frac = sum(af.get(ARCHETYPE_NAMES[c], 0) for c in CHANGE_ARCHETYPES)
    ap(
        f"Of analysed pixels, {stable_frac * 100:.1f}% kept their state, "
        f"{change_frac * 100:.1f}% underwent a persistent change, and the rest "
        f"were unstable or fluctuating."
    )
    ap("")
    for row in s["top_signatures"][:6]:
        if row["signature"] == "unobserved":
            continue
        ap(f"- `{row['signature']}` — {row['fraction'] * 100:.1f}% of pixels")
    ap("")

    an = s["anomalies"]
    ap("## Unusual trajectories")
    ap("")
    if an["top_rare_signatures"]:
        ap(
            f"{an['fraction_of_area'] * 100:.2f}% of the area followed trajectories "
            f"seen in less than {an['rarity_threshold'] * 100:.1f}% of pixels — "
            f"statistically rare for this region, which is a rarity statement, "
            f"not an assessment of legality or intent. Most common rare paths:"
        )
        for row in an["top_rare_signatures"][:5]:
            ap(f"- `{row['signature']}` ({row['pixels']} px)")
    else:
        ap("No rare trajectories at the configured threshold.")
    ap("")

    ap("## Where change concentrated")
    ap("")
    for h in s["hotspots"]:
        ap(
            f"{h['rank']}. ({h['lat']:.5f}°N, {h['lon']:.5f}°E) — "
            f"{h['change_fraction'] * 100:.0f}% of a {h['block_m']} m block changed; "
            f"dominant: {_label(h['dominant_from'])} → {_label(h['dominant_to'])}, "
            f"appearing by {h['dominant_year']} "
            f"(mean confidence {h['mean_confidence']:.2f})."
        )
    if not s["hotspots"]:
        ap("No change hotspots — the area was largely stable.")
    ap("")

    c = s["confidence"]
    ap("## Confidence")
    ap("")
    tc = c["tier_counts"]
    total_ev = max(sum(tc.values()), 1)
    ap(
        f"Detected changes: {tc.get('high', 0) * 100 // total_ev}% high, "
        f"{tc.get('medium', 0) * 100 // total_ev}% medium, "
        f"{tc.get('low', 0) * 100 // total_ev}% low confidence "
        f"(mean score {c['mean_event_score']:.2f}). {c['note']}"
    )
    ap("")

    ap("## Caveats")
    ap("")
    ap("- Observations come from an automated land-cover product; per-pixel classifications carry error and the product's biases propagate to this analysis.")
    ap("- Annual composites cannot resolve sub-year timing; every date is a between-composites window.")
    ap("- This report describes *what* the observations show, not *why* it happened; no causal claims are made.")
    ap("- Changes beginning in the final year of the series are excluded by the persistence requirement.")
    ap("")
    return "\n".join(lines)


