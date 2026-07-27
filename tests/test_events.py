import numpy as np
import pytest

from citychange.events import change_volumes, extract_events, peak_change_period
from citychange.landstate import BARE, BUILT, CROPS, NODATA, VEGETATION, WATER
from citychange.params import AnalysisParams

P = AnalysisParams()


def stack_from_sequences(*seqs):
    """Build a {year: grid} stack from per-pixel year sequences (1 row)."""
    t = len(seqs[0])
    years = list(range(2017, 2017 + t))
    arr = np.array(seqs, dtype=np.uint8).T  # (T, n)
    return {y: arr[i][None, :] for i, y in enumerate(years)}


def test_clean_transition_dated_correctly():
    # veg for 3 years, built from 2020 onward -> event year 2020
    stack = stack_from_sequences([VEGETATION] * 3 + [BUILT] * 4)
    f = extract_events(stack, P)
    assert f.event[0, 0]
    assert f.year_of_change[0, 0] == 2020
    assert f.from_state[0, 0] == VEGETATION
    assert f.to_state[0, 0] == BUILT
    assert f.trail_len[0, 0] == 4


def test_flickering_pre_phase_uses_modal_state():
    # crops/veg flicker, then built from 2021: from_state should be modal (crops)
    stack = stack_from_sequences([CROPS, VEGETATION, CROPS, CROPS, BUILT, BUILT, BUILT])
    f = extract_events(stack, P)
    assert f.event[0, 0]
    assert f.from_state[0, 0] == CROPS
    assert f.year_of_change[0, 0] == 2021
    assert f.pre_mode_frac[0, 0] == pytest.approx(3 / 4)


def test_final_year_change_fails_persistence():
    stack = stack_from_sequences([VEGETATION] * 6 + [BUILT])
    f = extract_events(stack, P)
    assert not f.event[0, 0]


def test_stable_pixel_has_no_event():
    stack = stack_from_sequences([BUILT] * 7)
    f = extract_events(stack, P)
    assert not f.event[0, 0]
    assert f.year_of_change[0, 0] == 0


def test_reverted_pixel_has_no_event():
    # veg -> water excursion -> veg persistent: pre-phase is tied between
    # veg and water, so the conservative tie-break claims no event
    stack = stack_from_sequences(
        [VEGETATION, VEGETATION, WATER, WATER, VEGETATION, VEGETATION, VEGETATION]
    )
    f = extract_events(stack, P)
    assert not f.event[0, 0]


def test_short_initial_observation_still_yields_event():
    # 1 year veg, then 2 years water, then 4 years veg: water has strictly
    # more pre-phase evidence, so this IS a water->veg event (e.g. a lake
    # drying), dated 2020, with reduced pre-stability
    stack = stack_from_sequences(
        [VEGETATION, WATER, WATER, VEGETATION, VEGETATION, VEGETATION, VEGETATION]
    )
    f = extract_events(stack, P)
    assert f.event[0, 0]
    assert f.from_state[0, 0] == WATER
    assert f.year_of_change[0, 0] == 2020


def test_mostly_nodata_pixel_excluded():
    stack = stack_from_sequences(
        [NODATA, NODATA, NODATA, NODATA, VEGETATION, BUILT, BUILT]
    )
    f = extract_events(stack, P)  # only 3 observed years < min_observed_years
    assert not f.event[0, 0]


def test_nodata_breaks_trailing_run():
    stack = stack_from_sequences(
        [VEGETATION, VEGETATION, VEGETATION, BUILT, BUILT, NODATA, BUILT]
    )
    f = extract_events(stack, P)  # trailing run is 1 (nodata interrupts)
    assert not f.event[0, 0]


def test_staged_transition_dates_final_phase():
    # veg -> bare (construction) -> built from 2021
    stack = stack_from_sequences(
        [VEGETATION, VEGETATION, VEGETATION, BARE, BUILT, BUILT, BUILT]
    )
    f = extract_events(stack, P)
    assert f.event[0, 0]
    assert f.to_state[0, 0] == BUILT
    assert f.year_of_change[0, 0] == 2021
    assert f.from_state[0, 0] == VEGETATION  # modal pre-state, not bare


def test_change_volumes_and_peak():
    stack = stack_from_sequences(
        [VEGETATION, VEGETATION, BUILT, BUILT, BUILT, BUILT, BUILT],   # 2019
        [CROPS, CROPS, CROPS, BUILT, BUILT, BUILT, BUILT],             # 2020
        [CROPS, CROPS, CROPS, BUILT, BUILT, BUILT, BUILT],             # 2020
        [WATER] * 7,                                                   # none
    )
    f = extract_events(stack, P)
    vols = change_volumes(f)
    assert vols[2019][(VEGETATION, BUILT)] == 1
    assert vols[2020][(CROPS, BUILT)] == 2
    assert peak_change_period(vols) == (2019, 2020)


def test_no_events_no_peak():
    stack = stack_from_sequences([WATER] * 7)
    f = extract_events(stack, P)
    assert change_volumes(f) == {}
    assert peak_change_period({}) is None


def test_too_few_years_raises():
    stack = stack_from_sequences([VEGETATION, BUILT])
    with pytest.raises(ValueError):
        extract_events(stack, AnalysisParams(persistence=2))
