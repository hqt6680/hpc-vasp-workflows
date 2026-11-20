#!/usr/bin/env python3
"""Validate trusted local TB2J results, exports, and convergence by bond."""

import argparse
import csv
import json
import pickle
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np


NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
ROW = re.compile(r"^\s*(\S+)\s+(\S+)\s+\(\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)\s+(" + NUM + r")")
DETAIL = re.compile(r"^\s*J_iso:\s*(" + NUM + ")")
KINDS = ("Jiso", "DMI", "Jani")


def max_abs(value):
    return float(np.max(np.abs(value)))


def get_result(path):
    file = path / "TB2J.pickle" if path.is_dir() else path
    with file.open("rb") as source:
        data = pickle.load(source)
    if not data.get("exchange_Jdict"):
        raise ValueError("No exchange interactions in " + str(file))
    atoms = data["atoms"]
    atom_by_spin = {int(index): i for i, index in enumerate(data["index_spin"]) if index >= 0}
    names = []
    counts = {}
    for element in atoms.get_chemical_symbols():
        counts[element] = counts.get(element, 0) + 1
        names.append(element + str(counts[element]))
    names_by_spin = {index: names[i] for index, i in atom_by_spin.items()}
    positions = atoms.get_positions()
    cell = atoms.cell.array
    interactions = {
        "Jiso": data["exchange_Jdict"],
        "DMI": data.get("dmi_ddict") or {},
        "Jani": data.get("Jani_dict") or {},
    }
    keys = set(interactions["Jiso"])
    for kind, values in interactions.items():
        shape = {"Jiso": (), "DMI": (3,), "Jani": (3, 3)}[kind]
        if values and (set(values) != keys or
                       any(np.shape(value) != shape or not np.all(np.isfinite(value))
                           for value in values.values())):
            raise ValueError("Invalid or incomplete %s in %s" % (kind, file))
        interactions[kind] = {key: np.asarray(value) * 1000 for key, value in values.items()}
    distances = {}
    for key in keys:
        r, i, j = key
        displacement = np.asarray(r) @ cell + positions[atom_by_spin[j]] - positions[atom_by_spin[i]]
        distances[key] = float(np.linalg.norm(displacement))
    if any(value <= 0 for value in distances.values()):
        raise ValueError("Zero-length interaction in " + str(file))
    return {
        "path": file.parent,
        "version": str(data.get("TB2J_version", "unknown")),
        "cell": cell,
        "positions": positions,
        "atom_by_spin": atom_by_spin,
        "name_by_spin": names_by_spin,
        "moments": np.asarray(data["spinat"]),
        "distances": distances,
        "interactions": interactions,
    }


def check_exports(result):
    directory = result["path"]
    by_name = {name: index for index, name in result["name_by_spin"].items()}
    jiso = result["interactions"]["Jiso"]
    table, detail = {}, {}
    current = None
    for line in (directory / "exchange.out").read_text(encoding="utf-8").splitlines():
        row = ROW.match(line)
        if row:
            name_i, name_j, r1, r2, r3, value = row.groups()
            current = ((int(r1), int(r2), int(r3)), by_name[name_i], by_name[name_j])
            if current in table:
                raise ValueError("Duplicate exchange.out row")
            table[current] = float(value)
        elif current and DETAIL.match(line):
            detail[current] = float(DETAIL.match(line).group(1))
    if set(table) != set(jiso) or set(detail) != set(jiso):
        raise ValueError("Exchange text/pickle bond keys differ")
    errors = {
        "text_table_Jiso_max_abs_error_mev": max(abs(table[key] - float(value)) for key, value in jiso.items()),
        "text_detail_Jiso_max_abs_error_mev": max(abs(detail[key] - float(value)) for key, value in jiso.items()),
    }

    root = ET.parse(directory / "Multibinit" / "exchange.xml").getroot()
    for kind, name in zip(KINDS, ("exchange", "DMI", "bilinear")):
        values = result["interactions"][kind]
        export = root.find("spin_%s_list" % name)
        if not values and export is None:
            continue
        if export is None or export.get("units") != "eV":
            raise ValueError("Missing or unexpected Multibinit %s units" % kind)
        loaded = {}
        for term in export.findall("spin_%s_term" % name):
            i, j, r1, r2, r3 = map(int, term.findtext("ijR").split())
            key = ((r1, r2, r3), i - 1, j - 1)
            item = np.asarray(term.findtext("data").split(), dtype=float) * 1000
            if key in loaded:
                raise ValueError("Duplicate Multibinit %s bond" % kind)
            loaded[key] = item
        if set(loaded) != set(values):
            raise ValueError("Multibinit/pickle %s bond keys differ" % kind)
        errors["multibinit_%s_max_abs_error_mev" % kind] = max(
            (max_abs(loaded[key] - value.ravel()) for key, value in values.items()), default=0.0)
    return errors


