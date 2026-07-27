"""Geographic benchmark: run every region under configs/benchmark/ with the
identical global AnalysisParams and produce one comparative report.

The benchmark's purpose is falsification, not demo polish: regions were
chosen to cover contrasting transformation regimes (rapid urbanization,
dense stable urban, suburban expansion, deforestation frontier, water
dynamics, stable rural control) so that region-specific tuning has nowhere
to hide. A region that is stable on the ground must come out stable in the
numbers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from citychange.config import data_dir, load_region
from citychange.params import DEFAULT_PARAMS
from citychange.pipeline import run_analysis
from citychange.report import _label

log = logging.getLogger(__name__)


def run_benchmark(bench_dir: Path, force: bool = False) -> int:
    configs = sorted(bench_dir.glob("*.yaml"))
    if not configs:
        log.error("no region YAMLs in %s", bench_dir)
        return 1

    summaries = []
    failures = []
    for cfg in configs:
        region = load_region(cfg)
        log.info("=== benchmark region: %s ===", region.name)
        try:
            summaries.append(run_analysis(region, DEFAULT_PARAMS, force=force))
        except Exception:
            log.exception("region %s FAILED", region.name)
            failures.append(region.name)

    out = data_dir() / "outputs" / "benchmark_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render(summaries, failures))
    (data_dir() / "outputs" / "benchmark_report.json").write_text(
        json.dumps(
            {
                "regions": [s["region"] for s in summaries],
                "failures": failures,
                "rows": [_row(s) for s in summaries],
            },
            indent=2,
        )
    )
    log.info("benchmark report: %s", out)
    print(out.read_text())
    return 1 if failures else 0


def _row(s: dict) -> dict:
    af = s["archetype_fractions"]
    tiers = s["confidence"]["tier_counts"]
    total_ev = max(sum(tiers.values()), 1)
    deltas = s["fraction_deltas_first_to_last"]
    biggest_delta = max(deltas.items(), key=lambda kv: abs(kv[1])) if deltas else ("-", 0)
    return {
        "region": s["region"],
        "area_km2": s["area_km2"],
        "event_change_pct": round(s["change_fractions"]["event_based"] * 100, 2),
        "raw_change_pct": round(s["change_fractions"]["raw_two_date"] * 100, 2),
        "biggest_delta_state": biggest_delta[0],
        "biggest_delta_pp": round(biggest_delta[1] * 100, 1),
        "peak_period": s["peak_change_period"],
        "stable_pct": round(
            (af.get("stable", 0) + af.get("stable_with_flicker", 0)) * 100, 1
        ),
        "anomaly_pct": round(s["anomalies"]["fraction_of_area"] * 100, 3),
        "high_conf_pct_of_events": round(tiers.get("high", 0) * 100 / total_ev, 1),
        "mean_confidence": s["confidence"]["mean_event_score"],
    }


def _render(summaries: list[dict], failures: list[str]) -> str:
    lines = ["# CityChange geographic benchmark", ""]
    lines.append(
        "All regions analysed with identical global parameters "
        "(no per-region tuning). Change percentages are event-based "
        "(persistence-verified), raw = naive two-date difference."
    )
    lines.append("")
    lines.append(
        "| region | km² | event chg % | raw chg % | biggest Δ | peak | stable % | anomalies % | high-conf % | mean conf |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for s in summaries:
        r = _row(s)
        peak = f"{r['peak_period'][0]}–{r['peak_period'][1]}" if r["peak_period"] else "—"
        lines.append(
            f"| {r['region']} | {r['area_km2']} | {r['event_change_pct']} | "
            f"{r['raw_change_pct']} | {_label(r['biggest_delta_state'])} "
            f"{r['biggest_delta_pp']:+.1f} pp | {peak} | {r['stable_pct']} | "
            f"{r['anomaly_pct']} | {r['high_conf_pct_of_events']} | "
            f"{r['mean_confidence']} |"
        )
    if failures:
        lines.append("")
        lines.append(f"**FAILED regions:** {', '.join(failures)}")
    lines.append("")
    return "\n".join(lines)
