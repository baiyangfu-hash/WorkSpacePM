"""Long jobs outside the agent's terminal: a detached worker, a memory guard that pauses the job, and a status file that is the evidence.

Why (11-03 laptop memory P1): the same regression run detached stays flat for 20 minutes, run in an agent terminal it climbs linearly and fills
the commit limit.  ``main.py long-run start`` starts the command the way the frozen release tools did by hand
(``detach_run.py`` + ``mem_guard.py`` + ``keepawake.py``, card 219 section 5.2) and leaves a status file that ``pm verify`` can later trust.

Layout: ``<control root>/.auto-pm/long-run/<name>/`` (git-ignored)

- ``spec.json``      what to run (written once, before anything starts)
- ``status.json``    ``long-run.v1``: command, cwd, git head, pids, state ``STARTING|RUNNING|DONE|FAILED|STOPPED``, exit code, log hash.
  Written only by ``start`` (the first time) and by the worker (afterwards); never by the guard.
- ``run.log``        the command's combined output
- ``worker.pid``     the worker's pid: the root of the tree the guard may pause
- ``guard.json``     written only by the guard: its pid, samples taken, peak committed GiB, alerts.  A job whose guard never took a sample is
  not "run under mem_guard"
- ``ALERT_*.txt`` / ``PAUSED`` / ``RESUME`` / ``RESUMED_*.txt``  the guard's pause and resume trail (same names as the frozen mem_guard)
- ``DONE`` / ``FAILED``  end markers (the guard and ``status`` stop on them)

Processes: ``start`` launches the worker and the guard, both detached from the caller (own process group, no console, outside the caller's
job object when allowed).  The guard is a **separate** process on purpose: a thread inside the worker would be paused with the tree it
is supposed to pause.  The worker runs the command, waits, and writes the final status.

The status file is evidence of how the job was run, not a security boundary: anyone who can write the control root can edit it, like the
ledger itself (the single-user local trust model of TD-SW008-065).

Standard library only (plus the sibling ``memory_preflight.py``, loaded by path), so the worker and the guard can be started as plain scripts:
``python -B long_run_core.py worker <dir>`` and ``python -B long_run_core.py guard <dir>``.
"""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

SCHEMA = "long-run.v1"
RUN_ROOT = Path(".auto-pm") / "long-run"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
GUARD_LIMIT_GIB = 40.0  # pause the tree at this much committed memory (the frozen mem_guard's default)
GUARD_RESUME_GIB = 36.0  # resume below this
UNOWNED_RISE_GIB = 8.0
GIT_TIMEOUT_SECONDS = 60
#: pytest reads these from the environment and they can select part of a suite (``-k``) or change which plugins run; a long-run record is
#: evidence of the whole command, so the worker removes them (even if the caller's ``env`` adds them) and records what it removed.
STRIPPED_ENV = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD")
GUARD_POLL_SECONDS = 20
#: On Windows a reader that opens a file in the instant ``os.replace`` swaps it gets ``PermissionError`` (winerror 5) or a sharing violation
#: (winerror 32).  The writer keeps the file for microseconds, so a read retries a few times before it calls the file unreadable.
READ_RETRIES = 8
READ_RETRY_SECONDS = 0.05
_SHARING_ERRORS = (5, 32)
MAX_SECONDS = 8 * 3600  # the guard and keep-awake never outlive this
DEFAULT_TIMEOUT_MINUTES = 240
TIMEOUT_EXIT = 124  # what `timeout` returns
END_MARKERS = ("DONE", "FAILED")


class LongRunError(RuntimeError):
    """The job cannot be started, found or stopped; nothing was changed."""


class LongRunMissingError(LongRunError):
    """The file does not exist (as opposed to: it exists but could not be read)."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Replace ``path`` atomically (a reader never sees half a file)."""

    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _is_sharing_error(error: OSError) -> bool:
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in _SHARING_ERRORS


