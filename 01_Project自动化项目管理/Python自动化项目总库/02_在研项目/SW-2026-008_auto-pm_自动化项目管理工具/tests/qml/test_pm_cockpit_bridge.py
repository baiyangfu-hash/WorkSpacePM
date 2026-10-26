"""Bridge coverage for the no-write default cockpit path."""

from __future__ import annotations

import ctypes
import faulthandler
import gc
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread, get_native_id
from typing import Literal, NoReturn, cast
from weakref import ReferenceType, ref

import pytest
from auto_pm.change.ledger_reconciler import ReconcileDiff
from auto_pm.core.pm_closure_service import PmClosureService
from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from PySide6.QtCore import QRunnable, Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_cockpit import (
    PmCockpitCompletion,
    PmCockpitCompletionState,
    PmCockpitEvidence,
    PmCockpitFocus,
    PmCockpitSnapshot,
)
from auto_pm.contracts.pm_facade import PmConfirmationCard, PmConfirmationKind, PmRunOutcome
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge, _StartWorker
from tests.core.test_pm_closure_service import _MISSION_ID as _CLOSE_MISSION
from tests.core.test_pm_closure_service import (
    _accepted_lineage,
    _lineage_states,
    _ProjectionReconciler,
)
from tests.core.test_pm_cockpit_service import _registry as _core_registry
from tests.core.test_pm_cockpit_service import _seed_authorized_mission
from tests.qml.conftest import _assert_gui_thread, _delete_qobject


class _HoldingThreadPool:
    def __init__(self) -> None:
        self.worker: QRunnable | None = None

    def start(self, worker: QRunnable, priority: int = 0) -> None:
        del priority
        self.worker = worker


@contextmanager
def _managed_start_bridge(
    root: Path, service: PmCockpitService, pool: _HoldingThreadPool
) -> Iterator[PmCockpitBridge]:
    """Close a synchronous holding-pool test even when an assertion interrupts it."""
    bridge = PmCockpitBridge(str(root), service=service, thread_pool=cast(QThreadPool, pool))
    try:
        yield bridge
    finally:
        _assert_gui_thread(bridge)
        for timer in bridge.findChildren(QTimer):
            timer.stop()
        bridge.blockSignals(True)
        # This pool only holds tasks; discard unexecuted work without running business code.
        pool.worker = None
        bridge._start_workers.clear()
        _delete_qobject(bridge)


class _StartService:
    def __init__(self, outcomes: list[PmRunOutcome | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def start_execution(self, mission_id: str) -> PmRunOutcome:
        self.calls.append(mission_id)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _SnapshotService:
    def __init__(self, outcomes: list[PmCockpitSnapshot | Exception]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def snapshot(self) -> PmCockpitSnapshot:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _receipt(
    status: Literal["VERIFYING", "FAILED", "PENDING"],
) -> PmRunOutcome:
    verified = status == "VERIFYING"
    return PmRunOutcome(
        mission_id="MISSION-001",
        run_id=f"RUN-{status}",
        receipt_status=status,
        verified=verified,
        checkpoint_id=f"CP-RUN-{status}-VERIFY" if verified else "",
        mission_state=MissionState.ACCEPTANCE_PENDING if verified else MissionState.ACTIVE,
        message=(
            "已执行并通过质量验证，等待您的最终验收。"
            if verified
            else "执行未完成，未进行质量验证；已保留现场。"
        ),
    )


def _python_stack(root: Path) -> None:
    """Give the fixture project a stack, from which the chosen kind gets its technical domain."""
    project = root / "projects" / "DJ-2026-005"
    project.mkdir(parents=True, exist_ok=True)
    (project / ".copier-answers.yml").write_text(
        "project_id: DJ-2026-005\nproject_name: Bridge fixture\nstack: python\n",
        encoding="utf-8",
        errors="replace",
    )


def _registry(root: Path) -> None:
    path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "DJ-2026-005",
                        "project_root": "projects/DJ-2026-005",
                        "development_root": "projects/DJ-2026-005",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _git_root(root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "init"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_bridge_default_load_is_read_only_when_continuity_store_is_missing(tmp_path: Path) -> None:
    _registry(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))

    result = bridge.loadSnapshot()

    assert result["success"] is True
    card = result["snapshot"]["projects"][0]
    assert card["project_id"] == "DJ-2026-005"
    assert "向 PM 描述需求" in card["next_user_action"]
    assert "不会自动修复" in card["next_user_action"]
    assert not (tmp_path / ".auto-pm").exists()


def test_bridge_rejects_evidence_for_an_unregistered_project(tmp_path: Path) -> None:
    _registry(tmp_path)
    bridge = PmCockpitBridge(str(tmp_path))

    result = bridge.loadEvidence("UNKNOWN-001")

    assert result["success"] is False
    assert "不在工作空间项目清单" in result["message"]


def test_bridge_persists_pre_auth_draft_and_replays_same_input(tmp_path: Path) -> None:
    _registry(tmp_path)
    _python_stack(tmp_path)
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))
    first = bridge.createPlanningDraft(
        "DJ-2026-005", " Improve line throughput ", "Measure cycle time\nNo safety bypass", "iteration"
    )
    replay = bridge.createPlanningDraft(
        "DJ-2026-005", "Improve line throughput", "Measure cycle time\nNo safety bypass", "iteration"
    )
    changed = bridge.createPlanningDraft(
        "DJ-2026-005", "Improve quality", "Measure cycle time\nNo safety bypass", "iteration"
    )
    new_session = PmCockpitBridge(str(tmp_path)).createPlanningDraft(
        "DJ-2026-005", "Improve line throughput", "Measure cycle time\nNo safety bypass", "iteration"
    )

    assert all(result["success"] for result in (first, replay, changed, new_session))
    assert first["draft"] == replay["draft"]
    assert first["draft"]["state"] == "PRE_AUTH"
    assert first["draft"]["scope_status"] == "范围待规划"
    assert first["draft"]["acceptance_criteria"] == ["Measure cycle time", "No safety bypass"]
    assert "request_id" not in first["draft"]
    with sqlite3.connect(store.db_path) as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("planning_drafts", "mission_items", "work_items", "run_items")
        }
        request_ids = conn.execute("SELECT request_id FROM planning_drafts").fetchall()
    assert counts == {"planning_drafts": 3, "mission_items": 0, "work_items": 0, "run_items": 0}
    assert len(set(request_ids)) == 3
    assert not list(tmp_path.rglob("CHG-*.md"))


