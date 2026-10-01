"""Real-process, real-Git, real-quality-gate proofs for approved run -> verification -> acceptance."""

from __future__ import annotations

import json
import logging
import re
import secrets
import sqlite3
import subprocess
import sys
import textwrap
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.ledger_reconciler import LedgerReconciler
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator

from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import (
    PlanningExecutionGrant,
    PlanningScopeCard,
    PmIntent,
    PmRunOutcome,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor

if TYPE_CHECKING:
    from auto_pm.application.core.pm_closure_service import (
        ClosureCompletionState,
        PmClosureService,
    )
    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
else:
    from auto_pm.core.pm_closure_service import ClosureCompletionState, PmClosureService
    from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

PROJECT_ID = "SW-TEST-001"
CALC = f"{PROJECT_ID}/src/calc.py"
CALC_TEST = f"{PROJECT_ID}/tests/test_calc.py"
LEASE_ENV = "AUTO_PM_EXECUTION_LEASE_TOKEN"

VERIFIED_SENTENCE = "已执行并通过质量验证，等待您的最终验收。"
NOT_VERIFIED_SENTENCE = "质量验证未通过，已保留现场；未进入验收。"
NOT_FINISHED_SENTENCE = "执行未完成，未进行质量验证；已保留现场。"

FIXED_CALC = "def add(a: int, b: int) -> int:\n    return a + b\n"
BROKEN_CALC = "def add(a: int, b: int) -> int:\n    return a * b\n"
GOOD_TESTS = (
    "from calc import add\n\n\n"
    "def test_add() -> None:\n    assert add(2, 3) == 5\n\n\n"
    "def test_add_negative() -> None:\n    assert add(-1, 1) == 0\n"
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _build_workspace(root: Path) -> None:
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "U07A Test")
    _git(root, "config", "user.email", "u07a@example.invalid")
    project = root / PROJECT_ID
    (project / "src").mkdir(parents=True)
    (project / "tests").mkdir()
    changes = project / "04_监控" / "01_变更管理"
    (changes / "01_变更单").mkdir(parents=True)
    (changes / "01_版本变更台帐.md").write_text(
        "# 台帐\n\n| 序号 | 变更编号 | 描述 |\n|---|---|---|\n", encoding="utf-8"
    )
    (project / ".copier-answers.yml").write_text(
        f"project_id: {PROJECT_ID}\nproject_name: U07A E2E\nstack: python\n", encoding="utf-8"
    )
    (project / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 88\n\n[tool.mypy]\nstrict = true\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["src"]\n',
        encoding="utf-8",
    )
    (project / "src" / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8"
    )
    (project / "tests" / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    (root / "specs").mkdir()
    (root / "specs" / "python.md").write_text("python", encoding="utf-8")
    (root / "specs" / "plc.md").write_text("plc", encoding="utf-8")
    registry = root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "specs": {
                    "DEV-TEST": {
                        "domain": "python",
                        "lifecycle": "stable",
                        "canonical_path": "specs/python.md",
                        "version": "V1",
                    },
                    "LSP-TEST": {
                        "domain": "plc",
                        "lifecycle": "active",
                        "canonical_path": "specs/plc.md",
                        "version": "V1",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    workspace = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    workspace.parent.mkdir(parents=True)
    workspace.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": PROJECT_ID,
                        "project_root": PROJECT_ID,
                        "development_root": PROJECT_ID,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        ".auto-pm/\n__pycache__/\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n.coverage\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")


def _helper_source(*, calc: str, tests: str, exit_code: int, counter: Path) -> str:
    """A real child process that speaks the handshake, writes real files and exits."""

    return textwrap.dedent(
        f"""\
        import json, pathlib, sys, time
        repo = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])
        with open({str(counter)!r}, 'a', encoding='utf-8') as handle:
            handle.write('start\\n')
        print(json.dumps({{'type': 'thread.started', 'thread_id': 'thread-u07a'}}), flush=True)
        (repo / {CALC!r}).write_text({calc!r}, encoding='utf-8')
        (repo / {CALC_TEST!r}).write_text({tests!r}, encoding='utf-8')
        time.sleep(0.15)
        sys.exit({exit_code})
        """
    )


@dataclass
class _Env:
    root: Path
    store: ContinuityStore
    facade: PmFacadeService
    changes: ChangeService
    card: PlanningScopeCard
    counter: Path
    token: str

    def starts(self) -> int:
        if not self.counter.exists():
            return 0
        return len(self.counter.read_text(encoding="utf-8").splitlines())

    def run(self) -> PmRunOutcome:
        return self.facade.run_approved_planning(
            self.card,
            expected_plan_hash=self.card.plan_hash,
            lease_token=self.token,
            lease_token_environment=LEASE_ENV,
        )

    def mission_id(self) -> str:
        return self.facade.materialize_planning_mission(self.card).mission_id

    def mission_state(self) -> MissionState:
        return self.store.get_mission(self.mission_id()).state

    def latest_run(self) -> tuple[str, RunState]:
        mission = self.store.get_mission(self.mission_id())
        assert mission.root_work_id
        run = self.store.list_runs(mission.root_work_id, include_terminal=True)[0]
        return run.run_id, run.state

    def event_count(self) -> int:
        return self._count("events")

    def checkpoint_count(self) -> int:
        return self._count("checkpoints")

    def _count(self, table: str) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def token_locations(self) -> set[tuple[str, str]]:
        """Every (table, column) whose stored value contains this env's lease token."""

        found: set[tuple[str, str]] = set()
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            tables = [
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            for table in tables:
                columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
                for row in conn.execute(f'SELECT * FROM "{table}"'):
                    for column, value in zip(columns, row, strict=True):
                        if self.token in str(value):
                            found.add((table, column))
        return found


def _env(
    tmp_path: Path,
    *,
    calc: str = FIXED_CALC,
    tests: str = GOOD_TESTS,
    exit_code: int = 0,
    name: str = "ws",
) -> _Env:
    root = (tmp_path / name).resolve()
    _build_workspace(root)
    counter = tmp_path / f"{name}-starts.txt"
    helper = tmp_path / f"{name}-fake_codex.py"
    helper.write_text(
        _helper_source(calc=calc, tests=tests, exit_code=exit_code, counter=counter),
        encoding="utf-8",
    )
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "u07a-e2e")
    changes = ChangeService(str(root))
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))
    facade = PmFacadeService(
        root,
        store=store,
        change_service=changes,
        local_orchestrator=LocalExecutionOrchestrator(root, store=store, executor=executor),
    )
    scope = (CALC, CALC_TEST)
    grant = PlanningExecutionGrant(
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="agent-a",
        declared_dirty_paths=scope,
    )
    intent = PmIntent(
        request_id="REQ-U07A-E2E",
        subject_project_id=PROJECT_ID,
        objective="Fix add()",
        acceptance_criteria=("add(2, 3) == 5",),
    )
    card = facade.create_planning_scope_card(
        intent,
        scope_paths=scope,
        risks=("none",),
        non_goals=("no refactor",),
        execution_grant=grant,
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(
            card.change_id, state, approver="fubai", comment="human", project_id=PROJECT_ID
        )
    facade.approve_planning_scope_card(
        card,
        expected_plan_hash=card.plan_hash,
        approver="fubai",
        approval_evidence_ref="user-confirmation:U07A-E2E",
    )
    return _Env(root, store, facade, changes, card, counter, secrets.token_urlsafe(32))


def test_success_chain_runs_verifies_and_opens_the_acceptance_gate_from_any_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _env(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.chdir(outside)

    outcome = env.facade.run_approved_planning(
        env.card,
        expected_plan_hash=env.card.plan_hash,
        lease_token=env.token,
        lease_token_environment=LEASE_ENV,
    )

    assert outcome.verified is True
    assert outcome.message == VERIFIED_SENTENCE
    assert outcome.receipt_status == "VERIFYING"
    assert outcome.mission_state is MissionState.ACCEPTANCE_PENDING
    mission = env.store.get_mission(outcome.mission_id)
    assert mission.state is MissionState.ACCEPTANCE_PENDING
    assert mission.root_work_id
    assert env.store.get_work(mission.root_work_id).state is WorkState.IN_PROGRESS
    run_id, run_state = env.latest_run()
    assert run_state is RunState.VERIFYING
    assert outcome.run_id == run_id
    assert outcome.checkpoint_id == f"CP-{run_id}-VERIFY"
    checkpoint = env.store.get_checkpoint(outcome.checkpoint_id)
    assert json.loads(checkpoint.evidence[0])["schema_version"] == "checkpoint-evidence.v2"
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""
    accepted = env.facade.accept(outcome.mission_id)
    assert accepted.mission_state is MissionState.ACCEPTED
    worktree = Path(env.store.get_run(run_id).worktree_path)
    assert (worktree / CALC).read_text(encoding="utf-8") == FIXED_CALC
    # Only the approved change record may appear in the source tree; no source file is touched.
    assert _git(env.root, "status", "--porcelain", "--", f"{PROJECT_ID}/src", f"{PROJECT_ID}/tests") == ""
    assert _git(env.root, "diff", "--name-only") == ""
    assert (env.root / CALC).read_text(encoding="utf-8").endswith("return a - b\n")


def test_replay_returns_the_same_outcome_without_a_second_process_or_new_evidence(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    first = env.run()
    events, checkpoints, starts = env.event_count(), env.checkpoint_count(), env.starts()

    second = env.run()

    assert second == first
    assert (env.event_count(), env.checkpoint_count(), env.starts()) == (events, checkpoints, starts)
    assert starts == 1


def test_failing_quality_gate_keeps_the_scene_and_never_opens_the_gate(tmp_path: Path) -> None:
    env = _env(tmp_path, calc=BROKEN_CALC)

    outcome = env.run()

    assert outcome.verified is False
    assert outcome.checkpoint_id == ""
    assert outcome.message == NOT_VERIFIED_SENTENCE
    assert outcome.receipt_status == "VERIFYING"
    assert env.checkpoint_count() == 0
    assert env.mission_state() is MissionState.ACTIVE
    assert env.latest_run()[1] is RunState.VERIFYING
    assert env.facade.acceptance_gate_reason(outcome.mission_id) != ""


def test_failed_execution_is_reported_without_verification(tmp_path: Path) -> None:
    env = _env(tmp_path, exit_code=3)

    outcome = env.run()

    assert outcome.receipt_status == "FAILED"
    assert outcome.verified is False
    assert outcome.checkpoint_id == ""
    assert outcome.message == NOT_FINISHED_SENTENCE
    assert env.checkpoint_count() == 0
    assert env.mission_state() is MissionState.ACTIVE


def test_wrong_lease_token_never_verifies_and_the_right_one_does(tmp_path: Path) -> None:
    env = _env(tmp_path)
    mission_id = env.mission_id()
    work = env.facade.create_planning_work(env.card)
    env.facade.plan(mission_id)
    env.facade.approve(mission_id, work.work_id)
    env.facade.execute(mission_id)
    receipt = env.facade.execute_planning_foreground(
        env.card,
        expected_plan_hash=env.card.plan_hash,
        lease_token=env.token,
        lease_token_environment=LEASE_ENV,
    )
    assert receipt.status == "VERIFYING"
    events = env.event_count()

    wrong = env.facade.verify_for_acceptance(mission_id, lease_token=secrets.token_urlsafe(32))

    assert wrong.verified is False
    assert wrong.checkpoint_id == ""
    assert wrong.mission_state is MissionState.ACTIVE
    assert env.checkpoint_count() == 0
    assert env.event_count() == events
    right = env.facade.verify_for_acceptance(mission_id, lease_token=env.token)
    assert right.verified is True
    assert right.mission_state is MissionState.ACCEPTANCE_PENDING


def test_illegal_states_are_refused_without_writing_anything(tmp_path: Path) -> None:
    env = _env(tmp_path, exit_code=3)
    mission_id = env.mission_id()
    env.facade.create_planning_work(env.card)
    events = env.event_count()
    with pytest.raises(PmFacadeError, match="不在可验证状态"):
        env.facade.verify_for_acceptance(mission_id, lease_token=env.token)
    assert env.event_count() == events

    failed = env.run()
    assert failed.receipt_status == "FAILED"
    events = env.event_count()
    with pytest.raises(PmFacadeError, match="未处于 VERIFYING"):
        env.facade.verify_for_acceptance(mission_id, lease_token=env.token)
    assert env.event_count() == events


def test_an_accepted_mission_cannot_be_run_again(tmp_path: Path) -> None:
    env = _env(tmp_path)
    outcome = env.run()
    env.facade.accept(outcome.mission_id)
    events, starts = env.event_count(), env.starts()

    with pytest.raises(PmFacadeError, match="已验收、已结束或被阻塞"):
        env.run()
    with pytest.raises(PmFacadeError, match="不在可验证状态"):
        env.facade.verify_for_acceptance(outcome.mission_id, lease_token=env.token)

    assert (env.event_count(), env.starts()) == (events, starts)


def test_lease_token_and_paths_never_leak(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        failing = _env(tmp_path, calc=BROKEN_CALC, name="failing")
        failed = failing.run()
        passing = _env(tmp_path, name="passing")
        passed = passing.run()

    for env, outcome in ((failing, failed), (passing, passed)):
        # The lease capability itself lives only in the store's own lease column.
        assert env.token_locations() == {("execution_leases", "lease_token")}
        assert env.token not in outcome.model_dump_json()
        assert env.token not in caplog.text
        assert str(env.root) not in outcome.message
        assert outcome.mission_id not in outcome.message
        assert outcome.run_id not in outcome.message
    assert not (passing.root / ".coverage").exists()


_CLOSURE_PLACEHOLDERS = ("（待填写）", "(待填写)", "待补充", "[在此填写", "[___________]")


def _accepted_outcome(env: _Env) -> PmRunOutcome:
    outcome = env.run()
    assert outcome.verified is True
    env.facade.accept(outcome.mission_id)
    return outcome


def _change_file(env: _Env) -> Path:
    return next(env.root.glob(f"**/{env.card.change_id}.md"))


def _change_status(path: Path) -> str:
    match = re.search(r"^\|\s*变更状态\s*\|\s*([^|\n]*?)\s*\|", path.read_text(encoding="utf-8"), re.M)
    assert match is not None
    return match.group(1)


def test_real_chain_closes_to_completed_with_a_filled_change_and_a_clean_ledger(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    outcome = _accepted_outcome(env)
    change = _change_file(env)
    status_before = _change_status(change)
    service = PmClosureService(env.root, store=env.store)

    preparation = service.prepare_closure(outcome.mission_id, idempotency_key="u07b-prepare")
    receipt = service.complete_closure(
        preparation.closure.closure_id, idempotency_key="u07b-complete"
    )

    assert receipt.state is ClosureCompletionState.COMPLETED
    assert receipt.run_state is RunState.SUCCEEDED
    assert receipt.work_state is WorkState.CLOSED
    assert receipt.mission_state is MissionState.CLOSED
    assert env.mission_state() is MissionState.CLOSED
    content = change.read_text(encoding="utf-8")
    assert not [item for item in _CLOSURE_PLACEHOLDERS if item in content]
    conclusion = next(line for line in content.splitlines() if line.startswith("| **验证结论**"))
    assert preparation.closure.closure_id in conclusion
    assert outcome.checkpoint_id in content
    assert CALC in content and CALC_TEST in content
    assert "需求：Fix add()" in content
    assert "验收条件：add(2, 3) == 5" in content
    assert _change_status(change) == status_before
    assert LedgerReconciler().reconcile(str(env.root)).is_clean


def test_closure_replay_is_idempotent_and_leaves_the_change_untouched(tmp_path: Path) -> None:
    env = _env(tmp_path)
    outcome = _accepted_outcome(env)
    change = _change_file(env)
    service = PmClosureService(env.root, store=env.store)
    preparation = service.prepare_closure(outcome.mission_id, idempotency_key="u07b-prepare")
    first = service.complete_closure(
        preparation.closure.closure_id, idempotency_key="u07b-complete"
    )
    content, events = change.read_bytes(), env.event_count()

    second = service.complete_closure(
        preparation.closure.closure_id, idempotency_key="u07b-complete"
    )

    assert second == first
    assert change.read_bytes() == content
    assert env.event_count() == events


def test_a_change_missing_its_conclusion_section_stays_pending_and_recovers_on_retry(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    outcome = _accepted_outcome(env)
    change = _change_file(env)
    original = change.read_text(encoding="utf-8")
    assert "### 10.3 验证结论" in original
    change.write_text(original.replace("### 10.3 验证结论", "### 10.3 结论"), encoding="utf-8")
    broken = change.read_bytes()
    service = PmClosureService(env.root, store=env.store)
    preparation = service.prepare_closure(outcome.mission_id, idempotency_key="u07b-prepare")
    run_before = env.latest_run()

    pending = service.complete_closure(
        preparation.closure.closure_id, idempotency_key="u07b-complete"
    )

    assert pending.state is ClosureCompletionState.PENDING_SYNC
    assert env.mission_state() is MissionState.ACCEPTED
    assert env.latest_run() == run_before
    assert change.read_bytes() == broken

    change.write_text(original, encoding="utf-8")
    done = service.complete_closure(
        preparation.closure.closure_id, idempotency_key="u07b-complete"
    )

    assert done.state is ClosureCompletionState.COMPLETED
    assert env.mission_state() is MissionState.CLOSED
