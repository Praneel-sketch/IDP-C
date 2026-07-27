# Roadmap

Build vertically: something runnable at every phase. Status as of v1.0.

| phase | goal | status |
|---|---|---|
| 1–2 | one location, multi-year data, trends, visualization | ✅ v0.1 |
| 3 | automatic change-event extraction (timing, volumes) | ✅ events.py |
| 4 | temporal trajectory modelling (signatures, archetypes) | ✅ trajectory.py |
| 5 | multiple geographic regions, arbitrary AOIs (mosaic) | ✅ |
| 6 | trajectory pattern discovery (block clustering) | ✅ |
| 7 | anomaly discovery (budgeted rarity) | ✅ |
| 8 | uncertainty (evidence-grade confidence + holdout validation) | ✅ |
| 9 | interactive City Time Machine (API + web app) | ✅ |
| 10 | evaluation + baselines + cross-product validation | ✅ docs/EVALUATION.md |
| 11 | deployment (Docker; build-untested in sandbox, see DEPLOY.md) | ✅* |
| 12 | paper/report material | 🔨 reports/REPORT_OUTLINE.md + logs |

## Post-v1.0 candidates (research extensions, in priority order)

1. **Trajectory-aware confidence** — replace two-phase event confidence
   with sequence-likelihood scoring; evaluate with the same temporal
   holdout (fixes the documented Rondônia inversion).
2. **Manual ground-truth sample** — stratified visual verification of
   ~100 events/region against Sentinel-2 chips; turns holdout metrics
   into accuracy estimates.
3. **Sub-year timing** — S2 NDVI/NDBI series inside the estimated
   transition window to narrow ±1 year toward ±1 quarter.
4. **Cross-region trajectory atlas** — cluster signatures across all
   analysed regions to build a transferable taxonomy of urban change.
5. **Area comparison UI** — side-by-side Area A vs Area B mode.
6. **Newer vintages** — adopt IO 2024+ releases when published; extend
   WorldCover-style validation as new independent products appear.