def test_bridge_refuses_a_draft_without_a_chosen_kind_and_writes_nothing(tmp_path: Path) -> None:
    _registry(tmp_path)
    _python_stack(tmp_path)
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))

    # TD-SW008-070: no kind, an unknown kind, or a CHANGE (which also needs an action) is never saved.
    for kind in ("", "   ", "nonsense", "change"):
        result = bridge.createPlanningDraft("DJ-2026-005", "Improve", "Measure cycle time", kind)
        assert result["success"] is False, kind
        assert "draft" not in result
        assert "类型" in result["message"] or "草稿未保存" in result["message"], result["message"]

    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0] == 0
        bindings = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='planning_draft_intake_bindings'"
        ).fetchone()
        assert bindings is None or conn.execute(
            "SELECT COUNT(*) FROM planning_draft_intake_bindings"
        ).fetchone()[0] == 0


def test_bridge_binds_the_chosen_kind_to_the_saved_draft(tmp_path: Path) -> None:
    _registry(tmp_path)
    _python_stack(tmp_path)
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))

    saved = bridge.createPlanningDraft("DJ-2026-005", "Fix the jam", "No jam in 100 cycles", "bug")
    again = bridge.createPlanningDraft("DJ-2026-005", "Fix the jam", "No jam in 100 cycles", "bug")
    other = bridge.createPlanningDraft("DJ-2026-005", "Fix the jam", "No jam in 100 cycles", "debt")

    assert saved["success"] and again["success"] and other["success"]
    with sqlite3.connect(store.db_path) as conn:
        kinds = sorted(
            json.loads(row[0])["kind"]
            for row in conn.execute("SELECT classification_json FROM planning_draft_intake_bindings")
        )
    # The same words with the same kind replay one draft; another kind is a different request.
    assert kinds == ["BUG", "DEBT"]


def test_bridge_rejects_incomplete_or_unknown_planning_input(tmp_path: Path) -> None:
    _registry(tmp_path)
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))

    for project, objective, acceptance in (
        ("DJ-2026-005", "", "Accepted"),
        ("DJ-2026-005", "Objective", "  "),
        ("", "Objective", "Accepted"),
        ("UNKNOWN", "Objective", "Accepted"),
        ("DJ-2026-005", "Objective", "Same\nSame"),
    ):
        result = bridge.createPlanningDraft(project, objective, acceptance, "iteration")
        assert result["success"] is False
        assert "draft" not in result

    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0] == 0


def test_start_execution_is_one_shot_until_worker_finishes(tmp_path: Path) -> None:
    service = _StartService([_receipt("VERIFYING"), _receipt("VERIFYING")])
    pool = _HoldingThreadPool()
    with _managed_start_bridge(tmp_path, cast(PmCockpitService, service), pool) as bridge:
        finished: list[tuple[str, bool, str]] = []
        bridge.startFinished.connect(
            lambda mission_id, success, message: finished.append(
                (mission_id, success, message)
            )
        )

        first = bridge.startExecution(" MISSION-001 ")
        replay = bridge.startExecution("MISSION-001")

        assert first == {
            "accepted": True,
            "busy": True,
            "message": "已提交启动请求，正在后台执行。",
        }
        assert replay["accepted"] is False
        assert replay["busy"] is True
        assert service.calls == []
        assert pool.worker is not None

        pool.worker.run()
        bridge._poll_start_workers()

        assert service.calls == ["MISSION-001"]
        assert finished == [("MISSION-001", True, "已执行并通过质量验证，等待您的最终验收。")]
        assert bridge.startExecution("MISSION-001")["accepted"] is True


