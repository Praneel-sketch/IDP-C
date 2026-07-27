# CITYCHANGE FINAL PLAN

Authoritative execution document. Revised as evidence changes; if this file
and the code disagree, the code wins and this file gets fixed.

Status legend: ✅ done · 🔨 in progress · ⬜ planned

---

## 1. v0.1 architecture (audited 2026-07-27)

Audit result: **22/22 tests pass, package compiles clean, `pip check`
clean, pipeline reruns fully offline from cache in ~5 s.** The architecture
described in docs/ARCHITECTURE.md exists as described:

`configs/*.yaml → datasets/io_annual_lulc (windowed COG reads, cache,
co-registration asserts) → landstate (canonical states) → analysis (pure
NumPy) → viz + report (grounded templates)`

## 2. Strengths (confirmed, to preserve)

- **Canonical-state abstraction** — source classes → CityChange states →
  source-independent analysis. Locked in as the backbone.
- Acquisition strictly separated from analysis; analysis is pure NumPy and
  unit-testable without network.
- COG windowed reads: per-region cost is a few MB / ~30 s; cache makes
  re-runs offline and deterministic.
- Persistence-based evidence filtering from day one.
- Grounded, template-only narrative (observation language, caveats,
  no causal claims).
- Reproducibility: region config + cache fully determines outputs.

## 3. Weaknesses / technical debt

| # | debt | resolution |
|---|---|---|
| W1 | single-UTM-tile regions only | mosaic + reprojection in acquisition (M4) |
| W2 | transitions are first-vs-last only; no timing | event extraction (M1) |
| W3 | no trajectory representation | trajectory module (M2) |
| W4 | binary persistence rule, no graded confidence | confidence module (M3) |
| W5 | one hotspot only, Python-loop block scan | top-N hotspots, vectorized |
| W6 | persistence constant hardcoded in cli.py | AnalysisParams in config |
| W7 | no independent validation of outputs | WorldCover cross-check (M5) |
| W8 | no API / no UI | FastAPI + web frontend (M6/M7) |
| W9 | orchestration lives in cli.py | pipeline.py orchestrator reused by CLI and API |

## 4. Scientific limitations (honest, some irreducible)

- Annual cadence bounds timing precision to ±1 year; Sentinel-2 evidence
  chips (M8) provide inspectability, not automatic sub-year dating.
- All land states come from one derived product (IO Annual LULC); its
  classifier biases propagate. Mitigation: cross-product agreement
  metrics, never claiming per-pixel certainty, confidence tiers.
- Confidence scores are **documented heuristics, not calibrated
  probabilities**; the evaluation measures how confidence relates to
  cross-product agreement and says exactly that.
- 2017–2023 window only (verified: 2016/2024 absent from the source).
- No causal inference anywhere. Observation/inference/association language
  enforced by the template layer.

## 5. Final product architecture

```
                       ┌──────────────────────────────────────────────┐
configs / API request  │            citychange (Python pkg)           │
  bbox + years  ──────▶│ pipeline.py  (orchestrator, resumable,       │
                       │               persists an AnalysisBundle)    │
                       │   ├─ datasets/io_annual_lulc  (mosaic, cache)│
                       │   ├─ landstate   (canonical states)          │
                       │   ├─ analysis    (trends, transitions)       │
                       │   ├─ events      (per-pixel transition year) │
                       │   ├─ trajectory  (archetypes, rarity,        │
                       │   │               block clustering)          │
                       │   ├─ confidence  (graded evidence tiers)     │
                       │   ├─ overlays    (EPSG:4326 RGBA PNGs)       │
                       │   ├─ report      (grounded story JSON/MD)    │
                       │   └─ datasets/sentinel2 (evidence chips)     │
                       └───────────────┬──────────────────────────────┘
                                       │ AnalysisBundle on disk
                                       │ (JSON + GeoTIFF + PNG per region)
                       ┌───────────────▼──────────────────────────────┐
                       │ server.py — FastAPI                          │
                       │  /api/regions /api/analyze /api/region/...   │
                       │  /api/geocode (Nominatim proxy, cached)      │
                       │  serves frontend/ (static, no build step)    │
                       └───────────────┬──────────────────────────────┘
                       ┌───────────────▼──────────────────────────────┐
                       │ frontend/ — City Time Machine                │
                       │  vendored Leaflet, no CDN, no build step     │
                       │  map + year slider + trend charts + story    │
                       │  change/timing/anomaly overlays + confidence │
                       └──────────────────────────────────────────────┘
```

