"""Read the current zjt group index or one of its Markdown documents over SSH."""
import argparse
import re
import shlex
import subprocess
from pathlib import PurePosixPath
from setup_workspace import LIBRARY_ROOT


DOCUMENT_ROOTS = ("Master", "Materials/examples", ".auto-computational-chemist")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh", required=True, help="Your configured OpenSSH alias for zjt")
    parser.add_argument("document", nargs="?", help="Markdown path relative to the group root")
    args = parser.parse_args()
    if not re.fullmatch(r"[\w][\w.-]*", args.ssh):
        parser.error("Expected an SSH alias")

    commands = [
        "set -eu",
        "test \"$(id -un)\" = zjt",
        "cd " + shlex.quote(LIBRARY_ROOT.as_posix()),
        "test \"$(pwd -P)\" = " + shlex.quote(LIBRARY_ROOT.as_posix()),
        'printf "%s@%s %s\\n" "$(id -un)" "$(hostname -s)" "$(pwd -P)" >&2',
    ]
    if args.document:
        path = PurePosixPath(args.document)
        if (".." in path.parts or path.is_absolute() or path.suffix.lower() != ".md"
                or not any(PurePosixPath(root) in path.parents for root in DOCUMENT_ROOTS)):
            parser.error("Choose a Markdown file from the group library")
        commands.extend([
            "test -r AGENTS.md",
            "doc=$(readlink -f -- " + shlex.quote(str(path)) + ")",
            'case "$doc" in "$PWD/Master/"*|"$PWD/Materials/examples/"*|'
            '"$PWD/.auto-computational-chemist/"*) ;; *) exit 2 ;; esac',
            'cat -- "$doc"',
        ])
    else:
        commands.extend([
            "cat AGENTS.md Master/README.md",
            "printf '\\nMaterials/examples/\\n'",
            "find Materials/examples -mindepth 1 -maxdepth 1 -type d -print",
            "find Materials/examples -mindepth 2 -maxdepth 2 -name workflow.md -type f -print",
        ])
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             args.ssh, "bash -s"], input=("\n".join(commands) + "\n").encode())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
