"""Contract tests for the bounded, non-technical PM cockpit surface."""

from __future__ import annotations

from auto_pm.contracts.execution_adapter import (
    ExecutionActivityStage,
    ExecutionFailureCode,
)
from auto_pm.contracts.pm_cockpit import (
    CockpitUserAction,
    PmCockpitActivity,
    PmCockpitEvidence,
    PmCockpitProjectCard,
    PmCockpitSnapshot,
)


def test_project_card_contains_the_user_decision_fields() -> None:
    card = PmCockpitProjectCard(
        project_id="SW-2026-008",
        project_name="自动化项目管理工具",
        mission="A4 老板驾驶舱",
        milestone="等待开工确认",
        progress="需求准备",
        blocked=False,
        verification="尚无验证结论",
        risk="低：在既定授权范围内",
        current_owner="驾驶舱待命",
        next_user_action="确认开始执行",
        user_action=CockpitUserAction.CONFIRM_START,
    )

    payload = card.model_dump(mode="json")
    assert {
        "project_name",
        "mission",
        "milestone",
        "progress",
        "blocked",
        "verification",
        "risk",
        "current_owner",
        "next_user_action",
    }.issubset(payload)


def test_evidence_contract_has_no_execution_lease_field() -> None:
    evidence = PmCockpitEvidence(
        project_id="SW-2026-008",
        read_set=("SYS-2026-001_WorkspaceGovernance/workspace_registry.json",),
        work_graph=(),
        checkpoints=(),
        verification_evidence=(),
        status_note="只读。",
    )

    payload = evidence.model_dump_json().lower()
    assert "lease" not in payload
    assert "token" not in payload


def test_snapshot_activity_is_canonical_and_secret_free() -> None:
    activity = PmCockpitActivity(
        project_id="SW-2026-008",
        mission_id="MISSION-001",
        work_id="WORK-001",
        run_id="RUN-001",
        operation_id="OP-001",
        stage=ExecutionActivityStage.FAILED,
        title="执行失败",
        description="历史原因未记录",
        occurred_at="2026-09-28T00:00:00+00:00",
        tone="error",
        failure_code=ExecutionFailureCode.LEGACY_UNKNOWN,
    )
    snapshot = PmCockpitSnapshot(projects=(), activities=(activity,))

    payload = snapshot.model_dump(mode="json")
    assert payload["activities"][0]["stage"] == "FAILED"
    assert payload["activities"][0]["failure_code"] == "LEGACY_UNKNOWN"
    serialized = snapshot.model_dump_json().lower()
    assert "lease" not in serialized
    assert "token" not in serialized
    assert "stdout" not in serialized
