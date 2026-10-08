"""Real-process proofs of interruption and lease-expiry recovery: nothing is faked, nothing is started twice, nothing succeeds by silence (V04).

Every actor is a real child process on the real clock: a controller process runs the foreground execution Saga, the executor is a real grandchild, the test
kills them with the operating system, and the recovery commands are the real ``continuity`` commands. The unit tests already prove each rule with a fake
clock; this file adds real processes and real elapsed lease time. It does not prove process reclamation (V04-R1) or any project-manager-layer recovery
command (none exists): the restart reconciliation is exercised at the service level because that is the only level it exists at. Scenarios r08 and r09 run
several processes against one store at once (writers against writers, and a writer against readers) because that is how several agents will use it.
"""

from __future__ import annotations

import ctypes
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.continuity_resume_service import ContinuityResumeService

import auto_pm
from auto_pm.contracts.continuity import RunState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind, WorktreeMode
from auto_pm.contracts.mission import InternalRoutingPolicy
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_continuity_execution_service import (
    Clock,
    _settlement_ready,
    _start,
)
from tests.core.test_execution_adapter_service import PROJECT_PATH, _ready
from tests.infrastructure.test_continuity_store_sidecars import _make_root

LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""
CONTROLLER = """import os
import sys
from pathlib import Path

from auto_pm.core.execution_adapter_service import ExecutionDispatchResult, ExecutionDispatchService
from auto_pm.core.execution_adapter_service import LeaseCapability as DispatchLeaseCapability
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor

root, operation_id = Path(sys.argv[1]), sys.argv[2]
store = ContinuityStore(root)
intent = store.get_execution_intent(operation_id)
assert intent is not None
dispatch = ExecutionDispatchResult(
    receipt=intent.receipt, intent=intent, lease=DispatchLeaseCapability(intent.receipt.owner_id, os.environ["V04_LEASE_TOKEN"])
)
microtask = ExecutionDispatchService(root).prepare_microtask(operation_id)
helper = (
    "import json,sys,time;"
    "print(json.dumps({'type':'thread.started','thread_id':'thread-v04'}),flush=True);"
    "time.sleep(300)"
)
executor = LocalCodexExecutor(command_prefix=(sys.executable, "-c", helper))
receipt = LocalExecutionOrchestrator(root, executor=executor).execute(
    dispatch=dispatch,
    microtask=microtask,
    lease_token_environment="V04_LEASE_TOKEN",
    lease_seconds=60,
    renew_before_seconds=40,
    renewal_interval_seconds=2.0,
)
print("RECEIPT=" + receipt.model_dump_json(), flush=True)
"""
PROBE = """import ctypes
import os
import sys


def process_state(pid, api=None):
    \"\"\"'alive', 'exited' or 'unknown': an API failure is never reported as an exit; the caller decides how to fail closed.\"\"\"
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "exited"
        except PermissionError:
            return "alive"
        except OSError:
            return "unknown"
        return "alive"
    kernel32 = api if api is not None else ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return "exited" if ctypes.get_last_error() == 87 else "unknown"  # ERROR_INVALID_PARAMETER: no such process
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "unknown"
        return "alive" if code.value == 259 else "exited"  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
"""
RECONCILER = """import json
from datetime import datetime
from pathlib import Path

from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.execution_supervisor_service import ExecutionSupervisorError, ExecutionSupervisorService


""" + PROBE + """

def alive(pid):
    return process_state(pid) == "alive"


root, operation_id, pid, session, started_at = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4], datetime.fromisoformat(sys.argv[5])
try:
    evidence = ExecutionSupervisorService(root).recover_started_session(
        operation_id, observed_process_id=pid, observed_session_id=session, observed_started_at=started_at, is_process_alive=alive
    )
    print("RECOVERED=" + json.dumps({"process_id": evidence.process_id, "session_id": evidence.session_id}), flush=True)
except ExecutionSupervisorError as error:
    detail = ""
    try:
        _, _, durable = ContinuityExecutionService(root).resolve_started_run(operation_id)
        detail = f" durable=({durable.process_id}, {durable.session_id}, {durable.started_at.isoformat()}) state={process_state(durable.process_id)}"
    except Exception as inner:
        detail = f" resolve_failed={inner}"
    print("REFUSED=" + str(error) + detail, flush=True)
"""
STRESSOR = """import sys
import time
from pathlib import Path

from auto_pm.infrastructure.continuity_store import ContinuityStore

store = ContinuityStore(Path(sys.argv[1]))
mode, hold, pause = sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
for _ in range(int(sys.argv[2])):
    if mode == "write":
        with store._transaction():
            time.sleep(hold)
    else:
        with store._read_connection() as conn:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    time.sleep(pause)
print("STRESS_OK", flush=True)
"""
LEASE_TOKEN = "must-never-persist"
PROJECT_ID = "SW-TEST-001"
SETTLEMENT_REASON = "The legacy lease expired on the real clock; close it forward and keep the evidence."


