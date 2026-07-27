import json

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CITYCHANGE_DATA_DIR", str(tmp_path))
    # Build a minimal fake bundle the API can serve.
    bundle = tmp_path / "outputs" / "testregion"
    (bundle / "overlays").mkdir(parents=True)
    summary = {
        "region": "testregion",
        "display_name": "Test Region",
        "bbox": {"west": 0, "south": 0, "east": 0.1, "north": 0.1},
        "years": [2017, 2023],
        "change_fractions": {"event_based": 0.1},
        "generated_at": "2026-01-01T00:00:00+00:00",
    }
    (bundle / "summary.json").write_text(json.dumps(summary))
    (bundle / "overlays" / "overlays.json").write_text(
        json.dumps({"bounds": [[0, 0], [0.1, 0.1]], "layers": {}})
    )
    (bundle / "overlays" / "change.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")

    from citychange import server

    return TestClient(server.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_regions_lists_bundle(client):
    r = client.get("/api/regions")
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["region"] == "testregion"
    assert rows[0]["display_name"] == "Test Region"


def test_summary_roundtrip(client):
    r = client.get("/api/region/testregion/summary")
    assert r.status_code == 200
    assert r.json()["display_name"] == "Test Region"


def test_overlay_manifest_and_file(client):
    assert client.get("/api/region/testregion/overlays").status_code == 200
    r = client.get("/api/region/testregion/overlays/change.png")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_unknown_region_404(client):
    assert client.get("/api/region/nope/summary").status_code == 404


def test_bad_region_name_rejected(client):
    assert client.get("/api/region/..%2Fetc/summary").status_code in (400, 404)


def test_path_traversal_blocked(client):
    r = client.get("/api/region/testregion/overlays/..%2F..%2Fsummary.json")
    assert r.status_code in (400, 404)


def test_analyze_rejects_huge_aoi(client):
    r = client.post(
        "/api/analyze",
        json={"west": 0, "south": 0, "east": 5, "north": 5},
    )
    assert r.status_code == 400
    assert "km²" in r.json()["detail"]


def test_analyze_rejects_bad_years(client):
    r = client.post(
        "/api/analyze",
        json={"west": 0, "south": 0, "east": 0.05, "north": 0.05, "years": [1999]},
    )
    assert r.status_code == 400


def test_analyze_returns_done_for_existing_bundle(client):
    r = client.post(
        "/api/analyze",
        json={"west": 0, "south": 0, "east": 0.05, "north": 0.05, "name": "testregion"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"
