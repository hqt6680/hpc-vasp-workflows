"""验证原 Python 图像逐像素一致性，以及历史构型批量重绘和数据保护。"""
import argparse
import csv
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from matplotlib.image import imread
from matplotlib.quiver import Quiver

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render_snapshot
import replot_existing


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-dir", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.python_dir).resolve()))
    import spin_simulation as original
    import llg_nanoribbon as ribbon

    rng = np.random.default_rng(1710)
    with TemporaryDirectory(prefix="plot-validation-") as temporary:
        root = Path(temporary)
        square = original.HexagonalLattice(original.LatticeConfig(L=16, boundary="open"))
        spins = original.normalize(rng.normal(size=(16, 16, 3)))
        state = root / "state.npy"
        np.save(str(state), spins)
        original.plot_spins(spins, square, root / "original.png", 0.1, -0.7, 0.3)
        render_snapshot.render(state, root / "new.png", 16, 16, 0.1, -0.7, 0.3)
        assert np.array_equal(imread(str(root / "original.png")), imread(str(root / "new.png")))
        lattice = ribbon.Nanoribbon(ribbon.RibbonConfig(16, 16))
        ribbon.plot_spins(spins, lattice, root / "python_ribbon.png", 0.1, -0.7, 0.3, 0.0)
        assert np.array_equal(imread(str(root / "original.png")), imread(str(root / "python_ribbon.png")))
        rectangular = original.normalize(rng.normal(size=(132, 7, 3)))
        figure = render_snapshot.build_figure(rectangular, 0.1, 1.0, 0.0)
        ax = figure.axes[0]
        assert len(ax.collections) == 1 and isinstance(ax.collections[0], Quiver)
        quiver = ax.collections[0]
        assert len(quiver.U) == 132 * 7
        assert np.array_equal(quiver.get_array(), rectangular[..., 2].ravel())
        assert quiver.get_clim() == (-1, 1)
        assert quiver.width == 0.004 and quiver.scale == 30
        assert ax.get_aspect() == 1
        figure.clear()
        print("PASS: square PNG matches original Python pixel-for-pixel; all rectangular sites use colored quiver", flush=True)

        fixtures = root / "results"
        paths = []

        def save(relative, shape, npy=False):
            path = fixtures / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = original.normalize(rng.normal(size=shape))
            if npy:
                np.save(str(path), data)
            else:
                np.savetxt(str(path), data.reshape(-1, 3))
            paths.append(path)
            return path

        save("new/Nx12_Ny6_Xopen_Yperiodic/llg/magnetic_relaxation/"
             "Nx12_Ny6_Xopen_Yperiodic_magnetic_relaxation_T_2K_B_0.7T_Ez_0.txt", (12, 6, 3))
        save("layout_v2/MnInP2Te6/llg/temperature/Nx10_Ny6_Xperiodic_Yperiodic/"
             "T_0.1K_B_0T_Ez_0.txt", (10, 6, 3))
        mc_state = save("layout_v2/MnInP2Te6/mc/band/magnetic/Nx9_Ny5_Xopen_Yopen/"
                        "T_10K_B_0.7T_Ez_0.txt", (9, 5, 3))
        mc_meta = replot_existing.filename_settings(mc_state)
        assert mc_meta == dict(engine="mc", length=9, width=5, boundary_x="open", boundary_y="open",
                               temperature=10.0, field=0.7, electric=0.0)
        save("old_cpp/Nx12_Ny6/llg/magnetic/point_000001_T_2K_B_0.7T_Ez_0.txt", (12, 6, 3))
        legacy = save("legacy/temperature/5.0000K.txt", (8, 8, 3))
        (legacy.parent / "run_settings.ini").write_text("L=8\nboundary=periodic\nengine=llg\n", encoding="utf-8")
        orphan = save("orphan/saved_configuration.txt", (9, 5, 3))
        (orphan.parent / "run_settings.ini").write_text("Nx=9\nNy=5\n", encoding="utf-8")
        with (orphan.parent / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["temperature_K", "Bz_T", "Ez", "snapshot"])
            writer.writerow([3, 0.2, -0.1, "C:\\old_server\\saved_configuration.txt"])
        save("no_metadata/T_4K_B_0T_Ez_0.npy", (9, 5, 3), True)
        json_state = save("json_case/cached.npy", (14, 5, 3), True)
        (json_state.parent / "run_config.json").write_text(json.dumps(dict(
            ribbon=dict(length=14, width=5), temperatures_K=[6], magnetic_fields_T=[-0.2],
            electric_fields=[0.3])), encoding="utf-8")
        helper = legacy.parent / "final_state.txt"
        helper.write_bytes(legacy.read_bytes())
        hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths + [helper]}
        before = {path.with_suffix(".png"): b"old picture" for path in paths}
        for path, data in before.items():
            path.write_bytes(data)
        with redirect_stdout(io.StringIO()):
            assert replot_existing.main([str(fixtures), "--dry-run"]) == 0
        assert not (fixtures / "replotted").exists()
        with redirect_stdout(io.StringIO()):
            assert replot_existing.main([str(fixtures)]) == 0
        pictures = list((fixtures / "replotted").rglob("*.png"))
        assert len(pictures) == len(paths)
        assert all(path.read_bytes() == data for path, data in before.items())
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in hashes.items())
        fingerprints = {path: path.read_bytes() for path in pictures}
        with redirect_stdout(io.StringIO()):
            assert replot_existing.main([str(fixtures)]) == 0
        assert all(path.read_bytes() == data for path, data in fingerprints.items())
        with redirect_stdout(io.StringIO()):
            assert replot_existing.main([str(fixtures), "--in-place"]) == 0
        assert all(path.read_bytes().startswith(b"\x89PNG") for path in before)
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in hashes.items())
        print("PASS: recursive new/legacy names, summary/config metadata, NPY dimensions, dry-run, copy and overwrite; source data unchanged", flush=True)

        ambiguous = root / "ambiguous.txt"
        np.savetxt(str(ambiguous), original.normalize(rng.normal(size=(18, 8, 3))).reshape(-1, 3))
        with redirect_stdout(io.StringIO()):
            assert replot_existing.main([str(ambiguous)]) == 1
            assert replot_existing.main([str(ambiguous), "--length", "18", "--width", "8",
                                         "--temperature", "0.1", "--field", "1", "--electric", "0"]) == 0
        invalid = root / "invalid.npy"
        np.save(str(invalid), np.zeros((6, 4, 3)))
        old = invalid.with_suffix(".png")
        old.write_bytes(b"preserve on failure")
        with redirect_stdout(io.StringIO()):
            assert replot_existing.main([str(invalid), "--in-place", "--temperature", "0",
                                         "--field", "0", "--electric", "0"]) == 1
        assert old.read_bytes() == b"preserve on failure"
        print("PASS: ambiguous flat TXT requires dimensions; bad data cannot replace an existing PNG", flush=True)
    print("All plotting checks passed.", flush=True)


if __name__ == "__main__":
    main()