def test_start_execution_failure_clears_busy_without_false_success(tmp_path: Path) -> None:
    service = _StartService([PmCockpitError("授权已失效"), _receipt("PENDING")])
    pool = _HoldingThreadPool()
    with _managed_start_bridge(tmp_path, cast(PmCockpitService, service), pool) as bridge:
        finished: list[tuple[str, bool, str]] = []
        bridge.startFinished.connect(
            lambda mission_id, success, message: finished.append(
                (mission_id, success, message)
            )
        )

        assert bridge.startExecution("MISSION-FAIL")["accepted"] is True
        assert pool.worker is not None
        pool.worker.run()
        bridge._poll_start_workers()

        assert finished == [("MISSION-FAIL", False, "授权已失效")]
        assert bridge.startExecution("MISSION-FAIL")["accepted"] is True
        assert pool.worker is not None
        pool.worker.run()
        bridge._poll_start_workers()
        assert finished[-1] == (
            "MISSION-FAIL",
            False,
            "无法确认任务已启动，已保留待核验状态。",
        )


def _finished_start(
    tmp_path: Path, outcome: PmRunOutcome | Exception
) -> list[tuple[str, bool, str]]:
    pool = _HoldingThreadPool()
    with _managed_start_bridge(tmp_path, cast(PmCockpitService, _StartService([outcome])), pool) as bridge:
        finished: list[tuple[str, bool, str]] = []
        bridge.startFinished.connect(
            lambda mission_id, success, message: finished.append((mission_id, success, message))
        )
        assert bridge.startExecution("MISSION-001")["accepted"] is True
        assert pool.worker is not None
        pool.worker.run()
        bridge._poll_start_workers()
        return finished


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (_receipt("VERIFYING"), (True, "已执行并通过质量验证，等待您的最终验收。")),
        (_receipt("FAILED"), (False, "任务启动失败，执行记录已保留。")),
        (_receipt("PENDING"), (False, "无法确认任务已启动，已保留待核验状态。")),
        (
            PmRunOutcome(
                mission_id="MISSION-001",
                run_id="RUN-VERIFYING",
                receipt_status="VERIFYING",
                verified=False,
                mission_state=MissionState.ACTIVE,
                message="质量验证未通过，已保留现场；未进入验收。",
            ),
            (False, "质量验证未通过，已保留现场；未进入验收。"),
        ),
    ],
    ids=["verified", "failed", "pending", "not-verified"],
)
def test_start_worker_maps_every_outcome_to_a_fixed_sentence(
    tmp_path: Path, outcome: PmRunOutcome, expected: tuple[bool, str]
) -> None:
    assert _finished_start(tmp_path, outcome) == [("MISSION-001", *expected)]


def test_start_worker_never_exposes_unexpected_exception_text(tmp_path: Path) -> None:
    finished = _finished_start(tmp_path, RuntimeError(r"C:\secret\path token=abc123"))

    assert finished == [("MISSION-001", False, "任务启动失败，已保留现场。")]
    assert "secret" not in finished[0][2] and "abc123" not in finished[0][2]


def test_snapshot_refresh_is_background_and_skips_overlapping_ticks(tmp_path: Path) -> None:
    service = _SnapshotService([PmCockpitSnapshot(projects=())])
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, pool),
        snapshot_interval_ms=1_000,
    )
    finished: list[dict[str, object]] = []
    bridge.snapshotFinished.connect(lambda response: finished.append(response))

    first = bridge.requestSnapshot()
    overlap = bridge.requestSnapshot()

    assert first["accepted"] is True
    assert overlap == {
        "accepted": False,
        "busy": True,
        "message": "状态刷新正在进行。",
    }
    assert service.calls == 0
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_snapshot_worker()
    assert service.calls == 1
    assert finished[0]["success"] is True
    assert cast(dict[str, object], finished[0]["snapshot"])["activities"] == []


def test_snapshot_failure_and_shutdown_never_publish_a_replacement(tmp_path: Path) -> None:
    service = _SnapshotService([RuntimeError("read failed"), PmCockpitSnapshot(projects=())])
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, pool),
    )
    finished: list[dict[str, object]] = []
    bridge.snapshotFinished.connect(lambda response: finished.append(response))

    assert bridge.requestSnapshot()["accepted"] is True
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_snapshot_worker()
    assert finished == [{"success": False, "snapshot": {}, "message": "read failed"}]

    assert bridge.requestSnapshot()["accepted"] is True
    assert pool.worker is not None
    bridge.stopSnapshotRefresh()
    pool.worker.run()
    bridge._poll_snapshot_worker()
    assert finished == [{"success": False, "snapshot": {}, "message": "read failed"}]
    assert bridge.requestSnapshot()["accepted"] is False


# --- U05: background, one-at-a-time evidence reads -------------------------------------------


class _EvidenceService:
    def __init__(self, outcomes: list[PmCockpitEvidence | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def evidence(self, project_id: str) -> PmCockpitEvidence:
        self.calls.append(project_id)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _evidence(project_id: str = "SW-2026-008") -> PmCockpitEvidence:
    return PmCockpitEvidence(
        project_id=project_id,
        read_set=(),
        work_graph=(),
        checkpoints=(),
        verification_evidence=(),
        status_note="只读。",
        focus=PmCockpitFocus(
            mission_id="MISSION-001", work_id="WORK-001", run_id="RUN-001", run_state="执行中"
        ),
    )


def _evidence_bridge(
    tmp_path: Path, outcomes: list[PmCockpitEvidence | Exception]
) -> tuple[PmCockpitBridge, _EvidenceService, _HoldingThreadPool, list[dict[str, object]]]:
    service = _EvidenceService(outcomes)
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, pool),
    )
    finished: list[dict[str, object]] = []
    bridge.evidenceFinished.connect(lambda response: finished.append(response))
    return bridge, service, pool, finished


