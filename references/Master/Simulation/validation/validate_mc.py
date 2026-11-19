"""核对 MC 的三壳层并行着色、Metropolis 更新、接受率、目录与配置优先级。"""
import argparse
import csv
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_nanoribbon import write_config
from validate_workflows import geometry_oracle


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
    import spin_simulation as original
    from dataclasses import replace

    def invoke(config, *flags, success=True, environment=None):
        env = dict(os.environ, OMP_NUM_THREADS="2", OMP_DYNAMIC="FALSE")
        env.pop("PBS_NODEFILE", None)
        if environment:
            env.update(environment)
        result = subprocess.run([binary, "--config", str(config), *map(str, flags)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert (result.returncode == 0) == success, result.stdout.decode("utf-8", errors="replace")
        return result.stdout.decode("utf-8", errors="replace")

    rng = np.random.default_rng(171019)
    maximum = 0.0
    with TemporaryDirectory(prefix="mc-validation-") as temporary:
        root = Path(temporary)
        config = root / "case.ini"
        layouts = ((9, 5, False, False), (8, 8, True, True), (7, 6, True, False),
                   (7, 6, False, True), (6, 6, True, True))
        for nx, ny, px, py_periodic in layouts:
            lattice = geometry_oracle(py, nx, ny, px, py_periodic)
            initial = py.normalize(rng.normal(size=lattice.shape))
            initial_file = root / "initial.txt"
            np.savetxt(str(initial_file), initial.reshape(-1, 3))
            for dmi in ("bloch", "neel"):
                material = replace(py.MATERIAL, lambda_meV=0.13, Kxy_meV=0.2, Kxz_meV=-0.3, dmi_type=dmi)
                write_config(config, engine="mc", Nx=nx, Ny=ny, boundary_x="periodic" if px else "open",
                             boundary_y="periodic" if py_periodic else "open", dmi_type=dmi,
                             initial_state=str(initial_file), temperature_start_K=25, temperature_end_K=25,
                             field_start_T=0.6, field_end_T=0.6, electric_start=2, electric_end=4, electric_count=3,
                             equilibration_sweeps=2, measurement_sweeps=4, proposal_sigma=0.3)
                output = root / "probe"
                invoke(config, "--check-model", "--output", output)
                sites = np.loadtxt(str(output / "sites.txt"), dtype=int)
                offsets = np.loadtxt(str(output / "offsets.txt"), dtype=int)
                colours = np.loadtxt(str(output / "colours.txt"), dtype=int)
                neighbours = np.loadtxt(str(output / "neighbours.txt"), dtype=int)
                for site, near in enumerate(neighbours):
                    assert not np.any(colours[near[near >= 0]] == colours[site])
                assert np.array_equal(np.sort(sites), np.arange(lattice.sites))
                groups = len(offsets) - 1
                normal = rng.normal(size=(6, lattice.sites, 3))
                uniform = rng.random(size=(6, lattice.sites))
                orders = np.array([rng.permutation(groups) for _ in range(6)])
                np.savetxt(str(root / "normal.txt"), normal.reshape(-1, 3))
                np.savetxt(str(root / "uniform.txt"), uniform.ravel())
                np.savetxt(str(root / "orders.txt"), orders, fmt="%d")
                expected = initial.copy()
                rates = []
                # 独立逐格点实现：直接比较整套哈密顿量的前后能量，而非复用 C++ 局域差公式。
                for sweep in range(6):
                    accepted = 0
                    for colour in orders[sweep]:
                        for site in sites[offsets[colour]:offsets[colour + 1]]:
                            proposal = py.normalize(expected.reshape(-1, 3)[site] + 0.3 * normal[sweep, site])
                            candidate = expected.copy()
                            candidate.reshape(-1, 3)[site] = proposal
                            delta = (py.hamiltonian_energy(candidate, lattice, material, 0.6, 0.0)
                                     - py.hamiltonian_energy(expected, lattice, material, 0.6, 0.0)) * original.MEV_TO_K
                            if delta <= 0 or uniform[sweep, site] < np.exp(-delta / 25):
                                expected = candidate
                                accepted += 1
                    rates.append(accepted / lattice.sites)
                previous = None
                for threads in (1, 2):
                    invoke(config, "--check-model", "--output", output, "--threads", threads,
                           "--noise-file", root / "normal.txt", "--uniform-file", root / "uniform.txt",
                           "--orders-file", root / "orders.txt")
                    actual = np.loadtxt(str(output / "final_state.txt")).reshape(lattice.shape)
                    error = float(np.max(np.abs(actual - expected)))
                    maximum = max(maximum, error)
                    assert error < 2e-12, (nx, ny, px, py_periodic, dmi, error)
                    info = dict(line.split() for line in (output / "probe.txt").read_text().splitlines())
                    assert abs(float(info["acceptance"]) - np.mean(rates[2:])) < 1e-14
                    assert abs(float(info["initial_energy_meV"]) - py.hamiltonian_energy(initial, lattice, material, 0.6, 0)) < 2e-10
                    assert np.max(np.abs(np.linalg.norm(actual, axis=-1) - 1)) < 1e-14
                    if previous is not None:
                        assert np.array_equal(previous, actual)
                    previous = actual
        print("PASS: 10 MC physical cases, all boundaries, fast/greedy colours, serial full-energy oracle, 1/2 threads", flush=True)
        print("Max MC spin error {:.3e}; measurement acceptance excludes equilibration".format(maximum), flush=True)

        # 生产路径与方法隔离：4 个 T/B 场点；MC 的非零电场设置被明确忽略。
        output = root / "production"
        write_config(config, engine="mc", output_dir=str(output), temperature_start_K=20, temperature_end_K=10,
                     temperature_count=2, field_start_T=0, field_end_T=1, field_count=2,
                     electric_start=1, electric_end=2, electric_count=3, dt_fs=0, damping=-1,
                     equilibration_sweeps=2, measurement_sweeps=3, proposal_sigma=0.4)
        log = invoke(config)
        directory = output / py.MATERIAL.name / "mc" / "band" / "temperature_magnetic" / "Nx9_Ny5_Xopen_Yopen"
        saved = rows(directory)
        assert len(saved) == 4 and "MC 电场" in log
        assert all(row["unit"] == "sweeps" and int(row["steps"]) == 5 and float(row["Ez"]) == 0 for row in saved)
        assert all(0 <= float(row["acceptance"]) <= 1 for row in saved)
        assert not (output / py.MATERIAL.name / "llg").exists()
        invoke(config)
        assert all(row["status"] == "reused_state" and int(row["steps"]) == 0 and row["acceptance"] == "" for row in rows(directory))
        invoke(config, "--no-reuse")
        assert all(row["status"] == "completed" for row in rows(directory))
        # 两方向周期的结果不进入 band。
        invoke(config, "--length", 8, "--width", 6, "--boundary-x", "periodic", "--boundary-y", "periodic")
        assert (output / py.MATERIAL.name / "mc" / "temperature_magnetic" / "Nx8_Ny6_Xperiodic_Yperiodic" / "summary.csv").is_file()
        print("PASS: MC production scans, acceptance, ignored electric/LLG settings, cache, engine and band layout", flush=True)

        # 参数优先级：CLI > INI；有效分组独立；--steps/llg_steps/时间预算关系。
        write_config(config, engine="mc", temperature_start_K=10, temperature_end_K=10, cpu_threads=1,
                     equilibration_sweeps=0, measurement_sweeps=2)
        log = invoke(config, "--engine", "llg", "--temperature", 0, "--steps", 3, "--dry-run")
        assert "[LLG]" in log and "3 steps/point" in log
        invoke(config, "--temperature", 0, "--dry-run", success=False)
        invoke(config, "--steps", 3, "--dry-run", success=False)
        invoke(config, "--measurement-sweeps", 0, "--dry-run", success=False)
        invoke(config, "--proposal-sigma", 0, "--dry-run", success=False)
        write_config(config, engine="llg", llg_steps=7, relaxation_ps=100,
                     measurement_sweeps=0, proposal_sigma=-1)
        assert "7 steps/point" in invoke(config, "--dry-run")
        assert "3 steps/point" in invoke(config, "--steps", 3, "--dry-run")
        assert "T=4 -> 4" in invoke(config, "--temperature", 2, "--temperature", 4, "--dry-run")
        assert "T=4 -> 5" in invoke(config, "--temperature", 2, "--temperature-sweep", 4, 5, 2, "--dry-run")
        assert "T=2 -> 2" in invoke(config, "--temperature-sweep", 4, 5, 2, "--temperature", 2, "--dry-run")
        write_config(config, engine="mc", initial_state="uniform", read_ground_state="true",
                     ground_state_file="missing.txt", temperature_start_K=10, temperature_end_K=10,
                     equilibration_sweeps=0, measurement_sweeps=1)
        invoke(config, "--dry-run", success=False)
        invoke(config, "--random", "--dry-run")
        invoke(config, "--random", "--uniform", "--dry-run", success=False)
        nodefile = root / "nodes"
        nodefile.write_text("node10\nnode10\n")
        write_config(config, engine="mc", cpu_threads=1, temperature_start_K=10, temperature_end_K=10,
                     equilibration_sweeps=0, measurement_sweeps=1)
        env = {"PBS_NODEFILE": str(nodefile)}
        assert "threads: 1/1" in invoke(config, "--dry-run", environment=env)
        assert "threads: 2/2" in invoke(config, "--threads", 2, "--dry-run", environment=env)
        invoke(config, "--threads", 3, "--dry-run", success=False, environment=env)
        print("PASS: engine/scan/budget/initial-state/thread priorities and invalid MC inputs", flush=True)
    print("All MC and priority checks passed.", flush=True)


if __name__ == "__main__":
    main()
