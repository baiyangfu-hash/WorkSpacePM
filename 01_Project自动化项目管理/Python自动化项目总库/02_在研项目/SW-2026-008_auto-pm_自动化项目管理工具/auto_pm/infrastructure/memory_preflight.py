"""Pre-launch memory check for long jobs: refuse to start when the system commit charge is already too high (11-03 laptop memory P1).

Why: the same regression run detached stays flat for 20 minutes, run in an agent's terminal it climbs linearly and fills the commit limit
(every test builds a real Git repository).  A job started on a machine that is already close to the limit only makes it worse, so
``pm verify`` and ``scripts/long_gate.py launch`` ask this module first.

Rule (the coordinator's ruling of 11-03, measured by the main executor on the 31.3 GiB laptop): refuse when the committed memory is at
least ``ABSOLUTE_GIB`` GiB **or** at least ``RATIO`` of the current commit limit.  There is deliberately no environment switch or option
to continue anyway: an agent could set it, and the check exists to stop agents.

Readings (``\\Memory\\Committed Bytes`` and the current limit):

- Windows: ``psapi.GetPerformanceInfo`` (CommitTotal / CommitLimit in pages), no subprocess and no locale dependent counter output.
- Linux: ``/proc/meminfo`` ``Committed_AS`` / ``CommitLimit`` (cloud sessions and tests only).
- Anything else, or a failed reading: unknown.  Unknown is **refused on Windows** (the machine this guards) and passed with an
  "unverified" note elsewhere.

Standard library only and no import of other ``auto_pm`` modules, so ``scripts/long_gate.py`` can load this file by path.
Every reading function can be replaced by the caller (tests); nothing is read when the module is imported.
"""

from __future__ import annotations

import atexit
import contextlib
import ctypes
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")
GIB = 2**30
ABSOLUTE_GIB = 35.0
RATIO = 0.85
TOP_COUNT = 5
#: Committed memory that no readable process owns (committed minus the sum of readable per-process private commit).  The laptop's normal
#: baseline is about 17.5 GiB (unreadable system processes, kernel pools, shared sections); the 11-03 incident was estimated at 45-55 GiB.
UNOWNED_ALERT_GIB = 25.0
LONG_RUN_USAGE = "python main.py long-run start --name <任务名> -- <命令…>"


class MemoryPreflightRefusedError(RuntimeError):
    """The machine has no memory headroom for a long job; the message is the plain-words refusal."""


@dataclass(frozen=True)
class CommitSnapshot:
    """System-wide commit charge in bytes: what is committed now, the current limit, and the installed physical memory."""

    committed: int
    limit: int
    physical: int


@dataclass(frozen=True)
class ProcessUse:
    """One process and the private memory it has committed (bytes)."""

    pid: int
    name: str
    committed: int


@dataclass(frozen=True)
class Preflight:
    """The verdict: ``ok`` is False when a rule fired or (on Windows) nothing could be read."""

    ok: bool
    reasons: tuple[str, ...]
    snapshot: CommitSnapshot | None
    top: tuple[ProcessUse, ...]
    unverified: str = ""
    #: Sum of the private commit of every process that could be read; None when no process list was available.
    #: The part of the committed memory that no process owns (``committed - attributed``) is what the top five cannot point at.
    attributed: int | None = None


def _gib(value: int) -> str:
    return f"{value / GIB:.1f}"


