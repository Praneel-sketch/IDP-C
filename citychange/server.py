"""CityChange web backend.

FastAPI app serving:

- the analysis API (region bundles produced by pipeline.run_analysis),
- on-demand analysis of arbitrary bounding boxes (background jobs),
- a geocoding proxy (Nominatim, cached, rate-limited, proper user agent),
- the static no-build frontend (frontend/ at the repo root).

Run: `citychange serve` (dev) or via uvicorn/Docker (docs/DEPLOY.md).

The server contains no analysis logic — it orchestrates pipeline calls and
serves bundle artifacts from disk.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import requests as _requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from citychange import __version__
from citychange.config import REPO_ROOT, BBox, RegionConfig, data_dir, load_region
from citychange.datasets.io_annual_lulc import AVAILABLE_YEARS
from citychange.params import DEFAULT_PARAMS
from citychange.pipeline import bundle_dir, load_summary, run_analysis

log = logging.getLogger(__name__)
logging.getLogger("rasterio.session").setLevel(logging.WARNING)


def _prewarm_wanted() -> bool:
    """True when the deployment asked for demo prewarm AND the data dir has
    no analysed regions yet (a populated or volume-backed deployment is
    never re-warmed)."""
    if os.environ.get("CITYCHANGE_PREWARM", "").strip().lower() not in ("1", "true", "yes"):
        return False
    return not any((data_dir() / "outputs").glob("*/summary.json"))


def _enqueue_prewarm() -> int:
    """Queue the benchmark demo regions through the normal job machinery.

    Non-blocking: the server (and its health endpoint) is up immediately;
    regions appear in /api/regions one by one as jobs finish. Failures are
    per-job and visible in logs, never fatal to the server.
    """
    n = 0
    for cfg in sorted((REPO_ROOT / "configs" / "benchmark").glob("*.yaml")):
        try:
            region = load_region(cfg)
        except Exception:
            log.exception("prewarm: bad config %s", cfg)
            continue
        job_id = f"prewarm-{region.name}"
        with _jobs_lock:
            _jobs[job_id] = {
                "id": job_id,
                "region": region.name,
                "status": "queued",
                "started": time.time(),
            }
        _executor.submit(_run_job, job_id, region)
        n += 1
    return n


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if _prewarm_wanted():
        n = _enqueue_prewarm()
        log.info("prewarm: queued %d demo regions (background)", n)
    yield


app = FastAPI(title="CityChange", version=__version__, lifespan=_lifespan)

# One analysis at a time: a region run peaks at a few hundred MB of RAM;
# serialization keeps the demo host healthy. Queued jobs wait.
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

MAX_AREA_KM2 = 1500.0
_NAME_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")


class AnalyzeRequest(BaseModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    name: str | None = None
    display_name: str | None = None
    years: list[int] | None = None


def _approx_area_km2(b: BBox) -> float:
    import math

    lat_mid = (b.south + b.north) / 2
    dy = (b.north - b.south) * 111.32
    dx = (b.east - b.west) * 111.32 * math.cos(math.radians(lat_mid))
    return abs(dx * dy)


def _region_from_request(req: AnalyzeRequest) -> RegionConfig:
    bbox = BBox(west=req.west, south=req.south, east=req.east, north=req.north)
    area = _approx_area_km2(bbox)
    if area > MAX_AREA_KM2:
        raise HTTPException(
            400,
            f"AOI is {area:.0f} km²; the limit is {MAX_AREA_KM2:.0f} km² "
            "(pick a smaller area — CityChange is about neighbourhood-to-city "
            "scale histories)",
        )
    years = tuple(req.years) if req.years else AVAILABLE_YEARS
    bad = [y for y in years if y not in AVAILABLE_YEARS]
    if bad:
        raise HTTPException(400, f"years {bad} outside available {AVAILABLE_YEARS}")
    if req.name:
        if not _NAME_RE.match(req.name):
            raise HTTPException(400, "name must match [a-z0-9_-]{1,64}")
        name = req.name
    else:
        name = "aoi_" + uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{bbox.west:.4f},{bbox.south:.4f},{bbox.east:.4f},{bbox.north:.4f},{years}",
        ).hex[:10]
    display = req.display_name or (
        f"AOI {abs(bbox.center[1]):.3f}°{'N' if bbox.center[1] >= 0 else 'S'} "
        f"{abs(bbox.center[0]):.3f}°{'E' if bbox.center[0] >= 0 else 'W'}"
    )
    return RegionConfig(name=name, display_name=display, bbox=bbox, years=years)


def _run_job(job_id: str, region: RegionConfig) -> None:
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"
    try:
        run_analysis(region, DEFAULT_PARAMS)
        with _jobs_lock:
            _jobs[job_id].update(status="done", finished=time.time())
    except Exception as err:  # surfaced via the job endpoint
        log.exception("analysis job %s failed", job_id)
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=str(err), finished=time.time())


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/regions")
def list_regions() -> list[dict]:
    """All region bundles on disk, newest first."""
    out = []
    root = data_dir() / "outputs"
    if root.exists():
        for summary_path in sorted(
            root.glob("*/summary.json"), key=lambda p: -p.stat().st_mtime
        ):
            try:
                s = json.loads(summary_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            out.append(
                {
                    "region": s["region"],
                    "display_name": s["display_name"],
                    "bbox": s["bbox"],
                    "years": s["years"],
                    "event_change_fraction": s["change_fractions"]["event_based"],
                    "generated_at": s.get("generated_at"),
                }
            )
    return out


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    region = _region_from_request(req)
    existing = load_summary(region.name)
    if existing:
        return {"status": "done", "region": region.name}
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "region": region.name,
            "status": "queued",
            "started": time.time(),
        }
    _executor.submit(_run_job, job_id, region)
    return {"status": "queued", "job": job_id, "region": region.name}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job


def _bundle_file(region: str, *parts: str) -> Path:
    if not _NAME_RE.match(region):
        raise HTTPException(400, "bad region name")
    base = bundle_dir(region).resolve()
    path = base.joinpath(*parts).resolve()
    if not str(path).startswith(str(base)):  # path traversal guard
        raise HTTPException(400, "bad path")
    if not path.exists():
        raise HTTPException(404, f"{'/'.join(parts)} not found for {region}")
    return path


@app.get("/api/region/{region}/summary")
def region_summary(region: str) -> dict:
    return json.loads(_bundle_file(region, "summary.json").read_text())


@app.get("/api/region/{region}/validation")
def region_validation(region: str) -> dict:
    return json.loads(_bundle_file(region, "validation.json").read_text())


@app.get("/api/region/{region}/overlays")
def region_overlays(region: str) -> dict:
    return json.loads(_bundle_file(region, "overlays", "overlays.json").read_text())


@app.get("/api/region/{region}/overlays/{filename}")
def region_overlay_file(region: str, filename: str) -> FileResponse:
    return FileResponse(_bundle_file(region, "overlays", filename))


@app.get("/api/region/{region}/figures/{filename}")
def region_figure_file(region: str, filename: str) -> FileResponse:
    return FileResponse(_bundle_file(region, "figures", filename))


@app.get("/api/region/{region}/evidence")
def region_evidence(region: str) -> dict:
    return json.loads(_bundle_file(region, "evidence", "evidence.json").read_text())


@app.get("/api/region/{region}/evidence/{filename}")
def region_evidence_file(region: str, filename: str) -> FileResponse:
    return FileResponse(_bundle_file(region, "evidence", filename))


# ---------------------------------------------------------------------------
# Geocoding proxy (Nominatim usage policy: identify the app, ≤1 req/s,
# results cached).
# ---------------------------------------------------------------------------
_geo_cache: dict[str, list] = {}
_geo_last_call = 0.0
_geo_lock = threading.Lock()


@app.get("/api/geocode")
def geocode(q: str) -> list[dict]:
    global _geo_last_call
    q = q.strip()[:200]
    if len(q) < 2:
        return []
    key = q.lower()
    if key in _geo_cache:
        return _geo_cache[key]
    with _geo_lock:
        wait = 1.1 - (time.time() - _geo_last_call)
        if wait > 0:
            time.sleep(wait)
        _geo_last_call = time.time()
    try:
        resp = _requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "jsonv2", "limit": 5},
            headers={"User-Agent": "CityChange/1.0 (academic urban-change project)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = [
            {
                "display_name": r["display_name"],
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "type": r.get("type"),
            }
            for r in resp.json()
        ]
    except _requests.RequestException as err:
        raise HTTPException(502, f"geocoding unavailable: {err}") from err
    _geo_cache[key] = results
    return results


# Static frontend (mounted last so /api keeps priority).
_frontend = REPO_ROOT / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
