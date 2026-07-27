"""Change-event extraction: from annual state stacks to dated transitions.

The event model is a deliberately simple, defensible two-phase
approximation of a pixel's history:

    pre-phase (dominant state A)  →  final phase (state B, persistent)

A pixel carries a *change event* iff:

- it is observed (non-nodata) in >= min_observed_years years,
- its final state B persists through the last `persistence` years
  (trailing run length >= persistence),
- the trailing run does not span the whole series (something existed
  before it),
- the dominant (modal) pre-phase state A is observed and differs from B.

The event's `year` is the first year of the final persistent run, i.e. the
first annual composite in which the new state appears and then holds.
Because observations are annual composites, the physical change occurred
*between* the previous composite and this one — reporting must say
"between <year-1> and <year>", never a date.

Everything is vectorized NumPy over the (T, H, W) stack; T is small (<=7),
so per-year Python loops over the time axis are fine, per-pixel loops are
not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from citychange.landstate import ANALYSIS_STATES, NODATA
from citychange.params import AnalysisParams


@dataclass(frozen=True)
class EventFields:
    """Per-pixel event decomposition shared by events, trajectory and
    confidence modules (computed once).

    All arrays are (H, W). Pixels without an event have year_index == -1.
    """

    years: tuple[int, ...]
    event: np.ndarray          # bool: pixel carries a change event
    year_index: np.ndarray     # int16: index into `years` of the event, -1 if none
    from_state: np.ndarray     # uint8: modal pre-phase state (0 if none)
    to_state: np.ndarray       # uint8: final persistent state (0 if none)
    trail_len: np.ndarray      # int16: length of the final run equal to last state
    observed_years: np.ndarray # int16: number of non-nodata observations
    pre_mode_frac: np.ndarray  # float32: fraction of observed pre-phase years in modal state
    purity: np.ndarray         # float32: fraction of observed years in {A, B}

    @property
    def year_of_change(self) -> np.ndarray:
        """uint16 raster of event years (0 where no event)."""
        out = np.zeros(self.event.shape, dtype=np.uint16)
        yrs = np.asarray(self.years, dtype=np.uint16)
        out[self.event] = yrs[self.year_index[self.event]]
        return out


def _as_cube(stack: dict[int, np.ndarray]) -> tuple[np.ndarray, tuple[int, ...]]:
    years = tuple(sorted(stack))
    cube = np.stack([stack[y] for y in years], axis=0)
    return cube, years


def extract_events(
    stack: dict[int, np.ndarray], params: AnalysisParams
) -> EventFields:
    """Compute the per-pixel event decomposition for an annual state stack."""
    cube, years = _as_cube(stack)
    t, h, w = cube.shape
    if t < params.persistence + 1:
        raise ValueError(
            f"need at least {params.persistence + 1} annual observations, got {t}"
        )

    final = cube[-1]
    observed = (cube != NODATA).sum(axis=0).astype(np.int16)

    # Trailing run length of the final state (nodata final => run 0).
    trail = np.where(final != NODATA, 1, 0).astype(np.int16)
    alive = final != NODATA
    for i in range(t - 2, -1, -1):
        alive = alive & (cube[i] == final)
        trail = trail + alive.astype(np.int16)

    start_idx = (t - trail).astype(np.int16)  # first index of the final run

    # Pre-phase modal state: per-state counts over indices < start_idx.
    idx = np.arange(t).reshape(t, 1, 1)
    pre_mask = idx < start_idx[None, :, :]
    counts = np.zeros((len(ANALYSIS_STATES), h, w), dtype=np.int16)
    for si, state in enumerate(ANALYSIS_STATES):
        counts[si] = ((cube == state) & pre_mask).sum(axis=0)
    pre_observed = counts.sum(axis=0)
    mode_idx = counts.argmax(axis=0)
    mode_count = np.take_along_axis(counts, mode_idx[None, :, :], axis=0)[0]
    from_state = np.where(
        pre_observed > 0,
        np.asarray(ANALYSIS_STATES, dtype=np.uint8)[mode_idx],
        NODATA,
    ).astype(np.uint8)

    # Conservative tie-break: if the final state is represented in the
    # pre-phase as strongly as the modal state, the history is equally well
    # explained as an excursion that reverted — claim no event.
    final_count_pre = np.zeros_like(mode_count)
    for si, state in enumerate(ANALYSIS_STATES):
        final_count_pre = np.where(final == state, counts[si], final_count_pre)
    strict_majority = mode_count > final_count_pre

    with np.errstate(invalid="ignore", divide="ignore"):
        pre_mode_frac = np.where(
            pre_observed > 0, mode_count / pre_observed, 0.0
        ).astype(np.float32)

    event = (
        (final != NODATA)
        & (trail >= params.persistence)
        & (trail < observed)              # something observed before the final run
        & (from_state != NODATA)
        & (from_state != final)
        & strict_majority
        & (observed >= params.min_observed_years)
    )

    year_index = np.where(event, start_idx, -1).astype(np.int16)
    to_state = np.where(event, final, NODATA).astype(np.uint8)
    from_state = np.where(event, from_state, NODATA).astype(np.uint8)

    # Purity: observed years consistent with the two-phase model {A, B}.
    in_ab = ((cube == from_state[None, :, :]) | (cube == to_state[None, :, :])).sum(
        axis=0
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        purity = np.where(observed > 0, in_ab / observed, 0.0).astype(np.float32)
    purity = np.where(event, purity, 0.0).astype(np.float32)

    return EventFields(
        years=years,
        event=event,
        year_index=year_index,
        from_state=from_state,
        to_state=to_state,
        trail_len=trail,
        observed_years=observed,
        pre_mode_frac=np.where(event, pre_mode_frac, 0.0).astype(np.float32),
        purity=purity,
    )


def change_volumes(fields: EventFields) -> dict[int, dict[tuple[int, int], int]]:
    """Pixels changed per event year, grouped by (from_state, to_state).

    Returns {year: {(from, to): pixel_count}} for years with any events.
    """
    out: dict[int, dict[tuple[int, int], int]] = {}
    ev = fields.event
    if not ev.any():
        return out
    yi = fields.year_index[ev]
    fr = fields.from_state[ev].astype(np.int32)
    to = fields.to_state[ev].astype(np.int32)
    key = yi.astype(np.int32) * 10000 + fr * 100 + to
    uniq, cnt = np.unique(key, return_counts=True)
    for k, c in zip(uniq.tolist(), cnt.tolist()):
        year = fields.years[k // 10000]
        pair = ((k % 10000) // 100, k % 100)
        out.setdefault(year, {})[pair] = int(c)
    return out


def peak_change_period(volumes: dict[int, dict[tuple[int, int], int]]) -> tuple[int, int] | None:
    """The event year with the largest change volume, returned as the
    bounding composite pair (year-1, year) to respect annual-cadence limits."""
    if not volumes:
        return None
    totals = {y: sum(v.values()) for y, v in volumes.items()}
    peak = max(totals, key=lambda y: totals[y])
    return (peak - 1, peak)
