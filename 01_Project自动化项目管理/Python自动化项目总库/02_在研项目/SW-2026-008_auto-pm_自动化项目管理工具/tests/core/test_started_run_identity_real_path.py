"""TD-SW008-075: the started-Run identity checks proved on a really dispatched Run, not on hand-made objects.

The dispatch adapter records the Run owner as ``<adapter>:<executor>`` (the receipt's ``owner_id``) while the receipt keeps the
bare ``executor_id`` too.  A test that builds both sides by hand can make them equal and hide a comparison on the wrong field
(V04 found exactly that in ``resolve_started_run``).  These tests go through the real dispatch, the real start claim and the
real store, then check what the later readers see.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.execution_supervisor_service import (
    ExecutionSupervisorError,
    ExecutionSupervisorService,
)
from auto_pm.application.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_local_execution_orchestrator import (
    _LEASE_ENV,
    _LEASE_TOKEN,
    _CountingExecutor,
    _helper_code,
    _inputs,
)


@pytest.fixture
def started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    operation_id = "OP-TD075-REAL"
    dispatch, microtask = _inputs(tmp_path, operation_id)
    monkeypatch.setenv(_LEASE_ENV, _LEASE_TOKEN)
    LocalExecutionOrchestrator(
        tmp_path, executor=_CountingExecutor(_helper_code("td075\n"))
    ).execute(
        dispatch=dispatch,
        microtask=microtask,
        lease_token_environment=_LEASE_ENV,
        renewal_interval_seconds=0.05,
    )
    return tmp_path, operation_id, dispatch.receipt


def test_a_really_dispatched_run_carries_the_receipt_owner_not_the_bare_executor(started) -> None:
    root, _operation, receipt = started
    store = ContinuityStore(root)
    run = store.get_run(receipt.run_id)
    # The shape the hand-made tests used to hide: the two ids differ on a real Run.
    assert receipt.executor_id != receipt.owner_id
    assert run.executor_id == receipt.owner_id == f"{receipt.adapter.value}:{receipt.executor_id}"
    assert store.get_lease(receipt.run_id).owner_id == receipt.owner_id
    assert store.get_run_started_evidence(receipt.run_id)[0] == receipt.owner_id


def test_resolve_started_run_accepts_the_real_run_and_refuses_a_bare_executor_owner(
    started,
) -> None:
    root, operation_id, receipt = started
    resolved_receipt, run, evidence = ContinuityExecutionService(root).resolve_started_run(
        operation_id
    )
    assert resolved_receipt.owner_id == receipt.owner_id and run.run_id == receipt.run_id
    assert evidence.session_id

    # Counter-example: the Run records the bare executor (what a hand-made fixture would do); the real reader must refuse it.
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn, conn:
        conn.execute(
            "UPDATE run_items SET executor_id=? WHERE run_id=?",
            (receipt.executor_id, receipt.run_id),
        )
    with pytest.raises(ContinuityExecutionError, match="身份不一致"):
        ContinuityExecutionService(root).resolve_started_run(operation_id)


def test_supervisor_recovers_the_real_session_and_blocks_a_different_one(started) -> None:
    root, operation_id, _receipt = started
    _, _, evidence = ContinuityExecutionService(root).resolve_started_run(operation_id)
    supervisor = ExecutionSupervisorService(root)

    got = supervisor.recover_started_session(
        operation_id,
        observed_process_id=evidence.process_id,
        observed_session_id=evidence.session_id,
        observed_started_at=evidence.started_at,
        is_process_alive=lambda pid: pid == evidence.process_id,
    )
    assert got == evidence
    with pytest.raises(ExecutionSupervisorError, match="BLOCKED"):
        supervisor.recover_started_session(
            operation_id,
            observed_process_id=evidence.process_id,
            observed_session_id="another-session",
            observed_started_at=evidence.started_at,
            is_process_alive=lambda _pid: True,
        )
