"""Trajectory modelling: per-pixel state sequences as first-class objects.

Three complementary representations, all location-independent:

1. **Signatures** — the run-length compressed sequence of states, ignoring
   durations (e.g. vegetation→bare→built). Encoded per pixel as a base-8
   integer so that a region's full signature distribution is one
   np.unique() away. Signature frequency is the basis of rarity/anomaly
   scoring: a signature is anomalous in a region if it explains less than
   `rarity_threshold` of analysed pixels. Language rule: rare, not wrong.

2. **Archetypes** — a small interpretable grammar classifying every pixel:

   stable            one state throughout (allowing nodata gaps)
   flicker_stable    dominant state with a brief excursion, returns to it
   direct_change     A → B, single transition (change event)
   staged_change     A → M → B, monotone two-step (e.g. clearing → built)
   noisy_change      change event preceded by flickering years
   reverted          A → B → A, a persistent excursion that reversed
   fluctuating       alternation between two states (>= 3 switches)
   unstable          anything more chaotic
   unobserved        too few valid observations

   Rules operate on structure (runs, switches), never on which states or
   places are involved — no geographic special cases.

3. **Block features + clustering** — coarse blocks summarised by
   composition/timing/stability features and clustered with k-means to
   surface "areas that evolved similarly" without hand-drawn boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from citychange.events import EventFields
from citychange.landstate import NODATA, STATE_NAMES
from citychange.params import AnalysisParams

# Archetype codes (uint8 raster values).
UNOBSERVED = 0
STABLE = 1
FLICKER_STABLE = 2
DIRECT_CHANGE = 3
STAGED_CHANGE = 4
REVERTED = 5
FLUCTUATING = 6
UNSTABLE = 7
NOISY_CHANGE = 8

ARCHETYPE_NAMES: dict[int, str] = {
    UNOBSERVED: "unobserved",
    STABLE: "stable",
    FLICKER_STABLE: "stable_with_flicker",
    DIRECT_CHANGE: "direct_change",
    STAGED_CHANGE: "staged_change",
    REVERTED: "reverted",
    FLUCTUATING: "fluctuating",
    UNSTABLE: "unstable",
    NOISY_CHANGE: "noisy_change",
}

CHANGE_ARCHETYPES = (DIRECT_CHANGE, STAGED_CHANGE, NOISY_CHANGE)


def _as_cube(stack: dict[int, np.ndarray]) -> tuple[np.ndarray, tuple[int, ...]]:
    years = tuple(sorted(stack))
    return np.stack([stack[y] for y in years], axis=0), years


def encode_signatures(stack: dict[int, np.ndarray]) -> np.ndarray:
    """Base-8 integer encoding of each pixel's run-length state signature.

    Nodata years are skipped (the last observed state carries forward), so
    a cloud gap does not fabricate a transition. Pixels never observed
    encode to 0.
    """
    cube, _years = _as_cube(stack)
    t = cube.shape[0]
    sig = np.zeros(cube.shape[1:], dtype=np.int64)
    last = np.zeros(cube.shape[1:], dtype=np.uint8)
    for i in range(t):
        cur = cube[i]
        valid = cur != NODATA
        changed = valid & (cur != last)
        sig = np.where(changed, sig * 8 + cur, sig)
        last = np.where(valid, cur, last)
    return sig


def decode_signature(sig: int) -> list[str]:
    """Signature integer -> ordered state names, e.g. [vegetation, built]."""
    if sig <= 0:
        return []
    digits: list[int] = []
    while sig > 0:
        digits.append(sig % 8)
        sig //= 8
    return [STATE_NAMES[d] for d in reversed(digits)]


def signature_stats(
    sig: np.ndarray, analysed: np.ndarray
) -> list[dict[str, object]]:
    """Frequency table of signatures over analysed pixels, most common first."""
    vals, counts = np.unique(sig[analysed], return_counts=True)
    total = int(counts.sum())
    order = np.argsort(-counts)
    out = []
    for i in order:
        v = int(vals[i])
        out.append(
            {
                "signature": "→".join(decode_signature(v)) or "unobserved",
                "states": decode_signature(v),
                "pixels": int(counts[i]),
                "fraction": counts[i] / total if total else 0.0,
            }
        )
    return out


def _switch_count(cube: np.ndarray) -> np.ndarray:
    """Number of state switches per pixel, skipping nodata years."""
    t = cube.shape[0]
    switches = np.zeros(cube.shape[1:], dtype=np.int16)
    last = np.zeros(cube.shape[1:], dtype=np.uint8)
    for i in range(t):
        cur = cube[i]
        valid = cur != NODATA
        seen = last != NODATA
        switches += (valid & seen & (cur != last)).astype(np.int16)
        last = np.where(valid, cur, last)
    return switches


def _states_involved(cube: np.ndarray) -> np.ndarray:
    """Number of distinct observed states per pixel."""
    present = np.zeros(cube.shape[1:], dtype=np.int16)
    for state in range(1, 7):
        present += (cube == state).any(axis=0).astype(np.int16)
    return present


def classify_archetypes(
    stack: dict[int, np.ndarray], fields: EventFields, params: AnalysisParams
) -> np.ndarray:
    """uint8 archetype raster, applying the grammar in the module docstring."""
    cube, _years = _as_cube(stack)
    switches = _switch_count(cube)
    n_states = _states_involved(cube)
    first_observed = _first_observed_state(cube)
    final = cube[-1]

    observed_ok = fields.observed_years >= params.min_observed_years
    ends_at_start = (final != NODATA) & (final == first_observed)
    ev = fields.event

    dom_count = np.zeros(cube.shape[1:], dtype=np.int16)
    for state in range(1, 7):
        c = (cube == state).sum(axis=0).astype(np.int16)
        dom_count = np.maximum(dom_count, c)
    excursion_years = fields.observed_years - dom_count

    # Priority order: later assignments override earlier ones only where
    # their condition holds; conditions are mutually exclusive by design.
    out = np.full(cube.shape[1:], UNSTABLE, dtype=np.uint8)
    # Two-state alternation without a persistent outcome.
    out[(switches >= 3) & (n_states == 2) & ~ev] = FLUCTUATING
    # Non-event pixels that returned to their initial state.
    returned = ~ev & ends_at_start
    out[returned & (switches == 2) & (excursion_years >= 2)] = REVERTED
    out[returned & (switches == 2) & (excursion_years < 2)] = FLICKER_STABLE
    # Change events, by how clean the path was.
    out[ev & (switches == 1)] = DIRECT_CHANGE
    out[ev & (switches == 2) & (n_states == 3)] = STAGED_CHANGE
    out[ev & (switches == 2) & (n_states == 2)] = DIRECT_CHANGE
    out[ev & (switches >= 3)] = NOISY_CHANGE
    # No switches at all.
    out[switches == 0] = STABLE
    out[~observed_ok] = UNOBSERVED
    return out


def _first_observed_state(cube: np.ndarray) -> np.ndarray:
    first = np.zeros(cube.shape[1:], dtype=np.uint8)
    for i in range(cube.shape[0] - 1, -1, -1):
        cur = cube[i]
        first = np.where(cur != NODATA, cur, first)
    return first


def rarity(
    sig: np.ndarray, analysed: np.ndarray, params: AnalysisParams
) -> tuple[np.ndarray, list[dict[str, object]]]:
    """Anomaly mask + table of rare *trajectories*.

    Two deliberate restrictions keep "unusual" meaningful:

    - Only multi-state signatures qualify: a rare but static state is a
      composition fact, not an unusual evolution.
    - A cumulative area budget (params.anomaly_budget): starting from the
      rarest qualifying signatures, pixels are flagged until the budget is
      exhausted, so the anomaly layer highlights the genuinely exceptional
      instead of ~10% of a noisy region.

    This is a *statistical* statement about rarity within the region —
    reported as such, never as wrongdoing.
    """
    vals, counts = np.unique(sig[analysed], return_counts=True)
    total = int(counts.sum())
    if total == 0:
        return np.zeros(sig.shape, dtype=bool), []
    freq = counts / total

    multi_state = np.array([len(decode_signature(int(v))) >= 2 for v in vals])
    qualifying = multi_state & (freq < params.rarity_threshold)

    order = np.argsort(counts)  # rarest first
    budget_px = int(params.anomaly_budget * total)
    chosen: list[int] = []
    spent = 0
    for i in order:
        if not qualifying[i]:
            continue
        if spent + counts[i] > budget_px and chosen:
            break
        chosen.append(i)
        spent += int(counts[i])

    rare_vals = vals[chosen]
    mask = np.isin(sig, rare_vals) & analysed
    table = [
        {
            "signature": "→".join(decode_signature(int(vals[i]))),
            "pixels": int(counts[i]),
            "fraction": float(freq[i]),
        }
        for i in chosen
    ]
    table.sort(key=lambda r: -r["pixels"])
    return mask, table


# ---------------------------------------------------------------------------
# Block-level features and clustering ("areas that evolved similarly").
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BlockFeatures:
    """Per-block trajectory features on a coarse grid.

    rows/cols index blocks; features is (n_blocks, n_features) float32;
    block_rc maps feature rows to (block_row, block_col).
    """

    block_px: int
    grid_shape: tuple[int, int]  # block grid (rows, cols)
    block_rc: np.ndarray         # (n, 2) int
    features: np.ndarray         # (n, f) float32
    feature_names: tuple[str, ...]


def block_features(
    stack: dict[int, np.ndarray], fields: EventFields, params: AnalysisParams
) -> BlockFeatures:
    cube, years = _as_cube(stack)
    h, w = cube.shape[1:]
    bp = params.block_px
    rows = -(-h // bp)
    cols = -(-w // bp)

    first = _first_observed_state(cube)
    final = cube[-1]
    yoc = fields.year_of_change.astype(np.float32)
    yoc_norm = np.where(
        fields.event, (yoc - years[0]) / max(years[-1] - years[0], 1), 0.0
    )
    switches = _switch_count(cube).astype(np.float32)

    names: list[str] = []
    layers: list[np.ndarray] = []
    for s in range(1, 7):
        layers.append((first == s).astype(np.float32))
        names.append(f"first_{STATE_NAMES[s]}")
    for s in range(1, 7):
        layers.append((final == s).astype(np.float32))
        names.append(f"final_{STATE_NAMES[s]}")
    layers.append(fields.event.astype(np.float32))
    names.append("changed")
    layers.append(yoc_norm.astype(np.float32))
    names.append("change_timing")
    layers.append(switches / max(len(years) - 1, 1))
    names.append("volatility")

    feats = np.zeros((rows * cols, len(layers)), dtype=np.float32)
    rc = np.zeros((rows * cols, 2), dtype=np.int32)
    i = 0
    for br in range(rows):
        for bc in range(cols):
            sl = np.s_[br * bp : (br + 1) * bp, bc * bp : (bc + 1) * bp]
            rc[i] = (br, bc)
            for j, layer in enumerate(layers):
                feats[i, j] = float(layer[sl].mean())
            i += 1
    return BlockFeatures(
        block_px=bp,
        grid_shape=(rows, cols),
        block_rc=rc,
        features=feats,
        feature_names=tuple(names),
    )


def cluster_blocks(
    bf: BlockFeatures, params: AnalysisParams, seed: int = 42
) -> tuple[np.ndarray, list[dict[str, object]], float]:
    """K-means over block features; k chosen by silhouette score.

    Returns (labels per block (n,), cluster descriptions, silhouette).
    Falls back to a single cluster if variance is degenerate.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    x = bf.features
    if x.std(axis=0).max() < 1e-6 or len(x) < params.cluster_k_min + 1:
        return np.zeros(len(x), dtype=np.int32), [_describe_cluster(bf, np.zeros(len(x), dtype=bool) | True)], 0.0

    xs = StandardScaler().fit_transform(x)
    best_labels, best_k, best_score = None, None, -2.0
    for k in range(params.cluster_k_min, min(params.cluster_k_max, len(x) - 1) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=seed)
        labels = km.fit_predict(xs)
        if len(np.unique(labels)) < 2:
            continue
        score = float(silhouette_score(xs, labels, sample_size=min(2000, len(xs)), random_state=seed))
        if score > best_score:
            best_labels, best_k, best_score = labels, k, score
    if best_labels is None:
        return np.zeros(len(x), dtype=np.int32), [_describe_cluster(bf, np.ones(len(x), dtype=bool))], 0.0

    descriptions = [
        _describe_cluster(bf, best_labels == c) for c in range(best_k)
    ]
    return best_labels.astype(np.int32), descriptions, best_score


def _describe_cluster(bf: BlockFeatures, member: np.ndarray) -> dict[str, object]:
    """Grounded description of a cluster from its mean feature vector."""
    mean = bf.features[member].mean(axis=0) if member.any() else np.zeros(len(bf.feature_names))
    f = dict(zip(bf.feature_names, mean.tolist()))
    dom_first = max((n for n in f if n.startswith("first_")), key=lambda n: f[n])
    dom_final = max((n for n in f if n.startswith("final_")), key=lambda n: f[n])
    return {
        "blocks": int(member.sum()),
        "changed_fraction": round(f["changed"], 3),
        "dominant_initial_state": dom_first.removeprefix("first_"),
        "dominant_final_state": dom_final.removeprefix("final_"),
        "mean_change_timing": round(f["change_timing"], 3),
        "volatility": round(f["volatility"], 3),
    }
