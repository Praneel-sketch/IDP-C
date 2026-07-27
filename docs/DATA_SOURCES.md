# Data sources

Every source used by CityChange is verified here *before* code depends on
it: access conditions, license, coverage, resolution, and empirically
confirmed behaviour. Nothing in this file is assumed from memory alone —
"verified" means we tested it from this project.

## In use

### Impact Observatory / Esri 10 m Annual Land Use Land Cover (v003)

- **What**: global annual land-cover classification, 9 classes, derived
  from ESA Sentinel-2 imagery by Impact Observatory's deep-learning model;
  published by Esri/IO/Microsoft as open data.
- **Access**: public Azure blob container, no credentials:
  `https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{year}/{TILE}_{year}0101-{year+1}0101.tif`
  where `TILE` is a UTM zone + MGRS latitude band (e.g. `43P`).
- **License**: CC BY 4.0. Attribution: Impact Observatory, Microsoft, Esri;
  source imagery ESA Sentinel-2.
- **Verified empirically (2026-07, from this repo)**:
  - years **2017–2023** return HTTP 200 for tile 43P; 2016 and 2024 return
    404 under `lulctimeseriesv003` (also checked v004/v005 paths: absent);
  - range requests honoured (HTTP 206) → true COG streaming works;
  - format: uint8, nodata=0, 10 m pixels, EPSG:326xx (UTM), 256 px internal
    tiles, overviews 2–32;
  - class codes and embedded colormap: 1 water `#419BDF`, 2 trees `#397D49`,
    4 flooded vegetation `#7A87C6`, 5 crops `#E49635`, 7 built `#C4281B`,
    8 bare `#A59B8F`, 9 snow/ice `#A8EBFF`, 10 clouds `#616161`,
    11 rangeland `#E3E2C3`.
- **Known limitations** (must be respected by analysis):
  - it is a *derived classification*, not ground truth; class flicker
    between years is common (notably crops ↔ rangeland);
  - annual cadence — no sub-year timing;
  - "built area" includes roads and large paved surfaces, not only
    buildings;
  - the model/version differs subtly across years; year-to-year
    comparisons inherit that inconsistency;
  - 2024+ not available in v003 at time of verification — re-check
    periodically.

## Candidates for later phases (not yet integrated)

- **Sentinel-2 L2A via Earth Search STAC** (`https://earth-search.aws.element84.com/v1`,
  Element 84 / AWS Open Data): reachability verified (HTTP 200, no auth for
  search; COG assets on AWS). Gives sub-annual raw imagery for Phase 3+
  (event timing within a year, NDVI/NDBI evidence). License: Copernicus
  Sentinel data terms (free, attribution required).
- **ESA WorldCover** (2020, 2021 only): cross-validation of land states in
  those years.
- **GHSL built-up surface** (multi-epoch): independent long-baseline
  built-up evidence for validation.
- **Dynamic World (near-real-time, 2015-06→)**: richer per-observation
  probabilities, but access is via Google Earth Engine, which requires an
  account and quota — deliberately avoided for the credential-free v0.1.
- **OpenStreetMap / OSM history**: geographic context; mapping dates must
  never be conflated with construction dates.

When one of these is integrated, it moves to "In use" with its own verified
section.
