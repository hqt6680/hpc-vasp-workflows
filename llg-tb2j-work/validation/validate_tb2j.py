"""Validate the actual six-shell TB2J CSV against a Cartesian energy oracle."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np


LATTICE_CONSTANT = 7.0295868475
MOMENT = 4.2
DAMPING = 0.5
STEP_S = 0.1e-15
MEV_TO_TESLA = 1.602176634e-22 / (MOMENT * 9.274e-24)
GAMMA = 1.76e11


def cartesian_pairs(rows, nx, ny, boundary):
    # Integer Cartesian coordinates in units a/2 and sqrt(3)*a/2.
    sites = [(2 * i + j % 2, j) for i in range(nx) for j in range(ny)]
    index = {site: n for n, site in enumerate(sites)}
    neighbours = np.full((len(sites), len(rows)), -1, dtype=int)
    matrices = []
    dmi = []
    for k, row in enumerate(rows):
        r1, r2, r3 = (int(row[f"R{i}"]) for i in (1, 2, 3))
        assert r3 == 0
        dx, dy = 2 * r1 - r2, r2
        for i, (x, y) in enumerate(sites):
            xx, yy = x + dx, y + dy
            if boundary[0] == "periodic":
                xx %= 2 * nx
            if boundary[1] == "periodic":
                yy %= ny
            neighbours[i, k] = index.get((xx, yy), -1)
        matrix = np.array([[float(row[f"Jani_{x}{y}_meV"]) for y in "xyz"] for x in "xyz"])
        matrices.append(matrix + np.eye(3) * float(row["Jiso_meV"]))
        dmi.append([float(row[f"D{x}_meV"]) for x in "xyz"])
    origins, bonds = np.nonzero(neighbours >= 0)
    pairs = (origins, neighbours[origins, bonds], np.array(matrices)[bonds], np.array(dmi)[bonds])
    return neighbours, pairs


def energy_field(spins, pairs, onsite):
    # Use the raw TB2J directed-pair energy and differentiate both endpoints.
    # There is no factor 2 in this independent oracle.
    i, j, matrix, dmi = pairs
    left, right = spins[i], spins[j]
    interaction = np.einsum("pij,pj->pi", matrix, right)
    energy = -np.einsum("pi,pi->", left, interaction)
    energy -= np.einsum("pi,pi->", dmi, np.cross(left, right))
    energy -= onsite * np.dot(spins[:, 2], spins[:, 2])
    field = np.zeros_like(spins)
    np.add.at(field, i, interaction + np.cross(right, dmi))
    np.add.at(field, j, np.einsum("pij,pi->pj", matrix, left) + np.cross(dmi, left))
    field[:, 2] += 2 * onsite * spins[:, 2]
    return energy, field


def unit(spins):
    return spins / np.linalg.norm(spins, axis=1, keepdims=True)


def heun(spins, pairs, onsite):
    def derivative(state):
        _, field = energy_field(state, pairs, onsite)
        precession = np.cross(state, field * MEV_TO_TESLA)
        damping = np.cross(state, precession)
        return -GAMMA * (precession + DAMPING * damping) / (1 + DAMPING**2)

    first = derivative(spins)
    predictor = unit(spins + STEP_S * first)
    return unit(spins + 0.5 * STEP_S * (first + derivative(predictor)))


def write_config(path, bonds, nx, ny, boundary, onsite):
    settings = {
        "Nx": nx,
        "Ny": ny,
        "engine": "llg",
        "boundary_x": boundary[0],
        "boundary_y": boundary[1],
        "temperature_start_K": 0,
        "temperature_end_K": 0,
        "temperature_count": 1,
        "field_start_T": 0,
        "electric_start": 0,
        "write_png": "false",
        "reuse_states": "false",
        "lattice_constant_angstrom": LATTICE_CONSTANT,
        "moment_muB": MOMENT,
        "damping": DAMPING,
        "dt_fs": 0.1,
        "K_meV": onsite,
        "tb2j_bonds": bonds,
    }
    path.write_text("".join(f"{name} = {value}\n" for name, value in settings.items()), encoding="utf-8")


def invoke(binary, config, spins, destination):
    return subprocess.run(
        [str(binary), "--config", str(config), "--check-model", "--ground-state", str(spins),
         "--steps", "1", "--no-thermal-noise", "--threads", "2", "--output", str(destination)],
        cwd=config.parent, capture_output=True, encoding="utf-8", errors="replace", timeout=20,
    )


def validate_cases(binary, bonds, rows, root):
    rng = np.random.default_rng(47031)
    nx, ny = 9, 10
    spins = unit(rng.normal(size=(nx * ny, 3)))
    perturbation = unit(rng.normal(size=spins.shape))
    state_file = root / "state.txt"
    np.savetxt(state_file, spins, fmt="%.17g")
    errors = dict(energy=0.0, field=0.0, step=0.0, finite_difference=0.0)
    for ix, boundary in enumerate((
        ("open", "open"), ("periodic", "periodic"), ("open", "periodic"), ("periodic", "open"),
    )):
        onsite = 0.0 if ix == 0 else -0.27
        neighbours, pairs = cartesian_pairs(rows, nx, ny, boundary)
        energy, field = energy_field(spins, pairs, onsite)
        expected_final = heun(spins, pairs, onsite)
        final_energy, _ = energy_field(expected_final, pairs, onsite)
        h = 1e-3
        plus, _ = energy_field(spins + h * perturbation, pairs, onsite)
        minus, _ = energy_field(spins - h * perturbation, pairs, onsite)
        finite_difference = (plus - minus) / (2 * h)
        config, destination = root / f"case-{ix}.ini", root / f"probe-{ix}"
        write_config(config, bonds, nx, ny, boundary, onsite)
        result = invoke(binary, config, state_file, destination)
        assert result.returncode == 0, result.stdout + result.stderr
        actual_neighbours = np.loadtxt(destination / "tb2j_neighbours.txt", dtype=int)
        assert np.array_equal(actual_neighbours, neighbours), f"Wrong neighbours for {boundary}"
        actual_field = np.loadtxt(destination / "field_meV.txt")
        actual_final = np.loadtxt(destination / "final_state.txt")
        info = dict(line.split() for line in (destination / "probe.txt").read_text().splitlines())
        errors["energy"] = max(errors["energy"], abs(float(info["initial_energy_meV"]) - energy),
                               abs(float(info["final_energy_meV"]) - final_energy))
        errors["field"] = max(errors["field"], np.max(np.abs(actual_field - field)))
        errors["step"] = max(errors["step"], np.max(np.abs(actual_final - expected_final)))
        errors["finite_difference"] = max(errors["finite_difference"],
                                          abs(finite_difference + np.sum(actual_field * perturbation)))
    assert errors["energy"] < 1e-10, errors
    assert errors["field"] < 1e-11, errors
    assert errors["step"] < 1e-12, errors
    assert errors["finite_difference"] < 1e-8, errors
    print("PASS: Cartesian neighbours, energy, field and one Heun step for all four boundary combinations")
    print("Maximum errors: " + ", ".join(f"{key}={value:.3g}" for key, value in errors.items()))
    return state_file


def validate_rejections(binary, rows, root, state_file):
    invalid_cases = (
        (rows[1:], "Missing reverse TB2J bond"),
        ([dict(rows[0], Dx_meV="0"), *rows[1:]], "Inconsistent reverse DMI"),
        ([dict(rows[0], R3="1"), *rows[1:]], "nonzero in-plane translations"),
        ([dict(rows[0], Jiso_meV="nan"), *rows[1:]], "invalid numeric value"),
    )
    for n, (invalid, message) in enumerate(invalid_cases):
        path, config = root / f"invalid-{n}.csv", root / f"invalid-{n}.ini"
        with path.open("w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(invalid)
        write_config(config, path.name, 9, 10, ("open", "open"), 0.0)
        result = invoke(binary, config, state_file, root / f"invalid-probe-{n}")
        assert result.returncode != 0 and message in result.stdout + result.stderr, result.stdout + result.stderr
    print(f"PASS: {len(invalid_cases)} malformed or unsupported CSV inputs rejected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("bonds_csv", type=Path)
    args = parser.parse_args()
    binary, source = args.binary.resolve(), args.bonds_csv.resolve()
    with source.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert {(row["i"], row["j"]) for row in rows} == {("Mn1", "Mn1")}
    shell_counts = Counter(round(float(row["distance_angstrom"]) ** 2 / LATTICE_CONSTANT**2) for row in rows)
    assert shell_counts == {1: 6, 3: 6, 4: 6, 7: 12, 9: 6, 12: 6}, shell_counts
    with TemporaryDirectory(prefix="tb2j-llg-validation-") as temporary:
        root = Path(temporary)
        bonds = root / "bonds.csv"
        bonds.write_bytes(source.read_bytes())
        state_file = validate_cases(binary, bonds.name, rows, root)
        validate_rejections(binary, rows, root, state_file)


if __name__ == "__main__":
    main()
