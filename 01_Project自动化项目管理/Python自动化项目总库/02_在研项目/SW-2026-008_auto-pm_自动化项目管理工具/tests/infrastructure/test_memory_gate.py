"""Memory master gate (``scripts/memory_gate.py``): freeze the fastest-growing tree at 40 GiB, never kill, never touch the protected (11-03 memory P1, PR-D)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "memory_gate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("memory_gate_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["memory_gate_under_test"] = module  # dataclasses look the module up by name while it executes
    spec.loader.exec_module(module)
    return module


mg = _load()
GIB = mg.GIB
SELF = 900_001  # the "gate's own pid" in the fake world


class World:
    """A fake machine: a process table, a commit reading, a clock, and the suspend count of every process."""

    def __init__(self) -> None:
        self.procs: dict[int, Any] = {}
        self.committed = 10.0
        self.t = 1_000_000.0
        self.suspended: dict[int, int] = {}
        self.created: dict[int, int] = {}
        self.notices: list[tuple[str, str]] = []
        self.next_pid = 40_000

    def add(self, pid: int, ppid: int, name: str, gib: float = 0.1) -> int:
        self.procs[pid] = mg.Proc(pid, ppid, name, int(gib * GIB))
        self.created.setdefault(pid, 1000 + pid)
        return pid

    def grow(self, pid: int, gib: float) -> None:
        old = self.procs[pid]
        self.procs[pid] = mg.Proc(old.pid, old.ppid, old.name, old.committed + int(gib * GIB))

    def spawn(self, ppid: int, name: str = "git.exe", count: int = 1) -> list[int]:
        found = []
        for _ in range(count):
            self.next_pid += 1
            found.append(self.add(self.next_pid, ppid, name, 0.05))
        return found

    def _suspend(self, pids: list[int]) -> int:
        done = 0
        for pid in pids:
            if pid in self.procs:
                self.suspended[pid] = self.suspended.get(pid, 0) + 1
                done += 1
        return done

    def _resume(self, pids: list[int]) -> int:
        done = 0
        for pid in pids:
            if self.suspended.get(pid, 0) > 0:
                self.suspended[pid] -= 1
                done += 1
        return done

    def frozen(self) -> set[int]:
        return {pid for pid, count in self.suspended.items() if count > 0}

    def gate(self, folder: Path) -> Any:
        return mg.Gate(
            folder,
            committed_gib=lambda: self.committed,
            processes=lambda: list(self.procs.values()),
            created_of=lambda pid: self.created.get(pid, 0),
            suspend=self._suspend,
            resume=self._resume,
            alive=lambda pid: pid in self.procs,
            now=lambda: self.t,
            notify=lambda title, text: self.notices.append((title, text)),
            self_pids=[SELF],
        )

    def tick(self, gate: Any, seconds: float = 5.0, steps: int = 1) -> None:
        for _ in range(steps):
            self.t += seconds
            gate.step()


# The tree the coordinator got from M3 (group A, written up afterwards, not saved as a log): explorer -> Trae CN main -> terminal owner
# -> powershell -> python launcher -> pytest; beside it OpenConsole x4, conhost x3, cmd.exe under another Trae CN child, git.exe under yet
# another, and aha_doctor.exe under the main process.
EXPLORER, TRAE_MAIN, TERMINAL_OWNER, SHELL, LAUNCHER, PYTEST = 8416, 5640, 26936, 26060, 19476, 23192


def _trae_world() -> World:
    w = World()
    w.add(SELF, 700_000, "python.exe")
    w.add(700_000, 1, "powershell.exe")  # the gate's own parent chain
    w.add(EXPLORER, 1, "explorer.exe", 0.3)
    w.add(TRAE_MAIN, EXPLORER, "Trae CN.exe", 0.8)
    w.add(TERMINAL_OWNER, TRAE_MAIN, "Trae CN.exe", 0.4)
    w.add(SHELL, TERMINAL_OWNER, "powershell.exe", 0.1)
    w.add(LAUNCHER, SHELL, "python.exe", 0.05)
    w.add(PYTEST, LAUNCHER, "python.exe", 0.5)
    for index in range(4):
        w.add(30_001 + index, TERMINAL_OWNER, "OpenConsole.exe", 0.02)
    for index in range(3):
        w.add(30_011 + index, SHELL, "conhost.exe", 0.01)
    w.add(25_176, TRAE_MAIN, "Trae CN.exe", 0.2)
    w.add(31_000, 25_176, "cmd.exe", 0.01)
    w.add(6_016, TRAE_MAIN, "Trae CN.exe", 0.2)
    w.add(32_000, 6_016, "git.exe", 0.02)
    w.add(33_000, TRAE_MAIN, "aha_doctor.exe", 0.05)
    return w


PROTECTED_IN_TREE = {EXPLORER, TRAE_MAIN, *range(30_001, 30_005), *range(30_011, 30_014), SELF, 700_000}


def _warm(w: World, gate: Any, steps: int = 4) -> None:
    """A quiet minute at 30 GiB: the gate learns what is normal."""

    w.committed = 30.0
    w.tick(gate, steps=steps)


def _leak(w: World, gate: Any, to_gib: float) -> None:
    """The runaway the Trae tree showed: pytest keeps spawning git.exe (new processes, growth nobody owns)."""

    w.spawn(PYTEST, count=6)
    w.grow(PYTEST, 0.3)
    w.committed = to_gib
    w.tick(gate)


# ---------------------------------------------------------------- thresholds
def test_the_gate_freezes_at_exactly_the_limit_and_not_below(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    w.spawn(PYTEST, count=3)
    w.committed = 39.99
    w.tick(gate)
    assert w.frozen() == set()

    w.committed = 40.0
    w.tick(gate)

    assert w.frozen()


def test_resume_waits_for_below_36_held_30_seconds_and_36_exactly_does_not_resume(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    assert w.frozen()

    w.committed = 36.0
    w.tick(gate, steps=12)  # 60 seconds at exactly 36.0
    assert w.frozen()

    w.committed = 35.9
    w.tick(gate, seconds=5, steps=5)  # 25 seconds below: not yet
    assert w.frozen()
    w.tick(gate, seconds=5, steps=3)  # past 30 seconds
    assert w.frozen() == set()


# ---------------------------------------------------------------- the Trae tree
def test_ladder_of_the_trae_tree_is_the_shell_then_the_terminal_owner_and_never_the_main_process(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    procs = {proc.pid: proc for proc in w.procs.values()}

    assert gate.ladder(procs[PYTEST], procs, gate._protected_pids(procs)) == [SHELL, TERMINAL_OWNER]
    assert gate.ladder(procs[33_000], procs, set()) == [33_000]  # a direct child of the main process: it is its own unit
    assert gate.ladder(procs[TRAE_MAIN], procs, set()) == []  # the application's main process: its parent is explorer, children run below it


def test_the_shell_subtree_is_frozen_first_and_a_flat_reading_afterwards_does_nothing_more(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 40.5)

    frozen = w.frozen()
    assert {SHELL, LAUNCHER, PYTEST} <= frozen and TERMINAL_OWNER not in frozen
    assert not frozen & PROTECTED_IN_TREE  # OpenConsole, conhost, explorer, the main process, the gate and its parents are untouched
    assert 31_000 not in frozen and 32_000 not in frozen and 33_000 not in frozen
    entry = gate.load()["frozen"][0]
    assert entry["root"] == SHELL and entry["level"] == 1 and entry["ladder_rest"] == [TERMINAL_OWNER]
    assert w.notices and "冻结" in w.notices[0][1] and "26060" in w.notices[0][1]

    w.committed = 40.58  # frozen: growth has stopped (0.08 GiB in a minute, the jitter of a browser)
    w.tick(gate, seconds=5, steps=12)

    assert w.frozen() == frozen  # no escalation, no second tree
    assert len(gate.load()["frozen"]) == 1


def test_when_the_shell_freeze_does_not_stop_the_growth_it_escalates_to_the_terminal_owner_but_never_to_the_main_process(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 40.5)
    seen: set[int] = set()

    for _ in range(40):  # it keeps climbing 0.5 GiB every 5 seconds for ever: the gate may use every step it has, and no more
        w.committed += 0.5
        w.tick(gate)
        seen |= w.frozen()

    assert TERMINAL_OWNER in seen and SHELL in seen
    assert not seen & PROTECTED_IN_TREE
    assert TRAE_MAIN not in seen and EXPLORER not in seen
    state = gate.load()["frozen"]
    assert 2 <= len(state) <= mg.MAX_FROZEN_UNITS
    assert [entry["level"] for entry in state][:2] == [1, 2]
    assert max(w.suspended.values()) == 1  # nothing was suspended twice: one resume undoes one freeze


def test_a_terminal_owner_that_is_the_growth_source_itself_can_be_frozen(tmp_path: Path) -> None:
    """Unowned growth hanging on the terminal layer: Trae itself (not only its shell subtree) has to be freezable."""

    w = World()
    w.add(SELF, 700_000, "python.exe")
    w.add(EXPLORER, 1, "explorer.exe")
    w.add(TRAE_MAIN, EXPLORER, "Trae CN.exe")
    w.add(TERMINAL_OWNER, TRAE_MAIN, "Trae CN.exe", 1.0)
    gate = w.gate(tmp_path)
    _warm(w, gate)
    w.grow(TERMINAL_OWNER, 6.0)
    w.spawn(TERMINAL_OWNER, "node.exe", 5)
    w.committed = 41.0
    w.tick(gate)

    assert TERMINAL_OWNER in w.frozen() and TRAE_MAIN not in w.frozen()


# ---------------------------------------------------------------- the protected list and the lone runaway
def test_a_lone_runaway_process_with_nothing_above_it_is_frozen_itself(tmp_path: Path) -> None:
    w = World()
    w.add(SELF, 700_000, "python.exe")
    w.add(EXPLORER, 1, "explorer.exe")
    w.add(77, EXPLORER, "hog.exe", 1.0)
    w.add(79, 77, "conhost.exe", 0.01)  # its console host does not count as something running below it
    gate = w.gate(tmp_path)
    _warm(w, gate)
    w.grow(77, 8.0)
    w.committed = 41.0
    w.tick(gate)

    assert w.frozen() == {77}


def test_an_application_main_process_is_not_frozen_even_when_it_is_what_grows(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    w.grow(TRAE_MAIN, 9.0)  # the main process itself leaks; the processes below it are quiet
    w.committed = 41.0
    w.tick(gate)

    assert TRAE_MAIN not in w.frozen()


def test_the_gate_itself_its_parents_and_every_protected_name_are_never_frozen(tmp_path: Path) -> None:
    w = World()
    w.add(SELF, 700_000, "python.exe", 3.0)
    w.add(700_000, 600_000, "powershell.exe", 3.0)
    w.add(600_000, 1, "WindowsTerminal.exe", 3.0)
    for pid, name in enumerate(["lsass.exe", "csrss.exe", "svchost.exe", "dwm.exe", "MsMpEng.exe", "conhost.exe", "OpenConsole.exe", "?", "System"], start=10):
        w.add(pid, 1, name, 5.0)
    gate = w.gate(tmp_path)
    _warm(w, gate)
    for pid in list(w.procs):
        w.grow(pid, 4.0)
    w.committed = 45.0
    w.tick(gate)

    assert w.frozen() == set()
    assert not w.notices


def test_the_protected_list_is_a_constant_in_the_code_not_read_from_a_file_or_the_environment() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "PROTECTED_NAMES = frozenset(" in source
    assert "os.environ.get(\"MEMORY_GATE" not in source and "environ[\"MEMORY_GATE" not in source
    assert {"explorer.exe", "conhost.exe", "openconsole.exe", "lsass.exe", "svchost.exe", "windowsterminal.exe"} <= mg.PROTECTED_NAMES


# ---------------------------------------------------------------- locking, identity, bookkeeping
def test_the_same_tree_triggering_again_soon_after_resume_is_frozen_and_locked_with_a_loud_reason(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    w.committed = 30.0
    w.tick(gate, seconds=5, steps=10)
    assert w.frozen() == set()  # resumed

    _leak(w, gate, 41.5)  # within 120 seconds: the same shell again

    entry = gate.load()["frozen"][0]
    assert entry["locked"] is True and entry["root"] == SHELL
    assert any("锁定" in text for _title, text in w.notices)
    assert "【锁定】" in (tmp_path / "gate.log").read_text(encoding="utf-8")
    assert "新进程" in entry["reason"] and "GiB" in entry["reason"]  # which tree and how much it grew
    w.committed = 20.0
    w.tick(gate, seconds=5, steps=30)
    assert w.frozen()  # a locked tree is not resumed automatically

    assert gate.resume_all() > 0 and w.frozen() == set() and gate.load()["frozen"] == []


def test_a_tree_that_triggers_again_after_the_relock_window_is_not_locked(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    w.committed = 30.0
    w.tick(gate, seconds=5, steps=10)
    w.tick(gate, seconds=30, steps=6)  # three minutes of calm

    _leak(w, gate, 41.5)

    assert gate.load()["frozen"][0]["locked"] is False


def test_a_reused_pid_is_not_resumed(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    w.created[PYTEST] = 5  # the pid now belongs to another process, created later
    w.committed = 20.0

    w.tick(gate, seconds=5, steps=12)

    assert PYTEST in w.frozen() and SHELL not in w.frozen()  # only the members that are still the same processes were resumed


def test_a_frozen_tree_that_has_exited_is_dropped_from_the_record(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    for pid in [pid for pid in w.procs if pid >= 40_000 or pid in {SHELL, LAUNCHER, PYTEST}]:
        del w.procs[pid]
    w.committed = 35.0

    w.tick(gate)

    assert gate.load()["frozen"] == []


def test_an_unreadable_commit_reading_does_nothing_and_the_gate_survives_a_failing_step(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    gate.committed_gib = lambda: None
    w.tick(gate)
    assert w.frozen() == set() and "读不到" in (tmp_path / "gate.log").read_text(encoding="utf-8")

    def broken() -> list[Any]:
        raise OSError("boom")

    gate.committed_gib = lambda: 50.0
    gate.processes = broken
    mg.run_forever(gate, sleep=lambda _s: None, max_steps=2)  # must return, not raise

    assert "本轮异常 OSError: boom" in (tmp_path / "gate.log").read_text(encoding="utf-8")


def test_nothing_is_ever_killed_the_gate_has_no_kill_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "kill_tree" not in source and ".kill(" not in source.split("def selftest")[0] and "taskkill" not in source


def test_the_heartbeat_and_state_survive_a_restart_of_the_gate(tmp_path: Path) -> None:
    w = _trae_world()
    first = w.gate(tmp_path)
    _warm(w, first)
    _leak(w, first, 41.0)
    frozen = w.frozen()

    second = w.gate(tmp_path)  # a restarted watchdog loads the same record
    w.tick(second)

    assert w.frozen() == frozen and second.load()["heartbeat"] == w.t


# ---------------------------------------------------------------- the real machine
def test_the_real_host_lists_a_child_with_its_parent_and_a_creation_time() -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])  # noqa: S603
    try:
        deadline = time.time() + 20
        found = None
        host = mg.Host()
        while time.time() < deadline and found is None:
            found = next((proc for proc in host.processes() if proc.pid == child.pid), None)
            time.sleep(0.2)
        assert found is not None and found.ppid == os.getpid()
        assert mg.created_of(child.pid) != 0
        assert mg.created_of(2_000_000_000) == 0
    finally:
        child.kill()
        child.wait(timeout=30)


def test_the_selftest_freezes_and_resumes_a_real_process(tmp_path: Path) -> None:
    assert mg.selftest(tmp_path) == []


def test_the_install_script_checks_first_runs_as_system_and_unfreezes_before_it_removes_the_task() -> None:
    script = (ROOT / "scripts" / "install_memory_gate.ps1").read_text(encoding="utf-8-sig")

    assert script.index("selftest") < script.index("Register-ScheduledTask")
    assert "-UserId \"SYSTEM\"" in script and "AtStartup" in script and "RestartCount 3" in script
    assert script.index("STOP") < script.index("resume-all") < script.index("Unregister-ScheduledTask")
