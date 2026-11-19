"""兼容旧命令的重绘入口；默认替换原 PNG，可用 --output-dir 另存。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replot_existing import main as replot_main


def main():
    arguments = sys.argv[1:]
    if not any(arg == "--output-dir" or arg.startswith("--output-dir=") or arg == "--in-place" for arg in arguments):
        arguments.append("--in-place")
    return replot_main(arguments)


if __name__ == "__main__":
    sys.exit(main())
