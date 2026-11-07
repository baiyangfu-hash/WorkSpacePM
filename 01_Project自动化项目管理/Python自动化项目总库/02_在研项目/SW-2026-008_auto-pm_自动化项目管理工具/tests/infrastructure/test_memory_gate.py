"""Memory master gate (``scripts/memory_gate.py``): freeze the fastest-growing tree at 40 GiB, never kill, never touch the protected (11-03 memory P1, PR-D)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

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


@pytest.fixture(autouse=True)
def _no_real_message_box(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-16: no test may put a real warning box on the user's desktop (``mg.main(["run", "--require-manifest", ...])`` used to; ``WTSSendMessageW`` does not wait for a click, so the boxes piled up)."""

    monkeypatch.setattr(mg, "message_box", lambda title, text: True, raising=False)

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
        self.system_pids: set[int] = set()  # SYSTEM / service processes: not a logged-in user's, never eligible

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
        gate = mg.Gate(
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
            eligible=lambda pid: pid not in self.system_pids,
        )
        gate.self_pids = {SELF}  # Gate adds the real os.getpid() to its protected set; a real pid equal to a fake pid of the world (26936) hid it from the ladder (D-92)
        return gate

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


def test_when_the_growth_hangs_on_the_terminal_layer_it_climbs_to_the_terminal_owner_but_never_to_the_main_process(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 40.5)
    seen: set[int] = set()

    for _ in range(40):  # it keeps climbing 0.5 GiB every 5 seconds and the new processes now hang on the terminal owner: the gate may use every step it has, and no more
        w.spawn(TERMINAL_OWNER, "node.exe", 2)
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


def test_audit_579_a_steam_that_grows_after_the_shell_freeze_gets_frozen_not_the_terminal_owner(tmp_path: Path) -> None:
    """The probe: the shell tree is frozen, memory keeps rising because another application's helpers grow; the next rung must not be taken for the cause."""

    w = _trae_world()
    steam = w.add(5_000, EXPLORER, "steam.exe", 0.5)
    helpers = [w.add(5_001 + index, steam, "steamwebhelper.exe", 0.3) for index in range(3)]
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 40.5)
    assert SHELL in w.frozen()

    for _ in range(12):
        for pid in helpers:
            w.grow(pid, 1.0)
        w.spawn(helpers[0], "steamwebhelper.exe", 2)
        w.committed += 0.6
        w.tick(gate)

    assert TERMINAL_OWNER not in w.frozen() and TRAE_MAIN not in w.frozen() and steam not in w.frozen()
    assert w.frozen() & {*helpers}  # the unit that really grows was frozen instead
    assert any(entry["level"] == 1 and entry["root"] in helpers for entry in gate.load()["frozen"])


def test_a_rise_that_no_freezable_process_explains_freezes_nothing_more(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 40.5)
    before = w.frozen()

    for _ in range(30):  # memory rises, but no process anywhere grows or appears
        w.committed += 0.5
        w.tick(gate)

    assert w.frozen() == before and len(gate.load()["frozen"]) == 1
    assert "没有一个在涨" in (tmp_path / "gate.log").read_text(encoding="utf-8")


