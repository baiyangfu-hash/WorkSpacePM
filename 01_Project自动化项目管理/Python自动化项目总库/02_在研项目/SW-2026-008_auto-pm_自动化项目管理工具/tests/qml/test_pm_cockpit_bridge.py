"""Bridge coverage for the no-write default cockpit path."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Literal, cast

from auto_pm.core.pm_cockpit_service import PmCockpitError, PmCockpitService
from PySide6.QtCore import QRunnable, QThreadPool

from auto_pm.contracts.execution_adapter import ForegroundExecutionReceipt
from auto_pm.contracts.pm_cockpit import PmCockpitSnapshot
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.qml.bridges.pm_cockpit_bridge import PmCockpitBridge


class _HoldingThreadPool:
    def __init__(self) -> None:
        self.worker: QRunnable | None = None

    def start(self, worker: QRunnable, priority: int = 0) -> None:
        del priority
        self.worker = worker


class _StartService:
    def __init__(self, outcomes: list[ForegroundExecutionReceipt | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def start_execution(self, mission_id: str) -> ForegroundExecutionReceipt:
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
) -> ForegroundExecutionReceipt:
    common: dict[str, object] = {
        "operation_id": f"OP-{status}",
        "run_id": f"RUN-{status}",
        "status": status,
        "claim_sha256": "a" * 64,
    }
    if status == "VERIFYING":
        common.update({
            "process_id": 1234,
            "session_id": "SESSION-1",
            "exit_code": 0,
            "projection_sha256": "b" * 64,
        })
    return ForegroundExecutionReceipt.model_validate(common)


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
    _git_root(tmp_path)
    store = ContinuityStore(tmp_path)
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    bridge = PmCockpitBridge(str(tmp_path))
    first = bridge.createPlanningDraft(
        "DJ-2026-005", " Improve line throughput ", "Measure cycle time\nNo safety bypass"
    )
    replay = bridge.createPlanningDraft(
        "DJ-2026-005", "Improve line throughput", "Measure cycle time\nNo safety bypass"
    )
    changed = bridge.createPlanningDraft(
        "DJ-2026-005", "Improve quality", "Measure cycle time\nNo safety bypass"
    )
    new_session = PmCockpitBridge(str(tmp_path)).createPlanningDraft(
        "DJ-2026-005", "Improve line throughput", "Measure cycle time\nNo safety bypass"
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
        result = bridge.createPlanningDraft(project, objective, acceptance)
        assert result["success"] is False
        assert "draft" not in result

    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0] == 0


def test_start_execution_is_one_shot_until_worker_finishes(tmp_path: Path) -> None:
    service = _StartService([_receipt("VERIFYING"), _receipt("VERIFYING")])
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, pool),
    )
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
    assert finished == [("MISSION-001", True, "任务已启动，正在验证。")]
    assert bridge.startExecution("MISSION-001")["accepted"] is True


def test_start_execution_failure_clears_busy_without_false_success(tmp_path: Path) -> None:
    service = _StartService([PmCockpitError("授权已失效"), _receipt("PENDING")])
    pool = _HoldingThreadPool()
    bridge = PmCockpitBridge(
        str(tmp_path),
        service=cast(PmCockpitService, service),
        thread_pool=cast(QThreadPool, pool),
    )
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
