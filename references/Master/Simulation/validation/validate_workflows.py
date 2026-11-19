"""验证四种 x/y 边界、几何近邻、输出命名和先读取后弛豫的耦合扫描。"""
import argparse
import csv
import hashlib
import itertools
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_nanoribbon import write_config


def geometry_oracle(py, nx, ny, px, py_periodic):
    """由真实坐标和物理键向量独立查表，不使用 C++ 的奇偶行偏移表。"""
    lattice = py.Nanoribbon(py.RibbonConfig(nx, ny))
    positions = lattice.coordinates.reshape(-1, 2)
    coordinates = {tuple(np.round(point, 10)): index for index, point in enumerate(positions)}
    root = np.sqrt(3.0)
    bonds = [py.BOND_DIRECTIONS[:, :2],
             np.array([[1.5, root / 2], [1.5, -root / 2], [0, root], [0, -root],
                       [-1.5, root / 2], [-1.5, -root / 2]]),
             np.array([[2, 0], [-2, 0], [1, root], [1, -root], [-1, root], [-1, -root]])]
    indices = np.zeros_like(lattice.neighbours)
    valid = np.zeros_like(lattice.valid)
    for shell, vectors in enumerate(bonds):
        for direction, vector in enumerate(vectors):
            for site, point in enumerate(positions):
                target = point + vector
                if px:
                    target[0] %= nx
                if py_periodic:
                    target[1] %= ny * root / 2
                    if abs(target[1] - ny * root / 2) < 1e-10:
                        target[1] = 0
                neighbour = coordinates.get(tuple(np.round(target, 10)))
                if neighbour is not None:
                    indices[shell, direction, site] = neighbour
                    valid[shell, direction, site] = 1
    lattice.neighbours, lattice.valid = indices, valid
    return lattice


def charge_oracle(spins, lattice):
    """遍历每个格点相邻键形成的三角形，每个物理三角形恰好出现三次。"""
    flat = spins.reshape(-1, 3)
    total = 0.0
    for site, a in enumerate(flat):
        for direction in range(6):
            following = (direction + 1) % 6
            if lattice.valid[0, direction, site] and lattice.valid[0, following, site]:
                b = flat[lattice.neighbours[0, direction, site]]
                c = flat[lattice.neighbours[0, following, site]]
                total += 2 * np.arctan2(np.dot(a, np.cross(b, c)),
                                       1 + np.dot(a, b) + np.dot(b, c) + np.dot(c, a))
    return total / (12 * np.pi)