def test_at_the_limit_with_nothing_growing_the_gate_does_not_freeze_a_bystander(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    w.committed = 42.0
    w.tick(gate, steps=6)  # high, but flat and nothing new: the largest process is not "the cause"

    assert w.frozen() == set() and not w.notices


def test_system_and_service_processes_are_never_frozen_even_when_they_grow(tmp_path: Path) -> None:
    """TiWorker (TrustedInstaller) is SYSTEM: not a logged-in user's process."""

    w = _trae_world()
    w.add(700, 1, "services.exe")
    tiworker = w.add(701, 700, "TiWorker.exe", 0.5)
    w.system_pids.add(tiworker)
    gate = w.gate(tmp_path)
    _warm(w, gate)
    w.grow(tiworker, 9.0)
    w.spawn(tiworker, "TiWorker.exe", 4)
    w.system_pids.update(w.procs)  # the spawned children are SYSTEM's as well
    w.system_pids -= {pid for pid in w.procs if pid in {EXPLORER, TRAE_MAIN, TERMINAL_OWNER, SHELL, LAUNCHER, PYTEST}}
    w.committed = 41.0
    w.tick(gate)

    assert w.frozen() == set() and not w.notices


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


def test_a_locked_tree_nobody_handles_is_announced_again_every_15_minutes_and_stays_frozen(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    w.committed = 30.0
    w.tick(gate, seconds=5, steps=10)
    _leak(w, gate, 41.5)
    assert gate.load()["frozen"][0]["locked"] is True
    first = len(w.notices)

    w.committed = 20.0
    w.tick(gate, seconds=60, steps=14)  # 14 minutes
    assert len(w.notices) == first
    w.tick(gate, seconds=60, steps=2)  # past 15 minutes
    assert len(w.notices) == first + 1 and "没有人处理" in w.notices[-1][1]
    w.tick(gate, seconds=60, steps=16)
    assert len(w.notices) == first + 2 and w.frozen()


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


def test_stop_unfreezes_everything_before_the_gate_exits(tmp_path: Path) -> None:
    w = _trae_world()
    gate = w.gate(tmp_path)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    assert w.frozen()
    calls = {"n": 0}

    def sleep(_seconds: float) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            (tmp_path / mg.STOP_FILE).write_text("x", encoding="utf-8")

    mg.run_forever(gate, sleep=sleep, max_steps=50)

    assert w.frozen() == set() and gate.load()["frozen"] == []
    assert "收到 STOP，已解冻" in (tmp_path / "gate.log").read_text(encoding="utf-8")


def _install(root: Path) -> None:
    for relative in mg.MANIFEST_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    files = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in mg.MANIFEST_FILES}
    (root / mg.MANIFEST_FILE).write_text(json.dumps({"files": files}), encoding="utf-8")


def test_the_installed_files_must_match_the_hashes_the_installer_recorded(tmp_path: Path) -> None:
    _install(tmp_path)
    assert mg.verify_install(tmp_path) == ""

    (tmp_path / "scripts" / "memory_gate.py").write_text("# changed\n", encoding="utf-8")
    assert "scripts/memory_gate.py 的 SHA-256 与安装时记录的不一致" in mg.verify_install(tmp_path)

    _install(tmp_path)
    (tmp_path / "auto_pm" / "infrastructure" / "long_run_core.py").unlink()
    assert "long_run_core.py 缺失" in mg.verify_install(tmp_path)

    _install(tmp_path)
    manifest = json.loads((tmp_path / mg.MANIFEST_FILE).read_text(encoding="utf-8"))
    del manifest["files"]["auto_pm/infrastructure/memory_preflight.py"]
    (tmp_path / mg.MANIFEST_FILE).write_text(json.dumps(manifest), encoding="utf-8")
    assert "memory_preflight.py" in mg.verify_install(tmp_path)

    (tmp_path / mg.MANIFEST_FILE).write_text("{not json", encoding="utf-8")
    assert "读不出" in mg.verify_install(tmp_path)


def test_the_scheduled_task_form_refuses_to_run_without_an_install_and_says_so(tmp_path: Path) -> None:
    code = mg.main(["run", "--require-manifest", "--state-dir", str(tmp_path)])

    assert code == 3
    alerts = list(tmp_path.glob("ALERT-*.txt"))
    assert alerts and "拒绝运行" in alerts[0].read_text(encoding="utf-8")


def test_the_state_and_alerts_live_in_the_install_folder_and_nothing_is_written_to_a_public_place() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "Desktop" not in source and "ProgramData" not in source and "PUBLIC" not in source
    assert mg.install_root() is None  # a development checkout has no manifest beside it


def test_the_user_process_test_is_false_for_what_cannot_be_identified() -> None:
    assert mg.user_process(2_000_000_000) is False and mg.user_process(0) is False and mg.user_process(4) is False
    if sys.platform != "win32":
        assert mg.user_process(os.getpid()) is True


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


def _install_script() -> str:
    return (ROOT / "scripts" / "install_memory_gate.ps1").read_text(encoding="utf-8-sig")


def _function_body(script: str, name: str) -> str:
    """The text of ``function <name>`` up to the next top-level ``function`` (or the dot-source guard)."""

    start = script.index(f"function {name}")
    rest = script[start + 1 :]
    ends = [rest.index(marker) for marker in ("\nfunction ", "\n# Tests dot-source") if marker in rest]
    return script[start : start + 1 + min(ends)] if ends else script[start:]


def _code_after_help(script: str) -> str:
    return "\n".join(line for line in script[script.index("#>") :].splitlines() if not line.lstrip().startswith("#"))


def test_a_venv_launcher_is_never_the_root_the_real_interpreter_below_it_is(tmp_path: Path) -> None:
    """M3 real-machine finding: a venv's python.exe is a launcher whose child is the real interpreter; the growing process is the child."""

    w = World()
    w.add(SELF, 700_000, "python.exe")
    launcher = w.add(23_308, SELF, "python.exe", 0.01)  # started by the (protected) gate's own process, like the selftest's child
    real = w.add(23_309, launcher, "python.exe", 0.3)
    gate = w.gate(tmp_path)
    _warm(w, gate)
    w.grow(real, 8.0)
    w.spawn(real, "python.exe", 2)
    w.committed = 41.0
    w.tick(gate)

    entry = gate.load()["frozen"][0]
    assert entry["root"] == real and launcher not in w.frozen() and real in w.frozen()


def test_the_embedded_python_hash_is_pinned_in_the_installer_as_a_real_sha256() -> None:
    """Audit 579 R1: the installer fetches the official embeddable Python of a fixed version and checks a hash written in the code."""

    script = _install_script()
    match = re.search(r'\$EmbedSha256 = "([^"]*)"', script)

    assert match is not None and re.fullmatch(r"[0-9a-f]{64}", match.group(1)), "嵌入式 Python 的 SHA-256 还没有写死（PIN-REQUIRED）"
    assert '$EmbedVersion = "3.12.10"' in script and "python-3.12.10-embed-amd64.zip" in script
    assert "-notmatch '^[0-9a-f]{64}$'" in script  # an unpinned installer refuses to run


def test_the_install_script_never_uses_a_python_found_on_the_machine_or_a_venv() -> None:
    script = _install_script()
    code = _code_after_help(script)

    for forbidden in ("-CopyPython", "Test-UserWritable", "Get-Command py", "Get-Command python", ".venv", "Find-SystemPython"):
        assert forbidden not in code
    assert "Expand-Archive" in code and "installedPython" in code


def test_the_install_script_checks_the_sources_before_it_touches_anything_and_locks_the_folder_before_it_copies_into_it() -> None:
    script = _install_script()
    apply_body = _function_body(script, "Invoke-Apply")

    order = [
        "Get-BundleHash $Root",
        "$bundle.Combined -ne $Expected.ToLower()",
        "Remove-GateInstallation $Dest $TaskName $false",
        "New-Item -ItemType Directory -Force -Path $Dest | Out-Null",
        '"/inheritance:r"',
        "Assert-DestLocked $Dest",
        "Copy-Item -LiteralPath $Zip",
        "(Get-FileHash -Algorithm SHA256 -LiteralPath $zipInDest)",
        "Expand-CheckedPython $zipInDest",
        "Copy-Item -LiteralPath (Join-Path $Root",
        'WriteAllText((Join-Path $Dest "manifest.json")',
        "selftest",
        "Register-ScheduledTask",
    ]
    positions = [apply_body.index(marker) for marker in order]

    assert positions == sorted(positions), dict(zip(order, positions, strict=True))
    for git_word in ("git.exe", "fetch", "merge-base", "status --porcelain", "Invoke-Native \"git\""):
        assert git_word not in apply_body, git_word  # audit 579 R5: no git in the elevated path; the combined hash is the only gate
    assert "*S-1-5-18" in apply_body and "*S-1-5-32-544" in apply_body and "*S-1-5-32-545:(OI)(CI)RX" in apply_body
    assert "Assert-Admin" in apply_body[:200]


def test_the_elevated_phase_requires_the_hash_and_the_bundle_covers_the_three_sources_and_the_installer_itself() -> None:
    script = _install_script()
    apply_body = _function_body(script, "Invoke-Apply")

    assert "-notmatch '^[0-9a-fA-F]{64}$'" in apply_body and "Read-PinnedHash $Root" in apply_body  # the hash handed over AND the pin in the repo must both match
    assert list(mg.BUNDLE_FILES) == sorted(mg.BUNDLE_FILES)
    assert set(mg.BUNDLE_FILES) == {
        "auto_pm/infrastructure/long_run_core.py", "auto_pm/infrastructure/memory_preflight.py", "scripts/install_memory_gate.ps1", "scripts/memory_gate.py",
    }  # fmt: skip
    listed = re.search(r"\$BundleFiles = @\((.*?)\n\)", script, re.S)
    assert listed is not None
    assert re.findall(r'"([^"]+)"', listed.group(1)) == list(mg.BUNDLE_FILES)  # the PowerShell side hashes the very same list in the same order


def test_the_task_and_the_selftest_run_isolated_without_site_and_without_bytecode() -> None:
    script = _install_script()

    assert script.count('"-I", "-S", "-B"') >= 6 and "-I -S -B" in script and "run --require-manifest" in script  # every Python run (task, selftest, status, resume-all) is isolated
    assert mg.interpreter_problem(SimpleNamespace(isolated=1, no_site=1, dont_write_bytecode=1)) == ""
    assert "-S" in mg.interpreter_problem(SimpleNamespace(isolated=1, no_site=0, dont_write_bytecode=1))
    assert "-I" in mg.interpreter_problem(SimpleNamespace(isolated=0, no_site=1, dont_write_bytecode=1))
    assert mg.interpreter_problem(sys.flags) != "" or sys.flags.isolated  # pytest itself is not isolated


def test_the_bundle_hash_is_stable_across_line_endings_and_changes_with_any_file(tmp_path: Path) -> None:
    for relative in mg.BUNDLE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"# {relative}\nline\n".encode())
    first, lines = mg.bundle_hash(tmp_path)
    assert len(first) == 64 and [relative for relative, _digest in lines] == list(mg.BUNDLE_FILES)

    (tmp_path / "scripts" / "install_memory_gate.ps1").write_bytes(b"# scripts/install_memory_gate.ps1\r\nline\r\n")  # a Windows checkout of the same text
    assert mg.bundle_hash(tmp_path)[0] == first

    for relative in mg.BUNDLE_FILES:
        original = (tmp_path / relative).read_bytes()
        (tmp_path / relative).write_bytes(original + b"x")
        assert mg.bundle_hash(tmp_path)[0] != first, relative
        (tmp_path / relative).write_bytes(original)


