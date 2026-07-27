# Decision log

Newest at the bottom. Format: DECISION / REASON / ALTERNATIVES / TRADEOFF /
CAN REVISIT?

---

## D-001 — Land-state backbone for v0.1: Impact Observatory annual LULC

- **DECISION**: power v0.1 with the Impact Observatory / Esri 10 m Annual
  LULC product (2017–2023), streamed per-bbox from public COGs.
- **REASON**: zero credentials, zero cost, verified reachable from our
  environment; 7 annual global observations at 10 m; class schema matches
  our needs almost exactly; per-region cost is a few MB thanks to COG
  windowed reads. It gets a full temporal pipeline working in days, not
  months.
- **ALTERNATIVES**: Dynamic World (finer cadence + probabilities, but
  requires Google Earth Engine accounts/quota); ESA WorldCover (only
  2020/2021 — no time series); raw Sentinel-2 + own classifier (months of
  work, GPU cost, and we'd be reinventing what IO already does well);
  GHSL (built-up only, coarse epochs).
- **TRADEOFF**: annual cadence (no sub-year timing), inherited classifier
  errors, series currently ends at 2023. We accept all three for v0.1;
  Sentinel-2 via STAC is the planned complement for sub-year evidence.
- **CAN REVISIT?**: yes — the canonical-state layer (D-003) exists
  precisely so the backbone can be swapped or complemented.

## D-002 — Pilot region: Devanahalli / North Bengaluru airport corridor

- **DECISION**: pilot on a ~10 km × 10 km bbox (77.63–77.73°E,
  13.17–13.27°N).
- **REASON**: among the fastest-urbanizing zones in India across exactly
  our 2017–2023 window; change is large enough (built-up +19 pp, measured)
  that every pipeline stage produces interpretable output; single UTM tile;
  documented development context for later validation.
- **ALTERNATIVES**: Gurgaon/Noida, Hyderabad ORR, Dubai, Shenzhen, Cairo
  New Capital.
- **TRADEOFF**: monsoon-climate agriculture causes crops↔rangeland
  flicker, stressing (usefully) our noise handling.
- **CAN REVISIT?**: yes — regions are pure config; adding one is a YAML
  file.

## D-003 — Canonical land-state vocabulary decoupled from the source product

- **DECISION**: analysis operates on CityChange states (water, vegetation,
  crops, built, bare, snow_ice, nodata), not raw product codes. Trees,
  rangeland and flooded vegetation all map to "vegetation"; clouds map to
  nodata.
- **REASON**: decouples reasoning from any one product; collapses the
  noisiest distinctions (trees vs rangeland) that don't matter for urban
  history; makes "unobservable" explicit.
- **ALTERNATIVES**: analyse raw 9-class codes (noisier transitions,
  product lock-in); merge crops into vegetation (loses the distinct
  cropland→built urbanization signal).
- **TRADEOFF**: loses ecological detail (deforestation vs grassland loss
  are conflated). Raw grids are cached, so nothing is destroyed.
- **CAN REVISIT?**: yes — mapping is one dict in `landstate.py`.

## D-004 — Stable-change persistence rule as the v0.1 evidence filter

- **DECISION**: a pixel counts as changed only if its final state differs
  from the first year AND is identical across the last 2 years of the
  series.
- **REASON**: single-year class flips are frequently classifier noise
  (measured on the pilot: 36.3% raw first-vs-last change vs 26.1% stable
  change — the rule rejects ~10 pp of weakly-evidenced change). Embeds the
  project principle "one observation ≠ a transformation" from day one.
- **ALTERNATIVES**: raw two-date difference (Baseline 0/1 — kept for
  comparison); majority vote over all years; probabilistic temporal models
  (Phase 8).
- **TRADEOFF**: blind to changes in the final year of the series;
  "persistence = 2" is a heuristic, not calibrated confidence.
- **CAN REVISIT?**: yes — this is explicitly a placeholder for the Phase 8
  uncertainty machinery.

## D-005 — v0.1 storage: filesystem cache + YAML configs, no database

- **DECISION**: no PostGIS/database in v0.1. Cached GeoTIFFs per
  region/year + JSON/PNG outputs on disk.
- **REASON**: v0.1 state is a handful of small rasters; a database adds
  operational weight with zero current benefit.
- **ALTERNATIVES**: PostGIS (justified later for multi-region trajectory
  storage and the web API), SQLite, Zarr stores.
- **TRADEOFF**: no concurrent/queryable storage yet; revisit when the
  backend arrives (Phase 5/9).
- **CAN REVISIT?**: yes, planned.

## D-006 — Single-UTM-tile regions only in v0.1

- **DECISION**: a bbox spanning multiple UTM tiles raises a clear
  NotImplementedError instead of being mosaicked.
- **REASON**: mosaicking across UTM zones requires reprojection choices we
  don't need for any pilot region; a loud error beats a silently truncated
  analysis.
- **ALTERNATIVES**: immediate mosaic support (complexity without a current
  user).
- **TRADEOFF**: some bboxes must be shifted/shrunk for now.
- **CAN REVISIT?**: yes — Phase 5 (multiple regions) is the natural time.

## D-007 — Grounded template reports; no LLM in the loop yet

- **DECISION**: v0.1 summaries are generated from computed numbers via
  fixed templates, with observation-language only and an explicit caveats
  section.
- **REASON**: narrative safety is a core project principle; the cheapest
  way to guarantee "no invented explanations" is to have no free-text
  generator at all until there is a grounding mechanism to constrain one.
- **ALTERNATIVES**: LLM summarization now (risk of fabricated causality).
- **TRADEOFF**: prose is formulaic; acceptable until the analysis outputs
  are rich enough to warrant a constrained generator.
- **CAN REVISIT?**: yes — Phase 12 explanation layer.
