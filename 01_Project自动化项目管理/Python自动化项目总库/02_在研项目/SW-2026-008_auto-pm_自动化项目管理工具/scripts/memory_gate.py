r"""内存总闸看门狗：整机已提交内存到冻结线（默认 = 本机提交上限 x 0.62，31.3 GiB 内存的笔记本约 39 GiB）就冻结涨得最快的一棵进程树（只暂停，绝不杀），回落到解冻线（默认 x 0.57）以下再解冻。

为什么（2026-11-02/03 笔记本内存事件）：agent 在自己终端里直接跑回归，已提交内存线性涨到 72 GB。``main.py long-run`` 的守卫只管
经它起的任务，相当于每台电机自己的热继电器；这里是总进线断路器：不管谁在跑（Claude、Trae、反重力、手敲命令），都由它兜底。
它开机自启（计划任务，见 ``install_memory_gate.ps1``），不依赖任何 agent。

安装形态（审计 579）：计划任务以 SYSTEM 运行，所以代码不能放在用户可写的目录里。``-Install`` 把本脚本和 ``memory_preflight.py``、
``long_run_core.py`` 复制到 ``%ProgramFiles%\AutoPM\MemoryGate``，只给 SYSTEM 和 Administrators 完全控制、Users 只读，记下三个文件的
SHA-256（``manifest.json``）；解释器是系统安装的（或复制进该目录的）Python，不用 .venv；运行加 ``-I -B``。状态、告警、STOP 文件都在该目录的
``state`` 下，普通用户写不进去。每次启动和 ``status`` 都核对 SHA-256，不符就拒绝运行并告警；更新只能由管理员重跑 ``-Install``。

规则（判据写死在本文件；阈值只读一个纯数据配置文件，见下“阈值”；不读环境变量）：

- 每 5 秒采样整机已提交内存和每个进程的私有已提交量，保留最近 60 秒。
- 已提交 >= 冻结线：在“可冻结”的进程里，按 60 秒窗内（私有已提交涨幅 + 新进程数 * 0.02 GiB）给每个“单元”打分，
  冻结得分最高的单元的整棵子树。单元 = 涨得最快的进程所属的 shell 层（powershell/pwsh/cmd/bash…）。
- 冻结梯子：冻后每个检查点（至少隔 10 秒，看最近 30 秒），已提交涨速仍 >= 0.3 GiB/分钟且涨幅 >= 0.15 GiB（止不住）就升一层，冻“终端属主”（应用主进程的直接子进程）；
  梯子用完仍涨，才换下一个得分最高的单元；最多同时冻 4 个单元。涨速已低于 0.3 GiB/分钟就不再多冻（冻结只止涨，不降内存）。
- 只冻交互会话里属于登录用户的进程（Windows：会话号 > 0 且令牌用户 SID 以 S-1-5-21-（本地/域账户）或 S-1-12-1-（Azure AD 账户）开头）；TiWorker 这类 SYSTEM 和服务进程一律不冻。
- 绝不冻：保护名单（看门狗自己及其祖先、系统关键进程、explorer、终端宿主、杀毒、svchost）；应用主进程（父进程是保护进程或不存在、
  且下面还有非保护的后代，如 Trae CN 主进程）。孤零零涨的单个进程（上无非保护祖先、下无非保护后代）则冻它自己。
- 冻后仍在涨时重新打分：只有得分最高的单元落在梯子下一层的子树里才升层，否则换成那个得分最高的单元；没有任何可冻结的进程在涨就不再动手。
- 已提交 < 解冻线持续 30 秒：按冻结的反序逐棵解冻，每棵间隔 5 秒。解冻后 120 秒内同一棵再触发 -> 冻住并锁定，不再自动解冻，
  写醒目日志 + 告警文件 + Windows 通知（哪棵树、涨了多少），等人用 ``resume-all``；没人处理就每 15 分钟再通知一次，不自动解冻。
- 阈值（本节是 2026-11-04 并入驾驶舱时加的）：冻结线 = 提交上限 x ``LIMIT_RATIO``，解冻线 = min(提交上限 x ``RESUME_RATIO``, 冻结线 - 3 GiB)。
  可由 ``scripts/memory_gate.json`` 覆盖（只认 limit_ratio / resume_ratio / limit_gib / resume_gib 四个数值字段，文件大小上限 4 KiB，按纯数据严格解析，
  不是普通文件或是符号链接就不读）。写死的上下限：冻结线在提交上限的 40%~90% 之间、不低于 8 GiB，解冻线至少比冻结线低 3 GiB；
  越界、坏 JSON、未知字段一律整份忽略并用默认值，原因写进日志和 status。每 60 秒重读一次，改配置不用重装。提交上限读不到时退回 40/36 GiB。
- STOP 文件（只认受保护状态目录里的）：看门狗先解冻全部已冻进程再退出。
- PID 复用：冻结与解冻都核对进程创建时间。

用法：
    python -B scripts/memory_gate.py run         # 看门狗本体（计划任务调用）
    python -B scripts/memory_gate.py status      # 只读：是否在跑、现在多少、冻了谁
    python -B scripts/memory_gate.py resume-all  # 手动解冻全部（含已锁定的）
    python -B scripts/memory_gate.py bundle-hash # 四个文件的哈希（pin-check 比对仓库里钉住的那份）
    python -B scripts/memory_gate.py pin-check   # 只读：四个文件的合并哈希是否等于 scripts/memory_gate.pin.json
    python -B scripts/memory_gate.py pin-write   # 开发者改完四个文件后重写钉哈希文件（改动要走 PR 和独立审计）
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
from typing import Any, TypeVar

GIB = 2**30
LIMIT_GIB = 40.0  # the fallback when the commit limit cannot be read (the ratios below are the normal case)
RESUME_GIB = 36.0
LIMIT_RATIO = 0.62
RESUME_RATIO = 0.57
MIN_LIMIT_RATIO = 0.40
MAX_LIMIT_RATIO = 0.90
MIN_LIMIT_FLOOR_GIB = 8.0
MIN_GAP_GIB = 3.0
CONFIG_FILE = "memory_gate.json"
PIN_FILE = "memory_gate.pin.json"
CONFIG_MAX_BYTES = 4096
CONFIG_RELOAD_SECONDS = 60.0
CONFIG_KEYS = frozenset({"limit_ratio", "resume_ratio", "limit_gib", "resume_gib"})
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
STOP_RETRY_SECONDS = 180.0  # STOP with an unreadable state file: keep trying this long (every POLL_SECONDS) before giving up
RENOTIFY_SECONDS = 15 * 60.0  # a locked tree nobody has dealt with is announced again this often
#: On Windows a reader that opens a file in the instant ``os.replace`` swaps it gets PermissionError (winerror 5) or a sharing violation (winerror 32):
#: read it again a few times before calling the file unreadable.  Same numbers as the long-run state files (PR #518).
READ_RETRIES = 8
READ_RETRY_SECONDS = 0.05
_SHARING_ERRORS = (5, 32)
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


class StateUnreadableError(RuntimeError):
    """A file the gate depends on exists but cannot be read (after retries): never to be mistaken for "nothing recorded"."""


def _read_text_retrying(path: Path) -> str:
    """The text of ``path`` (see ``_read_retrying``)."""

    return _read_retrying(path, lambda: path.read_text(encoding="utf-8"))


def _read_bytes_retrying(path: Path) -> bytes:
    """The bytes of ``path`` (see ``_read_retrying``); a virus scanner holding an installed file for a moment is the same kind of race."""

    return _read_retrying(path, path.read_bytes)


_T = TypeVar("_T")


def _read_retrying(path: Path, read: Callable[[], _T]) -> _T:
    """``read()`` of ``path``.  A permission / sharing error is retried ``READ_RETRIES`` times; every other error is raised at once.

    ``FileNotFoundError`` passes through (the one case that means "nothing there"); anything else that stops the read is a
    ``StateUnreadableError`` naming the file and how often it retried.
    """

    retries = 0
    while True:
        try:
            return read()
        except FileNotFoundError:
            raise
        except UnicodeDecodeError as error:
            raise StateUnreadableError(f"读不了 {path}：{type(error).__name__}（未重试）") from error
        except OSError as error:
            if not (isinstance(error, PermissionError) or getattr(error, "winerror", None) in _SHARING_ERRORS):
                raise StateUnreadableError(f"读不了 {path}：{type(error).__name__}（未重试）") from error
            if retries >= READ_RETRIES:
                raise StateUnreadableError(f"读不了 {path}：{type(error).__name__}（已重试 {retries} 次）") from error
            retries += 1
            time.sleep(READ_RETRY_SECONDS)


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

    def commit_limit_gib(self) -> float | None:
        snapshot = self.preflight.read_commit()
        return None if snapshot is None or int(snapshot.limit) <= 0 else float(snapshot.limit) / GIB

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


# ---------------------------------------------------------------- thresholds: per machine, from the commit limit
@dataclass(frozen=True)
class Thresholds:
    """The freeze line and the resume line in GiB, and where they came from (shown by ``status`` and written to the log when they change)."""

    limit_gib: float
    resume_gib: float
    source: str
    commit_limit_gib: float | None = None

    def same_lines(self, other: Thresholds) -> bool:
        return abs(self.limit_gib - other.limit_gib) < 0.005 and abs(self.resume_gib - other.resume_gib) < 0.005


def parse_config(text: str) -> tuple[dict[str, float], str]:
    """(values, problem).  Strict pure-data parse: a JSON object holding only the four known numeric keys; anything else is a problem."""

    try:
        data = json.loads(text)
    except ValueError as error:
        return {}, f"不是合法的 JSON：{type(error).__name__}"
    if not isinstance(data, dict):
        return {}, "顶层不是 JSON 对象"
    unknown = sorted(str(key) for key in data if key not in CONFIG_KEYS)
    if unknown:
        return {}, f"含未知字段 {', '.join(unknown)[:80]}（只认 {', '.join(sorted(CONFIG_KEYS))}）"
    values: dict[str, float] = {}
    for key, value in data.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")) or value <= 0:
            return {}, f"字段 {key} 必须是大于 0 的有限数值"
        values[key] = float(value)
    return values, ""


def read_config(path: Path | None) -> tuple[dict[str, float], str]:
    """(values, note) for ``path``; ``note`` is empty when there is simply no file.  Never raises: a bad file is ignored with the reason in ``note``."""

    if path is None:
        return {}, ""
    try:
        if not os.path.lexists(path):
            return {}, ""
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)() or not path.is_file():
            return {}, f"配置路径 {path.name} 不是普通文件（符号链接、联接点或目录），已忽略"
        raw = _read_bytes_retrying(path)
    except FileNotFoundError:
        return {}, ""
    except (OSError, StateUnreadableError) as error:
        return {}, f"配置文件读不出（{type(error).__name__}），已忽略"
    if len(raw) > CONFIG_MAX_BYTES:
        return {}, f"配置文件超过 {CONFIG_MAX_BYTES} 字节，已忽略"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {}, "配置文件不是 UTF-8，已忽略"
    values, problem = parse_config(text)
    return (values, "") if not problem else ({}, f"配置文件{problem}，已忽略")


def default_thresholds(commit_limit_gib: float | None) -> Thresholds:
    """Ratio defaults of the commit limit; 40/36 when the limit is unknown or too small to be sensible."""

    if commit_limit_gib is None or commit_limit_gib < MIN_LIMIT_FLOOR_GIB / MIN_LIMIT_RATIO:
        return Thresholds(LIMIT_GIB, RESUME_GIB, "默认 40/36 GiB（读不到提交上限）", commit_limit_gib)
    limit = commit_limit_gib * LIMIT_RATIO
    resume = min(commit_limit_gib * RESUME_RATIO, limit - MIN_GAP_GIB)
    return Thresholds(limit, resume, f"默认：提交上限 x {LIMIT_RATIO:g} / x {RESUME_RATIO:g}", commit_limit_gib)


def compute_thresholds(commit_limit_gib: float | None, config: dict[str, float] | None = None, config_note: str = "") -> Thresholds:
    """The effective lines: the ratio defaults, or the (validated) config.  Out of bounds -> the whole config is ignored, never half-applied."""

    base = default_thresholds(commit_limit_gib)
    if not config:
        return base if not config_note else Thresholds(base.limit_gib, base.resume_gib, f"{base.source}；{config_note}", base.commit_limit_gib)
    if commit_limit_gib is None or base.source.startswith("默认 40/36"):
        return Thresholds(base.limit_gib, base.resume_gib, f"{base.source}；提交上限未知，无法核对配置边界，配置已忽略", base.commit_limit_gib)
    limit = config["limit_gib"] if "limit_gib" in config else commit_limit_gib * config["limit_ratio"] if "limit_ratio" in config else base.limit_gib
    if "resume_gib" in config:
        resume = config["resume_gib"]
    elif "resume_ratio" in config:
        resume = commit_limit_gib * config["resume_ratio"]
    else:
        resume = min(limit * RESUME_RATIO / LIMIT_RATIO, limit - MIN_GAP_GIB)
    problem = ""
    if limit < max(MIN_LIMIT_RATIO * commit_limit_gib, MIN_LIMIT_FLOOR_GIB) - 1e-9:
        problem = f"冻结线 {limit:.1f} GiB 低于下限（提交上限的 {MIN_LIMIT_RATIO:.0%} 且不低于 {MIN_LIMIT_FLOOR_GIB:g} GiB）"
    elif limit > MAX_LIMIT_RATIO * commit_limit_gib + 1e-9:
        problem = f"冻结线 {limit:.1f} GiB 高于上限（提交上限的 {MAX_LIMIT_RATIO:.0%}）"
    elif resume > limit - MIN_GAP_GIB + 1e-9:
        problem = f"解冻线 {resume:.1f} GiB 没有比冻结线 {limit:.1f} GiB 至少低 {MIN_GAP_GIB:g} GiB"
    if problem:
        return Thresholds(base.limit_gib, base.resume_gib, f"{base.source}；配置越界已整份忽略：{problem}", commit_limit_gib)
    return Thresholds(limit, resume, f"配置文件（提交上限 {commit_limit_gib:.1f} GiB）", commit_limit_gib)


def _manifest_config_path(root: Path) -> Path | None:
    """The config file the installer recorded (written by an administrator): only the fixed file name is accepted."""

    try:
        recorded = json.loads(_read_text_retrying(root / MANIFEST_FILE)).get("config_path")
    except (OSError, ValueError, StateUnreadableError, AttributeError):
        return None
    if not isinstance(recorded, str) or not recorded:
        return None
    path = Path(recorded)
    return path if path.name == CONFIG_FILE and path.is_absolute() else None


def config_path() -> Path | None:
    """Installed: the path in ``manifest.json``.  A development checkout: ``<project>/scripts/memory_gate.json``."""

    root = install_root()
    if root is not None:
        return _manifest_config_path(root)
    return Path(__file__).resolve().parent / CONFIG_FILE


def resolve_thresholds(commit_limit_gib: float | None, path: Path | None = None) -> Thresholds:
    values, note = read_config(path if path is not None else config_path())
    return compute_thresholds(commit_limit_gib, values, note)


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
        thresholds: Callable[[], Thresholds] | None = None,
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
        self.thresholds = thresholds  # re-read every CONFIG_RELOAD_SECONDS: a changed config file takes effect without a reinstall
        self._thresholds_at: float | None = None
        self.threshold_source = "构造参数"
        self.history: list[tuple[float, float, dict[int, int]]] = []
        self.first_seen: dict[int, float] = {}
        self.last_known_frozen: list[int] = []  # root pids of the last state that could be read: what may still be frozen if the file cannot be read later
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
        """The saved state.  No file at all is the empty state; a file that exists but cannot be read (or is not a JSON object) is an error.

        Returning the empty state for an unreadable file would make the gate (or ``resume-all``) believe nothing is frozen and leave
        processes suspended for good, so it raises ``StateUnreadableError`` instead.
        """

        path = self.dir / STATE_FILE
        try:
            text = _read_text_retrying(path)
        except FileNotFoundError:
            return {"frozen": [], "recent_resumed": {}, "next_id": 1, "watch": None, "below_since": None, "last_resume_at": 0.0}
        try:
            state = json.loads(text)
        except ValueError as error:
            raise StateUnreadableError(f"读不了 {path}：内容不是合法的 JSON（未重试）") from error
        if not isinstance(state, dict):
            raise StateUnreadableError(f"读不了 {path}：内容不是 JSON 对象（未重试）")
        state.setdefault("frozen", [])
        state.setdefault("recent_resumed", {})
        state.setdefault("next_id", 1)
        self.last_known_frozen = [int(entry["root"]) for entry in state["frozen"] if isinstance(entry, dict) and "root" in entry]
        return state

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

    def alert_unreadable_while_hot(self, error: StateUnreadableError) -> bool:
        """The state file cannot be read and the machine is over the limit: nothing can be frozen this round, so say so loudly (ALERT file + notice).

        Returns whether the commit was over the limit (and an alert written).
        """

        try:
            committed = self.committed_gib()
        except Exception:  # noqa: BLE001 - a failing reading must not stop the watchdog
            return False
        if committed is None or committed < self.limit:
            return False
        known = ", ".join(str(pid) for pid in self.last_known_frozen) or "无"
        self.alert(
            f"整机已提交 {committed:.1f} GiB 已超过 {self.limit:g} GiB，但读不了状态文件，总闸这一轮不能冻结任何进程",
            f"{error}\n上次读得到状态时已冻结的进程树根 PID：{known}。\n请立刻手动处理：关掉最占内存的任务；状态文件恢复可读后总闸会自动继续。",
            loud=True,
        )
        return True

    # ------------------------------------------------ one step
    def refresh_thresholds(self, now: float) -> None:
        """Re-read the freeze/resume lines at most once per ``CONFIG_RELOAD_SECONDS``; a failure keeps the lines in force."""

        if self.thresholds is None or (self._thresholds_at is not None and now - self._thresholds_at < CONFIG_RELOAD_SECONDS):
            return
        self._thresholds_at = now
        try:
            fresh = self.thresholds()
        except Exception as error:  # noqa: BLE001 - a config problem must never stop the watchdog; the lines in force stay
            self.log(f"重读阈值失败，沿用 {self.limit:g}/{self.resume_limit:g} GiB：{type(error).__name__}: {error}")
            return
        changed = abs(fresh.limit_gib - self.limit) >= 0.005 or abs(fresh.resume_gib - self.resume_limit) >= 0.005
        first = self.threshold_source == "构造参数"
        self.limit, self.resume_limit, self.threshold_source = fresh.limit_gib, fresh.resume_gib, fresh.source
        if changed or first:
            self.log(f"阈值：冻结线 {self.limit:.2f} GiB，解冻线 {self.resume_limit:.2f} GiB（{fresh.source}）")

    def step(self) -> None:
        state = self.load()
        now = self.now()
        self.refresh_thresholds(now)
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


def run_forever(
    gate: Gate,
    *,
    sleep: Callable[[float], None] = time.sleep,
    poll: float = POLL_SECONDS,
    max_steps: int | None = None,
    stop_retry_seconds: float = STOP_RETRY_SECONDS,
) -> None:
    (gate.dir / STOP_FILE).unlink(missing_ok=True)
    steps = 0
    last_state_error = ("", 0.0)  # (message, monotonic time) - an unreadable state file is logged when it changes or once a minute, not every 5 seconds
    hot_alert_at: float | None = None  # when the "unreadable state while over the limit" alert was last raised (once, then every RENOTIFY_SECONDS)
    while not (gate.dir / STOP_FILE).exists():
        try:
            gate.step()
            hot_alert_at = None
        except StateUnreadableError as error:
            if str(error) != last_state_error[0] or time.monotonic() - last_state_error[1] >= 60:
                gate.log(f"读不了状态，本轮不动作（不会当成空状态）：{error}")
                last_state_error = (str(error), time.monotonic())
            if hot_alert_at is None or time.monotonic() - hot_alert_at >= RENOTIFY_SECONDS:
                try:
                    if gate.alert_unreadable_while_hot(error):
                        hot_alert_at = time.monotonic()
                except Exception as problem:  # noqa: BLE001 - raising the alarm must not stop the watchdog either
                    gate.log(f"告警失败 {type(problem).__name__}: {problem}")
        except Exception as error:  # noqa: BLE001 - the watchdog must outlive any single failure
            gate.log(f"本轮异常 {type(error).__name__}: {error}")
        steps += 1
        if max_steps is not None and steps >= max_steps:
            return
        sleep(poll)
    waited = 0.0
    while True:
        try:
            resumed = gate.resume_all()  # never leave anything frozen behind
            break
        except StateUnreadableError as error:
            if waited >= stop_retry_seconds:  # a few minutes of trying every POLL_SECONDS: the file is not coming back, say so and leave
                known = ", ".join(str(pid) for pid in gate.last_known_frozen) or "无"
                gate.alert(
                    "内存总闸收到 STOP，但读不了状态文件，没有解冻任何进程",
                    f"{error}\n已每 {poll:g} 秒重试 {waited:g} 秒仍读不了。上次读得到状态时已冻结的进程树根 PID（可能仍在冻结）：{known}。\n"
                    "请稍后手动运行：python -B scripts\\memory_gate.py resume-all（读得了时才会解冻）。",
                    loud=True,
                )
                return
            gate.log(f"收到 STOP，但读不了状态，{poll:g} 秒后重试（已等 {waited:g} 秒）：{error}")
            sleep(poll)
            waited += poll
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

    return hashlib.sha256(_read_bytes_retrying(path).replace(b"\r\n", b"\n")).hexdigest()


def bundle_hash(project_root: Path | None = None) -> tuple[str, list[tuple[str, str]]]:
    """(the combined SHA-256, the per-file lines): the value that ``scripts/memory_gate.pin.json`` pins and ``install_memory_gate.ps1`` checks before installing.

    Combined = SHA-256 of ``"<sha256>  <relative path>\n"`` for every file in ``BUNDLE_FILES`` (UTF-8, LF).  The installer computes the same
    thing from the files it is about to copy plus itself, and refuses on any difference from the pin committed in the repository, so the user installs exactly what was merged.
    """

    root = project_root or Path(__file__).resolve().parent.parent
    lines = [(relative, _normalized_sha256(root / relative)) for relative in BUNDLE_FILES]
    text = "".join(f"{digest}  {relative}\n" for relative, digest in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), lines


def pin_path(project_root: Path | None = None) -> Path:
    return (project_root or Path(__file__).resolve().parent.parent) / "scripts" / PIN_FILE


def read_pin(project_root: Path | None = None) -> tuple[str, dict[str, str]]:
    """(the pinned combined hash, the pinned per-file hashes) from ``scripts/memory_gate.pin.json``; raises ValueError when it is missing or malformed."""

    try:
        data = json.loads(_read_text_retrying(pin_path(project_root)))
        combined = data["bundle_sha256"]
        files = data["files"]
    except (OSError, StateUnreadableError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"{PIN_FILE} 缺失或读不出：{type(error).__name__}") from error
    if not (isinstance(combined, str) and len(combined) == 64 and isinstance(files, dict) and all(isinstance(v, str) for v in files.values())):
        raise ValueError(f"{PIN_FILE} 格式不对")
    return combined.lower(), {str(k): v.lower() for k, v in files.items()}


def pin_problem(project_root: Path | None = None) -> str:
    """Why the four bundle files differ from the pin committed in the repository (empty when they match).  Read-only."""

    try:
        pinned, pinned_files = read_pin(project_root)
    except ValueError as error:
        return str(error)
    combined, lines = bundle_hash(project_root)
    if combined == pinned:
        return ""
    changed = [relative for relative, digest in lines if pinned_files.get(relative) != digest]
    return f"四个文件的合并哈希 {combined} 不等于 {PIN_FILE} 钉住的 {pinned}；变了的文件：{', '.join(changed) or '（文件清单不同）'}。改了总闸文件后要重写钉哈希文件并走 PR。"


def write_pin(project_root: Path | None = None) -> None:
    combined, lines = bundle_hash(project_root)
    target = pin_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {"bundle_sha256": combined, "files": dict(lines), "note": "合并哈希覆盖 BUNDLE_FILES 四个文件；改总闸文件必须同时更新本文件，经 PR、独立审计、手动 sw008-ci，由用户合并"}
    target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def interpreter_problem(flags: Any = sys.flags) -> str:
    """The scheduled task must run ``python -I -S -B``: isolated (no PYTHON* variables, no user site, no script directory on the path), no ``site``."""

    missing = [name for name, ok in (("-I", flags.isolated), ("-S", flags.no_site), ("-B", flags.dont_write_bytecode)) if not ok]
    return f"解释器没有用 {' '.join(missing)} 运行" if missing else ""


def verify_install(root: Path) -> str:
    """Why the installed files cannot be trusted (empty when they match the SHA-256 the installer recorded)."""

    try:
        recorded = json.loads(_read_text_retrying(root / MANIFEST_FILE))["files"]
    except FileNotFoundError:
        return f"{MANIFEST_FILE} 缺失"
    except StateUnreadableError as error:
        return f"{MANIFEST_FILE} 读不出：{error}"
    except (ValueError, KeyError, TypeError):
        return f"{MANIFEST_FILE} 缺失或读不出"
    if not isinstance(recorded, dict):
        return f"{MANIFEST_FILE} 格式不对"
    for relative in MANIFEST_FILES:
        want = recorded.get(relative)
        try:
            have = hashlib.sha256(_read_bytes_retrying(root / relative)).hexdigest()
        except FileNotFoundError:
            return f"{relative} 缺失"
        except StateUnreadableError as error:
            return f"{relative} 读不出：{error}"
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
        thresholds=lambda: resolve_thresholds(host.commit_limit_gib()),
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
    except StateUnreadableError as error:
        problems.append(f"自检中读不了状态文件，无法下结论：{error}")
    finally:
        try:
            gate.resume_all()
        except (OSError, StateUnreadableError) as error:  # must not hide the verdict above, and must not skip killing the child below
            problems.append(f"自检结束时没能解冻假进程（读不了状态）：{error}")
            with contextlib.suppress(OSError):
                host.resume([child.pid, *gate.last_known_frozen])
        with contextlib.suppress(OSError):
            child.kill()
        child.wait(timeout=30)
    return problems


def cmd_status(state_dir: Path, integrity: str = "") -> int:
    gate = Gate(state_dir, committed_gib=lambda: None, processes=list, created_of=created_of, suspend=lambda p: 0, resume=lambda p: 0, alive=lambda p: False)
    try:
        state = gate.load()
    except StateUnreadableError as error:
        print(json.dumps({"running": None, "state_error": f"读不了状态：{error}", "install_check": integrity or "ok", "state_dir": str(state_dir)}, ensure_ascii=False, indent=1))
        return 1
    age = time.time() - float(state.get("heartbeat", 0.0))
    running = age <= HEARTBEAT_STALE_SECONDS
    host = Host()
    now_gib = host.committed_gib()
    thresholds = resolve_thresholds(host.commit_limit_gib())
    root = install_root()
    installed_bundle = ""
    if root is not None:
        with contextlib.suppress(OSError, ValueError, StateUnreadableError, AttributeError):
            installed_bundle = str(json.loads(_read_text_retrying(root / MANIFEST_FILE)).get("bundle_sha256", ""))
    print(
        json.dumps(
            {
                "running": running,
                "heartbeat_age_seconds": round(age, 1) if state.get("heartbeat") else None,
                "committed_gib_now": None if now_gib is None else round(now_gib, 2),
                "limit_gib": round(thresholds.limit_gib, 2),
                "resume_gib": round(thresholds.resume_gib, 2),
                "threshold_source": thresholds.source,
                "commit_limit_gib": None if thresholds.commit_limit_gib is None else round(thresholds.commit_limit_gib, 2),
                "installed_bundle_sha256": installed_bundle,
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
    parser.add_argument("command", choices=["run", "status", "resume-all", "selftest", "bundle-hash", "pin-check", "pin-write"])
    parser.add_argument("--state-dir", type=Path, default=None, help="状态与告警目录（默认：已安装时为安装目录下的 state，否则 ~/.auto-pm/memory-gate）")
    parser.add_argument("--require-manifest", action="store_true", help="计划任务用：必须是已安装形态，文件 SHA-256 与 manifest.json 一致才运行")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a Windows pipe defaults to the ANSI code page (cp1252 cannot print the Chinese messages); the installer reads UTF-8
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a captured stream (tests)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")
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
        gate.refresh_thresholds(gate.now())
        gate.log(f"看门狗启动，冻结线 {gate.limit:.2f} GiB，解冻线 {gate.resume_limit:.2f} GiB（{gate.threshold_source}）")
        run_forever(gate)
        return 0
    if args.command == "status":
        return cmd_status(state_dir, integrity)
    if args.command == "resume-all":
        try:
            count = real_gate(state_dir).resume_all()
        except StateUnreadableError as error:
            print(f"没有解冻任何进程：读不了状态文件 {state_dir / STATE_FILE}\n{error}\n稍后重新运行：python -B scripts\\memory_gate.py resume-all", file=sys.stderr)  # noqa: T201
            return 2
        print(f"已解冻 {count} 个进程")
        return 0
    if args.command == "bundle-hash":
        combined, lines = bundle_hash()
        for relative, digest in lines:
            print(f"{digest}  {relative}")
        print(f"\n合并哈希 {combined}")
        return 0
    if args.command == "pin-check":
        problem = pin_problem()
        print(problem or "钉住的哈希与四个文件一致")
        return 1 if problem else 0
    if args.command == "pin-write":
        write_pin()
        print(f"已写 scripts/{PIN_FILE}；这份改动要走 PR、独立审计和手动 sw008-ci")
        return 0
    with tempfile.TemporaryDirectory() as folder:
        problems = selftest(Path(folder), strict=True)
    print("自检通过：冻结与解冻都在真进程上生效" if not problems else "自检失败：\n" + "\n".join(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