def test_the_bundle_hash_command_prints_the_combined_hash_that_pin_check_compares() -> None:
    done = subprocess.run([sys.executable, "-B", str(SCRIPT), "bundle-hash"], capture_output=True, check=True, timeout=60)  # noqa: S603
    text = done.stdout.decode("utf-8")

    assert f"合并哈希 {mg.bundle_hash()[0]}" in text and "scripts/memory_gate.py" in text


def test_a_logged_in_users_sid_includes_azure_ad_accounts() -> None:
    assert mg.USER_SID_PREFIXES == ("S-1-5-21-", "S-1-12-1-")
    assert "S-1-5-18".startswith(mg.USER_SID_PREFIXES) is False and "S-1-5-80-1".startswith(mg.USER_SID_PREFIXES) is False


def test_without_a_shell_on_the_path_the_first_rung_is_the_branch_that_holds_the_culprit_not_the_terminal_owner(tmp_path: Path) -> None:
    w = World()
    w.add(SELF, 700_000, "python.exe")
    w.add(EXPLORER, 1, "explorer.exe")
    w.add(TRAE_MAIN, EXPLORER, "app.exe")
    w.add(TERMINAL_OWNER, TRAE_MAIN, "host.exe")
    branch = w.add(500, TERMINAL_OWNER, "worker.exe")
    leaf = w.add(501, branch, "task.exe")
    gate = w.gate(tmp_path)
    procs = {proc.pid: proc for proc in w.procs.values()}

    assert gate.ladder(procs[leaf], procs, gate._protected_pids(procs)) == [branch, TERMINAL_OWNER]


