r"""内存总闸看门狗：整机已提交内存到 40 GiB 就冻结涨得最快的一棵进程树（只暂停，绝不杀），回落到 36 GiB 以下再解冻。

为什么（2026-11-02/03 笔记本内存事件）：agent 在自己终端里直接跑回归，已提交内存线性涨到 72 GB。``main.py long-run`` 的守卫只管
经它起的任务，相当于每台电机自己的热继电器；这里是总进线断路器：不管谁在跑（Claude、Trae、反重力、手敲命令），都由它兜底。
它开机自启（计划任务，见 ``install_memory_gate.ps1``），不依赖任何 agent。

安装形态（审计 579）：计划任务以 SYSTEM 运行，所以代码不能放在用户可写的目录里。``-Install`` 把本脚本和 ``memory_preflight.py``、
``long_run_core.py`` 复制到 ``%ProgramFiles%\AutoPM\MemoryGate``，只给 SYSTEM 和 Administrators 完全控制、Users 只读，记下三个文件的
SHA-256（``manifest.json``）；解释器是系统安装的（或复制进该目录的）Python，不用 .venv；运行加 ``-I -B``。状态、告警、STOP 文件都在该目录的
``state`` 下，普通用户写不进去。每次启动和 ``status`` 都核对 SHA-256，不符就拒绝运行并告警；更新只能由管理员重跑 ``-Install``。

规则（判据写死在本文件，不读配置、不读环境变量）：

- 每 5 秒采样整机已提交内存和每个进程的私有已提交量，保留最近 60 秒。
- 已提交 >= 40 GiB：在“可冻结”的进程里，按 60 秒窗内（私有已提交涨幅 + 新进程数 * 0.02 GiB）给每个“单元”打分，
  冻结得分最高的单元的整棵子树。单元 = 涨得最快的进程所属的 shell 层（powershell/pwsh/cmd/bash…）。
- 冻结梯子：冻后每个检查点（至少隔 10 秒，看最近 30 秒），已提交涨速仍 >= 0.3 GiB/分钟且涨幅 >= 0.15 GiB（止不住）就升一层，冻“终端属主”（应用主进程的直接子进程）；
  梯子用完仍涨，才换下一个得分最高的单元；最多同时冻 4 个单元。涨速已低于 0.3 GiB/分钟就不再多冻（冻结只止涨，不降内存）。
- 只冻交互会话里属于登录用户的进程（Windows：会话号 > 0 且令牌用户 SID 以 S-1-5-21-（本地/域账户）或 S-1-12-1-（Azure AD 账户）开头）；TiWorker 这类 SYSTEM 和服务进程一律不冻。
- 绝不冻：保护名单（看门狗自己及其祖先、系统关键进程、explorer、终端宿主、杀毒、svchost）；应用主进程（父进程是保护进程或不存在、
  且下面还有非保护的后代，如 Trae CN 主进程）。孤零零涨的单个进程（上无非保护祖先、下无非保护后代）则冻它自己。
- 冻后仍在涨时重新打分：只有得分最高的单元落在梯子下一层的子树里才升层，否则换成那个得分最高的单元；没有任何可冻结的进程在涨就不再动手。
- 已提交 < 36 GiB 持续 30 秒：按冻结的反序逐棵解冻，每棵间隔 5 秒。解冻后 120 秒内同一棵再触发 -> 冻住并锁定，不再自动解冻，
  写醒目日志 + 告警文件 + Windows 通知（哪棵树、涨了多少），等人用 ``resume-all``；没人处理就每 15 分钟再通知一次，不自动解冻。
- STOP 文件（只认受保护状态目录里的）：看门狗先解冻全部已冻进程再退出。
- PID 复用：冻结与解冻都核对进程创建时间。

用法：
    python -B scripts/memory_gate.py run         # 看门狗本体（计划任务调用）
    python -B scripts/memory_gate.py status      # 只读：是否在跑、现在多少、冻了谁
    python -B scripts/memory_gate.py resume-all  # 手动解冻全部（含已锁定的）
    python -B scripts/memory_gate.py bundle-hash # 四个文件的哈希，安装时作为 -ExpectedSha256
    python -B scripts/memory_gate.py selftest    # 用无害的假进程走一遍 冻结 -> 解冻（不需要内存压力）
"""

# ruff: noqa: T201
from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