def test_request_evidence_rejects_a_blank_project_without_queueing_anything(
    tmp_path: Path,
) -> None:
    bridge, service, pool, finished = _evidence_bridge(tmp_path, [_evidence()])

    result = bridge.requestEvidence("   ")

    assert result == {"accepted": False, "busy": False, "message": "未找到要查看证据的项目。"}
    assert pool.worker is None
    assert service.calls == []
    assert finished == []


def test_request_evidence_is_background_one_at_a_time_and_finishes_exactly_once(
    tmp_path: Path,
) -> None:
    bridge, service, pool, finished = _evidence_bridge(tmp_path, [_evidence()])

    first = bridge.requestEvidence(" SW-2026-008 ")
    overlap = bridge.requestEvidence("SW-2026-008")

    assert first == {"accepted": True, "busy": True, "message": "正在读取证据。"}
    assert overlap == {"accepted": False, "busy": True, "message": "证据正在读取，请稍候。"}
    assert service.calls == []
    assert pool.worker is not None
    bridge._poll_evidence_worker()
    assert finished == []
    pool.worker.run()
    bridge._poll_evidence_worker()
    bridge._poll_evidence_worker()

    assert service.calls == ["SW-2026-008"]
    assert len(finished) == 1
    assert finished[0]["success"] is True
    assert finished[0]["project_id"] == "SW-2026-008"
    payload = cast(dict[str, object], finished[0]["evidence"])
    assert cast(dict[str, object], payload["focus"])["run_id"] == "RUN-001"
    assert bridge.requestEvidence("SW-2026-008")["accepted"] is True


def test_evidence_failures_never_expose_exception_text_or_paths(tmp_path: Path) -> None:
    secret = f"boom at {tmp_path} secret-detail"
    bridge, _, pool, finished = _evidence_bridge(
        tmp_path, [PmCockpitError("该项目不在工作空间项目清单中。"), RuntimeError(secret)]
    )

    assert bridge.requestEvidence("A-1")["accepted"] is True
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_evidence_worker()
    assert bridge.requestEvidence("A-2")["accepted"] is True
    pool.worker.run()
    bridge._poll_evidence_worker()

    assert finished[0] == {
        "success": False,
        "project_id": "A-1",
        "evidence": {},
        "message": "该项目不在工作空间项目清单中。",
    }
    assert finished[1]["success"] is False
    assert finished[1]["message"] == "无法读取证据。"
    assert "secret-detail" not in json.dumps(finished)
    assert str(tmp_path) not in json.dumps(finished, ensure_ascii=False)


def test_evidence_pool_refusal_clears_the_busy_flag(tmp_path: Path) -> None:
    class _RefusingPool:
        def start(self, worker: QRunnable, priority: int = 0) -> None:
            del worker, priority
            raise RuntimeError("pool is shut down")

    service = _EvidenceService([_evidence()])
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, _RefusingPool()),
    )

    result = bridge.requestEvidence("SW-2026-008")

    assert result["accepted"] is False
    assert result["busy"] is False
    assert "未能进入后台" in str(result["message"])
    assert bridge._evidence_worker is None


def test_evidence_result_is_suppressed_after_shutdown(tmp_path: Path) -> None:
    bridge, _, pool, finished = _evidence_bridge(tmp_path, [_evidence()])

    assert bridge.requestEvidence("SW-2026-008")["accepted"] is True
    assert pool.worker is not None
    bridge.stopSnapshotRefresh()
    pool.worker.run()
    bridge._poll_evidence_worker()

    assert finished == []
    assert bridge._evidence_worker is None
    refused = bridge.requestEvidence("SW-2026-008")
    assert refused == {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}


def test_request_evidence_reads_the_real_store_and_a_reopened_bridge_sees_the_same_run(
    tmp_path: Path,
) -> None:
    _core_registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    expected = {
        "mission_id": "MISSION-COCKPIT-001",
        "work_id": "WORK-COCKPIT-001",
        "run_id": "RUN-COCKPIT-001",
        "run_state": "已授权",
    }
    seen: list[dict[str, object]] = []
    for _ in range(2):
        pool = _HoldingThreadPool()
        bridge = PmCockpitBridge(str(tmp_path), thread_pool=cast(QThreadPool, pool))
        finished: list[dict[str, object]] = []
        bridge.evidenceFinished.connect(lambda response, sink=finished: sink.append(response))
        assert bridge.requestEvidence("SW-2026-008")["accepted"] is True
        assert pool.worker is not None
        pool.worker.run()
        bridge._poll_evidence_worker()
        assert len(finished) == 1 and finished[0]["success"] is True
        seen.append(cast(dict[str, object], finished[0]["evidence"]))
        del bridge
    assert seen[0]["focus"] == seen[1]["focus"] == expected
    assert cast(dict[str, object], seen[1]["resume"])["user_action"] == "CONFIRM_START"
    assert "lease" not in json.dumps(seen).lower()


