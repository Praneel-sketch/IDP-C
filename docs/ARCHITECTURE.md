# CityChange architecture (v1.0)

If this file and the code disagree, the code wins and this file has a bug.

## Design philosophy

CityChange does not reinvent Earth observation. Trusted open land-cover
products play the role a chess engine plays in a chess-analytics app: a
per-observation oracle. CityChange's contribution is the *longitudinal
intelligence layer*:

```
raw observations → canonical states → change events → trajectories
→ patterns/anomalies → evidence-graded, grounded histories
```

## System map

```
configs/*.yaml or API bbox request
        ▼
citychange/pipeline.py — run_analysis()  (single orchestrator for CLI & API)
  ├─ datasets/io_annual_lulc.py   backbone acquisition: windowed COG reads,
  │                               single-tile fast path or multi-tile mosaic
  │                               with reprojection; per-region disk cache;
  │                               co-registration hard-asserted
  ├─ landstate.py                 product classes → canonical states
  │                               (clouds/unknown → NODATA, never a state)
  ├─ analysis.py                  trends, transition matrices, B2 baseline
  ├─ events.py                    two-phase event model: per-pixel
  │                               transition year, from/to, volumes, peak
  ├─ trajectory.py                run-length signatures, archetype grammar,
  │                               budgeted rarity anomalies, block k-means
  ├─ confidence.py                evidence grades: persistence,
  │                               pre-stability, purity, spatial support
  ├─ report.py                    grounded JSON + Markdown (template-only,
  │                               observation language, caveats)
  ├─ viz.py                       7 static figures per region
  ├─ overlays.py                  EPSG:4326 RGBA PNGs + manifest for the map
  └─ datasets/sentinel2.py        OPTIONAL evidence chips (Earth Search STAC)
        ▼
analysis bundle  data/outputs/<region>/   (summary, figures, rasters,
                                           overlays, evidence, validation)
        ▼
citychange/server.py — FastAPI            regions/analyze/jobs/summary/
                                          overlays/figures/evidence/geocode
        ▼
frontend/ — City Time Machine             vendored Leaflet, no build step:
                                          timeline, 6 layers, story panel,
                                          SVG charts, hotspots, evidence view
```

Validation path (separate from the product pipeline):
`citychange validate` → datasets/esa_worldcover.py + validation.py →
cross-product agreement + temporal holdout → validation.json/md.

Benchmark path: `citychange benchmark` → benchmark.py over
configs/benchmark/*.yaml → benchmark_report.md/json.

## Key invariants

1. **Acquisition ≠ analysis.** Analysis is pure NumPy on state stacks;
   tests run on synthetic arrays with zero network.
2. **Canonical states decouple sources from reasoning** — adding/swapping
   a product touches only a datasets/ mapping.
3. **Unobservable pixels are NODATA**, excluded from every denominator.
4. **Change requires multi-year evidence**; ambiguous histories are
   tie-broken toward "no claim" (D-008).
5. **No location-specific logic in citychange/** — coordinates exist only
   in configs/; one global AnalysisParams for every region (the benchmark
   enforces this socially and the code enforces it structurally).
6. **Narratives are grounded**: templates over computed numbers,
   observation language, no causal claims, rare ≠ wrong.
7. **Reproducibility**: config + params fingerprint stamped into bundles;
   caches make re-runs offline; clustering is seeded.
8. **Servers contain no science**: server.py orchestrates and serves.

## Team ownership (3 students)

- **A — data**: datasets/, tiles.py, mosaic/caching, future sources.
- **B — ML/temporal**: events/trajectory/confidence/analysis, validation,
  experiments/.
- **C — product**: server.py, frontend/, overlays.py, viz/report, deploy.

Interfaces between them: `RegionConfig`, `AnnualStack`, canonical state
arrays, `EventFields`, and the bundle contract (`summary.json` +
`overlays.json`). As long as those hold, work is parallel.