def check_pairs(interactions):
    residuals = {}
    for kind, values in interactions.items():
        if not values:
            continue
        errors = []
        for (r, i, j), value in values.items():
            opposite = (tuple(-n for n in r), j, i)
            if opposite not in values:
                raise ValueError("Missing reversed bond %s" % (opposite,))
            partner = values[opposite]
            if kind == "DMI":
                partner = -partner
            elif kind == "Jani":
                partner = partner.T
            errors.append(max_abs(value - partner))
        residuals[kind + "_reversal_max_abs_mev"] = max(errors)
    if interactions["Jani"]:
        residuals["Jani_asymmetry_max_abs_mev"] = max(max_abs(a - a.T) for a in interactions["Jani"].values())
    return residuals


def shell_data(result, shell_tol):
    interactions = result["interactions"]
    shells = []
    for key in sorted(result["distances"], key=result["distances"].get):
        distance = result["distances"][key]
        if not shells or abs(shells[-1][0] - distance) > shell_tol:
            shells.append((distance, []))
        shells[-1][1].append(key)
    output = []
    for distance, keys in shells:
        jiso = np.asarray([interactions["Jiso"][key] for key in keys])
        row = {
            "distance_angstrom": distance,
            "ordered_bonds": len(keys),
            "Jiso_mean_mev": float(jiso.mean()),
            "Jiso_range_mev": [float(jiso.min()), float(jiso.max())],
        }
        for kind in ("DMI", "Jani"):
            values = interactions[kind]
            if values:
                row[kind + "_max_component_mev"] = max(max_abs(values[key]) for key in keys)
        output.append(row)
    return output


def check_c3(result):
    if len(result["atom_by_spin"]) != 1:
        raise ValueError("--triangular-c3 expects one magnetic atom in a triangular cell")
    angle = 2 * np.pi / 3
    c, s = np.cos(angle), np.sin(angle)
    q = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    lattice = result["cell"]
    lattice_mapping = lattice @ q.T @ np.linalg.inv(lattice)
    lattice_integer = np.rint(lattice_mapping).astype(int)
    if not np.allclose(lattice_mapping, lattice_integer, atol=1e-6):
        raise ValueError("Cell does not admit Cartesian C3 around z")
    errors = {}
    for kind, values in result["interactions"].items():
        if not values:
            continue
        differences = []
        missing = []
        for (r, i, j), value in values.items():
            rotated_key = (tuple(np.asarray(r) @ lattice_integer), i, j)
            if rotated_key not in values:
                missing.append(result["distances"][(r, i, j)])
                continue
            rotated = value
            if kind == "DMI":
                rotated = q @ value
            elif kind == "Jani":
                rotated = q @ value @ q.T
            differences.append(max_abs(values[rotated_key] - rotated))
        errors[kind + "_c3_max_abs_residual_mev"] = max(differences, default=None)
        errors[kind + "_c3_missing_rotated_bonds"] = len(missing)
        errors[kind + "_c3_nearest_missing_rotated_bond_angstrom"] = min(missing, default=None)
    return errors


