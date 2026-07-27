"""Web map overlays: analysis rasters reprojected to EPSG:4326 RGBA PNGs.

The frontend (Leaflet) drapes each PNG over the map with its WGS84 bounds.
For AOIs up to a few tens of km this is geometrically accurate and avoids
running a tile server. Nodata / no-signal pixels are fully transparent so
the basemap shows through.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from citychange.config import BBox
from citychange.landstate import STATE_COLORS

log = logging.getLogger(__name__)

MAX_OVERLAY_PX = 1600

TIER_COLORS = {1: "#d73027", 2: "#fdae61", 3: "#1a9850"}  # low, medium, high
ANOMALY_COLOR = "#8b2fc9"
CLUSTER_COLORS = [
    "#4477aa", "#ee6677", "#228833", "#ccbb44", "#66ccee", "#aa3377", "#bbbbbb",
]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _latlon_grid(bbox: BBox, src_shape: tuple[int, int]) -> tuple[rasterio.Affine, int, int]:
    """A 4326 grid roughly matching the source resolution, capped in size.

    Both dimensions are scaled by the same factor so pixel aspect (and thus
    the overlay's geometry) is preserved for non-square AOIs."""
    h, w = src_shape
    scale = min(1.0, MAX_OVERLAY_PX / max(h, w))
    height = max(int(round(h * scale)), 1)
    width = max(int(round(w * scale)), 1)
    transform = rasterio.transform.from_bounds(
        bbox.west, bbox.south, bbox.east, bbox.north, width, height
    )
    return transform, width, height


def _to_4326(
    data: np.ndarray,
    src_transform: rasterio.Affine,
    src_crs,
    bbox: BBox,
    nodata: int = 0,
) -> np.ndarray:
    transform, width, height = _latlon_grid(bbox, data.shape)
    out = np.full((height, width), nodata, dtype=data.dtype)
    reproject(
        source=data,
        destination=out,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=transform,
        dst_crs="EPSG:4326",
        resampling=Resampling.nearest,
        src_nodata=nodata,
        dst_nodata=nodata,
    )
    return out


def _write_rgba(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.imsave(path, rgba)


def _categorical_rgba(
    data: np.ndarray, colors: dict[int, str], alpha: int = 255
) -> np.ndarray:
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
    for value, color in colors.items():
        r, g, b = _hex_to_rgb(color)
        mask = data == value
        rgba[mask] = (r, g, b, alpha)
    return rgba


class OverlayWriter:
    """Accumulates overlays for one region bundle and writes the manifest."""

    def __init__(self, out_dir: Path, bbox: BBox, src_transform, src_crs):
        self.dir = out_dir
        self.bbox = bbox
        self.src_transform = src_transform
        self.src_crs = src_crs
        self.manifest: dict[str, object] = {
            "bounds": [[bbox.south, bbox.west], [bbox.north, bbox.east]],
            "layers": {},
        }

    def _add(self, key: str, filename: str, legend: dict | None, **extra) -> None:
        layers: dict = self.manifest["layers"]  # type: ignore[assignment]
        layers[key] = {"file": filename, "legend": legend or {}, **extra}

    def add_states(self, year: int, state_grid: np.ndarray) -> None:
        data = _to_4326(state_grid, self.src_transform, self.src_crs, self.bbox)
        rgba = _categorical_rgba(data, {k: v for k, v in STATE_COLORS.items() if k != 0})
        name = f"states_{year}.png"
        _write_rgba(self.dir / name, rgba)
        self._add(f"states_{year}", name, None, year=year)

    def add_change(self, event_mask: np.ndarray, to_state: np.ndarray) -> None:
        layer = np.where(event_mask, to_state, 0).astype(np.uint8)
        data = _to_4326(layer, self.src_transform, self.src_crs, self.bbox)
        rgba = _categorical_rgba(data, {k: v for k, v in STATE_COLORS.items() if k != 0})
        _write_rgba(self.dir / "change.png", rgba)
        self._add("change", "change.png", None)

    def add_year_of_change(self, yoc: np.ndarray, years: tuple[int, ...]) -> None:
        data = _to_4326(yoc.astype(np.uint16), self.src_transform, self.src_crs, self.bbox)
        cmap = matplotlib.colormaps["viridis"]
        rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
        legend = {}
        span = max(years[-1] - years[0], 1)
        for year in years:
            frac = (year - years[0]) / span
            r, g, b, _ = (np.array(cmap(frac)) * 255).astype(np.uint8)
            rgba[data == year] = (r, g, b, 255)
            legend[str(year)] = "#%02x%02x%02x" % (r, g, b)
        _write_rgba(self.dir / "year_of_change.png", rgba)
        self._add("year_of_change", "year_of_change.png", legend)

    def add_confidence(self, tiers: np.ndarray) -> None:
        data = _to_4326(tiers, self.src_transform, self.src_crs, self.bbox)
        rgba = _categorical_rgba(data, TIER_COLORS)
        _write_rgba(self.dir / "confidence.png", rgba)
        self._add(
            "confidence",
            "confidence.png",
            {"low": TIER_COLORS[1], "medium": TIER_COLORS[2], "high": TIER_COLORS[3]},
        )

    def add_anomalies(self, mask: np.ndarray) -> None:
        data = _to_4326(mask.astype(np.uint8), self.src_transform, self.src_crs, self.bbox)
        rgba = _categorical_rgba(data, {1: ANOMALY_COLOR})
        _write_rgba(self.dir / "anomalies.png", rgba)
        self._add("anomalies", "anomalies.png", {"rare trajectory": ANOMALY_COLOR})

    def add_clusters(
        self, labels_grid: np.ndarray, block_px: int, pixel_shape: tuple[int, int]
    ) -> None:
        # labels_grid is the coarse block grid; upscale to the pixel grid
        # (cropping the ragged edge) so georeferencing stays exact.
        up = np.kron(
            labels_grid.astype(np.int16) + 1,
            np.ones((block_px, block_px), dtype=np.int16),
        )[: pixel_shape[0], : pixel_shape[1]].astype(np.uint8)
        data = _to_4326(up, self.src_transform, self.src_crs, self.bbox)
        n = int(labels_grid.max()) + 1
        colors = {i + 1: CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(n)}
        rgba = _categorical_rgba(data, colors, alpha=160)
        _write_rgba(self.dir / "clusters.png", rgba)
        self._add(
            "clusters",
            "clusters.png",
            {f"pattern {i + 1}": colors[i + 1] for i in range(n)},
        )

    def write_manifest(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / "overlays.json"
        path.write_text(json.dumps(self.manifest, indent=2))
        return path