def test_the_install_script_forces_tls12_and_points_to_the_local_zip_when_it_cannot() -> None:
    """Audit 579 P3: Windows PowerShell 5.1 may default to old TLS; a download failure must name the -PythonZip way out."""

    script = _install_script()

    assert script.index("Tls12") < script.index("function Get-EmbeddedPythonZip")
    assert "-PythonZip" in script[script.index("Tls12") : script.index("function Get-EmbeddedPythonZip")]
    download = script[script.index("Invoke-WebRequest") - 200 : script.index("Invoke-WebRequest") + 400]
    assert "catch" in download and "-PythonZip" in download


def test_the_install_script_checks_the_python_exe_is_signed_by_the_python_software_foundation_before_using_it() -> None:
    script = _install_script()
    expand = _function_body(script, "Expand-CheckedPython")
    apply_body = _function_body(script, "Invoke-Apply")
    prepare = _function_body(script, "Invoke-Prepare")

    assert expand.index("Expand-Archive") < expand.index("Get-AuthenticodeSignature")
    assert "Python Software Foundation" in expand and '-ne "Valid"' in expand
    assert apply_body.index("Expand-CheckedPython") < apply_body.index("Copy-Item -LiteralPath (Join-Path $Root") < apply_body.index("selftest")
    assert prepare.index("Expand-CheckedPython") < prepare.index("selftest")  # tried in a temp folder first


