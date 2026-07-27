# Evaluation

All numbers reproducible: `citychange benchmark` +
`python -c "...validate_region..."` (see docs/REPRODUCE.md). Identical
global parameters for every region; no per-region tuning anywhere.

## 1. Geographic benchmark (6 regions, 4 continents)

| region | regime | event chg % | raw chg % | stable % | note |
|---|---|---|---|---|---|
| devanahalli (IN) | rapid urbanization | 26.6 | 36.3 | 58.8 | built +19.4 pp |
| frisco_tx (US) | suburban expansion | 14.9 | 20.3 | 77.6 | built +10.6 pp |
| rondonia_frontier (BR) | deforestation frontier | 14.6 | 29.5 | 68.4 | crops +28.1 pp |
| lake_mead_west (US) | water dynamics | 8.4 | 9.0 | 90.7 | shoreline exposure |
| ansbach_rural (DE) | stable rural control | 2.3 | 4.2 | 94.5 | crop-rotation flicker filtered |
| paris_core (FR) | dense stable control | 0.2 | 0.6 | 99.3 | "not much changed" ✓ |

Key claims supported:

- **Stability is detected as stability.** The two control regions come out
  1–2 orders of magnitude below the change regions on the same thresholds.
- **The event model adds value over naive differencing everywhere**: the
  gap between raw and event-based change (e.g. 29.5% → 14.6% in Rondônia,
  4.2% → 2.3% in Ansbach) is single-year flicker and reverted excursions
  that a two-date method reports as change.

## 2. Cross-product state agreement (vs ESA WorldCover, canonical states)

Overall agreement 2021: Paris 89%, Rondônia 92%, Ansbach 68%, Frisco 67%,
Devanahalli 59%, Lake Mead 51%.

Finding: agreement is high where landscapes are unambiguous (dense city,
closed forest) and low where the products' class semantics split —
IO "rangeland"(→vegetation) vs WC "bare" in deserts (Lake Mead),
IO "crops" vs WC "grassland" for pasture (Rondônia), and mixed
suburban pixels. **Cross-product comparison validates state
comparability; it is a weak instrument for validating change**, because
freshly changed land is exactly where transitional surfaces make the
products disagree most. Both raw and stable-pixel-normalised
("relative ratio") numbers are in each region's `validation.json`.

## 3. Confidence validation: temporal holdout

Events detected on 2017–2021 only; verified = the claimed new state
persists through withheld 2022–2023. Verified rate by confidence-score
quartile:

| region | q1 | q2 | q3 | q4 | verdict |
|---|---|---|---|---|---|
| ansbach_rural | 43.2 | 43.6 | 70.3 | 84.4 | monotone ✓ |
| devanahalli | 62.3 | 72.8 | 80.8 | 87.3 | monotone ✓ |
| frisco_tx | 68.5 | 79.5 | 85.6 | 92.5 | monotone ✓ |
| lake_mead_west | 99.9 | 100 | 100 | 100 | saturated (uninformative) |
| paris_core | 78.4 | 45.2 | 47.9 | 91.8 | noisy, n=498 |
| rondonia_frontier | 76.2 | — | 46.7 | 38.6 | **inverted** |

Interpretation, stated honestly:

- In settlement-driven regimes the score has clear ranking value: the
  highest-confidence quartile is 20–41 pp more likely to persist than the
  lowest.
- In the active frontier (Rondônia) the relationship inverts: land that
  changed once keeps changing (clearing → crops → pasture regrowth), so
  persistence-based confidence overestimates stability of the *first*
  transition. This is a documented limitation of two-phase confidence in
  multi-stage landscapes — and the motivation for the multi-phase
  trajectory representation (staged_change, signatures), which does
  capture these continued evolutions.
- The holdout test measures ranking value within the source product; a
  misclassification repeated across all years is invisible to it.

## 4. Baseline comparison (methods ladder)

| baseline | definition | status |
|---|---|---|
| B0 raw pixel diff | two-date changed-pixel fraction | reported per region (`raw_two_date`) |
| B1 land-cover diff | two-date canonical-state transitions | reported (`top_transitions_first_to_last`) |
| B2 persistence rule | v0.1 stable-change mask | reported (`persistence_rule_b2`) |
| full system | event model + trajectories + confidence | primary output |

What the full system adds over B0–B2, concretely: dated transitions
(±1 year), trajectory shape (direct/staged/reverted/noisy), rarity-based
anomaly discovery, graded confidence with demonstrated ranking value, and
grounded narrative — none of which exist in the baselines.

## 5. Known evaluation gaps

- No manually verified ground-truth sample yet (planned: stratified manual
  check of N=100 events per region against Sentinel-2 imagery chips).
- No user study of the narrative/UI layer.
- Paris/Lake Mead quartile analyses under-powered or saturated.
