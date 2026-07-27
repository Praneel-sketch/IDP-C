# Experiment log

Format per entry: hypothesis · setup · result · interpretation · follow-up.
All experiments reproducible via docs/REPRODUCE.md; numbers live in
`data/outputs/*/summary.json`, `*/validation.json`,
`benchmark_report.json`.

---

## E-001 — Geographic generalization benchmark

- **Hypothesis**: the event pipeline, with one global parameter set,
  produces regime-appropriate outputs across 6 contrasting regions
  (2 change-heavy urban, 1 deforestation, 1 hydrological, 2 stable
  controls).
- **Setup**: `citychange benchmark`; identical `AnalysisParams` everywhere;
  regions in `configs/benchmark/`.
- **Result**: event-based change — Devanahalli 26.6%, Frisco 14.9%,
  Rondônia 14.6%, Lake Mead 8.4%, Ansbach 2.3%, Paris 0.2%. Stable
  controls 1–2 orders of magnitude below change regions; dominant
  transitions match the known regime of each region (crops→built,
  veg→crops, water→bare respectively).
- **Interpretation**: no evidence of pilot-region overfitting; the
  persistence machinery filters agricultural flicker without suppressing
  genuine change.
- **Follow-up**: none required for v1.0; add monsoon-coastal and arid-gulf
  regions for the paper's robustness table.

## E-002 — Cross-product state agreement (IO vs WorldCover)

- **Hypothesis**: canonical states agree strongly between independent
  products, justifying product-derived land states as analysis input.
- **Setup**: `citychange validate <region>` for all 6 regions; 2020 and
  2021 vintages.
- **Result**: overall agreement 51–96% depending on landscape; high in
  dense urban (Paris 89%) and closed forest (Rondônia 92–96%); low in
  deserts (Lake Mead 51%) and mixed agriculture (Devanahalli 59%).
  Systematic semantic splits identified: IO rangeland vs WC bare
  (deserts), IO crops vs WC grassland (pasture).
- **Interpretation**: per-pixel state claims are strong for built/water/
  forest, weaker at vegetation/crops/bare boundaries; reports must (and
  do) avoid pixel-level certainty language.
- **Follow-up**: none; feeds the paper's limitations section.

## E-003 — Change credibility via stable-pixel-normalised agreement

- **Hypothesis**: WorldCover agreement on changed pixels, normalised by
  agreement on unchanged pixels of the same state, isolates change
  credibility from class semantics.
- **Setup**: `relative_ratio` in validation.py, per region and per
  confidence-score quartile.
- **Result**: ratios 0.36–1.0 across regions; no consistent monotone
  relationship with confidence score; freshly changed land shows *larger*
  product divergence than stable land (transitional surfaces).
- **Interpretation**: cross-product comparison is structurally weak as a
  change validator — an honest negative result documented in
  docs/EVALUATION.md; motivated E-004.
- **Follow-up**: superseded by E-004 as the primary confidence evaluation.

## E-004 — Temporal holdout: does confidence predict persistence?

- **Hypothesis**: confidence scores computed on 2017–2021 rank which
  detected events remain in their new state through withheld 2022–2023.
- **Setup**: `holdout_consistency()` — events on the truncated series,
  verification = new state present in both held-out years, reported by
  score quartile.
- **Result**: monotone in settlement regimes (Ansbach 43→84%, Devanahalli
  62→87%, Frisco 69→93% across quartiles); saturated at Lake Mead (100%);
  **inverted** in Rondônia (76→39%).
- **Interpretation**: the score has real ranking value where change is
  terminal (construction); it overestimates stability in multi-stage
  frontier landscapes where first transitions are followed by further
  evolution — precisely the cases the staged/noisy trajectory archetypes
  capture. Limitation documented; scores are labelled evidence grades,
  not probabilities, everywhere they surface.
- **Follow-up**: candidate research extension — replace the two-phase
  event confidence with trajectory-aware confidence (sequence-model
  likelihood), evaluated the same way.

## E-005 — Anomaly budget refinement

- **Hypothesis**: raw rarity thresholding flags too much area to be
  useful (observed 10.9% on the pilot), including static-but-rare states.
- **Setup**: restrict rarity to multi-state signatures + cumulative 2%
  area budget (rarest first).
- **Result**: pilot anomaly area 10.94% → 2.00%; flagged paths are
  genuinely irregular (e.g. `built→crops→built→vegetation→built`).
- **Interpretation**: "unusual" now selects the exceptional rather than
  the merely uncommon; UI language reinforces rare ≠ wrong.
