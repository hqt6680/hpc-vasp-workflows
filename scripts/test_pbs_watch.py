"""Regression tests for the project-local PBS watcher."""

import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

import pbs_watch
from desktop_owner import proxy_matches


JOB_ID = "52255.master"
SECOND_JOB_ID = "52256.master"
CASE = "Materials/test/tb2j"
THREAD = "07bc3684-3d4d-418a-9bd8-d5ee3d74b8c1"


def job(name, state="R", exit_code=None, owner="zjt@master", case=CASE):
    properties = {
        "Job_Name": name,
        "Job_Owner": owner,
        "job_state": state,
        "resources_used": {"walltime": "01:54:30"},
        "Variable_List": {"PBS_O_WORKDIR": f"/public/home/zjt/task/now/hqt/{case}/z"},
    }
    if exit_code is not None:
        properties["Exit_status"] = exit_code
    return properties


def dispatching_job(name="socz", run_count=1):
    properties = job(name)
    del properties["resources_used"]
    properties.update(substate=41, run_count=run_count)
    return properties


class QstatParserTests(unittest.TestCase):
    def test_parses_the_jobs_object_without_inventing_missing_jobs(self):
        partial = {JOB_ID: job("socz")}
        raw = json.dumps({"pbs_version": "19.1.3", "Jobs": partial})
        self.assertEqual(pbs_watch.parse_qstat(raw), partial)

    def test_malformed_response_is_rejected(self):
        with self.assertRaises(ValueError):
            pbs_watch.parse_qstat("Connection closed by the remote host")

    def test_explicit_proxy_matches_the_launch_argument(self):
        proxy = "http://127.0.0.1:17897"
        self.assertTrue(proxy_matches(f'ChatGPT.exe --proxy-server="{proxy}"', proxy))
        self.assertFalse(proxy_matches(f"ChatGPT.exe --proxy-server={proxy}0", proxy))
        self.assertFalse(proxy_matches(f"ChatGPT.exe --proxy-server={proxy} --proxy-server=other", proxy))
        self.assertFalse(proxy_matches("ChatGPT.exe", proxy))
        self.assertTrue(proxy_matches("ChatGPT.exe", None))


class StartupTraceTests(unittest.TestCase):
    def test_latest_specific_rejection_is_preserved_over_generic_lines(self):
        snapshot = {JOB_ID: dispatching_job()}
        raw = f"""Job: {JOB_ID}
11/16/2026 15:55:24  S    send of job to node12 failed error = 15010 reject_msg=Previous scheduler error
11/16/2026 15:55:25  S    send of job to node12 failed error = 15010 reject_msg=pbs_mom: System error: No space left on device
11/16/2026 19:34:40  S    Unable to Run Job, MOM rejected
11/16/2026 19:34:41  L    Job run

Job: {SECOND_JOB_ID}
11/16/2026 19:34:42  S    send of job to node13 failed error = 15010 reject_msg=Unrelated node failure
"""
        result = pbs_watch.parse_startup_trace(raw, snapshot)
        self.assertEqual(set(result), {JOB_ID})
        self.assertIn("No space left on device", result[JOB_ID])
        self.assertNotIn("Unrelated node failure", result[JOB_ID])

    def test_ignores_rejections_older_than_job_submission(self):
        observed = dispatching_job()
        observed["qtime"] = "Sun Nov 15 00:00:00 2026"
        raw = f"""Job: {JOB_ID}
11/12/2026 10:00:00  S    send of job to node08 failed error = 15010 reject_msg=Old rejection
11/16/2026 10:01:00  L    Considering job to run

Job: {SECOND_JOB_ID}
11/16/2026 10:01:01  S    send of job to node12 failed error = 15010 reject_msg=Other job rejection
"""
        self.assertEqual(pbs_watch.parse_startup_trace(raw, {JOB_ID: observed}), {})