def read_text_retrying(path: Path, *, encoding: str = "utf-8") -> str:
    """The text of ``path``; a permission / sharing error is retried ``READ_RETRIES`` times, every other error at once.

    ``LongRunMissingError`` when the file does not exist; ``LongRunError`` (naming how often it retried) when it exists but cannot be read.
    """

    retries = 0
    while True:
        try:
            return path.read_text(encoding=encoding)
        except FileNotFoundError as error:
            raise LongRunMissingError(f"没有 {path.name}") from error
        except UnicodeDecodeError as error:  # a ValueError, not an OSError: undecodable bytes are not a race either
            raise LongRunError(f"读不了 {path.name}：{type(error).__name__}（未重试）") from error
        except OSError as error:
            if not _is_sharing_error(error):
                raise LongRunError(f"读不了 {path.name}：{type(error).__name__}（未重试）") from error
            if retries >= READ_RETRIES:
                raise LongRunError(f"读不了 {path.name}：{type(error).__name__}（已重试 {retries} 次）") from error
            retries += 1
            time.sleep(READ_RETRY_SECONDS)


def _read_json(path: Path) -> dict[str, Any]:
    text = read_text_retrying(path)
    try:
        value = json.loads(text)
    except ValueError as error:  # ValueError covers broken JSON; the writer replaces the file atomically, so this is not a race
        raise LongRunError(f"读不了 {path.name}：{type(error).__name__}（未重试）") from error
    if not isinstance(value, dict):
        raise LongRunError(f"{path.name} 格式不对")
    return value


def read_json_file(path: Path) -> dict[str, Any]:
    """Public reader for the files of a run directory: ``LongRunMissingError`` when absent, ``LongRunError`` when present but unreadable or not an object."""

    return _read_json(path)


def _sibling(module_name: str, loaded_as: str) -> ModuleType:
    """A sibling module of this package: the package module when ``auto_pm`` is importable (so tests and callers share one copy),
    otherwise the file next to this one loaded by path, so this file also works when run as a plain script."""

    try:
        return importlib.import_module(f"auto_pm.infrastructure.{module_name}")
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(loaded_as, Path(__file__).with_name(f"{module_name}.py"))
    if spec is None or spec.loader is None:
        raise LongRunError(f"找不到 {module_name} 模块")
    module = importlib.util.module_from_spec(spec)
    sys.modules[loaded_as] = module  # dataclasses look the module up by name while it executes
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(loaded_as, None)
    return module


def _preflight_module() -> ModuleType:
    return _sibling("memory_preflight", "long_run_memory_preflight")


def _find_git() -> str | None:
    """``git`` found the cockpit's way (never ``shutil.which``: on Windows it searches the working directory first)."""

    found: str | None = _sibling("executable_lookup", "long_run_executable_lookup").find_on_path("git")
    return found


