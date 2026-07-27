import numpy as np

from citychange.confidence import score_events, tier_events, tier_summary
from citychange.events import extract_events
from citychange.landstate import BUILT, CROPS, VEGETATION, WATER
from citychange.params import AnalysisParams

P = AnalysisParams()


def test_coherent_patch_scores_higher_than_isolated_pixel():
    t, h, w = 7, 9, 9
    cube = np.full((t, h, w), VEGETATION, dtype=np.uint8)
    # coherent 4x4 patch converts to built in 2020
    cube[3:, 0:4, 0:4] = BUILT
    # isolated single pixel converts the same year
    cube[3:, 7, 7] = BUILT
    stack = {2017 + i: cube[i] for i in range(t)}
    fields = extract_events(stack, P)
    scores = score_events(fields, P)
    assert scores[1, 1] > scores[7, 7]
    assert scores[7, 7] > 0  # still an event, just weaker evidence


def test_long_hold_scores_higher_than_short_hold():
    stack = {
        y: np.array(
            [[VEGETATION if y < 2019 else BUILT, VEGETATION if y < 2022 else BUILT]],
            dtype=np.uint8,
        )
        for y in range(2017, 2024)
    }
    fields = extract_events(stack, P)
    scores = score_events(fields, P)
    assert fields.event[0, 0] and fields.event[0, 1]
    assert scores[0, 0] > scores[0, 1]


def test_noisy_history_scores_lower_than_clean():
    clean = [VEGETATION] * 4 + [BUILT] * 3
    noisy = [VEGETATION, CROPS, VEGETATION, WATER, BUILT, BUILT, BUILT]
    arr = np.array([clean, noisy], dtype=np.uint8).T
    stack = {2017 + i: arr[i][None, :] for i in range(7)}
    fields = extract_events(stack, P)
    scores = score_events(fields, P)
    assert fields.event[0, 0] and fields.event[0, 1]
    assert scores[0, 0] > scores[0, 1]


def test_scores_bounded_and_zero_without_event():
    cube = np.full((7, 5, 5), WATER, dtype=np.uint8)
    stack = {2017 + i: cube[i] for i in range(7)}
    fields = extract_events(stack, P)
    scores = score_events(fields, P)
    assert (scores == 0).all()


def test_tiers_partition_events():
    t, h, w = 7, 6, 6
    cube = np.full((t, h, w), VEGETATION, dtype=np.uint8)
    cube[2:, 0:3, 0:3] = BUILT
    cube[5:, 5, 5] = BUILT
    stack = {2017 + i: cube[i] for i in range(t)}
    fields = extract_events(stack, P)
    scores = score_events(fields, P)
    tiers = tier_events(scores, fields, P)
    summary = tier_summary(tiers)
    assert sum(summary.values()) == int(fields.event.sum())
    assert (tiers[~fields.event] == 0).all()