class SiteConfigTests(unittest.TestCase):
    config = {
        "ssh_host": "cluster-alias",
        "ssh_user": "researcher",
        "ssh_hostname": "head",
        "remote_root": "/work/research team",
        "case_prefix": "simulations/vasp",
        "job_id_suffix": ".pbs.example.org",
        "desktop_proxy": None,
        "qstat_path": "/usr/local/pbs tools/qstat",
    }

    def load(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pbs_watch.config.json"
            if config is not None:
                path.write_text(json.dumps(config), encoding="utf-8-sig")
            return pbs_watch.read_site_config(path)

    def test_workspace_without_config_keeps_existing_storage(self):
        site, custom = self.load(None)
        self.assertEqual(site, pbs_watch.SiteConfig())
        self.assertFalse(custom)
        task, path = pbs_watch.workspace_storage(pbs_watch.PROJECT, custom)
        self.assertEqual(task, "CodexVaspPbsWatch")
        self.assertEqual(path, pbs_watch.STATE_DIR / "watch.sqlite3")

    def test_custom_storage_is_consistent_per_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first_task, first_path = pbs_watch.workspace_storage(first, True)
            second_task, second_path = pbs_watch.workspace_storage(second, True)
            self.assertEqual(pbs_watch.workspace_storage(first.resolve(), True), (first_task, first_path))
            self.assertEqual(first_task, "CodexVaspPbsWatch-" + first_path.parent.name)
            self.assertNotEqual(first_task, second_task)
            self.assertNotEqual(first_path, second_path)

    @patch.object(pbs_watch, "run_command")
    def test_custom_site_uses_configured_identity_paths_and_job_ids(self, run):
        site, custom = self.load(self.config)
        self.assertTrue(custom)
        self.assertIsNone(site.desktop_proxy)
        identifier = "123.pbs.example.org"
        case = "simulations/vasp/example"
        observed = job("scf", owner="researcher@head")
        observed["Variable_List"]["PBS_O_WORKDIR"] = "/work/research team/" + case + "/scf"
        response = "researcher\nhead\n/work/research team\n" + json.dumps({"Jobs": {identifier: observed}})
        run.return_value = subprocess.CompletedProcess([], 0, response, "")
        with patch.object(pbs_watch, "SITE", site):
            self.assertEqual(pbs_watch.validate_job(identifier, "scf", case, THREAD), THREAD)
            self.assertTrue(pbs_watch.matches_job({"name": "scf", "case_dir": case}, observed))
            self.assertEqual(pbs_watch.query_pbs([identifier]), {identifier: observed})
            command = run.call_args.args[0]
            self.assertEqual(command[-4:-1], ["-l", "researcher", "cluster-alias"])
            self.assertIn("cd '/work/research team'", command[-1])
            self.assertIn("'/usr/local/pbs tools/qstat' -xf -F json 123.pbs.example.org", command[-1])
            with self.assertRaises(ValueError):
                pbs_watch.validate_job(JOB_ID, "scf", case, THREAD)
            with self.assertRaises(ValueError):
                pbs_watch.validate_job(identifier, "scf", "simulations/vasp/../other", THREAD)
            run.return_value.stdout = response.replace("head\n", "other\n", 1)
            with self.assertRaises(RuntimeError):
                pbs_watch.query_pbs([identifier])

    def test_config_rejects_unsafe_or_malformed_values(self):
        for key, value in (
            ("ssh_host", "-oProxyCommand=bad"),
            ("job_id_suffix", ".pbs;false"),
            ("remote_root", "/work/../other"),
            ("case_prefix", "/simulations"),
            ("qstat_path", "qstat"),
            ("desktop_proxy", ""),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(dict(self.config, **{key: value}))


class WatchDBTests(unittest.TestCase):
    def setUp(self):
        desktop = patch.object(pbs_watch, "verified_desktop", return_value=1234)
        self.desktop = desktop.start()
        self.addCleanup(desktop.stop)
        self.read_allowance = pbs_watch.weekly_allowance_available
        allowance = patch.object(pbs_watch, "weekly_allowance_available", return_value=True)
        self.allowance = allowance.start()
        self.addCleanup(allowance.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "watch.sqlite"
        self.db = pbs_watch.WatchDB(self.path)
        self.addCleanup(self.db.close)
        self.db.add(JOB_ID, "socz", CASE, THREAD)

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch, "run_delivery")
    def test_weekly_limit_keeps_terminal_event_pending(self, delivery, _verify):
        self.allowance.return_value = False
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        pbs_watch.deliver_pending(self.db)
        self.assertEqual(self.db.status()[0]["delivery"], "pending")
        delivery.assert_not_called()

    def test_weekly_snapshot_exhaustion_and_reset(self):
        rollout = self.path.with_name("rollout.jsonl")
        for used, reset, expected in (
            (87, time.time() + 1800, True),
            (100, time.time() + 1800, False),
            (87, time.time() - 1, False),
        ):
            limits = {"limit_id": "codex", "primary": {"used_percent": 12, "window_minutes": 300},
                      "secondary": {"used_percent": used, "window_minutes": 10080, "resets_at": reset}}
            snapshot = {"payload": {"type": "token_count", "rate_limits": limits}}
            rollout.write_text(json.dumps(snapshot) + '\n{"unfinished":', encoding="utf-8")
            self.assertIs(self.read_allowance(rollout), expected)

    def test_partial_scheduler_response_does_not_create_terminal_event(self):
        self.db.add(SECOND_JOB_ID, "socx", CASE, THREAD)
        self.assertEqual(self.db.observe({JOB_ID: job("socz")}), 0)
        self.assertTrue(self.db.has_work())
        self.assertTrue(all(row["delivery"] is None for row in self.db.status()))
        self.assertEqual(self.db.observe({}), 0)
        self.assertTrue(self.db.has_work())

    def test_terminal_event_is_created_only_once_even_after_reopen(self):
        terminal = {JOB_ID: job("socz", state="F", exit_code=0)}
        self.assertEqual(self.db.observe({JOB_ID: job("socz")}), 0)
        self.assertEqual(self.db.observe(terminal), 1)
        self.assertEqual(self.db.observe(terminal), 0)
        reopened = pbs_watch.WatchDB(self.path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.observe(terminal), 0)
        row, = reopened.status()
        self.assertEqual(row["pbs_state"], "F")
        self.assertEqual(row["delivery"], "pending")

    def test_foreign_scheduler_job_cannot_create_event(self):
        unexpected = {SECOND_JOB_ID: job("other", state="F", exit_code=0)}
        self.assertEqual(self.db.observe(unexpected), 0)
        self.assertTrue(self.db.has_work())
        row, = self.db.status()
        self.assertIsNone(row["delivery"])

    def test_terminal_with_nonzero_exit_is_delivered_for_diagnosis(self):
        terminal = {JOB_ID: job("socz", state="F", exit_code=137)}
        self.assertEqual(self.db.observe(terminal), 1)
        row, = self.db.status()
        self.assertEqual(row["pbs_state"], "F")
        self.assertEqual(row["delivery"], "pending")

    def test_same_id_from_another_case_or_owner_is_ignored(self):
        wrong_case = {JOB_ID: job("socz", state="F", exit_code=0, case=f"{CASE}-other")}
        wrong_owner = {JOB_ID: job("socz", state="F", exit_code=0, owner="someone@master")}
        for snapshot in (wrong_case, wrong_owner):
            self.assertEqual(self.db.observe(snapshot), 0)
        row, = self.db.status()
        self.assertIsNone(row["delivery"])

    def test_terminal_record_without_exit_code_is_incomplete(self):
        self.assertEqual(self.db.observe({JOB_ID: job("socz", state="F")}), 0)
        row, = self.db.status()
        self.assertIsNone(row["delivery"])
        self.assertTrue(self.db.has_work())

    def test_cancelled_before_start_has_no_exit_code(self):
        cancelled = job("socz", state="F")
        cancelled.update(substate=91, history_timestamp=1794551283)
        self.assertEqual(self.db.observe({JOB_ID: cancelled}), 1)
        self.assertEqual(self.db.active(), [])
        row, = self.db.status()
        self.assertIsNone(row["exit_code"])
        self.assertEqual(row["delivery"], "pending")

    def test_dispatch_failure_notifies_once_and_retains_terminal_tracking(self):
        now = 1794815700
        retrying = {JOB_ID: dispatching_job(run_count=4)}
        reasons = {JOB_ID: "pbs_mom: System error: No space left on device"}
        self.assertEqual(self.db.startup_candidates(retrying, now=now), [JOB_ID])
        self.assertEqual(self.db.observe(retrying, startup_reasons=reasons, now=now), 1)
        alert, = self.db.pending()
        self.assertEqual(alert["event_id"], f"{CASE}:{JOB_ID}:startup")
        self.assertEqual(alert["event_kind"], "startup")
        self.assertEqual(alert["reason"], reasons[JOB_ID])
        event, = json.loads(pbs_watch.event_message([alert]).splitlines()[-1])
        self.assertEqual(event["job_id"], JOB_ID)
        self.assertEqual(event["event_kind"], "startup")
        self.assertEqual(event["reason"], reasons[JOB_ID])
        self.assertEqual(event["pbs_state"], "R")
        self.assertNotIn("cancelled_before_start", event)

        self.assertTrue(self.db.change(alert["event_id"], "pending", "acked"))
        self.assertEqual(self.db.observe(retrying, startup_reasons=reasons, now=now + 120), 0)
        with contextlib.closing(pbs_watch.WatchDB(self.path)) as reopened:
            self.assertEqual(reopened.startup_candidates(retrying, now=now + 240), [])
            self.assertEqual(reopened.pending(), [])
            active, = reopened.active()
            self.assertEqual(active["job_id"], JOB_ID)
            self.assertTrue(reopened.has_work())

            running = job("socz")
            running.update(substate=42, stime=now + 240, session_id=1042, run_count=4)
            self.assertEqual(reopened.startup_candidates({JOB_ID: running}, now=now + 240), [])
            self.assertEqual(reopened.observe({JOB_ID: running}, now=now + 240), 0)
            self.assertEqual(reopened.observe({JOB_ID: job("socz", state="F", exit_code=0)}), 1)
            terminal, = reopened.pending()
            self.assertEqual(terminal["event_id"], f"{CASE}:{JOB_ID}:terminal")
            self.assertEqual(terminal["event_kind"], "terminal")
            self.assertEqual(terminal["exit_code"], 0)
            self.assertEqual(reopened.active(), [])

    def test_stuck_start_only_warns_after_grace_period(self):
        now = 1794815700
        dispatching = {JOB_ID: dispatching_job()}
        self.assertEqual(self.db.startup_candidates(dispatching, now=now), [])
        self.assertEqual(self.db.observe(dispatching, now=now), 0)
        self.assertEqual(self.db.startup_candidates(dispatching, now=now + 239), [])
        self.assertEqual(self.db.observe(dispatching, now=now + 239), 0)
        self.assertEqual(self.db.startup_candidates(dispatching, now=now + 240), [JOB_ID])
        reasons = {JOB_ID: pbs_watch.startup_reason(dispatching[JOB_ID], None)}
        self.assertEqual(self.db.observe(dispatching, startup_reasons=reasons, now=now + 240), 1)
        row, = self.db.pending()
        self.assertEqual(row["event_kind"], "startup")
        self.assertTrue(row["reason"])

    def test_queued_retry_needs_scheduler_diagnosis(self):
        now = 1794815700
        dispatching = dispatching_job(run_count=3)
        dispatching.update(job_state="Q", substate=10)
        observed = {JOB_ID: dispatching}
        self.assertEqual(self.db.startup_candidates(observed, now=now), [JOB_ID])
        self.assertEqual(self.db.observe(observed, now=now), 0)
        self.assertEqual(self.db.pending(), [])
        reasons = {JOB_ID: "Unable to Run Job, MOM rejected"}
        self.assertEqual(self.db.observe(observed, startup_reasons=reasons, now=now + 120), 1)

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch, "run_delivery")
    def test_weekly_limit_also_keeps_startup_event_pending(self, delivery, _verify):
        self.allowance.return_value = False
        retrying = {JOB_ID: dispatching_job(run_count=3)}
        self.db.observe(retrying, startup_reasons={JOB_ID: "MOM rejected"})
        pbs_watch.deliver_pending(self.db)
        event, = self.db.pending()
        self.assertEqual(event["event_kind"], "startup")
        delivery.assert_not_called()

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch, "run_bounded")
    def test_terminal_delivery_is_batched_and_requires_ack(self, run, _find, verify):
        self.db.add(SECOND_JOB_ID, "socx", CASE, THREAD)
        self.assertEqual(self.db.observe({
            JOB_ID: job("socz", state="F", exit_code=0),
            SECOND_JOB_ID: job("socx", state="F", exit_code=1),
        }), 2)
        run.return_value = subprocess.CompletedProcess([], 0, '{"status":"steered","turnId":"turn-1"}', "")
        pbs_watch.deliver_pending(self.db)
        pbs_watch.deliver_pending(self.db)
        verify.assert_called_once_with(THREAD)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["test-node.exe", str(pbs_watch.DELIVERY_SCRIPT)])
        self.assertEqual(run.call_args.kwargs["max_output_bytes"], pbs_watch.DELIVERY_OUTPUT_LIMIT)
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["threadId"], THREAD)
        event_ids = {row["event_id"] for row in self.db.status()}
        self.assertEqual(payload["clientUserMessageId"], str(uuid.uuid5(uuid.UUID(THREAD), "\n".join(sorted(event_ids)))))
        events = json.loads(payload["prompt"].splitlines()[-1])
        self.assertEqual({event["event_id"] for event in events}, event_ids)
        self.assertFalse(self.db.has_work())
        self.assertEqual({(row["delivery"], row["detail"]) for row in self.db.status()}, {("steered", "turn-1")})
        event_id = next(iter(event_ids))
        self.assertEqual(pbs_watch.main(["--db", str(self.path), "ack", event_id]), 0)
        self.assertEqual({row["delivery"] for row in self.db.status()}, {"steered", "acked"})

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch, "run_delivery")
    def test_unavailable_delivery_retries_same_batch_with_same_message_id(self, run, _find, _verify):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        run.side_effect = [
            subprocess.CompletedProcess([], 0, '{"status":"unavailable"}', ""),
            subprocess.CompletedProcess([], 0, '{"status":"started","turnId":"turn-2"}', ""),
        ]
        pbs_watch.deliver_pending(self.db)
        self.assertTrue(self.db.has_work())
        self.assertEqual(self.db.status()[0]["delivery"], "pending")
        pbs_watch.deliver_pending(self.db)
        self.assertEqual(run.call_args_list[0], run.call_args_list[1])
        row, = self.db.status()
        self.assertEqual((row["delivery"], row["detail"]), ("started", "turn-2"))

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch.time, "sleep")
    @patch.object(pbs_watch, "reopen_desktop_thread", return_value=True)
    @patch.object(pbs_watch, "run_delivery")
    def test_missing_thread_owner_reopens_and_retries_same_event(self, run, reopen, _sleep, _find, _verify):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        run.side_effect = [
            subprocess.CompletedProcess([], 0, '{"status":"unavailable","reason":"thread_owner_missing"}', ""),
            subprocess.CompletedProcess([], 0, '{"status":"steered","turnId":"resumed-turn"}', ""),
        ]
        pbs_watch.deliver_pending(self.db)
        reopen.assert_called_once_with(THREAD)
        self.assertEqual(len(run.call_args_list), 2)
        self.assertEqual(run.call_args_list[0], run.call_args_list[1])
        row, = self.db.status()
        self.assertEqual((row["delivery"], row["detail"]), ("steered", "resumed-turn"))

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch.time, "sleep")
    @patch.object(pbs_watch, "reopen_desktop_thread", return_value=True)
    @patch.object(pbs_watch, "run_delivery")
    def test_chat_is_not_reopened_again_if_owner_stays_missing(self, run, reopen, _sleep, _find, _verify):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        missing = subprocess.CompletedProcess([], 0, '{"status":"unavailable","reason":"thread_owner_missing"}', "")
        offline = subprocess.CompletedProcess([], 0, '{"status":"unavailable","reason":"desktop_owner"}', "")
        run.side_effect = [missing, missing, offline, missing]
        pbs_watch.deliver_pending(self.db)
        reopened_db = pbs_watch.WatchDB(self.path)
        self.addCleanup(reopened_db.close)
        pbs_watch.deliver_pending(reopened_db)
        pbs_watch.deliver_pending(reopened_db)
        reopen.assert_called_once_with(THREAD)
        row, = reopened_db.status()
        self.assertEqual(row["delivery"], "pending")
        self.assertTrue(row["detail"].startswith(pbs_watch.REOPENED_CHAT))

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch, "run_bounded", side_effect=OSError("launch failed"))
    def test_process_spawn_failure_returns_to_pending(self, run, _find, _verify):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        with self.assertLogs(level="WARNING"):
            pbs_watch.deliver_pending(self.db)
        run.assert_called_once()
        self.assertEqual(self.db.status()[0]["delivery"], "pending")
        self.assertTrue(self.db.has_work())

    @patch.object(pbs_watch, "verify_project_thread", side_effect=ValueError("wrong project"))
    @patch.object(pbs_watch, "run_delivery")
    def test_unverified_thread_remains_pending(self, run, _verify):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        with self.assertLogs(level="WARNING"):
            pbs_watch.deliver_pending(self.db)
        run.assert_not_called()
        self.assertEqual(self.db.status()[0]["delivery"], "pending")

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch, "run_bounded")
    def test_wrong_desktop_keeps_event_pending_without_opening_ipc_client(self, run, _find, _verify):
        self.desktop.return_value = None
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        pbs_watch.deliver_pending(self.db)
        self.desktop.assert_called_once_with(pbs_watch.SITE.desktop_proxy)
        run.assert_not_called()
        row, = self.db.status()
        self.assertEqual(row["delivery"], "pending")
        self.assertIn("IPC pipe", row["detail"])

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch, "run_delivery")
    def test_ambiguous_delivery_does_not_replay(self, run, _find, _verify):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        reopened = pbs_watch.WatchDB(self.path)
        self.addCleanup(reopened.close)
        row, = self.db.status()
        event_id = row["event_id"]
        responses = {
            "timeout": subprocess.TimeoutExpired("test-node.exe", timeout=45),
            "ipc_error": OSError("IPC interrupted"),
            "output_overflow": RuntimeError("output exceeded the limit"),
            "nonzero": subprocess.CompletedProcess([], 1, '{"status":"unavailable"}', ""),
            "malformed": subprocess.CompletedProcess([], 0, "invalid output", ""),
            "missing_turn": subprocess.CompletedProcess([], 0, '{"status":"started"}', ""),
            "unknown": subprocess.CompletedProcess([], 0, '{"status":"unknown"}', ""),
        }
        for name, response in responses.items():
            with self.subTest(name=name):
                run.reset_mock(side_effect=True)
                run.side_effect = [response]
                with self.assertLogs(level="WARNING"):
                    pbs_watch.deliver_pending(self.db)
                pbs_watch.deliver_pending(reopened)
                run.assert_called_once()
                self.assertEqual(reopened.status()[0]["delivery"], "sending")
                self.assertFalse(reopened.has_work())
                self.assertEqual(pbs_watch.main(["--db", str(self.path), "retry", event_id]), 0)

    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch.shutil, "which", return_value="test-node.exe")
    @patch.object(pbs_watch, "run_delivery")
    def test_delivery_uses_pending_only_and_limits_messages(self, run, _find, _verify):
        observed = {}
        for index in range(pbs_watch.DELIVERY_BATCH_SIZE + 1):
            job_id = f"{60000 + index}.master"
            self.db.add(job_id, "scf", CASE, THREAD)
            observed[job_id] = job("scf", state="F", exit_code=0)
        self.db.observe(observed)
        run.return_value = subprocess.CompletedProcess([], 0, '{"status":"started","turnId":"turn-1"}', "")
        with patch.object(self.db, "status", side_effect=AssertionError("history materialized")):
            self.assertTrue(self.db.has_work())
            pbs_watch.deliver_pending(self.db)
            run.assert_called_once()
            self.assertEqual(len(self.db.pending()), 1)
            pbs_watch.deliver_pending(self.db)
            self.assertEqual(run.call_count, 2)
            self.assertFalse(self.db.pending())

    def test_ack_and_retry_keep_legacy_queued_compatibility(self):
        self.db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
        event_id = self.db.status()[0]["event_id"]
        for state in ("queued", "started", "steered"):
            with self.subTest(state=state):
                self.assertTrue(self.db.change(event_id, "pending", state))
                self.assertEqual(pbs_watch.main(["--db", str(self.path), "retry", event_id]), 0)
                self.assertTrue(self.db.change(event_id, "pending", state))
                self.assertEqual(pbs_watch.main(["--db", str(self.path), "ack", event_id]), 0)
                self.assertTrue(self.db.change(event_id, "acked", "pending"))