def _environment(**extra: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    environment.update(extra)
    return environment


_PROBE: dict[str, Any] = {}
exec(PROBE, _PROBE)  # the very source the reconciler child process runs
_process_state = _PROBE["process_state"]


def _alive(pid: int) -> bool:
    """True only while the process provably runs; never sends a signal (on Windows ``os.kill(pid, 0)`` would terminate it)."""

    return bool(_process_state(pid) == "alive")


def _exited(pid: int) -> bool:
    """True only when the operating system says the process is gone; an API failure (state unknown) is not an exit."""

    return bool(_process_state(pid) == "exited")


def _short_lease_dispatch(root: Path, operation_id: str) -> None:
    """The same prepared dispatch as the unit fixtures, with the shortest lease the policy allows."""

    routing = InternalRoutingPolicy(
        allow_execution_branch_changes=True,
        allowed_execution_adapters=frozenset({ExecutionAdapterKind.CODEX, ExecutionAdapterKind.TRAE}),
        approved_model="agent-a",
        required_worktree_mode=WorktreeMode.ISOLATED,
        declared_dirty_paths=(PROJECT_PATH,),
    )
    missions, _, dispatch = _ready(root, routing=routing, scope_paths=(PROJECT_PATH,))
    dispatch.prepare(
        mission=missions.get("MISSION-A5-001"),
        work_id="WORK-A5-001",
        run_id=f"RUN-{operation_id}",
        adapter=ExecutionAdapterKind.CODEX,
        executor_id="agent-a",
        lease_token=LEASE_TOKEN,
        lease_seconds=60,
        idempotency_key=f"dispatch-{operation_id}",
        operation_id=operation_id,
        stack="python",
    )


def _query(root: Path, statement: str, *parameters: Any) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return [tuple(row) for row in conn.execute(statement, parameters).fetchall()]


def _events(root: Path, event_type: str, aggregate_id: str = "") -> list[dict[str, Any]]:
    statement = "SELECT payload_json FROM events WHERE event_type=?" + (" AND aggregate_id=?" if aggregate_id else "") + " ORDER BY rowid"
    parameters = (event_type, aggregate_id) if aggregate_id else (event_type,)
    return [json.loads(row[0]) for row in _query(root, statement, *parameters)]


@dataclass
class Controller:
    """One real controller process that runs the foreground execution Saga and owns its executor child."""

    root: Path
    operation_id: str
    process: subprocess.Popen[str]

    @property
    def run_id(self) -> str:
        return f"RUN-{self.operation_id}"

    def started(self, timeout: float = 90.0) -> dict[str, Any]:
        """The durable start evidence the controller wrote once the executor completed its handshake."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"controller exited early: {self.process.communicate()}")
            events = _events(self.root, "RUN_STARTED", self.run_id)
            if events:
                evidence: dict[str, Any] = events[0]["evidence"]
                return evidence
            time.sleep(0.5)
        self.process.kill()
        raise AssertionError(f"no RUN_STARTED evidence in time: {self.process.communicate()}")

    def outcome(self, timeout: float = 120.0) -> tuple[int, dict[str, Any] | None]:
        """Exit code and the receipt the controller printed, if it got that far."""

        stdout, _ = self.process.communicate(timeout=timeout)
        lines = [line for line in stdout.splitlines() if line.startswith("RECEIPT=")]
        return self.process.returncode, (json.loads(lines[0][len("RECEIPT="):]) if lines else None)


@dataclass
class Scene:
    root: Path
    controller_script: Path
    reconciler_script: Path
    stressor_script: Path
    launcher: Path
    spawned: list[subprocess.Popen[str]]
    pids: list[int]

    def controller(self, operation_id: str) -> Controller:
        process = subprocess.Popen(
            [sys.executable, str(self.controller_script), str(self.root), operation_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            env=_environment(V04_LEASE_TOKEN=LEASE_TOKEN),
        )
        self.spawned.append(process)
        return Controller(self.root, operation_id, process)

    def reconcile(self, operation_id: str, pid: int, session: str, started_at: str) -> str:
        """A fresh process asks the supervisor to recognise the earlier session; returns RECOVERED=… or REFUSED=…."""

        result = subprocess.run(
            [sys.executable, str(self.reconciler_script), str(self.root), operation_id, str(pid), session, started_at],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_environment(), timeout=120, check=False,
        )
        lines = [line for line in result.stdout.splitlines() if line.startswith(("RECOVERED=", "REFUSED="))]
        assert result.returncode == 0 and len(lines) == 1, result.stdout + result.stderr
        return lines[0]

    def command(self, *arguments: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.launcher), "-w", str(self.root), "continuity", *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=_environment(**extra), timeout=120, check=False,
        )

    def kill(self, pid: int) -> None:
        assert pid in self.pids, f"refusing to signal process {pid}: the test did not start it"
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 15
        while not _exited(pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert _exited(pid), f"process {pid} did not exit (state {_process_state(pid)})"

    def assert_no_second_start(self, operation_id: str, started: dict[str, Any]) -> None:
        """A restarted controller may fail or answer PENDING, but it never claims a second start or launches a second executor."""

        restarted = self.controller(operation_id)
        code, receipt = restarted.outcome()
        assert (code != 0 and receipt is None) or (receipt is not None and receipt["status"] == "PENDING")
        assert len(_events(self.root, "EXECUTION_START_CLAIMED")) == 1
        assert [event["evidence"] for event in _events(self.root, "RUN_STARTED", f"RUN-{operation_id}")] == [started]


def _build_scene(base: Path) -> Scene:
    root = base / "ws"
    root.mkdir()
    tools = base / "tools"
    tools.mkdir()
    (tools / "controller.py").write_text(CONTROLLER, encoding="utf-8")
    (tools / "reconciler.py").write_text(RECONCILER, encoding="utf-8")
    (tools / "stressor.py").write_text(STRESSOR, encoding="utf-8")
    (tools / "main.py").write_text(LAUNCHER, encoding="utf-8")
    return Scene(root, tools / "controller.py", tools / "reconciler.py", tools / "stressor.py", tools / "main.py", [], [])


@pytest.fixture
def scene(tmp_path: Path) -> Iterator[Scene]:
    current = _build_scene(tmp_path)
    try:
        yield current
    finally:
        for process in current.spawned:
            if process.poll() is None:
                process.kill()
            process.communicate()
        for pid in current.pids:
            if _alive(pid):
                os.kill(pid, signal.SIGTERM)


def test_r01_a_killed_executor_is_recorded_as_a_failure_never_as_success(scene: Scene) -> None:
    _short_lease_dispatch(scene.root, "OP-V04-R01")
    controller = scene.controller("OP-V04-R01")
    started = controller.started()
    pid = int(started["process_id"])
    scene.pids.append(pid)
    assert _alive(pid)
    scene.kill(pid)

    code, receipt = controller.outcome()
    assert code == 0 and receipt is not None and receipt["status"] == "FAILED" and receipt["process_id"] == pid
    store = ContinuityStore(scene.root)
    assert store.get_run(controller.run_id).state is RunState.FAILED
    assert store.get_lease(controller.run_id).lease_token.startswith("RELEASED:")
    transitions = _events(scene.root, "RUN_TRANSITIONED", controller.run_id)
    assert [event["new_state"] for event in transitions] == ["FAILED"]
    assert transitions[0]["failure"]["code"] == "NONZERO_EXIT" and transitions[0]["lease_release"]["reason"] == "terminal:FAILED"
    assert len(_events(scene.root, "EXECUTION_START_CLAIMED")) == 1 and len(_events(scene.root, "RUN_STARTED", controller.run_id)) == 1
    assert not _query(scene.root, "SELECT 1 FROM events WHERE payload_json LIKE ?", f"%{LEASE_TOKEN}%")


def test_r02_a_controller_that_dies_is_not_replaced_by_a_guess_and_the_session_is_recognised_only_by_its_full_identity(scene: Scene) -> None:
    _short_lease_dispatch(scene.root, "OP-V04-R02")
    controller = scene.controller("OP-V04-R02")
    started = controller.started()
    pid, session, started_at = int(started["process_id"]), str(started["session_id"]), str(started["started_at"])
    scene.pids.append(pid)
    store = ContinuityStore(scene.root)

    controller.process.kill()
    controller.process.communicate()
    assert _alive(pid), "the orphaned executor must still be running: this scenario kills the controller, not the executor"
    lease_before = store.get_lease(controller.run_id)
    time.sleep(6)
    assert store.get_lease(controller.run_id) == lease_before, "with the controller dead nothing renews the lease"
    assert store.get_run(controller.run_id).state is RunState.RUNNING

    assert scene.reconcile("OP-V04-R02", pid, session, started_at).startswith("RECOVERED=")
    for wrong in ((pid + 1, session, started_at), (pid, "thread-other", started_at), (pid, session, "2026-01-01T00:00:00+00:00")):
        assert scene.reconcile("OP-V04-R02", *wrong).startswith("REFUSED="), wrong
    scene.assert_no_second_start("OP-V04-R02", started)

    scene.kill(pid)
    assert scene.reconcile("OP-V04-R02", pid, session, started_at).startswith("REFUSED="), "a dead process is never recognised"
    assert store.get_run(controller.run_id).state is RunState.RUNNING
    assert len(_events(scene.root, "EXECUTION_START_CLAIMED")) == 1


def test_r03_an_expired_lease_never_turns_into_success(scene: Scene) -> None:
    _short_lease_dispatch(scene.root, "OP-V04-R03")
    controller = scene.controller("OP-V04-R03")
    started = controller.started()
    pid = int(started["process_id"])
    scene.pids.append(pid)
    controller.process.kill()
    controller.process.communicate()
    scene.kill(pid)
    store = ContinuityStore(scene.root)
    lease = store.get_lease(controller.run_id)
    expires_at = datetime.fromisoformat(lease.expires_at)
    while datetime.now(UTC) <= expires_at:
        time.sleep(1)
    time.sleep(1)

    assert store.get_run(controller.run_id).state is RunState.RUNNING, "an abandoned Run is neither succeeded nor failed by silence"
    assert not _events(scene.root, "RUN_TRANSITIONED", controller.run_id)
    resumed = ContinuityResumeService(scene.root).collect(project_id=PROJECT_ID, invocation_path=scene.root)
    assert "LEASE_EXPIRED" in resumed.conflicts and resumed.next_legal_action == ""
    events_before = _query(scene.root, "SELECT rowid, event_type, aggregate_id FROM events ORDER BY rowid")
    renewal = scene.command(
        "lease", "renew", "--run-id", controller.run_id, "--owner", lease.owner_id, "--lease-token-env", "V04_LEASE_TOKEN",
        "--expected-version", str(lease.version), "--idempotency-key", "late-renew", V04_LEASE_TOKEN=LEASE_TOKEN,
    )
    assert renewal.returncode != 0
    assert "lease 已过期" in renewal.stdout + renewal.stderr, "the expiry defence itself must refuse, not an ownership mismatch"
    assert store.get_lease(controller.run_id) == lease
    assert _query(scene.root, "SELECT rowid, event_type, aggregate_id FROM events ORDER BY rowid") == events_before
    scene.assert_no_second_start("OP-V04-R03", started)
    assert store.get_run(controller.run_id).state is RunState.RUNNING


@pytest.fixture(scope="module")
def settled(tmp_path_factory: pytest.TempPathFactory) -> tuple[Scene, dict[str, Any]]:
    current = _build_scene(tmp_path_factory.mktemp("settled"))
    clock = Clock()
    clock.value = datetime.now(UTC)
    service = _settlement_ready(current.root, clock, advance_before_recovery=False)
    expires_at = datetime.fromisoformat(service._store.get_lease("RUN-TARGET").expires_at)
    while datetime.now(UTC) <= expires_at:
        time.sleep(1)
    time.sleep(1)
    result = current.command(*_settle_arguments(), "--idempotency-key", "settle-v04")
    assert result.returncode == 0, result.stderr + result.stdout
    output: dict[str, Any] = json.loads(result.stdout)
    return current, output


def _settle_arguments() -> tuple[str, ...]:
    return (
        "run", "settle-expired", "--target-run-id", "RUN-TARGET", "--recovery-run-id", "RUN-RECOVERY", "--recovery-owner", "recovery-agent",
        "--recovery-lease-token", "recovery-secret", "--decision-id", "DEC-20260911-5C37A985", "--outcome", "CANCELLED", "--reason", SETTLEMENT_REASON,
    )


def test_r04_a_real_expired_run_is_settled_forward_and_fenced(settled: tuple[Scene, dict[str, Any]]) -> None:
    scene, output = settled
    assert output["state"] == "CANCELLED"
    store = ContinuityStore(scene.root)
    assert store.get_run("RUN-TARGET").state is RunState.CANCELLED
    lease = store.get_lease("RUN-TARGET")
    assert lease.lease_token.startswith("RELEASED:") and lease.version >= 2
    events = _query(scene.root, "SELECT payload_json FROM events WHERE event_type='RUN_EXPIRED_SETTLED'")
    assert len(events) == 1 and "target-secret" not in events[0][0] and "recovery-secret" not in events[0][0]
    assert json.loads(events[0][0])["lease_release"]["lease_epoch"] == lease.version
    checkpoint = store.latest_checkpoint("RUN-TARGET")
    assert checkpoint is not None and checkpoint.checkpoint_id == "CP-TARGET"


def test_r05_the_same_settlement_replays_and_every_other_attempt_is_refused(settled: tuple[Scene, dict[str, Any]]) -> None:
    scene, output = settled
    replay = scene.command(*_settle_arguments(), "--idempotency-key", "settle-v04")
    assert replay.returncode == 0 and json.loads(replay.stdout)["state"] == output["state"]
    again = scene.command(*_settle_arguments(), "--idempotency-key", "settle-v04-second-key")
    assert again.returncode != 0
    assert len(_events(scene.root, "RUN_EXPIRED_SETTLED")) == 1
    late = scene.command(
        "checkpoint", "create", "--checkpoint-id", "CP-LATE", "--run-id", "RUN-TARGET", "--owner", "legacy-agent", "--lease-token", "target-secret",
        "--summary", "a write after the settlement", "--evidence", "pytest:0", "--idempotency-key", "late-write",
    )
    assert late.returncode != 0
    assert not _query(scene.root, "SELECT 1 FROM checkpoints WHERE checkpoint_id='CP-LATE'")


def test_r06_the_same_work_continues_in_a_new_run_and_the_history_is_kept(settled: tuple[Scene, dict[str, Any]]) -> None:
    scene, _ = settled
    service = ContinuityExecutionService(scene.root)
    _start(
        service, run_id="RUN-SUCCESSOR", work_id="WORK-TARGET", executor_id="successor-agent", lease_token="successor-secret",
        lease_seconds=900, idempotency_key="start-successor",
    )
    service.transition_run("RUN-SUCCESSOR", RunState.RUNNING, "successor-agent", "successor-secret", "successor-running")
    store = ContinuityStore(scene.root)
    service.checkpoint(
        checkpoint_id="CP-SUCCESSOR", run_id="RUN-SUCCESSOR", owner_id="successor-agent", lease_token="successor-secret", summary="the successor continues the work",
        git_head=store.get_run("RUN-SUCCESSOR").git_head, dirty_paths=["auto_pm/core/a.py"], evidence=["pytest:0"], idempotency_key="cp-successor",
    )
    runs = {run.run_id: run.state for run in store.list_runs("WORK-TARGET", include_terminal=True)}
    assert runs == {"RUN-TARGET": RunState.CANCELLED, "RUN-SUCCESSOR": RunState.RUNNING}
    target_checkpoint, successor_checkpoint = store.latest_checkpoint("RUN-TARGET"), store.latest_checkpoint("RUN-SUCCESSOR")
    assert target_checkpoint is not None and target_checkpoint.checkpoint_id == "CP-TARGET"
    assert successor_checkpoint is not None and successor_checkpoint.checkpoint_id == "CP-SUCCESSOR"


def test_r07_a_settlement_before_the_lease_expires_is_refused_and_changes_nothing(scene: Scene) -> None:
    clock = Clock()
    clock.value = datetime.now(UTC)
    service = _settlement_ready(scene.root, clock, advance_before_recovery=False)
    store = service._store
    run_before, lease_before = store.get_run("RUN-TARGET"), store.get_lease("RUN-TARGET")
    assert datetime.fromisoformat(lease_before.expires_at) > datetime.now(UTC), "the target lease must still be live for this scenario"

    early = scene.command(*_settle_arguments(), "--idempotency-key", "settle-too-early")

    assert early.returncode != 0
    assert store.get_run("RUN-TARGET") == run_before and store.get_lease("RUN-TARGET") == lease_before
    assert not _events(scene.root, "RUN_EXPIRED_SETTLED")


def test_r08_many_processes_opening_the_store_at_once_never_see_a_spurious_validation_error(scene: Scene) -> None:
    _make_root(scene.root)
    children = [
        subprocess.Popen(
            [sys.executable, str(scene.stressor_script), str(scene.root), "60", "write", "0", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=_environment(),
        )
        for _ in range(6)
    ]
    scene.spawned.extend(children)
    outputs = [child.communicate(timeout=300) for child in children]
    assert [child.returncode for child in children] == [0] * 6, [error for _, error in outputs]
    assert all("STRESS_OK" in output for output, _ in outputs)


def test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open(scene: Scene) -> None:
    _make_root(scene.root)
    jobs = [("30", "write", "0.01", "0.15"), ("100", "read", "0", "0.02"), ("100", "read", "0", "0.02")]
    children = [
        subprocess.Popen(
            [sys.executable, str(scene.stressor_script), str(scene.root), count, mode, hold, pause],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=_environment(),
        )
        for count, mode, hold, pause in jobs
    ]
    scene.spawned.extend(children)
    outputs = [child.communicate(timeout=300) for child in children]
    assert [child.returncode for child in children] == [0] * len(jobs), [error for _, error in outputs]
    assert all("STRESS_OK" in output for output, _ in outputs)


def test_v04t_the_probe_tells_a_live_process_from_an_exited_one(scene: Scene) -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True
    )
    scene.spawned.append(child)
    assert _process_state(child.pid) == "alive" and _alive(child.pid) and not _exited(child.pid)
    child.kill()
    child.wait(timeout=30)
    assert _process_state(child.pid) == "exited" and _exited(child.pid) and not _alive(child.pid)


def _fake_kernel32(handle: int, exit_call_ok: int, exit_code: int) -> SimpleNamespace:
    """A kernel32 stand-in whose calls answer as the test dictates, to exercise the probe's failure branches."""

    def open_process(access: int, inherit: bool, pid: int) -> int:
        return handle

    def get_exit_code(opened: int, code: Any) -> int:
        code._obj.value = exit_code  # the ctypes.byref argument
        return exit_call_ok

    def close_handle(opened: int) -> int:
        return 1

    return SimpleNamespace(OpenProcess=open_process, GetExitCodeProcess=get_exit_code, CloseHandle=close_handle)


@pytest.mark.skipif(sys.platform != "win32", reason="the failure branches are the Win32 API ones")
@pytest.mark.parametrize(
    ("handle", "last_error", "exit_call_ok", "exit_code", "expected"),
    [
        (0, 87, 1, 0, "exited"),  # no such process
        (0, 5, 1, 0, "unknown"),  # access denied: the process may well be alive
        (7, 0, 0, 0, "unknown"),  # the exit-code call itself failed: its output is not an exit
        (7, 0, 1, 0, "exited"),
        (7, 0, 1, 259, "alive"),
    ],
    ids=["no-such-process", "api-failure-on-open", "api-failure-on-exit-code", "real-exit", "still-active"],
)
def test_v04t_an_api_failure_is_unknown_and_never_an_exit(handle: int, last_error: int, exit_call_ok: int, exit_code: int, expected: str) -> None:
    ctypes.set_last_error(last_error)
    assert _process_state(4242, _fake_kernel32(handle, exit_call_ok, exit_code)) == expected


def test_v04t_the_scene_refuses_to_signal_a_process_it_did_not_start(scene: Scene) -> None:
    try:
        scene.kill(2_000_000_000)  # not recorded by this test: the guard refuses before any signal is sent
    except AssertionError as error:
        message = str(error)
    else:
        message = "no refusal"
    assert "did not start it" in message
