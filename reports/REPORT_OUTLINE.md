# Academic report outline (working document)

Every number cited below exists in the repo (docs/EVALUATION.md,
data/outputs/*); every reference listed is a real publication we actually
rely on. Do not add citations that were not read.

## 1. Introduction & motivation
Cities change faster than our records of them; satellite archives contain
the history but not the story. CityChange: longitudinal intelligence over
open Earth observation — "git history for places".

## 2. Problem statement
Given an arbitrary AOI and years Y0–Yn of open observations, produce a
machine-readable and human-readable account of land-state evolution:
what changed, when, along which trajectory, how unusual, with what
evidence.

## 3. Related work (verified starting set)
- Product basis: Karra et al., "Global land use/land cover with
  Sentinel-2 and deep learning", IGARSS 2021 (the Esri/Impact Observatory
  product we consume).
- Independent product: Zanaga et al., ESA WorldCover 10 m 2020/2021
  product reports (ESA/Zenodo).
- Mission: Drusch et al., "Sentinel-2: ESA's Optical High-Resolution
  Mission for GMES Operational Services", RSE 2012.
- NRT land cover: Brown et al., "Dynamic World, Near real-time global
  10 m land use land cover mapping", Scientific Data 2022.
- Temporal change detection lineage: Zhu & Woodcock, "Continuous change
  detection and classification of land cover using all available Landsat
  data", RSE 2014; Verbesselt et al., BFAST, RSE 2010.
- Reviews: Singh, "Digital change detection techniques using remotely
  sensed data", IJRS 1989; Coppin et al., IJRS 2004; Gómez, White &
  Wulder, "Optical remotely sensed time series data for land cover
  classification: A review", ISPRS JPRS 2016.
Positioning: we do NOT claim novel change detection; the contribution is
the system layer above existing products (see §10).

## 4. Data
IO Annual LULC v003 (2017–2023, backbone), ESA WorldCover 2020/2021
(validation), Sentinel-2 L2A via Earth Search (evidence), Nominatim
(search). Licenses, access verification, and limitations:
docs/DATA_SOURCES.md.

## 5. Method
5.1 canonical land states · 5.2 two-phase event model with conservative
tie-break (D-008) · 5.3 trajectory signatures + archetype grammar ·
5.4 budgeted rarity anomalies (D-009) · 5.5 evidence-grade confidence
(D-010) · 5.6 block pattern clustering · 5.7 grounded narrative layer
(D-007: no free-text generation).

## 6. System
Pipeline → bundles → FastAPI → no-build City Time Machine. Reproducibility
(configs, caches, fingerprints). docs/ARCHITECTURE.md.

## 7. Experiments & results
E-001 geographic benchmark (6 regions, 4 continents, one parameter set);
E-002 cross-product agreement; E-003 normalised change credibility
(honest negative); E-004 temporal holdout (monotone in settlement
regimes, inverted at frontier); E-005 anomaly selectivity. Baselines
B0–B2 ladder.

## 8. Limitations & ethics
Annual cadence; single-backbone bias; confidence ≠ probability; no causal
claims; anomaly language ("rare", never "illicit"); dual-use note (land
monitoring can surveil as well as inform — scope limited to land states,
no person-level inference).

## 9. Future work
Post-v1.0 list in docs/ROADMAP.md (trajectory-aware confidence first).

## 10. Contribution statement (draft, honest)
1. Engineering: credential-free, reproducible pipeline from open products
   to interactive temporal histories at neighbourhood scale.
2. Experimental: 6-region generalization benchmark + temporal-holdout
   confidence evaluation, including documented failure modes.
3. Methodological (modest, to be defended): budgeted signature-rarity
   anomaly definition + holdout-validated evidence grading; we make no
   novelty claim for change detection itself.
