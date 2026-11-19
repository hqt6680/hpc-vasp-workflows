"""Verify which Windows Desktop owns the local Codex delivery pipe."""

import ctypes
import json
import os
import re
import subprocess
from ctypes import wintypes
from pathlib import PureWindowsPath

PIPE = r"\\.\pipe\codex-ipc"
DESKTOP = re.compile(
    r"[A-Za-z]:\\Program Files\\WindowsApps\\OpenAI\.Codex_[^\\]+\\app\\ChatGPT\.exe",
    re.IGNORECASE,
)


def pipe_owner():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(PIPE, 0xC0000000, 0, None, 3, 0, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        return None
    try:
        pid = wintypes.ULONG()
        owner_session = wintypes.DWORD()
        own_session = wintypes.DWORD()
        if (kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(pid))
                and kernel.ProcessIdToSessionId(pid, ctypes.byref(owner_session))
                and kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(own_session))
                and owner_session.value == own_session.value):
            return pid.value
        return None
    finally:
        kernel.CloseHandle(handle)


def desktop_process(pid):
    system_root = PureWindowsPath(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = (
        "$ErrorActionPreference='Stop';"
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}';"
        "if($p){$p|Select-Object ExecutablePath,CommandLine|ConvertTo-Json -Compress}"
    )
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, encoding="utf-8", errors="replace", timeout=8,
        creationflags=subprocess.CREATE_NO_WINDOW, check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def proxy_matches(command_line, expected):
    if expected is None:
        return True
    flags = re.findall(
        r'(?:^|\s)--proxy-server(?:=|\s+)(?:"([^"]+)"|([^\s"]+))(?=\s|$)',
        command_line,
    )
    return len(flags) == 1 and (flags[0][0] or flags[0][1]) == expected


def verified_desktop(expected_proxy):
    if os.name != "nt":
        return None
    try:
        pid = pipe_owner()
        if pid is None:
            return None
        process = desktop_process(pid)
        if (process and DESKTOP.fullmatch(process.get("ExecutablePath") or "")
                and proxy_matches(process.get("CommandLine") or "", expected_proxy)
                and pipe_owner() == pid):
            return pid
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None