def test_the_uninstall_path_copes_with_a_half_finished_install() -> None:
    """Audit 579 P3: no Python, no state folder or no task must not abort the removal (and a broken python.exe falls back to the clean-up path)."""

    script = _install_script()
    code = _function_body(script, "Remove-GateInstallation")

    assert "Test-Path -LiteralPath $stateDir" in code and "Test-Path -LiteralPath $python" in code
    assert code.index("resume-all") < code.index("Unregister-ScheduledTask") < code.index("Remove-Item -LiteralPath $Folder")
    assert "Test-Path -LiteralPath $Folder" in code[code.index("Remove-Item -LiteralPath $Folder") :]  # reports a folder that could not be removed
    assert "-Uninstall" in script and "-Repair" in script
    entry = script[script.index("# ---------------------------------------------------------------- entry") :]
    assert "Remove-GateInstallation $Dest $TaskName $ForceDelete.IsPresent" in entry  # -Repair and -Uninstall share one clean-up path


def test_the_installer_is_itself_covered_by_the_pinned_hash_and_checked_before_anything_is_touched() -> None:
    script = _install_script()
    prepare = _function_body(script, "Invoke-Prepare")

    assert "scripts/install_memory_gate.ps1" in mg.BUNDLE_FILES
    assert prepare.index("Read-PinnedHash") < prepare.index("Get-EmbeddedPythonZip") < prepare.index("Expand-CheckedPython")
    assert re.search(r"\$Dest\b|ProgramFiles", prepare) is None  # the unprivileged phase never touches the install folder


# ---------------------------------------------------------------- an unreadable state file is not an empty one (the #518 lesson, applied to the gate)
class _SharingViolationError(OSError):
    """Windows' "file in use" (``winerror`` 32); a class attribute so it also exists on Linux."""

    winerror = 32


def _fail_reads_of(monkeypatch: pytest.MonkeyPatch, name: str, error: OSError, times: int | None) -> dict[str, int]:
    """``Path.read_text`` of files called ``name`` raises ``error`` ``times`` times (None: always), then works.  Returns the call counter."""

    calls = {"n": 0}
    real = Path.read_text

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == name:
            calls["n"] += 1
            if times is None or calls["n"] <= times:
                raise error
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(mg, "READ_RETRY_SECONDS", 0.0)
    return calls


def _gate_with_a_frozen_tree(folder: Path) -> tuple[World, Any]:
    w = _trae_world()
    gate = w.gate(folder)
    _warm(w, gate)
    _leak(w, gate, 41.0)
    assert gate.load()["frozen"], "setup: the leak must have been frozen"
    return w, gate


def test_a_missing_state_file_is_the_empty_state(tmp_path: Path) -> None:
    state = World().gate(tmp_path).load()

    assert state["frozen"] == [] and state["next_id"] == 1