Storage stays filesystem-based (bundle directory per region). PostGIS
remains unjustified at this scale (revisits D-005; a bundle is <10 MB and
region counts are dozens, not millions).

## 6. Final research architecture

Per-pixel state sequences (7 obs) are the atomic research object.

1. **Events** — a changed pixel's transition year = first year of the
   final persistent run. Output: year-of-change, from/to, per-year change
   volumes by transition type.
2. **Trajectories** — run-length compression of state sequences into
   phases; interpretable archetype grammar (stable / stable-with-flicker /
   direct transition A→B / staged transition A→M→B / reverted / cyclic /
   unstable). Location-independent rules over durations, never over
   geography.
3. **Pattern discovery** — signature frequency statistics per region +
   k-means over block-level trajectory features (composition, timing,
   flicker) → "areas that evolved similarly".
4. **Anomaly discovery** — statistically rare trajectory signatures
   (low relative frequency) + spatially isolated transitions. Language:
   "rare", never "illegal"/"suspicious".
5. **Confidence** — per changed pixel from persistence length,
   pre-transition stability, sequence purity, 3×3 spatial support →
   score ∈ [0,1] + tier. Evaluated against cross-product agreement.
6. **Baselines kept for evaluation**: B0 raw two-date pixel diff,
   B1 two-date land-cover diff, B2 persistence rule (v0.1), full system.

## 7. Data strategy

- **Backbone**: IO/Esri Annual LULC v003, 2017–2023 (verified; D-001).
- **Validation**: ESA WorldCover 2020 (v100) & 2021 (v200) — public S3,
  to be verified before code depends on it (M5 gate).
- **Evidence**: Sentinel-2 L2A via Earth Search STAC (reachability
  verified) for before/after true-color chips around detected transitions.
  Optional path — the system degrades gracefully without network.
- **Context (OSM)**: deferred; mapping-date ≠ construction-date makes it
  validation-grade only, and it is not on the critical path.

## 8. Geographic generalization strategy

- Zero region-specific constants in `citychange/` (enforced by review; the
  only place coordinates may appear is `configs/`).
- Acquisition upgraded to arbitrary AOIs: multi-tile mosaic with
  reprojection onto the AOI-centre UTM grid.
- All thresholds (persistence, flicker tolerance, hotspot block size,
  confidence weights) live in `AnalysisParams` with global defaults —
  identical for every region.

## 9. Validation strategy (geographic benchmark)

Reusable benchmark = ordinary region configs under `configs/benchmark/` +
a `citychange benchmark` runner producing one comparative report.

| region | why | expectation |
|---|---|---|
| devanahalli (IN) | rapid urbanization (pilot, regression anchor) | large veg/crops→built |
| paris_core (FR) | mature dense urban | very little persistent change |
| frisco_tx (US) | suburban greenfield expansion | crops/veg→built, suburban texture |
| rondonia_frontier (BR) | vegetation-heavy, non-urban change, southern hemisphere | veg→crops/bare (deforestation) |
| lake_mead_west (US) | water dynamics | water recession (drought years) |
| ansbach_rural (DE) | stable control | "not much persistent change" |

Success criteria include the *stable* regions: the system must report low
stable-change fractions there without any per-region tuning. Cross-product
agreement (WorldCover) computed per region. Confidence-vs-agreement
relationship reported.

## 10. Frontend/backend strategy

- **FastAPI** backend (async, typed, serves both API and static frontend).
- **No-build frontend**: vendored Leaflet + hand-written JS/SVG charts.
  Rationale: 3-student team, zero node toolchain, deployable anywhere
  Python runs; the UI needs a map, a slider, charts and a story panel —
  none of which require React. (Recorded as D-008.)
