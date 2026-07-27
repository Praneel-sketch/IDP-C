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
    """Tile containing the whole bbox; raises if it spans several.

    Kept for the single-tile fast path — arbitrary AOIs go through
    tiles_for_bbox() + mosaicking in the acquisition layer.
    """
    tiles = tiles_for_bbox(bbox)
    if len(tiles) != 1:
        raise NotImplementedError(
            f"bbox spans multiple UTM tiles {tiles}; use the mosaic path"
        )
    return tiles[0]


def band_lat_range(band: str) -> tuple[float, float]:
    """South/north latitude limits of an MGRS band letter."""
    if band == "X":
        return 72.0, 84.0
    idx = _LAT_BANDS.index(band)
    return -80.0 + idx * 8, -80.0 + (idx + 1) * 8


def zone_lon_range(zone: int) -> tuple[float, float]:
    """West/east longitude limits of a UTM zone number."""
    return -180.0 + (zone - 1) * 6, -180.0 + zone * 6


def tiles_for_bbox(bbox: BBox) -> list[str]:
    """All UTM zone/band tiles intersecting a bbox, west→east, south→north."""
    z0, z1 = utm_zone(bbox.west), utm_zone(bbox.east)
    b0, b1 = lat_band(bbox.south), lat_band(bbox.north)
    bands = _LAT_BANDS[_LAT_BANDS.index(b0) : _LAT_BANDS.index(b1) + 1]
    return [f"{z}{b}" for b in bands for z in range(z0, z1 + 1)]
