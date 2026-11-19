#!/usr/bin/env python3
import argparse
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description="Inspect DFT energy-window occupancy by k point")
parser.add_argument("eigenvalues", type=Path)
parser.add_argument("--outer", type=float, nargs=2, required=True, metavar=("LOW", "HIGH"))
parser.add_argument("--frozen", type=float, nargs=2, required=True, metavar=("LOW", "HIGH"))
parser.add_argument("--num-wann", type=int, required=True)
args = parser.parse_args()
outer_lo, outer_hi = args.outer
frozen_lo, frozen_hi = args.frozen
if not outer_lo <= frozen_lo <= frozen_hi <= outer_hi:
    parser.error("Frozen window must lie inside the outer window.")
rows = np.loadtxt(args.eigenvalues)
nbands, nk = rows[:, :2].max(axis=0).astype(int)
if rows.shape != (nbands * nk, 3):
    raise ValueError("Incomplete .eig file")
eigenvalues = np.empty((nk, nbands))
band = rows[:, 0].astype(int) - 1
kpoint = rows[:, 1].astype(int) - 1
if len(set(zip(kpoint, band))) != len(rows):
    raise ValueError("Repeated .eig index")
eigenvalues[kpoint, band] = rows[:, 2]
counts_outer = ((eigenvalues >= outer_lo) & (eigenvalues <= outer_hi)).sum(axis=1)
counts_frozen = ((eigenvalues >= frozen_lo) & (eigenvalues <= frozen_hi)).sum(axis=1)
print(f"{nk} k-points × {nbands} bands, {args.num_wann} Wannier spinors")
print(f"Outer {args.outer} eV: {counts_outer.min()}–{counts_outer.max()} states per k")
print(f"Frozen {args.frozen} eV: {counts_frozen.min()}–{counts_frozen.max()} states per k")
for index in range(max(0, int(eigenvalues.shape[1] / 2) - 25), min(nbands, 84)):
    energy = eigenvalues[:, index]
    print(f"Band {index + 1:>3}: {energy.min():>9.4f} {energy.max():>9.4f}")
if counts_outer.min() < args.num_wann or counts_frozen.max() > args.num_wann:
    raise SystemExit("Incompatible windows and subspace dimension")
