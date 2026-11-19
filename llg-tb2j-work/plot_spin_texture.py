"""Render a nanoribbon spin state on its triangular lattice."""
import argparse
import math
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator


INK = "#18252e"
EDGE = "#a7b3ba"
VERTICAL_COLORS = mpl.colormaps["RdBu_r"]
VERTICAL_NORM = mpl.colors.Normalize(-1, 1)


def read_shape(source):
    """Find the Nx and Ny written by the simulator beside the state."""
    for directory in source.resolve().parents:
        settings = directory / "run_settings.ini"
        if settings.is_file():
            values = {}
            for line in settings.read_text(encoding="utf-8-sig").splitlines():
                key, _, value = line.partition("#")[0].partition("=")
                if key.strip() in {"Nx", "Ny"}:
                    values[key.strip()] = int(value.strip())
            if {"Nx", "Ny"} <= values.keys():
                return values["Nx"], values["Ny"]
    raise ValueError("Pass --nx and --ny or keep run_settings.ini beside the state.")


def load_state(source, nx, ny):
    data = np.load(source, allow_pickle=False) if source.suffix.lower() == ".npy" else np.loadtxt(source)
    if data.shape not in {(nx, ny, 3), (nx * ny, 3)}:
        raise ValueError("Expected three spin components at each of the Nx × Ny sites.")
    if not np.isrealobj(data) or not np.all(np.isfinite(data)):
        raise ValueError("Spin components must be real and finite.")
    spins = data.reshape(nx, ny, 3)
    if not np.allclose(np.linalg.norm(spins, axis=-1), 1.0, atol=1e-5, rtol=0):
        raise ValueError("Expected unit spins in the simulator output.")
    return spins


def add_spin_tiles(axis, xy, color):
    # The Voronoi cells of the group code's staggered triangular grid.
    vertices = np.deg2rad(30 + 60 * np.arange(6))
    cell = np.column_stack((np.cos(vertices), np.sin(vertices))) / math.sqrt(3)
    polygons = xy[:, None, :] + cell[None, :, :]
    axis.add_collection(
        PolyCollection(polygons, facecolors=color, edgecolors="face", linewidths=0.18)
    )


def make_figure(spins, title, subtitle):
    nx, ny, _ = spins.shape
    i, j = np.indices((nx, ny))
    x = i + 0.5 * (j % 2)
    y = j * math.sqrt(3) / 2
    xy = np.column_stack((x.ravel(), y.ravel()))
    sx, sy, sz = spins.reshape(-1, 3).T

    ratio = (y.max() + 1.2) / (x.max() + 1.2)
    height = min(10, max(3.1, 1.18 + 6.0 * ratio))
    fig = Figure(figsize=(7.25, height), facecolor="white")
    FigureCanvasAgg(fig)
    fig.text(0.11, 0.966, title, color=INK, fontsize=18, fontweight="bold", va="top")
    fig.text(0.11, 0.910, subtitle, color="#4e616d", fontsize=9, va="top")
    axis = fig.add_axes([0.11, 0.105, 0.72, 0.75])
    add_spin_tiles(axis, xy, VERTICAL_COLORS(VERTICAL_NORM(sz)))
    axis.set(
        xlim=(xy[:, 0].min() - 0.55, xy[:, 0].max() + 0.55),
        ylim=(xy[:, 1].min() - 0.62, xy[:, 1].max() + 0.62),
        xlabel=r"$x/a$", ylabel=r"$y/a$", aspect="equal",
    )
    axis.xaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
    axis.tick_params(length=3, width=0.55, color=EDGE, labelsize=9)
    for spine in axis.spines.values():
        spine.set_color(EDGE)
        spine.set_linewidth(0.6)

    stride = max(1, math.ceil(max(nx, ny) / 48))
    show = (i.ravel() % stride == 0) & (j.ravel() % stride == 0) & (np.hypot(sx, sy) > 0)
    if np.any(show):
        arrows = axis.quiver(
            xy[show, 0], xy[show, 1], sx[show], sy[show],
            angles="xy", scale_units="xy", scale=1 / (0.73 * stride),
            pivot="mid", units="inches", width=0.010, headwidth=3.6, headlength=4.0,
            headaxislength=3.6, minlength=0, minshaft=0.8,
            color="#142128", edgecolor="white", linewidth=0.38,
        )
        axis.quiverkey(arrows, 0.98, 1.035, 1.0, r"$|S_\parallel|=1$", labelpos="W",
                       color=INK, fontproperties={"size": 8})
    if stride > 1:
        fig.text(0.11, 0.02, f"Arrows sampled every {stride} sites.", color="#4e616d", fontsize=8)

    bar = fig.colorbar(mpl.cm.ScalarMappable(norm=VERTICAL_NORM, cmap=VERTICAL_COLORS),
                      cax=fig.add_axes([0.865, 0.26, 0.022, 0.47]),
                      ticks=[-1, -0.5, 0, 0.5, 1])
    bar.outline.set_edgecolor(EDGE)
    bar.outline.set_linewidth(0.6)
    bar.ax.tick_params(labelsize=9, length=3, width=0.55)
    bar.set_label(r"$S_z$", fontsize=12)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="Simulator final_state.txt or .npy snapshot")
    parser.add_argument("--nx", type=int)
    parser.add_argument("--ny", type=int)
    parser.add_argument("--output", type=Path, required=True, help="Output prefix for PNG and PDF")
    parser.add_argument("--title", default=r"MnInP$_2$Te$_6$ spin configuration")
    parser.add_argument("--subtitle", default="TB2J-driven LLG snapshot")
    args = parser.parse_args()
    if (args.nx is None) != (args.ny is None):
        parser.error("--nx and --ny must be supplied together.")
    try:
        nx, ny = read_shape(args.state) if args.nx is None else (args.nx, args.ny)
        if nx < 3 or ny < 3:
            raise ValueError("Nx and Ny must be at least 3.")
        spins = load_state(args.state, nx, ny)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with mpl.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                         "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                         "pdf.fonttype": 42, "figure.constrained_layout.h_pad": 0.05}):
        subtitle = f"{nx} × {ny} Mn sites  |  {args.subtitle}"
        figure = make_figure(spins, args.title, subtitle)
        figure.savefig(str(args.output) + ".png", dpi=300, facecolor="white")
        figure.savefig(str(args.output) + ".pdf", facecolor="white")


if __name__ == "__main__":
    main()


