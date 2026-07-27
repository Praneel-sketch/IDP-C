# CityChange architecture

This document describes the architecture as far as it is *implemented*, plus
the module boundaries the full system will grow into. It is updated whenever
implementation changes — if this file and the code disagree, the code wins
and this file has a bug.

## Design philosophy

CityChange does not reinvent Earth observation. Existing open land-cover
products play the role a chess engine plays in a chess-analytics app: a
trusted per-observation oracle. CityChange's contribution is the
*longitudinal intelligence layer* built on top:

```
raw observations → canonical temporal representation → change events
→ trajectories → patterns/anomalies → grounded human-readable history
```

## Layered view (target system)

| layer | v0.1 status |
|---|---|
| 1. Geographic input (bbox → later map selection/search) | YAML bbox configs |
| 2. Data acquisition (per-source modules, cached, resumable) | `datasets/io_annual_lulc.py` |
| 3. Preprocessing (alignment, validity, harmonization) | co-registration asserts + nodata/cloud handling |
| 4. Land representation (canonical states) | `landstate.py` |
| 5. Temporal representation (state stacks per pixel/cell) | in-memory annual stacks |
| 6. Change-event detection | stable-change persistence rule (first version) |
| 7. Trajectory modelling | — (Phase 4) |
| 8. Transformation discovery (clustering) | — (Phase 6) |
| 9. Anomaly discovery | — (Phase 7) |
| 10. Uncertainty estimation | — (Phase 8; caveats reported honestly meanwhile) |
| 11. Geospatial context (OSM etc.) | — (Phase 5+) |
| 12. Explanation (grounded narrative) | template-based `report.py`, zero free text |
| 13. Visualization | static matplotlib figures; interactive map in Phase 9 |

## v0.1 pipeline

```
configs/<region>.yaml
        │  load_region()
        ▼
fetch_annual_stack()          citychange/datasets/io_annual_lulc.py
  • bbox → UTM tile id        citychange/tiles.py
  • windowed HTTP read of remote COG (bytes for the bbox only)
  • local GeoTIFF cache  →  data/cache/io_annual_lulc/<region>/
  • hard assertion: all years share shape/CRS/transform
        ▼
remap_to_states()             citychange/landstate.py
  • product classes → canonical states (LUT)
  • clouds/unknown codes → NODATA (unobservable ≠ a land state)
        ▼
analysis                      citychange/analysis.py  (pure NumPy)
  • state_fractions / fraction_trends
  • transition_matrix (jointly-observed pixels only)
  • stable_change_mask: changed AND new state persists N final years
  • find_hotspot: densest-change coarse block
        ▼
outputs
  • viz.py    → yearly_states.png, trends.png, change_map.png
  • report.py → summary.md + summary.json (every sentence from numbers)
```

## Key invariants

1. **Acquisition is separated from analysis.** Analysis code never touches
   the network; it consumes NumPy arrays. Tests exercise analysis on
   synthetic arrays with zero I/O.
2. **The canonical state vocabulary decouples sources from reasoning.**
   Swapping/adding a land-cover product means writing a new mapping in the
   datasets layer, not touching analysis.
3. **Unobservable pixels are NODATA, never a state.** Clouds and missing
   data are excluded from every denominator.
4. **Change requires evidence.** A pixel counts as changed only if the new
   state persists; this rule will evolve into calibrated confidence, but
   the principle — single observations don't prove transformations — is
   locked in from v0.1.
5. **Narratives are grounded.** The report layer formats computed numbers.
   Observation language only; no causal claims without a causal design.
6. **Runs are reproducible.** A region config + cache fully determines the
   outputs; caches make re-runs offline and deterministic.

## Team ownership (3 students)

- **Student A — data**: `datasets/`, `tiles.py`, future preprocessing
  (multi-tile mosaics, Sentinel-2 path, OSM ingestion).
- **Student B — ML/temporal**: `analysis.py` and its successors (event
  detection, trajectories, clustering, anomalies, uncertainty),
  `experiments/`.
- **Student C — product**: `viz.py`, `report.py`, future backend API and
  web frontend (map + timeline).

The interfaces between them are the two dataclasses (`RegionConfig`,
`AnnualStack`) and the canonical state arrays — as long as those hold,
work proceeds in parallel.
