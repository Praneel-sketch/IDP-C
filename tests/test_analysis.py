import numpy as np
import pytest

from citychange.analysis import (
    find_hotspot,
    fraction_trends,
    stable_change_mask,
    state_fractions,
    top_transitions,
    transition_matrix,
)
from citychange.landstate import BUILT, CROPS, NODATA, VEGETATION, WATER


def grid(rows):
    return np.array(rows, dtype=np.uint8)


def test_state_fractions_ignore_nodata():
    g = grid([[BUILT, BUILT], [VEGETATION, NODATA]])
    f = state_fractions(g)
    assert f["built"] == pytest.approx(2 / 3)
    assert f["vegetation"] == pytest.approx(1 / 3)
    assert f["water"] == 0.0


def test_state_fractions_all_nodata_is_nan():
    f = state_fractions(grid([[NODATA]]))
    assert all(np.isnan(v) for v in f.values())


def test_transition_matrix_excludes_nodata_pixels():
    a = grid([[VEGETATION, VEGETATION], [WATER, NODATA]])
    b = grid([[BUILT, VEGETATION], [NODATA, BUILT]])
    m = transition_matrix(a, b)
    # only 2 jointly-observed pixels: veg->built and veg->veg
    assert m[("vegetation", "built")] == pytest.approx(0.5)
    assert m[("vegetation", "vegetation")] == pytest.approx(0.5)
    assert ("water", "built") not in m
    assert sum(m.values()) == pytest.approx(1.0)


def test_transition_matrix_shape_mismatch():
    with pytest.raises(ValueError):
        transition_matrix(grid([[1]]), grid([[1, 2]]))


def test_stable_change_requires_persistence():
    # Pixel history columns:
    #   col 0: veg,veg,built,built  -> stable change
    #   col 1: veg,veg,veg,built    -> change in final year only, not stable
    #   col 2: veg,built,veg,veg    -> flicker back to original, not a change
    #   col 3: veg,veg,veg,veg      -> unchanged
    stack = {
        2020: grid([[VEGETATION, VEGETATION, VEGETATION, VEGETATION]]),
        2021: grid([[VEGETATION, VEGETATION, BUILT, VEGETATION]]),
        2022: grid([[BUILT, VEGETATION, VEGETATION, VEGETATION]]),
        2023: grid([[BUILT, BUILT, VEGETATION, VEGETATION]]),
    }
    mask = stable_change_mask(stack, persistence=2)
    assert mask.tolist() == [[True, False, False, False]]


def test_stable_change_nodata_excluded():
    stack = {
        2021: grid([[NODATA, VEGETATION]]),
        2022: grid([[BUILT, NODATA]]),
        2023: grid([[BUILT, BUILT]]),
    }
    mask = stable_change_mask(stack, persistence=2)
    # col 0: first year unobserved; col 1: unobserved mid-tail breaks persistence
    assert mask.tolist() == [[False, False]]


def test_stable_change_needs_enough_years():
    with pytest.raises(ValueError):
        stable_change_mask({2022: grid([[1]]), 2023: grid([[1]])}, persistence=2)


def test_find_hotspot_locates_dense_block():
    mask = np.zeros((8, 8), dtype=bool)
    mask[4:8, 4:8] = True  # bottom-right 4x4 block fully changed
    h = find_hotspot(mask, block_px=4)
    assert (h.row0, h.col0) == (4, 4)
    assert h.change_fraction == 1.0


def test_find_hotspot_edge_blocks_use_actual_size():
    mask = np.zeros((6, 6), dtype=bool)
    mask[4:6, 4:6] = True  # 2x2 edge block, fully changed
    h = find_hotspot(mask, block_px=4)
    assert (h.row0, h.col0) == (4, 4)
    assert h.change_fraction == 1.0


def test_top_transitions_excludes_self():
    m = {
        ("vegetation", "vegetation"): 0.6,
        ("vegetation", "built"): 0.3,
        ("crops", "built"): 0.1,
    }
    top = top_transitions(m, k=5)
    assert top[0] == ("vegetation", "built", 0.3)
    assert all(f != t for f, t, _ in top)


def test_fraction_trends_years_sorted():
    stack = {
        2023: grid([[BUILT]]),
        2021: grid([[VEGETATION]]),
        2022: grid([[CROPS]]),
    }
    trends = fraction_trends(stack)
    assert list(trends["built"].keys()) == [2021, 2022, 2023]
    assert trends["built"][2023] == 1.0