@pytest.mark.parametrize("failures", [1, 3, mg.READ_RETRIES])
@pytest.mark.parametrize("error", [PermissionError(13, "denied"), _SharingViolationError("in use")], ids=["permission-or-winerror5", "winerror32"])
def test_a_state_read_that_meets_the_atomic_replace_is_retried_and_returns_the_real_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failures: int, error: OSError
) -> None:
    _w, gate = _gate_with_a_frozen_tree(tmp_path)
    frozen = [entry["root"] for entry in gate.load()["frozen"]]
    calls = _fail_reads_of(monkeypatch, mg.STATE_FILE, error, failures)

    state = gate.load()

    assert [entry["root"] for entry in state["frozen"]] == frozen  # the real state, not an empty one
    assert calls["n"] == failures + 1


def test_a_state_read_that_keeps_failing_raises_with_the_path_and_the_retries_and_never_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _w, gate = _gate_with_a_frozen_tree(tmp_path)
    calls = _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)

    with pytest.raises(mg.StateUnreadableError) as caught:
        gate.load()

    assert str(tmp_path / mg.STATE_FILE) in str(caught.value) and f"已重试 {mg.READ_RETRIES} 次" in str(caught.value)
    assert calls["n"] == mg.READ_RETRIES + 1 and mg.READ_RETRIES == 8


def test_other_read_errors_and_a_corrupt_file_are_not_retried_and_not_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _w, gate = _gate_with_a_frozen_tree(tmp_path)
    calls = _fail_reads_of(monkeypatch, mg.STATE_FILE, OSError(5, "input/output error"), None)
    with pytest.raises(mg.StateUnreadableError, match="未重试"):
        gate.load()
    assert calls["n"] == 1
    monkeypatch.undo()

    (tmp_path / mg.STATE_FILE).write_text("{ not json", encoding="utf-8")
    with pytest.raises(mg.StateUnreadableError, match="不是合法的 JSON"):
        gate.load()
    (tmp_path / mg.STATE_FILE).write_text("[1]", encoding="utf-8")
    with pytest.raises(mg.StateUnreadableError, match="不是 JSON 对象"):
        gate.load()


def test_a_step_that_cannot_read_the_state_does_nothing_and_leaves_the_file_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, gate = _gate_with_a_frozen_tree(tmp_path)
    before = (tmp_path / mg.STATE_FILE).read_bytes()
    frozen_before = dict(w.suspended)
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)
    w.committed = 20.0  # would resume everything if the gate believed the (empty) state

    with pytest.raises(mg.StateUnreadableError):
        gate.step()

    monkeypatch.undo()
    assert (tmp_path / mg.STATE_FILE).read_bytes() == before and w.suspended == frozen_before


def test_the_loop_survives_an_unreadable_state_logs_it_and_does_not_flood_the_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _w, gate = _gate_with_a_frozen_tree(tmp_path)
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)

    mg.run_forever(gate, sleep=lambda _s: None, max_steps=30)

    log = (tmp_path / "gate.log").read_text(encoding="utf-8")
    assert log.count("读不了状态，本轮不动作") == 1  # 30 rounds, one line (same message, under a minute)


def test_a_stop_that_cannot_read_the_state_raises_a_loud_alert_instead_of_claiming_it_resumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _w, gate = _gate_with_a_frozen_tree(tmp_path)
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)

    def stop_now(_seconds: float) -> None:
        (tmp_path / mg.STOP_FILE).write_text("stop", encoding="utf-8")

    mg.run_forever(gate, sleep=stop_now)

    texts = [path.read_text(encoding="utf-8") for path in tmp_path.glob("ALERT-*.txt")]  # the names carry only the second, so a run crossing a second writes two files and the glob order says nothing (D-91)
    assert any("没有解冻任何进程" in text and "resume-all" in text for text in texts)
    assert "已解冻" not in (tmp_path / "gate.log").read_text(encoding="utf-8").split("【锁定】")[-1]


