"""Watch registered VASP PBS jobs and deliver their terminal events to Codex Desktop."""

import argparse
import asyncio
import hashlib
import json
import logging
import logging.handlers
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from itertools import islice
from pathlib import Path, PurePosixPath

from bounded_process import run_bounded
from desktop_owner import verified_desktop
from desktop_followup import followup

PROJECT = Path(__file__).resolve().parents[1]
CONFIG_FILE = PROJECT / "scripts" / "pbs_watch.config.json"
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CodexVaspPbs"
TASK_NAME = "CodexVaspPbsWatch"
TERMINAL = {"F", "X"}
DELIVERED_STATES = ("steered", "started", "received")
ACKNOWLEDGEABLE_STATES = ("sending", "queued", *DELIVERED_STATES)
DELIVERY_SCRIPT = PROJECT / "scripts" / "desktop_delivery.mjs"
QUERY_BATCH_SIZE = 16
QUERY_OUTPUT_LIMIT = 1024 * 1024
DELIVERY_OUTPUT_LIMIT = 16 * 1024
DELIVERY_BATCH_SIZE = 16
PENDING_LIMIT = 64
DESTINATIONS_PER_POLL = 4


@dataclass(frozen=True)
class SiteConfig:
    ssh_host: str
    ssh_user: str
    ssh_hostname: str
    remote_root: PurePosixPath
    case_prefix: PurePosixPath
    job_id_suffix: str
    desktop_proxy: str | None
    qstat_path: PurePosixPath = PurePosixPath("/opt/pbs/bin/qstat")

    def is_job_id(self, value):
        return bool(re.fullmatch(r"[0-9]+" + re.escape(self.job_id_suffix), value))


SITE: SiteConfig


def read_site_config(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as error:
        raise ValueError("Create scripts/pbs_watch.config.json before running the PBS watcher") from error
    except (OSError, ValueError) as error:
        raise ValueError("Could not read pbs_watch.config.json as JSON") from error

    required = {"ssh_host", "ssh_user", "ssh_hostname", "remote_root", "case_prefix",
                "job_id_suffix", "desktop_proxy"}
    if not isinstance(data, dict) or not required <= data.keys() or data.keys() - required - {"qstat_path"}:
        raise ValueError("pbs_watch.config.json must contain the documented site keys")

    for key in ("ssh_host", "ssh_user", "ssh_hostname"):
        value = data[key]
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
            raise ValueError(f"Invalid {key} in pbs_watch.config.json")
    suffix = data["job_id_suffix"]
    if not isinstance(suffix, str) or not re.fullmatch(r"(?:\.[A-Za-z0-9_-]+)*", suffix):
        raise ValueError("job_id_suffix must be empty or a PBS server suffix starting with a dot")
    proxy = data["desktop_proxy"]
    if proxy is not None and (not isinstance(proxy, str) or not proxy
                              or any(char.isspace() or not char.isprintable() for char in proxy)):
        raise ValueError("desktop_proxy must be a nonempty proxy argument value or null")

    for key in ("remote_root", "case_prefix", "qstat_path"):
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str) or not value or not value.isprintable():
            raise ValueError(f"Invalid {key} in pbs_watch.config.json")
        remote_path = PurePosixPath(value)
        if (str(remote_path) != value or value.startswith("//") or "\\" in value
                or not remote_path.name or ".." in remote_path.parts
                or remote_path.is_absolute() != (key != "case_prefix")):
            raise ValueError(f"Invalid {key} in pbs_watch.config.json")
        if key == "case_prefix" and not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value):
            raise ValueError("case_prefix must use letters, digits, dots, underscores, hyphens or slashes")
        data[key] = remote_path
    return SiteConfig(**data), True


def workspace_storage(project, custom):
    if not custom:
        return TASK_NAME, STATE_DIR / "watch.sqlite3"
    normalized = os.path.normcase(str(project.resolve()))
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{TASK_NAME}-{key}", STATE_DIR / key / "watch.sqlite3"


def parse_qstat(text):
    payload = json.loads(text)
    jobs = payload.get("Jobs", {}) if isinstance(payload, dict) else None
    if not isinstance(jobs, dict) or any(not isinstance(job, dict) for job in jobs.values()):
        raise ValueError("Invalid PBS Jobs object")
    return jobs


def validate_job(job_id, name, case, thread):
    if len(job_id) > 128 or not SITE.is_job_id(job_id):
        raise ValueError(f"Use a numeric PBS job ID with configured suffix {SITE.job_id_suffix!r}")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,14}", name):
        raise ValueError("Use a short PBS job name")
    path = PurePosixPath(case)
    if (len(case) > 512 or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", case)
            or str(path) != case or ".." in path.parts or path == SITE.case_prefix
            or not path.is_relative_to(SITE.case_prefix)):
        raise ValueError(f"Case must be a case directory below {SITE.case_prefix}")
    return str(uuid.UUID(thread))


