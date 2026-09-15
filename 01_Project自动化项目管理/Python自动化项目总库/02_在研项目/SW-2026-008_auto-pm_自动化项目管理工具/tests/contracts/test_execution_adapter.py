"""Contract tests for provider-neutral, secret-free execution receipts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ExecutionDispatchReceipt,
    ExecutionIntent,
    ExecutionRole,
    WorktreeMode,
    execution_role_for_stack,
)


def _receipt(**overrides: object) -> ExecutionDispatchReceipt:
    values: dict[str, object] = {
        "mission_id": "MISSION-SW008-A5-001",
        "work_id": "WORK-SW008-A5-001",
        "run_id": "RUN-SW008-A5-001",
        "subject_project_id": "SW-2026-008",
        "adapter": ExecutionAdapterKind.CODEX,
        "executor_id": "agent-a",
        "owner_id": "codex:agent-a",
        "role": ExecutionRole.FULLSTACK_ENGINEER,
        "worktree_mode": WorktreeMode.ISOLATED,
        "worktree_path": "C:/workspace/.auto-pm/worktrees/run-sw008-a5-001",
        "branch_name": "codex/run-sw008-a5-001",
        "git_head": "a" * 40,
        "owned_paths": ("README.md",),
    }
    values.update(overrides)
    return ExecutionDispatchReceipt.model_validate(values)


@pytest.mark.parametrize(
    ("stack", "role"),
    [
        ("python", ExecutionRole.FULLSTACK_ENGINEER),
        ("PLC", ExecutionRole.PLC_ELECTRICAL_ENGINEER),
    ],
)
def test_execution_role_is_resolved_only_from_registered_stack(
    stack: str, role: ExecutionRole
) -> None:
    assert execution_role_for_stack(stack) is role


def test_execution_role_rejects_unknown_stack() -> None:
    with pytest.raises(ValueError, match="未登记"):
        execution_role_for_stack("qml")


def test_receipt_is_canonical_and_contains_no_lease_capability() -> None:
    receipt = _receipt()

    payload = receipt.model_dump(mode="json")
    assert payload["status"] == "PREPARED"
    assert payload["owner_id"] == "codex:agent-a"
    assert "lease_token" not in payload
    with pytest.raises(ValidationError, match="Extra inputs"):
        ExecutionDispatchReceipt.model_validate({**payload, "lease_token": "must-not-leak"})


def test_receipt_rejects_ambiguous_owner_or_worktree() -> None:
    with pytest.raises(ValidationError, match="canonical"):
        _receipt(owner_id="agent-a")
    with pytest.raises(ValidationError, match="CURRENT"):
        _receipt(worktree_mode=WorktreeMode.CURRENT)
    with pytest.raises(ValidationError, match="ISOLATED"):
        _receipt(branch_name="")


def _intent(**overrides: object) -> ExecutionIntent:
    values: dict[str, object] = {
        "operation_id": "OP-E02-001",
        "request_sha256": "a" * 64,
        "receipt": _receipt(),
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return ExecutionIntent.model_validate(values)


def test_execution_intent_is_immutable_and_explicitly_unstarted() -> None:
    intent = _intent()
    assert ExecutionIntent.model_validate_json(intent.model_dump_json()) == intent
    assert intent.status == intent.receipt.status == "PREPARED"
    assert {"pid", "session_id", "started_at", "lease_token"}.isdisjoint(
        intent.model_dump()
    )
    with pytest.raises(ValidationError, match="frozen"):
        intent.operation_id = "another-operation"


@pytest.mark.parametrize("value", ["", " ", " leading", "trailing ", "line\nbreak", "a" * 256])
def test_execution_intent_rejects_ambiguous_operation_id(value: str) -> None:
    with pytest.raises(ValidationError):
        _intent(operation_id=value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "RUNNING"},
        {"pid": 123},
        {"session_id": "unconfirmed"},
        {"started_at": "2026-09-15T00:00:00Z"},
        {"lease_token": "secret"},
        {"request_sha256": "not-a-digest"},
        {"created_at": "2026-09-15T00:00:00"},
    ],
)
def test_execution_intent_rejects_started_claims_and_invalid_evidence(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _intent(**overrides)
