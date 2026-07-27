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

from citychange.analysis import Hotspot
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


def plot_change_map(
    final_grid: np.ndarray,
    change_mask: np.ndarray,
    hotspot: Hotspot,
    title: str,
    out_path: Path,
) -> Path:
    """Grey basemap of the final year, changed pixels colored by the state
    they became, hotspot block outlined."""
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(final_grid != NODATA, cmap="gray", vmin=-3, vmax=1, interpolation="nearest")

    changed = np.where(change_mask, final_grid, NODATA)
    masked = np.ma.masked_where(changed == NODATA, changed)
    ax.imshow(masked, cmap=_STATE_CMAP, norm=_STATE_NORM, interpolation="nearest")

    ax.add_patch(
        Rectangle(
            (hotspot.col0 - 0.5, hotspot.row0 - 0.5),
            hotspot.block_px,
            hotspot.block_px,
            fill=False,
            edgecolor="black",
            linewidth=2.5,
            linestyle="--",
            label="Strongest change hotspot",
        )
    )
    present = _present_states([np.asarray(changed)])
    handles = _state_legend(present)
    handles.append(
        Patch(facecolor="none", edgecolor="black", linestyle="--", label="Hotspot")
    )
    ax.legend(handles=handles, loc="lower right", fontsize=9)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
