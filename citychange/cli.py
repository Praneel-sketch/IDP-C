"""CityChange command-line interface.

Usage:
    python -m citychange run configs/devanahalli.yaml
    citychange run configs/devanahalli.yaml          (after `pip install -e .`)

Pipeline stages: acquire (cached) -> remap to canonical states -> temporal
analysis -> figures + summary reports under data/outputs/<region>/.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from citychange import __version__
from citychange.analysis import (
    find_hotspot,
    fraction_trends,
    stable_change_mask,
    top_transitions,
    transition_matrix,
)
from citychange.config import data_dir, load_region
from citychange.datasets.io_annual_lulc import fetch_annual_stack
from citychange.landstate import NODATA, remap_to_states
from citychange.report import build_summary, render_markdown, write_reports
from citychange.viz import plot_change_map, plot_trends, plot_yearly_states

log = logging.getLogger("citychange")

STABLE_CHANGE_PERSISTENCE = 2  # final state must hold for the last N years


def run(config_path: Path) -> Path:
    region = load_region(config_path)
    out_dir = data_dir() / "outputs" / region.name
    log.info("region '%s' (%s), years %s", region.name, region.display_name, region.years)

    # 1. Acquire (windowed remote reads, cached locally).
    stack = fetch_annual_stack(region)
    log.info("grid %s px, tile %s", stack.shape, stack.tile)

    # 2. Canonical land states.
    states = {y: remap_to_states(g) for y, g in stack.grids.items()}
    nodata_frac = {
        y: float((g == NODATA).mean()) for y, g in states.items()
    }
    for y, f in nodata_frac.items():
        if f > 0.05:
            log.warning("year %d has %.1f%% unobserved pixels", y, f * 100)

    # 3. Temporal analysis.
    y0, y1 = region.years[0], region.years[-1]
    trends = fraction_trends(states)
    matrix = transition_matrix(states[y0], states[y1])
    transitions = top_transitions(matrix, k=5)
    raw_change = sum(v for (f, t), v in matrix.items() if f != t)

    change_mask = stable_change_mask(states, persistence=STABLE_CHANGE_PERSISTENCE)
    observed = (states[y0] != NODATA) & (states[y1] != NODATA)
    stable_change = float(change_mask.sum()) / max(int(observed.sum()), 1)
    hotspot = find_hotspot(change_mask, region.hotspot_block_px)
    hotspot_lonlat = stack.pixel_center_lonlat(
        hotspot.row0 + hotspot.block_px / 2, hotspot.col0 + hotspot.block_px / 2
    )

    # 4. Figures.
    plot_yearly_states(
        states,
        f"{region.display_name} — annual land states",
        out_dir / "yearly_states.png",
    )
    plot_trends(
        trends,
        f"{region.display_name} — land-state trends {y0}–{y1}",
        out_dir / "trends.png",
    )
    plot_change_map(
        states[y1],
        change_mask,
        hotspot,
        f"{region.display_name} — stable change {y0}–{y1} (colored by final state)",
        out_dir / "change_map.png",
    )

    # 5. Grounded reports.
    summary = build_summary(
        region=region,
        tile=stack.tile,
        shape=stack.shape,
        trends=trends,
        transitions=transitions,
        raw_change_fraction=raw_change,
        stable_change_fraction=stable_change,
        hotspot=hotspot,
        hotspot_lonlat=hotspot_lonlat,
        persistence=STABLE_CHANGE_PERSISTENCE,
    )
    write_reports(summary, out_dir)
    log.info("outputs written to %s", out_dir)
    print(render_markdown(summary))
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citychange", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="run the v0.1 analysis pipeline for a region")
    p_run.add_argument("config", type=Path, help="region YAML, e.g. configs/devanahalli.yaml")
    p_run.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.command == "run":
        run(args.config)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