def compare_result(result, reference):
    metrics = {}
    if (result["name_by_spin"] != reference["name_by_spin"]
            or not np.allclose(result["cell"], reference["cell"], atol=1e-6)
            or not np.allclose(result["positions"], reference["positions"], atol=1e-6)):
        raise ValueError("Structures differ between convergence runs")
    for kind in KINDS:
        current = result["interactions"][kind]
        baseline = reference["interactions"][kind]
        if set(current) != set(baseline):
            raise ValueError("Convergence pair has different %s bond keys. Use the same rcut and adequate meshes." % kind)
        if current:
            deltas = np.asarray([max_abs(value - baseline[key]) for key, value in current.items()])
            metrics[kind + "_max_abs_change_mev"] = float(deltas.max())
            metrics[kind + "_p95_abs_change_mev"] = float(np.percentile(deltas, 95))
    return metrics


def check_merge(result, branches):
    if len(result["atom_by_spin"]) != 1:
        raise ValueError("Merge projection diagnostic expects a one-magnetic-atom reference")
    index = next(iter(result["atom_by_spin"]))
    merged = result["interactions"]
    keys = set(merged["Jiso"])
    if any(set(merged[kind]) != keys for kind in KINDS):
        raise ValueError("Merged output has incomplete interaction keys")
    branch_jiso = np.asarray([[branch["interactions"]["Jiso"][key] for branch in branches] for key in keys])
    mean_jiso = dict(zip(keys, branch_jiso.mean(axis=1)))
    identity = np.eye(3)
    shifts = {key: float(merged["Jiso"][key]) - mean_jiso[key] for key in keys}
    dmi, jani, total_symmetric = [], [], []
    moments, transverse_bases, coefficients = [], [], []
    for branch in branches:
        if (result["name_by_spin"] != branch["name_by_spin"]
                or not np.allclose(result["cell"], branch["cell"], atol=1e-6)
                or not np.allclose(result["positions"], branch["positions"], atol=1e-6)):
            raise ValueError("Merge projection diagnostic expects identical Cartesian cells")
        values = branch["interactions"]
        if any(set(values[kind]) != keys for kind in KINDS):
            raise ValueError("Merge branch bond keys differ")
        moment = branch["moments"][branch["atom_by_spin"][index]]
        norm = np.linalg.norm(moment)
        if norm < 1e-3:
            raise ValueError("Merge branch moment is nearly zero")
        direction = moment / norm
        moments.append(direction)
        projector = identity - np.outer(direction, direction)
        u = np.cross(direction, identity[np.argmin(np.abs(direction))])
        u /= np.linalg.norm(u)
        v = np.cross(direction, u)
        transverse_bases.extend([u, v])
        for a, b in ((u, u), (u, v), (v, v)):
            coefficients.append(np.hstack([a * b, np.roll(a, -1) * b + np.roll(b, -1) * a]))
        for key in keys:
            dmi.append(max_abs(projector @ (merged["DMI"][key] - values["DMI"][key])))
            # Recent TB2J merge moves trace(Jani)/3 into Jiso. Restore it when
            # checking the Jani projection used by its least-squares solver.
            unstandardized_jani = merged["Jani"][key] + shifts[key] * identity
            jani.append(max_abs(projector @ (unstandardized_jani - values["Jani"][key]) @ projector))
            total_difference = (merged["Jani"][key] - values["Jani"][key]
                                + (float(merged["Jiso"][key]) - float(values["Jiso"][key])) * identity)
            total_symmetric.append(max_abs(projector @ total_difference @ projector))
    d_singular = np.linalg.svd(transverse_bases, compute_uv=False)
    a_singular = np.linalg.svd(coefficients, compute_uv=False)
    return {
        "branch_unit_moments": np.asarray(moments).tolist(),
        "branch_moment_matrix_rank": int(np.linalg.matrix_rank(moments, tol=0.05)),
        "DMI_projector_rank": int(np.sum(d_singular > 0.4 * d_singular[0])),
        "Jani_projector_rank": int(np.sum(a_singular > 0.01 * a_singular[0])),
        "raw_Jiso_max_branch_spread_mev": float(np.max(np.ptp(branch_jiso, axis=1))),
        "Jiso_max_trace_shift_from_branch_mean_mev": max(abs(shift) for shift in shifts.values()),
        "merged_Jani_max_abs_trace_mev": max(abs(float(np.trace(tensor))) for tensor in merged["Jani"].values()),
        "DMI_transverse_fit_max_abs_mev": max(dmi),
        "Jani_transverse_fit_max_abs_mev": max(jani),
        "full_symmetric_tensor_transverse_fit_max_abs_mev": max(total_symmetric),
    }


