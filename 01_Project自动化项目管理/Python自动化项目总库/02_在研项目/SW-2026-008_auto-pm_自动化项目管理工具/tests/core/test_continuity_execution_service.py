"""Run, checkpoint, lease, and handoff v2 failure-injection tests."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import RunState, WorkKind


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


def _services(root: Path, clock: Clock):
    work = WorkRegistryService(root, now=lambda: clock().isoformat())
    work.initialize("test")
    work.create_work(
        work_id="WORK-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Continuity",
        owner="architect",
        scope_paths=["auto_pm/core/a.py", "tests/test_a.py"],
        source_fingerprint="sha256:abc",
        idempotency_key="create-work",
        read_only=True,
    )
    return work, ContinuityExecutionService(root, now=clock)


def _start(service: ContinuityExecutionService, **changes):
    values = {
        "run_id": "RUN-001",
        "work_id": "WORK-001",
        "executor_id": "agent-a",
        "adapter": "codex",
        "owned_paths": ["auto_pm/core/a.py"],
        "declared_dirty_paths": ["auto_pm/core/a.py"],
        "observed_dirty_paths": ["auto_pm/core/a.py"],
        "git_head": "a" * 40,
        "worktree_path": "C:/workspace",
        "lease_token": "lease-secret",
        "lease_seconds": 900,
        "idempotency_key": "create-run",
    }
    values.update(changes)
    return service.start_run(**values)


def _checkpoint(service: ContinuityExecutionService, **changes):
    values = {
        "checkpoint_id": "CP-001",
        "run_id": "RUN-001",
        "owner_id": "agent-a",
        "lease_token": "lease-secret",
        "summary": "implemented",
        "git_head": "a" * 40,
        "dirty_paths": ["auto_pm/core/a.py"],
        "evidence": ["pytest:0"],
        "idempotency_key": "checkpoint-1",
    }
    values.update(changes)
    return service.checkpoint(**values)


def test_initializes_execution_tables_without_legacy_handoff_files(tmp_path: Path) -> None:
    clock = Clock()
    _services(tmp_path, clock)
    with sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db") as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"run_items", "execution_leases", "checkpoints", "handoffs_v2"} <= tables
    assert not (tmp_path / ".auto-pm" / "handoffs").exists()


def test_run_binds_work_owner_paths_git_and_lease(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)

    run = _start(service)
    lease = service._store.get_lease(run.run_id)

    assert run.state == RunState.RUNNING
    assert run.owned_paths == ("auto_pm/core/a.py",)
    assert lease.owner_id == "agent-a"
    assert datetime.fromisoformat(lease.expires_at) > clock()


def test_run_rejects_undeclared_dirty_and_out_of_scope_paths(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)

    with pytest.raises(ContinuityExecutionError, match="未声明"):
        _start(service, observed_dirty_paths=["tests/test_a.py"])
    with pytest.raises(ContinuityExecutionError, match="Work scope"):
        _start(
            service,
            run_id="RUN-002",
            idempotency_key="create-run-2",
            owned_paths=["outside.py"],
            observed_dirty_paths=[],
        )


def test_expired_or_wrong_owner_lease_fails_closed(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, lease_seconds=60)

    with pytest.raises(ContinuityExecutionError, match="ownership"):
        service.renew_lease("RUN-001", "agent-b", "lease-secret", 60, "wrong-owner")
    clock.value += timedelta(seconds=61)
    with pytest.raises(ContinuityExecutionError, match="过期"):
        service.renew_lease("RUN-001", "agent-a", "lease-secret", 60, "expired")


def test_checkpoint_is_sequenced_and_rejects_baseline_drift(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)

    first = _checkpoint(service)
    second = _checkpoint(
        service,
        checkpoint_id="CP-002",
        idempotency_key="checkpoint-2",
        evidence=["ruff:0"],
    )

    assert (first.sequence, second.sequence) == (1, 2)
    with pytest.raises(ContinuityExecutionError, match="baseline drift"):
        _checkpoint(
            service,
            checkpoint_id="CP-003",
            idempotency_key="checkpoint-3",
            git_head="b" * 40,
        )


def test_checkpoint_allows_new_owned_changes_and_rejects_foreign_paths(tmp_path: Path) -> None:
    """A clean Run may create owned changes; foreign paths remain fail-closed."""
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service, declared_dirty_paths=[], observed_dirty_paths=[])

    checkpoint = _checkpoint(service)

    assert checkpoint.dirty_paths == ("auto_pm/core/a.py",)
    with pytest.raises(ContinuityExecutionError, match="owned_paths"):
        _checkpoint(
            service,
            checkpoint_id="CP-002",
            dirty_paths=["tests/test_a.py"],
            idempotency_key="checkpoint-foreign-path",
        )


def test_handoff_v2_points_to_checkpoint_and_is_hash_signed(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)
    checkpoint = _checkpoint(service)

    handoff = service.create_handoff(
        handoff_id="HO-001",
        checkpoint_id=checkpoint.checkpoint_id,
        from_owner="agent-a",
        to_owner="agent-b",
        lease_token="lease-secret",
        idempotency_key="handoff-1",
    )

    assert handoff.schema_version == "handoff.v2"
    assert handoff.checkpoint_id == "CP-001"
    assert len(handoff.snapshot_hash) == 64
    assert not (tmp_path / ".auto-pm" / "handoffs").exists()

    lease = service.accept_handoff(
        handoff_id="HO-001",
        receiver_id="agent-b",
        new_lease_token="receiver-secret",
        lease_seconds=900,
        idempotency_key="accept-1",
    )
    assert lease.owner_id == "agent-b"
    with pytest.raises(ContinuityExecutionError, match="ownership"):
        service.renew_lease("RUN-001", "agent-a", "lease-secret", 900, "old-owner")


def test_legacy_handoff_is_read_only_and_unknown_schema_is_rejected(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"schema_version": "handoff.v1", "request_id": "OLD"}), encoding="utf-8")

    loaded = service.load_legacy_handoff(old)
    assert loaded["compatibility"] == "READ_ONLY"
    old.write_text(json.dumps({"schema_version": "handoff.v9"}), encoding="utf-8")
    with pytest.raises(ContinuityExecutionError, match="未知"):
        service.load_legacy_handoff(old)


def test_run_state_machine_rejects_terminal_reopen(tmp_path: Path) -> None:
    clock = Clock()
    _, service = _services(tmp_path, clock)
    _start(service)
    service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "verify")
    service.transition_run("RUN-001", RunState.SUCCEEDED, "agent-a", "lease-secret", "succeed")

    with pytest.raises(ContinuityExecutionError, match="非法"):
        service.transition_run("RUN-001", RunState.RUNNING, "agent-a", "lease-secret", "reopen")