- UI principle: MAP / TIME / CHANGE / STORY / CONFIDENCE within 30 s;
  remote-sensing jargon stays out of the primary UI.

## 11. Deployment strategy

- Dockerfile (single image: pipeline + API + frontend) + docker-compose
  with a volume for the data directory. Pre-warm script for demo regions.
- Local dev: `pip install -e . && citychange serve`.

## 12. Milestone sequence

| id | milestone | status |
|---|---|---|
| M0 | audit v0.1 + this plan | ✅ |
| M1 | change-event extraction (timing, volumes, year-of-change) | ✅ |
| M2 | trajectory modelling (archetypes, signatures, rarity, clustering) | ✅ |
| M3 | confidence scoring | ✅ |
| M4 | arbitrary-AOI acquisition (mosaic) + pipeline orchestrator + extended reports | ✅ |
| M5 | geographic benchmark (6 regions) + WorldCover cross-validation + temporal holdout | ✅ |
| M6 | FastAPI backend + overlays + geocode proxy | ✅ |
| M7 | City Time Machine frontend (verified with live-browser screenshots) | ✅ |
| M8 | Sentinel-2 evidence chips (optional-path) | ✅ |
| M9 | Docker + deployment + evaluation/experiment docs + report skeleton | ✅ (Docker image build untested in sandbox — no daemon; see docs/DEPLOY.md) |

Each milestone ended with green tests and a pushed commit.

### M10 — final hardening pass (v1.1)

| item | outcome |
|---|---|
| basemap failure fallback (offline demo safety) | frontend drops the tile layer after repeated errors, shows a notice, all local layers keep working — verified by `scripts/demo_check.py` with every external host blocked |
| loading/error states | region-load spinner + failure message; analysis poll timeout (12 min); unknown-job and oversized-AOI errors surfaced to the user |
| synthetic end-to-end pipeline test | `tests/test_pipeline.py` runs the REAL run_analysis on synthetic stacks (changing + fully-stable regions) with zero network — 69 tests total |
| geocode proxy tests | mocked success/caching/failure paths |
| production path from zero state | fresh empty data dir → API analyze of a never-seen AOI (Nairobi, tile 37M) → complete bundle in 33 s, served to the frontend |
| deprecation/debt cleanup | `matplotlib.colormaps` API, aspect-preserving overlay cap, dead code removed, rasterio log noise silenced |
| honesty wording | "confirms" → "meets the event criterion"; UI card "Confirmed" → "Persistent change" |
| Docker image | built and smoke-tested in-sandbox (daemon started manually; `--network=host` needed only because the sandbox lacks a bridge) |

## 13. Risks

| risk | mitigation |
|---|---|
| WorldCover/S3 access differs from expectation | verify before coding (hard gate); validation degrades to IO-internal stability metrics |
| Earth Search throttling/absence | evidence chips are optional-path with caching and clear absence handling |
| trajectory archetypes overfit the pilot | frozen rules, then benchmark on 6 diverse regions; report failures honestly |
| session/container limits mid-build | commit after every milestone; caches re-creatable |
| source product discontinuity (no 2024+) | architecture supports year subsets; documented limitation |

## 14. Definition of done

1. `citychange run` works for **any** in-coverage bbox ≤ ~30 km via config
   or CLI flags, single- or multi-tile, no region-specific logic.
2. Full intelligence chain per region: trends, transitions, event timing,
   trajectories/archetypes, similar-area clusters, rare-trajectory
   anomalies, per-change confidence tiers — all grounded in computed data.
3. Benchmark suite runs across the 6 regions with one command and produces
   a comparative report in which stable regions read as stable.
4. Cross-product validation metrics computed and documented, including the
   confidence-vs-agreement relationship.
5. Web app: search/navigate → select area → run/view analysis → timeline,
   overlays, charts, story, confidence, evidence.
6. Dockerized deployment; README + docs current; decision/experiment logs
   maintained; academic report skeleton with real citations.
7. All tests green; no secrets in repo; no fabricated claims anywhere.
