
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import subprocess

parser = argparse.ArgumentParser(description="Package the VASP/PBS skill from this worktree")
parser.add_argument("output", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
skill = root / "share" / "vasp-pbs"
shared = ("bounded_process.py", "desktop_delivery.mjs", "desktop_owner.py", "desktop_followup.py")
tracked = subprocess.check_output(
    ["git", "-C", str(root), "ls-files", "-z", "--", "share/vasp-pbs"]
).decode().rstrip("\0").split("\0")
assert (skill / "SKILL.md").is_file()
args.output.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(args.output, "w", ZIP_DEFLATED) as result:
    for name in tracked:
        source = root / name
        assert source.is_file()
        result.write(source, "vasp-pbs/" + source.relative_to(skill).as_posix())
    for name in shared:
        result.write(root / "scripts" / name, "vasp-pbs/assets/project/scripts/" + name)
with ZipFile(args.output) as release:
    assert release.testzip() is None
    assert len(set(release.namelist())) == len(release.namelist())
