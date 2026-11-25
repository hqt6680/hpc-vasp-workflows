"""Install or restore the Windows side of one VASP workspace. Never connects over SSH."""
import argparse
import base64
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
from setup_workspace import BEGIN, END, save, section

SOURCE = Path(__file__).resolve().parents[1]
SKILL = ".agents/skills/vasp-pbs/"
META = ".vasp-local/"
RECEIPT = META + "restore.json"
RULES = "AGENTS.md"
CONFIG = META + "knowledge.md"
IGNORE = META + ".gitignore"
SITE = "scripts/pbs_watch.config.json"
WATCH = ("README.md", "install_pbs_watch.ps1", "pbs_watch.py", "pbs_watch.config.example.json",
         "bounded_process.py", "desktop_delivery.mjs", "desktop_owner.py", "desktop_followup.py")
PACKAGE = ("README.md", "SKILL.md", "references/setup.md", "references/group-library.md",
           "scripts/setup_workspace.py", "scripts/read_group_library.py", "scripts/local_workspace.py",
           "scripts/legacy_files.json", "assets/project/AGENTS.md",
           *("assets/project/scripts/" + name for name in WATCH))
STATE_FILES = ("watch.sqlite3", "watch.sqlite3-shm", "watch.sqlite3-wal", "watch.sqlite3-journal",
               "watch.log", "watch.log.1")
LOCAL_RULE = ("## VASP 计算\n\n先读本机 .vasp-local/knowledge.md，再通过配置的 SSH 别名"
              "进入个人工作根，读取 AGENTS.md，并使用其中的 .auto-computational-chemist/。"
              "启用默认库时从 /public/home/zjt/.examples 查教程和算例。\n"
              "部署与重新配置按 .agents/skills/vasp-pbs/references/setup.md 执行。每个缺项单独发一张问答卡，"
              "收到回答再问下一项。缺少 SSH 别名时引导配置并验证免密复连。")


def checked(root, name):
    path = root
    for part in Path(name).parts:
        if part in (".", "..") or Path(part).anchor or ":" in part:
            raise ValueError("Invalid deployment path: " + name)
        path = path / part
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Refusing to follow a deployment link: " + str(path))
    return path


