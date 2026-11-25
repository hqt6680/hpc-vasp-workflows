"""Set up one member's Windows project and remote VASP workspace."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile


LIBRARY_ROOT = Path("/public/home/zjt/.examples")
OLD_ROOT = Path("/public/home/zjt/task/now/hqt")
AICC_NAME = ".auto-computational-chemist"
BEGIN = "<!-- vasp-pbs:begin -->"
END = "<!-- vasp-pbs:end -->"


def section(path, body):
    """Prepare a managed section while preserving all other bytes."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Expected a regular file: " + str(path))
    old = path.read_bytes() if path.exists() else b""
    if b"\0" in old:
        raise ValueError("Expected UTF-8 Markdown in " + str(path))
    old.decode("utf-8-sig")
    nl = b"\r\n" if b"\r\n" in old else b"\n"
    start, end = BEGIN.encode(), END.encode()
    block = nl.join((start, body.strip().encode().replace(b"\n", nl), end))
    if start in old or end in old:
        if old.count(start) != 1 or old.count(end) != 1 or old.index(start) >= old.index(end):
            raise ValueError("Check the vasp-pbs markers in " + str(path))
        return old[:old.index(start)] + block + old[old.index(end) + len(end):]
    return old + (nl * 2 if old else b"") + block + nl


def save(path, content):
    if path.exists() and path.read_bytes() == content:
        return
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    with tempfile.NamedTemporaryFile(dir=str(path.parent), delete=False) as out:
        temp = Path(out.name)
        out.write(content)
    try:
        os.chmod(str(temp), mode)
        os.replace(str(temp), str(path))
    finally:
        if temp.exists():
            temp.unlink()


def real_directory(path):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("Expected a directory at " + str(path))


def install_aicc(root):
    """Install a private tree once. A repeat deployment keeps the member's edits."""
    aicc = root / AICC_NAME
    real_directory(aicc)
    required = ("AGENTS.md", "site-zjt.md", "tools/vasp/SKILL.md", "tools/hpc-submit/SKILL.md",
                "procedures/comp-chem-workflow/SKILL.md", "tools/vasp/scripts/check_inputs.py",
                "tools/vasp/scripts/parse_vasp.py")
    source = aicc if aicc.exists() else LIBRARY_ROOT / AICC_NAME
    for name in required:
        entry = source / name
        if not entry.is_file() or source not in entry.resolve().parents:
            raise ValueError("Missing or external AICC file: " + str(entry))
    site_rule = ("## 本工作区\n\n工作根为 `" + str(root) + "`。先读工作根的 AGENTS.md。"
                 "从本目录读取 AICC 工具、流程和知识，在工作根下的算例目录运行。")
    if aicc.exists():
        guide = aicc / "site-zjt.md"
        save(guide, section(guide, site_rule))
    else:
        with tempfile.TemporaryDirectory(dir=str(root)) as tmp:
            staged = Path(tmp) / AICC_NAME
            shutil.copytree(str(source), str(staged))
            guide = staged / "site-zjt.md"
            save(guide, section(guide, site_rule))
            staged.rename(aicc)
    return aicc


