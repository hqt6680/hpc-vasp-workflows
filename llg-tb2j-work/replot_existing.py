"""从已计算的 TXT/NPY 自旋构型批量生成原 Python LLG 风格图片，不运行模拟。

默认递归扫描目录，另存至目录下的 replotted；--in-place 可替换原 PNG。
优先读取 summary.csv / run_settings.ini / run_config.json，并兼容新旧文件名。
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_snapshot import render


NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
HELPERS = {"initial_state", "final_state", "checkpoint", "noise", "neighbours", "field_mev", "probe"}


def read_settings(path):
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        values = dict(data)
        values.update(data.get("ribbon", {}))
        if "length" in values:
            values["Nx"] = values["length"]
        if "width" in values:
            values["Ny"] = values["width"]
        for key, target in (("temperatures_K", "temperature_start_K"),
                            ("magnetic_fields_T", "field_start_T"), ("electric_fields", "electric_start")):
            items = values.get(key, [])
            if items and len(set(items)) == 1:
                values[target] = items[0]
                values[target.replace("start", "end")] = items[0]
    else:
        values = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    result = {}
    for source, target in (("Nx", "length"), ("Ny", "width"), ("L", "length")):
        if source in values:
            result[target] = int(values[source])
    if "L" in values and "Ny" not in values:
        result["width"] = int(values["L"])
    for target, start, end in (("temperature", "temperature_start_K", "temperature_end_K"),
                               ("field", "field_start_T", "field_end_T"),
                               ("electric", "electric_start", "electric_end")):
        if start in values and end in values and float(values[start]) == float(values[end]):
            result[target] = float(values[start])
    for target in ("boundary_x", "boundary_y", "engine"):
        if target in values:
            result[target] = str(values[target])
    if "boundary" in values:
        result.setdefault("boundary_x", values["boundary"])
        result.setdefault("boundary_y", values["boundary"])
    return result


def filename_settings(path):
    result = {}
    for part in (*path.parent.parts, path.stem):
        if part.lower() in ("llg", "mc"):
            result["engine"] = part.lower()
        shape = re.search(r"Nx(\d+)_Ny(\d+)", part, re.I)
        if shape:
            result.update(length=int(shape[1]), width=int(shape[2]))
        boundary = re.search(r"_X(open|periodic|closed)_Y(open|periodic|closed)", part, re.I)
        if boundary:
            result.update(boundary_x=boundary[1].lower(), boundary_y=boundary[2].lower())
        for name, pattern in (("temperature", r"(?:^|_)T_(" + NUMBER + r")K?(?=_|$)"),
                               ("field", r"(?:^|_)B_(" + NUMBER + r")T?(?=_|$)"),
                               ("electric", r"(?:^|_)Ez_(" + NUMBER + r")(?=_|$)")):
            match = re.search(pattern, part, re.I)
            if match:
                result[name] = float(match[1])
        temperature_only = re.fullmatch("(" + NUMBER + ")K", part, re.I)
        if temperature_only:
            result["temperature"] = float(temperature_only[1])
            result.setdefault("field", 0.0)
            result.setdefault("electric", 0.0)
    # 原程序的单场目录/文件名中，另一外场不写出时表示零场。
    kinds = {part.lower()[:-11] if part.lower().endswith("_relaxation") else part.lower()
             for part in path.parent.parts}
    if "magnetic" in kinds or "temperature_magnetic" in kinds:
        result.setdefault("electric", 0.0)
    if "electric" in kinds or "temperature_electric" in kinds:
        result.setdefault("field", 0.0)
    if "temperature" in kinds:
        result.setdefault("field", 0.0)
        result.setdefault("electric", 0.0)
    if "field" in result and "electric" not in result:
        result["electric"] = 0.0
    if "electric" in result and "field" not in result:
        result["field"] = 0.0
    return result


def is_snapshot(path):
    return (path.suffix.lower() in (".txt", ".npy") and path.stem.lower() not in HELPERS
            and not path.name.lower().endswith((".tmp.txt", ".render.tmp.txt"))
            and (path.suffix.lower() == ".npy" or bool(filename_settings(path).get("temperature") is not None)))


def summary_metadata(path):
    result = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not row.get("snapshot"):
                continue
            candidate = Path(row["snapshot"])
            candidate = candidate if candidate.is_absolute() else path.parent / candidate
            if not candidate.is_file():
                # 兼容从服务器拷回后失效的绝对路径。
                candidate = path.parent / Path(row["snapshot"].replace("\\", "/")).name
            if not candidate.is_file():
                continue
            settings = {}
            for target, keys in (("temperature", ("T_K", "temperature_K")),
                                 ("field", ("B_T", "Bz_T")), ("electric", ("Ez",))):
                for key in keys:
                    if row.get(key, "") != "":
                        settings[target] = float(row[key])
                        break
            result[candidate.resolve()] = settings
    return result


def collect_jobs(inputs):
    jobs = {}
    for entry in inputs:
        entry = entry.expanduser().resolve()
        if not entry.exists():
            raise ValueError("找不到输入路径：{}".format(entry))
        root = entry if entry.is_dir() else entry.parent
        if entry.is_dir():
            for summary in sorted(entry.rglob("summary.csv")):
                for source, hints in summary_metadata(summary).items():
                    jobs.setdefault(source, dict(source=source, root=root, hints={}))["hints"].update(hints)
            sources = sorted(p for p in entry.rglob("*") if p.is_file() and is_snapshot(p))
        elif entry.suffix.lower() in (".txt", ".npy"):
            sources = [entry]
        else:
            raise ValueError("输入须为结果目录、TXT 或 NPY 构型；PNG 中没有完整自旋数据：{}".format(entry))
        for source in sources:
            source = source.resolve()
            jobs.setdefault(source, dict(source=source, root=root, hints={}))
    # 与 C++ 构型读取一致：同目录同名 TXT/NPY 同时存在时优先 TXT。
    unique = {}
    for source, job in jobs.items():
        key = (source.parent, source.stem)
        if key not in unique or source.suffix.lower() == ".txt":
            unique[key] = job
    return list(unique.values())


def metadata(job, overrides, settings_cache):
    source, root = job["source"], job["root"]
    ancestors = []
    current = source.parent
    while True:
        ancestors.append(current)
        if current == root or current == current.parent:
            break
        current = current.parent
    result = dict(engine="llg", boundary_x="open", boundary_y="open")
    for parent in reversed(ancestors):
        for name in ("run_config.json", "run_settings.ini"):
            candidate = parent / name
            if candidate.is_file():
                if candidate not in settings_cache:
                    settings_cache[candidate] = read_settings(candidate)
                result.update(settings_cache[candidate])
    result.update(filename_settings(source))
    result.update(job["hints"])
    result.update({key: value for key, value in overrides.items() if value is not None})
    if "length" not in result or "width" not in result:
        if source.suffix.lower() == ".npy":
            data = np.load(str(source), mmap_mode="r", allow_pickle=False)
            if data.ndim == 3 and data.shape[-1] == 3:
                result.setdefault("length", data.shape[0])
                result.setdefault("width", data.shape[1])
    missing = [key for key in ("length", "width", "temperature", "field", "electric") if key not in result]
    if missing:
        flags = " ".join("--" + key.replace("_", "-") for key in missing)
        raise ValueError("无法确定 {}，请显式指定 {}；三列 TXT 的总行数不能确定长宽".format(
            "/".join(missing), flags))
    return result


def output_path(job, args, multiple):
    source, root = job["source"], job["root"]
    if args.in_place:
        return source.with_suffix(".png")
    destination = args.output_dir.expanduser().resolve() if args.output_dir else root / "replotted"
    if args.output_dir and multiple:
        destination /= root.name
    try:
        relative = source.relative_to(root)
    except ValueError:
        relative = Path("_referenced") / source.parent.name / source.name
    return destination / relative.with_suffix(".png")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+", help="结果根目录，或一个/多个 TXT/NPY 文件")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output-dir", type=Path, help="另存目录，保留源目录层级")
    destination.add_argument("--in-place", action="store_true", help="从构型重绘并替换原同名 PNG")
    parser.add_argument("--overwrite", action="store_true", help="覆盖另存目录中已经存在的图片")
    parser.add_argument("--dry-run", action="store_true", help="只显示转换计划，不写图片或清单")
    parser.add_argument("--length", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--field", type=float)
    parser.add_argument("--electric", type=float)
    parser.add_argument("--boundary-x", choices=("open", "closed", "periodic"))
    parser.add_argument("--boundary-y", choices=("open", "closed", "periodic"))
    parser.add_argument("--engine")
    parser.add_argument("--dpi", type=int, default=150)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    overrides = {key: getattr(args, key) for key in (
        "length", "width", "temperature", "field", "electric", "boundary_x", "boundary_y", "engine")}
    try:
        jobs = collect_jobs(args.paths)
        if not jobs:
            raise ValueError("没有找到可重绘的自旋 TXT/NPY 构型；请保留计算输出的自旋数据")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    settings_cache, records, targets = {}, [], {}
    multiple = len({job["root"] for job in jobs}) > 1
    for index, job in enumerate(jobs, 1):
        source = job["source"]
        target = output_path(job, args, multiple)
        record = dict(source=str(source), target=str(target), status="", error="")
        try:
            if target in targets and targets[target] != source:
                raise ValueError("不同构型会生成同一个 PNG，请分别运行或指定另一输出目录：{}".format(target))
            targets[target] = source
            settings = metadata(job, overrides, settings_cache)
            record.update(settings)
            if args.dry_run:
                record["status"] = "planned"
            elif target.exists() and not (args.in_place or args.overwrite):
                record["status"] = "skipped_existing"
            else:
                render(source, target, dpi=args.dpi, **settings)
                record["status"] = "rendered"
            print("[{}/{} {}] {} -> {}".format(index, len(jobs), record["status"], source.name, target), flush=True)
        except (ValueError, OSError, TypeError) as error:
            record.update(status="error", error=str(error))
            print("[{}/{} ERROR] {}: {}".format(index, len(jobs), source, error), flush=True)
        records.append(record)
    if not args.dry_run:
        if args.output_dir:
            report = args.output_dir.expanduser().resolve() / "replot_manifest.csv"
        else:
            first_root = jobs[0]["root"]
            report = (first_root if args.in_place else first_root / "replotted") / "replot_manifest.csv"
        report.parent.mkdir(parents=True, exist_ok=True)
        columns = ["source", "target", "status", "length", "width", "temperature", "field", "electric",
                   "boundary_x", "boundary_y", "engine", "error"]
        with report.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
        print("转换清单：{}".format(report), flush=True)
    failed = sum(row["status"] == "error" for row in records)
    print("总计 {} 个构型，成功/计划 {}，已存在跳过 {}，失败 {}。".format(
        len(records), sum(row["status"] in ("rendered", "planned") for row in records),
        sum(row["status"] == "skipped_existing" for row in records), failed), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