def test_request_evidence_for_an_unregistered_project_fails_with_the_service_message(
    tmp_path: Path,
) -> None:
    _registry(tmp_path)
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(str(tmp_path), thread_pool=cast(QThreadPool, pool))
    finished: list[dict[str, object]] = []
    bridge.evidenceFinished.connect(lambda response: finished.append(response))

    assert bridge.requestEvidence("UNKNOWN-001")["accepted"] is True
    assert pool.worker is not None
    pool.worker.run()
    bridge._poll_evidence_worker()

    assert finished[0]["success"] is False
    assert "不在工作空间项目清单" in str(finished[0]["message"])


# --- U06: acceptance is followed by a background closure that can be retried -----------------


class _AcceptAndCloseService:
    def __init__(
        self,
        acceptance: PmConfirmationCard | Exception,
        closures: list[PmCockpitCompletion | Exception],
    ) -> None:
        self.acceptance = acceptance
        self.closures = closures
        self.accept_calls: list[str] = []
        self.close_calls: list[str] = []

    def confirm_acceptance(self, mission_id: str) -> PmConfirmationCard:
        self.accept_calls.append(mission_id)
        if isinstance(self.acceptance, Exception):
            raise self.acceptance
        return self.acceptance

    def close_accepted(self, mission_id: str) -> PmCockpitCompletion:
        self.close_calls.append(mission_id)
        outcome = self.closures.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _MultiThreadPool:
    """Holds every started worker so several Missions can be in flight at once."""

    def __init__(self) -> None:
        self.workers: list[QRunnable] = []

    @property
    def worker(self) -> QRunnable | None:
        return self.workers[-1] if self.workers else None

    def start(self, worker: QRunnable, priority: int = 0) -> None:
        del priority
        self.workers.append(worker)


def _acceptance_card(mission_id: str = "MISSION-001") -> PmConfirmationCard:
    return PmConfirmationCard(
        kind=PmConfirmationKind.ACCEPTANCE,
        mission_id=mission_id,
        title="验收",
        mission_state=MissionState.ACCEPTED,
        summary="请确认最终验收；确认后驾驶舱才会执行关闭和台账闭环。",
        acceptance_criteria=("通过",),
        next_actions=("close",),
    )


def _completion(state: PmCockpitCompletionState, message: str, mission_id: str = "MISSION-001") -> PmCockpitCompletion:
    return PmCockpitCompletion(mission_id=mission_id, state=state, message=message)


def _closing_bridge(
    tmp_path: Path,
    acceptance: PmConfirmationCard | Exception,
    closures: list[PmCockpitCompletion | Exception],
) -> tuple[PmCockpitBridge, _AcceptAndCloseService, _MultiThreadPool, list[tuple[str, bool, str]]]:
    service = _AcceptAndCloseService(acceptance, closures)
    pool = _MultiThreadPool()
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, pool),
    )
    finished: list[tuple[str, bool, str]] = []
    bridge.closureFinished.connect(lambda m, ok, msg: finished.append((m, ok, msg)))
    return bridge, service, pool, finished


def test_accepting_queues_exactly_one_background_closure_and_keeps_the_legacy_keys(
    tmp_path: Path,
) -> None:
    done = _completion(PmCockpitCompletionState.COMPLETED, "已完成：变更单与台账已同步。")
    bridge, service, pool, finished = _closing_bridge(tmp_path, _acceptance_card(), [done])

    result = bridge.confirmAcceptance("MISSION-001")

    assert result["success"] is True
    assert result["closing"] is True
    assert "确认后驾驶舱才会执行关闭" in result["message"]
    assert result["confirmation"]["mission_id"] == "MISSION-001"
    assert service.accept_calls == ["MISSION-001"]
    assert service.close_calls == []
    assert len(pool.workers) == 1
    assert finished == []
    pool.workers[0].run()
    bridge._poll_close_workers()
    bridge._poll_close_workers()
    assert service.close_calls == ["MISSION-001"]
    assert finished == [("MISSION-001", True, "已完成：变更单与台账已同步。")]


def test_a_refused_acceptance_queues_no_closure(tmp_path: Path) -> None:
    bridge, service, pool, finished = _closing_bridge(
        tmp_path, PmCockpitError("最新 Checkpoint 未证明当前通过的质量证据"), []
    )

    result = bridge.confirmAcceptance("MISSION-001")

    assert result == {
        "success": False,
        "message": "最新 Checkpoint 未证明当前通过的质量证据",
        "closing": False,
    }
    assert pool.workers == []
    assert service.close_calls == []
    assert finished == []
    blank = bridge.confirmAcceptance("   ")
    assert blank["success"] is False and blank["closing"] is False


