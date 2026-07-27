# Reproducing every result

All commands from the repo root, after `pip install -e ".[dev]"`.
Everything is deterministic given the cache (fixed seeds for clustering);
first runs download observations (a few MB per region-year).

| result | command |
|---|---|
| unit tests (61) | `pytest` |
| pilot region analysis bundle | `citychange run configs/devanahalli.yaml` |
| any ad-hoc area | `citychange run --bbox 77.63 13.17 77.73 13.27 --name my_area` |
| 6-region geographic benchmark + comparative report | `citychange benchmark` |
| cross-product + holdout validation for one region | `citychange validate configs/benchmark/devanahalli.yaml` |
| web app | `citychange serve` → http://127.0.0.1:8000 |

Artifacts land in `data/outputs/<region>/`:

```
summary.json / summary.md      grounded analysis + story
figures/*.png                  yearly states, trends, change map,
                               year-of-change, volumes, archetypes, anomalies
rasters/*.tif                  georeferenced: year_of_change, from/to state,
                               confidence (+tier), archetype, anomaly
overlays/                      EPSG:4326 RGBA PNGs + manifest for the web map
evidence/                      Sentinel-2 before/after chips (network path)
validation.json / .md          WorldCover agreement + temporal holdout
```

plus `data/outputs/benchmark_report.{md,json}` for the cross-region table
(the source of docs/EVALUATION.md numbers).

Caches (`data/cache/`) make re-runs offline; delete a region's cache
folder to force refetching. `--force` recomputes analysis without
refetching.
