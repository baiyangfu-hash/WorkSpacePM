"""Keep the machine from going to sleep while a long foreground command runs (TD-SW008-160).

A laptop that sleeps suspends every thread, including the lease keep-alive; when it wakes the lease has expired and the whole
run of a long command (a full pytest, ``pm verify``) is lost. ``scripts/long_gate.py`` already holds the machine awake for the
release gate; this is the same call for the everyday wrapper (:mod:`auto_pm.application.core.lease_keepalive`).

Windows only (``SetThreadExecutionState``); elsewhere it does nothing. It never raises: a machine that refuses the request
just runs the command as before. Limits, stated plainly: it does not stop the sleep that closing the lid triggers (the lid
action is a power-plan setting), and it asks for the system to stay on, not the display.

``SetThreadExecutionState`` belongs to the *thread* that calls it, so the request and its release must come from the same
thread: use the context manager inside the thread that lives as long as the command.
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

#: ``SetThreadExecutionState(flags) -> previous flags`` (0 means the call failed).
ExecutionStateSetter = Callable[[int], int]


def _windows_setter() -> ExecutionStateSetter | None:
    """The real ``SetThreadExecutionState`` on Windows, ``None`` anywhere else or when it cannot be reached."""

    if os.name != "nt":  # not sys.platform: mypy would mark the rest unreachable on Linux
        return None
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    try:
        func = windll.kernel32.SetThreadExecutionState
        func.restype = ctypes.c_uint
        func.argtypes = [ctypes.c_uint]
    except (AttributeError, OSError):
        return None
    setter: ExecutionStateSetter = func
    return setter


@contextmanager
def keep_system_awake(setter: ExecutionStateSetter | None = None) -> Iterator[bool]:
    """Ask the system to stay awake for the block; yields whether the request was accepted.

    ``setter`` is for tests; by default the real Windows call is used (and nothing happens off Windows). The release always
    runs, and neither the request nor the release can raise into the caller's command.
    """

    call = setter if setter is not None else _windows_setter()
    if call is None:
        yield False
        return
    try:
        accepted = bool(call(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
    except Exception:  # noqa: BLE001 -- an unreachable power API must never stop the command
        accepted = False
    try:
        yield accepted
    finally:
        try:
            call(ES_CONTINUOUS)
        except Exception:  # noqa: BLE001 -- the release is best effort; the thread ending also drops the request
            pass
