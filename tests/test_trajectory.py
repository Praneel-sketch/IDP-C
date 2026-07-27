import numpy as np

from citychange.events import extract_events
from citychange.landstate import BARE, BUILT, CROPS, NODATA, VEGETATION, WATER
from citychange.params import AnalysisParams
from citychange.trajectory import (
    DIRECT_CHANGE,
    FLICKER_STABLE,
    FLUCTUATING,
    NOISY_CHANGE,
    REVERTED,
    STABLE,
    STAGED_CHANGE,
    UNOBSERVED,
    classify_archetypes,
    cluster_blocks,
    block_features,
    decode_signature,
    encode_signatures,
    rarity,
    signature_stats,
)

P = AnalysisParams()


def stack_from_sequences(*seqs):
    t = len(seqs[0])
    years = list(range(2017, 2017 + t))
    arr = np.array(seqs, dtype=np.uint8).T
    return {y: arr[i][None, :] for i, y in enumerate(years)}


def classify(*seqs):
    stack = stack_from_sequences(*seqs)
    fields = extract_events(stack, P)
    return classify_archetypes(stack, fields, P)[0]


def test_signature_encoding_roundtrip():
    stack = stack_from_sequences(
        [VEGETATION, VEGETATION, BARE, BUILT, BUILT, BUILT, BUILT]
    )
    sig = encode_signatures(stack)
    assert decode_signature(int(sig[0, 0])) == ["vegetation", "bare", "built"]


def test_signature_skips_nodata_gap():
    with_gap = stack_from_sequences(
        [VEGETATION, NODATA, VEGETATION, BUILT, BUILT, BUILT, BUILT]
    )
    without = stack_from_sequences(
        [VEGETATION, VEGETATION, VEGETATION, BUILT, BUILT, BUILT, BUILT]
    )
    assert int(encode_signatures(with_gap)[0, 0]) == int(
        encode_signatures(without)[0, 0]
    )


def test_archetype_grammar():
    assert classify([BUILT] * 7)[0] == STABLE
    assert classify([VEGETATION] * 3 + [BUILT] * 4)[0] == DIRECT_CHANGE
    assert (
        classify([VEGETATION, VEGETATION, VEGETATION, BARE, BUILT, BUILT, BUILT])[0]
        == STAGED_CHANGE
    )
    # flicker then persistent change -> noisy_change
    assert (
        classify([CROPS, VEGETATION, CROPS, VEGETATION, BUILT, BUILT, BUILT])[0]
        == NOISY_CHANGE
    )
    # persistent excursion that reversed (tie-broken to no event)
    assert (
        classify([VEGETATION, VEGETATION, WATER, WATER, VEGETATION, VEGETATION, VEGETATION])[0]
        == REVERTED
    )
    # single-year excursion
    assert (
        classify([CROPS, CROPS, VEGETATION, CROPS, CROPS, CROPS, CROPS])[0]
        == FLICKER_STABLE
    )
    # two-state alternation
    assert (
        classify([WATER, VEGETATION, WATER, VEGETATION, WATER, VEGETATION, WATER])[0]
        == FLUCTUATING
    )
    # too few observations
    assert (
        classify([NODATA, NODATA, NODATA, NODATA, BUILT, BUILT, BUILT])[0]
        == UNOBSERVED
    )


def test_rarity_flags_infrequent_signature():
    seqs = [[VEGETATION] * 7] * 300 + [
        [VEGETATION, VEGETATION, VEGETATION, WATER, BUILT, WATER, WATER]
    ]
    stack = stack_from_sequences(*seqs)
    sig = encode_signatures(stack)
    analysed = np.ones(sig.shape, dtype=bool)
    mask, table = rarity(sig, analysed, P)
    assert mask[0, 300]
    assert not mask[0, 0]
    assert len(table) == 1
    assert table[0]["pixels"] == 1


def test_rarity_ignores_static_states():
    # one pixel of stable water among 300 stable vegetation: rare, but a
    # static state is not an unusual *trajectory*
    seqs = [[VEGETATION] * 7] * 300 + [[WATER] * 7]
    stack = stack_from_sequences(*seqs)
    sig = encode_signatures(stack)
    mask, table = rarity(sig, np.ones(sig.shape, dtype=bool), P)
    assert not mask.any()
    assert table == []


def test_rarity_respects_area_budget():
    # 1000 stable pixels + 60 pixels of one rare-but-not-rarest signature
    # + 5 pixels of an even rarer one; budget 2% of 1065 ≈ 21 px keeps the
    # 5-px signature but cannot afford the 60-px one
    seqs = (
        [[VEGETATION] * 7] * 1000
        + [[VEGETATION, VEGETATION, WATER, WATER, WATER, WATER, WATER]] * 60
        + [[VEGETATION, WATER, BUILT, BUILT, BUILT, BUILT, BUILT]] * 5
    )
    stack = stack_from_sequences(*seqs)
    sig = encode_signatures(stack)
    mask, table = rarity(sig, np.ones(sig.shape, dtype=bool), P)
    assert int(mask.sum()) == 5
    assert len(table) == 1
    assert table[0]["pixels"] == 5


def test_signature_stats_ordering():
    seqs = [[VEGETATION] * 7] * 3 + [[BUILT] * 7] * 2
    stack = stack_from_sequences(*seqs)
    sig = encode_signatures(stack)
    stats = signature_stats(sig, np.ones(sig.shape, dtype=bool))
    assert stats[0]["signature"] == "vegetation"
    assert stats[0]["pixels"] == 3
    assert abs(sum(s["fraction"] for s in stats) - 1.0) < 1e-9


def test_block_clustering_separates_changed_from_stable():
    rng = np.random.default_rng(0)
    h = w = 40
    t = 7
    cube = np.full((t, h, w), VEGETATION, dtype=np.uint8)
    cube[3:, :, 20:] = BUILT  # right half converts in 2020
    stack = {2017 + i: cube[i] for i in range(t)}
    fields = extract_events(stack, P)
    bf = block_features(stack, fields, AnalysisParams(block_px=10))
    labels, descriptions, score = cluster_blocks(bf, AnalysisParams(block_px=10, cluster_k_min=2, cluster_k_max=3))
    labels_grid = labels.reshape(bf.grid_shape)
    # all-left blocks share a label; all-right blocks share a different one
    assert len(set(labels_grid[:, 0].tolist())) == 1
    assert len(set(labels_grid[:, -1].tolist())) == 1
    assert labels_grid[0, 0] != labels_grid[0, -1]
    changed_desc = descriptions[labels_grid[0, -1]]
    assert changed_desc["dominant_final_state"] == "built"
    assert changed_desc["changed_fraction"] > 0.9
