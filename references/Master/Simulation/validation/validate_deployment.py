"""验证完整目录版的真实 Bash 入口、编译、独立日志、result、PBS 工作目录和重绘路径。"""
import argparse
import csv
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bash", default="bash")
    parser.add_argument("--compiler", help="给定编译器时测试 run.sh 自动编译，否则使用已有二进制")
    parser.add_argument("--binary", type=Path, default=Path("./program/nanoribbon_cpu"))
    args = parser.parse_args()
    package = Path(__file__).resolve().parent.parent
    binary = args.binary.resolve()
    if not args.compiler and not binary.is_file():
        parser.error("请先 bash build.sh，或给定 --compiler")

    def shell_path(path):
        value = Path(path).resolve().as_posix()
        return "/" + value[0].lower() + value[2:] if os.name == "nt" and value[1:2] == ":" else value

    with TemporaryDirectory(prefix="ribbon-deployment-") as temporary:
        root = Path(temporary)
        stage = root / "release copy with spaces"
        stage.mkdir()
        for directory in ("program", "docs", "validation", "result"):
            (stage / directory).mkdir()
        for path in package.rglob("*"):
            relative = path.relative_to(package)
            if path.is_file() and "__pycache__" not in relative.parts and path.suffix in (".cpp", ".hpp", ".ini", ".sh", ".pbs", ".py", ".md"):
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(target))
        unrelated = root / "another working directory"
        unrelated.mkdir()
        env = dict(os.environ)
        for name in ("PBS_NODEFILE", "PBS_O_WORKDIR", "PBS_JOBID", "RIBBON_CONFIG", "RIBBON_ENGINE", "RIBBON_THREADS", "RIBBON_OUTPUT", "RIBBON_HOME", "BUILD_ON_NODE"):
            env.pop(name, None)
        env["OMP_NUM_THREADS"] = "2"
        if args.compiler:
            env["CXX"] = args.compiler
        else:
            shutil.copyfile(str(binary), str(stage / "program" / "nanoribbon_cpu"))
            os.chmod(str(stage / "program" / "nanoribbon_cpu"), 0o755)
        settings = dict(engine="llg", Nx=12, Ny=8, boundary_x="open", boundary_y="open",
                        cpu_threads=1, initial_state="uniform", temperature_start_K=10,
                        temperature_end_K=10, temperature_count=1, field_start_T=1, field_end_T=1,
                        field_count=1, electric_start=0, electric_end=0, electric_count=1,
                        llg_steps=3, thermal_noise="false", equilibration_sweeps=1,
                        measurement_sweeps=2, proposal_sigma=0.4, output_dir="result",
                        save_text="true", write_png="true", python_executable=Path(sys.executable).as_posix(),
                        plot_script="render_snapshot.py")
        (stage / "nanoribbon.ini").write_text("".join("{} = {}\n".format(k, v) for k, v in settings.items()), encoding="utf-8")

        def invoke(script, *flags, environment=None, success=True):
            current = env.copy()
            if environment:
                current.update(environment)
            before = {path: path.read_bytes() for path in stage.glob("*_master_*.out")}
            result = subprocess.run([args.bash, "--noprofile", "--norc", shell_path(script), *map(str, flags)],
                                    cwd=str(unrelated), env=current, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            changed = [path for path in stage.glob("*_master_*.out") if before.get(path) != path.read_bytes()]
            assert len(changed) <= 1
            log = changed[0].read_text(encoding="utf-8", errors="replace") if changed else ""
            assert (result.returncode == 0) == success, result.stdout.decode("utf-8", errors="replace") + "\n" + log
            return result, log

        def verify_output(engine, output="result"):
            directory = stage / output / "MnInP2Te6" / engine / "band" / "magnetic" / "Nx12_Ny8_Xopen_Yopen"
            with (directory / "summary.csv").open(newline="", encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            snapshot = (directory / row["snapshot"]).resolve()
            assert snapshot.is_file() and snapshot.with_suffix(".png").is_file()
            return directory

        result, first_log = invoke(stage / "run.sh")
        assert result.stdout == b"" and "[LLG]" in first_log
        assert "exit status: 0" in first_log
        if args.compiler:
            assert "Built:" in first_log
        verify_output("llg")
        first_file = next(stage.glob("nanoribbon_master_local_*.out"))
        first_bytes = first_file.read_bytes()
        assert (stage / "program" / "nanoribbon_cpu").is_file()
        assert not (stage / "nanoribbon_cpu").exists()
        assert not (stage / "program" / "result").exists() and not (stage / "program" / "master.out").exists()
        assert not (unrelated / "master.out").exists() and not (unrelated / "result").exists()
        assert not (stage / "master.out").exists()
        assert not list((stage / "program").glob("*_master_*.out"))
        print("PASS: Bash run from another directory, program/ executable, outer task log/result and real LLG PNG", flush=True)

        # 模拟 PBS 把脚本复制到 spool 后运行；必须仍回到原提交目录。
        spool = root / "spool"
        spool.mkdir()
        shutil.copy2(str(stage / "wz.pbs"), str(spool / "job_script"))
        nodes = stage / "allocated_nodes"
        nodes.write_text("node10\nnode10\n", encoding="ascii")
        pbs = dict(PBS_O_WORKDIR=stage.as_posix(), PBS_NODEFILE=nodes.as_posix(), PBS_JOBID="123.local",
                   RIBBON_ENGINE="mc", RIBBON_THREADS="2")
        result, log = invoke(spool / "job_script", environment=pbs)
        assert result.stdout == b"" and first_file.read_bytes() == first_bytes
        assert (stage / "nanoribbon_master_123.local.out").is_file() and "[LLG]" not in log
        assert "[MC]" in log and "threads: 2/2" in log and "123.local" in log
        verify_output("mc")
        assert not (spool / "master.out").exists() and not (spool / "result").exists()
        invoke(stage / "run.sh", "--engine", "mc", environment={"RIBBON_OUTPUT": "custom_result"})
        verify_output("mc", "custom_result")
        nodes.write_text("node10\nnode11\n", encoding="ascii")
        invoke(spool / "job_script", environment=pbs, success=False)
        print("PASS: spooled PBS entry, separate local/PBS logs, MC/threads/output overrides and multinode rejection", flush=True)

        # qsub 用本地替身，仅记录参数和工作目录；测试不向集群提交作业。
        mock_bin = root / "mockbin"
        mock_bin.mkdir()
        qsub = mock_bin / "qsub"
        qsub.write_text('#!/bin/bash\nprintf \'%s\\n\' "$PWD" "$@" > qsub_record.txt\nprintf \'123.local\\n\'\n', encoding="utf-8")
        os.chmod(str(qsub), 0o755)
        result, _ = invoke(stage / "submit.sh", "-v", "RIBBON_ENGINE=mc",
                           environment={"PATH": str(mock_bin) + os.pathsep + env["PATH"]})
        record = (stage / "qsub_record.txt").read_text(encoding="utf-8").splitlines()
        assert record[0] == shell_path(stage) and record[1:] == ["-v", "RIBBON_ENGINE=mc", "wz.pbs"]
        assert result.stdout.strip() == b"123.local"

        # 源码变化应触发重编译；失败不能破坏上一份可执行文件。
        header = stage / "program" / "io.hpp"
        executable = stage / "program" / "nanoribbon_cpu"
        before = hashlib.sha256(executable.read_bytes()).hexdigest()
        failing_compiler = mock_bin / "failing_compiler"
        failing_compiler.write_text('#!/bin/bash\nif [[ ${1:-} == --version ]]; then printf \'test compiler\\n\'; exit 0; fi\nprintf \'intentional compilation failure\\n\' >&2\nexit 9\n', encoding="utf-8")
        os.chmod(str(failing_compiler), 0o755)
        original_times = (header.stat().st_atime, header.stat().st_mtime)
        newer = executable.stat().st_mtime + 10
        os.utime(str(header), (newer, newer))
        invoke(stage / "run.sh", "--dry-run", environment={"CXX": shell_path(failing_compiler)}, success=False)
        assert hashlib.sha256(executable.read_bytes()).hexdigest() == before
        assert not list((stage / "program").glob(".nanoribbon_cpu.*"))
        os.utime(str(header), original_times)
        print("PASS: submit.sh fixes submission directory; header rebuild detected; failed build preserves binary and cleans temporary files", flush=True)
    print("All deployment checks passed; no cluster job was submitted.", flush=True)


if __name__ == "__main__":
    main()