def verify_project_thread(thread):
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    state = codex_home / "state_5.sqlite"
    with closing(sqlite3.connect(state.as_uri() + "?mode=ro", uri=True, timeout=3)) as connection:
        row = connection.execute("SELECT cwd FROM threads WHERE id=?", (thread,)).fetchone()
    cwd = row[0] if row else None
    if not cwd or not Path(cwd).samefile(PROJECT):
        raise ValueError("The target Codex chat must belong to this VASP project")


def matches_job(expected, observed):
    variables = observed.get("Variable_List")
    if not isinstance(variables, dict):
        return False
    workdir = PurePosixPath(str(variables.get("PBS_O_WORKDIR", "")))
    case = SITE.remote_root / expected["case_dir"]
    return (
        str(observed.get("Job_Owner", "")).partition("@")[0] == SITE.ssh_user
        and observed.get("Job_Name") == expected["name"]
        and ".." not in workdir.parts
        and workdir.is_relative_to(case)
    )


class WatchDB:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, isolation_level="IMMEDIATE")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, name TEXT NOT NULL, case_dir TEXT NOT NULL,
                thread TEXT NOT NULL, pbs_state TEXT, exit_code INTEGER, walltime TEXT,
                updated TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
                delivery TEXT NOT NULL DEFAULT 'pending', detail TEXT,
                updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS events_delivery_job ON events(delivery, job_id);
            """
        )

    def add(self, job_id, name, case, thread):
        thread = validate_job(job_id, name, case, thread)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO jobs(job_id,name,case_dir,thread) VALUES(?,?,?,?)",
                            (job_id, name, case, thread))
            row = self.db.execute("SELECT name,case_dir,thread FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if tuple(row) != (name, case, thread):
                raise ValueError(f"{job_id} is already registered with different metadata")

    def active(self, after="", limit=None):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM jobs WHERE job_id>? "
            "AND NOT EXISTS (SELECT 1 FROM events WHERE events.job_id=jobs.job_id) "
            "ORDER BY job_id LIMIT ?", (after, limit if limit is not None else -1)
        )]

    def observe(self, observed):
        if not observed:
            return 0
        new_events = 0
        with self.db:
            for job_id, job in observed.items():
                row = self.db.execute(
                    "SELECT * FROM jobs WHERE job_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM events WHERE events.job_id=jobs.job_id)",
                    (job_id,),
                ).fetchone()
                if row is None:
                    continue
                job_id = row["job_id"]
                if not job or not matches_job(row, job):
                    continue
                state = job.get("job_state")
                if state not in {"B", "E", "F", "H", "M", "Q", "R", "S", "T", "U", "W", "X"}:
                    continue
                code = job.get("Exit_status")
                exit_code = int(code) if state in TERMINAL and re.fullmatch(r"-?\d+", str(code)) else None
                cancelled_before_start = (
                    state == "F" and str(job.get("substate")) == "91"
                    and job.get("history_timestamp") and not job.get("stime")
                )
                resources = job.get("resources_used") or {}
                walltime = resources.get("walltime") if isinstance(resources, dict) else None
                self.db.execute(
                    "UPDATE jobs SET pbs_state=?,exit_code=?,walltime=?,updated=CURRENT_TIMESTAMP "
                    "WHERE job_id=? AND exit_code IS NULL", (state, exit_code, walltime, job_id)
                )
                if exit_code is not None or cancelled_before_start:
                    event_id = f"{row['case_dir']}:{job_id}:terminal"
                    result = self.db.execute(
                        "INSERT OR IGNORE INTO events(event_id,job_id) VALUES(?,?)", (event_id, job_id)
                    )
                    new_events += result.rowcount
        return new_events

    def status(self):
        return [dict(row) for row in self.db.execute(
            "SELECT jobs.*, event_id, delivery, detail FROM jobs LEFT JOIN events USING(job_id) ORDER BY job_id"
        )]

    def has_work(self):
        return bool(self.db.execute(
            "SELECT EXISTS (SELECT 1 FROM events WHERE delivery='pending') OR EXISTS ("
            "SELECT 1 FROM jobs WHERE NOT EXISTS (SELECT 1 FROM events WHERE events.job_id=jobs.job_id))"
        ).fetchone()[0])

    def pending(self):
        return [dict(row) for row in self.db.execute(
            "SELECT jobs.*, events.event_id FROM events JOIN jobs USING(job_id) "
            "WHERE delivery='pending' ORDER BY events.updated, events.job_id LIMIT ?", (PENDING_LIMIT,)
        )]

    def change(self, event_id, before, after, detail=None):
        with self.db:
            return bool(self.db.execute(
                "UPDATE events SET delivery=?,detail=?,updated=CURRENT_TIMESTAMP WHERE event_id=? AND delivery=?",
                (after, detail, event_id, before)
            ).rowcount)

    def close(self):
        self.db.close()


def run_command(args, timeout):
    return run_bounded(
        args, cwd=PROJECT, timeout=timeout, max_output_bytes=QUERY_OUTPUT_LIMIT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def query_pbs(job_ids):
    if not 0 < len(job_ids) <= QUERY_BATCH_SIZE or any(not SITE.is_job_id(job_id) for job_id in job_ids):
        raise ValueError("Expected registered PBS job IDs")
    root = str(SITE.remote_root)
    header = ["cd " + shlex.quote(root), "cat AGENTS.md >/dev/null", "id -un", "hostname -s", "pwd -P"]
    command = " && ".join(header + [shlex.join([str(SITE.qstat_path), "-xf", "-F", "json", *job_ids])])
    result = run_command(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                          "-l", SITE.ssh_user, SITE.ssh_host, command], 25)
    output = result.stdout.split("\n", 3)
    if len(output) != 4 or output[:3] != [SITE.ssh_user, SITE.ssh_hostname, root]:
        raise RuntimeError("SSH did not verify the configured account, host and working directory")
    jobs = parse_qstat(output[3])
    if result.returncode and not jobs:
        raise RuntimeError("PBS returned no job records")
    return jobs


def event_message(rows):
    events = [{
        "event_id": row["event_id"], "job_id": row["job_id"], "job": row["name"],
        "case": row["case_dir"], "pbs_state": row["pbs_state"], "exit_code": row["exit_code"],
        "cancelled_before_start": row["exit_code"] is None,
    } for row in rows]
    return (
        "[VASP PBS 状态回传] 以下是本机 VASP 监听脚本记录的调度事件。"
        "按本项目 AGENTS.md，经 SSH 独立核验 PBS 和科学输出，再处理这个阶段。"
        "先对账已提交的作业，避免重复提交，只提交已验收且当前可运行的下一步。"
        "处理后运行 python scripts/pbs_watch.py ack <event_id>。"
        "新提交且需要回传的作业用 python scripts/pbs_watch.py add <job_id> <name> <case> 登记，"
        "再运行 scripts/install_pbs_watch.ps1 -Action Start。\n"
        + json.dumps(events, ensure_ascii=False, separators=(",", ":"))
    )


class DeliveryLaunchError(Exception):
    """The delivery subprocess did not start."""


def run_delivery(executable, payload):
    if verified_desktop(SITE.desktop_proxy) is None:
        response = asyncio.run(followup(executable, json.loads(payload), SITE.desktop_proxy))
        return subprocess.CompletedProcess([], 0, json.dumps(response), "")
    command = [executable, str(DELIVERY_SCRIPT)]
    try:
        return run_bounded(
            command, cwd=PROJECT, input=payload, timeout=25, max_output_bytes=DELIVERY_OUTPUT_LIMIT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise DeliveryLaunchError(str(error)) from error


def deliver_pending(db):
    batches = {}
    for row in db.pending():
        batch = batches.setdefault((row["thread"], row["case_dir"]), [])
        if len(batch) < DELIVERY_BATCH_SIZE:
            batch.append(row)
    for (thread, _), rows in islice(batches.items(), DESTINATIONS_PER_POLL):
        if len(event_message(rows).encode("utf-8")) > 32768:
            logging.warning("PBS delivery batch exceeds the IPC size limit; keeping events pending")
            continue
        try:
            verify_project_thread(thread)
        except (OSError, sqlite3.Error, ValueError) as error:
            logging.warning("Could not verify the target VASP chat: %s", error)
            continue
        executable = shutil.which("node.exe") or shutil.which("node")
        if executable is None:
            logging.warning("Node.js is unavailable; keeping PBS events pending")
            continue
        claimed = [row for row in rows if db.change(row["event_id"], "pending", "sending")]
        if not claimed:
            continue
        event_ids = sorted(row["event_id"] for row in claimed)
        message_id = str(uuid.uuid5(uuid.UUID(thread), "\n".join(event_ids)))
        payload = json.dumps({
            "threadId": thread,
            "clientUserMessageId": message_id,
            "prompt": event_message(claimed),
        }, ensure_ascii=False)
        try:
            result = run_delivery(executable, payload)
        except DeliveryLaunchError as error:
            for row in claimed:
                db.change(row["event_id"], "sending", "pending", str(error)[:300])
            logging.warning("Could not launch Codex Desktop delivery: %s", error)
            continue
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            logging.warning("Codex Desktop delivery %s ended without confirmation (%s); verify before retry",
                            message_id, type(error).__name__)
            continue
        if result.returncode:
            logging.warning("Codex Desktop delivery %s exited with code %d; verify before retry",
                            message_id, result.returncode)
            continue
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            response = None
        status = response.get("status") if isinstance(response, dict) else None
        turn_id = response.get("turnId") if isinstance(response, dict) else None
        if status == "unavailable":
            detail = ("Expected Codex Desktop does not own the local IPC pipe"
                      if response.get("reason") == "desktop_owner" else "Codex Desktop unavailable")
            for row in claimed:
                db.change(row["event_id"], "sending", "pending", detail)
            logging.info("%s; keeping %d PBS events pending", detail, len(claimed))
            break
        elif status in DELIVERED_STATES and isinstance(turn_id, str) and turn_id.strip():
            for row in claimed:
                db.change(row["event_id"], "sending", status, turn_id)
            logging.info("Delivered %d PBS terminal events to Codex Desktop (%s)", len(claimed), status)
        else:
            logging.warning("Codex Desktop delivery %s has no confirmed outcome; verify before retry", message_id)


def watch(db, interval, once):
    failures = 0
    after = ""
    while db.has_work():
        active = db.active(after, QUERY_BATCH_SIZE)
        if not active and after:
            active = db.active(limit=QUERY_BATCH_SIZE)
        if active:
            after = active[-1]["job_id"] if len(active) == QUERY_BATCH_SIZE else ""
            try:
                observed = query_pbs([row["job_id"] for row in active])
                db.observe(observed)
                missing = len(active) - sum(matches_job(row, observed.get(row["job_id"], {})) for row in active)
                if missing:
                    logging.warning("%d PBS jobs could not be verified; retaining previous state", missing)
                failures = failures + 1 if missing == len(active) else 0
                del observed
            except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                failures += 1
                logging.warning("PBS unavailable: %s", error)
        deliver_pending(db)
        if once or not db.has_work():
            break
        time.sleep(min(interval * (2 ** min(failures, 3)), 900))


def main(argv=None):
    global SITE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="Register an existing job")
    add.add_argument("job_id")
    add.add_argument("name")
    add.add_argument("case")
    add.add_argument("--thread", default=os.environ.get("CODEX_THREAD_ID"))
    monitor = sub.add_parser("watch")
    monitor.add_argument("--interval", type=int, default=120)
    monitor.add_argument("--once", action="store_true")
    sub.add_parser("status")
    sub.add_parser("task-name", help="Print the Windows task name for this workspace")
    sub.add_parser("has-work", help="Exit 0 if polling or delivery is required")
    for name in ("ack", "retry"):
        sub.add_parser(name).add_argument("event_id")
    args = parser.parse_args(argv)
    try:
        SITE, custom = read_site_config(CONFIG_FILE)
    except ValueError as error:
        parser.error(str(error))
    task_name, default_db = workspace_storage(PROJECT, custom)
    if args.command == "task-name":
        print(task_name)
        return 0
    args.db = args.db or default_db
    if args.command == "watch" and not 30 <= args.interval <= 900:
        parser.error("--interval must be between 30 and 900 seconds")
    if not args.db.exists() and args.command in {"watch", "has-work"}:
        return int(args.command == "has-work")
    db = WatchDB(args.db)
    try:
        if args.command == "add":
            if not args.thread:
                parser.error("Pass --thread with the VASP chat UUID")
            args.thread = str(uuid.UUID(args.thread))
            try:
                verify_project_thread(args.thread)
            except (OSError, sqlite3.Error) as error:
                raise ValueError(f"Could not verify the target Codex chat: {error}") from error
            db.add(args.job_id, args.name, args.case, args.thread)
        elif args.command == "status":
            print(json.dumps(db.status(), ensure_ascii=False, indent=2))
        elif args.command == "has-work":
            return 0 if db.has_work() else 1
        elif args.command == "ack":
            for state in ACKNOWLEDGEABLE_STATES:
                if db.change(args.event_id, state, "acked"):
                    return 0
            return 0 if any(row["event_id"] == args.event_id and row["delivery"] == "acked"
                            for row in db.status()) else 1
        elif args.command == "retry":
            return 0 if any(db.change(args.event_id, state, "pending")
                            for state in ACKNOWLEDGEABLE_STATES) else 1
        elif db.has_work():
            logging.basicConfig(
                handlers=[logging.handlers.RotatingFileHandler(
                    args.db.parent / "watch.log", maxBytes=128_000, backupCount=1, encoding="utf-8"
                )],
                level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
            )
            logging.info("VASP PBS watcher started")
            watch(db, args.interval, args.once)
            logging.info("VASP PBS watcher exited")
    except ValueError as error:
        parser.error(str(error))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
