#!/usr/bin/env python3
"""Run the pinned TB2J spinor workflow on one Wannier90 Hamiltonian."""

import argparse
import json
import math
from importlib.metadata import version
from pathlib import Path


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("expected a finite positive number")
    return number


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--axis", choices=("x", "y", "z"), default="z")
    parser.add_argument("--input", type=Path, help="Wannier files; defaults to ./AXIS")
    parser.add_argument("--output", type=Path, required=True, help="New results directory")
    parser.add_argument("--prefix", default="wannier90")
    parser.add_argument("--groupby", choices=("orbital", "spin"), default="orbital")
    parser.add_argument("--element", nargs="+", default=["Mn"])
    parser.add_argument("--efermi", type=float, required=True, help="DFT Fermi energy in eV")
    parser.add_argument("--kmesh", nargs=3, type=int, default=(17, 17, 1))
    parser.add_argument("--temperature", type=positive_float, default=600.0, help="CFR temperature in K")
    parser.add_argument("--nz", type=int, default=100, help="Requested CFR pole count")
    parser.add_argument("--rcut", type=positive_float, default=20.0, help="Pair distance in angstroms")
    parser.add_argument("--emin", type=float, default=-14.0, help="Lower-bound seed relative to EF in eV")
    parser.add_argument("--np", type=int, default=1, help="Worker processes on one node")
    args = parser.parse_args()
    if not math.isfinite(args.efermi) or not math.isfinite(args.emin) or args.emin >= 0:
        parser.error("use a finite --efermi and a finite negative --emin")
    if any(n < 1 or n % 2 == 0 for n in args.kmesh):
        parser.error("--kmesh must contain positive odd integers")
    if args.nz < 2 or args.nz % 2 or args.np < 1:
        parser.error("--nz must be a positive even integer and --np must be positive")
    if Path(args.prefix).name != args.prefix or not args.prefix:
        parser.error("--prefix must be a single nonempty filename component")
    return args


def require_files(directory, filenames):
    for filename in filenames:
        path = directory / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Missing or empty file: {path}")


def main():
    args = parse_args()
    input_dir = (args.input or Path(args.axis)).resolve()
    output = args.output.resolve()
    filenames = [
        "POSCAR",
        f"{args.prefix}.win",
        f"{args.prefix}_hr.dat",
        f"{args.prefix}_centres.xyz",
    ]
    require_files(input_dir, filenames + ["hr_preparation.json"])
    import hashlib

    preparation = json.loads((input_dir / "hr_preparation.json").read_text(encoding="utf-8"))
    if not preparation.get("verified") or preparation.get("groupby") != args.groupby:
        raise SystemExit("HamiltonIO validation failed or used a different spinor order")
    with (input_dir / f"{args.prefix}_hr.dat").open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != preparation.get("staged_hr_sha256"):
        raise SystemExit("Staged HR does not match the verified Hamiltonian")
    if output.exists():
        raise SystemExit(f"Output path already exists: {output}")

    import numpy as np
    from ase.units import kB
    from TB2J.interfaces import gen_exchange
    from TB2J.io_exchange.io_exchange import SpinIO

    output.mkdir(parents=True)
    # The pinned HamiltonIO reader uses _tb.dat ahead of _hr.dat and does not
    # apply _wsvec.dat; stage the explicit HR/centres input without copying it.
    staged = output / "wannier_input"
    staged.mkdir()
    for filename in filenames:
        (staged / filename).symlink_to(input_dir / filename)

    manifest = {
        "state": "running",
        "axis": args.axis,
        "input": str(input_dir),
        "staged_hr_sha256": digest,
        "output": str(output),
        "prefix": args.prefix,
        "groupby": args.groupby,
        "magnetic_elements": args.element,
        "fermi_energy_eV": args.efermi,
        "kmesh": args.kmesh,
        "temperature_K": args.temperature,
        "smearing_eV": args.temperature * kB,
        "requested_cfr_poles": args.nz,
        "rcut_angstrom": args.rcut,
        "emin_seed_eV": args.emin,
        "processes": args.np,
        "versions": {package: version(package) for package in ("TB2J", "HamiltonIO", "numpy", "scipy")},
    }
    manifest_path = output / "run.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    gen_exchange(
        path=str(staged),
        posfile="POSCAR",
        prefix_SOC=args.prefix,
        prefix_up=None,
        prefix_dn=None,
        colinear=False,
        groupby=args.groupby,
        efermi=args.efermi,
        kmesh=args.kmesh,
        magnetic_elements=args.element,
        Rcut=args.rcut,
        emin=args.emin,
        emax=0.0,
        nz=args.nz,
        nproc=args.np,
        smearing=args.temperature * kB,
        integration_method="CFR",
        output_path=str(output),
    )

    require_files(output, ["exchange.out", "assigned_basis.txt", "TB2J.pickle", "Multibinit/exchange.xml"])
    result = SpinIO.load_pickle(path=str(output))
    keys = set(result.exchange_Jdict)
    dictionaries = (result.exchange_Jdict, result.dmi_ddict, result.Jani_dict)
    if not keys or any(set(values) != keys for values in dictionaries):
        raise SystemExit("TB2J output has missing exchange, DMI or anisotropic terms")
    if any(not np.all(np.isfinite(list(values.values()))) for values in dictionaries):
        raise SystemExit("TB2J output contains a non-finite exchange term")
    magnetic_spins = np.asarray(result.spinat)[np.asarray(result.index_spin) >= 0]
    if not magnetic_spins.size or not np.all(np.isfinite(magnetic_spins)):
        raise SystemExit("TB2J output has missing or non-finite magnetic moments")
    manifest.update(state="completed", pair_count=len(keys), magnetic_spins_muB=magnetic_spins.tolist())
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
