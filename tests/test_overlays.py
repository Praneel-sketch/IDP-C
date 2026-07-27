import json

import numpy as np
import rasterio
from rasterio import Affine

from citychange.config import BBox
from citychange.landstate import BUILT, VEGETATION
from citychange.overlays import MAX_OVERLAY_PX, OverlayWriter, _latlon_grid


def _writer(tmp_path, h=40, w=40):
    bbox = BBox(west=77.0, south=13.0, east=77.01, north=13.01)
    transform = Affine(10.0, 0.0, 700000.0, 0.0, -10.0, 1500000.0)
    crs = rasterio.crs.CRS.from_epsg(32643)
    return OverlayWriter(tmp_path / "overlays", bbox, transform, crs), (h, w)


def test_overlay_writer_produces_manifest_and_pngs(tmp_path):
    ow, (h, w) = _writer(tmp_path)
    states = np.full((h, w), VEGETATION, dtype=np.uint8)
    states[:, w // 2:] = BUILT
    event = states == BUILT
    ow.add_states(2020, states)
    ow.add_change(event, states)
    ow.add_year_of_change(np.where(event, 2020, 0).astype(np.uint16), (2017, 2020, 2023))
    ow.add_confidence(np.where(event, 3, 0).astype(np.uint8))
    ow.add_anomalies(np.zeros((h, w), dtype=bool))
    ow.add_clusters(np.zeros((2, 2), dtype=np.int32), 20, (h, w))
    manifest_path = ow.write_manifest()

    manifest = json.loads(manifest_path.read_text())
    assert manifest["bounds"] == [[13.0, 77.0], [13.01, 77.01]]
    for key in ("states_2020", "change", "year_of_change", "confidence",
                "anomalies", "clusters"):
        f = tmp_path / "overlays" / manifest["layers"][key]["file"]
        assert f.exists() and f.stat().st_size > 0, key


def test_year_of_change_legend_colors(tmp_path):
    ow, (h, w) = _writer(tmp_path)
    yoc = np.zeros((h, w), dtype=np.uint16)
    yoc[0, 0] = 2018
    ow.add_year_of_change(yoc, (2017, 2018, 2019))
    legend = ow.manifest["layers"]["year_of_change"]["legend"]
    assert set(legend) == {"2017", "2018", "2019"}
    assert all(v.startswith("#") for v in legend.values())


def test_latlon_grid_preserves_aspect_when_capped():
    bbox = BBox(west=0.0, south=0.0, east=0.2, north=0.1)
    h, w = 2000, 4000  # wide source, above cap
    _tfm, width, height = _latlon_grid(bbox, (h, w))
    assert width == MAX_OVERLAY_PX
    assert height == MAX_OVERLAY_PX // 2  # 2:1 aspect kept