def write_bonds(result, path):
    values = result["interactions"]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["i", "j", "R1", "R2", "R3", "distance_angstrom", "Jiso_meV",
                         "Dx_meV", "Dy_meV", "Dz_meV"] +
                        ["Jani_%s%s_meV" % (a, b) for a in "xyz" for b in "xyz"])
        for key in sorted(result["distances"], key=lambda k: (result["distances"][k], k)):
            r, i, j = key
            writer.writerow([result["name_by_spin"][i], result["name_by_spin"][j], *r,
                             result["distances"][key], float(values["Jiso"][key]),
                             *values["DMI"].get(key, [""] * 3),
                             *np.ravel(values["Jani"].get(key, [""] * 9))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="Directory containing the trusted TB2J.pickle, exchange.out and Multibinit")
    parser.add_argument("--compare", type=Path, action="append", default=[], help="Repeat for independently varied runs")
    parser.add_argument("--branches", nargs=3, type=Path, metavar=("X", "Y", "Z"), help="Three same-cell SOC branches used to merge")
    parser.add_argument("--triangular-c3", action="store_true", help="Report C3 residuals around Cartesian z for one triangular magnetic sublattice")
    parser.add_argument("--shell-tol", type=float, default=1e-3, help="Distance tolerance in Angstrom")
    parser.add_argument("--pair-tol", type=float, default=1e-5, help="Pair-reversal tolerance in meV")
    parser.add_argument("--convergence-tol", type=float, help="Maximum component change in meV")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()

    result = get_result(args.result)
    pairs = check_pairs(result["interactions"])
    exports = check_exports(result)
    metrics = {
        "result": str(result["path"]),
        "TB2J_version": result["version"],
        "magnetic_sites": {result["name_by_spin"][index]: result["moments"][atom].tolist()
                           for index, atom in result["atom_by_spin"].items()},
        "pair_checks": pairs,
        "export_checks": exports,
        "shells": shell_data(result, args.shell_tol),
    }
    valid = max(pairs.values()) <= args.pair_tol and max(exports.values()) <= 0.001
    if args.triangular_c3:
        metrics["c3_checks"] = check_c3(result)
    if args.branches:
        merge = check_merge(result, [get_result(path) for path in args.branches])
        metrics["merge_checks"] = merge
        valid &= (merge["branch_moment_matrix_rank"] == 3
                  and merge["DMI_projector_rank"] == 3 and merge["Jani_projector_rank"] == 6)
    if args.compare:
        comparisons = {str(path): compare_result(result, get_result(path)) for path in args.compare}
        metrics["convergence_checks"] = comparisons
        if args.convergence_tol is not None:
            valid &= all(value <= args.convergence_tol for comp in comparisons.values() for value in comp.values())
    metrics["passed"] = bool(valid)

    output = json.dumps(metrics, indent=2, allow_nan=False)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    if args.csv:
        write_bonds(result, args.csv)
    print(output)
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

