"""验证配置名前缀、PBS/本地任务隔离、并发启动和命令行配置优先级；不提交集群作业。"""
import argparse
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
    args = parser.parse_args()
    package = Path(__file__).resolve().parent.parent

    def shell_path(path):
        value = Path(path).resolve().as_posix()
        return "/" + value[0].lower() + value[2:] if os.name == "nt" and value[1:2] == ":" else value

    with TemporaryDirectory(prefix="ribbon-logs-") as temporary:
        root = Path(temporary)
        stage = root / "package with spaces"
        stage.mkdir()
        (stage / "program").mkdir()
        for name in ("run.sh", "wz.pbs", "build.sh"):
            shutil.copy2(str(package / name), str(stage / name))
        executable = stage / "program" / "nanoribbon_cpu"
        executable.write_text('#!/bin/bash\nprintf \'[Test] Job: %s\\n\' "${PBS_JOBID:-local}"\nprintf \'[Test] Args:\'; printf \' <%s>\' "$@"; printf \'\\n\'\nsleep 0.15\nprintf \'[Test] Complete: %s\\n\' "${PBS_JOBID:-local}"\n', encoding="utf-8")
        os.chmod(str(executable), 0o755)
        original_master = stage / "master.out"
        original_master.write_bytes(b'legacy master log stays intact\n')
        unrelated = root / "unrelated"
        unrelated.mkdir()
        nodes = stage / "nodes"
        nodes.write_text("node10\nnode10\n", encoding="ascii")
        env = dict(os.environ)
        for key in ("PBS_NODEFILE", "PBS_O_WORKDIR", "PBS_JOBID", "RIBBON_CONFIG", "RIBBON_ENGINE", "RIBBON_THREADS", "RIBBON_OUTPUT", "RIBBON_HOME", "BUILD_ON_NODE"):
            env.pop(key, None)
        env.update(OMP_NUM_THREADS="2", MPLCONFIGDIR=(root / "mpl").as_posix())

        def start(script="run.sh", flags=(), config=None, job=None):
            current = env.copy()
            if config is not None:
                current["RIBBON_CONFIG"] = config
            if job is not None:
                current.update(PBS_JOBID=job, PBS_NODEFILE=nodes.as_posix(), PBS_O_WORKDIR=stage.as_posix())
            return subprocess.Popen([args.bash, "--noprofile", "--norc", shell_path(stage / script), *flags],
                                    cwd=str(unrelated), env=current, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        def finish(process):
            output, _ = process.communicate(timeout=30)
            assert process.returncode == 0 and output == b"", output.decode("utf-8", errors="replace")

        finish(start("wz.pbs", config="case_A.ini", job="1001.server"))
        finish(start("wz.pbs", config="case_B.ini", job="1002.server"))
        a = stage / "case_A_master_1001.server.out"
        b = stage / "case_B_master_1002.server.out"
        assert a.is_file() and b.is_file()
        before = a.read_bytes()
        finish(start("wz.pbs", config="case_A.ini", job="1003.server"))
        assert (stage / "case_A_master_1003.server.out").is_file() and a.read_bytes() == before
        # 相同作业 ID 重启追加，之前不同任务的文件保持不变。
        finish(start("wz.pbs", config="case_A.ini", job="1001.server"))
        assert a.read_bytes().startswith(before) and a.stat().st_size > len(before)
        print("PASS: configuration prefixes, repeated configuration jobs separated, same-job rerun appends", flush=True)

        finish(start(flags=("--config", "first.ini", "--config", "nested/final.case.ini"), config="ignored.ini", job="1004.server"))
        final = stage / "final.case_master_1004.server.out"
        assert final.is_file()
        log = final.read_text(encoding="utf-8", errors="replace")
        assert "[Run] Config: nested/final.case.ini;" in log and "<nested/final.case.ini>" in log
        finish(start(config="/some/other/folder/absolute.ini", job="1005[2].server"))
        assert (stage / "absolute_master_1005[2].server.out").is_file()
        # 用 argv 传中文/空格，保留 Unicode 名称，只把空白规范为下划线。
        finish(start(flags=("--config", "nested/测试 扫场.ini"), job="1006.server"))
        assert (stage / "测试_扫场_master_1006.server.out").is_file()
        print("PASS: last CLI --config overrides environment; paths/extensions, Unicode, spaces and array-job IDs", flush=True)

        first = start(config="shared.ini", job="2001.server")
        second = start(config="shared.ini", job="2002.server")
        finish(first)
        finish(second)
        for own, other in (("2001.server", "2002.server"), ("2002.server", "2001.server")):
            log = (stage / ("shared_master_" + own + ".out")).read_text(encoding="utf-8", errors="replace")
            assert own in log and other not in log
        first = start(config="local.ini")
        second = start(config="local.ini")
        finish(first)
        finish(second)
        assert len(list(stage.glob("local_master_local_*.out"))) == 2
        assert original_master.read_bytes() == b'legacy master log stays intact\n'
        assert not list(unrelated.glob("*_master_*.out"))
        assert not list((stage / "program").glob("*_master_*.out"))
        print("PASS: simultaneous PBS/local jobs have distinct files; logs stay beside scripts; legacy master.out untouched", flush=True)
    print("All task-log checks passed; no cluster job was submitted.", flush=True)


if __name__ == "__main__":
    main()
