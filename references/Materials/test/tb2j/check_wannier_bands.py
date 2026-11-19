#!/usr/bin/env python3
"""Compare the Wannier Hamiltonian with VASP at exact fractional k points."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


def read_win(seed):
    text = Path(str(seed) + ".win").read_text(encoding="utf-8")
    text = re.sub(r"[#!].*", "", text).lower()
    tags = dict(re.findall(r"^\s*(\w+)\s*[:=]\s*([^\n]+)", text, re.M))
    points = np.array([line.split()[:3] for line in get_block(text, "kpoints")], dtype=float)
    lattice = get_block(text, "unit_cell_cart")
    scale = 0.529177210903 if lattice[0].strip() == "bohr" else 1.0
    lattice = np.array([line.split() for line in lattice[-3:]], dtype=float) * scale
    return tags, points, lattice


def get_block(text, name):
    block = re.search(r"^\s*begin\s+" + name + r"\s*\n(.*?)^\s*end\s+" + name + r"\s*$", text, re.M | re.S)
    if not block:
        raise ValueError("Missing .win block " + name)
    return [line for line in block.group(1).splitlines() if line.strip()]


def read_vasp(path, spin):
    root = ET.parse(path).getroot()
    kpoints = root.find("kpoints/varray[@name='kpointlist']")
    lattice = root.find("structure[@name='finalpos']/crystal/varray[@name='basis']")
    if kpoints is None or lattice is None:
        raise ValueError("Missing VASP k-point list or final cell")
    final_step = root.findall("calculation")[-1]
    values = final_step.find("eigenvalues/array/set/set[@comment='spin %d']" % spin)
    if values is None:
        raise ValueError("VASP eigenvalues missing requested spin %d" % spin)
    points = np.array([line.text.split() for line in kpoints], dtype=float)
    cell = np.array([line.text.split() for line in lattice], dtype=float)
    eigenvalues = np.array([[float(line.text.split()[0]) for line in kpoint] for kpoint in values])
    if len(points) != len(eigenvalues):
        raise ValueError("VASP k-point and eigenvalue counts differ")
    soc = root.find("incar/i[@name='LSORBIT']")
    spinor = root.find("incar/i[@name='LNONCOLLINEAR']")
    is_spinor = any(entry is not None and entry.text.strip() == "T" for entry in (soc, spinor))
    return points, eigenvalues, cell, is_spinor


def read_eig(seed, nk):
    data = np.loadtxt(str(seed) + ".eig")
    nb = len(data) // nk
    if data.shape != (nk * nb, 3):
        raise ValueError("Unexpected .eig length")
    rows = data.reshape(nk, nb, 3)
    if not (np.all(rows[:, :, 0] == np.arange(1, nb + 1))
            and np.all(rows[:, :, 1] == np.arange(1, nk + 1)[:, None])):
        raise ValueError("Unexpected .eig band or k-point indexing")
    return rows[:, :, 2]


def read_hr(seed, use_ws):
    with open(str(seed) + "_hr.dat", encoding="utf-8") as source:
        source.readline()
        nw = int(source.readline())
        nr = int(source.readline())
        degeneracy = []
        while len(degeneracy) < nr:
            degeneracy.extend(map(int, source.readline().split()))
        entries = np.loadtxt(source).reshape(nr, nw * nw, 7)
    keys = entries[:, 0, :3].astype(int)
    weights = np.asarray(degeneracy)
    if len(weights) != nr or min(weights) < 1 or np.any(entries[:, :, :3] != keys[:, None, :]):
        raise ValueError("Malformed _hr.dat Wigner-Seitz translations")
    rows = entries[:, :, 3].astype(int) - 1
    cols = entries[:, :, 4].astype(int) - 1
    if np.any(np.sort(rows * nw + cols, axis=1) != np.arange(nw * nw)):
        raise ValueError("Malformed _hr.dat orbital indices")
    elements = (entries[:, :, 5] + 1j * entries[:, :, 6]) / weights[:, None]
    h = np.zeros((nr, nw, nw), complex)
    h[np.arange(nr)[:, None], rows, cols] = elements
    if not use_ws:
        return keys, h

    by_translation = {tuple(r): matrix for r, matrix in zip(keys, h)}
    expanded = defaultdict(lambda: np.zeros((nw, nw), complex))
    seen = set()
    with open(str(seed) + "_wsvec.dat", encoding="utf-8") as source:
        header = next(source)
        if ".false." in header.lower():
            raise ValueError("_wsvec.dat declares use_ws_distance=false")
        for line in source:
            if not line.strip():
                continue
            r1, r2, r3, m, n = map(int, line.split())
            r = (r1, r2, r3)
            key = (r, m, n)
            if key in seen or not (1 <= m <= nw and 1 <= n <= nw):
                raise ValueError("Malformed _wsvec.dat orbital indices")
            seen.add(key)
            count = int(next(source))
            value = by_translation[r][m - 1, n - 1] / count
            for _ in range(count):
                t1, t2, t3 = map(int, next(source).split())
                expanded[(r1 + t1, r2 + t2, r3 + t3)][m - 1, n - 1] += value
    if len(seen) != nr * nw * nw:
        raise ValueError("_wsvec.dat coverage differs from _hr.dat")
    return np.asarray(list(expanded)), np.stack(list(expanded.values()))


def diagonalize(points, translations, h):
    bands = []
    hermiticity = 0.0
    for start in range(0, len(points), 128):
        phase = np.exp(2j * np.pi * (points[start:start + 128] @ translations.T))
        hk = np.einsum("kr,rij->kij", phase, h, optimize=True)
        adjoint = hk.transpose(0, 2, 1).conj()
        hermiticity = max(hermiticity, float(np.max(np.abs(hk - adjoint))))
        bands.append(np.linalg.eigvalsh((hk + adjoint) / 2))
    return np.concatenate(bands), hermiticity


def match_levels(target, model):
    """Minimum squared energy mismatch with unique, order-preserving matches."""
    n_target, n_model = len(target), len(model)
    if n_target > n_model:
        return None
    if n_target == 0:
        return np.array([])
    differences = target[:, None] - model
    cost = np.full((n_target + 1, n_model + 1), np.inf)
    cost[0, :] = 0
    used = np.zeros_like(cost, dtype=bool)
    for i in range(1, n_target + 1):
        for j in range(i, n_model + 1):
            take = cost[i - 1, j - 1] + differences[i - 1, j - 1] ** 2
            used[i, j] = take < cost[i, j - 1]
            cost[i, j] = take if used[i, j] else cost[i, j - 1]
    errors = []
    i, j = n_target, n_model
    while i:
        if used[i, j]:
            errors.append(differences[i - 1, j - 1])
            i -= 1
        j -= 1
    return np.array(errors[::-1])


def window_mask(energies, window):
    return (energies >= window[0]) & (energies <= window[1])


def compare(reference, model, window):
    errors = []
    unmatched_kpoints = 0
    for ref_k, model_k in zip(reference, model):
        match = match_levels(ref_k[window_mask(ref_k, window)], model_k)
        if match is None:
            unmatched_kpoints += 1
        else:
            errors.extend(match)
    abs_errors = np.abs(errors)
    return {
        "matched_levels": len(errors),
        "kpoints_with_insufficient_levels": unmatched_kpoints,
        "rms_ev": float(np.sqrt(np.mean(abs_errors ** 2))) if len(errors) else None,
        "p95_abs_ev": float(np.percentile(abs_errors, 95)) if len(errors) else None,
        "max_abs_ev": float(np.max(abs_errors)) if len(errors) else None,
    }


def count_range(energies, window):
    counts = np.sum(window_mask(energies, window), axis=1)
    return [int(counts.min()), int(counts.max())]


def passes(metrics, rms, maximum):
    return (metrics["matched_levels"] > 0 and metrics["kpoints_with_insufficient_levels"] == 0
            and metrics["rms_ev"] <= rms and metrics["max_abs_ev"] <= maximum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True, help="Path prefix to .win, .eig, _hr.dat and _wsvec.dat")
    parser.add_argument("--vasprun", type=Path, help="Same-method independent band reference")
    parser.add_argument("--spin", default=1, type=int, choices=(1, 2), help="VASP XML spin dataset")
    parser.add_argument("--window", nargs=2, type=float, metavar=("LOW", "HIGH"), help="Absolute eV interval for band comparison")
    parser.add_argument("--ws", choices=("auto", "global", "pair"), default="auto",
                        help="Use global _hr.dat degeneracy or per-pair _wsvec.dat, as in the TB2J reader")
    parser.add_argument("--rms-ev", type=float, default=0.04)
    parser.add_argument("--max-ev", type=float, default=0.12)
    parser.add_argument("--frozen-max-ev", type=float, default=0.001)
    parser.add_argument("--gauge", choices=("mlwf", "projected"), default="mlwf",
                        help="Require MLWF convergence, or validate an explicit zero-iteration projection gauge")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--wout", type=Path, help="Wannier90 output log, defaults to SEED.wout")
    args = parser.parse_args()
    if bool(args.vasprun) != bool(args.window):
        parser.error("Supply --vasprun and --window together")
    if args.window and args.window[0] >= args.window[1]:
        parser.error("Expected --window LOW HIGH with LOW < HIGH")

    tags, training_k, cell = read_win(args.seed)
    ws_file = Path(args.seed + "_wsvec.dat")
    use_ws = args.ws == "pair" or (args.ws == "auto" and ws_file.is_file()
                                   and "false" not in tags.get("use_ws_distance", "true"))
    translations, h = read_hr(args.seed, use_ws)
    nw = h.shape[1]
    dft = read_eig(args.seed, len(training_k))
    wannier, hermiticity = diagonalize(training_k, translations, h)
    outer = (float(tags.get("dis_win_min", "-inf")), float(tags.get("dis_win_max", "inf")))
    frozen = (float(tags.get("dis_froz_min", tags.get("dis_win_min", "-inf"))),
              float(tags.get("dis_froz_max", "-inf")))
    has_frozen = frozen[1] > frozen[0]
    metrics = {
        "seed": args.seed,
        "ws_scheme": "pair" if use_ws else "global",
        "wannier_orbitals": nw,
        "training_kpoints": len(training_k),
        "training_outer_count_range": count_range(dft, outer),
        "training_frozen_count_range": count_range(dft, frozen) if has_frozen else [0, 0],
    }
    valid = metrics["training_outer_count_range"][0] >= nw >= metrics["training_frozen_count_range"][1]
    if has_frozen:
        fit = compare(dft, wannier, frozen)
        metrics["training_frozen_fit"] = fit
        valid &= passes(fit, args.frozen_max_ev, args.frozen_max_ev)

    if args.vasprun:
        path_k, path_dft, vasp_cell, is_spinor = read_vasp(args.vasprun, args.spin)
        if is_spinor != ("true" in tags.get("spinors", "false") or tags.get("spinors", "F").strip() == ".t."):
            raise ValueError("VASP and Wannier spin treatments differ")
        if not np.allclose(cell, vasp_cell, rtol=1e-7, atol=1e-6):
            raise ValueError("VASP and Wannier cells differ")
        path_wannier, path_hermiticity = diagonalize(path_k, translations, h)
        metrics["band_reference"] = str(args.vasprun)
        metrics["path_kpoints"] = len(path_k)
        metrics["path_window_ev_absolute"] = args.window
        metrics["path_dft_to_wannier"] = compare(path_dft, path_wannier, args.window)
        metrics["path_wannier_to_dft"] = compare(path_wannier, path_dft, args.window)
        valid &= all(passes(metrics[key], args.rms_ev, args.max_ev)
                     for key in ("path_dft_to_wannier", "path_wannier_to_dft"))
        hermiticity = max(hermiticity, path_hermiticity)

    metrics["max_hermiticity_residual_ev"] = hermiticity
    metrics["band_checks_passed"] = bool(valid and hermiticity <= 1e-4)
    log = (args.wout or Path(args.seed + ".wout")).read_text(encoding="utf-8", errors="replace")
    log = log.lower()
    metrics["wannier_normal_exit"] = "all done: wannier90 exiting" in log
    metrics["disentanglement_converged"] = ("disentanglement convergence criteria satisfied" in log
                                            if dft.shape[1] > nw else None)
    metrics["localization_converged"] = "wannierisation convergence criteria satisfied" in log
    metrics["gauge"] = args.gauge
    if args.gauge == "projected":
        projection_input = (
            tags.get("num_iter", "").strip() == "0"
            and "restart" not in tags
            and "true" not in tags.get("use_bloch_phases", "false")
            and "initial state" in log
            and "final state" in log
        )
        zero_reported = bool(re.search(
            r"total number of iterations\s*:\s*0\s*\|", log
        ))
        metrics["projected_gauge_verified"] = bool(projection_input and zero_reported)
        localization_ok = metrics["projected_gauge_verified"]
    else:
        localization_ok = metrics["localization_converged"]
    metrics["passed"] = bool(metrics["band_checks_passed"] and metrics["wannier_normal_exit"]
                             and metrics["disentanglement_converged"] is not False
                             and localization_ok)
    output = json.dumps(metrics, indent=2, allow_nan=False)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

