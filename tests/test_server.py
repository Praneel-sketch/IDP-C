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


def test_geocode_proxies_and_caches(client, monkeypatch):
    from citychange import server

    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"display_name": "Testville", "lat": "1.5", "lon": "2.5", "type": "city"}]

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        assert "nominatim" in url
        assert "CityChange" in headers["User-Agent"]
        return FakeResp()

    monkeypatch.setattr(server._requests, "get", fake_get)
    server._geo_cache.clear()

    r1 = client.get("/api/geocode", params={"q": "Testville"})
    assert r1.status_code == 200
    assert r1.json()[0] == {"display_name": "Testville", "lat": 1.5, "lon": 2.5, "type": "city"}
    r2 = client.get("/api/geocode", params={"q": "testville"})  # cache hit (case-folded)
    assert r2.status_code == 200
    assert calls["n"] == 1


def test_prewarm_queues_benchmark_regions_on_empty_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("CITYCHANGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CITYCHANGE_PREWARM", "1")
    from citychange import server

    ran: list[str] = []
    monkeypatch.setattr(server, "run_analysis", lambda region, params: ran.append(region.name))

    with TestClient(server.app):
        pass  # entering the context runs the lifespan startup

    import time as _t

    for _ in range(100):  # jobs run on the executor thread; wait for drain
        with server._jobs_lock:
            done = all(
                j["status"] in ("done", "error")
                for j in server._jobs.values()
                if j["id"].startswith("prewarm-")
            ) and any(j["id"].startswith("prewarm-") for j in server._jobs.values())
        if done:
            break
        _t.sleep(0.05)

    expected = sorted(p.stem for p in (server.REPO_ROOT / "configs" / "benchmark").glob("*.yaml"))
    assert sorted(ran) == expected
    with server._jobs_lock:
        server._jobs.clear()


def test_prewarm_skipped_when_bundles_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("CITYCHANGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CITYCHANGE_PREWARM", "1")
    bundle = tmp_path / "outputs" / "existing"
    bundle.mkdir(parents=True)
    (bundle / "summary.json").write_text("{}")
    from citychange import server

    called = []
    monkeypatch.setattr(server, "_enqueue_prewarm", lambda: called.append(1))
    with TestClient(server.app):
        pass
    assert not called


def test_prewarm_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CITYCHANGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CITYCHANGE_PREWARM", raising=False)
    from citychange import server

    called = []
    monkeypatch.setattr(server, "_enqueue_prewarm", lambda: called.append(1))
    with TestClient(server.app):
        pass
    assert not called


def test_geocode_failure_returns_502(client, monkeypatch):
    from citychange import server
    import requests as req

    def fake_get(*a, **k):
        raise req.ConnectionError("no network")

    monkeypatch.setattr(server._requests, "get", fake_get)
    server._geo_cache.clear()
    r = client.get("/api/geocode", params={"q": "nowhere-at-all"})
    assert r.status_code == 502
