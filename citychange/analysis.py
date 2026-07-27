"""Temporal land-state analysis for CityChange v0.1.

Everything here operates on canonical state grids (see landstate.py) and is
pure NumPy — no I/O — so it is unit-testable on synthetic arrays.

Noise principle: a single-year class flip in the source product is weak
evidence. v0.1 therefore distinguishes raw first-vs-last change from
"stable change", where the final state must persist for the last
`persistence` years of the series. This is the seed of the evidence /
confidence machinery of later phases, not a substitute for it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from citychange.landstate import ANALYSIS_STATES, NODATA, STATE_NAMES


def state_fractions(state_grid: np.ndarray) -> dict[str, float]:
    """Fraction of *observed* (non-nodata) pixels per canonical state."""
    observed = state_grid != NODATA
    n = int(observed.sum())
    if n == 0:
        return {STATE_NAMES[s]: float("nan") for s in ANALYSIS_STATES}
    return {
        STATE_NAMES[s]: float((state_grid == s).sum()) / n
        for s in ANALYSIS_STATES
    }


def fraction_trends(stack: dict[int, np.ndarray]) -> dict[str, dict[int, float]]:
    """Per-state fraction time series: {state_name: {year: fraction}}."""
    trends: dict[str, dict[int, float]] = {STATE_NAMES[s]: {} for s in ANALYSIS_STATES}
    for year in sorted(stack):
        for name, frac in state_fractions(stack[year]).items():
            trends[name][year] = frac
    return trends


def transition_matrix(a: np.ndarray, b: np.ndarray) -> dict[tuple[str, str], float]:
    """Fraction of jointly-observed pixels per (state_at_a -> state_at_b) pair.

    Pixels that are nodata in either grid are excluded: an unobserved pixel
    cannot testify about change.
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    valid = (a != NODATA) & (b != NODATA)
    n = int(valid.sum())
    result: dict[tuple[str, str], float] = {}
    if n == 0:
        return result
    for s_from in ANALYSIS_STATES:
        from_mask = valid & (a == s_from)
        if not from_mask.any():
            continue
        to_states, counts = np.unique(b[from_mask], return_counts=True)
        for s_to, c in zip(to_states.tolist(), counts.tolist()):
            result[(STATE_NAMES[s_from], STATE_NAMES[int(s_to)])] = c / n
    return result


def stable_change_mask(stack: dict[int, np.ndarray], persistence: int = 2) -> np.ndarray:
    """Pixels whose state genuinely changed over the series, by a
    persistence rule:

    - observed (non-nodata) in the first year and in each of the last
      `persistence` years,
    - final state differs from the first-year state,
    - final state is identical across the last `persistence` years.

    This suppresses single-year classification flicker at the cost of
    missing changes that occur in the very last year of the series — an
    acceptable trade for v0.1 and recorded in docs/DECISIONS.md.
    """
    years = sorted(stack)
    if len(years) < persistence + 1:
        raise ValueError(f"need at least {persistence + 1} years, got {len(years)}")
    first = stack[years[0]]
    tail = [stack[y] for y in years[-persistence:]]

    final = tail[-1]
    mask = (first != NODATA) & (final != NODATA) & (final != first)
    for grid in tail[:-1]:
        mask &= grid == final
    return mask


@dataclass(frozen=True)
class Hotspot:
    """Coarse block with the highest stable-change density."""

    row0: int  # top-left pixel of the block
    col0: int
    block_px: int
    change_fraction: float  # stable-change pixels / block pixels


def find_hotspot(change_mask: np.ndarray, block_px: int) -> Hotspot:
    """Locate the block_px x block_px block with the largest fraction of
    changed pixels (edge blocks may be smaller; fractions use actual size)."""
    if change_mask.ndim != 2:
        raise ValueError("change_mask must be 2-D")
    h, w = change_mask.shape
    best = Hotspot(0, 0, block_px, -1.0)
    for r0 in range(0, h, block_px):
        for c0 in range(0, w, block_px):
            block = change_mask[r0 : r0 + block_px, c0 : c0 + block_px]
            frac = float(block.mean()) if block.size else 0.0
            if frac > best.change_fraction:
                best = Hotspot(r0, c0, block_px, frac)
    return best


def top_transitions(
    matrix: dict[tuple[str, str], float], k: int = 5, exclude_self: bool = True
) -> list[tuple[str, str, float]]:
    """The k largest (from, to, fraction) entries, optionally skipping
    self-transitions (unchanged land)."""
    items = [
        (f, t, v)
        for (f, t), v in matrix.items()
        if not (exclude_self and f == t)
    ]
    items.sort(key=lambda x: -x[2])
    return items[:k]
