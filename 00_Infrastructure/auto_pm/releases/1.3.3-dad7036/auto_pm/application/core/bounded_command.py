"""Run one command to its end, but stop it when told to or when its time limit passes."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Literal

TIMEOUT_EXIT_CODE = 124
STOPPED_EXIT_CODE = 125
_POLL_SECONDS = 0.2
_TERMINATE_GRACE_SECONDS = 10


@dataclass(frozen=True)
class CommandOutcome:
    """``stopped_by`` is empty when the command ended on its own; then ``returncode`` is the command's own."""

    returncode: int
    stopped_by: Literal["", "stop", "timeout"] = ""


def run_until_done_or_stopped(
    command: list[str], env: dict[str, str], timeout_seconds: float, stop: threading.Event
) -> CommandOutcome:
    """Wait for ``command``; terminate it when ``stop`` is set (exit 125) or after ``timeout_seconds`` (exit 124).

    This module owns the process lifetime, which is why it may start a ``Popen`` (see the allowlist in
    ``tests/test_subprocess_timeout_guard.py``): the loop below is the time limit.
    """
    process = subprocess.Popen(command, env=env)  # noqa: S603
    deadline = time.monotonic() + timeout_seconds
    while process.poll() is None:
        if stop.is_set():
            _terminate(process)
            return CommandOutcome(STOPPED_EXIT_CODE, "stop")
        if time.monotonic() > deadline:
            _terminate(process)
            return CommandOutcome(TIMEOUT_EXIT_CODE, "timeout")
        stop.wait(_POLL_SECONDS)
    return CommandOutcome(int(process.returncode))


def _terminate(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
