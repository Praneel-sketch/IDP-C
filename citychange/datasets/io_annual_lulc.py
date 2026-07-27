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
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform
from pyproj import Transformer

from citychange.config import BBox, RegionConfig, data_dir
from citychange.tiles import (
    band_lat_range,
    tiles_for_bbox,
    utm_zone,
    zone_lon_range,
)

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


def _bbox_to_crs(bbox: BBox, transformer: Transformer) -> tuple[float, float, float, float]:
    """Project a WGS84 bbox: corners + edge midpoints for curvature safety."""
    pts = [
        (bbox.west, bbox.south), (bbox.west, bbox.north),
        (bbox.east, bbox.south), (bbox.east, bbox.north),
        ((bbox.west + bbox.east) / 2, bbox.south),
        ((bbox.west + bbox.east) / 2, bbox.north),
        (bbox.west, (bbox.south + bbox.north) / 2),
        (bbox.east, (bbox.south + bbox.north) / 2),
    ]
    xs, ys = zip(*(transformer.transform(lon, lat) for lon, lat in pts))
    return min(xs), min(ys), max(xs), max(ys)


def _target_grid(bbox: BBox) -> tuple[rasterio.crs.CRS, rasterio.Affine, int, int]:
    """Analysis grid for an arbitrary AOI: the UTM zone of the AOI centre,
    10 m pixels, snapped to the 10 m lattice."""
    lon_c, lat_c = bbox.center
    epsg = (32600 if lat_c >= 0 else 32700) + utm_zone(lon_c)
    crs = rasterio.crs.CRS.from_epsg(epsg)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x0, y0, x1, y1 = _bbox_to_crs(bbox, tr)
    res = 10.0
    x0, y0 = np.floor(x0 / res) * res, np.floor(y0 / res) * res
    x1, y1 = np.ceil(x1 / res) * res, np.ceil(y1 / res) * res
    width = int(round((x1 - x0) / res))
    height = int(round((y1 - y0) / res))
    transform = rasterio.Affine(res, 0, x0, 0, -res, y1)
    return crs, transform, width, height


def _tile_wgs84_bounds(tile: str) -> BBox:
    zone = int(tile[:-1])
    w, e = zone_lon_range(zone)
    s, n = band_lat_range(tile[-1])
    return BBox(west=w, south=s, east=e, north=n)


def _intersect_bbox(a: BBox, b: BBox, margin_deg: float = 0.003) -> BBox | None:
    """Intersection of two WGS84 bboxes, padded by a small margin so
    reprojection at tile seams has source pixels to sample from."""
    west = max(a.west, b.west - margin_deg)
    east = min(a.east, b.east + margin_deg)
    south = max(a.south, b.south - margin_deg)
    north = min(a.north, b.north + margin_deg)
    if west >= east or south >= north:
        return None
    return BBox(west=west, south=south, east=east, north=north)


def _fetch_year_mosaic(
    region: RegionConfig,
    year: int,
    tiles: list[str],
    crs: rasterio.crs.CRS,
    transform: rasterio.Affine,
    width: int,
    height: int,
) -> np.ndarray:
    """Assemble one year of observations onto the target grid from one or
    more product tiles, reprojecting (nearest-neighbour — class data) where
    the tile CRS differs from the target CRS."""
    out = np.zeros((height, width), dtype=np.uint8)
    for tile in tiles:
        part = _intersect_bbox(region.bbox, _tile_wgs84_bounds(tile))
        if part is None:
            continue
        url = product_url(tile, year)
        with rasterio.open(url) as src_probe:
            src_crs = src_probe.crs
        tr = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
        data, tfm, src_crs = _read_remote_window(url, _bbox_to_crs(part, tr))
        if data.size == 0:
            continue
        piece = np.zeros((height, width), dtype=np.uint8)
        reproject(
            source=data,
            destination=piece,
            src_transform=tfm,
            src_crs=src_crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.nearest,
            src_nodata=0,
            dst_nodata=0,
        )
        # Later tiles only fill pixels still empty — no double-write at seams.
        out = np.where(out == 0, piece, out)
    return out


def fetch_annual_stack(region: RegionConfig) -> AnnualStack:
    """Fetch (or load from cache) co-registered annual class grids for an
    arbitrary in-coverage AOI.

    Single-tile AOIs are read directly on the product's native grid (no
    resampling). Multi-tile AOIs are mosaicked onto a 10 m UTM grid in the
    AOI-centre zone with nearest-neighbour reprojection. Either way, all
    years share one grid, verified with hard assertions.
    """
    tiles = tiles_for_bbox(region.bbox)
    single = len(tiles) == 1
    log.info("AOI covered by tile(s): %s", ", ".join(tiles))

    grids: dict[int, np.ndarray] = {}
    ref_transform: rasterio.Affine | None = None
    ref_crs: rasterio.crs.CRS | None = None
    to_utm: Transformer | None = None
    mosaic_grid: tuple | None = None

    for year in region.years:
        cache = _cache_path(region.name, "+".join(tiles), year)
        if cache.exists():
            with rasterio.open(cache) as src:
                data = src.read(1)
                tfm, crs = src.transform, src.crs
            log.info("year %d: loaded from cache %s", year, cache)
        elif single:
            url = product_url(tiles[0], year)
            log.info("year %d: fetching window from %s", year, url)
            if to_utm is None:
                with rasterio.open(url) as src:
                    to_utm = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            data, tfm, crs = _read_remote_window(
                url, _bbox_to_crs(region.bbox, to_utm)
            )
            _write_cache(cache, data, tfm, crs)
            log.info("year %d: cached %s (%d x %d px)", year, cache, *data.shape)
        else:
            if mosaic_grid is None:
                mosaic_grid = _target_grid(region.bbox)
            crs, tfm, width, height = mosaic_grid
            log.info(
                "year %d: mosaicking %d tiles onto %s (%d x %d px)",
                year, len(tiles), crs, height, width,
            )
            data = _fetch_year_mosaic(region, year, tiles, crs, tfm, width, height)
            _write_cache(cache, data, tfm, crs)

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
        tile="+".join(tiles),
        years=region.years,
        grids=grids,
        crs=ref_crs,
        transform=ref_transform,
    )
