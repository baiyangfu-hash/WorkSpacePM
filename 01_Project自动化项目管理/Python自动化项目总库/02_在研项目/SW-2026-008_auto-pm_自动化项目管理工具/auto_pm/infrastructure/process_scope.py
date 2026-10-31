"""Child processes started inside one bounded gate, so a timeout can take them down with it (TD-SW008-188).

A gate that outlives its time limit is abandoned on its thread (Python cannot kill a thread).  Without this module the plugin command line it
had started kept running, and the abandoned thread could start the next one.  ``ProcessScope`` is entered by the gate's worker thread;
``run_in_scope`` (used by the Siemens runner) registers every child there; the supervisor calls ``cancel`` on timeout, which kills the whole
process tree of every registered child and makes later starts fail at once.
"""

from __future__ import annotations

import contextlib
import contextvars
import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

__all__ = [
    "GateAbandonedError",
    "GateCancelledError",
    "ProcessScope",
    "current_scope",
    "kill_process_tree",
    "leaked_threads",
    "reclaim_thread",
    "run_in_scope",
]

_SCOPE: contextvars.ContextVar[ProcessScope | None] = contextvars.ContextVar("auto_pm_process_scope", default=None)
_REAP_SECONDS = 5
RECLAIM_GRACE_SECONDS = 3.0
_RECLAIM_RETRY_SECONDS = 0.1
_SETTLE_SECONDS = 0.5
_WINDOWS = sys.platform == "win32"


class GateCancelledError(OSError):
    """The gate was abandoned after its time limit; no further child process may start."""


class GateAbandonedError(BaseException):  # noqa: N818 - deliberately not an Exception: ``except Exception`` in the checked code must not swallow it
    """Raised inside an abandoned gate's thread by ``reclaim_thread`` so that pure-Python work stops at its next bytecode."""


_LEAKED: list[threading.Thread] = []
_LEAKED_LOCK = threading.Lock()


def _raise_in_thread(thread: threading.Thread) -> bool:
    """Ask the interpreter to raise ``GateAbandonedError`` in ``thread`` at its next bytecode; False if that was not possible."""

    ident = thread.ident
    if ident is None or not thread.is_alive():
        return False
    api = ctypes.pythonapi.PyThreadState_SetAsyncExc
    changed = int(api(ctypes.c_ulong(ident), ctypes.py_object(GateAbandonedError)))
    if changed > 1:  # more than one thread state matched: take it back, never hit an innocent thread
        api(ctypes.c_ulong(ident), None)
        return False
    return changed == 1


def reclaim_thread(thread: threading.Thread, grace: float | None = None) -> bool:
    """Stop an abandoned gate thread if it can be stopped; True when it has ended.

    Python cannot kill a thread, but it can raise an exception in one: pure-Python work (loops, string handling) ends at its next bytecode.
    A call stuck inside C code (a regular-expression backtrack, a blocking system call) only ends when that call returns, so the thread
    may outlive ``grace``; it is then remembered in ``leaked_threads`` instead of being silently forgotten.
    """

    deadline = time.monotonic() + max(0.0, RECLAIM_GRACE_SECONDS if grace is None else grace)
    # first let the scope's own cancel run its course: a thread waiting on a killed child unwinds by itself with GateCancelledError
    thread.join(_SETTLE_SECONDS)
    while thread.is_alive():
        _raise_in_thread(thread)
        thread.join(_RECLAIM_RETRY_SECONDS)
        if time.monotonic() >= deadline:
            break
    if thread.is_alive():
        with _LEAKED_LOCK:
            if thread not in _LEAKED:
                _LEAKED.append(thread)
        return False
    return True


def leaked_threads() -> list[threading.Thread]:
    """Abandoned gate threads that are still running (threads that have since ended are dropped from the list)."""

    with _LEAKED_LOCK:
        _LEAKED[:] = [thread for thread in _LEAKED if thread.is_alive()]
        return list(_LEAKED)


def kill_process_tree(process: subprocess.Popen[str]) -> None:
    """Kill ``process`` and everything it started; a process that is already gone is not an error."""

    # taskkill that hangs or fails must not escape (its TimeoutExpired is not an OSError) and must not stop the fallback kill below
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        if _WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=30,
            )
        else:
            killpg = getattr(os, "killpg", None)  # POSIX only; looked up by name so the Windows type check sees no missing attribute
            sigkill = getattr(signal, "SIGKILL", None)
            if killpg is not None and sigkill is not None:
                killpg(process.pid, sigkill)
    with contextlib.suppress(OSError):
        process.kill()


class ProcessScope:
    """The live children of one gate run; thread safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._children: set[subprocess.Popen[str]] = set()
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def enter(self) -> contextvars.Token[ProcessScope | None]:
        """Make this the scope of the calling thread (the gate's worker thread)."""

        return _SCOPE.set(self)

    def register(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            cancelled = self._cancelled
            if not cancelled:
                self._children.add(process)
        if cancelled:  # cancel() ran between the start and the registration: this child must not survive
            kill_process_tree(process)
            raise GateCancelledError("门禁已超时被放弃，不再启动新的子进程")

    def release(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._children.discard(process)

    def cancel(self) -> int:
        """Kill every registered child's process tree and refuse later starts; returns how many children were killed."""

        with self._lock:
            self._cancelled = True
            children = list(self._children)
            self._children.clear()
        for child in children:
            kill_process_tree(child)
        return len(children)


def current_scope() -> ProcessScope | None:
    return _SCOPE.get()


def _start(args: list[str], cwd: Path, env: Mapping[str, str]) -> subprocess.Popen[str]:
    """Start ``args`` as the leader of its own process group, so the whole tree can be killed later."""

    return subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
        args,
        cwd=str(cwd),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if _WINDOWS else 0,
        start_new_session=not _WINDOWS,
    )


def run_in_scope(
    args: Sequence[str], cwd: Path, env: Mapping[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` with the same text settings, whose child is killed with its whole tree on timeout or when the scope is cancelled."""

    scope = current_scope()
    if scope is not None and scope.cancelled:
        raise GateCancelledError("门禁已超时被放弃，不再启动新的子进程")
    process = _start(list(args), cwd, env)
    if scope is not None:
        scope.register(process)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        kill_process_tree(process)
        with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
            process.communicate(timeout=_REAP_SECONDS)  # a grandchild that survived must not hold the read forever
        raise subprocess.TimeoutExpired(list(args), timeout, output=error.output, stderr=error.stderr) from error
    except BaseException:
        kill_process_tree(process)
        raise
    finally:
        if scope is not None:
            scope.release(process)
    if scope is not None and scope.cancelled:
        raise GateCancelledError("门禁已超时被放弃，这次命令行结果不算数")
    return subprocess.CompletedProcess(list(args), process.returncode, stdout, stderr)