def test_a_stop_whose_state_comes_back_within_the_retry_window_still_unfreezes_everything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, gate = _gate_with_a_frozen_tree(tmp_path)
    assert w.frozen()
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), 3 * (mg.READ_RETRIES + 1))  # three whole loads fail (the first round's step, two STOP retries), the fourth works
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        (tmp_path / mg.STOP_FILE).write_text("stop", encoding="utf-8")

    mg.run_forever(gate, sleep=sleep)

    assert w.frozen() == set()  # everything was resumed
    assert sleeps == [mg.POLL_SECONDS] * 3  # the loop's own sleep, then two retries every 5 s
    assert not any("没有解冻任何进程" in path.read_text(encoding="utf-8") for path in tmp_path.glob("ALERT-*.txt"))


def test_a_stop_that_never_gets_the_state_back_retries_three_minutes_then_alerts_with_the_possibly_frozen_pids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, gate = _gate_with_a_frozen_tree(tmp_path)
    roots = [entry["root"] for entry in gate.load()["frozen"]]
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        (tmp_path / mg.STOP_FILE).write_text("stop", encoding="utf-8")

    mg.run_forever(gate, sleep=sleep)

    assert len(sleeps) == 1 + int(mg.STOP_RETRY_SECONDS / mg.POLL_SECONDS) == 37  # the loop's own sleep + 36 retries = 180 s
    texts = [path.read_text(encoding="utf-8") for path in tmp_path.glob("ALERT-*.txt")]
    text = next((candidate for candidate in texts if "没有解冻任何进程" in candidate), "")  # not the glob's last file: a run that crosses a second writes two (D-91)
    assert "没有解冻任何进程" in text and "resume-all" in text and "180" in text
    assert all(str(root) in text for root in roots) and roots
    assert w.frozen()  # (and the alert says so, instead of the log claiming "已解冻")


def test_an_unreadable_state_while_over_the_limit_raises_one_loud_alert_not_one_per_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, gate = _gate_with_a_frozen_tree(tmp_path)
    roots = [entry["root"] for entry in gate.load()["frozen"]]
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)
    w.committed = 45.0
    clock = {"t": 0.0}
    monkeypatch.setattr(mg.time, "monotonic", lambda: clock["t"])

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    mg.run_forever(gate, sleep=sleep, max_steps=20)  # 100 s of rounds

    alerts = [path for path in tmp_path.glob("ALERT-*.txt") if "读不了状态文件" in path.read_text(encoding="utf-8")]
    assert len(alerts) == 1  # 20 rounds, one alert
    text = alerts[0].read_text(encoding="utf-8")
    assert "已超过" in text and "读不了状态文件" in text and all(str(root) in text for root in roots)
    assert any("读不了状态文件" in notice[1] for notice in w.notices)  # a Windows notice too, like a freeze
    assert "【锁定】" in (tmp_path / "gate.log").read_text(encoding="utf-8")

    clock["t"] += mg.RENOTIFY_SECONDS  # nobody did anything for a quarter of an hour: say it again
    mg.run_forever(gate, sleep=sleep, max_steps=1)
    assert sum("读不了状态文件" in notice[1] for notice in w.notices) == 2


def test_an_unreadable_state_below_the_limit_stays_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, gate = _gate_with_a_frozen_tree(tmp_path)
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)
    w.committed = 30.0
    notices_before, alerts_before = len(w.notices), len(list(tmp_path.glob("ALERT-*.txt")))  # (the freeze itself already wrote one)

    mg.run_forever(gate, sleep=lambda _s: None, max_steps=10)

    assert len(list(tmp_path.glob("ALERT-*.txt"))) == alerts_before and len(w.notices) == notices_before


def test_the_alert_for_an_unreadable_state_is_raised_again_after_the_state_was_read_and_failed_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, gate = _gate_with_a_frozen_tree(tmp_path)
    w.committed = 45.0
    real = Path.read_text
    broken = {"on": True}

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name == mg.STATE_FILE and broken["on"]:
            raise PermissionError(13, "denied")
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(mg, "READ_RETRY_SECONDS", 0.0)

    rounds = {"n": 0}

    def sleep(_seconds: float) -> None:
        rounds["n"] += 1
        broken["on"] = rounds["n"] not in (2,)  # broken, broken, one readable round, broken, broken ...

    mg.run_forever(gate, sleep=sleep, max_steps=5)

    # a readable round resets the "already told you" memory, so the second outage is announced again (the first one only once)
    assert sum("读不了状态文件" in notice[1] for notice in w.notices) == 2


