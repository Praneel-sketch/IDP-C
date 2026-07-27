"""CityChange command-line interface.

Usage:
    citychange run configs/devanahalli.yaml
    citychange run --bbox 77.63 13.17 77.73 13.27 --name my_area
    citychange benchmark                 # all regions in configs/benchmark/
    citychange serve                     # web app (see server.py)

All analysis logic lives in pipeline.run_analysis(); this module only
parses arguments.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from citychange import __version__
from citychange.config import REPO_ROOT, BBox, RegionConfig, load_region
from citychange.datasets.io_annual_lulc import AVAILABLE_YEARS
from citychange.params import DEFAULT_PARAMS
from citychange.pipeline import run_analysis
from citychange.report import render_markdown

log = logging.getLogger("citychange")


def _region_from_args(args: argparse.Namespace) -> RegionConfig:
    if args.config:
        return load_region(args.config)
    if not args.bbox:
        raise SystemExit("provide either a config file or --bbox W S E N")
    west, south, east, north = args.bbox
    name = args.name or f"bbox_{west:.3f}_{south:.3f}_{east:.3f}_{north:.3f}".replace(
        "-", "m"
    ).replace(".", "p")
    years = tuple(args.years) if args.years else AVAILABLE_YEARS
    return RegionConfig(
        name=name,
        display_name=args.display_name or name,
        bbox=BBox(west=west, south=south, east=east, north=north),
        years=years,
    )


def cmd_run(args: argparse.Namespace) -> int:
    region = _region_from_args(args)
    summary = run_analysis(region, DEFAULT_PARAMS, force=args.force)
    print(render_markdown(summary))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from citychange.benchmark import run_benchmark

    bench_dir = Path(args.dir) if args.dir else REPO_ROOT / "configs" / "benchmark"
    return run_benchmark(bench_dir, force=args.force)


def cmd_validate(args: argparse.Namespace) -> int:
    from citychange.pipeline import bundle_dir
    from citychange.validation import validate_region

    region = load_region(args.config)
    validate_region(region)
    print((bundle_dir(region.name) / "validation.md").read_text())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "citychange.server:app", host=args.host, port=args.port, log_level="info"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citychange", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="analyse one region")
    p_run.add_argument("config", nargs="?", type=Path, help="region YAML")
    p_run.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    p_run.add_argument("--name", help="region name for the output bundle")
    p_run.add_argument("--display-name")
    p_run.add_argument("--years", nargs="+", type=int)
    p_run.add_argument("--force", action="store_true", help="recompute even if current")
    p_run.add_argument("-v", "--verbose", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_bench = sub.add_parser("benchmark", help="run the geographic benchmark suite")
    p_bench.add_argument("--dir", help="directory of region YAMLs")
    p_bench.add_argument("--force", action="store_true")
    p_bench.add_argument("-v", "--verbose", action="store_true")
    p_bench.set_defaults(func=cmd_benchmark)

    p_serve = sub.add_parser("serve", help="serve the web app")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("-v", "--verbose", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_val = sub.add_parser(
        "validate", help="cross-product + holdout validation for a region"
    )
    p_val.add_argument("config", type=Path, help="region YAML")
    p_val.add_argument("-v", "--verbose", action="store_true")
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # rasterio logs a harmless "boto3 not available" INFO line on every
    # anonymous S3 read; keep demo/CI output clean.
    logging.getLogger("rasterio.session").setLevel(logging.WARNING)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