# ---------------------------------------------------------------- process tree (platform specific)
if sys.platform == "win32":
    from ctypes import wintypes

    class _ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    _PROCESS_SUSPEND_RESUME = 0x0800
    _PROCESS_TERMINATE = 0x0001
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _DETACHED_PROCESS = 0x00000008
    _CREATE_NEW_PROCESS_GROUP = 0x00000200
    _CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    _CREATE_NO_WINDOW = 0x08000000

    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def _kernel() -> Any:
        """kernel32 with explicit argument and result types (a 64-bit handle must not be squeezed into a 32-bit int)."""

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
        kernel.Process32FirstW.restype = wintypes.BOOL
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
        kernel.Process32NextW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        kernel.SetThreadExecutionState.restype = wintypes.DWORD
        return kernel

    def _children() -> dict[int, list[int]] | None:
        """parent pid -> child pids from a Toolhelp snapshot; ``None`` when no snapshot could be taken."""

        kernel = _kernel()
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:  # NULL or INVALID_HANDLE_VALUE
            return None
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        children: dict[int, list[int]] = {}
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            children.setdefault(int(entry.th32ParentProcessID), []).append(int(entry.th32ProcessID))
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        kernel.CloseHandle(snapshot)
        return children

    def pid_alive(pid: int) -> bool:
        """Whether ``pid`` is a process that has not exited (``GetExitCodeProcess`` says ``STILL_ACTIVE``)."""

        if pid <= 0:
            return False
        kernel = _kernel()
        handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return bool(ctypes.get_last_error() == _ERROR_ACCESS_DENIED)  # it exists, we are only not allowed to look
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == _STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)

    def process_tree(root: int) -> list[int]:
        """``root`` and all its descendants; empty when ``root`` does not exist (a dead pid has no tree)."""

        if not pid_alive(root):
            return []
        children = _children()
        if children is None:
            return [root]  # no snapshot: at least the process we know about
        found: list[int] = []
        todo = [root]
        while todo:
            pid = todo.pop()
            if pid in found:
                continue
            found.append(pid)
            todo.extend(children.get(pid, []))
        return found

    def _act(pids: list[int], function: str, access: int) -> int:
        kernel = _kernel()
        ntdll = ctypes.WinDLL("ntdll")
        routine = getattr(ntdll, function)
        routine.argtypes = [wintypes.HANDLE]
        routine.restype = ctypes.c_long
        done = 0
        for pid in pids:
            handle = kernel.OpenProcess(access, False, pid)
            if handle:
                routine(handle)
                kernel.CloseHandle(handle)
                done += 1
        return done

    def suspend(pids: list[int]) -> int:
        return _act(pids, "NtSuspendProcess", _PROCESS_SUSPEND_RESUME)

    def resume(pids: list[int]) -> int:
        return _act(pids, "NtResumeProcess", _PROCESS_SUSPEND_RESUME)

    def kill_tree(root: int) -> None:
        with contextlib.suppress(subprocess.TimeoutExpired):
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(root)], capture_output=True, check=False, timeout=30)  # noqa: S603, S607

    def keep_awake(on: bool) -> None:
        """Ask Windows not to sleep (the call is per thread: the guard repeats it from its own loop)."""

        _kernel().SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED if on else _ES_CONTINUOUS)

    def detach_flags() -> tuple[int, ...]:
        """Strongest first: leave the caller's job object when allowed, else only the process group and console."""

        base = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
        return (base | _CREATE_BREAKAWAY_FROM_JOB, base)

else:

    def process_tree(root: int) -> list[int]:
        """``root`` and all its descendants (/proc parent links); empty when ``root`` does not exist."""

        if not (Path("/proc") / str(root)).exists():
            return []
        children: dict[int, list[int]] = {}
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text(encoding="utf-8")
                parent = int(stat.rsplit(")", 1)[1].split()[1])  # field 4, after the "(comm)" which may hold spaces
            except (OSError, ValueError, IndexError):
                continue
            children.setdefault(parent, []).append(int(entry.name))
        found: list[int] = []
        todo = [root]
        while todo:
            pid = todo.pop()
            if pid in found:
                continue
            found.append(pid)
            todo.extend(children.get(pid, []))
        return found

    def _signal_all(pids: list[int], number: int) -> int:
        done = 0
        for pid in pids:
            with contextlib.suppress(OSError):
                os.kill(pid, number)
                done += 1
        return done

    def suspend(pids: list[int]) -> int:
        return _signal_all(pids, signal.SIGSTOP)

    def resume(pids: list[int]) -> int:
        return _signal_all(pids, signal.SIGCONT)

    def kill_tree(root: int) -> None:
        pids = process_tree(root)
        resume(pids)  # a stopped process cannot act on SIGKILL's cleanup, and its children would otherwise stay stopped
        _signal_all(pids, signal.SIGKILL)

    def keep_awake(on: bool) -> None:
        return None

    def detach_flags() -> tuple[int, ...]:
        return (0,)

    def pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        try:  # a finished child nobody has waited for yet is a zombie: it exists, but it is not running
            state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
        except (OSError, ValueError, IndexError):
            return True
        return state != "Z"


def launch_detached(argv: list[str], log: Path, cwd: Path) -> int:
    """Start ``argv`` detached from the caller (no console, own process group, own session); its output goes to ``log``.  Returns the pid."""

    last: OSError | None = None
    with log.open("ab", buffering=0) as handle:
        for flags in detach_flags():
            try:
                if sys.platform == "win32":
                    child = subprocess.Popen(  # noqa: S603
                        argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, creationflags=flags, close_fds=True
                    )
                else:
                    child = subprocess.Popen(  # noqa: S603
                        argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True
                    )
                return child.pid
            except OSError as error:
                last = error
    raise LongRunError(f"启动不了脱离终端的进程：{last}")