GIB = 2**30
LIMIT_GIB = 40.0
RESUME_GIB = 36.0
POLL_SECONDS = 5.0
WINDOW_SECONDS = 60.0
RECHECK_SECONDS = 10.0
RISING_GIB_PER_MIN = 0.3
RISING_MIN_GIB = 0.15  # and at least this much in absolute terms, so ordinary jitter (browsers) does not climb the ladder
RATE_WINDOW_SECONDS = 30.0
SPAWN_GIB = 0.02
RESUME_HOLD_SECONDS = 30.0
RESUME_SPACING_SECONDS = 5.0
RELOCK_SECONDS = 120.0
MAX_FROZEN_UNITS = 4
HEARTBEAT_STALE_SECONDS = 30.0
LOG_LIMIT_BYTES = 1024 * 1024
RENOTIFY_SECONDS = 15 * 60.0  # a locked tree nobody has dealt with is announced again this often
MANIFEST_FILE = "manifest.json"
MANIFEST_FILES = ("scripts/memory_gate.py", "auto_pm/infrastructure/memory_preflight.py", "auto_pm/infrastructure/long_run_core.py")
STATE_FILE = "state.json"
STOP_FILE = "STOP"
LOG_FILE = "gate.log"

# 写死的保护名单（小写）。名字读不出来（"?"）的也按保护处理：不认识的进程不动。
PROTECTED_NAMES = frozenset(
    {
        "system", "system idle process", "idle", "registry", "memory compression", "secure system",
        "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe", "dwm.exe", "fontdrvhost.exe",
        "svchost.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe", "runtimebroker.exe", "spoolsv.exe",
        "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe", "securityhealthsystray.exe",
        "explorer.exe", "openconsole.exe", "conhost.exe", "windowsterminal.exe", "wt.exe",
        "systemd", "init", "kthreadd", "sshd", "login", "dbus-daemon",
    }
)  # fmt: skip
#: Token user SIDs of people: local and domain accounts (S-1-5-21-*) and Azure AD / Microsoft accounts (S-1-12-1-*).
USER_SID_PREFIXES = ("S-1-5-21-", "S-1-12-1-")
#: The files whose bytes the installer was told to trust (relative to the project root); ``bundle-hash`` hashes them in this order.
BUNDLE_FILES = (
    "auto_pm/infrastructure/long_run_core.py",
    "auto_pm/infrastructure/memory_preflight.py",
    "scripts/install_memory_gate.ps1",
    "scripts/memory_gate.py",
)
SHELL_NAMES = frozenset({"powershell.exe", "pwsh.exe", "cmd.exe", "bash.exe", "wsl.exe", "bash", "sh", "zsh", "fish", "dash"})


@dataclass(frozen=True)
class Proc:
    """One process: pid, parent pid, image name and the private memory it has committed (bytes)."""

    pid: int
    ppid: int
    name: str
    committed: int


def _now_text() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


# ---------------------------------------------------------------- sibling modules (standard library only, loaded by path)
def _load(file_name: str) -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "auto_pm" / "infrastructure" / f"{file_name}.py"
    name = f"memory_gate_{file_name}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"找不到 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name while it executes
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


# ---------------------------------------------------------------- the host: real readings and real suspend/resume
if sys.platform == "win32":
    from ctypes import wintypes

    def created_of(pid: int) -> int:
        """Creation time (FILETIME ticks) of ``pid``; 0 when it cannot be read.  Pairs with the pid to identify one process."""

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

    def _parent_map(core: ModuleType) -> dict[int, int]:
        children = core._children() or {}
        return {child: parent for parent, kids in children.items() for child in kids}

    class _SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    def user_process(pid: int) -> bool:
        """A process of a logged-in user in an interactive session: session id > 0 and a token user SID of the form S-1-5-21-*.

        SYSTEM (S-1-5-18), LOCAL/NETWORK SERVICE, virtual service accounts (S-1-5-80-*, e.g. TrustedInstaller's TiWorker) and everything in
        session 0 are not.  Anything that cannot be read counts as "not a user process": the gate never freezes what it cannot identify.
        """

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel.ProcessIdToSessionId.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi.OpenProcessToken.restype = wintypes.BOOL
        advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        advapi.GetTokenInformation.restype = wintypes.BOOL
        advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
        if pid <= 4:
            return False
        session = wintypes.DWORD()
        if not kernel.ProcessIdToSessionId(pid, ctypes.byref(session)) or session.value == 0:
            return False
        process = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            return False
        token = wintypes.HANDLE()
        try:
            if not advapi.OpenProcessToken(process, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
                return False
            try:
                needed = wintypes.DWORD()
                advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))  # TokenUser: first ask for the size
                if needed.value == 0:
                    return False
                buffer = ctypes.create_string_buffer(needed.value)
                if not advapi.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)):
                    return False
                sid = ctypes.cast(buffer, ctypes.POINTER(_SidAndAttributes)).contents.Sid
                text = wintypes.LPWSTR()
                if not sid or not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                    return False
                try:
                    return bool((text.value or "").startswith(USER_SID_PREFIXES))
                finally:
                    kernel.LocalFree(text)
            finally:
                kernel.CloseHandle(token)
        finally:
            kernel.CloseHandle(process)

    def message_box(title: str, text: str) -> bool:
        """A message box in the active console session that does not wait for a click (``WTSSendMessageW``; works on every Windows edition)."""

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        wtsapi = ctypes.WinDLL("wtsapi32", use_last_error=True)
        kernel.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
        wtsapi.WTSSendMessageW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
        ]  # fmt: skip
        wtsapi.WTSSendMessageW.restype = wintypes.BOOL
        session = kernel.WTSGetActiveConsoleSessionId()
        if session == 0xFFFFFFFF:
            return False
        answer = wintypes.DWORD()
        return bool(wtsapi.WTSSendMessageW(None, session, title, len(title) * 2, text, len(text) * 2, 0x30, 0, ctypes.byref(answer), False))  # MB_ICONWARNING

