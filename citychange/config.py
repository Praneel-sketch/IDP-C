"""Configuration loading for CityChange pipelines.

Regions and pipeline parameters live in YAML files under configs/ so that
every run is reproducible from a checked-in configuration, never from
hardcoded coordinates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Base directory for cached rasters and generated outputs.

    Overridable with CITYCHANGE_DATA_DIR so machines with small home
    partitions can point the cache elsewhere.
    """
    return Path(os.environ.get("CITYCHANGE_DATA_DIR", REPO_ROOT / "data"))


@dataclass(frozen=True)
class BBox:
    """Geographic bounding box in WGS84 (EPSG:4326) degrees."""

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (-180 <= self.west < self.east <= 180):
            raise ValueError(f"invalid longitudes: west={self.west}, east={self.east}")
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError(f"invalid latitudes: south={self.south}, north={self.north}")

    @property
    def center(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)


@dataclass(frozen=True)
class RegionConfig:
    """One study region: where, and which annual observations to use."""

    name: str
    display_name: str
    bbox: BBox
    years: tuple[int, ...]
    # Side length (in pixels) of the coarse blocks used for hotspot detection.
    # At 10 m resolution the default 25 px block is 250 m x 250 m.
    hotspot_block_px: int = 25
    notes: str = ""

    def __post_init__(self) -> None:
        if len(self.years) < 2:
            raise ValueError("need at least two years for temporal comparison")
        if list(self.years) != sorted(set(self.years)):
            raise ValueError("years must be strictly increasing and unique")


def load_region(path: str | Path) -> RegionConfig:
    """Load a region configuration from a YAML file."""
    raw = yaml.safe_load(Path(path).read_text())
    region = raw["region"]
    b = region["bbox"]
    return RegionConfig(
        name=region["name"],
        display_name=region.get("display_name", region["name"]),
        bbox=BBox(west=b["west"], south=b["south"], east=b["east"], north=b["north"]),
        years=tuple(int(y) for y in region["years"]),
        hotspot_block_px=int(region.get("hotspot_block_px", 25)),
        notes=region.get("notes", ""),
    )
