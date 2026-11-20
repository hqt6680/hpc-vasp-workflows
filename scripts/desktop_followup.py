"""Deliver a registered follow-up with the bundled Codex Desktop MCP server."""

import asyncio
import json
import os
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from contextlib import closing
from pathlib import Path

from desktop_owner import app_tools_pipe


def receipt(db, thread, prompt):
    rows = db.execute(
        "SELECT turn_id,item_json FROM thread_items WHERE thread_id=? AND item_type='functionCallOutput' "
        "AND instr(item_json,'codex_delegation')>0 ORDER BY created_at_ms DESC LIMIT 32", (thread,))
    for turn, raw in rows:
        item = json.loads(raw)
        if item.get("namespace") != "codex_app" or item.get("name") != "send_message_to_thread":
            continue
        try:
            envelope = ET.fromstring(item["output"])
        except (ET.ParseError, TypeError, KeyError):
            continue
        if (envelope.tag == "codex_delegation" and envelope.findtext("source_thread_id") == thread
                and envelope.findtext("input") == prompt):
            return turn
    return None


async def followup(node, message, proxy):
    offline = {"status": "unavailable", "reason": "desktop_owner"}
    pipe = app_tools_pipe(proxy)
    if not pipe:
        return offline
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    root = home / "plugins/cache/openai-bundled/codex-app-tools"
    versions = [(tuple(map(int, path.parent.name.split("."))), path) for path in root.glob("*/server.mjs")
                if all(s.isascii() and s.isdigit() for s in path.parent.name.split("."))]
    if not versions:
        return offline
    thread, prompt = message["threadId"], message["prompt"]
    history = (home / "thread_history_1.sqlite").resolve().as_uri() + "?mode=ro"
    sent = False
    proc = None
    try:
        with closing(sqlite3.connect(history, uri=True, timeout=2)) as db:
            previous = receipt(db, thread, prompt)
            if previous:
                return {"status": "received", "turnId": previous}
            active = db.execute("SELECT turn_id FROM thread_turns WHERE thread_id=? AND status='inProgress' "
                                "ORDER BY started_at DESC LIMIT 1", (thread,)).fetchone()
            proc = await asyncio.create_subprocess_exec(
                node, str(max(versions)[1]), env={**os.environ, "CODEX_APP_TOOLS_PIPE_PATH": pipe},
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=1024 * 1024, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

            async def rpc(number, method, params):
                req = {"jsonrpc": "2.0", "method": method, "params": params}
                if number is not None:
                    req["id"] = number
                proc.stdin.write(json.dumps(req).encode() + b"\n")
                await proc.stdin.drain()
                if number is None:
                    return
                while line := await proc.stdout.readline():
                    response = json.loads(line)
                    if response.get("id") == number:
                        if "error" in response:
                            raise ValueError("Desktop MCP call failed")
                        return response["result"]
                raise EOFError("Desktop MCP closed")

            await asyncio.wait_for(rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                   "clientInfo": {"name": "vasp-pbs-watcher", "version": "1"}}), 8)
            await asyncio.wait_for(rpc(None, "notifications/initialized", {}), 3)
            tools = await asyncio.wait_for(rpc(2, "tools/list", {}), 8)
            if not any(t["name"] == "send_message_to_thread" for t in tools["tools"]):
                return offline
            sent = True
            await asyncio.wait_for(rpc(3, "tools/call", {"name": "send_message_to_thread",
                                   "arguments": {"hostId": "local", "threadId": thread, "prompt": prompt},
                                   "_meta": {"threadId": thread}}), 25)
            for _ in range(30):
                turn = receipt(db, thread, prompt)
                if turn:
                    return {"status": "steered" if active == (turn,) else "received", "turnId": turn}
                await asyncio.sleep(0.5)
    except (OSError, EOFError, ValueError, KeyError, asyncio.TimeoutError, sqlite3.Error):
        pass
    finally:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
    return {"status": "unknown"} if sent else offline
