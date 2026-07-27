"""Land-state schema for CityChange.

Two layers of representation:

1. Source classes — the raw 9-class schema of the Impact Observatory /
   Esri 10 m Annual Land Use Land Cover product (verified against the
   product rasters, including its embedded colormap). Never discarded.

2. Canonical states — CityChange's own vocabulary (built, vegetation,
   crops, water, bare, snow_ice, nodata). All temporal reasoning happens in
   this space so that a future switch of the underlying land-cover product
   (e.g. to Dynamic World or ESA WorldCover) only requires a new mapping,
   not a rewrite of the analysis layer.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Source product classes (Impact Observatory annual LULC v003, uint8 codes).
# Colors are the product's own embedded colormap.
# ---------------------------------------------------------------------------
SOURCE_CLASSES: dict[int, str] = {
    0: "nodata",
    1: "water",
    2: "trees",
    4: "flooded_vegetation",
    5: "crops",
    7: "built_area",
    8: "bare_ground",
    9: "snow_ice",
    10: "clouds",
    11: "rangeland",
}

SOURCE_COLORS: dict[int, str] = {
    1: "#419BDF",
    2: "#397D49",
    4: "#7A87C6",
    5: "#E49635",
    7: "#C4281B",
    8: "#A59B8F",
    9: "#A8EBFF",
    10: "#616161",
    11: "#E3E2C3",
}

# ---------------------------------------------------------------------------
# Canonical CityChange states.
# ---------------------------------------------------------------------------
NODATA = 0
WATER = 1
VEGETATION = 2
CROPS = 3
BUILT = 4
BARE = 5
SNOW_ICE = 6

STATE_NAMES: dict[int, str] = {
    NODATA: "nodata",
    WATER: "water",
    VEGETATION: "vegetation",
    CROPS: "crops",
    BUILT: "built",
    BARE: "bare",
    SNOW_ICE: "snow_ice",
}

STATE_LABELS: dict[int, str] = {
    WATER: "Water",
    VEGETATION: "Vegetation",
    CROPS: "Crops",
    BUILT: "Built-up",
    BARE: "Bare / open",
    SNOW_ICE: "Snow / ice",
}

STATE_COLORS: dict[int, str] = {
    NODATA: "#FFFFFF",
    WATER: "#419BDF",
    VEGETATION: "#4C8C4A",
    CROPS: "#E4B031",
    BUILT: "#C4281B",
    BARE: "#A59B8F",
    SNOW_ICE: "#A8EBFF",
}

# Source class -> canonical state.
# - trees, rangeland and flooded vegetation are all treated as vegetation in
#   v0.1: rangeland/grassland vs trees distinctions are noisy year to year
#   and not needed for the urbanization story.
# - crops stay separate because cropland -> built is a distinct, common
#   urbanization trajectory worth tracking on its own.
# - clouds (10) map to nodata: an unobservable pixel must not be treated as
#   a land state.
SOURCE_TO_STATE: dict[int, int] = {
    0: NODATA,
    1: WATER,
    2: VEGETATION,
    4: VEGETATION,
    5: CROPS,
    7: BUILT,
    8: BARE,
    9: SNOW_ICE,
    10: NODATA,
    11: VEGETATION,
}

# States participating in analysis (everything except nodata).
ANALYSIS_STATES: tuple[int, ...] = (WATER, VEGETATION, CROPS, BUILT, BARE, SNOW_ICE)


def _build_remap_lut() -> np.ndarray:
    lut = np.zeros(256, dtype=np.uint8)  # unknown codes fall back to nodata
    for src_code, state in SOURCE_TO_STATE.items():
        lut[src_code] = state
    return lut


_REMAP_LUT = _build_remap_lut()


def remap_to_states(source_grid: np.ndarray) -> np.ndarray:
    """Map a raster of source class codes to canonical CityChange states.

    Unknown source codes map to NODATA rather than raising: a future product
    version adding a class must not silently corrupt an analysis, and must
    not crash a long batch run either. Callers can detect the situation via
    the nodata fraction.
    """
    if source_grid.dtype != np.uint8:
        raise ValueError(f"expected uint8 source grid, got {source_grid.dtype}")
    return _REMAP_LUT[source_grid]