# ---------------------------------------------------------------- the worker
def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _update_status(run_dir: Path, **changes: Any) -> dict[str, Any]:
    status = _read_json(run_dir / "status.json")
    status.update(changes)
    _write_json(run_dir / "status.json", status)
    return status


def worker_main(run_dir: Path) -> int:
    """Run the command from ``spec.json``, wait for it, and write the final status and the DONE/FAILED marker.  Returns the command's exit code."""

    spec = _read_json(run_dir / "spec.json")
    (run_dir / "worker.pid").write_text(str(os.getpid()), encoding="ascii")
    log = run_dir / "run.log"
    argv = [str(item) for item in spec["argv"]]
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    # No lease credential reaches the job (the same rule as the acceptance runner); the spec adds the variables the caller asked for.
    environment = {key: value for key, value in os.environ.items() if "LEASE" not in key.upper()}
    environment.update({str(key): str(value) for key, value in dict(spec.get("env") or {}).items()})
    stripped = sorted(name for name in environment if name.upper() in STRIPPED_ENV)
    for name in stripped:
        del environment[name]
    try:
        with log.open("ab", buffering=0) as out:
            child = subprocess.Popen(  # noqa: S603
                argv, cwd=spec["cwd"], env=environment, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, creationflags=flags
            )
            _update_status(
                run_dir, state="RUNNING", detached=True, child_pid=child.pid, worker_pid=os.getpid(), running_at=_now(), env_stripped=stripped
            )
            try:
                code = child.wait(timeout=spec["timeout_seconds"])
            except subprocess.TimeoutExpired:
                kill_tree(child.pid)
                child.wait()
                code = TIMEOUT_EXIT
    except OSError as error:
        with log.open("ab") as out:
            out.write(f"long-run: cannot start the command: {error}\n".encode())
        code = 127
    digest, size = _sha256(log) if log.exists() else ("", 0)
    stopped = (run_dir / "STOP").exists()
    final = "STOPPED" if stopped else ("DONE" if code == 0 else "FAILED")
    peak: float | None = None
    guard_error: str | None = None
    try:
        peak = _read_json(run_dir / "guard.json").get("peak_committed_gib")
    except LongRunMissingError:
        pass  # the guard never wrote its file: no peak, which the verifier sees as "the guard did not sample"
    except LongRunError as error:
        guard_error = str(error)  # present but unreadable is not the same as absent: say so in the record
    changes: dict[str, Any] = {"guard_read_error": guard_error} if guard_error else {}
    _update_status(run_dir, state=final, exit_code=code, ended_at=_now(), log_sha256=digest, log_bytes=size, peak_committed_gib=peak, **changes)
    (run_dir / ("DONE" if final == "DONE" else "FAILED")).write_text(f"{_now()} exit {code}\n", encoding="utf-8")
    return code


