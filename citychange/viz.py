"""Static visual outputs for CityChange v0.1.

Interactive maps come later (Phase 9). v0.1 produces three reproducible
PNG figures per region:

1. yearly_states.png — the canonical state map for every year in the series
2. trends.png       — built/vegetation/crops/water/bare fractions over time
3. change_map.png   — stable-change pixels colored by their final state,
                      with the strongest change hotspot outlined
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch, Rectangle

from citychange.landstate import (
    ANALYSIS_STATES,
    NODATA,
    STATE_COLORS,
    STATE_LABELS,
    STATE_NAMES,
)

_STATE_CMAP = ListedColormap(
    [STATE_COLORS[s] for s in sorted(STATE_COLORS)], name="citychange_states"
)
_STATE_NORM = plt.Normalize(vmin=-0.5, vmax=len(STATE_COLORS) - 0.5)


def _state_legend(states: list[int]) -> list[Patch]:
    return [Patch(facecolor=STATE_COLORS[s], label=STATE_LABELS[s]) for s in states]


def _present_states(grids: list[np.ndarray]) -> list[int]:
    present: set[int] = set()
    for g in grids:
        present.update(np.unique(g).tolist())
    present.discard(NODATA)
    return [s for s in ANALYSIS_STATES if s in present]


def plot_yearly_states(
    stack: dict[int, np.ndarray], title: str, out_path: Path
) -> Path:
    years = sorted(stack)
    ncols = min(4, len(years))
    nrows = -(-len(years) // ncols)
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(4 * ncols, 4.2 * nrows), squeeze=False
    )
    for ax in axes.flat:
        ax.axis("off")
    for ax, year in zip(axes.flat, years):
        ax.imshow(stack[year], cmap=_STATE_CMAP, norm=_STATE_NORM, interpolation="nearest")
        ax.set_title(str(year), fontsize=12)
        ax.axis("off")
    fig.legend(
        handles=_state_legend(_present_states(list(stack.values()))),
        loc="lower center",
        ncol=6,
        frameon=False,
    )
    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_trends(
    trends: dict[str, dict[int, float]], title: str, out_path: Path
) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    name_to_state = {v: k for k, v in STATE_NAMES.items()}
    for name, series in trends.items():
        if not series or all(v == 0 for v in series.values()):
            continue
        years = sorted(series)
        ax.plot(
            years,
            [series[y] * 100 for y in years],
            marker="o",
            label=STATE_LABELS[name_to_state[name]],
            color=STATE_COLORS[name_to_state[name]],
            linewidth=2,
        )
    ax.set_xlabel("Year")
    ax.set_ylabel("Share of observed area (%)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_change_events(
    final_grid: np.ndarray,
    event_mask: np.ndarray,
    to_state: np.ndarray,
    hotspots: list[dict],
    stack,
    title: str,
    out_path: Path,
) -> Path:
    """Grey basemap of the final year, event pixels colored by the state
    they became, top hotspot blocks outlined and numbered."""
    from pyproj import Transformer

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(final_grid != NODATA, cmap="gray", vmin=-3, vmax=1, interpolation="nearest")

    changed = np.where(event_mask, to_state, NODATA)
    masked = np.ma.masked_where(changed == NODATA, changed)
    ax.imshow(masked, cmap=_STATE_CMAP, norm=_STATE_NORM, interpolation="nearest")

    if hotspots:
        to_utm = Transformer.from_crs("EPSG:4326", stack.crs, always_xy=True)
        inv = ~stack.transform
        for h in hotspots:
            x, y = to_utm.transform(h["lon"], h["lat"])
            col, row = inv * (x, y)
            half = h["block_m"] / 10 / 2
            ax.add_patch(
                Rectangle(
                    (col - half, row - half),
                    2 * half,
                    2 * half,
                    fill=False,
                    edgecolor="black",
                    linewidth=2,
                    linestyle="--",
                )
            )
            ax.annotate(
                str(h["rank"]),
                (col + half, row - half),
                fontsize=11,
                fontweight="bold",
                color="black",
            )
    present = _present_states([np.asarray(changed)])
    handles = _state_legend(present)
    handles.append(
        Patch(facecolor="none", edgecolor="black", linestyle="--", label="Hotspots")
    )
    ax.legend(handles=handles, loc="lower right", fontsize=9)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_year_of_change(
    yoc: np.ndarray, years: tuple[int, ...], title: str, out_path: Path
) -> Path:
    """When each changed pixel adopted its new state, on a grey base."""
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(yoc >= 0, cmap="gray", vmin=-3, vmax=1, interpolation="nearest")
    masked = np.ma.masked_where(yoc == 0, yoc)
    im = ax.imshow(
        masked,
        cmap="viridis",
        vmin=years[0],
        vmax=years[-1],
        interpolation="nearest",
    )
    cbar = fig.colorbar(im, ax=ax, shrink=0.7, ticks=list(years))
    cbar.set_label("first year the new state appears (±1 year)")
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_volumes(
    volumes: dict[int, dict[tuple[int, int], int]],
    years: tuple[int, ...],
    title: str,
    out_path: Path,
) -> Path:
    """Stacked bars of change volume per event year, split by destination state."""
    fig, ax = plt.subplots(figsize=(8, 5))
    xs = list(years[1:])  # events can only be dated from the 2nd year on
    bottoms = {y: 0.0 for y in xs}
    for state in ANALYSIS_STATES:
        vals = []
        for y in xs:
            px = sum(c for (f, t), c in volumes.get(y, {}).items() if t == state)
            vals.append(px * 100 / 1e6)  # km²
        if not any(vals):
            continue
        ax.bar(
            xs,
            vals,
            bottom=[bottoms[y] for y in xs],
            color=STATE_COLORS[state],
            label=f"→ {STATE_LABELS[state]}",
        )
        for y, v in zip(xs, vals):
            bottoms[y] += v
    ax.set_xlabel("Year the new state first appears")
    ax.set_ylabel("Changed area (km²)")
    ax.set_title(title)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=9)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


_ARCHETYPE_COLORS = {
    1: "#e8e6df",  # stable
    2: "#c9c6ba",  # stable_with_flicker
    3: "#d95f02",  # direct_change
    4: "#7570b3",  # staged_change
    5: "#1b9e77",  # reverted
    6: "#66a61e",  # fluctuating
    7: "#a6761d",  # unstable
    8: "#e7298a",  # noisy_change
}


def plot_archetypes(archetypes: np.ndarray, title: str, out_path: Path) -> Path:
    from citychange.trajectory import ARCHETYPE_NAMES

    cmap = ListedColormap(["#ffffff"] + [_ARCHETYPE_COLORS[i] for i in range(1, 9)])
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(archetypes, cmap=cmap, vmin=-0.5, vmax=8.5, interpolation="nearest")
    handles = [
        Patch(facecolor=_ARCHETYPE_COLORS[i], label=ARCHETYPE_NAMES[i].replace("_", " "))
        for i in range(1, 9)
        if (archetypes == i).any()
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_anomalies(
    final_grid: np.ndarray, anomaly_mask: np.ndarray, title: str, out_path: Path
) -> Path:
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(final_grid != NODATA, cmap="gray", vmin=-3, vmax=1, interpolation="nearest")
    masked = np.ma.masked_where(~anomaly_mask, anomaly_mask.astype(np.uint8))
    ax.imshow(masked, cmap=ListedColormap(["#8b2fc9"]), interpolation="nearest")
    ax.legend(handles=[Patch(facecolor="#8b2fc9", label="Statistically rare trajectory")], loc="lower right", fontsize=9)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
