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

> **Status:** the image is build-tested and smoke-tested (health endpoint,
> frontend, vendored assets all verified from a running container). The
> slim base needs `libexpat1` for rasterio's bundled GDAL — already handled
> in the Dockerfile. If your build environment sits behind an HTTP proxy,
> pass it through: `docker build --build-arg HTTPS_PROXY=... ...`.

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

## Railway

The repo is Railway-ready via config-as-code — no dashboard build settings
needed:

- `railway.json` selects the **Dockerfile builder** (`docker/Dockerfile`),
  wires the healthcheck to `/api/health` (300 s timeout) and an
  ON_FAILURE restart policy. Docker is deliberately chosen over
  Railpack: the image is container-verified including the non-obvious
  GDAL system dependency (`libexpat1`) that a rebuilt-from-scratch Python
  environment can miss.
- The container binds `0.0.0.0:${PORT}` (Railway injects `PORT`;
  defaults to 8000 elsewhere) and hands PID 1 to uvicorn for graceful
  shutdown on redeploys.
- `CITYCHANGE_PREWARM=1` (the image default): a fresh deployment with an
  empty `/data` queues the six demo regions in the background on first
  boot — health passes immediately and regions appear in the UI one by
  one over ~5–10 minutes. Deployments with existing data never re-warm.
- **Storage**: without a volume, `/data` is ephemeral — demo regions
  re-warm automatically after each deploy, but visitor-run analyses are
  lost. For persistence, attach a Railway volume mounted at `/data`
  (dashboard → service → Volumes); prewarm then runs only once ever.
- Suggested resources: 1 vCPU / 2 GB. No env vars or secrets are
  required beyond the optional `CITYCHANGE_PREWARM`.

Deploy = connect the repo/branch in Railway and push; each push to the
connected branch redeploys. Verify with `https://<your-app>.up.railway.app/api/health`.

## Hosted demo: Hugging Face Spaces (free)

A ready-made deployment kit lives in `deploy/hf/`:

```bash
citychange benchmark                       # ensure demo bundles exist locally
HF_TOKEN=hf_xxx HF_SPACE=<user>/citychange scripts/deploy_hf.sh
```

The script stages a Space repo (app + Space Dockerfile + Space README +
the local `data/outputs` bundles baked in as always-on demo data), and
pushes it with the token via a temporary git credential helper (the token
never lands in the repo, the remote URL, or the output). The Space
Dockerfile runs as UID 1000 per Spaces rules and was container-verified
locally. Free CPU-basic hardware is sufficient (analyses peak ~1 GB RAM);
ephemeral storage means user-run analyses last until restart while the
baked demo regions always remain.
