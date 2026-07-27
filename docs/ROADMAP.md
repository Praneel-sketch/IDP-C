# Roadmap

Build vertically: something runnable at every phase.

| phase | goal | status |
|---|---|---|
| 1 | One location, several dates: retrieve data, visualize change | ✅ v0.1 (exceeded: 7 years, trends, transitions, hotspot) |
| 2 | Multi-year land-state trends | ✅ folded into v0.1 |
| 3 | Automatic change-event extraction (per-pixel/zone event timing) | next — v0.2 |
| 4 | Temporal trajectory modelling | |
| 5 | Multiple geographic regions (+ multi-tile support) | |
| 6 | Trajectory clustering (recurring transformation patterns) | |
| 7 | Anomaly discovery (unusual trajectories) | |
| 8 | Uncertainty modelling (calibrated confidence) | |
| 9 | Interactive City Time Machine (web app: map + timeline) | |
| 10 | Evaluation + ablations vs baselines | designed alongside each phase |
| 11 | Optimization / deployment | |
| 12 | Paper / report / final demo | material accumulates in docs/ |

## What v0.1 proves

- Public, credential-free Earth-observation data **can** be turned into a
  machine-readable temporal history of one place, cheaply (a few MB and
  ~30 s per 10 km × 10 km region) and reproducibly (config + cache).
- The temporal signal is real and large: on the pilot region the pipeline
  measures built-up 22.7% → 42.1% (2017–2023), dominated by cropland
  conversion, and surfaces localized stories (lake refilling) that a
  two-date pixel diff would report as anonymous "change".
- Multi-year evidence filtering matters: ~10 pp of apparent first-vs-last
  change fails the persistence test — i.e. a large share of naive "change"
  is weakly evidenced.

## What v0.1 does NOT prove

- **No sub-year timing**: annual composites cannot say *when* in a year
  something changed.
- **No accuracy claim**: we have not validated detected changes against
  independent ground truth yet (that starts with cross-checking WorldCover/
  GHSL and manual samples).
- **No trajectory intelligence yet**: transitions are first-vs-last;
  per-pixel event timing, trajectory patterns, clustering, anomalies and
  calibrated confidence are all still ahead.
- **No claim of source independence**: everything currently rests on one
  derived product and inherits its biases.

## v0.2 proposal (Phase 3 start)

Goal: **per-pixel change-event timing with evidence.**

1. For every stable-changed pixel, scan its 7-year state sequence and
   estimate the transition year (first year the final state is adopted and
   held), producing a "when did it change" raster and per-year change
   volumes — the first real *event* representation.
2. Aggregate events into zone-level statements ("construction accelerated
   2021–2022") and a year-of-change map figure.
3. Add Sentinel-2 (Earth Search STAC, verified reachable) as an *evidence*
   source for a sampled subset of events: fetch a handful of cloud-filtered
   scenes around the estimated transition to narrow timing below one year
   and to give the report inspectable before/after imagery.
4. Extend tests + docs accordingly; keep the two-date diff as Baseline 0/1
   for the evaluation chapter.
