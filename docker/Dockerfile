# CityChange: single image serving the pipeline, API and frontend.
# Build (repo root):  docker build -f docker/Dockerfile -t citychange .
# Run:                docker run -p 8000:8000 -v citychange-data:/data citychange
FROM python:3.11-slim

WORKDIR /app

# rasterio's bundled GDAL still links a few system libraries that the slim
# image lacks (verified: libexpat is required at import time).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY citychange ./citychange
COPY frontend ./frontend
COPY configs ./configs

# Python deps: rasterio/pyproj ship manylinux wheels with bundled GDAL/PROJ.
RUN pip install --no-cache-dir .

# CITYCHANGE_PREWARM=1: a fresh production container with an empty data
# directory queues the six benchmark demo regions on startup (background,
# non-blocking) so the app is never an empty map. Set to 0 to disable.
# No VOLUME directive: platforms like Railway don't support it; attach
# persistent storage at /data via the platform (docs/DEPLOY.md) or
# docker run -v / compose.
ENV CITYCHANGE_DATA_DIR=/data \
    CITYCHANGE_PREWARM=1
EXPOSE 8000

# Analyses run in-process; keep a single worker (jobs are serialized
# anyway). Shell needed to expand PORT (injected by Railway/Render/...);
# `exec` hands PID 1 to uvicorn so SIGTERM reaches it and redeploys shut
# down gracefully instead of waiting for the platform's kill timeout.
CMD ["sh", "-c", "exec uvicorn citychange.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