# ---------------------------------------------------------------- readings
if sys.platform == "win32":
    from ctypes import wintypes

    class _PerformanceInformation(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("CommitTotal", ctypes.c_size_t),
            ("CommitLimit", ctypes.c_size_t),
            ("CommitPeak", ctypes.c_size_t),
            ("PhysicalTotal", ctypes.c_size_t),
            ("PhysicalAvailable", ctypes.c_size_t),
            ("SystemCache", ctypes.c_size_t),
            ("KernelTotal", ctypes.c_size_t),
            ("KernelPaged", ctypes.c_size_t),
            ("KernelNonpaged", ctypes.c_size_t),
            ("PageSize", ctypes.c_size_t),
            ("HandleCount", wintypes.DWORD),
            ("ProcessCount", wintypes.DWORD),
            ("ThreadCount", wintypes.DWORD),
        ]

    class _ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


    def _read_commit_windows() -> CommitSnapshot | None:
        info = _PerformanceInformation()
        info.cb = ctypes.sizeof(info)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetPerformanceInfo.argtypes = [ctypes.POINTER(_PerformanceInformation), wintypes.DWORD]
        psapi.GetPerformanceInfo.restype = wintypes.BOOL
        if not psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
            return None
        page = int(info.PageSize)
        return CommitSnapshot(
            committed=int(info.CommitTotal) * page, limit=int(info.CommitLimit) * page, physical=int(info.PhysicalTotal) * page
        )


    def _all_windows() -> tuple[ProcessUse, ...]:
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCountersEx), wintypes.DWORD]
        capacity = 8192
        pids = (wintypes.DWORD * capacity)()
        returned = wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(returned)):
            return ()
        found: list[ProcessUse] = []
        for index in range(min(returned.value // ctypes.sizeof(wintypes.DWORD), capacity)):
            pid = int(pids[index])
            handle = kernel.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                continue
            try:
                counters = _ProcessMemoryCountersEx()
                counters.cb = ctypes.sizeof(counters)
                if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    continue
                buffer = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(buffer))
                name = buffer.value.rsplit("\\", 1)[-1] if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else "?"
                found.append(ProcessUse(pid=pid, name=name or "?", committed=int(counters.PrivateUsage)))
            finally:
                kernel.CloseHandle(handle)
        return tuple(sorted(found, key=lambda item: item.committed, reverse=True))

else:

    def _read_commit_windows() -> CommitSnapshot | None:
        return None

    def _all_windows() -> tuple[ProcessUse, ...]:
        return ()


def _guarded(read: Callable[[], T], fallback: T) -> T:
    """``read()``, or ``fallback`` when it fails in any way: a reading that cannot be taken is "unreadable" (refused on Windows), never a stack trace."""

    try:
        return read()
    except Exception:  # noqa: BLE001 - ctypes raises ArgumentError/AttributeError/TypeError as well as OSError
        return fallback


def _meminfo_kib(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        fields = rest.split()
        if fields and fields[0].isdigit():
            values[name.strip()] = int(fields[0])
    return values


def _read_commit_linux(meminfo: Path = Path("/proc/meminfo"), overcommit: Path = Path("/proc/sys/vm/overcommit_memory")) -> CommitSnapshot | None:
    """``/proc/meminfo`` read as a commit charge.  ``CommitLimit`` is only a limit in strict mode (``overcommit_memory`` = 2); otherwise it is
    advisory (a 16 GiB sandbox reports 8 GiB), so the limit is reported as unknown (0) and the percentage rule does not fire on it."""

    try:
        values = _meminfo_kib(meminfo.read_text(encoding="utf-8"))
        try:
            strict = overcommit.read_text(encoding="ascii").strip() == "2"
        except (OSError, ValueError):
            strict = False
        return CommitSnapshot(
            committed=values["Committed_AS"] * 1024, limit=values["CommitLimit"] * 1024 if strict else 0, physical=values["MemTotal"] * 1024
        )
    except (OSError, KeyError, ValueError):  # ValueError: undecodable bytes are "unreadable", never silently replaced
        return None


if sys.platform == "win32":

    def read_commit() -> CommitSnapshot | None:
        """The system commit charge now, or ``None`` when it cannot be read."""

        return _guarded(_read_commit_windows, None)

else:

    def read_commit() -> CommitSnapshot | None:
        """The system commit charge now, or ``None`` when it cannot be read."""

        return _read_commit_linux() if sys.platform.startswith("linux") else None


def _all_linux(proc: Path = Path("/proc")) -> tuple[ProcessUse, ...]:
    found: list[ProcessUse] = []
    try:
        entries = list(proc.iterdir())
    except OSError:
        return ()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            values = {}
            name = "?"
            for line in (entry / "status").read_text(encoding="utf-8").splitlines():
                key, _, rest = line.partition(":")
                if key == "Name":
                    name = rest.strip() or "?"
                elif key == "VmData":
                    values[key] = int(rest.split()[0]) * 1024
            found.append(ProcessUse(pid=int(entry.name), name=name, committed=values.get("VmData", 0)))
        except (OSError, ValueError, IndexError):
            continue
    return tuple(sorted(found, key=lambda item: item.committed, reverse=True))


if sys.platform == "win32":

    def all_processes() -> tuple[ProcessUse, ...]:
        """Every process whose private (committed) memory can be read, biggest first; the others (protected, vanished) are skipped."""

        return _guarded(_all_windows, ())

else:

    def all_processes() -> tuple[ProcessUse, ...]:
        """Every process whose private (committed) memory can be read, biggest first; the others (protected, vanished) are skipped."""

        return _all_linux() if sys.platform.startswith("linux") else ()


# ---------------------------------------------------------------- the rule
def check(
    snapshot: CommitSnapshot,
    top: tuple[ProcessUse, ...] = (),
    *,
    absolute_gib: float = ABSOLUTE_GIB,
    ratio: float = RATIO,
) -> Preflight:
    """Apply the two rules to a reading: committed >= absolute GiB, or committed / limit >= ratio (both inclusive)."""

    reasons: list[str] = []
    if snapshot.committed >= absolute_gib * GIB:
        reasons.append(f"已提交内存 {_gib(snapshot.committed)} GiB ≥ {absolute_gib:g} GiB")
    if snapshot.limit > 0 and snapshot.committed / snapshot.limit >= ratio:
        reasons.append(f"已提交内存占当前提交上限的 {snapshot.committed / snapshot.limit:.0%} ≥ {ratio:.0%}")
    return Preflight(ok=not reasons, reasons=tuple(reasons), snapshot=snapshot, top=top)


def run_preflight(
    *,
    read: Callable[[], CommitSnapshot | None] | None = None,
    list_all: Callable[[], tuple[ProcessUse, ...]] | None = None,
    platform: str | None = None,
) -> Preflight:
    """Read the machine and judge.  The processes are listed (five biggest, plus the total) only when the verdict is a refusal.

    The readers are looked up when called, not bound as defaults, so a test can replace ``read_commit`` / ``all_processes`` on the module.
    """

    snapshot = (read or read_commit)()
    if snapshot is None:
        if (platform or sys.platform) == "win32":
            return Preflight(ok=False, reasons=("读不到已提交内存（无法确认机器有余量，按规矩拒绝）",), snapshot=None, top=())
        return Preflight(ok=True, reasons=(), snapshot=None, top=(), unverified="本机读不到已提交内存，内存预检未验证")
    verdict = check(snapshot)
    if verdict.ok:
        return verdict
    processes = tuple(sorted((list_all or all_processes)(), key=lambda item: item.committed, reverse=True))
    return Preflight(
        ok=False,
        reasons=verdict.reasons,
        snapshot=snapshot,
        top=processes[:TOP_COUNT],
        attributed=sum(use.committed for use in processes) if processes else None,
    )


def unowned_commit(committed: int, attributed: int) -> int:
    """Committed memory that no readable process owns, floored at zero."""

    return max(committed - attributed, 0)


def read_unowned_gib() -> float | None:
    """The unowned commit now, in GiB; ``None`` when the commit charge or the process list cannot be read.  Used by the long-run guard."""

    snapshot = read_commit()
    processes = all_processes()
    if snapshot is None or not processes:
        return None
    return unowned_commit(snapshot.committed, sum(use.committed for use in processes)) / GIB


def refusal_text(result: Preflight) -> str:
    """The plain-words refusal: what was read, which rule fired, the five biggest processes, and what to do."""

    lines = ["拒绝启动：这台电脑的已提交内存已经太高，再起长任务会把它拖垮。"]
    snapshot = result.snapshot
    if snapshot is not None:
        share = f"{snapshot.committed / snapshot.limit:.0%}" if snapshot.limit > 0 else "未知"
        lines.append(
            f"当前已提交 {_gib(snapshot.committed)} GiB，提交上限 {_gib(snapshot.limit)} GiB（占 {share}），物理内存 {_gib(snapshot.physical)} GiB。"
        )
    lines.append("触发：" + "；".join(result.reasons) + "。")
    if result.top:
        lines.append(f"占用最大的 {len(result.top)} 个进程（私有已提交内存）：")
        lines.extend(f"  {number}. {use.name}（PID {use.pid}）{_gib(use.committed)} GiB" for number, use in enumerate(result.top, 1))
    if snapshot is not None and result.attributed is not None:
        unowned = unowned_commit(snapshot.committed, result.attributed)
        detail = f"（= 已提交 {_gib(snapshot.committed)} − 能读到的进程私有合计 {_gib(result.attributed)}；含读不到的系统进程和内核）"
        if unowned > UNOWNED_ALERT_GIB * GIB:
            lines.append(
                f"**未归属进程的提交量 {_gib(unowned)} GiB，超过 {UNOWNED_ALERT_GIB:g} GiB：提交量不在任何进程里，上面的前几名指不出元凶。"
                f"先关闭 Trae、浏览器，并保留 fast_watch 日志。**{detail}"
            )
        else:
            lines.append(f"未归属进程的提交量：{_gib(unowned)} GiB，未超过 {UNOWNED_ALERT_GIB:g} GiB，上面的前几名就是主要占用。{detail}")
    lines.append(
        f"怎么办：关掉上面没用的程序（尤其是还在跑的 pytest、浏览器、后台终端），等已提交回落到 {ABSOLUTE_GIB:g} GiB 以下再启动；"
        f"要跑的长任务（超过 10 分钟或超过 100 个用例的回归）请用 {LONG_RUN_USAGE}，它会脱离终端、带内存保护地跑。"
        "这个检查没有“强行继续”的选项。"
    )
    return "\n".join(lines)


def require_headroom(*, run: Callable[[], Preflight] | None = None, label: str | None = None, timeout_seconds: float | None = None) -> str:
    """Raise ``MemoryPreflightRefusedError`` with the refusal text when the preflight fails; return the "unverified" note (possibly empty) otherwise.

    With ``label`` the caller is also armed for the memory gate (D-168, see ``arm``) once the preflight has passed: the gate only freezes
    inside the trees of processes that armed themselves for a heavy job.  Arming never raises and never changes the preflight's verdict.
    """

    result = (run or run_preflight)()
    if not result.ok:
        raise MemoryPreflightRefusedError(refusal_text(result))
    if label is not None:
        arm(label, timeout_seconds=timeout_seconds)
    return result.unverified


# ---------------------------------------------------------------- arming the memory gate (D-168)
#: The gate (``scripts/memory_gate.py``, SYSTEM) freezes only inside the process trees listed here: one small JSON file per armed process.
ARM_DIR_NAME = "memory-gate-arm"
ARM_SCHEMA = "memory-gate-arm.v1"
#: label -> (default seconds when no command timeout is known, hard cap in seconds).  The gate holds the same table and rejects a longer record.
ARM_LABEL_LIMITS: dict[str, tuple[float, float]] = {
    "full-tests": (5400.0, 5400.0),
    "pm-verify": (5400.0, 5400.0),
    "deploy-gate": (5400.0, 5400.0),
    "long-run": (15000.0, 43800.0),
    "long-gate": (36600.0, 36600.0),
}
ARM_MARGIN_SECONDS = 600.0
ARM_SEARCH_LEVELS = 12


def arm_dir(start: Path | None = None) -> Path | None:
    """``<control root>/.auto-pm/memory-gate-arm`` found by walking up from ``start`` (default: this file); None when no ``.auto-pm`` is on the way.

    An ancestor that is itself named ``.auto-pm`` wins (a managed worktree sits below ``<root>/.auto-pm/worktrees`` and may hold an ``.auto-pm`` of its own);
    otherwise the nearest ancestor that contains an ``.auto-pm`` folder.
    """

    here = (start if start is not None else Path(__file__)).resolve()
    chain = [here, *here.parents][: ARM_SEARCH_LEVELS + 1]
    for folder in chain:
        if folder.name == ".auto-pm":
            return folder / ARM_DIR_NAME
    for folder in chain:
        if (folder / ".auto-pm").is_dir():
            return folder / ".auto-pm" / ARM_DIR_NAME
    return None


if sys.platform == "win32":

    def process_created(pid: int) -> int:
        """Creation time of ``pid`` as the gate reads it (Windows: FILETIME ticks); 0 when unreadable."""

        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return 0
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
                return 0
            return (int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)

else:

    def process_created(pid: int) -> int:
        """Creation time of ``pid`` as the gate reads it (Linux: start time in clock ticks since boot); 0 when unreadable."""

        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            return int(stat.rsplit(")", 1)[1].split()[19])
        except (OSError, ValueError, IndexError):
            return 0


def arm(
    label: str,
    *,
    timeout_seconds: float | None = None,
    start: Path | None = None,
    pid: int | None = None,
    now: Callable[[], float] = time.time,
) -> Path | None:
    """Arm this process for the memory gate until it exits (or the label's cap passes).  Returns the record path, or None when it could not be written.

    Deliberately silent on failure: a missing arm folder only means the gate stays out of this job's way, never that the job refuses to run.
    The record is removed again at normal interpreter exit; a crash leaves a record that the gate rejects (process gone or creation time different).
    """

    limits = ARM_LABEL_LIMITS.get(label)
    folder = arm_dir(start)
    if limits is None or folder is None:
        return None
    default_seconds, hard_cap = limits
    seconds = timeout_seconds + ARM_MARGIN_SECONDS if timeout_seconds is not None and timeout_seconds > 0 else default_seconds
    seconds = min(seconds, hard_cap)
    owner = pid if pid is not None else os.getpid()
    armed_at = now()
    record = {
        "schema": ARM_SCHEMA,
        "pid": owner,
        "created": process_created(owner),
        "label": label,
        "armed_at": armed_at,
        "expires_at": armed_at + seconds,
    }
    target = folder / f"{owner}.json"
    temporary = folder / f"{owner}.json.tmp"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _sweep_dead(folder, owner)
        temporary.write_text(json.dumps(record), encoding="ascii")
        os.replace(temporary, target)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink()
        return None
    atexit.register(disarm, target)
    return target


def _sweep_dead(folder: Path, keep: int) -> None:
    """Remove the records of processes that no longer exist (a killed job cannot clean up after itself).  Best effort; the gate ignores them anyway."""

    with contextlib.suppress(OSError):
        for item in folder.glob("*.json"):
            if not item.stem.isdigit() or int(item.stem) == keep:
                continue
            try:
                created = json.loads(item.read_text(encoding="ascii")).get("created")
            except (OSError, ValueError, AttributeError):
                continue
            if process_created(int(item.stem)) != created:
                item.unlink()


def disarm(path: Path) -> None:
    """Remove an arm record; already gone is fine."""

    with contextlib.suppress(OSError):
        path.unlink()
