"""End-to-end pipeline tests on synthetic data — no network.

fetch_annual_stack is monkeypatched with a synthetic AnnualStack, then the
REAL run_analysis executes every stage (events, trajectories, confidence,
clustering, figures, rasters, overlays, reports) into a tmp data dir.
"""

import json

import numpy as np
import pytest
import rasterio
from rasterio import Affine

from citychange.config import BBox, RegionConfig
from citychange.datasets.io_annual_lulc import AnnualStack
from citychange.landstate import BUILT, VEGETATION
from citychange.params import DEFAULT_PARAMS


YEARS = tuple(range(2017, 2024))


def synthetic_stack(name: str, grids: dict[int, np.ndarray]) -> AnnualStack:
    return AnnualStack(
        region=name,
        tile="43P",
        years=YEARS,
        grids=grids,
        crs=rasterio.crs.CRS.from_epsg(32643),
        transform=Affine(10.0, 0.0, 700000.0, 0.0, -10.0, 1500000.0),
    )


def region(name: str) -> RegionConfig:
    return RegionConfig(
        name=name,
        display_name=f"Synthetic {name}",
        bbox=BBox(west=77.0, south=13.0, east=77.01, north=13.01),
        years=YEARS,
    )


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CITYCHANGE_DATA_DIR", str(tmp_path))
    return tmp_path


def _patch_fetch(monkeypatch, stack: AnnualStack):
    import citychange.pipeline as pipeline

    monkeypatch.setattr(pipeline, "fetch_annual_stack", lambda _region: stack)


def test_full_pipeline_on_changing_region(data_dir, monkeypatch):
    from citychange.pipeline import run_analysis

    h = w = 60
    # IO source codes: vegetation is class 2, built is class 7.
    grids = {}
    for i, y in enumerate(YEARS):
        g = np.full((h, w), 2, dtype=np.uint8)
        if y >= 2020:
            g[:, w // 2 :] = 7  # right half converts to built in 2020
        grids[y] = g
    _patch_fetch(monkeypatch, synthetic_stack("synth_change", grids))

    summary = run_analysis(region("synth_change"), DEFAULT_PARAMS, make_evidence=False)

    assert summary["change_fractions"]["event_based"] == pytest.approx(0.5, abs=0.02)
    assert summary["peak_change_period"] == [2019, 2020]
    assert summary["hotspots"], "a coherent conversion must produce hotspots"
    assert summary["hotspots"][0]["dominant_from"] == "vegetation"
    assert summary["hotspots"][0]["dominant_to"] == "built"
    assert summary["hotspots"][0]["dominant_year"] == 2020
    assert summary["confidence"]["tier_counts"]["high"] > 0

    bundle = data_dir / "outputs" / "synth_change"
    for f in ("summary.json", "summary.md"):
        assert (bundle / f).exists()
    for fig in (
        "yearly_states.png", "trends.png", "change_map.png",
        "year_of_change.png", "volumes.png", "archetypes.png", "anomalies.png",
    ):
        assert (bundle / "figures" / fig).exists(), fig
    for r in (
        "year_of_change.tif", "from_state.tif", "to_state.tif",
        "confidence.tif", "confidence_tier.tif", "archetype.tif", "anomaly.tif",
    ):
        assert (bundle / "rasters" / r).exists(), r

    manifest = json.loads((bundle / "overlays" / "overlays.json").read_text())
    for key in ("states_2017", "states_2023", "change", "year_of_change",
                "confidence", "anomalies", "clusters"):
        assert key in manifest["layers"], key
        assert (bundle / "overlays" / manifest["layers"][key]["file"]).exists()

    # year_of_change raster is georeferenced and dates the event correctly
    with rasterio.open(bundle / "rasters" / "year_of_change.tif") as src:
        yoc = src.read(1)
        assert src.crs.to_epsg() == 32643
    assert (yoc[:, w // 2 + 1 :] == 2020).all()
    assert (yoc[:, : w // 2 - 1] == 0).all()


def test_rerun_without_force_is_noop(data_dir, monkeypatch):
    from citychange.pipeline import run_analysis

    grids = {y: np.full((30, 30), 2, dtype=np.uint8) for y in YEARS}
    _patch_fetch(monkeypatch, synthetic_stack("synth_noop", grids))
    first = run_analysis(region("synth_noop"), DEFAULT_PARAMS, make_evidence=False)
    second = run_analysis(region("synth_noop"), DEFAULT_PARAMS, make_evidence=False)
    assert first["generated_at"] == second["generated_at"]


def test_full_pipeline_on_stable_region(data_dir, monkeypatch):
    """The demo-critical boring case: a fully stable area must produce a
    complete, coherent bundle that says 'nothing much happened'."""
    from citychange.pipeline import run_analysis

    grids = {y: np.full((50, 50), 2, dtype=np.uint8) for y in YEARS}
    _patch_fetch(monkeypatch, synthetic_stack("synth_stable", grids))

    summary = run_analysis(region("synth_stable"), DEFAULT_PARAMS, make_evidence=False)

    assert summary["change_fractions"]["event_based"] == 0.0
    assert summary["peak_change_period"] is None
    assert summary["hotspots"] == []
    assert summary["anomalies"]["top_rare_signatures"] == []
    assert summary["archetype_fractions"].get("stable") == pytest.approx(1.0)

    md = (data_dir / "outputs" / "synth_stable" / "summary.md").read_text()
    assert "No persistent change events" in md
    # every figure still renders for a stable region (no crashes on empties)
    figs = list((data_dir / "outputs" / "synth_stable" / "figures").glob("*.png"))
    assert len(figs) == 7
