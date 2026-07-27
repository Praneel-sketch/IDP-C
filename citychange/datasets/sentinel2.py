"""Sentinel-2 evidence chips: inspectable before/after imagery for detected
change events.

Uses the Earth Search STAC API (Element 84, AWS Open Data, no credentials;
verified 2026-07) to find low-cloud Sentinel-2 L2A scenes around a change
event's estimated transition window, then windowed-reads the `visual`
(true-color COG) asset for a small chip around the location.

Role in the system: EVIDENCE, not analysis. Chips let a human verify a
claimed transformation with their own eyes; nothing downstream depends on
them, and every function here degrades gracefully (returns None / skips)
when the network or archive is unavailable.

Timing semantics: an event dated year Y means the new state first appears
in the year-Y composite, i.e. the physical change happened between the
Y-1 and Y composites. "Before" chips are drawn from the first half of
year Y-1 (safely before), "after" chips from year Y+1 (safely after).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.windows import Window, from_bounds

log = logging.getLogger(__name__)

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"


def search_best_scene(
    bbox: tuple[float, float, float, float],
    date_start: str,
    date_end: str,
    max_cloud: float = 20.0,
) -> dict | None:
    """Lowest-cloud L2A scene covering bbox in a date range, or None."""
    try:
        resp = requests.post(
            STAC_URL,
            json={
                "collections": [COLLECTION],
                "bbox": list(bbox),
                "datetime": f"{date_start}T00:00:00Z/{date_end}T23:59:59Z",
                "query": {"eo:cloud_cover": {"lt": max_cloud}},
                "limit": 1,
                "sortby": [
                    {"field": "properties.eo:cloud_cover", "direction": "asc"}
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        feats = resp.json().get("features", [])
        return feats[0] if feats else None
    except requests.RequestException as err:
        log.warning("STAC search failed (%s–%s): %s", date_start, date_end, err)
        return None


def fetch_visual_chip(
    item: dict, bbox: tuple[float, float, float, float], out_path: Path
) -> dict | None:
    """Save a true-color PNG chip of `bbox` from a STAC item's visual asset."""
    href = item.get("assets", {}).get("visual", {}).get("href")
    if not href:
        return None
    try:
        with rasterio.open(href) as src:
            tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            xs, ys = zip(*(tr.transform(lon, lat) for lon, lat in
                           [(bbox[0], bbox[1]), (bbox[2], bbox[3]),
                            (bbox[0], bbox[3]), (bbox[2], bbox[1])]))
            win = (
                from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
                .round_offsets()
                .round_lengths()
                .intersection(Window(0, 0, src.width, src.height))
            )
            data = src.read([1, 2, 3], window=win)  # uint8 RGB
    except rasterio.errors.RasterioIOError as err:
        log.warning("chip read failed for %s: %s", item.get("id"), err)
        return None
    if data.size == 0:
        return None
    rgb = np.moveaxis(data, 0, -1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.imsave(out_path, rgb)
    return {
        "file": out_path.name,
        "scene_id": item.get("id"),
        "date": item.get("properties", {}).get("datetime", "")[:10],
        "cloud_cover": item.get("properties", {}).get("eo:cloud_cover"),
    }


def evidence_for_hotspot(
    hotspot: dict, out_dir: Path, chip_half_deg: float = 0.006
) -> dict | None:
    """Before/after chips for one hotspot; returns a manifest entry or None.

    chip_half_deg ≈ 650 m of context around the hotspot centre.
    """
    lon, lat = hotspot["lon"], hotspot["lat"]
    year = hotspot["dominant_year"]
    bbox = (lon - chip_half_deg, lat - chip_half_deg, lon + chip_half_deg, lat + chip_half_deg)

    before_item = search_best_scene(bbox, f"{year - 1}-01-01", f"{year - 1}-06-30")
    if before_item is None:  # widen to the year before that
        before_item = search_best_scene(bbox, f"{year - 2}-01-01", f"{year - 1}-06-30")
    after_item = search_best_scene(bbox, f"{year + 1}-01-01", f"{year + 1}-12-31")
    if after_item is None:
        after_item = search_best_scene(bbox, f"{year}-07-01", f"{year + 1}-12-31")
    if before_item is None or after_item is None:
        log.info("hotspot %s: no usable scenes for evidence", hotspot.get("rank"))
        return None

    rank = hotspot["rank"]
    before = fetch_visual_chip(before_item, bbox, out_dir / f"hotspot{rank}_before.png")
    after = fetch_visual_chip(after_item, bbox, out_dir / f"hotspot{rank}_after.png")
    if not before or not after:
        return None
    return {
        "rank": rank,
        "lat": lat,
        "lon": lon,
        "transition": f"{hotspot['dominant_from']} → {hotspot['dominant_to']}",
        "estimated_window": f"{year - 1}–{year}",
        "before": before,
        "after": after,
        "note": (
            "True-color Sentinel-2 scenes bracketing the estimated transition "
            "window (Copernicus Sentinel data, ESA)."
        ),
    }