def rows(directory):
    with (directory / "summary.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="./program/nanoribbon_cpu")
    parser.add_argument("--python-dir", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    sys.path.insert(0, str(Path(args.python_dir).resolve()))
    import llg_nanoribbon as py
    from dataclasses import replace

    def invoke(config, *flags, success=True):
        env = dict(os.environ, OMP_NUM_THREADS="2", OMP_DYNAMIC="FALSE")
        env.pop("PBS_NODEFILE", None)
        result = subprocess.run([binary, "--config", str(config), *map(str, flags)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert (result.returncode == 0) == success, result.stdout.decode("utf-8", errors="replace")
        return result.stdout.decode("utf-8", errors="replace")

    rng = np.random.default_rng(719)
    material = replace(py.MATERIAL, lambda_meV=0.13, Kxy_meV=0.2, Kxz_meV=-0.3)
    maximum = 0.0
    with TemporaryDirectory(prefix="ribbon-workflow-validation-") as temporary:
        root = Path(temporary)
        config = root / "case.ini"
        for px, py_periodic in itertools.product((False, True), repeat=2):
            nx, ny = 7, 6 if py_periodic else 5
            lattice = geometry_oracle(py, nx, ny, px, py_periodic)
            initial = py.normalize(rng.normal(size=lattice.shape))
            state_file = root / "initial.txt"
            np.savetxt(str(state_file), initial.reshape(-1, 3))
            normals = rng.normal(size=(65, nx, ny, 3))
            noise_file = root / "noise.txt"
            np.savetxt(str(noise_file), normals.reshape(-1, 3))
            for mode in ("bloch", "neel"):
                active_material = replace(material, dmi_type=mode)
                write_config(config, Nx=nx, Ny=ny, boundary_x="periodic" if px else "open",
                             boundary_y="periodic" if py_periodic else "open", dmi_type=mode,
                             initial_state=str(state_file), temperature_start_K=13, temperature_end_K=13)
                expected = initial.copy()
                active = py.LLGConfig(relaxation_ps=0.0065)
                sigma = py.noise_sigma(active_material, active, 13)
                for normal in normals:
                    expected = py.heun_step(expected, lattice, active_material, active, 0.7, 0.4, normal * sigma)
                for kernel in ("optimized", "reference"):
                    destination = root / "probe"
                    invoke(config, "--check-model", "--noise-file", noise_file, "--output", destination, "--kernel", kernel)
                    actual_neighbours = np.loadtxt(str(destination / "neighbours.txt"), dtype=int)
                    wanted = np.where(lattice.valid, lattice.neighbours, -1).reshape(18, -1).T
                    assert np.array_equal(actual_neighbours, wanted), (px, py_periodic)
                    # 三壳层所有有向键都须有互反键。
                    for site, neighbours in enumerate(wanted):
                        for shell in range(3):
                            for near in neighbours[shell * 6:(shell + 1) * 6]:
                                if near >= 0:
                                    assert site in wanted[near, shell * 6:(shell + 1) * 6]
                    actual = np.loadtxt(str(destination / "final_state.txt")).reshape(lattice.shape)
                    maximum = max(maximum, float(np.max(np.abs(actual - expected))))
                    assert maximum < 2e-12
                    info = dict(line.split() for line in (destination / "probe.txt").read_text().splitlines())
                    assert abs(float(info["initial_Q"]) - charge_oracle(initial, lattice)) < 2e-12
                    wanted_field = py.effective_field(initial, lattice, active_material, 0.7, 0.4)
                    wanted_field *= active_material.spin_moment_J_T / py.MEV_TO_J
                    assert np.max(np.abs(np.loadtxt(str(destination / "field_meV.txt")) - wanted_field.reshape(-1, 3))) < 2e-12
        write_config(config, Ny=5, boundary_y="periodic")
        invoke(config, "--dry-run", success=False)
        write_config(config)
        invoke(config, "--boundary-x", "closed", "--boundary-y", "closed", "--dry-run")
        print("PASS: four independent boundaries, geometry oracle, reciprocal bonds, Q and noisy Heun; error={:.3e}".format(maximum), flush=True)

        # 先跑纯磁场，随后加入电场：所有磁场基底必须复用，电场按独立分支演化。
        output = root / "cache"
        lattice = geometry_oracle(py, 9, 6, False, False)
        initial = py.normalize(rng.normal(size=lattice.shape))
        state_file = root / "workflow_initial.txt"
        np.savetxt(str(state_file), initial.reshape(-1, 3))
        options = dict(Nx=9, Ny=6, initial_state=str(state_file), field_start_T=1,
                       field_end_T=0, field_count=3, relaxation_ps=0.0003,
                       electric_start=0, electric_end=0, output_dir=str(output))
        write_config(config, **options)
        invoke(config)
        base_directory = next(output.rglob("summary.csv")).parent
        base_rows = rows(base_directory)
        bases = {float(row["B_T"]): np.loadtxt(str(base_directory / row["snapshot"])).reshape(lattice.shape)
                 for row in base_rows}
        base_files = {float(row["B_T"]): (base_directory / row["snapshot"]).resolve() for row in base_rows}
        before = {path: path.read_bytes() for path in base_files.values()}
        options.update(electric_start=0.2, electric_end=-0.2, electric_count=3)
        write_config(config, **options)
        invoke(config)
        directory = next(p.parent for p in output.rglob("summary.csv") if p.parent.parent.name == "magnetic_electric")
        saved = rows(directory)
        assert len(saved) == 12
        assert all(row["status"] == "reused_state" and int(row["steps"]) == 0 for row in saved[:3])
        assert all(row["status"] == "completed" for row in saved[3:])
        assert all(path.read_bytes() == data for path, data in before.items())
        for field in (0.0, 0.5, 1.0):
            expected = bases[field].copy()
            branch = [row for row in saved if row["phase"] == "electric_sweep" and float(row["B_T"]) == field]
            assert [float(row["Ez"]) for row in branch] == [-0.2, 0.0, 0.2]
            for row in branch:
                for _ in range(3):
                    expected = py.heun_step(expected, lattice, material, py.LLGConfig(), field, float(row["Ez"]), 0.0)
                actual = np.loadtxt(str(directory / row["snapshot"])).reshape(lattice.shape)
                assert np.max(np.abs(actual - expected)) < 2e-12
                name = Path(row["snapshot"]).name
                assert name.startswith("T_") and "Nx" not in name and "relaxation" not in name
        snapshots = {(directory / row["snapshot"]).resolve() for row in saved}
        fingerprints = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in snapshots}
        invoke(config)
        assert all(row["status"] == "reused_state" and int(row["steps"]) == 0 for row in rows(directory))
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in fingerprints.items())
        # 部分缺失：只补算一个磁场基底和一个电场场点。
        base_files[0.5].unlink()
        absent = (directory / saved[-1]["snapshot"]).resolve()
        absent.unlink()
        invoke(config)
        repaired = rows(directory)
        assert sum(row["status"] == "completed" for row in repaired) == 2
        assert sum(int(row["steps"]) == 3 for row in repaired) == 2
        # 已有磁场 NPY 也能读取，不需要 TXT；不会把无效 TXT 当作缺失静默重算。
        base = base_files[0.0]
        np.save(str(base.with_suffix(".npy")), np.asfortranarray(np.loadtxt(str(base)).reshape(lattice.shape)))
        base.unlink()
        invoke(config)
        assert rows(directory)[0]["source"].endswith(".npy")
        np.savetxt(str(base_files[0.5]), np.zeros((lattice.sites, 3)))
        invoke(config, success=False)
        print("PASS: pure-B reuse, independent electric branches, all/partial cache, NPY, no overwrite, invalid cache rejection", flush=True)

        # 不同边界隔离；PNG-only 所需的纯磁场临时构型在运行后清理。
        for flag, value in (("--boundary-x", "periodic"), ("--boundary-y", "periodic")):
            invoke(config, flag, value)
            geometry = "Nx9_Ny6_X{}_Y{}".format("periodic" if flag == "--boundary-x" else "open",
                                               "periodic" if flag == "--boundary-y" else "open")
            other = output / py.MATERIAL.name / "llg" / "band" / "magnetic_electric" / geometry
            assert all(row["status"] == "completed" for row in rows(other))
        options.update(save_text="false", output_dir=str(root / "temporary_bases"))
        write_config(config, **options)
        invoke(config)
        temporary_output = root / "temporary_bases"
        assert not list(temporary_output.rglob("*.tmp.txt"))
        assert not list(temporary_output.rglob("T_*K_B_*T_Ez_*.txt"))
        # 关闭复用时同条件明确重新弛豫。
        write_config(config, **dict(options, save_text="true", output_dir=str(root / "forced")))
        invoke(config)
        invoke(config, "--no-reuse")
        forced = next((root / "forced").rglob("summary.csv")).parent
        assert all(row["status"] == "completed" for row in rows(forced))
        print("PASS: boundary cache isolation, named outputs, temporary bases cleanup, forced relaxation", flush=True)
    print("All boundary/workflow checks passed.", flush=True)


if __name__ == "__main__":
    main()