class WatchCommandTests(unittest.TestCase):
    def test_legacy_database_preserves_pending_terminal_events_and_active_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watch.sqlite"
            with contextlib.closing(sqlite3.connect(path)) as old:
                old.executescript(
                    """
                    CREATE TABLE jobs (
                        job_id TEXT PRIMARY KEY, name TEXT NOT NULL, case_dir TEXT NOT NULL,
                        thread TEXT NOT NULL, pbs_state TEXT, exit_code INTEGER, walltime TEXT,
                        updated TEXT
                    );
                    CREATE TABLE events (
                        event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
                        delivery TEXT NOT NULL DEFAULT 'pending', detail TEXT,
                        updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX events_delivery_job ON events(delivery, job_id);
                    """
                )
                old.executemany(
                    "INSERT INTO jobs (job_id, name, case_dir, thread, pbs_state, exit_code) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [(JOB_ID, "socz", CASE, THREAD, "F", 0), (SECOND_JOB_ID, "socx", CASE, THREAD, "R", None)],
                )
                event_id = f"{CASE}:{JOB_ID}:terminal"
                old.execute("INSERT INTO events (event_id, job_id) VALUES (?, ?)", (event_id, JOB_ID))
                old.commit()

            with contextlib.closing(pbs_watch.WatchDB(path)) as db:
                terminal, = db.pending()
                self.assertEqual(terminal["event_id"], event_id)
                self.assertEqual(terminal["event_kind"], "terminal")
                self.assertEqual(terminal["exit_code"], 0)
                running, = db.active()
                self.assertEqual(running["job_id"], SECOND_JOB_ID)
                self.assertEqual(running["pbs_state"], "R")

    @unittest.skipUnless(pbs_watch.os.name == "nt", "Windows task start")
    @patch.object(pbs_watch, "verify_project_thread")
    @patch.object(pbs_watch, "run_command")
    def test_add_start_registers_before_requesting_task_and_skips_finished_jobs(self, run, verify):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watch.sqlite"
            args = ["add", JOB_ID, "socz", CASE, "--thread", THREAD, "--start"]

            def start_task(command, timeout):
                self.assertEqual(command, ["schtasks.exe", "/Run", "/TN", "test-watch"])
                with contextlib.closing(pbs_watch.WatchDB(path)) as db:
                    self.assertEqual(db.active()[0]["job_id"], JOB_ID)
                return subprocess.CompletedProcess(command, 0, "", "")

            run.side_effect = start_task
            with patch.object(pbs_watch, "workspace_storage", return_value=("test-watch", path)):
                self.assertEqual(pbs_watch.main(args), 0)
                with contextlib.closing(pbs_watch.WatchDB(path)) as db:
                    db.observe({JOB_ID: job("socz", state="F", exit_code=0)})
                    db.change(db.pending()[0]["event_id"], "pending", "acked")
                self.assertEqual(pbs_watch.main(args), 0)
            run.assert_called_once()

    def test_idle_watch_once_does_not_contact_pbs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watch.sqlite"
            with patch.object(pbs_watch, "query_pbs") as query:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = pbs_watch.main(["--db", str(path), "watch", "--once"])
                    self.assertIn(result, (None, 0))
                    self.assertFalse(path.exists())
                    pbs_watch.WatchDB(path).close()
                    result = pbs_watch.main(["--db", str(path), "watch", "--once"])
        self.assertIn(result, (None, 0))
        query.assert_not_called()

    @patch.object(pbs_watch, "run_command")
    def test_partial_qstat_nonzero_preserves_returned_records(self, run):
        partial = {JOB_ID: job("socz", state="F", exit_code=0)}
        output = "zjt\nmaster\n/public/home/zjt/task/now/hqt\n" + json.dumps({"Jobs": partial})
        run.return_value = subprocess.CompletedProcess([], 153, output, "Unknown Job Id")
        self.assertEqual(pbs_watch.query_pbs([JOB_ID, SECOND_JOB_ID]), partial)
        self.assertIn(f"qstat -xf -F json {JOB_ID} {SECOND_JOB_ID}", run.call_args.args[0][-1])

    @patch.object(pbs_watch, "deliver_pending")
    @patch.object(pbs_watch, "query_startup_failures")
    @patch.object(pbs_watch, "query_pbs")
    def test_watch_only_queries_startup_details_for_candidates(self, query, diagnose, deliver):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.closing(pbs_watch.WatchDB(Path(directory) / "watch.sqlite")) as db:
                db.add(JOB_ID, "socz", CASE, THREAD)
                db.add(SECOND_JOB_ID, "socx", CASE, THREAD)
                retrying = dispatching_job(run_count=4)
                query.return_value = {
                    JOB_ID: retrying,
                    SECOND_JOB_ID: job("socx", state="F", exit_code=0),
                }
                diagnose.return_value = {JOB_ID: "No space left on device"}
                pbs_watch.watch(db, interval=120, once=True)
                diagnose.assert_called_once_with({JOB_ID: retrying})
                deliver.assert_called_once_with(db)
                self.assertEqual(
                    {row["job_id"]: row["event_kind"] for row in db.pending()},
                    {JOB_ID: "startup", SECOND_JOB_ID: "terminal"},
                )

    @patch.object(pbs_watch, "deliver_pending")
    @patch.object(pbs_watch, "query_pbs", side_effect=RuntimeError("SSH disconnected"))
    def test_unreachable_pbs_does_not_invent_terminal_events(self, query, deliver):
        with tempfile.TemporaryDirectory() as directory:
            db = pbs_watch.WatchDB(Path(directory) / "watch.sqlite")
            try:
                db.add(JOB_ID, "socz", CASE, THREAD)
                db.observe({JOB_ID: job("socz")})
                with self.assertLogs(level="WARNING"):
                    pbs_watch.watch(db, interval=120, once=True)
                query.assert_called_once_with([JOB_ID])
                deliver.assert_called_once_with(db)
                row, = db.status()
                self.assertEqual(row["pbs_state"], "R")
                self.assertIsNone(row["delivery"])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