def fingerprint(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def project_key(root):
    return hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()[:16]


@contextmanager
def project_lock(root):
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateMutexW(None, False, "Local\\VaspPbsDeploy-" + project_key(root))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.WaitForSingleObject(handle, 30000) not in (0, 0x80):
            raise ValueError("Another deployment is busy for this project")
        try:
            yield
        finally:
            kernel.ReleaseMutex(handle)
    finally:
        kernel.CloseHandle(handle)


def task(root, remove=False):
    # Identify the task even if the watcher or its site configuration was removed.
    script = r"""
$ErrorActionPreference='Stop'
$p=$env:VASP_RESTORE_PROJECT
$name=$env:VASP_RESTORE_TASK
$t=Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object TaskName -eq $name
if (!$t) { 'absent'; exit 0 }
if ($t.Description -ne "VASP PBS watcher for $p" -or
    @($t.Actions).Count -ne 1 -or $t.Actions[0].WorkingDirectory -ne $p) {
    throw 'Task belongs to a different workspace or action'
}
if ($env:VASP_RESTORE_REMOVE -eq '1') {
    if ($t.State -eq 'Running') {
        Stop-ScheduledTask -InputObject $t
        $until=[DateTime]::UtcNow.AddSeconds(15)
        while ((Get-ScheduledTask -TaskName $name -TaskPath '\').State -eq 'Running') {
            if ([DateTime]::UtcNow -ge $until) { throw 'Watcher has not stopped yet' }
            Start-Sleep -Milliseconds 150
        }
    }
    Unregister-ScheduledTask -InputObject $t -Confirm:$false
}
'present'
"""
    env = dict(os.environ, VASP_RESTORE_PROJECT=str(root),
               VASP_RESTORE_TASK="CodexVaspPbsWatch-" + project_key(root),
               VASP_RESTORE_REMOVE=str(int(remove)))
    out = subprocess.check_output(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                  env=env)
    return out.strip() == b"present"


def runtime(root):
    base = Path(os.environ["LOCALAPPDATA"]).resolve()
    return checked(base, "CodexVaspPbs/" + project_key(root))


def legacy_hashes():
    return json.loads((SOURCE / "scripts/legacy_files.json").read_text(encoding="utf-8"))


def read(path):
    return path.read_bytes() if path.exists() else None


def encode(data):
    return None if data is None else base64.b64encode(data).decode()


def original(value):
    return None if value is None else base64.b64decode(value, validate=True)


def remove_section(data, baseline):
    """Undo only the generated insertion, keeping later edits outside the markers."""
    if data is None:
        return data
    start, end = BEGIN.encode(), END.encode()
    if start not in data and end not in data:
        return data
    if data.count(start) != 1 or data.count(end) != 1 or data.index(start) >= data.index(end):
        raise ValueError("Ambiguous managed Markdown section")
    before, _, tail = data.partition(start)
    _, _, after = tail.partition(end)
    prior = baseline or b""
    if start in prior:
        replaced = prior[prior.index(start):prior.index(end) + len(end)]
        result = before + replaced + after
    else:
        nl = b"\r\n" if after.startswith(b"\r\n") else b"\n"
        if after.startswith(nl):
            after = after[len(nl):]
        if before.endswith(nl * 2):
            before = before[:-2 * len(nl)]
        join = nl if before and after and not before.endswith(b"\n") and not after.startswith(nl) else b""
        result = before + join + after
    return result if result or baseline is not None else None


def cache_files(root, files):
    found = set()
    for name in files:
        if not name.endswith(".py"):
            continue
        p = Path(name)
        cache = checked(root, (p.parent / "__pycache__").as_posix())
        if cache.is_dir():
            for item in cache.glob(p.stem + ".*.pyc"):
                if re.fullmatch(re.escape(p.stem) + r"\.[\w-]+(?:\.opt-\d+)?\.pyc", item.name):
                    rel = item.relative_to(root).as_posix()
                    checked(root, rel)
                    found.add(rel)
    return found


def payload(watcher):
    paths = {SKILL + name: SOURCE / name for name in PACKAGE}
    if watcher:
        paths.update({"scripts/" + n: SOURCE / "assets/project/scripts" / n for n in WATCH})
    # The four shared modules are injected by the packager in a release checkout.
    repo = SOURCE.parent.parent
    if SOURCE == repo / "share/vasp-pbs" and (repo / "scripts/package_vasp_pbs.py").is_file():
        for name, path in paths.items():
            if not path.exists() and path.name in ("bounded_process.py", "desktop_delivery.mjs",
                                                   "desktop_owner.py", "desktop_followup.py"):
                paths[name] = repo / "scripts" / path.name
    return paths


def directories(names):
    return {p.as_posix() for n in names for p in Path(n).parents if p != Path(".")}


def legacy_state(root):
    """Old packages have no receipt. Adopt only known content in a member installation."""
    if not checked(root, CONFIG).is_file() and not checked(root, SKILL + "SKILL.md").is_file():
        return None
    hashes = legacy_hashes()
    files = {}
    for name, accepted in hashes.items():
        p = checked(root, name)
        if p.is_file() and fingerprint(p.read_bytes()) in accepted:
            files[name] = fingerprint(p.read_bytes())
    sections = {}
    for name in (RULES, CONFIG):
        data = read(checked(root, name))
        if data is not None and BEGIN.encode() in data:
            base = remove_section(data, None)
            sections[name] = encode(base)
    member = CONFIG in sections or SKILL + "SKILL.md" in files
    if not member:
        return None
    watcher = "scripts/pbs_watch.py" in files and "scripts/install_pbs_watch.ps1" in files
    if not watcher:
        files = {n: h for n, h in files.items() if n.startswith(SKILL)}
    if watcher and checked(root, SITE).is_file():
        files[SITE] = None
    if read(checked(root, IGNORE)) in (b"*\n", b"*\r\n"):
        files[IGNORE] = fingerprint(b"*\n")
    dirs = directories([*files, *sections, RECEIPT])
    dirs.update(str(Path(n).parent.as_posix()) for n in cache_files(root, files))
    return {"project": str(root), "files": files, "sections": sections, "legacy": True,
            "dirs": sorted(dirs), "keep_cache": [],
            "watch": {"task_preexisting": False, "keep": [], "keep_dir": False,
                      "keep_parent": True} if watcher else None}


def install(root, watcher=False, cfg=None):
    journal = checked(root, RECEIPT)
    has_receipt = journal.exists()
    state = json.loads(journal.read_text(encoding="utf-8")) if has_receipt else legacy_state(root)
    if state is None:
        state = {"project": str(root), "files": {}, "sections": {}, "dirs": [],
                 "created_project": not root.exists(), "keep_cache": [], "watch": None}
    if state["project"] != str(root):
        raise ValueError("Restore record belongs to another project")
    track_cache = not has_receipt and not state.get("legacy")
    adding_watcher = watcher and state["watch"] is None
    paths = payload(watcher)
    writes = {}
    pending = state.setdefault("pending", {})
    for name, src in paths.items():
        content = src.read_bytes()
        p = checked(root, name)
        current = read(p)
        if has_receipt and src == p and current is not None:
            continue
        h = fingerprint(content)
        if current is not None and fingerprint(current) != h:
            if fingerprint(current) not in (state["files"].get(name), pending.get(name)):
                raise ValueError("Existing file differs: " + str(p))
        if current is None or name in state["files"] or (not has_receipt and name.startswith(SKILL) and src == p):
            if current is not None and fingerprint(current) != h:
                pending[name] = fingerprint(current)
            state["files"][name] = h
            writes[name] = content
    for name, data in [(IGNORE, b"*\n")] + ([(SITE, (SOURCE / "assets/project/scripts/pbs_watch.config.example.json").read_bytes())] if watcher else []):
        if not checked(root, name).exists():
            state["files"][name] = None if name == SITE else fingerprint(data)
            writes[name] = data
    bodies = {RULES: LOCAL_RULE}
    if watcher or state["watch"]:
        template = (SOURCE / "assets/project/AGENTS.md").read_text(encoding="utf-8")
        bodies[RULES] += "\n\n## PBS 回传" + template.split("## PBS 回传", 1)[1]
    if cfg is not None:
        bodies[CONFIG] = cfg
    for name, body in bodies.items():
        p = checked(root, name)
        state["sections"].setdefault(name, encode(read(p)))
        writes[name] = section(p, body)
    candidates = directories([*paths, *writes, RECEIPT])
    caches = {(Path(n).parent / "__pycache__").as_posix() for n in paths if n.endswith(".py")}
    managed_dirs = set(state["dirs"])
    for name in candidates | caches:
        p = checked(root, name)
        if p.exists() and not p.is_dir():
            raise ValueError("Expected a directory: " + str(p))
        if not p.exists():
            managed_dirs.add(name)
    # Snapshot caches at first ownership of each component, never on a repeated install.
    if track_cache:
        state["keep_cache"] = sorted(cache_files(root, paths))
    elif adding_watcher:
        new_files = [n for n in paths if n.startswith("scripts/")]
        state["keep_cache"] = sorted(set(state["keep_cache"]) | cache_files(root, new_files))
    state["dirs"] = sorted(managed_dirs)
    if adding_watcher:
        location = runtime(root)
        state["watch"] = {"task_preexisting": task(root),
                          "keep": [n for n in STATE_FILES if checked(location, n).exists()],
                          "keep_dir": location.exists(), "keep_parent": location.parent.exists()}
    # Commit ownership before creating files so an interrupted install is recoverable.
    journal.parent.mkdir(parents=True, exist_ok=True)
    save(journal, json.dumps(state, ensure_ascii=True, indent=2).encode())
    for name, data in writes.items():
        p = checked(root, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        save(p, data)
    if pending:
        pending.clear()
        save(journal, json.dumps(state, ensure_ascii=True, indent=2).encode())


def empty_dir(path):
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()


def legacy_rules(data):
    if not data:
        return data
    template = (SOURCE / "assets/project/AGENTS.md").read_bytes().replace(b"\r\n", b"\n")
    nl = b"\r\n" if b"\r\n" in data else b"\n"
    block = template.replace(b"\n", nl).rstrip(b"\r\n")
    if block not in data:
        old_header = "## PBS 回传".encode()
        _, sep, body = block.partition(old_header)
        if not sep:
            return data
        block = old_header[1:] + body
    if data.count(block) != 1:
        return data
    left, _, right = data.partition(block)
    if (left and not left.endswith(nl)) or (right and not right.startswith(nl)):
        return data
    if left.endswith(nl * 2):
        left = left[:-2 * len(nl)]
    return (left + (right[len(nl):] if right.startswith(nl) else right)) or None


def restore(root):
    journal = checked(root, RECEIPT)
    state = json.loads(journal.read_text(encoding="utf-8")) if journal.exists() else legacy_state(root)
    if state is None:
        print("No local deployment found.")
        return
    if state["project"] != str(root):
        raise ValueError("Restore record belongs to another project")
    allowed = set(payload(True)) | set(legacy_hashes()) | {SITE, IGNORE}
    allowed_dirs = directories([*allowed, CONFIG, RECEIPT])
    allowed_dirs.update((Path(n).parent / "__pycache__").as_posix() for n in allowed if n.endswith(".py"))
    if (not set(state["files"]) <= allowed or not set(state["sections"]) <= {CONFIG, RULES}
            or not set(state["dirs"]) <= allowed_dirs):
        raise ValueError("Unexpected path in restore record")
    for name in [*state["dirs"], *state["files"], *state["sections"]]:
        checked(root, name)
    edits = {n: remove_section(read(checked(root, n)), original(b))
             for n, b in state["sections"].items()}
    if state.get("legacy"):
        edits[RULES] = legacy_rules(edits.get(RULES, read(checked(root, RULES))))
    modules = set(payload(bool(state["watch"]))) | set(state["files"])
    caches = cache_files(root, modules) - set(state["keep_cache"])
    if state["watch"]:
        watch = state["watch"]
        location = runtime(root)
        logs = [checked(location, n) for n in STATE_FILES if n not in watch["keep"]]
        if not watch["task_preexisting"]:
            task(root, remove=True)
        for p in logs:
            p.unlink(missing_ok=True)
        if not watch["keep_dir"]:
            empty_dir(location)
        if not watch["keep_parent"]:
            empty_dir(location.parent)
    for name, content in edits.items():
        p = checked(root, name)
        if content is None:
            p.unlink(missing_ok=True)
        else:
            save(p, content)
    for name in caches:
        checked(root, name).unlink(missing_ok=True)
    preserved = []
    for name, digest in state["files"].items():
        p = checked(root, name)
        if p.exists() and digest is not None and fingerprint(p.read_bytes()) not in (
                digest, state.get("pending", {}).get(name)):
            preserved.append(p)
        else:
            p.unlink(missing_ok=True)
    for name in sorted(set(state["dirs"]) - {META.rstrip("/")}, key=lambda n: len(Path(n).parts), reverse=True):
        empty_dir(checked(root, name))
    journal.unlink(missing_ok=True)
    if META.rstrip("/") in state["dirs"]:
        empty_dir(journal.parent)
    if state.get("created_project"):
        empty_dir(root)
    print("Local deployment restored.")
    for path in preserved:
        print("Preserved locally edited file:", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "restore"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--watcher", action="store_true", help="Also install the project PBS watcher")
    args = parser.parse_args()
    root = args.project.resolve()
    if root.parent == root:
        parser.error("Choose a project directory")
    with project_lock(root):
        if args.action == "restore":
            restore(root)
        else:
            install(root, args.watcher)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
