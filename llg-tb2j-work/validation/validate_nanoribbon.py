"""开发验证：C++ 开放纳米带对照先前的独立 Python 纳米带程序。

python validation/validate_nanoribbon.py --binary ./program/nanoribbon_cpu --python-dir ..
不参与生产运行；生产计算不依赖此文件或 Python 模拟核心。
"""
import argparse
import csv
import itertools
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np


def write_config(path, **extra):
    values = dict(Nx=9, Ny=5, boundary="open", engine="llg", initial_state="random",
                  write_png="false", save_text="true", cpu_threads=2,
                  temperature_start_K=0, temperature_end_K=0, temperature_count=1,
                  field_start_T=0.7, field_end_T=0.7, field_count=1,
                  electric_start=0.4, electric_end=0.4, electric_count=1,
                  lambda_meV=0.13, Kxy_meV=0.2, Kxz_meV=-0.3,
                  dt_fs=0.1, relaxation_ps=0.0065, log_interval_seconds=0.001,
                  checkpoint_interval_seconds=0.001)
    values.update(extra)
    path.write_text("\n".join("{} = {}".format(key, value) for key, value in values.items()) + "\n",
                    encoding="utf-8")
    return path


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="./program/nanoribbon_cpu")
    parser.add_argument("--python-dir", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    source = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(Path(args.python_dir).resolve()))
    import llg_nanoribbon as py
    from dataclasses import replace

    def invoke(config, *flags, **kwargs):
        env = dict(os.environ, OMP_NUM_THREADS="2", OMP_DYNAMIC="FALSE")
        env.pop("PBS_NODEFILE", None)
        env.update(kwargs.pop("env", {}))
        result = subprocess.run([binary, "--config", str(config), *map(str, flags)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        if result.returncode:
            raise AssertionError(result.stdout.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8", errors="replace")

    def rows(directory):
        with (directory / "summary.csv").open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    rng = np.random.default_rng(173)
    errors = dict(field=0.0, energy=0.0, state=0.0, charge=0.0)
    cases = 0
    with TemporaryDirectory(prefix="cpp-nanoribbon-validation-") as temporary:
        root = Path(temporary)
        config = root / "case.ini"
        for nx, ny in ((9, 5), (5, 8)):
            lattice = py.Nanoribbon(py.RibbonConfig(nx, ny))
            initial = py.normalize(rng.normal(size=lattice.shape))
            state_file = root / "initial.txt"
            np.savetxt(str(state_file), initial.reshape(-1, 3), fmt="%.17g")
            normals = rng.normal(size=(65, nx, ny, 3))
            noise_file = root / "noise.txt"
            np.savetxt(str(noise_file), normals.reshape(-1, 3), fmt="%.17g")
            for mode, temperature in itertools.product(("bloch", "neel"), (0.0, 125.0)):
                material = replace(py.MATERIAL, dmi_type=mode, lambda_meV=0.13, Kxy_meV=0.2, Kxz_meV=-0.3)
                active = py.LLGConfig(relaxation_ps=0.0065)
                expected_field = (py.effective_field(initial, lattice, material, 0.7, 0.4)
                                  * material.spin_moment_J_T / py.MEV_TO_J).reshape(-1, 3)
                expected_energy = py.hamiltonian_energy(initial, lattice, material, 0.7, 0.4)
                expected = initial.copy()
                sigma = py.noise_sigma(material, active, temperature)
                for step in range(65):
                    expected = py.heun_step(expected, lattice, material, active, 0.7, 0.4, normals[step] * sigma)
                write_config(config, Nx=nx, Ny=ny, dmi_type=mode, temperature_start_K=temperature,
                             temperature_end_K=temperature, initial_state=str(state_file))
                for kernel, threads in itertools.product(("optimized", "reference"), (1, 2)):
                    destination = root / "probe"
                    invoke(config, "--check-model", "--noise-file", noise_file, "--output", destination,
                           "--kernel", kernel, "--threads", threads)
                    actual_field = np.loadtxt(str(destination / "field_meV.txt"))
                    actual = np.loadtxt(str(destination / "final_state.txt")).reshape(lattice.shape)
                    info = dict(line.split() for line in (destination / "probe.txt").read_text().splitlines())
                    errors["field"] = max(errors["field"], float(np.max(np.abs(actual_field - expected_field))))
                    errors["energy"] = max(errors["energy"], abs(float(info["initial_energy_meV"]) - expected_energy))
                    errors["state"] = max(errors["state"], float(np.max(np.abs(actual - expected))))
                    errors["charge"] = max(errors["charge"], abs(float(info["initial_Q"]) - py.topological_charge(initial)))
                    assert np.max(np.abs(np.linalg.norm(actual, axis=-1) - 1)) < 1e-14
                    actual_neighbours = np.loadtxt(str(destination / "neighbours.txt"), dtype=int)
                    expected_neighbours = np.where(lattice.valid, lattice.neighbours, -1).reshape(18, -1).T
                    assert np.array_equal(actual_neighbours, expected_neighbours), "Boundary neighbour mismatch"
                cases += 1
        assert errors["field"] < 2e-12, errors
        assert errors["energy"] < 2e-10, errors
        assert errors["state"] < 2e-12, errors
        assert errors["charge"] < 2e-12, errors
        print("PASS: {} geometries/DMI/temperature cases, optimized/reference, 1/2 threads".format(cases), flush=True)
        print("Max errors: {}".format(errors), flush=True)

        # 真正生产入口：4 个磁场基底 + 8 个电场点，两种内核使用相同随机数。
        lattice = py.Nanoribbon(py.RibbonConfig(9, 5))
        initial = py.normalize(rng.normal(size=lattice.shape))
        state_file = root / "production_initial.txt"
        np.savetxt(str(state_file), initial.reshape(-1, 3))
        write_config(config, initial_state=str(state_file), temperature_start_K=7,
                     temperature_end_K=0, temperature_count=2, field_start_T=0.7, field_end_T=-0.3,
                     field_count=2, electric_start=0.4, electric_end=-0.2, electric_count=2)
        directories = []
        for kernel in ("optimized", "reference"):
            destination = root / kernel
            invoke(config, "--output", destination, "--kernel", kernel)
            directory = next(destination.rglob("summary.csv")).parent
            directories.append(directory)
            saved_rows = rows(directory)
            assert len(saved_rows) == 12
            expected_conditions = []
            for temperature in (7.0, 0.0):
                expected_conditions.extend((temperature, field, 0.0) for field in (-0.3, 0.7))
                expected_conditions.extend(itertools.product((temperature,), (-0.3, 0.7), (-0.2, 0.4)))
            assert [(float(r["T_K"]), float(r["B_T"]), float(r["Ez"])) for r in saved_rows] == expected_conditions
            assert len(list(directory.glob("T_*K_B_*T_Ez_*.txt"))) == 8
            final = np.loadtxt(str(directory / "final_state.txt"))
            assert np.array_equal(final, np.loadtxt(str(directory / saved_rows[-1]["snapshot"])))
            assert (directory / "checkpoint.txt").read_text().startswith("# point=12 iteration=65")
        for left, right in zip(rows(directories[0]), rows(directories[1])):
            a = np.loadtxt(str(directories[0] / left["snapshot"]))
            b = np.loadtxt(str(directories[1] / right["snapshot"]))
            assert np.max(np.abs(a - b)) < 2e-12
        # T=0 的磁场基底和各自电场分支逐点对照 Python。
        invoke(config, "--output", root / "continuation", "--temperature", 0, "--steps", 3)
        directory = next((root / "continuation").rglob("summary.csv")).parent
        expected = initial.copy()
        bases = {}
        previous_field = None
        material = replace(py.MATERIAL, lambda_meV=0.13, Kxy_meV=0.2, Kxz_meV=-0.3)
        for row in rows(directory):
            field = float(row["B_T"])
            if row["phase"] == "electric_sweep" and previous_field != field:
                expected = bases[field].copy()
            for _ in range(3):
                expected = py.heun_step(expected, lattice, material, py.LLGConfig(),
                                        float(row["B_T"]), float(row["Ez"]), 0.0)
            actual = np.loadtxt(str(directory / row["snapshot"])).reshape(lattice.shape)
            assert np.max(np.abs(actual - expected)) < 2e-12
            if row["phase"] == "magnetic_base":
                bases[field] = expected.copy()
                previous_field = None
            else:
                previous_field = field
        print("PASS: real three-field sweep, sorted magnetic/electric branches, independent bases, checkpoints", flush=True)

        # 矩形 NPY 的大小端与 C/Fortran 顺序。Fortran 展开依赖不同的 Nx/Ny。
        for dtype, fortran, flatten in itertools.product(("<f8", ">f8", "<f4", ">f4"), (False, True), (False, True)):
            data = (initial.reshape(-1, 3) if flatten else initial).astype(dtype)
            data = np.asfortranarray(data) if fortran else np.ascontiguousarray(data)
            path = root / "initial.npy"
            np.save(str(path), data)
            write_config(config, initial_state=str(path))
            destination = root / "npy_probe"
            invoke(config, "--check-model", "--output", destination, "--steps", 1)
            wanted = py.normalize(data.astype(np.float64).reshape(lattice.shape))
            wanted = py.heun_step(wanted, lattice, material, py.LLGConfig(), 0.7, 0.4, 0.0)
            actual = np.loadtxt(str(destination / "final_state.txt")).reshape(lattice.shape)
            assert np.max(np.abs(actual - wanted)) < 2e-12, (dtype, fortran, flatten)
        print("PASS: 16 rectangular NPY formats (C/Fortran, flat/3D, both endiannesses, f32/f64)", flush=True)

        # 实际 PNG 与无需积分的补画，绘图环境可以是当前 Python 或已有 python3.7。
        write_config(config, write_png="true", python_executable=sys.executable,
                     plot_script=str(source / "render_snapshot.py"), Nx=81, Ny=41,
                     initial_state="skyrmion", Kxy_meV=0, Kxz_meV=0, lambda_meV=0,
                     field_start_T=1, field_end_T=1, electric_start=0, electric_end=0,
                     relaxation_ps=0.0001)
        destination = root / "png"
        invoke(config, "--output", destination)
        directory = next(destination.rglob("summary.csv")).parent
        assert len(list(directory.glob("T_*K_B_*T_Ez_*.png"))) == 1
        seed = np.loadtxt(str(directory / "initial_state.txt")).reshape(81, 41, 3)
        wanted = py.skyrmion_state(py.Nanoribbon(py.RibbonConfig(81, 41)), py.MATERIAL)
        assert np.max(np.abs(seed - wanted)) < 2e-14
        assert abs(float(rows(directory)[0]["Q"]) + 1.0) < 1e-5
        image = next(directory.glob("T_*K_B_*T_Ez_*.png"))
        image.unlink()
        plotted = subprocess.run([sys.executable, str(source / "plot_results.py"), str(directory)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert plotted.returncode == 0, plotted.stdout
        assert image.is_file()
        invoke(config, "--ground-state", directory / "checkpoint.txt", "--dry-run")
        invoke(config, "--ground-state", directory / "final_state.txt", "--dry-run")
        write_config(config, save_text="false", write_png="true", python_executable=sys.executable,
                     plot_script=str(source / "render_snapshot.py"), relaxation_ps=0.0001)
        invoke(config, "--output", root / "png_only")
        png_directory = next((root / "png_only").rglob("summary.csv")).parent
        assert len(list(png_directory.glob("T_*K_B_*T_Ez_*.png"))) == 1
        assert not list(png_directory.glob("T_*K_B_*T_Ez_*.txt"))
        assert not (png_directory / "final_state.txt").exists()
        print("PASS: skyrmion seed, Q, real PNG, PNG-only, checkpoint/TXT reload", flush=True)

        write_config(config)
        no_output = root / "no_output"
        invoke(config, "--output", no_output, "--dry-run")
        assert not no_output.exists()
        for flags in (("--width", "2"), ("--temperature", "-1"), ("--dt-fs", "0"),
                      ("--field-sweep", "0", "1", "2.5"), ("--threads", "-1"),
                      ("--electric-sweep", "0", "1", "1"), ("--field", "nan")):
            result = subprocess.run([binary, "--config", str(config), *flags, "--dry-run"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            assert result.returncode != 0, flags
        for bad in (np.zeros((9, 5, 3)), np.ones((9, 6, 3)), np.full((9, 5, 3), np.nan)):
            path = root / "bad.npy"
            np.save(str(path), bad)
            result = subprocess.run([binary, "--config", str(config), "--ground-state", str(path), "--dry-run"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            assert result.returncode != 0
        write_config(config, boundary="periodic")
        result = subprocess.run([binary, "--config", str(config), "--dry-run"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert result.returncode != 0
        write_config(config)
        nodefile = root / "nodes"
        nodefile.write_text("node10\nnode10\n")
        invoke(config, "--threads", 2, "--dry-run", env={"PBS_NODEFILE": str(nodefile)})
        for text, threads in (("node10\nnode10\n", 3), ("node10\nnode11\n", 2), ("", 2)):
            nodefile.write_text(text)
            env = dict(os.environ, PBS_NODEFILE=str(nodefile))
            result = subprocess.run([binary, "--config", str(config), "--threads", str(threads), "--dry-run"],
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            assert result.returncode != 0
        print("PASS: dry-run has no outputs; invalid dimensions, fields, states, boundaries and PBS allocations rejected", flush=True)
    for path in [*source.glob("*.sh"), *source.glob("*.pbs")]:
        assert b"\r" not in path.read_bytes(), "Shell scripts must use LF"
    print("All C++ nanoribbon checks passed.", flush=True)


if __name__ == "__main__":
    main()
