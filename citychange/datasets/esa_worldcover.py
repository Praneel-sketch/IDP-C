"""ESA WorldCover: independent land-cover product used for cross-validation.

Two vintages exist: 2020 (v100) and 2021 (v200), 10 m, global, CC BY 4.0,
produced by the ESA WorldCover consortium from Sentinel-1 + Sentinel-2.
Distributed as public COGs on AWS S3 (eu-central-1), tiled in 3°x3° cells
named by their south-west corner.

Verified empirically (2026-07, from this repo): HTTP 206 range requests on
both vintages, e.g.
  .../v100/2020/map/ESA_WorldCover_10m_2020_v100_N12E075_Map.tif

IMPORTANT: WorldCover is *not* ground truth either — it is an independent
derived product with its own error profile. Agreement between IO Annual
LULC and WorldCover is evidence of reliability; disagreement flags where
per-pixel claims are weak. The two products also differ systematically
(e.g. WorldCover maps far more grassland where IO maps rangeland-as-
vegetation), which is why comparison happens in CityChange canonical state
space.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds

from citychange.config import BBox, data_dir
from citychange.landstate import (
    BARE,
    BUILT,
    CROPS,
    NODATA,
    SNOW_ICE,
    VEGETATION,
    WATER,
)

log = logging.getLogger(__name__)

_BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"
_VINTAGE = {2020: "v100", 2021: "v200"}
AVAILABLE_YEARS = tuple(_VINTAGE)

# WorldCover class codes -> CityChange canonical states.
# Wetland/mangrove/shrub/grass all fold into vegetation, mirroring how the
# IO product's rangeland/flooded-vegetation are folded (landstate.py).
WORLDCOVER_TO_STATE: dict[int, int] = {
    0: NODATA,
    10: VEGETATION,   # tree cover
    20: VEGETATION,   # shrubland
    30: VEGETATION,   # grassland
    40: CROPS,        # cropland
    50: BUILT,        # built-up
    60: BARE,         # bare / sparse vegetation
    70: SNOW_ICE,     # snow and ice
    80: WATER,        # permanent water bodies
    90: VEGETATION,   # herbaceous wetland
    95: VEGETATION,   # mangroves
    100: VEGETATION,  # moss and lichen
}

_LUT = np.zeros(256, dtype=np.uint8)
for code, state in WORLDCOVER_TO_STATE.items():
    _LUT[code] = state


def _tile_name(lat_sw: int, lon_sw: int) -> str:
    ns = f"N{lat_sw:02d}" if lat_sw >= 0 else f"S{-lat_sw:02d}"
    ew = f"E{lon_sw:03d}" if lon_sw >= 0 else f"W{-lon_sw:03d}"
    return ns + ew


def tile_url(year: int, lat_sw: int, lon_sw: int) -> str:
    v = _VINTAGE[year]
    name = _tile_name(lat_sw, lon_sw)
    return f"{_BASE}/{v}/{year}/map/ESA_WorldCover_10m_{year}_{v}_{name}_Map.tif"


def _tiles_for_bbox(bbox: BBox) -> list[tuple[int, int]]:
    lat0 = math.floor(bbox.south / 3) * 3
    lon0 = math.floor(bbox.west / 3) * 3
    out = []
    lat = lat0
    while lat < bbox.north:
        lon = lon0
        while lon < bbox.east:
            out.append((lat, lon))
            lon += 3
        lat += 3
    return out


def fetch_worldcover_states(
    region_name: str,
    bbox: BBox,
    year: int,
    dst_crs,
    dst_transform,
    dst_shape: tuple[int, int],
) -> np.ndarray:
    """WorldCover observations for a bbox, remapped to canonical states and
    reprojected onto the caller's analysis grid. Cached locally."""
    if year not in _VINTAGE:
        raise ValueError(f"WorldCover has vintages {AVAILABLE_YEARS}, not {year}")
    cache = (
        data_dir() / "cache" / "esa_worldcover" / region_name / f"wc_{year}.tif"
    )
    if cache.exists():
        with rasterio.open(cache) as src:
            if src.shape == dst_shape and src.transform == dst_transform:
                return src.read(1)
        log.info("worldcover cache stale for %s/%d — refetching", region_name, year)

    out = np.zeros(dst_shape, dtype=np.uint8)
    for lat_sw, lon_sw in _tiles_for_bbox(bbox):
        url = tile_url(year, lat_sw, lon_sw)
        log.info("worldcover %d: reading window from %s", year, url)
        with rasterio.open(url) as src:
            win = (
                from_bounds(
                    max(bbox.west, lon_sw) - 0.002,
                    max(bbox.south, lat_sw) - 0.002,
                    min(bbox.east, lon_sw + 3) + 0.002,
                    min(bbox.north, lat_sw + 3) + 0.002,
                    src.transform,
                )
                .round_offsets()
                .round_lengths()
                .intersection(Window(0, 0, src.width, src.height))
            )
            data = src.read(1, window=win)
            src_transform = rasterio.windows.transform(win, src.transform)
            piece = np.zeros(dst_shape, dtype=np.uint8)
            reproject(
                source=data,
                destination=piece,
                src_transform=src_transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.nearest,
                src_nodata=0,
                dst_nodata=0,
            )
            out = np.where(out == 0, piece, out)

    states = _LUT[out]
    cache.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "width": dst_shape[1],
        "height": dst_shape[0],
        "count": 1,
        "dtype": "uint8",
        "crs": dst_crs,
        "transform": dst_transform,
        "nodata": 0,
        "compress": "deflate",
    }
    tmp = cache.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(states, 1)
    tmp.replace(cache)
    return states
