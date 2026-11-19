#!/usr/bin/env python3
"""Prepare weighted Wannier90 HR data for the HamiltonIO 0.3.8 reader."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from check_wannier_bands import diagonalize, read_hr, read_vasp, read_win


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hr(destination, translations, hamiltonian, scheme):
    nw = hamiltonian.shape[1]
    nr = len(translations)
    with destination.open("x", encoding="ascii", newline="\n") as output:
        output.write("Wannier90 HR converted for HamiltonIO 0.3.8 (%s weights applied)\n" % scheme)
        output.write("%12d\n%12d\n" % (nw, nr))
        for start in range(0, nr, 15):
            output.write("    1" * min(15, nr - start) + "\n")
        for (r1, r2, r3), matrix in zip(translations, hamiltonian):
            records = (
                "%5d%5d%5d%5d%5d % .16e % .16e\n" %
                (r1, r2, r3, i + 1, j + 1, matrix[i, j].real, matrix[i, j].imag)
                for j in range(nw) for i in range(nw)
            )
            output.writelines(records)


def verify_reader(seed, structure, groupby, points, translations, hamiltonian):
    from ase.io import read
    from HamiltonIO.wannier import WannierHam

    atoms = read(structure)
    model = WannierHam.read_from_wannier_dir(
        path=str(seed.parent), prefix=seed.name, atoms=atoms, nls=True, groupby=groupby
    )
    expected, source_error = diagonalize(points, translations, hamiltonian)
    actual_h = np.stack([model.gen_ham(k) for k in points])
    actual_error = np.max(np.abs(actual_h - actual_h.transpose(0, 2, 1).conj()))
    actual = np.linalg.eigvalsh(actual_h)
    eigenvalue_error = np.max(np.abs(expected - actual))
    return {
        "verified_kpoints": len(points),
        "original_hermiticity_max_ev": float(source_error),
        "hamiltonio_hermiticity_max_ev": float(actual_error),
        "hamiltonio_eigenvalue_error_max_ev": float(eigenvalue_error),
        "verified": bool(max(source_error, actual_error) <= 1e-4 and eigenvalue_error <= 1e-7),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True, help="Source Wannier90 file prefix")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--structure", type=Path, help="POSCAR; defaults to source POSCAR")
    parser.add_argument("--scheme", choices=("global", "pair"), required=True)
    parser.add_argument("--groupby", choices=("orbital", "spin"), required=True)
    parser.add_argument("--vasprun", type=Path, help="Optional independent path for more k points")
    args = parser.parse_args()

    seed = args.seed.resolve()
    structure = (args.structure or seed.parent / "POSCAR").resolve()
    output = args.output.resolve()
    out_seed = output / seed.name
    source_hr = Path(str(seed) + "_hr.dat")
    source_ws = Path(str(seed) + "_wsvec.dat")
    source_win = Path(str(seed) + ".win")
    source_centres = Path(str(seed) + "_centres.xyz")
    _, training_points, cell = read_win(seed)
    if not structure.is_file() or not source_centres.is_file():
        raise ValueError("The structure and Wannier centres files are required")

    use_ws = args.scheme == "pair"
    translations, hamiltonian = read_hr(seed, use_ws)
    # Include generic off-grid points; integer rephasing can cancel at training k only.
    grid_points = training_points[::max(1, len(training_points) // 12)][:12]
    generic = np.random.default_rng(1407).uniform(-0.5, 0.5, size=(12, 3))
    if np.allclose(training_points[:, 2], 0.0):
        generic[:, 2] = 0.0
    points = np.concatenate((grid_points, generic))
    if args.vasprun:
        path_points, _, path_cell, _ = read_vasp(args.vasprun, 1)
        if not np.allclose(path_cell, cell, atol=1e-6, rtol=1e-7):
            raise ValueError("Band reference and Wannier cells differ")
        points = np.concatenate((points, path_points))
    points = np.unique(points, axis=0)

    source_paths = [source_hr, source_win, source_centres, structure]
    if use_ws:
        source_paths.append(source_ws)
    source_digests = {str(path): sha256(path) for path in source_paths}
    output.mkdir()
    for source, destination in (
        (source_win, Path(str(out_seed) + ".win")),
        (source_centres, Path(str(out_seed) + "_centres.xyz")),
        (structure, output / "POSCAR"),
    ):
        destination.symlink_to(source)

    dest_hr = Path(str(out_seed) + "_hr.dat")
    write_hr(dest_hr, translations, hamiltonian, args.scheme)
    from importlib.metadata import version
    result = {
        "source_sha256": source_digests,
        "staged_hr_sha256": sha256(dest_hr),
        "staged_hr": str(dest_hr),
        "source_scheme": args.scheme,
        "staged_degeneracies": "all 1; source weights applied to elements",
        "translations": len(translations),
        "orbitals": hamiltonian.shape[1],
        "groupby": args.groupby,
        "HamiltonIO": version("HamiltonIO"),
    }
    result.update(verify_reader(out_seed, output / "POSCAR", args.groupby, points, translations, hamiltonian))
    summary = json.dumps(result, indent=2, allow_nan=False)
    (output / "hr_preparation.json").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