else:

    def user_process(pid: int) -> bool:
        """Off Windows (development and tests): a process of the same user as the gate."""

        if pid <= 4:
            return False
        try:
            return Path(f"/proc/{pid}").stat().st_uid == os.getuid()
        except OSError:
            return False

    def message_box(title: str, text: str) -> bool:
        return False

    def created_of(pid: int) -> int:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            return int(stat.rsplit(")", 1)[1].split()[19])  # field 22: start time in clock ticks since boot
        except (OSError, ValueError, IndexError):
            return 0

    def _parent_map(core: ModuleType) -> dict[int, int]:
        found: dict[int, int] = {}
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text(encoding="utf-8")
                found[int(entry.name)] = int(stat.rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                continue
        return found


class Host:
    """Real readings and real suspend/resume, built on #513 ``memory_preflight`` and #514 ``long_run_core``."""

    def __init__(self) -> None:
        self.preflight = _load("memory_preflight")
        self.core = _load("long_run_core")

    def committed_gib(self) -> float | None:
        snapshot = self.preflight.read_commit()
        return None if snapshot is None else float(snapshot.committed) / GIB

    def processes(self) -> list[Proc]:
        parents = _parent_map(self.core)
        return [Proc(use.pid, parents.get(use.pid, 0), str(use.name), int(use.committed)) for use in self.preflight.all_processes()]

    def suspend(self, pids: list[int]) -> int:
        return int(self.core.suspend(pids))

    def resume(self, pids: list[int]) -> int:
        return int(self.core.resume(pids))

    def alive(self, pid: int) -> bool:
        return bool(self.core.pid_alive(pid))

    def eligible(self, pid: int) -> bool:
        return user_process(pid)


def notify_user(title: str, text: str) -> None:
    """A message box in the logged-in user's session (``WTSSendMessageW``, then ``msg`` as a second try); failures are ignored.

    The alert file in the protected state directory is the record; nothing is written to a place ordinary users can write.
    """

    if sys.platform != "win32":
        return
    shown = False
    with contextlib.suppress(OSError, ValueError):
        shown = message_box(title[:120], text[:900])
    if not shown:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(["msg", "*", "/TIME:0", f"{title}\n{text}"[:900]], capture_output=True, check=False, timeout=15)  # noqa: S603, S607


# ---------------------------------------------------------------- the gate
class Gate:
    """One decision step per ``step()``; all machine access is injected so every rule can be tested with a fake machine."""

    def __init__(
        self,
        state_dir: Path,
        *,
        committed_gib: Callable[[], float | None],
        processes: Callable[[], list[Proc]],
        created_of: Callable[[int], int],
        suspend: Callable[[list[int]], int],
        resume: Callable[[list[int]], int],
        alive: Callable[[int], bool],
        now: Callable[[], float] = time.time,
        notify: Callable[[str, str], None] = notify_user,
        self_pids: Iterable[int] = (),
        eligible: Callable[[int], bool] = lambda pid: True,
        limit_gib: float = LIMIT_GIB,
        resume_gib: float = RESUME_GIB,
    ) -> None:
        self.dir = state_dir
        self.committed_gib = committed_gib
        self.processes = processes
        self.created_of = created_of
        self.suspend = suspend
        self.resume = resume
        self.alive = alive
        self.now = now
        self.notify = notify
        self.self_pids = {int(pid) for pid in self_pids} | {os.getpid()}
        self.eligible = eligible
        self._eligible_cache: dict[int, bool] = {}
        self.limit = limit_gib
        self.resume_limit = resume_gib
        self.history: list[tuple[float, float, dict[int, int]]] = []
        self.first_seen: dict[int, float] = {}
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------ files
    def log(self, text: str) -> None:
        path = self.dir / LOG_FILE
        with contextlib.suppress(OSError):
            if path.exists() and path.stat().st_size > LOG_LIMIT_BYTES:
                path.replace(self.dir / f"{LOG_FILE}.1")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{_now_text()} {text}\n")

    def load(self) -> dict[str, Any]:
        try:
            state = json.loads((self.dir / STATE_FILE).read_text(encoding="utf-8"))
            if isinstance(state, dict):
                state.setdefault("frozen", [])
                state.setdefault("recent_resumed", {})
                state.setdefault("next_id", 1)
                return state
        except (OSError, ValueError):
            pass
        return {"frozen": [], "recent_resumed": {}, "next_id": 1, "watch": None, "below_since": None, "last_resume_at": 0.0}

    def save(self, state: dict[str, Any]) -> None:
        text = json.dumps(state, ensure_ascii=False, indent=1)
        temporary = self.dir / f"{STATE_FILE}.tmp"
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.dir / STATE_FILE)

    def alert(self, headline: str, body: str, *, loud: bool) -> None:
        stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
        text = (
            f"{headline}\n\n{body}\n\n"
            "说明：总闸只是暂停了进程（没有杀），目的是止涨；暂停不会让已提交内存下降，内存要等任务结束或你处理后才回落。\n"
            "手动解冻全部：python -B scripts\\memory_gate.py resume-all\n"
        )
        with contextlib.suppress(OSError):
            (self.dir / f"ALERT-{stamp}.txt").write_text(text, encoding="utf-8")
        self.log(("【锁定】" if loud else "【冻结】") + headline)
        self.notify("内存总闸", f"{headline}\n{body}"[:800])

    # ------------------------------------------------ one step
    def step(self) -> None:
        state = self.load()
        now = self.now()
        committed = self.committed_gib()
        state["heartbeat"] = now
        if committed is None:
            self.log("读不到整机已提交内存，本轮跳过")
            self.save(state)
            return
        procs = {proc.pid: proc for proc in self.processes()}
        self._eligible_cache.clear()
        self._record(now, committed, procs)
        state["committed_gib"] = round(committed, 2)
        self._drop_dead(state)
        self._renotify_locked(state, now)
        if committed >= self.limit:
            state["below_since"] = None
            self._hot(state, now, committed, procs)
        elif committed < self.resume_limit:
            self._cool(state, now)
        else:
            state["below_since"] = None
        self.save(state)

    def _record(self, now: float, committed: float, procs: dict[int, Proc]) -> None:
        first = not self.history
        for pid in procs:
            self.first_seen.setdefault(pid, float("-inf") if first else now)
        for pid in [pid for pid in self.first_seen if pid not in procs]:
            del self.first_seen[pid]
        self.history.append((now, committed, {pid: proc.committed for pid, proc in procs.items()}))
        while len(self.history) > 1 and now - self.history[0][0] > WINDOW_SECONDS:
            self.history.pop(0)

    # ------------------------------------------------ who may be frozen
    def _protected(self, proc: Proc) -> bool:
        return proc.name.lower() in PROTECTED_NAMES or proc.name == "?" or proc.pid <= 4 or proc.pid in self.self_pids

    def _excluded(self, proc: Proc) -> bool:
        """Protected by name or identity, or not a logged-in user's process: the gate neither freezes it nor climbs through it."""

        if self._protected(proc):
            return True
        if proc.pid not in self._eligible_cache:
            self._eligible_cache[proc.pid] = bool(self.eligible(proc.pid))
        return not self._eligible_cache[proc.pid]

    def _protected_pids(self, procs: dict[int, Proc]) -> set[int]:
        """The gate itself and all its ancestors are never frozen."""

        found = set(self.self_pids)
        for pid in list(self.self_pids):
            seen = 0
            while pid in procs and seen < 64:
                found.add(pid)
                pid = procs[pid].ppid
                seen += 1
        return found

    def _chain(self, proc: Proc, procs: dict[int, Proc], blocked: set[int]) -> list[Proc]:
        """``proc`` and its ancestors up to (not including) the first protected or missing one; index 0 is ``proc``."""

        chain: list[Proc] = []
        current: Proc | None = proc
        while current is not None and len(chain) < 64 and current.pid not in blocked and not self._excluded(current):
            if any(item.pid == current.pid for item in chain):
                break
            chain.append(current)
            current = procs.get(current.ppid)
        return chain

    def ladder(self, proc: Proc, procs: dict[int, Proc], blocked: set[int]) -> list[int]:
        """The roots to freeze for ``proc``, gentlest first: its shell level, then the terminal owner; never the application's main process."""

        chain = self._chain(proc, procs, blocked)
        if not chain:
            return []
        if len(chain) == 1:
            if any(other.ppid == proc.pid and not self._excluded(other) and other.pid not in blocked for other in procs.values()):
                return []  # an application's main process (something of the application runs below it): never frozen, only what runs below it
            return [proc.pid]  # a lone runaway process: nothing above it to spare, nothing below it to freeze instead
        below_top = chain[:-1]  # chain[-1] is the application's main process
        terminal_owner = below_top[-1]
        shell = next((item for item in below_top if item.name.lower() in SHELL_NAMES), None)
        if shell is not None:
            first = shell
        elif len(below_top) >= 2:
            first = below_top[-2]  # no shell on the path: the terminal owner's own branch that holds the culprit, not the terminal owner itself
        else:
            first = terminal_owner
        return list(dict.fromkeys([first.pid, terminal_owner.pid]))

    def _subtree(self, root: int, procs: dict[int, Proc]) -> list[int]:
        children: dict[int, list[int]] = {}
        for proc in procs.values():
            children.setdefault(proc.ppid, []).append(proc.pid)
        found: list[int] = []
        todo = [root]
        while todo:
            pid = todo.pop()
            if pid in found:
                continue
            found.append(pid)
            todo.extend(children.get(pid, []))
        return found

    # ------------------------------------------------ choosing a unit
    def _growth_gib(self, pid: int, procs: dict[int, Proc], now: float) -> tuple[float, bool]:
        """(private commit growth over the window in GiB, whether the process is new in the window)."""

        oldest = self.history[0][2]
        new = self.first_seen.get(pid, float("-inf")) >= now - WINDOW_SECONDS
        base = 0 if new else oldest.get(pid, procs[pid].committed)
        return max(procs[pid].committed - base, 0) / GIB, new

    def _pick(self, now: float, procs: dict[int, Proc], frozen_pids: set[int]) -> tuple[list[int], str] | None:
        blocked = self._protected_pids(procs) | frozen_pids
        score: dict[int, float] = {}
        held: dict[int, int] = {}
        spawned: dict[int, int] = {}
        growth_of: dict[int, float] = {}
        ladders: dict[int, list[int]] = {}
        for proc in procs.values():
            if proc.pid in blocked or self._excluded(proc):
                continue
            ladder = self.ladder(proc, procs, blocked)
            if not ladder:
                continue
            unit = ladder[0]
            growth, new = self._growth_gib(proc.pid, procs, now)
            score[unit] = score.get(unit, 0.0) + growth + (SPAWN_GIB if new else 0.0)
            held[unit] = held.get(unit, 0) + proc.committed
            spawned[unit] = spawned.get(unit, 0) + (1 if new else 0)
            growth_of[unit] = growth_of.get(unit, 0.0) + growth
            ladders.setdefault(unit, ladder)
        score = {unit: value for unit, value in score.items() if value > 0}
        if not score:
            return None  # nothing that may be frozen is growing: freezing a bystander would stop nothing
        unit = max(score, key=lambda key: (score[key], held[key]))
        name = procs[unit].name
        reason = f"{name}（PID {unit}）所在进程树：60 秒内私有已提交 +{growth_of[unit]:.1f} GiB、新进程 {spawned[unit]} 个、合计私有已提交 {held[unit] / GIB:.1f} GiB"
        return ladders[unit], reason

    # ------------------------------------------------ freeze
    def _freeze(self, state: dict[str, Any], now: float, committed: float, procs: dict[int, Proc], ladder: list[int], level: int, reason: str) -> None:
        blocked = self._protected_pids(procs) | {int(pid) for entry in state["frozen"] for pid in (member["pid"] for member in entry["members"])}
        root = ladder[0]
        pids = [pid for pid in self._subtree(root, procs) if pid not in blocked and not self._excluded(procs[pid])]
        members = [{"pid": pid, "created": self.created_of(pid)} for pid in pids]
        done = self.suspend(pids)
        key = f"{root}:{self.created_of(root)}"
        relocked = now - float(state["recent_resumed"].get(key, float("-inf"))) <= RELOCK_SECONDS
        entry = {
            "id": state["next_id"],
            "root": root,
            "root_name": procs[root].name,
            "members": members,
            "ladder_rest": ladder[1:],
            "level": level,
            "at": now,
            "committed_gib": round(committed, 2),
            "locked": relocked,
            "reason": reason,
        }
        state["next_id"] += 1
        state["frozen"].append(entry)
        state["watch"] = {"id": entry["id"], "at": now, "committed": committed}
        headline = f"已冻结 {procs[root].name}（PID {root}）的进程树，共 {len(pids)} 个进程（梯子第 {level} 层）；整机已提交 {committed:.1f} GiB"
        if done == 0:
            headline += "【注意：系统没有接受暂停，进程可能仍在运行】"
        if relocked:
            headline = f"同一棵树在解冻后 {RELOCK_SECONDS:.0f} 秒内再次触发，已冻结并锁定、不再自动解冻：" + headline
        self.alert(headline, f"原因：{reason}\n恢复：确认原因后运行 resume-all；锁定的树不会自动解冻。", loud=relocked)

    def _hot(self, state: dict[str, Any], now: float, committed: float, procs: dict[int, Proc]) -> None:
        frozen_pids = {int(member["pid"]) for entry in state["frozen"] for member in entry["members"]}
        watch = state.get("watch")
        if watch is None:
            picked = self._pick(now, procs, frozen_pids)
            if picked is None:
                self.log(f"已提交 {committed:.1f} GiB 超限，但可冻结的进程里没有一个在涨（涨的不在可冻结范围内），总闸不动手")
                return
            self._freeze(state, now, committed, procs, picked[0], 1, picked[1])
            return
        start = max(float(watch["at"]), now - RATE_WINDOW_SECONDS)
        base = next(((t, gib) for t, gib, _procs in self.history if t >= start), None)
        entry = next((item for item in state["frozen"] if item["id"] == watch["id"]), None)
        if base is None or now - base[0] < RECHECK_SECONDS:
            return
        elapsed, rise = now - base[0], committed - base[1]
        rate = rise / elapsed * 60.0
        if rate < RISING_GIB_PER_MIN or rise < RISING_MIN_GIB:
            if now - float(state.get("flat_logged_at", 0.0)) >= 60.0:
                state["flat_logged_at"] = now
                self.log(f"冻结后涨速 {rate:.2f} GiB/分钟，已止住（整机 {committed:.1f} GiB 仍高于上限，只等任务结束或人处理）")
            return
        state["watch"] = {"id": watch["id"], "at": now, "committed": committed}
        if len(state["frozen"]) >= MAX_FROZEN_UNITS:
            self.log(f"涨速 {rate:.2f} GiB/分钟仍在涨，但已冻满 {MAX_FROZEN_UNITS} 棵树，总闸没有更多动作，请人处理")
            return
        rest = [pid for pid in (entry["ladder_rest"] if entry else []) if pid in procs and pid not in frozen_pids]
        picked = self._pick(now, procs, frozen_pids)  # still rising: score everything again, do not assume the next rung is the cause
        if picked is None:
            self.log(f"涨速 {rate:.2f} GiB/分钟仍在涨，但可冻结的进程里没有一个在涨，总闸不再动手，请人处理")
            return
        ladder, reason = picked
        if rest and ladder[0] in self._subtree(rest[0], procs):  # the fastest-growing unit sits in the next rung's subtree: climb
            self._freeze(state, now, committed, procs, rest, int(entry["level"]) + 1, f"{reason}；冻后涨速仍 {rate:.2f} GiB/分钟，升一层")
            return
        self._freeze(state, now, committed, procs, ladder, 1, f"{reason}；冻后涨速仍 {rate:.2f} GiB/分钟，换一个单元")

    def _renotify_locked(self, state: dict[str, Any], now: float) -> None:
        for entry in state["frozen"]:
            if entry["locked"] and now - float(entry.get("renotified_at", entry["at"])) >= RENOTIFY_SECONDS:
                entry["renotified_at"] = now
                self.alert(
                    f"仍冻结着（已锁定）：{entry['root_name']}（PID {entry['root']}）的进程树，没有人处理；总闸不会自动解冻",
                    f"原因：{entry['reason']}\n确认后在管理员 PowerShell 运行 resume-all。",
                    loud=True,
                )

    # ------------------------------------------------ resume
    def _members_alive(self, entry: dict[str, Any]) -> list[int]:
        return [
            int(member["pid"])
            for member in entry["members"]
            if self.alive(int(member["pid"])) and (int(member["created"]) == 0 or self.created_of(int(member["pid"])) == int(member["created"]))
        ]

    def _drop_dead(self, state: dict[str, Any]) -> None:
        keep = []
        for entry in state["frozen"]:
            if self._members_alive(entry):
                keep.append(entry)
            else:
                self.log(f"冻结的进程树 {entry['root_name']}（PID {entry['root']}）已不存在，记录移除")
        state["frozen"] = keep
        if not keep:
            state["watch"] = None

    def _resume_entry(self, state: dict[str, Any], entry: dict[str, Any], now: float) -> int:
        pids = self._members_alive(entry)  # a pid that now belongs to another process (reuse) is not resumed
        done = self.resume(pids) if pids else 0
        state["frozen"] = [item for item in state["frozen"] if item["id"] != entry["id"]]
        state["recent_resumed"][f"{entry['root']}:{entry['members'][0]['created']}"] = now
        self.log(f"已解冻 {entry['root_name']}（PID {entry['root']}），{done}/{len(entry['members'])} 个进程")
        return done

    def _cool(self, state: dict[str, Any], now: float) -> None:
        if state.get("below_since") is None:
            state["below_since"] = now
            return
        if now - float(state["below_since"]) < RESUME_HOLD_SECONDS or now - float(state.get("last_resume_at", 0.0)) < RESUME_SPACING_SECONDS:
            return
        unlocked = [entry for entry in state["frozen"] if not entry["locked"]]
        if not unlocked:
            return
        self._resume_entry(state, unlocked[-1], now)  # reverse order of freezing
        state["last_resume_at"] = now
        if not state["frozen"]:
            state["watch"] = None

    def resume_all(self) -> int:
        """Resume every frozen tree now, locked ones too (the manual command and uninstall)."""

        state = self.load()
        total = 0
        for entry in reversed(list(state["frozen"])):
            total += self._resume_entry(state, entry, self.now())
        state["watch"] = None
        self.save(state)
        return total


