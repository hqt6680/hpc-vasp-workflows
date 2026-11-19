#!/usr/bin/env python3
"""Compare the MnInP2Te6 test z branch or merged result with the local z archive."""

import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from check_tb2j_exchange import DETAIL, ROW, check_exports, get_result


HISTORICAL = Path(__file__).resolve().parent / "../../MnInP2Te6/TB2J/TB2J_results"
TEXT_TOL_MEV = 5.1e-5
XML_TOL_MEV = 5e-5
CARTESIAN_DIRECTION_TOL = 1e-6
FIELDS = (
    "Jiso", "Dx", "Dy", "Jani_xx", "Jani_xy", "Jani_yx", "Jani_yy",
    "Jsym_xx", "Jsym_xy", "Jsym_yx", "Jsym_yy",
)
GROUPS = {
    "Jiso": ("Jiso",),
    "Dxy": ("Dx", "Dy"),
    "Jani_xy_block": ("Jani_xx", "Jani_xy", "Jani_yx", "Jani_yy"),
    "Jsym_xy_block": ("Jsym_xx", "Jsym_xy", "Jsym_yx", "Jsym_yy"),
}


def mn_moment(result):
    if result["name_by_spin"] != {0: "Mn1"}:
        raise ValueError(f"Expected one magnetic site, Mn1: {result['path']}")
    return result["moments"][result["atom_by_spin"][0]]


def check_z_axis(result):
    moment = mn_moment(result)
    tilt = float(np.degrees(np.arctan2(np.linalg.norm(moment[:2]), moment[2])))
    if np.linalg.norm(moment) <= 0 or tilt > 0.5:
        raise ValueError(f"Mn moment is not along +z within 0.5 degrees: {result['path']}")
    return tilt


def unit_rows(matrix):
    return matrix / np.linalg.norm(matrix, axis=1)[:, None]


def displacement(result, key):
    r, i, j = key
    sites = result["atom_by_spin"]
    return np.asarray(r) @ result["cell"] + result["positions"][sites[j]] - result["positions"][sites[i]]


def check_frame(current, archive):
    if not np.allclose(unit_rows(current["cell"]), unit_rows(archive["cell"]),
                       rtol=0, atol=CARTESIAN_DIRECTION_TOL):
        raise ValueError("Lattice row directions differ. Establish the lattice and spin frame mapping first.")
    for result in (current, archive):
        if not np.allclose(unit_rows(result["cell"])[2], [0, 0, 1], rtol=0, atol=CARTESIAN_DIRECTION_TOL):
            raise ValueError("Expected the third lattice vector to point along Cartesian +z")
    current_mn = current["positions"][current["atom_by_spin"][0]] @ np.linalg.inv(current["cell"])
    archive_mn = archive["positions"][archive["atom_by_spin"][0]] @ np.linalg.inv(archive["cell"])
    if not np.allclose(current_mn, archive_mn, rtol=0, atol=CARTESIAN_DIRECTION_TOL):
        raise ValueError("Mn sites differ in fractional coordinates. Check the periodic image convention.")


def validate_exports(result, historical=False):
    for kind in ("DMI", "Jani"):
        if not result["interactions"][kind]:
            raise ValueError(f"Missing {kind} terms: {result['path']}")
    errors = check_exports(result)
    for field, error in errors.items():
        if field.startswith("multibinit_") and error > XML_TOL_MEV:
            raise ValueError(f"{field}={error:.6g} meV: {result['path']}")
        if field.startswith("text_") and not (historical and field.startswith("text_detail_")):
            if error > TEXT_TOL_MEV:
                raise ValueError(f"{field}={error:.6g} meV: {result['path']}")
    return errors


def archive_text_discrepancies(archive):
    directory = archive["path"]
    names = {name: index for index, name in archive["name_by_spin"].items()}
    root = ET.parse(directory / "Multibinit" / "exchange.xml").getroot()
    exported = {}
    for term in root.find("spin_exchange_list").findall("spin_exchange_term"):
        i, j, rx, ry, rz = map(int, term.findtext("ijR").split())
        exported[((rx, ry, rz), i - 1, j - 1)] = float(term.findtext("data").split()[0]) * 1000

    result = []
    key = None
    for line in (directory / "exchange.out").read_text(encoding="utf-8").splitlines():
        header = ROW.match(line)
        detail = DETAIL.match(line)
        if header:
            i, j, rx, ry, rz, value = header.groups()
            key = ((int(rx), int(ry), int(rz)), names[i], names[j])
            table_value = float(value)
        elif detail and key is not None:
            pickle_value = float(archive["interactions"]["Jiso"][key])
            detail_value = float(detail.group(1))
            if abs(pickle_value - detail_value) > TEXT_TOL_MEV:
                result.append({
                    "R": key[0],
                    "site_i": archive["name_by_spin"][key[1]],
                    "site_j": archive["name_by_spin"][key[2]],
                    "exchange_out_table_mev": table_value,
                    "exchange_out_detail_mev": detail_value,
                    "pickle_mev": pickle_value,
                    "multibinit_mev": exported[key],
                })
            key = None
    return result


def transverse_components(result, key):
    interactions = result["interactions"]
    jiso = float(interactions["Jiso"][key])
    dxy = interactions["DMI"][key][:2]
    jani = interactions["Jani"][key][:2, :2]
    symmetric = jani + jiso * np.eye(2)
    return dict(zip(FIELDS, map(float, (jiso, *dxy, *jani.ravel(), *symmetric.ravel()))))


