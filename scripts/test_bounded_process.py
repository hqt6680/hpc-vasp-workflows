"""Tests for subprocess output limits using local Python children."""

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from bounded_process import OutputLimitExceeded, run_bounded


class BoundedProcessTests(unittest.TestCase):
    def run_python(self, code, *, timeout=10, limit=1024, cwd=None, input=None):
        return run_bounded(
            [sys.executable, "-X", "utf8", "-u", "-c", code],
            cwd=cwd, input=input, timeout=timeout, max_output_bytes=limit,
        )

    def test_captures_utf8_and_stderr_and_preserves_child_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_python(
                "import pathlib,sys; "
                "sys.stdout.buffer.write(sys.stdin.buffer.read()); "
                "pathlib.Path('started').touch(); "
                "sys.stderr.buffer.write(b'error'); sys.exit(7)",
                cwd=directory, input="作业", limit=11,
            )
            self.assertTrue((Path(directory) / "started").exists())
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "作业")
        self.assertEqual(result.stderr, "error")

    def test_combined_output_overflow_kills_child_instead_of_waiting_for_timeout(self):
        start = time.monotonic()
        with self.assertRaises(OutputLimitExceeded):
            self.run_python(
                "import sys,time; "
                "sys.stdout.buffer.write(b'x' * 150000); "
                "sys.stderr.buffer.write(b'y' * 150000); time.sleep(30)",
                timeout=10, limit=200000,
            )
        self.assertLess(time.monotonic() - start, 8)

    def test_timeout_closes_child_and_its_pipes(self):
        with tempfile.TemporaryDirectory() as directory:
            start = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_python(
                    "import os,pathlib,time; "
                    "pathlib.Path('pid').write_text(str(os.getpid())); time.sleep(30)",
                    timeout=1, cwd=directory,
                )
            self.assertLess(time.monotonic() - start, 8)
            pid = int((Path(directory) / "pid").read_text())
        if os.name == "nt":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(0x00100000, False, pid)
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0)
                finally:
                    kernel.CloseHandle(handle)
        else:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_spawn_error_remains_distinguishable(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / ("not-found.exe" if os.name == "nt" else "not-found"))
            with self.assertRaises(OSError):
                run_bounded([missing], timeout=1, max_output_bytes=1024)


if __name__ == "__main__":
    unittest.main()
