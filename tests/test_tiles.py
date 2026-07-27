import pytest

from citychange.config import BBox
from citychange.tiles import (
    lat_band,
    tile_for_bbox,
    tile_id,
    tiles_for_bbox,
    utm_zone,
)


def test_utm_zone_known_points():
    assert utm_zone(77.7) == 43  # Bengaluru
    assert utm_zone(-0.1) == 30  # London
    assert utm_zone(-74.0) == 18  # New York
    assert utm_zone(180.0) == 60  # antimeridian edge clamps into zone 60


def test_lat_band_known_points():
    assert lat_band(13.2) == "P"  # Bengaluru
    assert lat_band(51.5) == "U"  # London
    assert lat_band(-33.9) == "H"  # Sydney
    assert lat_band(75.0) == "X"  # extended X band


def test_lat_band_skips_i_and_o():
    bands = {lat_band(lat) for lat in range(-79, 84)}
    assert "I" not in bands and "O" not in bands


def test_tile_id():
    assert tile_id(77.7, 13.2) == "43P"


def test_tile_for_bbox_single_tile():
    bbox = BBox(west=77.63, south=13.17, east=77.73, north=13.27)
    assert tile_for_bbox(bbox) == "43P"


def test_tile_for_bbox_rejects_multi_tile():
    bbox = BBox(west=77.9, south=13.0, east=78.1, north=13.2)  # crosses zone 43/44
    with pytest.raises(NotImplementedError):
        tile_for_bbox(bbox)


def test_tiles_for_bbox_enumerates_zone_crossing():
    bbox = BBox(west=77.9, south=13.0, east=78.1, north=13.2)
    assert tiles_for_bbox(bbox) == ["43P", "44P"]


def test_tiles_for_bbox_enumerates_band_crossing():
    bbox = BBox(west=10.0, south=15.9, east=10.1, north=16.1)  # crosses P/Q at 16N
    assert tiles_for_bbox(bbox) == ["32P", "32Q"]


def test_tiles_for_bbox_four_corner():
    bbox = BBox(west=77.9, south=15.9, east=78.1, north=16.1)
    assert set(tiles_for_bbox(bbox)) == {"43P", "44P", "43Q", "44Q"}


def test_tiles_for_bbox_southern_hemisphere():
    bbox = BBox(west=-63.3, south=-9.35, east=-63.2, north=-9.25)  # Rondônia
    assert tiles_for_bbox(bbox) == ["20L"]


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        utm_zone(200)
    with pytest.raises(ValueError):
        lat_band(-85)
