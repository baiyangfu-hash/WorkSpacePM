"""Contract tests for provider-neutral, secret-free execution receipts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ExecutionDispatchReceipt,
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