def run_forever(gate: Gate, *, sleep: Callable[[float], None] = time.sleep, poll: float = POLL_SECONDS, max_steps: int | None = None) -> None:
    (gate.dir / STOP_FILE).unlink(missing_ok=True)
    steps = 0
    while not (gate.dir / STOP_FILE).exists():
        try:
            gate.step()
        except Exception as error:  # noqa: BLE001 - the watchdog must outlive any single failure
            gate.log(f"本轮异常 {type(error).__name__}: {error}")
        steps += 1
        if max_steps is not None and steps >= max_steps:
            return
        sleep(poll)
    resumed = gate.resume_all()  # never leave anything frozen behind
    gate.log(f"收到 STOP，已解冻 {resumed} 个进程，看门狗退出")


# ---------------------------------------------------------------- command line
def install_root() -> Path | None:
    """The installed layout's root (``%ProgramFiles%\\AutoPM\\MemoryGate``): the folder above ``scripts`` when it holds the install manifest."""

    root = Path(__file__).resolve().parent.parent
    return root if (root / MANIFEST_FILE).exists() else None


def default_state_dir() -> Path:
    """Installed: ``<install root>\\state`` (only SYSTEM and Administrators can write there).  A development checkout: ``~/.auto-pm/memory-gate``."""

    root = install_root()
    return root / "state" if root is not None else Path.home() / ".auto-pm" / "memory-gate"


