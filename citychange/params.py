"""Global analysis parameters.

Every threshold used by the intelligence pipeline lives here, with one
global default set. There are deliberately NO per-region parameters: the
benchmark (configs/benchmark/) runs all regions with identical settings,
which is what makes the geographic-generalization claim testable.

Regions may override values via an `analysis:` block in their YAML only
for explicitly experimental runs; the benchmark never does.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnalysisParams:
    # A change event requires the new state to persist this many final years.
    persistence: int = 2
    # A pixel needs at least this many observed (non-nodata) years to be analysed.
    min_observed_years: int = 4
    # Coarse block edge (pixels) for hotspots / clustering (250 m at 10 m px).
    block_px: int = 25
    # Number of change hotspots reported.
    n_hotspots: int = 5
    # A trajectory signature is "rare" if it covers less than this fraction
    # of analysed pixels in the region.
    rarity_threshold: float = 0.005
    # Total area budget for the anomaly set: starting from the rarest
    # signatures, pixels are flagged until this fraction of analysed area
    # is reached. Keeps "unusual" selective instead of covering 10% of a
    # noisy region.
    anomaly_budget: float = 0.02
    # Confidence weights: persistence, pre-transition stability, sequence
    # purity, 3x3 spatial support. Must sum to 1.
    w_persistence: float = 0.3
    w_pre_stability: float = 0.2
    w_purity: float = 0.2
    w_spatial: float = 0.3
    # Confidence tier boundaries (score in [0, 1]).
    high_tier: float = 0.75
    medium_tier: float = 0.5
    # k range explored for block-level pattern clustering.
    cluster_k_min: int = 3
    cluster_k_max: int = 6

    def __post_init__(self) -> None:
        if self.persistence < 1:
            raise ValueError("persistence must be >= 1")
        w = self.w_persistence + self.w_pre_stability + self.w_purity + self.w_spatial
        if abs(w - 1.0) > 1e-9:
            raise ValueError(f"confidence weights must sum to 1, got {w}")
        if not 0 < self.medium_tier < self.high_tier < 1:
            raise ValueError("need 0 < medium_tier < high_tier < 1")


DEFAULT_PARAMS = AnalysisParams()
