"""Real-process proofs that the cockpit's "confirm start" runs, verifies and reaches acceptance."""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from auto_pm.change.ledger_reconciler import LedgerReconciler
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from auto_pm.core.pm_facade_service import PmFacadeService
from PySide6.QtCore import QThreadPool

from auto_pm.api import CockpitClient
from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_cockpit import CockpitUserAction
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge
from tests.core.test_cockpit_api import APPROVER, EVIDENCE, _plan, _token_locations
from tests.core.test_pm_run_e2e import (
    BROKEN_CALC,
    CALC,
    FIXED_CALC,
    GOOD_TESTS,
    PROJECT_ID,
    _build_workspace,
    _helper_source,
)
from tests.qml.test_pm_cockpit_bridge import _HoldingThreadPool

_VERIFIED = "已执行并通过质量验证，等待您的最终验收。"
_NOT_VERIFIED = "质量验证未通过，已保留现场；未进入验收。"
_START_FAILED = "任务启动失败，执行记录已保留。"
_KNOWN_TOKEN = "u07d-known-lease-token-0123456789abcdefghij"
_PLACEHOLDERS = ("（待填写）", "(待填写)", "待补充", "[在此填写", "[___________]")


@dataclass
class _Cockpit:
    root: Path
    store: ContinuityStore
    facade: PmFacadeService
    service: PmCockpitService
    counter: Path
    mission_id: str

    def starts(self) -> int:
        return len(self.counter.read_text(encoding="utf-8").splitlines()) if self.counter.exists() else 0

    def events(self) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def card_action(self) -> tuple[CockpitUserAction, str]:
        card = self.service.snapshot().projects[0]
        return card.user_action, card.next_user_action

    def mission_state(self) -> MissionState:
        return self.store.get_mission(self.mission_id).state


def _cockpit(base: Path, *, calc: str = FIXED_CALC, exit_code: int = 0) -> _Cockpit:
    """An approved planning Mission in DRAFT, with a real subprocess standing in for codex."""

    root = (base / "ws").resolve()
    _build_workspace(root)
    counter = base / "starts.txt"
    helper = base / "fake_codex.py"
    helper.write_text(
        _helper_source(calc=calc, tests=GOOD_TESTS, exit_code=exit_code, counter=counter),
        encoding="utf-8",
    )
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "u07d-e2e")
    facade = PmFacadeService(
        root,
        store=store,
        local_orchestrator=LocalExecutionOrchestrator(
            root,
            store=store,
            executor=LocalCodexExecutor(command_prefix=(sys.executable, str(helper))),
        ),
    )
    client = CockpitClient(root, PROJECT_ID)
    card = _plan(client)
    client.approve_plan(card, approver=APPROVER, approval_evidence_ref=EVIDENCE)
    mission = facade.materialize_planning_mission(card)
    service = PmCockpitService(root, store=store, facade=facade)
    return _Cockpit(root, store, facade, service, counter, mission.mission_id)


def _bridge(cockpit: _Cockpit) -> tuple[PmCockpitBridge, _HoldingThreadPool]:
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(
        str(cockpit.root), service=cockpit.service, thread_pool=cast(QThreadPool, pool)
    )
    return bridge, pool


def _run_start(
    cockpit: _Cockpit,
) -> tuple[list[tuple[str, bool, str]], PmCockpitBridge, _HoldingThreadPool]:
    bridge, pool = _bridge(cockpit)
    finished: list[tuple[str, bool, str]] = []
    bridge.startFinished.connect(
        lambda mission_id, success, message: finished.append((mission_id, success, message))
    )
    assert bridge.startExecution(cockpit.mission_id)["accepted"] is True
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_start_workers()
    return finished, bridge, pool


