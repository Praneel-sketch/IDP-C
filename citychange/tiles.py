"""UTM zone/latitude-band tile arithmetic.

The Impact Observatory annual land-cover product is distributed as one
GeoTIFF per UTM grid cell, named like "43P": UTM zone number (6 degrees of
longitude) plus the MGRS latitude band letter (8 degrees of latitude).
"""

from __future__ import annotations

from citychange.config import BBox

# MGRS latitude bands from 80S to 84N. I and O are skipped by convention.
_LAT_BANDS = "CDEFGHJKLMNPQRSTUVWX"


def utm_zone(lon: float) -> int:
    """UTM zone number for a longitude (ignores the Norway/Svalbard exceptions,
    which do not affect the tile naming of this product's rasters)."""
    if not -180 <= lon <= 180:
        raise ValueError(f"longitude out of range: {lon}")
    return min(int((lon + 180) // 6) + 1, 60)


def lat_band(lat: float) -> str:
    """MGRS latitude band letter for a latitude."""
    if not -80 <= lat <= 84:
        raise ValueError(f"latitude outside MGRS bands (-80..84): {lat}")
    if lat >= 72:
        return "X"  # X is extended to 12 degrees (72..84)
    return _LAT_BANDS[int((lat + 80) // 8)]


def tile_id(lon: float, lat: float) -> str:
    """Tile identifier such as '43P' for a WGS84 point."""
    return f"{utm_zone(lon)}{lat_band(lat)}"


def tile_for_bbox(bbox: BBox) -> str:
    """Tile containing the whole bbox.

    v0.1 supports regions inside a single UTM tile. Multi-tile mosaicking is
    deliberately deferred (see docs/DECISIONS.md); a clear error is better
    than silently analysing a truncated region.
    """
    corners = {
        tile_id(bbox.west, bbox.south),
        tile_id(bbox.west, bbox.north),
        tile_id(bbox.east, bbox.south),
        tile_id(bbox.east, bbox.north),
    }
    if len(corners) != 1:
        raise NotImplementedError(
            f"bbox spans multiple UTM tiles {sorted(corners)}; "
            "v0.1 supports single-tile regions only — shrink or shift the bbox"
        )
    return corners.pop()
