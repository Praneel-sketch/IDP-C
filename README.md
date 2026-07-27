# CityChange

**AI-powered urban evolution intelligence from open Earth-observation data.**

Google Maps shows what a place looks like. CityChange tells the story of how
it became what it is — think *git history for physical places*. Given a
geographic area, CityChange reconstructs how land states (built-up,
vegetation, crops, water, bare land) evolved over the years, detects when and
where meaningful transformations happened, and reports them in plain,
defensible language with explicit uncertainty.

Current status: **v0.1 proof of concept — working.**

## What v0.1 does

For a bounding box defined in a YAML config, CityChange:

1. fetches annual 10 m land-cover observations (2017–2023) via windowed
   HTTP reads of public cloud-optimized GeoTIFFs — a few MB per region-year,
   no credentials, cached locally for offline re-runs;
2. remaps them to a canonical land-state vocabulary;
3. computes per-year land-state fractions, first-to-last transition
   matrices, and a *stable change* mask (a change only counts if the new
   state persists over multiple years — single-year classification flicker
   is rejected);
4. locates the densest change hotspot;
5. renders yearly state maps, trend charts and a change map, plus a
   grounded Markdown/JSON summary in which every sentence is instantiated
   from computed numbers — no free-text generation, no causal claims.

Pilot region: the Devanahalli / Kempegowda airport corridor in North
Bengaluru, where v0.1 measures built-up area growing from 22.7% to 42.1% of
the area between 2017 and 2023, mostly at the expense of cropland — and also
surfaces several lakes refilling in 2021–22.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run the unit tests (no network needed)
pytest

# run the pipeline for the pilot region (first run downloads ~400 kB)
citychange run configs/devanahalli.yaml
```

Outputs land in `data/outputs/<region>/`:

| file | contents |
|---|---|
| `yearly_states.png` | canonical land-state map for every year |
| `trends.png` | built/vegetation/crops/water/bare fractions over time |
| `change_map.png` | stable-change pixels colored by final state + hotspot |
| `summary.md` / `summary.json` | grounded human/machine-readable report |

To analyse a different area, copy `configs/devanahalli.yaml`, change the
bbox/name, and run it. v0.1 supports regions inside a single UTM tile
(~6° × 8°); keep boxes small (≲ 20 km) — that is the intended scale anyway.

## Repository layout

```
citychange/            pipeline library + CLI (production code)
  config.py            YAML region configs, data directories
  tiles.py             UTM zone/latitude-band tile arithmetic
  landstate.py         source-class → canonical land-state schema
  datasets/            data acquisition (one module per source)
  analysis.py          temporal analysis (pure NumPy, fully unit-tested)
  viz.py               static figures
  report.py            grounded summary generation
configs/               region definitions (reproducible runs)
tests/                 unit tests — synthetic arrays, no network
docs/                  architecture, decision log, data-source verification
data/                  gitignored: download cache + generated outputs
experiments/           research experiments (kept separate from production)
notebooks/             exploration only — never load-bearing
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design and v0.1 scope
- [docs/DECISIONS.md](docs/DECISIONS.md) — running decision log
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — verified data sources, licenses, limitations
- [docs/ROADMAP.md](docs/ROADMAP.md) — phase plan and what v0.1 proves / does not prove

## License and data attribution

Code: MIT. Land-cover data: Impact Observatory / Esri 10 m Annual Land Use
Land Cover (CC BY 4.0), derived from ESA Sentinel-2 imagery. See
docs/DATA_SOURCES.md for full attribution requirements.
