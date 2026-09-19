"""Failure-boundary tests for E03B startup evidence supervision."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from auto_pm.core.continuity_execution_service import ContinuityExecutionError
from auto_pm.core.execution_supervisor_service import (
    ExecutionSupervisorError,
    ExecutionSupervisorService,
    LeaseCapability,
)

from auto_pm.contracts.continuity import LeaseRenewalReceipt, RunState
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


def test_supervisor_renews_due_capability_without_exposing_secret(tmp_path) -> None:
    execution = Mock()
    supervisor = ExecutionSupervisorService(tmp_path, execution=execution)
    now = datetime.now(UTC)
    capability = LeaseCapability(
        run_id="RUN-E04-001",
        owner_id="codex:agent-a",
        version=3,
        expires_at=now + timedelta(seconds=20),
        token="must-not-leak",
    )
    receipt = LeaseRenewalReceipt(
        run_id=capability.run_id,
        owner_id=capability.owner_id,
        expires_at=(now + timedelta(minutes=15)).isoformat(),
        version=4,
        updated_at=now.isoformat(),
    )
    execution.renew_lease.return_value = receipt

    outcome = supervisor.renew_if_due(
        capability,
        lease_seconds=900,
        renew_before_seconds=30,
        idempotency_key="e04-renew-1",
        now=now,
    )

    assert outcome.receipt is receipt
    assert outcome.capability.version == 4
    assert outcome.capability.expires_at.isoformat() == receipt.expires_at
    assert "must-not-leak" not in repr(outcome)
    execution.renew_lease.assert_called_once_with(
        "RUN-E04-001",
        "codex:agent-a",
        "must-not-leak",
        900,
        "e04-renew-1",
        expected_version=3,
    )
    next_now = outcome.capability.expires_at - timedelta(seconds=20)
    second_receipt = LeaseRenewalReceipt(
        run_id=capability.run_id,
        owner_id=capability.owner_id,
        expires_at=(next_now + timedelta(minutes=15)).isoformat(),
        version=5,
        updated_at=next_now.isoformat(),
    )
    execution.renew_lease.return_value = second_receipt

    second = supervisor.renew_if_due(
        outcome.capability,
        lease_seconds=900,
        renew_before_seconds=30,
        idempotency_key="e04-renew-2",
        now=next_now,
    )

    assert second.receipt is second_receipt
    assert second.capability.version == 5
    assert execution.renew_lease.call_args_list[-1].kwargs == {"expected_version": 4}
    assert "must-not-leak" not in repr(capability)


def test_supervisor_skips_early_renewal_and_redacts_failures(tmp_path) -> None:
    execution = Mock()
    supervisor = ExecutionSupervisorService(tmp_path, execution=execution)
    now = datetime.now(UTC)
    capability = LeaseCapability(
        run_id="RUN-E04-001",
        owner_id="codex:agent-a",
        version=3,
        expires_at=now + timedelta(minutes=10),
        token="must-not-leak",
    )
    early = supervisor.renew_if_due(
        capability,
        lease_seconds=900,
        renew_before_seconds=30,
        idempotency_key="e04-renew-early",
        now=now,
    )
    assert early.capability is capability
    assert early.receipt is None
    execution.renew_lease.assert_not_called()

    execution.renew_lease.side_effect = ContinuityExecutionError("must-not-leak")
    near_expiry = LeaseCapability(
        run_id=capability.run_id,
        owner_id=capability.owner_id,
        version=capability.version,
        expires_at=now,
        token="must-not-leak",
    )
    with pytest.raises(ExecutionSupervisorError, match="自动续租失败") as raised:
        supervisor.renew_if_due(
            near_expiry,
            lease_seconds=900,
            renew_before_seconds=30,
            idempotency_key="e04-renew-fail",
            now=now,
        )
    assert "must-not-leak" not in str(raised.value)


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