def _normalized_sha256(path: Path) -> str:
    """SHA-256 of the file with CRLF read as LF, so a Windows checkout (autocrlf) and a Linux one hash the same."""

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def bundle_hash(project_root: Path | None = None) -> tuple[str, list[tuple[str, str]]]:
    """(the combined SHA-256, the per-file lines): the value ``install_memory_gate.ps1 -Install -ExpectedSha256`` must be given.

    Combined = SHA-256 of ``"<sha256>  <relative path>\n"`` for every file in ``BUNDLE_FILES`` (UTF-8, LF).  The installer computes the same
    thing from the files it is about to copy plus itself, and refuses on any difference, so the user installs exactly what was audited.
    """

    root = project_root or Path(__file__).resolve().parent.parent
    lines = [(relative, _normalized_sha256(root / relative)) for relative in BUNDLE_FILES]
    text = "".join(f"{digest}  {relative}\n" for relative, digest in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), lines


def interpreter_problem(flags: Any = sys.flags) -> str:
    """The scheduled task must run ``python -I -S -B``: isolated (no PYTHON* variables, no user site, no script directory on the path), no ``site``."""

    missing = [name for name, ok in (("-I", flags.isolated), ("-S", flags.no_site), ("-B", flags.dont_write_bytecode)) if not ok]
    return f"解释器没有用 {' '.join(missing)} 运行" if missing else ""


