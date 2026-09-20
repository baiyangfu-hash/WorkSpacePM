"""Capability proofs for approved-path projection and append-only receipts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import auto_pm.core.microtask_projection_service as projection_module
import pytest
from auto_pm.core.execution_supervisor_service import ExecutionSupervisorService
from auto_pm.core.microtask_projection_service import (
    MicrotaskProjectionError,
    MicrotaskProjectionService,
)

from auto_pm.contracts.execution_adapter import (
    ExecutionProjectionFile,
    ExecutionStartEvidence,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_execution_adapter_service import PROJECT_PATH
from tests.core.test_execution_microtask_service import _prepared

_LEASE_TOKEN = "must-never-persist"


def _running_plan(root: Path, operation_id: str):
    dispatch = _prepared(root, operation_id=operation_id)
    materialized = dispatch.prepare_microtask(operation_id)
    store = ContinuityStore(root)
    run = store.get_run(materialized.plan.run_id)
    claim, created = store.claim_execution_start(
        operation_id=operation_id,
        run_id=run.run_id,
        expected_run_version=run.version,
        owner_id="codex:agent-a",
        lease_token=_LEASE_TOKEN,
        plan_request_sha256=materialized.plan.request_sha256,
        marker_sha256=materialized.plan.marker_sha256,
        repository_path=materialized.plan.repository_path,
        microtask_commit=materialized.commit,
    )
    assert created
    ExecutionSupervisorService(root).record_started(
        run_id=run.run_id,
        owner_id="codex:agent-a",
        lease_token=_LEASE_TOKEN,
        evidence=ExecutionStartEvidence(
            process_id=4321,
            session_id=f"thread-{operation_id}",
            started_at=datetime.now(UTC),
        ),
        idempotency_key=f"{operation_id}:started",
        reap_current=lambda: None,
    )
    return materialized, claim


def test_projection_cas_receipt_and_cold_replay_are_exact(tmp_path: Path) -> None:
    operation_id = "OP-E08CD-PROJECTION"
    materialized, _claim = _running_plan(tmp_path, operation_id)
    plan = materialized.plan
    source = Path(plan.repository_path) / PROJECT_PATH
    target = Path(plan.source_worktree_path) / PROJECT_PATH
    source.write_text("projected content\n", encoding="utf-8")

    service = MicrotaskProjectionService(tmp_path)
    first = service.project(operation_id, expected_source_commit=materialized.commit)
    assert target.read_text(encoding="utf-8") == "projected content\n"
    assert first.files[0].projected_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert "must-never-persist" not in first.model_dump_json()

    cold = MicrotaskProjectionService(tmp_path).project(
        operation_id, expected_source_commit=materialized.commit
    )
    assert cold == first


def test_mid_batch_replace_failure_rolls_back_and_proves_clean_baseline(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = "OP-E08CD-PROJECTION-ROLLBACK"
    materialized, _claim = _running_plan(tmp_path, operation_id)
    plan = materialized.plan
    target = Path(plan.source_worktree_path)
    # The project directory is identified by the approved path, not the worktree name.
    relative_paths = (PROJECT_PATH, f"{Path(PROJECT_PATH).parent.as_posix()}/.copier-answers.yml")
    prepared = []
    baseline_by_path: dict[Path, bytes] = {}
    for index, relative in enumerate(relative_paths, start=1):
        destination = target / relative
        baseline = destination.read_bytes()
        projected = f"projected-{index}\n".encode()
        baseline_by_path[destination] = baseline
        prepared.append(
            (
                destination,
                projected,
                baseline,
                destination.stat().st_mode,
                ExecutionProjectionFile(
                    path=relative,
                    baseline_sha256=hashlib.sha256(baseline).hexdigest(),
                    projected_sha256=hashlib.sha256(projected).hexdigest(),
                ),
            )
        )
    service = MicrotaskProjectionService(tmp_path)
    real_replace = projection_module.os.replace
    calls = 0

    def fail_second_replace(source, destination) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected mid-batch replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(projection_module.os, "replace", fail_second_replace)
    with pytest.raises(MicrotaskProjectionError, match="回滚到 clean baseline"):
        service._apply_batch_with_rollback(
            target,
            plan,
            prepared,
            tuple(item[4] for item in prepared),
        )
    assert calls >= 4
    assert all(path.read_bytes() == baseline for path, baseline in baseline_by_path.items())
    assert service._dirty_paths(target) == ()
    assert ContinuityStore(tmp_path).get_execution_projection(operation_id) is None


@pytest.mark.parametrize("damage", ["source-link", "candidate-drift", "marker"])
def test_projection_rejects_partial_or_linked_inputs_without_receipt(
    tmp_path: Path,
    damage: str,
) -> None:
    operation_id = f"OP-E08CD-PARTIAL-{damage.upper()}"
    materialized, _claim = _running_plan(tmp_path, operation_id)
    plan = materialized.plan
    source = Path(plan.repository_path) / PROJECT_PATH
    target = Path(plan.source_worktree_path) / PROJECT_PATH
    baseline = target.read_bytes()
    if damage == "source-link":
        source.unlink()
        try:
            source.symlink_to(Path(plan.repository_path) / ".codex-microtask.json")
        except OSError:
            pytest.skip("symlink creation is not available")
    elif damage == "candidate-drift":
        target.write_text("unapproved candidate drift\n", encoding="utf-8")
    else:
        (Path(plan.repository_path) / ".codex-microtask.json").write_text(
            "{}\n", encoding="utf-8"
        )

    with pytest.raises(MicrotaskProjectionError):
        MicrotaskProjectionService(tmp_path).project(
            operation_id, expected_source_commit=materialized.commit
        )
    assert ContinuityStore(tmp_path).get_execution_projection(operation_id) is None
    if damage != "candidate-drift":
        assert target.read_bytes() == baseline
