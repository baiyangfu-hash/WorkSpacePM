"""U09C: one user click approves a pending scope card and starts it, off the UI thread.

Real store, real Git repository, real child process standing in for the executor, real quality gates. Scenario ids
b01..b12 follow card 040 section 5.4.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.ledger_reconciler import LedgerReconciler
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.core.pm_facade_service import PmFacadeService
from PySide6.QtCore import QRunnable, QThreadPool

from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_cockpit import CockpitUserAction
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_pm_run_e2e import (
    BROKEN_CALC,
    CALC,
    CALC_TEST,
    FIXED_CALC,
    GOOD_TESTS,
    PROJECT_ID,
    _build_workspace,
    _helper_source,
)
from tests.plan_checklist_support import full_checklist
from tests.qml.test_pm_cockpit_bridge import _HoldingThreadPool

_VERIFIED = "已执行并通过质量验证，等待您的最终验收。"
_REQUEST = "REQ-COCKPIT-0123456789ABCDEF0123456789ABCDEF"
_SECOND = "REQ-COCKPIT-FEDCBA9876543210FEDCBA9876543210"


@dataclass
class _Cockpit:
    root: Path
    store: ContinuityStore
    facade: PmFacadeService
    changes: ChangeService
    service: PmCockpitService
    counter: Path
    hashes: dict[str, str]

    def starts(self) -> int:
        return len(self.counter.read_text(encoding="utf-8").splitlines()) if self.counter.exists() else 0

    def count(self, table: str) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def writes(self) -> tuple[int, ...]:
        return tuple(
            self.count(table)
            for table in ("events", "planning_draft_decision_bindings", "mission_items", "work_items", "run_items")
        )

    def mission_id(self) -> str:
        return str(self.service.snapshot().projects[0].mission_id)

    def action(self) -> CockpitUserAction:
        return CockpitUserAction(self.service.snapshot().projects[0].user_action)

    def pending(self) -> list[tuple[str, bool]]:
        return [(c.request_id, c.can_approve) for c in self.service.snapshot().pending_cards]

    def add_request(self, request_id: str, *, risks: tuple[str, ...]) -> str:
        """Another draft with a persisted card; returns its plan hash."""

        self.facade.create_planning_draft(
            PmIntent(
                request_id=request_id,
                subject_project_id=PROJECT_ID,
                objective="Another goal",
                acceptance_criteria=("add(2, 3) == 5",),
            )
        )
        submitted = self.facade.submit_planning_scope_card(
            request_id,
            scope_paths=(CALC, CALC_TEST),
            risks=risks,
            non_goals=("no refactor",),
            execution_grant=PlanningExecutionGrant(
                adapter=ExecutionAdapterKind.CODEX, approved_model="agent-a", declared_dirty_paths=(CALC, CALC_TEST),
                plan_checklist=full_checklist(),
            ),
            submitted_by="PM (Claude)",
        )
        plan_hash = str(submitted.card.plan_hash)
        self.hashes[request_id] = plan_hash
        return plan_hash


def _cockpit(base: Path, *, approver: str = "fubai", calc: str = FIXED_CALC, exit_code: int = 0) -> _Cockpit:
    """A cockpit-shaped draft with a persisted, not yet approved scope card."""

    root = (base / "ws").resolve()
    _build_workspace(root)
    counter = base / "starts.txt"
    helper = base / "fake_codex.py"
    helper.write_text(
        _helper_source(calc=calc, tests=GOOD_TESTS, exit_code=exit_code, counter=counter), encoding="utf-8"
    )
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "u09c-e2e")
    changes = ChangeService(str(root))
    facade = PmFacadeService(
        root,
        store=store,
        change_service=changes,
        local_orchestrator=LocalExecutionOrchestrator(
            root, store=store, executor=LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))
        ),
    )
    service = PmCockpitService(root, store=store, facade=facade, approver=approver)
    cockpit = _Cockpit(root, store, facade, changes, service, counter, {})
    cockpit.add_request(_REQUEST, risks=("改错文件导致回归",))
    return cockpit


def _bridge(cockpit: _Cockpit) -> tuple[PmCockpitBridge, _HoldingThreadPool, list[tuple[str, bool, str]]]:
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(str(cockpit.root), service=cockpit.service, thread_pool=cast(QThreadPool, pool))
    finished: list[tuple[str, bool, str]] = []
    bridge.scopeApprovalFinished.connect(lambda rid, ok, msg: finished.append((rid, ok, msg)))
    return bridge, pool, finished


def _click(
    cockpit: _Cockpit, request_id: str = _REQUEST
) -> tuple[PmCockpitBridge, _HoldingThreadPool, list[tuple[str, bool, str]]]:
    """Queue the click, run the worker, deliver the result."""

    bridge, pool, finished = _bridge(cockpit)
    assert bridge.approveScopeAndStart(request_id, cockpit.hashes[request_id])["accepted"] is True
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_approve_workers()
    return bridge, pool, finished


# --------------------------------------------------------------------------- b: the single click


def test_b01_one_click_approves_starts_verifies_and_the_second_decision_closes_it(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path)
    assert cockpit.pending() == [(_REQUEST, True)]
    assert cockpit.mission_id() == ""

    bridge, pool, finished = _click(cockpit)

    assert finished == [(_REQUEST, True, _VERIFIED)]
    mission_id = cockpit.mission_id()
    assert cockpit.store.get_mission(mission_id).state is MissionState.ACCEPTANCE_PENDING
    assert cockpit.pending() == []
    assert cockpit.action() is CockpitUserAction.CONFIRM_ACCEPTANCE
    assert cockpit.starts() == 1
    assert cockpit.count("planning_draft_decision_bindings") == 1

    closed: list[tuple[str, bool, str]] = []
    bridge.closureFinished.connect(lambda m, ok, msg: closed.append((m, ok, msg)))
    accepted = bridge.confirmAcceptance(mission_id)
    assert accepted["success"] is True and accepted["closing"] is True
    cast(QRunnable, pool.worker).run()
    bridge._poll_close_workers()

    assert [(m, ok) for m, ok, _ in closed] == [(mission_id, True)]
    mission = cockpit.store.get_mission(mission_id)
    assert mission.state is MissionState.CLOSED and mission.root_work_id
    assert cockpit.store.get_work(mission.root_work_id).state is WorkState.CLOSED
    assert cockpit.store.list_runs(mission.root_work_id, include_terminal=True)[0].state is RunState.SUCCEEDED
    assert LedgerReconciler().reconcile(str(cockpit.root)).is_clean
    assert cockpit.count("planning_draft_decision_bindings") == 1


def test_b02_the_click_is_one_at_a_time_and_blocks_a_competing_start(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path)
    second_hash = cockpit.add_request(_SECOND, risks=("second",))
    bridge, pool, finished = _bridge(cockpit)

    first = bridge.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])
    replay = bridge.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])
    other = bridge.approveScopeAndStart(_SECOND, second_hash)
    competing_start = bridge.startExecution("MISSION-ANY-001")

    assert first["accepted"] is True
    for refused in (replay, other, competing_start):
        assert refused["accepted"] is False and refused["busy"] is True
    assert cockpit.writes()[1:] == (0, 0, 0, 0)
    assert cockpit.starts() == 0
    cast(QRunnable, pool.worker).run()
    bridge._poll_approve_workers()
    assert [(rid, ok) for rid, ok, _ in finished] == [(_REQUEST, True)]
    assert cockpit.starts() == 1


@pytest.mark.parametrize(("request_id", "plan_hash"), [("", "a" * 64), ("  ", "a" * 64), (_REQUEST, ""), (_REQUEST, "   ")])
def test_b03_blank_identifiers_are_rejected_without_queueing_anything(
    tmp_path: Path, request_id: str, plan_hash: str
) -> None:
    cockpit = _cockpit(tmp_path)
    bridge, pool, _ = _bridge(cockpit)
    before = cockpit.writes()

    result = bridge.approveScopeAndStart(request_id, plan_hash)

    assert result == {"accepted": False, "busy": False, "message": "未找到要批准的范围卡。"}
    assert pool.worker is None
    assert cockpit.writes() == before


def test_b04_without_a_configured_approver_the_click_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path, approver="")
    before = cockpit.writes()

    _, _, finished = _click(cockpit)

    assert len(finished) == 1
    assert finished[0][1] is False and "未配置批准人" in finished[0][2]
    assert cockpit.writes() == before
    assert cockpit.starts() == 0


def test_b05_a_card_the_pm_has_since_replaced_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path)
    stale = cockpit.hashes[_REQUEST]
    cockpit.add_request(_REQUEST, risks=("a newer revision",))
    cockpit.hashes[_REQUEST] = stale
    before = cockpit.writes()

    _, _, finished = _click(cockpit)

    assert finished[0][1] is False and "取代" in finished[0][2]
    assert cockpit.writes() == before
    assert cockpit.starts() == 0


def test_b06_an_unfinished_task_refuses_the_click_before_any_write(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path)
    second_hash = cockpit.add_request(_SECOND, risks=("second",))
    cockpit.service.approve_scope(_REQUEST, cockpit.hashes[_REQUEST])
    assert cockpit.pending() == [(_SECOND, False)]
    before = cockpit.writes()

    _, _, finished = _click(cockpit, _SECOND)

    assert finished[0][1] is False and "要改同一批文件" in finished[0][2]
    assert cockpit.writes() == before
    assert second_hash == cockpit.hashes[_SECOND]


def test_b07_when_the_execution_fails_the_scope_stays_approved_and_the_message_says_so(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path, exit_code=3)

    _, _, finished = _click(cockpit)

    assert finished == [(_REQUEST, False, "范围已批准，但任务启动失败，执行记录已保留。")]
    assert cockpit.count("planning_draft_decision_bindings") == 1
    assert cockpit.store.get_mission(cockpit.mission_id()).state is MissionState.ACTIVE
    assert cockpit.pending() == []
    assert cockpit.action() is not CockpitUserAction.CONFIRM_ACCEPTANCE
    assert cockpit.count("checkpoints") == 0


def test_b08_a_failing_quality_gate_keeps_the_scene_and_never_opens_acceptance(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path, calc=BROKEN_CALC)

    _, _, finished = _click(cockpit)

    assert finished == [(_REQUEST, False, "范围已批准；质量验证未通过，已保留现场；未进入验收。")]
    assert cockpit.action() is not CockpitUserAction.CONFIRM_ACCEPTANCE
    assert cockpit.count("checkpoints") == 0


def test_b09_approving_again_after_a_failed_start_is_idempotent(tmp_path: Path) -> None:
    cockpit = _cockpit(tmp_path, exit_code=3)
    _click(cockpit)
    before = cockpit.writes()

    again = cockpit.service.approve_scope(_REQUEST, cockpit.hashes[_REQUEST])

    assert again.request_id == _REQUEST
    assert cockpit.writes() == before


def test_b10_unexpected_errors_never_expose_text_and_say_whether_the_scope_was_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    cockpit = _cockpit(tmp_path)
    bridge, pool, finished = _bridge(cockpit)

    def explode(_request_id: str, _plan_hash: str) -> object:
        raise RuntimeError("secret-path C:\\private\\token")

    monkeypatch.setattr(cockpit.service, "approve_scope", explode)
    with caplog.at_level(logging.ERROR):
        assert bridge.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])["accepted"] is True
        cast(QRunnable, pool.worker).run()
        bridge._poll_approve_workers()
    assert finished == [(_REQUEST, False, "范围未能批准，已保留现场。")]
    assert "secret-path" not in finished[0][2]

    monkeypatch.undo()
    bridge2, pool2, finished2 = _bridge(cockpit)

    def explode_start(_mission_id: str) -> object:
        raise RuntimeError("secret-path C:\\private\\token")

    monkeypatch.setattr(cockpit.service, "start_execution", explode_start)
    assert bridge2.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])["accepted"] is True
    cast(QRunnable, pool2.worker).run()
    bridge2._poll_approve_workers()
    assert finished2 == [
        (_REQUEST, False, "范围已批准，但任务启动出现意外错误，已保留现场；可在项目卡上点击“确认开始”重试。")
    ]
    assert "secret-path" not in finished2[0][2]
    assert cockpit.count("planning_draft_decision_bindings") == 1


def test_b11_a_known_start_error_after_approval_points_to_the_confirm_start_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cockpit = _cockpit(tmp_path)
    bridge, pool, finished = _bridge(cockpit)

    def refuse(_mission_id: str) -> object:
        raise PmCockpitError("该需求当前不能开始执行。")

    monkeypatch.setattr(cockpit.service, "start_execution", refuse)
    assert bridge.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])["accepted"] is True
    cast(QRunnable, pool.worker).run()
    bridge._poll_approve_workers()

    assert finished == [
        (_REQUEST, False, "范围已批准，但任务未能启动：该需求当前不能开始执行。；可在项目卡上点击“确认开始”重试。")
    ]
    assert cockpit.action() is CockpitUserAction.CONFIRM_START


def test_b12_a_refused_pool_clears_the_busy_state_and_a_closing_cockpit_publishes_nothing(
    tmp_path: Path,
) -> None:
    cockpit = _cockpit(tmp_path)

    class _RefusingPool:
        def start(self, _worker: QRunnable, _priority: int = 0) -> None:
            raise RuntimeError("pool is shutting down")

    refusing = PmCockpitBridge(
        str(cockpit.root), service=cockpit.service, thread_pool=cast(QThreadPool, _RefusingPool())
    )
    refused = refusing.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])
    assert refused["accepted"] is False and refused["busy"] is False
    assert refusing._approve_workers == {}

    bridge, pool, finished = _bridge(cockpit)
    assert bridge.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])["accepted"] is True
    bridge.stopSnapshotRefresh()
    cast(QRunnable, pool.worker).run()
    bridge._poll_approve_workers()
    assert finished == []
    assert bridge.approveScopeAndStart(_REQUEST, cockpit.hashes[_REQUEST])["message"] == "驾驶舱正在关闭。"
