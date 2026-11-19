"""验证所有方法/场类型的尺寸目录、边界隔离、相对路径及上一版缓存兼容。"""
import argparse
import csv
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="./program/nanoribbon_cpu")
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    env = dict(os.environ, OMP_NUM_THREADS="2", OMP_DYNAMIC="FALSE")
    env.pop("PBS_NODEFILE", None)

    with TemporaryDirectory(prefix="layout-validation-") as temporary:
        root = Path(temporary)
        config = root / "case.ini"

        def invoke(output, engine="llg", bx="open", by="open", flags=(), success=True, **updates):
            settings = dict(engine=engine, Nx=9, Ny=6, boundary_x=bx, boundary_y=by, cpu_threads=2,
                            initial_state="uniform", temperature_start_K=10 if engine == "mc" else 0,
                            temperature_end_K=10 if engine == "mc" else 0, temperature_count=1,
                            field_start_T=0, field_end_T=0, field_count=1,
                            electric_start=0, electric_end=0, electric_count=1,
                            thermal_noise="false", llg_steps=2, equilibration_sweeps=0,
                            measurement_sweeps=2, proposal_sigma=0.4, Kxy_meV=0.17, Kxz_meV=-0.2,
                            write_png="false", output_dir=str(output))
            settings.update(updates)
            config.write_text("".join("{} = {}\n".format(k, v) for k, v in settings.items()), encoding="utf-8")
            result = subprocess.run([binary, "--config", str(config), *map(str, flags)], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log = result.stdout.decode("utf-8", errors="replace")
            assert (result.returncode == 0) == success, log
            return log

        def geom(bx, by, nx=9, ny=6):
            return "Nx{}_Ny{}_X{}_Y{}".format(nx, ny, bx, by)

        def category(output, engine, bx, by, kind):
            path = output / "MnInP2Te6" / engine
            return path / "band" / kind if "open" in (bx, by) else path / kind

        def rows(directory):
            with (directory / "summary.csv").open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))

        cases = [("llg", "temperature", {}), ("llg", "magnetic", dict(field_start_T=1, field_end_T=1)),
                 ("llg", "electric", dict(electric_start=0.2, electric_end=0.2)),
                 ("llg", "magnetic_electric", dict(field_start_T=1, field_end_T=1, electric_start=0.2, electric_end=0.2)),
                 ("llg", "temperature_magnetic", dict(temperature_end_K=0.1, temperature_count=2, field_start_T=1, field_end_T=1)),
                 ("llg", "temperature_electric", dict(temperature_end_K=0.1, temperature_count=2, electric_start=0.2, electric_end=0.2)),
                 ("llg", "temperature_magnetic_electric", dict(temperature_end_K=0.1, temperature_count=2,
                    field_start_T=1, field_end_T=1, electric_start=0.2, electric_end=0.2)),
                 ("mc", "temperature", {}), ("mc", "magnetic", dict(field_start_T=1, field_end_T=1)),
                 ("mc", "temperature_magnetic", dict(temperature_start_K=20, temperature_count=2, field_start_T=1, field_end_T=1))]
        boundaries = [("open", "open"), ("periodic", "open"), ("open", "periodic"), ("periodic", "periodic")]
        output = root / "all_modes"
        verified = []
        for bx, by in boundaries:
            for engine, kind, settings in cases:
                invoke(output, engine, bx, by, **settings)
                parent = category(output, engine, bx, by, kind)
                directory = parent / geom(bx, by)
                saved = rows(directory)
                assert saved and not (parent / "summary.csv").exists()
                for row in saved:
                    snapshot = (directory / row["snapshot"]).resolve()
                    assert snapshot.is_file(), row
                    assert snapshot.name.startswith("T_") and "Nx" not in snapshot.name and "relaxation" not in snapshot.name
                assert not list(directory.glob("Nx*"))
                verified.append(directory)
        # 同一分类下不同尺寸的运行记录和构型不能覆盖。
        protected = verified[0] / "run_settings.ini"
        before = protected.read_bytes()
        invoke(output, Nx=12, Ny=8)
        assert protected.read_bytes() == before
        assert (protected.parent.parent / "Nx12_Ny8_Xopen_Yopen" / "summary.csv").is_file()
        assert all(path.is_dir() for path in verified)
        print("PASS: 40 engine/category/boundary cases, field-only filenames, relative snapshot links and size isolation", flush=True)

        # 将已经计算的点布置成上一版扁平目录；新程序须直接读入且保持源文件不变。
        for engine in ("llg", "mc"):
            for bx, by in boundaries:
                output = root / ("legacy_" + engine + "_" + bx + "_" + by)
                settings = dict(field_start_T=1, field_end_T=1)
                invoke(output, engine, bx, by, **settings)
                parent = category(output, engine, bx, by, "magnetic")
                directory = parent / geom(bx, by)
                state = (directory / rows(directory)[0]["snapshot"]).resolve()
                legacy = parent / (geom(bx, by) + "_magnetic_relaxation_" + state.name)
                state.rename(legacy)
                digest = hashlib.sha256(legacy.read_bytes()).hexdigest()
                invoke(output, engine, bx, by, **settings)
                row = rows(directory)[0]
                assert row["status"] == "reused_state" and int(row["steps"]) == 0
                assert (directory / row["snapshot"]).resolve() == legacy.resolve()
                assert hashlib.sha256(legacy.read_bytes()).hexdigest() == digest and not state.exists()
                np.save(str(legacy.with_suffix(".npy")), np.loadtxt(str(legacy)).reshape(9, 6, 3))
                legacy.unlink()
                invoke(output, engine, bx, by, **settings)
                assert rows(directory)[0]["source"].endswith(".npy")
                # 新布局优先，即使旧布局还保留相同场点。
                np.savetxt(str(state), np.load(str(legacy.with_suffix(".npy"))).reshape(-1, 3))
                invoke(output, engine, bx, by, **settings)
                assert (directory / rows(directory)[0]["source"]).resolve() == state.resolve()
        print("PASS: previous-layout TXT/NPY caches read without recomputation or overwrite; new layout preferred", flush=True)

        # 老的纯磁场基底进入新的磁电分支；summary 跨两层目录的引用必须有效。
        output = root / "coupled_legacy"
        settings = dict(field_end_T=1, field_count=2)
        invoke(output, **settings)
        parent = category(output, "llg", "open", "open", "magnetic")
        directory = parent / geom("open", "open")
        for row in rows(directory):
            state = (directory / row["snapshot"]).resolve()
            state.rename(parent / (geom("open", "open") + "_magnetic_relaxation_" + state.name))
        settings.update(electric_start=0.1, electric_end=0.2, electric_count=2)
        invoke(output, **settings)
        directory = category(output, "llg", "open", "open", "magnetic_electric") / geom("open", "open")
        saved = rows(directory)
        assert len(saved) == 6 and all(row["status"] == "reused_state" for row in saved[:2])
        assert all((directory / row["snapshot"]).is_file() for row in saved)
        (directory / saved[-1]["snapshot"]).unlink()
        invoke(output, **settings)
        assert sum(row["status"] == "completed" for row in rows(directory)) == 1

        # auto 初态优先新尺寸目录；回退旧版时只接受明确带尺寸/边界的最终文件。
        output = root / "ground_auto"
        invoke(output)
        parent = category(output, "llg", "open", "open", "temperature")
        directory = parent / geom("open", "open")
        new = directory / "final_state.txt"
        legacy = parent / (geom("open", "open") + "_temperature_relaxation_final_state.txt")
        legacy.write_bytes(new.read_bytes())
        options = dict(read_ground_state="true", ground_state_file="auto", flags=("--dry-run",))
        log = invoke(output, **options)
        assert str(new).replace("\\", "/") in log.replace("\\", "/")
        new.unlink()
        log = invoke(output, **options)
        assert str(legacy).replace("\\", "/") in log.replace("\\", "/")
        legacy.rename(parent / "final_state.txt")
        invoke(output, success=False, **options)
        print("PASS: legacy magnetic bases, partial branch repair and new/legacy auto ground-state lookup", flush=True)
    print("All output-layout checks passed.", flush=True)


if __name__ == "__main__":
    main()
