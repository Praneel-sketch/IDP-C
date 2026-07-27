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

ENV CITYCHANGE_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# Analyses run in-process; keep a single worker (jobs are serialized anyway).
CMD ["uvicorn", "citychange.server:app", "--host", "0.0.0.0", "--port", "8000"]