def test_the_selftest_reports_its_verdict_even_when_the_state_cannot_be_read_at_the_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``finally`` of the selftest used to let a ``StateUnreadableError`` replace the verdict (and skip killing the child)."""

    real = mg.Gate.resume_all

    def resume_all(self: Any) -> int:
        raise mg.StateUnreadableError("读不了 state.json（已重试 8 次）")

    monkeypatch.setattr(mg.Gate, "resume_all", resume_all)

    problems = mg.selftest(tmp_path)  # must return, not raise

    monkeypatch.setattr(mg.Gate, "resume_all", real)
    assert any("没能解冻假进程" in problem for problem in problems)
    assert not any("没有冻结假进程" in problem or "回落后没有解冻" in problem for problem in problems)  # the real verdict is still the verdict


def test_resume_all_with_an_unreadable_state_stops_with_a_nonzero_exit_code_the_path_and_how_to_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / mg.STATE_FILE).write_text(json.dumps({"frozen": []}), encoding="utf-8")
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)

    code = mg.main(["resume-all", "--state-dir", str(tmp_path)])

    err = capsys.readouterr().err
    assert code != 0 and str(tmp_path / mg.STATE_FILE) in err and "没有解冻任何进程" in err and "重新运行" in err and "resume-all" in err


def test_status_with_an_unreadable_state_says_it_cannot_read_the_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / mg.STATE_FILE).write_text(json.dumps({"frozen": []}), encoding="utf-8")
    _fail_reads_of(monkeypatch, mg.STATE_FILE, PermissionError(13, "denied"), None)

    code = mg.main(["status", "--state-dir", str(tmp_path)])

    shown = json.loads(capsys.readouterr().out)
    assert code == 1 and "读不了状态" in shown["state_error"] and shown["running"] is None


def test_the_manifest_read_is_retried_too_and_an_unreadable_one_is_a_problem_not_a_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for relative in mg.MANIFEST_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    files = {relative: hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() for relative in mg.MANIFEST_FILES}
    (tmp_path / mg.MANIFEST_FILE).write_text(json.dumps({"files": files}), encoding="utf-8")

    _fail_reads_of(monkeypatch, mg.MANIFEST_FILE, PermissionError(13, "denied"), 3)
    assert mg.verify_install(tmp_path) == ""
    monkeypatch.undo()

    _fail_reads_of(monkeypatch, mg.MANIFEST_FILE, PermissionError(13, "denied"), None)
    assert "读不出" in mg.verify_install(tmp_path) and "已重试" in mg.verify_install(tmp_path)


def test_the_clean_up_does_not_delete_anything_when_a_frozen_process_cannot_be_thawed() -> None:
    script = _install_script()
    code = _function_body(script, "Remove-GateInstallation")

    resume = code.index("resume-all")
    guard = code.index("if (-not $thawed)", resume)
    assert resume < guard < code.index("Unregister-ScheduledTask") < code.index("Remove-Item -LiteralPath $Folder")
    assert "throw" in code[guard : guard + 500] and "没有删除任何东西" in code[guard : guard + 500]
    assert "-ForceDelete" in code[guard : guard + 500]  # the user decides, never the script


def test_an_installed_file_held_for_a_moment_is_hashed_after_a_retry_and_a_file_that_stays_unreadable_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for relative in mg.MANIFEST_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    files = {relative: hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() for relative in mg.MANIFEST_FILES}
    (tmp_path / mg.MANIFEST_FILE).write_text(json.dumps({"files": files}), encoding="utf-8")
    real, calls = Path.read_bytes, {"n": 0}

    def busy(path: Path) -> bytes:
        if path.name == "memory_gate.py":
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError(13, "held by the virus scanner")
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", busy)
    monkeypatch.setattr(mg, "READ_RETRY_SECONDS", 0.0)
    assert mg.verify_install(tmp_path) == "" and calls["n"] == 3

    def always(path: Path) -> bytes:
        if path.name == "memory_gate.py":
            raise PermissionError(13, "held")
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", always)
    problem = mg.verify_install(tmp_path)
    assert "memory_gate.py" in problem and "读不出" in problem and "缺失" not in problem  # present but unreadable is not "missing"
