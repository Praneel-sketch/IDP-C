"""Cross-product validation: IO Annual LULC vs ESA WorldCover.

Neither product is ground truth; both are independent derived products
with different sensors, models and error profiles. What this module
establishes:

1. **State agreement** (2020 and 2021): how often the two products assign
   the same canonical state — overall, per state (IoU), and as a confusion
   matrix. High agreement on built/water lends weight to change claims
   about those states; low agreement (typically vegetation/crops
   boundaries) marks where per-pixel claims must stay humble.

2. **Confidence-vs-agreement**: for change events whose new state was in
   place by 2021, does WorldCover 2021 independently show that state? If
   CityChange's confidence tiers mean anything, high-tier events should
   agree more often than low-tier events. This is the honest, feasible
   substitute for calibration against unavailable ground truth.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from citychange.config import RegionConfig
from citychange.datasets.esa_worldcover import fetch_worldcover_states
from citychange.datasets.io_annual_lulc import fetch_annual_stack
from citychange.confidence import score_events, tier_events
from citychange.events import extract_events
from citychange.landstate import ANALYSIS_STATES, NODATA, STATE_NAMES, remap_to_states
from citychange.params import DEFAULT_PARAMS, AnalysisParams
from citychange.pipeline import bundle_dir

log = logging.getLogger(__name__)


def _agreement(a: np.ndarray, b: np.ndarray) -> dict:
    """Agreement metrics between two canonical state grids."""
    valid = (a != NODATA) & (b != NODATA)
    n = int(valid.sum())
    if n == 0:
        return {"n_pixels": 0}
    overall = float((a[valid] == b[valid]).mean())
    per_state = {}
    confusion = {}
    for s in ANALYSIS_STATES:
        a_s = valid & (a == s)
        b_s = valid & (b == s)
        inter = int((a_s & b_s).sum())
        union = int((a_s | b_s).sum())
        if union:
            per_state[STATE_NAMES[s]] = {
                "iou": round(inter / union, 4),
                "io_pixels": int(a_s.sum()),
                "wc_pixels": int(b_s.sum()),
            }
        row = {}
        if a_s.any():
            to_states, counts = np.unique(b[a_s], return_counts=True)
            for t, c in zip(to_states.tolist(), counts.tolist()):
                row[STATE_NAMES.get(int(t), str(t))] = int(c)
            confusion[STATE_NAMES[s]] = row
    return {
        "n_pixels": n,
        "overall_agreement": round(overall, 4),
        "per_state": per_state,
        "confusion_io_rows_wc_cols": confusion,
    }


def validate_region(
    region: RegionConfig, params: AnalysisParams = DEFAULT_PARAMS
) -> dict:
    """Run the full cross-product validation for one region and persist
    validation.json/md into its bundle."""
    stack = fetch_annual_stack(region)
    states = {y: remap_to_states(g) for y, g in stack.grids.items()}

    result: dict = {"region": region.name, "years": {}}

    for year in (2020, 2021):
        if year not in states:
            continue
        wc = fetch_worldcover_states(
            region.name, region.bbox, year, stack.crs, stack.transform, stack.shape
        )
        result["years"][str(year)] = _agreement(states[year], wc)
        log.info(
            "%s %d: overall agreement %.3f",
            region.name,
            year,
            result["years"][str(year)].get("overall_agreement", float("nan")),
        )

    # Confidence-vs-agreement on events completed by 2021.
    #
    # Raw "does WC agree with the new state" mostly measures *between-
    # product class semantics* (e.g. WC maps IO's sparse rangeland as bare
    # in deserts, and post-clearing pasture as grassland where IO says
    # crops — both confirmed on this benchmark). To measure the thing we
    # care about — are detected CHANGES credible — event-pixel agreement is
    # normalised by the same region's agreement on never-changed pixels of
    # the same state: the "relative agreement ratio". Ratio ≈ 1 means a
    # changed pixel is as credible as the product's static mapping of that
    # state; the score-quartile breakdown tests whether higher confidence
    # scores actually buy higher independent credibility.
    if 2021 in states:
        fields = extract_events(states, params)
        scores = score_events(fields, params)
        wc21 = fetch_worldcover_states(
            region.name, region.bbox, 2021, stack.crs, stack.transform, stack.shape
        )
        idx_2021 = region.years.index(2021)
        done = fields.event & (fields.year_index <= idx_2021) & (wc21 != NODATA)
        stable = (~fields.event) & (wc21 != NODATA)

        # Per-state baseline: agreement on stable pixels of that state.
        baseline: dict[int, float] = {}
        for s in ANALYSIS_STATES:
            m = stable & (states[2021] == s)
            if int(m.sum()) >= 100:
                baseline[s] = float((wc21[m] == s).mean())

        def _relative(mask: np.ndarray) -> dict | None:
            n = int(mask.sum())
            if n < 50:
                return None
            num = den = w = 0.0
            for s in ANALYSIS_STATES:
                ms = mask & (fields.to_state == s)
                ns = int(ms.sum())
                if ns == 0 or s not in baseline or baseline[s] < 0.05:
                    continue
                num += float((wc21[ms] == s).mean()) * ns
                den += baseline[s] * ns
                w += ns
            if den == 0:
                return None
            return {
                "n_events": n,
                "n_evaluated": int(w),
                "agreement": round(num / max(w, 1), 4),
                "baseline": round(den / max(w, 1), 4),
                "relative_ratio": round(num / den, 3),
            }

        overall = _relative(done)
        quartiles = {}
        if int(done.sum()) >= 200:
            qs = np.quantile(scores[done], [0.25, 0.5, 0.75])
            bins = [
                ("q1_lowest", done & (scores <= qs[0])),
                ("q2", done & (scores > qs[0]) & (scores <= qs[1])),
                ("q3", done & (scores > qs[1]) & (scores <= qs[2])),
                ("q4_highest", done & (scores > qs[2])),
            ]
            for name, mask in bins:
                row = _relative(mask)
                if row:
                    quartiles[name] = row

        result["confidence_vs_agreement"] = {
            "description": (
                "Events whose new state was in place by 2021, checked against "
                "WorldCover 2021. 'relative_ratio' normalises event-pixel "
                "agreement by the region's stable-pixel agreement for the same "
                "states, separating change credibility from between-product "
                "class semantics."
            ),
            "state_baselines": {
                STATE_NAMES[s]: round(v, 4) for s, v in baseline.items()
            },
            "all_events": overall,
            "score_quartiles": quartiles,
        }

    result["holdout_consistency"] = holdout_consistency(states, region, params)

    out_dir = bundle_dir(region.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    (out_dir / "validation.md").write_text(render_validation_md(result))
    return result


def holdout_consistency(
    states: dict[int, np.ndarray],
    region: RegionConfig,
    params: AnalysisParams,
    holdout_years: int = 2,
) -> dict | None:
    """Temporal holdout test of the confidence score, within the source
    product.

    Events and confidence are computed on a truncated series (the last
    `holdout_years` withheld); a detected change is *verified* if the
    claimed new state is still present in every held-out year. If the
    confidence score measures what it claims (evidence that a change is
    persistent rather than flicker), verification rates must rise with the
    score. This tests the score's ranking value, not real-world truth —
    misclassifications shared across all years of the product remain
    invisible to it (stated limitation).
    """
    years = sorted(states)
    if len(years) < params.persistence + 1 + holdout_years + 1:
        return None
    train_years = years[:-holdout_years]
    held = years[-holdout_years:]
    train = {y: states[y] for y in train_years}

    fields = extract_events(train, params)
    scores = score_events(fields, params)
    if int(fields.event.sum()) < 200:
        return {"n_events": int(fields.event.sum()), "note": "too few events"}

    verified = fields.event.copy()
    for y in held:
        verified &= states[y] == fields.to_state

    ev = fields.event
    out_rows = {}
    qs = np.quantile(scores[ev], [0.25, 0.5, 0.75])
    bins = [
        ("q1_lowest", ev & (scores <= qs[0])),
        ("q2", ev & (scores > qs[0]) & (scores <= qs[1])),
        ("q3", ev & (scores > qs[1]) & (scores <= qs[2])),
        ("q4_highest", ev & (scores > qs[2])),
    ]
    for name, mask in bins:
        n = int(mask.sum())
        if n:
            out_rows[name] = {
                "n_events": n,
                "verified_rate": round(float(verified[mask].sum()) / n, 4),
            }
    return {
        "description": (
            f"Events detected on {train_years[0]}–{train_years[-1]} only; "
            f"verified = new state persists through {held[0]}–{held[-1]}. "
            "Within-product test of the confidence score's ranking value."
        ),
        "train_years": train_years,
        "holdout_years": held,
        "n_events": int(ev.sum()),
        "overall_verified_rate": round(float(verified.sum()) / int(ev.sum()), 4),
        "score_quartiles": out_rows,
    }


def render_validation_md(v: dict) -> str:
    lines = [f"# Cross-product validation — {v['region']}", ""]
    lines.append(
        "IO Annual LULC vs ESA WorldCover, compared in canonical state space. "
        "Neither product is ground truth; agreement is evidence, "
        "disagreement is a humility marker."
    )
    lines.append("")
    for year, m in v.get("years", {}).items():
        if not m.get("n_pixels"):
            continue
        lines.append(f"## {year}")
        lines.append("")
        lines.append(f"- jointly observed pixels: {m['n_pixels']:,}")
        lines.append(f"- overall agreement: **{m['overall_agreement'] * 100:.1f}%**")
        lines.append("- per-state IoU:")
        for name, row in sorted(
            m["per_state"].items(), key=lambda kv: -kv[1]["iou"]
        ):
            lines.append(f"  - {name}: {row['iou']:.2f}")
        lines.append("")
    cva = v.get("confidence_vs_agreement")
    if cva:
        lines.append("## Confidence vs independent agreement")
        lines.append("")
        lines.append(cva["description"])
        lines.append("")
        if cva.get("all_events"):
            a = cva["all_events"]
            lines.append(
                f"- all completed events (n={a['n_events']:,}): agreement "
                f"{a['agreement'] * 100:.1f}% vs stable-pixel baseline "
                f"{a['baseline'] * 100:.1f}% → relative ratio **{a['relative_ratio']}**"
            )
        for name, row in cva.get("score_quartiles", {}).items():
            lines.append(
                f"- {name} (n={row['n_events']:,}): agreement "
                f"{row['agreement'] * 100:.1f}%, ratio {row['relative_ratio']}"
            )
        lines.append("")
    ho = v.get("holdout_consistency")
    if ho and ho.get("score_quartiles"):
        lines.append("## Temporal holdout: does confidence predict persistence?")
        lines.append("")
        lines.append(ho["description"])
        lines.append("")
        lines.append(
            f"- events on truncated series: {ho['n_events']:,}; overall verified "
            f"in holdout: {ho['overall_verified_rate'] * 100:.1f}%"
        )
        for name, row in ho["score_quartiles"].items():
            lines.append(
                f"- {name} (n={row['n_events']:,}): verified "
                f"{row['verified_rate'] * 100:.1f}%"
            )
        lines.append("")
    return "\n".join(lines)