def verify_install(root: Path) -> str:
    """Why the installed files cannot be trusted (empty when they match the SHA-256 the installer recorded)."""

    try:
        recorded = json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return f"{MANIFEST_FILE} 缺失或读不出"
    if not isinstance(recorded, dict):
        return f"{MANIFEST_FILE} 格式不对"
    for relative in MANIFEST_FILES:
        want = recorded.get(relative)
        try:
            have = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        except OSError:
            return f"{relative} 缺失"
        if not isinstance(want, str) or have != want.lower():
            return f"{relative} 的 SHA-256 与安装时记录的不一致（文件被改过）"
    return ""


def real_gate(state_dir: Path) -> Gate:
    host = Host()
    return Gate(
        state_dir,
        committed_gib=host.committed_gib,
        processes=host.processes,
        created_of=created_of,
        suspend=host.suspend,
        resume=host.resume,
        alive=host.alive,
        eligible=host.eligible,
    )


def selftest(state_dir: Path, *, strict: bool = False) -> list[str]:
    """Freeze and resume a harmless child with the real code path; returns the problems found (empty = pass).

    The child writes a heartbeat file every 0.2 s; frozen means the file stops moving, resumed means it moves again.  The
    memory readings are injected (first over the limit, then far below), so no memory pressure is needed.  ``strict`` (the command line and
    the installer) also requires the child to pass the real "logged-in user's interactive process" test; a CI runner works in session 0 and
    cannot, so the unit test leaves it off.
    """

    problems: list[str] = []
    beat = state_dir / "selftest.beat"
    code = "import os, sys, time\nwhile True:\n    open(sys.argv[1], 'w').write(str(time.time()))\n    time.sleep(0.2)\n"
    reading = {"value": 1.0}
    clock = {"t": 1_000_000.0}
    target = {"pid": 0}
    host = Host()

    def only_the_child() -> list[Proc]:
        """The child and what runs below it (a venv's python.exe is a launcher with the real interpreter as its child); nothing else may be a candidate."""

        everything = host.processes()
        keep = {target["pid"]}
        grown = True
        while grown:
            below = {proc.pid for proc in everything if proc.ppid in keep and proc.pid not in keep}
            grown = bool(below)
            keep |= below
        return [proc for proc in everything if proc.pid in keep]

    gate = Gate(
        state_dir,
        committed_gib=lambda: reading["value"],
        processes=only_the_child,
        created_of=created_of,
        suspend=host.suspend,
        resume=host.resume,
        alive=host.alive,
        now=lambda: clock["t"],
        notify=lambda title, text: None,
        self_pids=[os.getpid()],
        eligible=host.eligible if strict else (lambda pid: True),
    )

    def moves(seconds: float) -> bool:
        before = beat.stat().st_mtime if beat.exists() else 0.0
        time.sleep(seconds)
        return (beat.stat().st_mtime if beat.exists() else 0.0) > before

    gate.step()  # a quiet reading first: the gate learns what is already running, so the child below counts as a new process
    child = subprocess.Popen([sys.executable, "-c", code, str(beat)])  # noqa: S603
    target["pid"] = child.pid
    try:
        deadline = time.time() + 20
        while not beat.exists() and time.time() < deadline:
            time.sleep(0.1)
        if not moves(1.0):
            problems.append("假进程没有在跑，自检无法进行")
            return problems
        reading["value"] = LIMIT_GIB + 5.0
        clock["t"] += 5.0
        gate.step()
        state = gate.load()
        if not state["frozen"]:  # the root may be the child's own child: a venv's python.exe is a launcher whose child is the real interpreter
            problems.append("没有冻结假进程（严格模式下它还必须是登录用户的交互进程）")
        elif moves(1.5):
            problems.append("状态里记了冻结，但假进程仍在动：系统没有接受暂停")
        reading["value"] = 1.0
        for _ in range(3):
            clock["t"] += 40.0
            gate.step()
        if gate.load()["frozen"]:
            problems.append("内存回落后没有解冻")
        elif not moves(1.5):
            problems.append("已记为解冻，但假进程没有恢复运行")
    finally:
        with contextlib.suppress(OSError):
            gate.resume_all()
            child.kill()
        child.wait(timeout=30)
    return problems


