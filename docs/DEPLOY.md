# Deployment

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
citychange serve            # http://127.0.0.1:8000
```

The app starts empty. Pre-warm the demo regions (downloads a few MB per
region, ~1 min each):

```bash
citychange benchmark        # analyses all configs/benchmark/ regions
```

## Docker

```bash
docker build -f docker/Dockerfile -t citychange .
docker run -p 8000:8000 -v citychange-data:/data citychange
# or
cd docker && docker compose up --build
```

> **Status note (honest):** the Dockerfile is straightforward (slim Python
> base + pip install of the same wheels used in development) but could not
> be build-tested in the development sandbox (no Docker daemon available).
> First person to deploy: run
> `docker build -f docker/Dockerfile -t citychange . && docker run --rm -p 8000:8000 citychange`
> and check `curl localhost:8000/api/health`; report any failure as a bug.

The `/data` volume holds the download cache and analysis bundles; keep it
persistent so re-deploys don't refetch observations. To pre-warm inside
the container:

```bash
docker exec -it <container> citychange benchmark
```

## Pre-demo checklist

1. `pytest` — 69 green.
2. `citychange benchmark` — pre-warms all demo regions into the data dir.
3. `python scripts/demo_check.py` — boots the server and drives the real
   frontend in headless Chromium **with all external hosts blocked**
   (worst-case venue Wi-Fi): page boot, all six layers, timeline, story
   panel, and the basemap-offline fallback must pass.
4. Optional: open the app and click through one region yourself.

The frontend degrades by design: if the OSM basemap or geocoder is
unreachable, a notice appears and every CityChange layer (served locally
from bundles) keeps working. An analysis of a *new* area is the only
feature that genuinely needs the data-source hosts.

## Operational notes

- **Network egress required** to: `lulctimeseries.blob.core.windows.net`
  (land cover), `esa-worldcover.s3.eu-central-1.amazonaws.com`
  (validation), `earth-search.aws.element84.com` + 
  `sentinel-cogs.s3.us-west-2.amazonaws.com` (evidence chips),
  `nominatim.openstreetmap.org` (search), `tile.openstreetmap.org`
  (basemap, browser-side). Already-analysed regions serve fully offline
  except the basemap.
- **Resource envelope**: one analysis run peaks around 0.5–1 GB RAM for a
  ~120 km² region; jobs are serialized (one worker). A 1 vCPU / 2 GB host
  is sufficient for a demo deployment.
- **Rate limits**: the geocode proxy enforces Nominatim's 1 req/s policy
  server-side and caches results. Land-cover/S2 reads are cached on disk.
- **No secrets**: every data source is anonymous public access; there is
  deliberately nothing to configure in `.env` for v1.0.
- **Reverse proxy**: standard uvicorn-behind-nginx works; nothing is
  stateful outside the data volume.
