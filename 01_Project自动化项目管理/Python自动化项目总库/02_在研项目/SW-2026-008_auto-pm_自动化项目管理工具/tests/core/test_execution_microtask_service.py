"""Capability proofs for append-only E08B plans and standalone microtask repositories."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from auto_pm.core.execution_adapter_service import (
    ExecutionDispatchError,
    ExecutionDispatchService,
)

from auto_pm.contracts.execution_adapter import (
    ExecutionAdapterKind,
    ExecutionMicrotaskPlan,
    WorktreeMode,
)
from auto_pm.contracts.mission import InternalRoutingPolicy
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from tests.core.test_execution_adapter_service import PROJECT_PATH, _ready


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _prepared(root: Path, *, operation_id: str = "OP-E08B-001") -> ExecutionDispatchService:
    routing = InternalRoutingPolicy(
        allow_execution_branch_changes=True,
        allowed_execution_adapters=frozenset(
            {ExecutionAdapterKind.CODEX, ExecutionAdapterKind.TRAE}
        ),
        approved_model="agent-a",
        required_worktree_mode=WorktreeMode.ISOLATED,
        declared_dirty_paths=(PROJECT_PATH,),
    )
    missions, _, dispatch = _ready(root, routing=routing)
    mission = missions.get("MISSION-A5-001")
    dispatch.prepare(
        mission=mission,
        work_id="WORK-A5-001",
        run_id=f"RUN-{operation_id}",
        adapter=ExecutionAdapterKind.CODEX,
        executor_id="agent-a",
        lease_token="must-never-persist",
        lease_seconds=900,
        idempotency_key=f"dispatch-{operation_id}",
        operation_id=operation_id,
        stack="python",
    )
    return dispatch


def _target(root: Path, operation_id: str) -> Path:
    digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
    return root / ".auto-pm" / "microtasks" / digest[:24]


def _rehash_plan(
    plan: ExecutionMicrotaskPlan, **updates: object
) -> ExecutionMicrotaskPlan:
    values = plan.model_dump(mode="json")
    values.update(updates)
    request = {
        name: values[name]
        for name in (
            "operation_id",
            "mission_id",
            "run_id",
            "approved_model",
            "objective",
            "owned_paths",
            "declared_dirty_paths",
            "source_worktree_path",
            "baseline_git_head",
            "repository_path",
            "manifest",
            "manifest_sha256",
        )
    }
    values["request_sha256"] = hashlib.sha256(
        json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    marker = {
        "schema_version": "codex-microtask.v1",
        **request,
        "request_sha256": values["request_sha256"],
    }
    values["marker_sha256"] = hashlib.sha256(
        json.dumps(
            marker, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return ExecutionMicrotaskPlan.model_validate(values)


def test_microtask_plan_precedes_repository_and_cold_replay_reuses_commit(
    tmp_path: Path,
) -> None:
    operation_id = "OP-E08B-HAPPY"
    dispatch = _prepared(tmp_path, operation_id=operation_id)
    first = dispatch.prepare_microtask(operation_id)
    target = Path(first.plan.repository_path)
    marker = target / ".codex-microtask.json"
    run = ContinuityStore(tmp_path).get_run(first.plan.run_id)

    assert first.status == "PREPARED"
    assert run.state.value == "READY"
    assert target == _target(tmp_path, operation_id)
    assert (target / ".git").is_dir()
    assert _git(target, "rev-list", "--count", "HEAD") == "1"
    assert _git(target, "status", "--porcelain") == ""
    assert json.loads(marker.read_text(encoding="utf-8"))["request_sha256"] == (
        first.plan.request_sha256
    )
    marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    assert marker_payload["approved_model"] == "agent-a"
    assert marker_payload["objective"] == first.plan.objective
    assert marker_payload["owned_paths"] == [PROJECT_PATH]
    assert marker_payload["declared_dirty_paths"] == [PROJECT_PATH]
    assert "must-never-persist" not in first.model_dump_json()

    cold = ExecutionDispatchService(tmp_path).prepare_microtask(operation_id)
    assert cold == first
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        rows = conn.execute(
            "SELECT event_type, payload_json FROM events "
            "WHERE event_type='EXECUTION_MICROTASK_PLANNED'"
        ).fetchall()
    assert len(rows) == 1
    assert "must-never-persist" not in rows[0][1]


def test_candidate_drift_and_changed_plan_fail_without_repository_side_effect(
    tmp_path: Path,
) -> None:
    operation_id = "OP-E08B-CANDIDATE-DRIFT"
    dispatch = _prepared(tmp_path, operation_id=operation_id)
    intent = ContinuityStore(tmp_path).get_execution_intent(operation_id)
    assert intent is not None
    candidate_file = Path(intent.receipt.worktree_path) / PROJECT_PATH
    candidate_file.write_text("drifted\n", encoding="utf-8")

    with pytest.raises(ExecutionDispatchError, match="candidate.*dirty|dirty.*漂移"):
        dispatch.prepare_microtask(operation_id)
    store = ContinuityStore(tmp_path)
    assert store.get_execution_microtask_plan(operation_id) is None
    assert not _target(tmp_path, operation_id).exists()
    assert candidate_file.read_text(encoding="utf-8") == "drifted\n"

    clean_operation = "OP-E08B-PLAN-CONFLICT"
    clean_root = tmp_path / "clean"
    clean_root.mkdir()
    clean = _prepared(clean_root, operation_id=clean_operation)
    materialized = clean.prepare_microtask(clean_operation)
    changed = materialized.plan.model_copy(
        update={"created_at": materialized.plan.created_at + timedelta(seconds=1)}
    )
    with pytest.raises(ContinuityStoreError, match="不同载荷"):
        ContinuityStore(clean_root).reserve_execution_microtask_plan(changed)
    assert clean.prepare_microtask(clean_operation) == materialized


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("approved_model", "agent-b", "approved_model"),
        ("objective", "Prepare a different safe objective.", "objective"),
        ("owned_paths", ("other.py",), "owned_paths"),
        ("declared_dirty_paths", ("other.py",), "declared_dirty_paths"),
    ],
)
def test_store_rejects_rehashed_authority_fact_tampering_on_replay(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    operation_id = f"OP-E08B-STORE-{field.upper()}"
    dispatch = _prepared(tmp_path, operation_id=operation_id)
    materialized = dispatch.prepare_microtask(operation_id)
    changed = _rehash_plan(materialized.plan, **{field: value})

    with pytest.raises(ContinuityStoreError, match=message):
        ContinuityStore(tmp_path).reserve_execution_microtask_plan(changed)
    assert ContinuityStore(tmp_path).get_execution_microtask_plan(operation_id) == (
        materialized.plan
    )
    assert dispatch.prepare_microtask(operation_id) == materialized


@pytest.mark.parametrize("mismatch", ["mission_model", "intent_owned", "run_declared"])
def test_mission_intent_run_mismatch_fails_before_plan_or_repository(
    tmp_path: Path,
    mismatch: str,
) -> None:
    operation_id = f"OP-E08B-MISMATCH-{mismatch.upper()}"
    dispatch = _prepared(tmp_path, operation_id=operation_id)
    database = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(database)) as conn:
        if mismatch == "mission_model":
            row = conn.execute(
                "SELECT authority_json FROM mission_items WHERE mission_id='MISSION-A5-001'"
            ).fetchone()
            assert row is not None
            authority = json.loads(row[0])
            authority["routing"]["approved_model"] = "agent-b"
            conn.execute(
                "UPDATE mission_items SET authority_json=? WHERE mission_id='MISSION-A5-001'",
                (json.dumps(authority),),
            )
        elif mismatch == "intent_owned":
            row = conn.execute(
                "SELECT payload_json FROM events WHERE event_type='EXECUTION_INTENT_PREPARED'"
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["receipt"]["owned_paths"] = ["other.py"]
            conn.execute(
                "UPDATE events SET payload_json=? WHERE event_type='EXECUTION_INTENT_PREPARED'",
                (json.dumps(payload),),
            )
        else:
            conn.execute(
                "UPDATE run_items SET declared_dirty_paths_json=? WHERE run_id=?",
                (json.dumps(["other.py"]), f"RUN-{operation_id}"),
            )
        conn.commit()

    with pytest.raises(ExecutionDispatchError, match="不一致"):
        dispatch.prepare_microtask(operation_id)
    store = ContinuityStore(tmp_path)
    assert store.get_execution_microtask_plan(operation_id) is None
    assert not _target(tmp_path, operation_id).exists()


def test_secret_shaped_mission_objective_fails_before_plan_or_repository(
    tmp_path: Path,
) -> None:
    operation_id = "OP-E08B-SECRET-OBJECTIVE"
    dispatch = _prepared(tmp_path, operation_id=operation_id)
    database = tmp_path / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(database)) as conn:
        conn.execute(
            "UPDATE mission_items SET objective=? WHERE mission_id='MISSION-A5-001'",
            ("Prepare with OPENAI_API_KEY=sk-proj-secretvalue.",),
        )
        conn.commit()

    with pytest.raises(ExecutionDispatchError, match="契约"):
        dispatch.prepare_microtask(operation_id)
    store = ContinuityStore(tmp_path)
    assert store.get_execution_microtask_plan(operation_id) is None
    assert not _target(tmp_path, operation_id).exists()


@pytest.mark.parametrize("damage", ["partial", "dirty", "marker", "content"])
def test_partial_or_drifted_repository_is_preserved_and_rejected(
    tmp_path: Path,
    damage: str,
) -> None:
    operation_id = f"OP-E08B-{damage.upper()}"
    dispatch = _prepared(tmp_path, operation_id=operation_id)
    target = _target(tmp_path, operation_id)
    if damage == "partial":
        target.mkdir(parents=True)
        sentinel = target / "keep.txt"
        sentinel.write_text("preserve me\n", encoding="utf-8")
        with pytest.raises(ExecutionDispatchError, match="standalone Git"):
            dispatch.prepare_microtask(operation_id)
        assert sentinel.read_text(encoding="utf-8") == "preserve me\n"
        return

    materialized = dispatch.prepare_microtask(operation_id)
    if damage == "dirty":
        path = target / PROJECT_PATH
        path.write_bytes(path.read_bytes() + b"dirty\n")
    elif damage == "marker":
        marker = target / ".codex-microtask.json"
        marker.write_text("{}\n", encoding="utf-8")
    else:
        path = target / PROJECT_PATH
        path.write_text("different committed content\n", encoding="utf-8")
        _git(target, "add", "--all")
        _git(
            target,
            "-c",
            "user.name=Drift Test",
            "-c",
            "user.email=drift@example.invalid",
            "commit",
            "--amend",
            "--no-edit",
        )
    with pytest.raises(ExecutionDispatchError):
        dispatch.prepare_microtask(operation_id)
    assert target.exists()
    assert ContinuityStore(tmp_path).get_execution_microtask_plan(operation_id) == (
        materialized.plan
    )