def cmd_status(state_dir: Path, integrity: str = "") -> int:
    gate = Gate(state_dir, committed_gib=lambda: None, processes=list, created_of=created_of, suspend=lambda p: 0, resume=lambda p: 0, alive=lambda p: False)
    state = gate.load()
    age = time.time() - float(state.get("heartbeat", 0.0))
    running = age <= HEARTBEAT_STALE_SECONDS
    host = Host()
    now_gib = host.committed_gib()
    print(
        json.dumps(
            {
                "running": running,
                "heartbeat_age_seconds": round(age, 1) if state.get("heartbeat") else None,
                "committed_gib_now": None if now_gib is None else round(now_gib, 2),
                "limit_gib": LIMIT_GIB,
                "resume_gib": RESUME_GIB,
                "install_check": integrity or "ok",
                "frozen": [{k: e[k] for k in ("root", "root_name", "level", "locked", "reason")} for e in state["frozen"]],
                "state_dir": str(state_dir),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if running and not integrity else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="内存总闸看门狗")
    parser.add_argument("command", choices=["run", "status", "resume-all", "selftest", "bundle-hash"])
    parser.add_argument("--state-dir", type=Path, default=None, help="状态与告警目录（默认：已安装时为安装目录下的 state，否则 ~/.auto-pm/memory-gate）")
    parser.add_argument("--require-manifest", action="store_true", help="计划任务用：必须是已安装形态，文件 SHA-256 与 manifest.json 一致才运行")
    args = parser.parse_args(argv)
    state_dir: Path = args.state_dir or default_state_dir()
    root = install_root()
    integrity = ""
    if args.require_manifest or root is not None:
        integrity = verify_install(root) if root is not None else f"{MANIFEST_FILE} 缺失：不是安装形态，--require-manifest 拒绝运行"
    if args.require_manifest and not integrity:
        integrity = interpreter_problem()
    if args.command == "run":
        if integrity:
            Gate(state_dir, committed_gib=lambda: None, processes=list, created_of=created_of, suspend=lambda p: 0, resume=lambda p: 0, alive=lambda p: False).alert(
                "内存总闸拒绝运行：安装文件校验失败", f"{integrity}\n只有管理员重跑 install_memory_gate.ps1 -Install 才能更新。", loud=True
            )
            return 3
        gate = real_gate(state_dir)
        gate.log(f"看门狗启动，上限 {LIMIT_GIB} GiB，解冻线 {RESUME_GIB} GiB")
        run_forever(gate)
        return 0
    if args.command == "status":
        return cmd_status(state_dir, integrity)
    if args.command == "resume-all":
        count = real_gate(state_dir).resume_all()
        print(f"已解冻 {count} 个进程")
        return 0
    if args.command == "bundle-hash":
        combined, lines = bundle_hash()
        for relative, digest in lines:
            print(f"{digest}  {relative}")
        print(f"\n-ExpectedSha256 {combined}")
        return 0
    with tempfile.TemporaryDirectory() as folder:
        problems = selftest(Path(folder), strict=True)
    print("自检通过：冻结与解冻都在真进程上生效" if not problems else "自检失败：\n" + "\n".join(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