def configure_remote(workdir, enabled):
    import fcntl
    import pwd
    if pwd.getpwuid(os.getuid()).pw_name != "zjt":
        raise ValueError("Expected the shared zjt account")
    root = Path(os.path.realpath(workdir))
    locations = {"default": "Master", "examples": "Materials/examples"}
    protected = [LIBRARY_ROOT, OLD_ROOT / AICC_NAME] + [OLD_ROOT / rel for rel in locations.values()]
    if root in (Path("/"), Path.home(), OLD_ROOT) or any(
            p == root or p in root.parents or root in p.parents for p in protected):
        raise ValueError("Choose a personal calculation directory, outside the shared library")
    if enabled:
        for name in ("README.md", "case_index.md"):
            if not (LIBRARY_ROOT / "Master" / name).is_file():
                raise ValueError("Missing library index: " + str(LIBRARY_ROOT / "Master" / name))
        if not (LIBRARY_ROOT / "Materials/examples").is_dir():
            raise ValueError("Missing example collection: " + str(LIBRARY_ROOT / "Materials/examples"))
    root.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(str(root), os.O_RDONLY)
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        knowledge = root / "knowledge"
        personal = knowledge / "personal"
        for directory in (knowledge, personal):
            real_directory(directory)
        index = personal / "README.md"
        if index.is_symlink() or (index.exists() and not index.is_file()):
            raise ValueError("Expected a personal index file: " + str(index))
        for name, rel in locations.items():
            link = knowledge / name
            if link.is_symlink():
                if Path(os.path.realpath(str(link))) not in (OLD_ROOT / rel, LIBRARY_ROOT / rel):
                    raise ValueError("Unrelated link already exists: " + str(link))
            elif link.exists():
                raise ValueError("Path already occupied: " + str(link))
        rules = root / "AGENTS.md"
        group_rule = ("默认知识库为 `" + str(LIBRARY_ROOT) + "`。通过 knowledge/default/README.md "
                      "和 knowledge/default/case_index.md 读取教程与四个标准算例的索引。"
                      "按索引读取 knowledge/examples/ 下相应的 workflow.md。" if enabled else
                      "本工作区已选择跳过默认组内知识库。")
        body = ("## VASP 工作区\n\n" + group_rule + "\n"
                "个人计算方法保存在 knowledge/personal/。收到学习目录的请求时，按指定范围整理来源、适用条件和验收依据。\n"
                "按需从本工作根的 " + AICC_NAME + "/ 读取 AGENTS.md、site-zjt.md 及对应工具说明，在本工作区计算。")
        content = section(rules, body)
        aicc = install_aicc(root)
        personal.mkdir(parents=True, exist_ok=True)
        if not index.exists():
            with index.open("x", encoding="utf-8") as out:
                out.write("# 个人计算知识库\n\n在此索引本人总结的方法，并记录来源目录和适用条件。\n")
        for name, rel in locations.items():
            link = knowledge / name
            target = LIBRARY_ROOT / rel
            if enabled and Path(os.path.realpath(str(link))) != target:
                with tempfile.TemporaryDirectory(dir=str(knowledge)) as tmp:
                    new_link = Path(tmp) / name
                    new_link.symlink_to(target, target_is_directory=True)
                    new_link.replace(link)
            elif not enabled and link.is_symlink():
                link.unlink()
        legacy = knowledge / "group"
        if legacy.is_symlink() and Path(os.path.realpath(str(legacy))) in (
                OLD_ROOT / "Master", LIBRARY_ROOT / "Master"):
            legacy.unlink()
        save(rules, content)
    finally:
        os.close(directory_fd)
    return {"host": socket.gethostname(), "workdir": str(root), "group": enabled,
            "aicc": str(aicc), "aicc_available": (aicc / "site-zjt.md").is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh", help="Configured OpenSSH alias for the shared zjt account")
    parser.add_argument("--project", type=Path, help="Windows project root")
    parser.add_argument("--workdir", required=True, help="Personal absolute Linux working directory")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--group", dest="group", action="store_true")
    choice.add_argument("--no-group", dest="group", action="store_false")
    parser.add_argument("--remote-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.workdir.startswith("/") or not args.workdir.isprintable():
        parser.error("Expected an absolute Linux working directory")
    if args.remote_worker:
        print(json.dumps(configure_remote(args.workdir, args.group)))
        return
    if not re.fullmatch(r"[\w][\w.-]*", args.ssh or "") or not args.project:
        parser.error("--ssh and --project are required")
    sys.dont_write_bytecode = True
    from local_workspace import LOCAL_RULE, install, project_lock
    project = args.project.resolve()
    real_directory(project)
    settings = project / ".vasp-local"
    real_directory(settings)
    rules = project / "AGENTS.md"
    section(rules, LOCAL_RULE)
    config = settings / "knowledge.md"
    section(config, "")  # Validate existing markers before changing the remote workspace.
    flag = "--group" if args.group else "--no-group"
    command = ("cd " + shlex.quote(LIBRARY_ROOT.as_posix()) + " && cat AGENTS.md >/dev/null && "
               "python3 - --remote-worker " + flag + " --workdir " + shlex.quote(args.workdir))
    proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", args.ssh, command],
                          input=Path(__file__).read_bytes(), stdout=subprocess.PIPE, check=True)
    state = json.loads(proc.stdout.decode())
    group_setting = "已启用 `" + LIBRARY_ROOT.as_posix() + "`" if args.group else "已关闭"
    cfg = ("SSH 别名 `{}`，已验证服务器 `{}`。\n个人工作根 `{}`。\n默认组内库{}。\n"
           "AICC 路径 `{}`。个人方法索引 `knowledge/personal/README.md`。").format(
               args.ssh, state["host"], state["workdir"], group_setting, state["aicc"])
    with project_lock(project):
        install(project, cfg=cfg)
    print(json.dumps(state, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