def bond_id(key, result):
    r, i, j = key
    return dict(zip(("Rx", "Ry", "Rz", "site_i", "site_j"), (*r, result["name_by_spin"][i], result["name_by_spin"][j])))


def compare_bonds(current, archive):
    current_keys = set(current["distances"])
    archive_keys = set(archive["distances"])
    common = current_keys & archive_keys
    if not common:
        raise ValueError("No shared directed bonds")
    rows = []
    for key in sorted(common, key=lambda key: (current["distances"][key], key)):
        current_r = displacement(current, key)
        archive_r = displacement(archive, key)
        current_d = current["distances"][key]
        archive_d = archive["distances"][key]
        if not np.allclose(current_r / current_d, archive_r / archive_d,
                           rtol=0, atol=CARTESIAN_DIRECTION_TOL):
            raise ValueError(f"Cartesian direction differs for exact bond key {key}")
        row = {
            **bond_id(key, current),
            "current_distance_angstrom": current_d,
            "archive_distance_angstrom": archive_d,
        }
        current_values = transverse_components(current, key)
        archive_values = transverse_components(archive, key)
        for field in FIELDS:
            row[f"{field}_current_mev"] = current_values[field]
            row[f"{field}_archive_mev"] = archive_values[field]
            row[f"{field}_delta_mev"] = current_values[field] - archive_values[field]
        rows.append(row)
    return rows, sorted(current_keys - common), sorted(archive_keys - common)


def summarize_changes(rows):
    summary = {}
    for name, fields in GROUPS.items():
        columns = [f"{field}_delta_mev" for field in fields]
        changes = np.abs([[row[column] for column in columns] for row in rows])
        index, component = np.unravel_index(np.argmax(changes), changes.shape)
        summary[name] = {
            "max_abs_delta_mev": float(changes[index, component]),
            "p95_of_per_bond_max_abs_delta_mev": float(np.percentile(changes.max(axis=1), 95)),
            "worst_bond": {key: rows[index][key] for key in ("Rx", "Ry", "Rz", "site_i", "site_j")},
            "worst_component": fields[component],
        }
    return summary


def describe_result(result, z_reference, errors):
    return {
        "path": str(result["path"].resolve()),
        "tb2j_version": result["version"],
        "cell_angstrom": result["cell"].tolist(),
        "mn_position_angstrom": result["positions"][result["atom_by_spin"][0]].tolist(),
        "stored_mn_moment_muB": mn_moment(result).tolist(),
        "z_reference_path": str(z_reference["path"].resolve()),
        "z_reference_moment_muB": mn_moment(z_reference).tolist(),
        "z_reference_tilt_degrees": check_z_axis(z_reference),
        "export_errors_mev": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path, help="Current z or merged TB2J result directory")
    parser.add_argument("--archive", type=Path, default=HISTORICAL)
    parser.add_argument("--z-reference", type=Path, help="Matching current z directory when current is merged")
    parser.add_argument("--json", type=Path, required=True, help="Summary and historical export audit")
    parser.add_argument("--csv", type=Path, required=True, help="Per-directed-bond comparison")
    args = parser.parse_args()

    current = get_result(args.current)
    archive = get_result(args.archive)
    z_reference = get_result(args.z_reference) if args.z_reference else current
    if args.z_reference and (
        not np.allclose(current["cell"], z_reference["cell"], rtol=0, atol=1e-8)
        or not np.allclose(current["positions"], z_reference["positions"], rtol=0, atol=1e-8)
        or current["name_by_spin"] != z_reference["name_by_spin"]
        or current["distances"].keys() != z_reference["distances"].keys()
    ):
        raise ValueError("Current merged structure or directed keys differ from the supplied z reference")
    current_errors = validate_exports(current)
    archive_errors = validate_exports(archive, historical=True)
    check_frame(current, archive)
    rows, current_only, archive_only = compare_bonds(current, archive)

    run_file = z_reference["path"] / "run.json"
    summary = {
        "comparison": "merged_to_archived_z" if args.z_reference else "z_to_archived_z",
        "current": describe_result(current, z_reference, current_errors),
        "archive": describe_result(archive, archive, archive_errors),
        "current_z_run": json.loads(run_file.read_text(encoding="utf-8")) if run_file.is_file() else None,
        "archive_text_Jiso_detail_disagreements": archive_text_discrepancies(archive),
        "coordinate_convention": (
            "Match exact directed (R, Mn1, Mn1) in the unchanged lattice basis. "
            "The Cartesian displacement from i to j is R @ cell + position[j] - position[i]. "
            "Components are signed stored Cartesian values in meV; no axis rotation, spin-length "
            "scaling, or bond multiplicity factor is applied."
        ),
        "interpretation": (
            "The old z response supports D_x, D_y and the xy block of Jani. "
            "Jsym_xy is the symmetric transverse block Jiso I + Jani and is invariant under a "
            "scalar shift between Jiso and Jani. The merged Jiso and raw Jani can use a different "
            "trace split. Different structures and methods make this a historical comparison."
        ),
        "matched_directed_bonds": len(rows),
        "current_only_directed_bonds": [bond_id(key, current) for key in current_only],
        "archive_only_directed_bonds": [bond_id(key, archive) for key in archive_only],
        "max_abs_cell_component_change_angstrom": float(np.max(np.abs(current["cell"] - archive["cell"]))),
        "statistics": summarize_changes(rows),
    }
    args.json.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with args.csv.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