def test_retry_closure_is_one_at_a_time_per_mission_and_never_stacks(tmp_path: Path) -> None:
    pending = _completion(PmCockpitCompletionState.PENDING_SYNC, "台账同步未完成，已保留现场；可稍后重试。")
    bridge, service, pool, finished = _closing_bridge(tmp_path, _acceptance_card(), [pending, pending])
    workers = pool.workers

    first = bridge.retryClosure(" MISSION-001 ")
    overlap = bridge.retryClosure("MISSION-001")
    other = bridge.retryClosure("MISSION-002")
    blank = bridge.retryClosure("  ")

    assert first == {"accepted": True, "busy": True, "message": "已提交收尾请求，正在后台同步。"}
    assert overlap == {"accepted": False, "busy": True, "message": "该需求正在同步，请勿重复操作。"}
    assert other["accepted"] is True
    assert blank == {"accepted": False, "busy": False, "message": "未找到可同步的需求。"}
    assert len(workers) == 2
    for worker in workers:
        worker.run()
    bridge._poll_close_workers()
    bridge._poll_close_workers()
    assert sorted(service.close_calls) == ["MISSION-001", "MISSION-002"]
    assert sorted(item[0] for item in finished) == ["MISSION-001", "MISSION-002"]
    assert all(ok is False for _, ok, _ in finished)
    assert bridge.retryClosure("MISSION-001")["accepted"] is True


def test_closure_failures_never_expose_exception_text_or_paths(tmp_path: Path) -> None:
    secret = f"boom at {tmp_path} secret-detail"
    bridge, _, pool, finished = _closing_bridge(
        tmp_path,
        _acceptance_card(),
        [PmCockpitError("该需求尚未验收，不能收尾。"), RuntimeError(secret)],
    )
    workers = pool.workers

    assert bridge.retryClosure("MISSION-A")["accepted"] is True
    workers[-1].run()
    bridge._poll_close_workers()
    assert bridge.retryClosure("MISSION-B")["accepted"] is True
    workers[-1].run()
    bridge._poll_close_workers()

    assert finished[0] == ("MISSION-A", False, "收尾失败：该需求尚未验收，不能收尾。")
    assert finished[1] == (
        "MISSION-B",
        False,
        "收尾失败：读写账本时出错（详情已写入日志），这次没有写入。"
        "验收记录已保存，不用重新验收；请关闭驾驶舱窗口，再由主执行重试收口。",
    )
    assert "secret-detail" not in json.dumps(finished, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(finished, ensure_ascii=False)


def test_closure_pool_refusal_clears_the_busy_flag(tmp_path: Path) -> None:
    class _RefusingPool:
        def start(self, worker: QRunnable, priority: int = 0) -> None:
            del worker, priority
            raise RuntimeError("pool is shut down")

    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, _AcceptAndCloseService(_acceptance_card(), [])),
        thread_pool=cast(QThreadPool, _RefusingPool()),
    )

    result = bridge.retryClosure("MISSION-001")

    assert result["accepted"] is False and result["busy"] is False
    assert "未能进入后台" in str(result["message"])
    assert bridge._close_workers == {}
    assert bridge.confirmAcceptance("MISSION-001")["closing"] is False


def test_closure_result_is_suppressed_after_shutdown(tmp_path: Path) -> None:
    done = _completion(PmCockpitCompletionState.COMPLETED, "已完成：变更单与台账已同步。")
    bridge, _, pool, finished = _closing_bridge(tmp_path, _acceptance_card(), [done])

    assert bridge.retryClosure("MISSION-001")["accepted"] is True
    bridge.stopSnapshotRefresh()
    pool.workers[0].run()
    bridge._poll_close_workers()

    assert finished == []
    assert bridge._close_workers == {}
    refused = bridge.retryClosure("MISSION-001")
    assert refused == {"accepted": False, "busy": False, "message": "驾驶舱正在关闭。"}
    assert bridge.confirmAcceptance("MISSION-001")["closing"] is False


def test_retry_closure_runs_the_real_closure_service_and_completes_after_a_failed_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _core_registry(tmp_path)
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(OSError("ledger unavailable"))
    closure = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    monkeypatch.setattr(closure, "inject_prepared_change_substance", lambda _id: tmp_path / "CHG.md")
    service = PmCockpitService(tmp_path, store=store, closure_service=closure)
    pool = _MultiThreadPool()
    bridge = PmCockpitBridge(str(tmp_path), service=service, thread_pool=cast(QThreadPool, pool))
    finished: list[tuple[str, bool, str]] = []
    bridge.closureFinished.connect(lambda m, ok, msg: finished.append((m, ok, msg)))

    for expect_ok in (False, True):
        if expect_ok:
            reconciler.result = ReconcileDiff()
        assert bridge.retryClosure(_CLOSE_MISSION)["accepted"] is True
        pool.workers[-1].run()
        bridge._poll_close_workers()
        assert finished[-1][0] == _CLOSE_MISSION and finished[-1][1] is expect_ok

    assert finished[0][2] == "台账同步未完成，已保留现场；可稍后重试。"
    assert finished[1][2] == "已完成：变更单与台账已同步。"
    assert _lineage_states(database)[:4] == ("SUCCEEDED", "CLOSED", "CLOSED", "COMPLETED")
    assert "ledger unavailable" not in json.dumps(finished)


def _destroyed_on(events: list[tuple[str, int]], label: str) -> Callable[..., None]:
    """Observe native destruction without retaining any Qt object or signal argument."""
    def record(*_args: object) -> None:
        events.append((label, get_native_id()))
    return record


