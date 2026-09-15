"""Failure-boundary tests for E03B startup evidence supervision."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from auto_pm.core.continuity_execution_service import ContinuityExecutionError
from auto_pm.core.execution_supervisor_service import (
    ExecutionSupervisorError,
    ExecutionSupervisorService,
)

from auto_pm.contracts.continuity import RunState
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence


def _evidence() -> ExecutionStartEvidence:
    return ExecutionStartEvidence(
        process_id=1234,
        session_id="thread-supervisor-test",
        started_at=datetime.now(UTC),
    )


def test_supervisor_maps_only_trusted_evidence_without_reaping(tmp_path) -> None:
    execution = Mock()
    expected = Mock()
    execution.record_start_evidence.return_value = expected
    supervisor = ExecutionSupervisorService(tmp_path, execution=execution)
    reaper = Mock()

    actual = supervisor.record_started(
        run_id="RUN-E03B-001",
        owner_id="codex:agent-a",
        lease_token="secret-token",
        evidence=_evidence(),
        idempotency_key="start-evidence-1",
        reap_current=reaper,
    )

    assert actual is expected
    reaper.assert_not_called()
    execution.record_start_evidence.assert_called_once()


def test_supervisor_reaps_before_retry_when_evidence_persistence_fails(tmp_path) -> None:
    execution = Mock()
    execution.record_start_evidence.side_effect = ContinuityExecutionError("disk failure")
    supervisor = ExecutionSupervisorService(tmp_path, execution=execution)
    reaper = Mock()

    with pytest.raises(ExecutionSupervisorError, match="已回收") as raised:
        supervisor.record_started(
            run_id="RUN-E03B-001",
            owner_id="codex:agent-a",
            lease_token="secret-token",
            evidence=_evidence(),
            idempotency_key="start-evidence-2",
            reap_current=reaper,
        )

    reaper.assert_called_once()
    execution.transition_run.assert_not_called()
    assert "secret-token" not in str(raised.value)


def test_supervisor_blocks_when_current_child_cannot_be_reaped(tmp_path) -> None:
    execution = Mock()
    execution.record_start_evidence.side_effect = ContinuityExecutionError("disk failure")
    supervisor = ExecutionSupervisorService(tmp_path, execution=execution)
    reaper = Mock(side_effect=RuntimeError("reaper failure"))

    with pytest.raises(ExecutionSupervisorError, match="BLOCKED") as raised:
        supervisor.record_started(
            run_id="RUN-E03B-001",
            owner_id="codex:agent-a",
            lease_token="secret-token",
            evidence=_evidence(),
            idempotency_key="start-evidence-3",
            reap_current=reaper,
        )

    execution.transition_run.assert_called_once_with(
        "RUN-E03B-001",
        RunState.BLOCKED,
        "codex:agent-a",
        "secret-token",
        "execution-start-blocked:4dd5e426e5e434186aa3dca46edec73cb6420feb874d0ad3a70fce972653e876",
    )
    assert "secret-token" not in str(raised.value)