# ---------------------------------------------------------------- the guard
def guard_loop(
    run_dir: Path,
    *,
    read_committed_gib: Callable[[], float | None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    limit_gib: float = GUARD_LIMIT_GIB,
    resume_gib: float = GUARD_RESUME_GIB,
    poll_seconds: float = GUARD_POLL_SECONDS,
    max_seconds: float = MAX_SECONDS,
    tree: Callable[[int], list[int]] = process_tree,
    pause: Callable[[list[int]], int] = suspend,
    unpause: Callable[[list[int]], int] = resume,
    awake: Callable[[bool], None] = keep_awake,
    read_unowned_gib: Callable[[], float | None] | None = None,
    unowned_rise_gib: float = UNOWNED_RISE_GIB,
) -> None:
    """Watch the system commit charge until the job ends (``DONE``/``FAILED``) or ``max_seconds``.

    At ``limit_gib`` committed the worker's whole process tree is paused (``ALERT_<time>.txt`` and ``PAUSED``); it is resumed when the charge
    falls below ``resume_gib`` or a ``RESUME`` file appears.  Also keeps the machine awake while it watches, and records the peak in ``guard.json``.

    Besides, it records (does not pause) an alert each time the commit that no readable process owns has grown by ``unowned_rise_gib`` over
    the first reading of this run: that growth is invisible to the per-process numbers (11-03 coordinator ruling).
    """

    if read_committed_gib is None:
        preflight = _preflight_module()
        if read_unowned_gib is None:
            read_unowned_gib = preflight.read_unowned_gib

        def read_committed_gib() -> float | None:
            snapshot = preflight.read_commit()
            return None if snapshot is None else float(snapshot.committed) / preflight.GIB

    paused: list[int] = []
    started = clock()
    unowned_baseline: float | None = None
    unowned_steps = 0
    state: dict[str, Any] = {"schema_version": SCHEMA, "guard_pid": os.getpid(), "started_at": _now(), "samples": 0, "peak_committed_gib": 0.0, "alerts": []}
    _write_json(run_dir / "guard.json", state)
    try:
        while clock() - started < max_seconds:
            # STOP: ``stop`` was asked, it unfreezes and kills.  A job that has already ended is still sampled once (below), so a short job
            # that finishes before this process has even started leaves evidence that the guard looked, instead of an empty record.
            ended = any((run_dir / marker).exists() for marker in (*END_MARKERS, "STOPPED", "STOP"))
            if ended and state["samples"] > 0:
                break
            awake(True)
            committed = read_committed_gib()
            if committed is not None:
                state["samples"] += 1
                state["peak_committed_gib"] = max(float(state["peak_committed_gib"]), round(committed, 2))
                state["last_committed_gib"] = round(committed, 2)
                state["last_sample_at"] = _now()
                _write_json(run_dir / "guard.json", state)  # at once: the first sample must be visible long before the (slower) process listing below
                if ended:
                    pass  # nothing left to protect: no pause, no resume
                elif not paused and committed >= limit_gib:
                    root = _worker_pid(run_dir)
                    members = tree(root) if root else []  # an empty tree: the worker is gone, there is nothing to pause (and nothing to alert about)
                    if members:
                        paused = members
                        count = pause(paused)
                        text = f"{_now()} committed {committed:.1f} GiB >= {limit_gib:g} GiB: paused {count} processes of the tree of pid {root}\n"
                        (run_dir / f"ALERT_{int(time.time())}.txt").write_text(text, encoding="utf-8")
                        (run_dir / "PAUSED").write_text(f"{_now()} committed {committed:.1f} GiB\n", encoding="utf-8")
                        state["alerts"].append(text.strip())
                elif paused and (committed < resume_gib or (run_dir / "RESUME").exists()):
                    count = unpause(paused)
                    (run_dir / "PAUSED").unlink(missing_ok=True)
                    (run_dir / "RESUME").unlink(missing_ok=True)
                    (run_dir / f"RESUMED_{int(time.time())}.txt").write_text(
                        f"{_now()} committed {committed:.1f} GiB: resumed {count} processes\n", encoding="utf-8"
                    )
                    paused = []
            unowned = read_unowned_gib() if read_unowned_gib is not None else None
            if unowned is not None:
                if unowned_baseline is None:
                    unowned_baseline = unowned
                    state["unowned_baseline_gib"] = round(unowned, 2)
                state["last_unowned_gib"] = round(unowned, 2)
                state["peak_unowned_gib"] = max(float(state.get("peak_unowned_gib", 0.0)), round(unowned, 2))
                steps = int((unowned - unowned_baseline) // unowned_rise_gib) if unowned_rise_gib > 0 else 0
                if steps > unowned_steps:
                    text = (
                        f"{_now()} unowned commit {unowned:.1f} GiB is {unowned - unowned_baseline:.1f} GiB above the start "
                        f"({unowned_baseline:.1f} GiB), more than {unowned_rise_gib * steps:g} GiB: close Trae and browsers, keep the fast_watch log\n"
                    )
                    (run_dir / f"ALERT_UNOWNED_{int(time.time())}.txt").write_text(text, encoding="utf-8")
                    state["alerts"].append(text.strip())
                unowned_steps = max(unowned_steps, steps)
            _write_json(run_dir / "guard.json", state)
            if ended:
                break
            sleep(poll_seconds)
    finally:
        if paused:
            unpause(paused)  # never leave the job frozen when the guard goes away
        awake(False)
        _write_json(run_dir / "guard.json", state)


def _worker_pid(run_dir: Path) -> int:
    try:
        return int(read_text_retrying(run_dir / "worker.pid", encoding="ascii").strip())
    except LongRunMissingError:
        return 0  # not written yet (or already cleaned up)
    except ValueError:
        return 0  # written half a second ago: an empty or partial pid


# ---------------------------------------------------------------- start / status / stop
def _abandon(run_dir: Path, reason: str, pids: list[int]) -> None:
    """A start that cannot complete: take down what was already started and leave a FAILED record (no exit code: it never ran)."""

    for pid in pids:
        kill_tree(pid)
    (run_dir / "STOP").write_text(f"{_now()}\n", encoding="utf-8")
    _update_status(run_dir, state="FAILED", exit_code=None, ended_at=_now(), error=reason)
    (run_dir / "FAILED").write_text(f"{_now()} {reason}\n", encoding="utf-8")


def run_directory(control_root: str | Path, name: str) -> Path:
    if NAME_RE.fullmatch(name) is None:
        raise LongRunError("任务名只能用字母、数字、点、下划线、连字符，且不超过 64 个字符")
    return Path(control_root).resolve() / RUN_ROOT / name


def _git_head(cwd: Path) -> str:
    git = _find_git()
    if git is None:
        return ""
    try:
        done = subprocess.run([git, "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, check=False, timeout=GIT_TIMEOUT_SECONDS)  # noqa: S603
    except subprocess.TimeoutExpired:
        return ""
    if done.returncode != 0:
        return ""
    try:
        return done.stdout.decode("ascii").strip()
    except ValueError:  # not a commit id: report nothing rather than guess
        return ""


def _git_dirty(cwd: Path) -> bool | None:
    """Whether tracked files in ``cwd`` differ from HEAD (the evidence is only worth something for committed code); ``None`` when git cannot say."""

    git = _find_git()
    if git is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603
            [git, "-C", str(cwd), "status", "--porcelain", "--untracked-files=no"], capture_output=True, check=False, timeout=GIT_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return None
    return bool(done.stdout.strip()) if done.returncode == 0 else None


def start(
    control_root: str | Path,
    name: str,
    argv: list[str],
    *,
    cwd: str | Path,
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
    python: str | None = None,
    poll_seconds: float = GUARD_POLL_SECONDS,
    worktree: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the memory preflight, then start ``argv`` under a detached worker and a guard.  Returns the initial status.

    A name that was used before is refused (the old run is evidence and is never overwritten).

    ``worktree`` is the tree whose code the job judges (a governed Run's worktree) when it is not the directory the job runs in: the status
    file records that tree's ``git_head`` / ``git_dirty`` instead, which is what ``pm verify`` compares.  ``env`` is added to the job's environment.
    """

    if not argv:
        raise LongRunError("没有给出要跑的命令（把命令写在 -- 后面）")
    working = Path(cwd).resolve()
    if not working.is_dir():
        raise LongRunError(f"工作目录不存在：{working}")
    preflight = _preflight_module()
    try:
        preflight.require_headroom()
    except preflight.MemoryPreflightRefusedError as error:
        raise LongRunError(str(error)) from error
    judged = Path(worktree).resolve() if worktree is not None else working
    if not judged.is_dir():
        raise LongRunError(f"工作树不存在：{judged}")
    run_dir = run_directory(control_root, name)
    if run_dir.exists():
        raise LongRunError(f"任务名 {name} 已经用过（{run_dir}）；旧记录是证据，不覆盖，请换一个名字")
    try:
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir()  # exist_ok stays False: of two starts with the same name at the same moment exactly one wins
    except FileExistsError as error:
        raise LongRunError(f"任务名 {name} 刚被另一个启动占用了；旧记录是证据，不覆盖，请换一个名字") from error
    except OSError as error:
        raise LongRunError(f"建不了任务目录 {run_dir}：{error}（任务名不能是系统保留名）") from error
    interpreter = python or sys.executable
    script = str(Path(__file__).resolve())
    status: dict[str, Any] = {
        "schema_version": SCHEMA,
        "name": name,
        "command": list(argv),
        "command_text": subprocess.list2cmdline(list(argv)),
        "cwd": str(working),
        "worktree": str(judged),
        "git_head": _git_head(judged),
        "git_dirty": _git_dirty(judged),
        "mem_guard": False,  # becomes true only once the guard process has really been started
        "state": "STARTING",
        "detached": False,  # likewise for the worker
        "guard_file": "guard.json",
        "started_at": _now(),
        "timeout_minutes": timeout_minutes,
        "log": str(run_dir / "run.log"),
    }
    spec = {"argv": list(argv), "cwd": str(working), "timeout_seconds": timeout_minutes * 60, "guard_poll_seconds": poll_seconds, "env": dict(env or {})}
    _write_json(run_dir / "spec.json", spec)
    _write_json(run_dir / "status.json", status)
    # The guard first: a job must never run unprotected.  If the worker cannot start afterwards, the guard is taken down with it.
    try:
        guard = launch_detached([interpreter, "-B", script, "guard", str(run_dir)], run_dir / "guard.out", working)
    except (OSError, LongRunError) as error:
        _abandon(run_dir, f"内存守卫起不来（{error}），任务没有启动", [])
        raise LongRunError(f"内存守卫起不来（{error}）；任务没有启动，没有无保护地跑") from error
    _update_status(run_dir, mem_guard=True, guard_launcher_pid=guard)
    try:
        worker = launch_detached([interpreter, "-B", script, "worker", str(run_dir)], run_dir / "worker.out", working)
    except (OSError, LongRunError) as error:
        _abandon(run_dir, f"工作进程起不来（{error}）", [guard])
        raise LongRunError(f"工作进程起不来（{error}）；已收掉守卫") from error
    status.update(mem_guard=True, detached=True)  # the file says so too, once the worker has started and written its first update
    status["launcher_pids"] = {"worker": worker, "guard": guard}
    return status


def read_status(run_dir: Path) -> dict[str, Any]:
    """The status file plus the guard's file (read-only); ``worker_alive`` says whether the worker process still exists."""

    if not run_dir.is_dir():
        raise LongRunError(f"没有这个任务：{run_dir.name}")
    status = _read_json(run_dir / "status.json")
    guard: dict[str, Any] = {}
    guard_error: str | None = None
    try:
        guard = _read_json(run_dir / "guard.json")
    except LongRunMissingError:
        pass  # no guard file yet
    except LongRunError as error:
        guard_error = str(error)
    status["guard"] = {
        "samples": guard.get("samples", 0),
        "peak_committed_gib": guard.get("peak_committed_gib"),
        "last_committed_gib": guard.get("last_committed_gib"),
        "alerts": guard.get("alerts", []),
        "paused": (run_dir / "PAUSED").exists(),
        **({"error": guard_error} if guard_error else {}),
    }
    pid = _worker_pid(run_dir)
    status["worker_alive"] = pid_alive(pid) if pid else False
    return status


def stop(run_dir: Path) -> dict[str, Any]:
    """Stop a running job: resume it if paused, kill its tree and let the worker record ``STOPPED``."""

    if not run_dir.is_dir():
        raise LongRunError(f"没有这个任务：{run_dir.name}")
    status = _read_json(run_dir / "status.json")
    if status.get("state") in {"DONE", "FAILED", "STOPPED"}:
        return read_status(run_dir)
    (run_dir / "STOP").write_text(f"{_now()}\n", encoding="utf-8")
    pid = _worker_pid(run_dir)
    child = int(status.get("child_pid") or 0)
    # The guard freezes the worker together with the job; a frozen worker cannot write STOPPED, so unfreeze the whole tree first.
    resume(process_tree(pid) if pid else [])
    if child:
        resume(process_tree(child))
        kill_tree(child)
    (run_dir / "PAUSED").unlink(missing_ok=True)
    if pid:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and pid_alive(pid):
            time.sleep(0.2)
    return read_status(run_dir)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "worker":
        return worker_main(Path(argv[2]))
    if len(argv) == 3 and argv[1] == "guard":
        run_dir = Path(argv[2])
        poll = float(_read_json(run_dir / "spec.json").get("guard_poll_seconds", GUARD_POLL_SECONDS))
        guard_loop(run_dir, poll_seconds=poll)
        return 0
    print("usage: long_run_core.py worker|guard <run dir>", file=sys.stderr)  # noqa: T201
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