# 真实成功用例正常耗时 67-75 秒（含真实质量门）；机器前台有重程序时门禁整体慢 2-3 倍（TD-SW008-135）。
_REAL_START_BASELINE_MS = {True: 600_000, False: 5_000}
_WATCHDOG_SCALE_ENV = "AUTO_PM_START_WATCHDOG_SCALE"


def _start_watchdog_ms(succeeds: bool, env: Mapping[str, str] | None = None) -> int:
    """看门狗时限：成功用例 600 秒（正常耗时的 8 倍），可用环境变量按倍数放宽，不能缩短。"""
    source = os.environ if env is None else env
    try:
        scale = float(source.get(_WATCHDOG_SCALE_ENV, "1"))
    except ValueError:
        scale = 1.0
    return int(_REAL_START_BASELINE_MS[succeeds] * max(scale, 1.0))


def _load_facts() -> dict[str, object]:
    """超时当时的机器负载，让 qml 组 124 退出不再只剩一个 git 栈。"""
    facts: dict[str, object] = {"cpu_count": os.cpu_count()}
    if hasattr(os, "getloadavg"):
        facts["load_average"] = os.getloadavg()
    facts["hint"] = (
        "超时先看机器负载：栈停在 git 子进程只说明当时正在跑质量门，不等于 git 卡死；"
        f"确认机器过载后可设环境变量 {_WATCHDOG_SCALE_ENV}=2 或 3 重跑"
    )
    return facts


def _exit_start_timeout(
    root: Path, phase: str, timeout_ms: int, facts: dict[str, object]
) -> NoReturn:
    """Persist phase and live Python stacks outside pytest's captured descriptors."""
    facts = {**_load_facts(), **facts}
    junit = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--junitxml=")), None)
    directory = Path(junit).resolve().parent if junit else root
    path = directory / f"pm-start-timeout-{os.getpid()}.log"
    try:
        with path.open("x", encoding="utf-8", errors="replace") as stream:
            stream.write(json.dumps({
                "phase": phase, "timeout_ms": timeout_ms, "pid": os.getpid(),
                "thread_id": get_native_id(), "at": datetime.now(UTC).isoformat(),
                "workspace": str(root), **facts,
            }, ensure_ascii=False) + "\n")
            stream.flush()
            faulthandler.dump_traceback(file=stream, all_threads=True)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os._exit(124)  # Never unwind owners whose worker completion is unproven.


def _real_start_owner_refs(
    root: Path, succeeds: bool, events: list[tuple[str, int]]
) -> tuple[_StartWorker, ReferenceType[PmCockpitBridge], ReferenceType[QThreadPool]]:
    """Run the real service in a real pool, then release every local GUI owner."""
    if succeeds:
        # Import lazily: this existing real-execution helper imports our holding pool.
        from tests.qml.test_pm_cockpit_start_e2e import _cockpit

        cockpit = _cockpit(root)
        service = cockpit.service
        mission_id = cockpit.mission_id
        workspace = cockpit.root
    else:
        workspace = root
        service = PmCockpitService(workspace)
        mission_id = "MISSION-NOT-IN-TEMP-STORE"
    pool = QThreadPool()
    bridge = PmCockpitBridge(str(workspace), service=service, thread_pool=pool)
    bridge.destroyed.connect(_destroyed_on(events, "bridge"), Qt.ConnectionType.DirectConnection)
    bridge._start_poll_timer.destroyed.connect(
        _destroyed_on(events, "start_timer"), Qt.ConnectionType.DirectConnection
    )
    delivered: list[tuple[str, bool, str]] = []
    bridge.startFinished.connect(lambda m, ok, msg: delivered.append((m, ok, msg)))
    try:
        assert bridge.startExecution(mission_id)["accepted"] is True
        worker = bridge._start_workers[mission_id]
        # The existing real success E2E takes 67-75 seconds, including genuine quality gates.
        timeout_ms = _start_watchdog_ms(succeeds)
        if not pool.waitForDone(timeout_ms):
            _exit_start_timeout(workspace, "real-start-worker-drain", timeout_ms, {
                "mission_id": mission_id, "succeeds": succeeds, "worker_done": worker.done,
                "active_threads": pool.activeThreadCount(),
            })
        assert worker.done and worker.result is not None
        assert worker.result[0] is succeeds
        assert any(value is worker for value in gc.get_referents(pool))
        bridge._poll_start_workers()
        assert delivered == [(mission_id, *worker.result)]
        assert bridge._start_workers == {}
        assert not bridge._start_poll_timer.isActive()
        if succeeds:
            assert cockpit.mission_state() is MissionState.ACCEPTANCE_PENDING
            assert cockpit.starts() == 1
        else:
            assert worker.result == (False, "无法读取该需求，已保留现场。")
            assert not (root / ".auto-pm").exists()
        return worker, ref(bridge), ref(pool)
    except BaseException:
        if not pool.waitForDone(5_000):
            _exit_start_timeout(workspace, "exception-cleanup-drain", 5_000, {
                "mission_id": mission_id, "active_threads": pool.activeThreadCount(),
                "exception_type": type(sys.exception()).__name__,
            })
        _delete_qobject(bridge)
        _delete_qobject(pool)
        raise


