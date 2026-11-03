"""内存总闸看门狗：整机已提交内存到 40 GiB 就冻结涨得最快的一棵进程树（只暂停，绝不杀），回落到 36 GiB 以下再解冻。

为什么（2026-11-02/03 笔记本内存事件）：agent 在自己终端里直接跑回归，已提交内存线性涨到 72 GB。``main.py long-run`` 的守卫只管
经它起的任务，相当于每台电机自己的热继电器；这里是总进线断路器：不管谁在跑（Claude、Trae、反重力、手敲命令），都由它兜底。
它开机自启（计划任务，见 ``install_memory_gate.ps1``），不依赖任何 agent。

规则（判据写死在本文件，不读配置、不读环境变量）：

- 每 5 秒采样整机已提交内存和每个进程的私有已提交量，保留最近 60 秒。
- 已提交 >= 40 GiB：在“可冻结”的进程里，按 60 秒窗内（私有已提交涨幅 + 新进程数 * 0.02 GiB）给每个“单元”打分，
  冻结得分最高的单元的整棵子树。单元 = 涨得最快的进程所属的 shell 层（powershell/pwsh/cmd/bash…）。
- 冻结梯子：冻后每个检查点（至少隔 10 秒，看最近 30 秒），已提交涨速仍 >= 0.3 GiB/分钟且涨幅 >= 0.15 GiB（止不住）就升一层，冻“终端属主”（应用主进程的直接子进程）；
  梯子用完仍涨，才换下一个得分最高的单元；最多同时冻 4 个单元。涨速已低于 0.3 GiB/分钟就不再多冻（冻结只止涨，不降内存）。
- 绝不冻：保护名单（看门狗自己及其祖先、系统关键进程、explorer、终端宿主、杀毒、svchost）；应用主进程（父进程是保护进程或不存在、
  且下面还有非保护的后代，如 Trae CN 主进程）。孤零零涨的单个进程（上无非保护祖先、下无非保护后代）则冻它自己。
- 已提交 < 36 GiB 持续 30 秒：按冻结的反序逐棵解冻，每棵间隔 5 秒。解冻后 120 秒内同一棵再触发 -> 冻住并锁定，不再自动解冻，
  写醒目日志 + 告警文件 + Windows 通知（哪棵树、涨了多少），等人用 ``resume-all``。
- PID 复用：冻结与解冻都核对进程创建时间。

用法：
    python -B scripts/memory_gate.py run         # 看门狗本体（计划任务调用）
    python -B scripts/memory_gate.py status      # 只读：是否在跑、现在多少、冻了谁
    python -B scripts/memory_gate.py resume-all  # 手动解冻全部（含已锁定的）
    python -B scripts/memory_gate.py selftest    # 用无害的假进程走一遍 冻结 -> 解冻（不需要内存压力）
"""

# ruff: noqa: T201
from __future__ import annotations

import argparse
import contextlib
import ctypes
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

else:

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


def notify_user(title: str, text: str) -> None:
    """A message box on every session (Windows ``msg``) and a copy on the public desktop; failures are ignored (the alert file is the record)."""

    if sys.platform != "win32":
        return
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(["msg", "*", "/TIME:0", f"{title}\n{text}"[:900]], capture_output=True, check=False, timeout=15)  # noqa: S603, S607
    with contextlib.suppress(OSError):
        desktop = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
        (desktop / "内存总闸告警.txt").write_text(f"{title}\n{text}\n", encoding="utf-8-sig")


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
        self._record(now, committed, procs)
        state["committed_gib"] = round(committed, 2)
        self._drop_dead(state)
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
        while current is not None and len(chain) < 64 and current.pid not in blocked and not self._protected(current):
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
            if any(other.ppid == proc.pid and not self._protected(other) and other.pid not in blocked for other in procs.values()):
                return []  # an application's main process (something of the application runs below it): never frozen, only what runs below it
            return [proc.pid]  # a lone runaway process: nothing above it to spare, nothing below it to freeze instead
        below_top = chain[:-1]  # chain[-1] is the application's main process
        terminal_owner = below_top[-1]
        shell = next((item for item in below_top if item.name.lower() in SHELL_NAMES), None)
        roots = [terminal_owner.pid] if shell is None else [shell.pid, terminal_owner.pid]
        return list(dict.fromkeys(roots))

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
            if proc.pid in blocked or self._protected(proc):
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
        if not score:
            return None
        unit = max(score, key=lambda key: (score[key], held[key]))
        name = procs[unit].name
        reason = f"{name}（PID {unit}）所在进程树：60 秒内私有已提交 +{growth_of[unit]:.1f} GiB、新进程 {spawned[unit]} 个、合计私有已提交 {held[unit] / GIB:.1f} GiB"
        return ladders[unit], reason

    # ------------------------------------------------ freeze
    def _freeze(self, state: dict[str, Any], now: float, committed: float, procs: dict[int, Proc], ladder: list[int], level: int, reason: str) -> None:
        blocked = self._protected_pids(procs) | {int(pid) for entry in state["frozen"] for pid in (member["pid"] for member in entry["members"])}
        root = ladder[0]
        pids = [pid for pid in self._subtree(root, procs) if pid not in blocked and not self._protected(procs[pid])]
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
                self.log(f"已提交 {committed:.1f} GiB 超限，但没有可冻结的进程")
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
        if rest:
            self._freeze(state, now, committed, procs, rest, int(entry["level"]) + 1, f"{entry['reason']}；冻后涨速仍 {rate:.2f} GiB/分钟，升一层")
            return
        picked = self._pick(now, procs, frozen_pids)
        if picked is None:
            self.log(f"涨速 {rate:.2f} GiB/分钟仍在涨，但没有更多可冻结的进程")
            return
        self._freeze(state, now, committed, procs, picked[0], 1, picked[1])

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
    gate.log("收到 STOP，看门狗退出")


