"""Contract tests for the bounded, non-technical PM cockpit surface."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_pm.contracts.execution_adapter import (
    ExecutionActivityStage,
    ExecutionFailureCode,
)
from auto_pm.contracts.pm_cockpit import (
    CockpitUserAction,
    PmCockpitActivity,
    PmCockpitCompletion,
    PmCockpitCompletionState,
    PmCockpitEvidence,
    PmCockpitEvidenceCurrency,
    PmCockpitFocus,
    PmCockpitProjectCard,
    PmCockpitResume,
    PmCockpitResumeState,
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


def _legacy_evidence_payload() -> dict[str, object]:
    """An evidence payload exactly as produced before U05 (no focus/currency/resume)."""
    return {
        "schema_version": "pm-cockpit-evidence.v1",
        "project_id": "SW-2026-008",
        "decision_id": "DEC-20260910-1B4F38FD",
        "change_id": "CHG-SCPT-2026-207",
        "read_set": ["SYS-2026-001_WorkspaceGovernance/workspace_registry.json"],
        "work_graph": [],
        "checkpoints": [
            {
                "checkpoint_id": "CP-001",
                "summary": "已建立只读证据投影。",
                "evidence": ["pytest: focused pass"],
                "created_at": "2026-09-30T00:00:00+00:00",
            }
        ],
        "verification_evidence": ["pytest: focused pass"],
        "status_note": "只读。",
    }


def test_legacy_evidence_payload_still_validates_with_safe_defaults() -> None:
    evidence = PmCockpitEvidence.model_validate(_legacy_evidence_payload())

    assert evidence.focus == PmCockpitFocus()
    assert evidence.evidence_currency is PmCockpitEvidenceCurrency.NOT_APPLICABLE
    assert evidence.evidence_currency_reason == ""
    assert evidence.resume == PmCockpitResume()
    assert evidence.resume.state is PmCockpitResumeState.NO_ACTIVE_WORK
    assert evidence.resume.user_action is CockpitUserAction.NONE
    checkpoint = evidence.checkpoints[0]
    assert (checkpoint.run_id, checkpoint.is_current_run) == ("", False)
    assert evidence.schema_version == "pm-cockpit-evidence.v1"


def test_u05_enums_expose_exactly_the_agreed_values() -> None:
    assert {item.value for item in PmCockpitEvidenceCurrency} == {
        "CURRENT",
        "NOT_CURRENT",
        "NOT_APPLICABLE",
    }
    assert {item.value for item in PmCockpitResumeState} == {
        "NO_ACTIVE_WORK",
        "WAITING_FOR_USER",
        "MONITORING",
        "NEEDS_REVIEW",
    }
    assert {item.value for item in CockpitUserAction} == {
        "NONE",
        "CONFIRM_START",
        "CONFIRM_ACCEPTANCE",
        "REVIEW_ESCALATION",
        "RETRY_SYNC",
    }


def test_focus_and_resume_are_frozen_value_objects() -> None:
    focus = PmCockpitFocus(
        mission_id="MISSION-001", work_id="WORK-001", run_id="RUN-001", run_state="执行中"
    )
    resume = PmCockpitResume(
        state=PmCockpitResumeState.WAITING_FOR_USER,
        user_action=CockpitUserAction.CONFIRM_START,
        reason="等待您确认开工。",
    )

    assert PmCockpitFocus.model_config.get("frozen") is True
    assert PmCockpitResume.model_config.get("frozen") is True
    assert hash(focus) == hash(PmCockpitFocus.model_validate(focus.model_dump()))
    assert focus == PmCockpitFocus.model_validate(focus.model_dump())
    assert resume == PmCockpitResume.model_validate(resume.model_dump(mode="json"))


def test_resume_reason_is_bounded_and_unknown_values_are_rejected() -> None:
    PmCockpitResume(reason="x" * 200)
    with pytest.raises(ValidationError):
        PmCockpitResume(reason="x" * 201)
    with pytest.raises(ValidationError):
        PmCockpitEvidence.model_validate(
            {**_legacy_evidence_payload(), "evidence_currency_reason": "x" * 201}
        )
    with pytest.raises(ValidationError):
        PmCockpitEvidence.model_validate(
            {**_legacy_evidence_payload(), "evidence_currency": "MAYBE"}
        )
    with pytest.raises(ValidationError):
        PmCockpitResume.model_validate({"state": "RESTART_NOW"})


def test_u05_fields_keep_the_evidence_contract_free_of_lease_and_token_data() -> None:
    evidence = PmCockpitEvidence.model_validate(
        {
            **_legacy_evidence_payload(),
            "focus": {
                "mission_id": "MISSION-001",
                "work_id": "WORK-001",
                "run_id": "RUN-001",
                "run_state": "验证中",
            },
            "evidence_currency": "NOT_CURRENT",
            "evidence_currency_reason": "最新 Checkpoint 未证明当前通过的质量证据",
            "resume": {
                "state": "NEEDS_REVIEW",
                "user_action": "REVIEW_ESCALATION",
                "reason": "验收证据不能确认：最新 Checkpoint 未证明当前通过的质量证据",
            },
        }
    )

    dumped = evidence.model_dump(mode="json")
    assert dumped["focus"]["run_id"] == "RUN-001"
    assert dumped["evidence_currency"] == "NOT_CURRENT"
    assert dumped["resume"]["user_action"] == "REVIEW_ESCALATION"
    serialized = evidence.model_dump_json().lower()
    assert "lease" not in serialized
    assert "token" not in serialized


def test_legacy_project_card_payload_validates_with_not_started_completion() -> None:
    card = PmCockpitProjectCard.model_validate(
        {
            "project_id": "SW-2026-008",
            "project_name": "自动化项目管理工具",
            "mission": "A4",
            "milestone": "系统执行",
            "progress": "执行中",
            "blocked": False,
            "verification": "等待执行验证",
            "risk": "低：在既定授权范围内",
            "current_owner": "PM",
            "next_user_action": "无需操作",
        }
    )

    assert card.completion_state is PmCockpitCompletionState.NOT_STARTED
    assert card.completion_note == ""
    assert card.user_action is CockpitUserAction.NONE


def test_completion_states_and_retry_action_are_exactly_the_agreed_values() -> None:
    assert {item.value for item in PmCockpitCompletionState} == {
        "NOT_STARTED",
        "PENDING_SYNC",
        "COMPLETED",
    }
    assert CockpitUserAction.RETRY_SYNC.value == "RETRY_SYNC"


def test_completion_result_is_a_frozen_bounded_secret_free_value_object() -> None:
    completion = PmCockpitCompletion(
        mission_id="MISSION-001",
        state=PmCockpitCompletionState.PENDING_SYNC,
        message="台账同步未完成，已保留现场；可稍后重试。",
    )

    assert PmCockpitCompletion.model_config.get("frozen") is True
    assert completion == PmCockpitCompletion.model_validate(completion.model_dump(mode="json"))
    serialized = completion.model_dump_json().lower()
    assert "lease" not in serialized and "token" not in serialized
    with pytest.raises(ValidationError):
        PmCockpitCompletion(
            mission_id="MISSION-001", state=PmCockpitCompletionState.COMPLETED, message="x" * 201
        )
    with pytest.raises(ValidationError):
        PmCockpitCompletion(mission_id="", state=PmCockpitCompletionState.COMPLETED)
    with pytest.raises(ValidationError):
        PmCockpitCompletion.model_validate({"mission_id": "M-1", "state": "DONE"})


def test_completion_note_on_a_card_is_bounded() -> None:
    base = {
        "project_id": "SW-2026-008",
        "project_name": "x",
        "mission": "m",
        "milestone": "m",
        "progress": "p",
        "blocked": False,
        "verification": "v",
        "risk": "r",
        "current_owner": "o",
        "next_user_action": "n",
    }
    PmCockpitProjectCard.model_validate({**base, "completion_note": "x" * 200})
    with pytest.raises(ValidationError):
        PmCockpitProjectCard.model_validate({**base, "completion_note": "x" * 201})
