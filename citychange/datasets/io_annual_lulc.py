"""Acquisition of the Impact Observatory / Esri 10 m Annual Land Use Land
Cover product (2017-2023), the land-state backbone of CityChange v0.1.

Access strategy
---------------
The product is published as cloud-optimized GeoTIFFs (COGs) on a public
Azure blob container, one file per UTM tile per year, no credentials
required (license: CC BY 4.0). Because the files are COGs with internal
256 px tiling, rasterio can fetch only the byte ranges covering a bounding
box — a 10 km x 10 km AOI costs a few MB instead of a multi-GB tile
download.

Every windowed read is cached locally as a small GeoTIFF, so re-runs (and
tests against cached data) are fully offline.

Verified empirically (2026-07): HTTP 200 for years 2017-2023, HTTP 206 on
range requests, uint8 with nodata=0, EPSG:326xx, 10 m pixels, embedded
colormap matching landstate.SOURCE_COLORS.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform
from pyproj import Transformer

from citychange.config import RegionConfig, data_dir
from citychange.tiles import tile_for_bbox

log = logging.getLogger(__name__)

BASE_URL = "https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003"
AVAILABLE_YEARS = tuple(range(2017, 2024))
_RETRIES = 4
_RETRY_BASE_SLEEP = 2.0


def product_url(tile: str, year: int) -> str:
    """Remote COG URL for one UTM tile and one calendar year."""
    if year not in AVAILABLE_YEARS:
        raise ValueError(
            f"year {year} not available in {BASE_URL} (has {AVAILABLE_YEARS[0]}-{AVAILABLE_YEARS[-1]})"
        )
    return f"{BASE_URL}/lc{year}/{tile}_{year}0101-{year + 1}0101.tif"


@dataclass(frozen=True)
class AnnualStack:
    """Co-registered annual class grids for one region.

    grids[year] is a uint8 array of source class codes; every year shares
    the same shape, CRS and affine transform (this is asserted at load
    time, not assumed).
    """

    region: str
    tile: str
    years: tuple[int, ...]
    grids: dict[int, np.ndarray]
    crs: rasterio.crs.CRS
    transform: rasterio.Affine

    @property
    def shape(self) -> tuple[int, int]:
        return self.grids[self.years[0]].shape

    def pixel_center_lonlat(self, row: float, col: float) -> tuple[float, float]:
        """WGS84 coordinates of a (row, col) pixel center."""
        x, y = self.transform * (col + 0.5, row + 0.5)
        to_wgs = Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)
        lon, lat = to_wgs.transform(x, y)
        return lon, lat


def _cache_path(region_name: str, tile: str, year: int) -> Path:
    return data_dir() / "cache" / "io_annual_lulc" / region_name / f"{tile}_{year}.tif"


def _read_remote_window(url: str, bbox_utm: tuple[float, float, float, float]) -> tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS]:
    """Read one bounding-box window from a remote COG, with retries for
    transient network failures."""
    last_err: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            with rasterio.open(url) as src:
                win = (
                    from_bounds(*bbox_utm, src.transform)
                    .round_offsets()
                    .round_lengths()
                )
                # Clamp to the raster in case the AOI touches a tile edge.
                full = Window(0, 0, src.width, src.height)
                win = win.intersection(full)
                data = src.read(1, window=win)
                return data, window_transform(win, src.transform), src.crs
        except rasterio.errors.RasterioIOError as err:
            last_err = err
            if attempt < _RETRIES:
                sleep = _RETRY_BASE_SLEEP * (2**attempt)
                log.warning("read failed (%s), retrying in %.0fs: %s", url, sleep, err)
                time.sleep(sleep)
    raise RuntimeError(f"failed to read {url} after {_RETRIES + 1} attempts") from last_err


def _write_cache(path: Path, data: np.ndarray, transform: rasterio.Affine, crs: rasterio.crs.CRS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "width": data.shape[1],
        "height": data.shape[0],
        "count": 1,
        "dtype": "uint8",
        "crs": crs,
        "transform": transform,
        "nodata": 0,
        "compress": "deflate",
    }
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(data, 1)
    tmp.replace(path)  # atomic: an interrupted run never leaves a corrupt cache entry


def fetch_annual_stack(region: RegionConfig) -> AnnualStack:
    """Fetch (or load from cache) the annual class grids for a region.

    Returns co-registered grids: identical shape/CRS/transform across all
    years, verified with hard assertions rather than assumed.
    """
    tile = tile_for_bbox(region.bbox)
    to_utm: Transformer | None = None

    grids: dict[int, np.ndarray] = {}
    ref_transform: rasterio.Affine | None = None
    ref_crs: rasterio.crs.CRS | None = None

    for year in region.years:
        cache = _cache_path(region.name, tile, year)
        if cache.exists():
            with rasterio.open(cache) as src:
                data = src.read(1)
                tfm, crs = src.transform, src.crs
            log.info("year %d: loaded from cache %s", year, cache)
        else:
            url = product_url(tile, year)
            log.info("year %d: fetching window from %s", year, url)
            if to_utm is None:
                # Resolve the product CRS from the first remote file.
                with rasterio.open(url) as src:
                    to_utm = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            b = region.bbox
            xs, ys = zip(*(to_utm.transform(lon, lat) for lon, lat in
                           [(b.west, b.south), (b.west, b.north), (b.east, b.south), (b.east, b.north)]))
            bbox_utm = (min(xs), min(ys), max(xs), max(ys))
            data, tfm, crs = _read_remote_window(url, bbox_utm)
            _write_cache(cache, data, tfm, crs)
            log.info("year %d: cached %s (%d x %d px)", year, cache, *data.shape)

        if ref_transform is None:
            ref_transform, ref_crs = tfm, crs
        else:
            if tfm != ref_transform or crs != ref_crs or data.shape != grids[region.years[0]].shape:
                raise RuntimeError(
                    f"year {year} grid is not co-registered with {region.years[0]} "
                    f"(transform/CRS/shape mismatch) — clear the cache for region "
                    f"'{region.name}' and re-run"
                )
        grids[year] = data

    assert ref_transform is not None and ref_crs is not None
    return AnnualStack(
        region=region.name,
        tile=tile,
        years=region.years,
        grids=grids,
        crs=ref_crs,
        transform=ref_transform,
    )