# ---------------------------------------------------------------- command line
def default_state_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "auto_pm" / "memory-gate"  # noqa: SIM112 - Windows variable name
    return Path.home() / ".auto-pm" / "memory-gate"


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
    )


def selftest(state_dir: Path) -> list[str]:
    """Freeze and resume a harmless child with the real code path; returns the problems found (empty = pass).

    The child writes a heartbeat file every 0.2 s; frozen means the file stops moving, resumed means it moves again.  The
    memory readings are injected (first over the limit, then far below), so no memory pressure is needed.
    """

    problems: list[str] = []
    beat = state_dir / "selftest.beat"
    code = "import os, sys, time\nwhile True:\n    open(sys.argv[1], 'w').write(str(time.time()))\n    time.sleep(0.2)\n"
    child = subprocess.Popen([sys.executable, "-c", code, str(beat)])  # noqa: S603
    reading = {"value": LIMIT_GIB + 5.0}
    clock = {"t": 1_000_000.0}
    host = Host()

    def only_the_child() -> list[Proc]:
        """The child and what runs below it (a venv's python.exe is a launcher with the real interpreter as its child); nothing else may be a candidate."""

        everything = host.processes()
        keep = {child.pid}
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
    )

    def moves(seconds: float) -> bool:
        before = beat.stat().st_mtime if beat.exists() else 0.0
        time.sleep(seconds)
        return (beat.stat().st_mtime if beat.exists() else 0.0) > before

    try:
        deadline = time.time() + 20
        while not beat.exists() and time.time() < deadline:
            time.sleep(0.1)
        if not moves(1.0):
            problems.append("假进程没有在跑，自检无法进行")
            return problems
        gate.history.clear()
        gate.step()
        state = gate.load()
        if not any(entry["root"] == child.pid for entry in state["frozen"]):
            problems.append(f"没有冻结假进程（状态：{[e['root'] for e in state['frozen']]}）")
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


def cmd_status(state_dir: Path) -> int:
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
                "frozen": [{k: e[k] for k in ("root", "root_name", "level", "locked", "reason")} for e in state["frozen"]],
                "state_dir": str(state_dir),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if running else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="内存总闸看门狗")
    parser.add_argument("command", choices=["run", "status", "resume-all", "selftest"])
    parser.add_argument("--state-dir", type=Path, default=None, help="状态与告警目录（默认 ProgramData\\auto_pm\\memory-gate）")
    args = parser.parse_args(argv)
    state_dir: Path = args.state_dir or default_state_dir()
    if args.command == "run":
        gate = real_gate(state_dir)
        gate.log(f"看门狗启动，上限 {LIMIT_GIB} GiB，解冻线 {RESUME_GIB} GiB")
        run_forever(gate)
        return 0
    if args.command == "status":
        return cmd_status(state_dir)
    if args.command == "resume-all":
        count = real_gate(state_dir).resume_all()
        print(f"已解冻 {count} 个进程")
        return 0
    with tempfile.TemporaryDirectory() as folder:
        problems = selftest(Path(folder))
    print("自检通过：冻结与解冻都在真进程上生效" if not problems else "自检失败：\n" + "\n".join(problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