def test_confirm_start_runs_verifies_and_reaches_acceptance_then_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    cockpit = _cockpit(tmp_path)
    module = sys.modules[PmCockpitService.__module__]
    monkeypatch.setattr(module, "secrets", SimpleNamespace(token_urlsafe=lambda _size: _KNOWN_TOKEN))
    source_before = (cockpit.root / CALC).read_text(encoding="utf-8")
    assert cockpit.card_action() == (CockpitUserAction.CONFIRM_START, "确认开始执行")
    assert cockpit.mission_state() is MissionState.DRAFT

    # 包日志器 auto_pm 被 AppContext 配过级别后，只设根日志器拦不住 auto_pm.* 的 DEBUG；两层都放开才查得全。
    with caplog.at_level(logging.DEBUG), caplog.at_level(logging.DEBUG, logger="auto_pm"):
        finished, bridge, pool = _run_start(cockpit)

        assert finished == [(cockpit.mission_id, True, _VERIFIED)]
        assert cockpit.mission_state() is MissionState.ACCEPTANCE_PENDING
        assert cockpit.card_action() == (CockpitUserAction.CONFIRM_ACCEPTANCE, "确认最终验收")
        assert _token_locations(cockpit.root, _KNOWN_TOKEN) == {("execution_leases", "lease_token")}

        closed: list[tuple[str, bool, str]] = []
        bridge.closureFinished.connect(
            lambda mission_id, ok, message: closed.append((mission_id, ok, message))
        )
        accepted = bridge.confirmAcceptance(cockpit.mission_id)
        assert accepted["success"] is True and accepted["closing"] is True
        assert pool.worker is not None
        pool.worker.run()
        bridge._poll_close_workers()

    assert [(mission_id, ok) for mission_id, ok, _ in closed] == [(cockpit.mission_id, True)]
    mission = cockpit.store.get_mission(cockpit.mission_id)
    assert mission.state is MissionState.CLOSED
    assert mission.root_work_id
    assert cockpit.store.get_work(mission.root_work_id).state is WorkState.CLOSED
    assert cockpit.store.list_runs(mission.root_work_id, include_terminal=True)[0].state is RunState.SUCCEEDED
    change = next(cockpit.root.glob("**/CHG-SCPT-*.md")).read_text(encoding="utf-8")
    assert not [item for item in _PLACEHOLDERS if item in change]
    assert any(line.startswith("| **验证结论**") for line in change.splitlines())
    assert LedgerReconciler().reconcile(str(cockpit.root)).is_clean
    assert (cockpit.root / CALC).read_text(encoding="utf-8") == source_before
    assert source_before != FIXED_CALC
    assert _token_locations(cockpit.root, _KNOWN_TOKEN) == set()
    visible = " ".join([*(message for _, _, message in finished), *(m for _, _, m in closed), caplog.text])
    assert _KNOWN_TOKEN not in visible


def test_a_second_start_is_refused_while_running_and_only_one_process_ever_starts(
    tmp_path: Path,
) -> None:
    cockpit = _cockpit(tmp_path)
    bridge, pool = _bridge(cockpit)

    first = bridge.startExecution(cockpit.mission_id)
    replay = bridge.startExecution(cockpit.mission_id)

    assert first["accepted"] is True
    assert replay["accepted"] is False and replay["busy"] is True
    assert cockpit.starts() == 0
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_start_workers()
    assert cockpit.starts() == 1
    with pytest.raises(PmCockpitError, match="已执行并验证"):
        cockpit.service.start_execution(cockpit.mission_id)
    assert cockpit.starts() == 1


def test_a_failed_execution_is_never_shown_as_started_or_ready_for_acceptance(
    tmp_path: Path,
) -> None:
    cockpit = _cockpit(tmp_path, exit_code=3)

    finished, _, _ = _run_start(cockpit)

    assert finished == [(cockpit.mission_id, False, _START_FAILED)]
    assert cockpit.mission_state() is MissionState.ACTIVE
    assert cockpit.card_action()[0] is not CockpitUserAction.CONFIRM_ACCEPTANCE
    with closing(sqlite3.connect(cockpit.root / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0


def test_a_failing_quality_gate_keeps_the_scene_and_does_not_open_acceptance(
    tmp_path: Path,
) -> None:
    cockpit = _cockpit(tmp_path, calc=BROKEN_CALC)

    finished, _, _ = _run_start(cockpit)

    assert finished == [(cockpit.mission_id, False, _NOT_VERIFIED)]
    assert cockpit.mission_state() is MissionState.ACTIVE
    assert cockpit.card_action()[0] is not CockpitUserAction.CONFIRM_ACCEPTANCE
    with closing(sqlite3.connect(cockpit.root / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
