"""Run a subprocess with a combined stdout and stderr byte limit."""

import asyncio
import subprocess


class OutputLimitExceeded(RuntimeError):
    """The subprocess exceeded the output budget."""


class ProcessIOError(RuntimeError):
    """A pipe failed after subprocess I/O began."""


class _Capture(asyncio.SubprocessProtocol):
    def __init__(self, done, input_bytes, limit):
        self.done = done
        self.input_bytes = input_bytes
        self.limit = limit
        self.output = {1: bytearray(), 2: bytearray()}
        self.captured_bytes = 0
        self.error = None
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        if self.input_bytes is not None:
            stdin = transport.get_pipe_transport(0)
            stdin.write(self.input_bytes)
            stdin.close()

    def pipe_data_received(self, fd, data):
        if self.error is not None:
            return
        if self.captured_bytes + len(data) > self.limit:
            self.stop(OutputLimitExceeded(f"Subprocess exceeded {self.limit} output bytes"))
            return
        self.output[fd].extend(data)
        self.captured_bytes += len(data)

    def pipe_connection_lost(self, fd, error):
        if error is None or (fd == 0 and isinstance(error, (BrokenPipeError, ConnectionResetError))):
            return
        self.stop(ProcessIOError(f"Subprocess pipe {fd} failed: {error}"))

    def connection_lost(self, error):
        if error is not None and self.error is None:
            self.error = ProcessIOError(f"Subprocess I/O failed: {error}")
        self.done.set_result(None)

    def stop(self, error):
        if self.error is None:
            self.error = error
            self.transport.close()


async def _run(args, cwd, input_bytes, timeout, max_output_bytes, creationflags):
    loop = asyncio.get_running_loop()
    done = loop.create_future()
    transport, capture = await loop.subprocess_exec(
        lambda: _Capture(done, input_bytes, max_output_bytes),
        *args, cwd=cwd, creationflags=creationflags,
        stdin=subprocess.DEVNULL if input_bytes is None else subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(asyncio.shield(done), timeout)
    except asyncio.TimeoutError:
        capture.stop(subprocess.TimeoutExpired(args, timeout))
        await done
    finally:
        transport.close()
    if capture.error is not None:
        raise capture.error
    return subprocess.CompletedProcess(
        args,
        transport.get_returncode(),
        capture.output[1].decode("utf-8", errors="replace").replace("\r\n", "\n"),
        capture.output[2].decode("utf-8", errors="replace").replace("\r\n", "\n"),
    )


def run_bounded(args, *, cwd=None, input=None, timeout, max_output_bytes, creationflags=0):
    """Capture UTF-8 output up to a shared limit, closing pipes and reaping the child on failure."""
    if timeout <= 0 or max_output_bytes <= 0:
        raise ValueError("timeout and max_output_bytes must be positive")
    input_bytes = None if input is None else input.encode("utf-8")
    return asyncio.run(_run(args, cwd, input_bytes, timeout, max_output_bytes, creationflags))
