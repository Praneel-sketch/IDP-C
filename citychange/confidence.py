"""Graded confidence for detected change events.

IMPORTANT FRAMING: these scores are documented evidence heuristics, NOT
calibrated probabilities. They combine four observable evidence factors,
each in [0, 1], into a weighted score used for tiering and ranking. The
evaluation chapter measures how the tiers relate to independent
cross-product agreement — that relationship, not the raw number, is the
scientific claim.

Factors (per event pixel):

1. persistence  — how long the new state has held, relative to what the
                  series could show (longer hold = harder to explain as
                  classifier noise).
2. pre-stability— how consistently the pixel showed its previous state
                  before the transition.
3. purity       — fraction of the pixel's observed years consistent with
                  the two-phase model (A years + B years).
4. spatial      — fraction of the 3×3 neighbourhood undergoing a change to
                  the same final state; isolated one-pixel changes are far
                  more likely to be noise than coherent patches.

All factors are computed from observations; none encodes any location.
"""

from __future__ import annotations

import numpy as np

from citychange.events import EventFields
from citychange.params import AnalysisParams

TIER_NAMES = {0: "none", 1: "low", 2: "medium", 3: "high"}


def _neighbor_same_change_fraction(fields: EventFields) -> np.ndarray:
    """For each pixel: fraction of its 8 neighbours that are event pixels
    with the same to_state. Computed with array shifts — no SciPy needed."""
    h, w = fields.event.shape
    same = np.zeros((h, w), dtype=np.float32)
    valid = np.zeros((h, w), dtype=np.float32)
    to = fields.to_state

    shifts = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for dr, dc in shifts:
        r0, r1 = max(dr, 0), h + min(dr, 0)
        q0, q1 = max(dc, 0), w + min(dc, 0)
        nr0, nr1 = max(-dr, 0), h + min(-dr, 0)
        nq0, nq1 = max(-dc, 0), w + min(-dc, 0)
        neigh_event = fields.event[nr0:nr1, nq0:nq1]
        neigh_to = to[nr0:nr1, nq0:nq1]
        same[r0:r1, q0:q1] += (neigh_event & (neigh_to == to[r0:r1, q0:q1])).astype(
            np.float32
        )
        valid[r0:r1, q0:q1] += 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(valid > 0, same / valid, 0.0).astype(np.float32)


def score_events(fields: EventFields, params: AnalysisParams) -> np.ndarray:
    """float32 confidence score in [0, 1] per pixel (0 where no event)."""
    t = len(fields.years)
    # Persistence saturates: holding for persistence+2 years (or the longest
    # hold the series can show, if shorter) scores 1.0.
    saturation = min(params.persistence + 2, t - 1)
    persist = np.clip(fields.trail_len / saturation, 0.0, 1.0).astype(np.float32)

    score = (
        params.w_persistence * persist
        + params.w_pre_stability * fields.pre_mode_frac
        + params.w_purity * fields.purity
        + params.w_spatial * _neighbor_same_change_fraction(fields)
    ).astype(np.float32)
    return np.where(fields.event, score, 0.0).astype(np.float32)


def tier_events(scores: np.ndarray, fields: EventFields, params: AnalysisParams) -> np.ndarray:
    """uint8 tier raster: 0 none, 1 low, 2 medium, 3 high."""
    tiers = np.zeros(scores.shape, dtype=np.uint8)
    tiers[fields.event] = 1
    tiers[fields.event & (scores >= params.medium_tier)] = 2
    tiers[fields.event & (scores >= params.high_tier)] = 3
    return tiers


def tier_summary(tiers: np.ndarray) -> dict[str, int]:
    """Pixel counts per confidence tier (events only)."""
    return {
        TIER_NAMES[t]: int((tiers == t).sum()) for t in (1, 2, 3)
    }
