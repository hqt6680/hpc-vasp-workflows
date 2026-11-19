"""沿用原 spin_simulation.py 的六角晶格彩色箭头图；兼容 Python 3.7。"""
import argparse
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


def load_spins(source, length, width):
    data = (np.load(str(source), allow_pickle=False) if Path(source).suffix.lower() == ".npy"
            else np.loadtxt(str(source)))
    if data.shape not in ((length, width, 3), (length * width, 3)):
        raise ValueError("Spin data shape does not match Nx, Ny")
    spins = data.reshape(length, width, 3)
    if not np.all(np.isfinite(spins)):
        raise ValueError("Spin data contains NaN/Inf")
    norms = np.linalg.norm(spins, axis=-1)
    if not np.all(np.isfinite(norms)) or np.any(norms < 1e-30):
        raise ValueError("Spin data contains a zero or invalid spin vector")
    return spins


def build_figure(spins, temperature, field, electric, engine="llg"):
    """方形时与原 Python 图逐像素一致；矩形只调整画布高度和坐标范围。"""
    length, width = spins.shape[:2]
    height = 10.0 * np.sqrt(3.0) / 2.0 if length == width else max(3.0, 10.0 * np.sqrt(3.0) / 2.0 * width / length)
    figure = Figure(figsize=(10.0, height))
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    i, j = np.indices((length, width))
    x, y = i + 0.5 * (j & 1), j * np.sqrt(3.0) / 2.0
    quiver = ax.quiver(x, y, spins[..., 0], spins[..., 1], spins[..., 2],
                       cmap="bwr", pivot="mid", width=0.004, headwidth=4,
                       headlength=5, headaxislength=4, scale=30, clim=(-1, 1))
    figure.colorbar(quiver, ax=ax, label="$S_z$", shrink=0.8)
    ax.set_aspect("equal")
    ax.set_xlim(-0.5, length + 0.5)
    ax.set_ylim(-0.5, (width - 0.5) * np.sqrt(3.0) / 2.0 + 0.5)
    ax.set_title("Hexagonal lattice ({})\nT = {:.2f} K, B = {:.2f} T, Ez = {:.2f}".format(
        engine.upper(), temperature, field, electric))
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    return figure


def render(source, target, length, width, temperature, field, electric, engine="llg",
           boundary_x="open", boundary_y="open", dpi=150):
    if length < 3 or width < 3 or dpi <= 0:
        raise ValueError("Nx/Ny must be >=3 and dpi must be positive")
    if not np.all(np.isfinite([temperature, field, electric])):
        raise ValueError("T, B and Ez must be finite")
    spins = load_spins(source, length, width)
    figure = build_figure(spins, temperature, field, electric, engine)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=str(target.parent), suffix=".png", delete=False) as handle:
            temporary = Path(handle.name)
        figure.savefig(str(temporary), dpi=dpi, bbox_inches="tight")
        os.replace(str(temporary), str(target))
    finally:
        figure.clear()
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--temperature", type=float, required=True)
    parser.add_argument("--field", type=float, required=True)
    parser.add_argument("--electric", type=float, default=0)
    parser.add_argument("--engine", default="llg")
    parser.add_argument("--boundary-x", default="open")
    parser.add_argument("--boundary-y", default="open")
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()
    render(args.state, args.output, args.length, args.width,
           args.temperature, args.field, args.electric, args.engine, args.boundary_x, args.boundary_y, args.dpi)


if __name__ == "__main__":
    main()