@pytest.mark.parametrize("succeeds", [False, True], ids=["missing-mission", "verified-run"])
def test_real_start_worker_does_not_retain_its_gui_owner(
    qapp: QApplication, tmp_path: Path, succeeds: bool
) -> None:
    """A completed runnable may remain retained; its GUI owner must not."""
    _assert_gui_thread(qapp)
    events: list[tuple[str, int]] = []
    worker, bridge_ref, pool_ref = _real_start_owner_refs(tmp_path, succeeds, events)
    try:
        assert worker.done
        assert bridge_ref() is None, "Completed real-pool worker retained its GUI bridge"
        assert pool_ref() is None
        assert events == [("bridge", get_native_id()), ("start_timer", get_native_id())]
    finally:
        # Keep old-code negative controls safe inside pytest, without masking the assertion.
        bridge = bridge_ref()
        if bridge is not None:
            _delete_qobject(bridge)
        pool = pool_ref()
        if pool is not None:
            _delete_qobject(pool)


def _probe_real_start_background_gc(root: Path) -> None:
    """Child-only real cycle probe; never add a self-cycle or alter GC policy."""
    app = QApplication([])
    app.processEvents()
    gui = get_native_id()
    events: list[tuple[str, int]] = []
    collector_ids: list[int] = []

    def collect() -> None:
        collector_ids.append(get_native_id())
        gc.collect()

    collector = Thread(target=collect, daemon=True)
    worker, bridge_ref, pool_ref = _real_start_owner_refs(root, False, events)
    del worker
    before = list(events)
    collector.start()
    collector.join(3)
    if collector.is_alive():
        _exit_start_timeout(root, "background-gc-join", 3_000, {"collector_ids": collector_ids})
    print(json.dumps({
        "gui": gui, "collector": collector_ids, "before_gc": before,
        "after_gc": events, "bridge_alive": bridge_ref() is not None,
        "pool_alive": pool_ref() is not None,
    }), flush=True)
    assert before == [("bridge", gui), ("start_timer", gui)], "GUI owner outlived its locals"
    assert events == before and collector_ids[0] != gui
    assert bridge_ref() is None and pool_ref() is None
    if os.name == "nt":
        post = ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW
        post.argtypes = [ctypes.c_ulong, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        post.restype = ctypes.c_int
        assert post(gui, 0, 0, 0), ctypes.get_last_error()
    app.processEvents()
    print("PM_START_NATIVE_PUMP_SURVIVED", flush=True)


def test_real_start_background_gc_never_destroys_gui_objects(
    tmp_path: Path, record_property: Callable[[str, object], None]
) -> None:
    """Isolate the native event pump and reap only this test's process tree on timeout."""
    argv = [
        sys.executable, "-B", "-X", "utf8", "-c",
        "from pathlib import Path; import sys; "
        "from tests.qml.test_pm_cockpit_bridge import _probe_real_start_background_gc; "
        "_probe_real_start_background_gc(Path(sys.argv[1]))",
        str(tmp_path),
    ]
    child = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    record_property("lifecycle_child_argv", json.dumps(argv))
    record_property("lifecycle_child_pid", child.pid)
    try:
        stdout, stderr = child.communicate(timeout=20)
    except subprocess.TimeoutExpired as error:
        if os.name == "nt":
            killed = subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            )
            record_property("lifecycle_child_taskkill_exit", killed.returncode)
        else:
            child.kill()
        stdout, stderr = child.communicate(timeout=5)
        raise AssertionError(
            f"PM lifecycle child timed out; pid={child.pid}, exit={child.returncode}\n{stdout}\n{stderr}"
        ) from error
    record_property("lifecycle_child_exit", child.returncode)
    record_property("lifecycle_child_stdout", stdout)
    record_property("lifecycle_child_stderr", stderr)
    assert child.returncode == 0, f"exit={child.returncode}\n{stdout}\n{stderr}"
    assert "PM_START_NATIVE_PUMP_SURVIVED" in stdout


def test_start_watchdog_leaves_at_least_eight_times_the_normal_runtime() -> None:
    """TD-SW008-135：正常 75 秒的用例，看门狗余量不再只有 2.4 倍。"""
    assert _start_watchdog_ms(True, {}) >= 8 * 75_000
    assert _start_watchdog_ms(False, {}) == 5_000


def test_start_watchdog_scale_can_only_widen_the_limit() -> None:
    assert _start_watchdog_ms(True, {_WATCHDOG_SCALE_ENV: "2"}) == 2 * _start_watchdog_ms(True, {})
    assert _start_watchdog_ms(True, {_WATCHDOG_SCALE_ENV: "0.1"}) == _start_watchdog_ms(True, {})
    assert _start_watchdog_ms(True, {_WATCHDOG_SCALE_ENV: "abc"}) == _start_watchdog_ms(True, {})


def test_start_timeout_log_carries_machine_load_and_a_hint() -> None:
    facts = _load_facts()
    assert facts["cpu_count"] == os.cpu_count()
    assert _WATCHDOG_SCALE_ENV in str(facts["hint"]) and "负载" in str(facts["hint"])
    if hasattr(os, "getloadavg"):
        load = facts["load_average"]
        assert isinstance(load, tuple) and len(load) == 3
