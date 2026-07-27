"""Grounded summary generation for CityChange v0.1.

Every sentence in the generated summary is instantiated from computed
numbers — there is no free-text generation and no LLM in v0.1. The
narrative-safety rule (docs/DECISIONS.md): the summary reports
*observations* (what the land-cover product shows) and clearly marked
*caveats*; it makes no causal claims.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from citychange.analysis import Hotspot
from citychange.config import RegionConfig
from citychange.landstate import STATE_LABELS, STATE_NAMES

_NAME_TO_LABEL = {STATE_NAMES[s]: label for s, label in STATE_LABELS.items()}


def _pp(x: float) -> str:
    """Format a fraction as signed percentage points."""
    return f"{x * 100:+.1f}"


def build_summary(
    region: RegionConfig,
    tile: str,
    shape: tuple[int, int],
    trends: dict[str, dict[int, float]],
    transitions: list[tuple[str, str, float]],
    raw_change_fraction: float,
    stable_change_fraction: float,
    hotspot: Hotspot,
    hotspot_lonlat: tuple[float, float],
    persistence: int,
) -> dict[str, Any]:
    """Assemble the machine-readable summary of one region analysis."""
    y0, y1 = region.years[0], region.years[-1]
    deltas = {
        name: series[y1] - series[y0]
        for name, series in trends.items()
        if y0 in series and y1 in series
    }
    return {
        "region": region.name,
        "display_name": region.display_name,
        "bbox": asdict(region.bbox),
        "utm_tile": tile,
        "grid_shape": list(shape),
        "years": list(region.years),
        "source": "Impact Observatory / Esri 10m Annual LULC v003 (CC BY 4.0)",
        "state_fractions_by_year": {
            name: {str(y): round(v, 4) for y, v in series.items()}
            for name, series in trends.items()
        },
        "fraction_deltas_first_to_last": {k: round(v, 4) for k, v in deltas.items()},
        "top_transitions_first_to_last": [
            {"from": f, "to": t, "fraction_of_area": round(v, 4)}
            for f, t, v in transitions
        ],
        "raw_change_fraction": round(raw_change_fraction, 4),
        "stable_change_fraction": round(stable_change_fraction, 4),
        "persistence_years_required": persistence,
        "hotspot": {
            "row0": hotspot.row0,
            "col0": hotspot.col0,
            "block_px": hotspot.block_px,
            "block_meters": hotspot.block_px * 10,
            "change_fraction": round(hotspot.change_fraction, 4),
            "center_lon": round(hotspot_lonlat[0], 6),
            "center_lat": round(hotspot_lonlat[1], 6),
        },
    }


def render_markdown(summary: dict[str, Any]) -> str:
    """Human-readable report from the machine-readable summary."""
    y0, y1 = summary["years"][0], summary["years"][-1]
    lines: list[str] = []
    lines.append(f"# CityChange v0.1 — {summary['display_name']}")
    lines.append("")
    b = summary["bbox"]
    lines.append(
        f"Area of interest: {b['west']:.3f}–{b['east']:.3f}°E, "
        f"{b['south']:.3f}–{b['north']:.3f}°N (UTM tile {summary['utm_tile']}, "
        f"{summary['grid_shape'][1]} × {summary['grid_shape'][0]} px at 10 m)."
    )
    lines.append(f"Observations: annual land cover, {y0}–{y1}.")
    lines.append(f"Source: {summary['source']}.")
    lines.append("")

    lines.append("## Observations")
    lines.append("")
    for name, delta in sorted(
        summary["fraction_deltas_first_to_last"].items(), key=lambda kv: -abs(kv[1])
    ):
        if abs(delta) < 0.001:
            continue
        series = summary["state_fractions_by_year"][name]
        v0, v1 = series[str(y0)] * 100, series[str(y1)] * 100
        label = _NAME_TO_LABEL.get(name, name)
        lines.append(
            f"- **{label}**: {v0:.1f}% of the area in {y0} → {v1:.1f}% in {y1} "
            f"({_pp(delta)} pp)."
        )
    lines.append("")
    lines.append(
        f"- {summary['raw_change_fraction'] * 100:.1f}% of observed pixels are "
        f"classified differently in {y1} than in {y0}."
    )
    lines.append(
        f"- {summary['stable_change_fraction'] * 100:.1f}% changed *and* held their "
        f"new state for the final {summary['persistence_years_required']} years "
        f"(the stable-change criterion)."
    )
    lines.append("")

    lines.append(f"## Largest transitions ({y0} → {y1})")
    lines.append("")
    for t in summary["top_transitions_first_to_last"]:
        lines.append(
            f"- {_NAME_TO_LABEL.get(t['from'], t['from'])} → "
            f"{_NAME_TO_LABEL.get(t['to'], t['to'])}: "
            f"{t['fraction_of_area'] * 100:.1f}% of the area"
        )
    lines.append("")

    h = summary["hotspot"]
    lines.append("## Strongest change hotspot")
    lines.append("")
    lines.append(
        f"A {h['block_meters']} m × {h['block_meters']} m block centred at "
        f"({h['center_lat']:.5f}°N, {h['center_lon']:.5f}°E) shows stable change "
        f"on {h['change_fraction'] * 100:.0f}% of its pixels — the densest "
        f"transformation in the area of interest."
    )
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- These are observations from an automated annual land-cover product, "
        "not verified ground truth; per-pixel classifications carry error."
    )
    lines.append(
        "- Annual cadence cannot resolve sub-year timing; \"changed by "
        f"{y1}\" means the change appears between two annual composites."
    )
    lines.append(
        "- No causal claims are made: the data shows *what* changed, not *why*."
    )
    lines.append(
        "- Changes occurring in the final year of the series may be excluded "
        "by the stable-change criterion."
    )
    lines.append("")
    return "\n".join(lines)


def write_reports(summary: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "summary.json"
    md_path = out_dir / "summary.md"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")
    md_path.write_text(render_markdown(summary))
    return json_path, md_path
