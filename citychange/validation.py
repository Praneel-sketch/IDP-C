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
    if 2021 in states:
        fields = extract_events(states, params)
        scores = score_events(fields, params)
        tiers = tier_events(scores, fields, params)
        wc21 = fetch_worldcover_states(
            region.name, region.bbox, 2021, stack.crs, stack.transform, stack.shape
        )
        idx_2021 = region.years.index(2021)
        done = fields.event & (fields.year_index <= idx_2021) & (wc21 != NODATA)
        tier_rows = {}
        for tier, name in ((1, "low"), (2, "medium"), (3, "high")):
            m = done & (tiers == tier)
            n = int(m.sum())
            if n:
                agree = float((wc21[m] == fields.to_state[m]).mean())
                tier_rows[name] = {"n_events": n, "wc2021_agrees_with_new_state": round(agree, 4)}
        result["confidence_vs_agreement"] = {
            "description": (
                "Events whose new state was in place by 2021, checked against "
                "WorldCover 2021 independently showing that state."
            ),
            "tiers": tier_rows,
        }

    out_dir = bundle_dir(region.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    (out_dir / "validation.md").write_text(render_validation_md(result))
    return result


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
    if cva and cva["tiers"]:
        lines.append("## Confidence vs independent agreement")
        lines.append("")
        lines.append(cva["description"])
        lines.append("")
        for name in ("high", "medium", "low"):
            row = cva["tiers"].get(name)
            if row:
                lines.append(
                    f"- {name}-confidence events: {row['n_events']:,} — WorldCover "
                    f"agrees on {row['wc2021_agrees_with_new_state'] * 100:.1f}%"
                )
        lines.append("")
    return "\n".join(lines)
