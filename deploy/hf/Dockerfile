# CityChange — Hugging Face Spaces (Docker) image.
# Differences from docker/Dockerfile (the generic image):
#   - runs as UID 1000 (Spaces requirement), writable /data owned by it
#   - demo analysis bundles are baked into the image (prebaked_outputs/,
#     staged by scripts/deploy_hf.sh) so the Space serves instantly and
#     survives restarts without persistent storage
#   - no VOLUME: Spaces free tier has ephemeral disk; user-run analyses
#     live until the Space restarts (documented in the Space README)
FROM python:3.11-slim

# rasterio's bundled GDAL needs libexpat at import time (verified).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser
WORKDIR /app

COPY pyproject.toml README.md ./
COPY citychange ./citychange
COPY frontend ./frontend
COPY configs ./configs

RUN pip install --no-cache-dir .

# Pre-analysed demo regions (benchmark suite) baked into the image.
COPY prebaked_outputs /data/outputs

ENV CITYCHANGE_DATA_DIR=/data \
    MPLCONFIGDIR=/tmp/mpl \
    HOME=/home/appuser
RUN mkdir -p /data/cache /tmp/mpl && chown -R appuser:appuser /data /tmp/mpl

USER appuser
EXPOSE 8000

CMD ["uvicorn", "citychange.server:app", "--host", "0.0.0.0", "--port", "8000"]
