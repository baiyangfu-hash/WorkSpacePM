"""Legacy terminal lease fence: token invalidation without rewriting Run history."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from auto_pm.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.decision_package import (
    RUNTIME_CAPABILITY_KEY,
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionCapability,
    RuntimeDecisionOutcome,
)
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_continuity_execution_service import (
    Clock,
    _runtime_change,
    _services,
    _start,
    _start_evidence,
)

ORIGINAL_DECISION = "DEC-20260910-A2TARGT1"
FENCE_DECISION = "DEC-20260911-5C37A985"
RECOVERY_TOKEN = "recovery-secret"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _legacy_fence_ready(
    root: Path,
    clock: Clock,
    *,
    terminal: bool = True,
    expired: bool = True,
    capability_targets: tuple[str, ...] = ("RUN-TARGET",),
    decision_conditions: list[str] | None = None,
    reuse_original_chain: bool = False,
    tracked: tuple[str, ...] = (ORIGINAL_DECISION, FENCE_DECISION),
) -> tuple[ContinuityExecutionService, WorkRegistryService]:
    """One terminal Run whose expired lease token was never RELEASED, plus a live authority.

    ``tracked`` selects which Decision files are committed before the recovery Run starts.
    """

    root.mkdir(parents=True, exist_ok=True)
    _works, execution = _services(root, clock)
    works = WorkRegistryService(root, store=execution._store, now=lambda: clock().isoformat())
    _runtime_change(root)
    canonical = ["auto_pm/core/a.py", ".auto-pm/continuity.db"]
    decisions = root / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    original = DecisionPackageDTO(
        decision_id=ORIGINAL_DECISION,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214" if reuse_original_chain else "CHG-SCPT-2026-213",
        approved_scope="MODULE",
        approved_files=["auto_pm/core/a.py"],
        approver="fubai",
        approved_at=clock().isoformat(),
        decision_conclusion="approved",
    )
    fence = DecisionPackageDTO(
        decision_id=FENCE_DECISION,
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
        approved_files=canonical,
        approver="fubai",
        approved_at=clock().isoformat(),
        decision_conclusion="approved",
        conditions=list(decision_conditions or []),
        metadata={
            RUNTIME_CAPABILITY_KEY: RuntimeDecisionCapability(
                allowed_runtime_actions=(RuntimeDecisionAction.FENCE_LEGACY_TERMINAL_LEASE,),
                target_run_ids=capability_targets,
                allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
            )
        },
    )
    for item in (original, fence):
        (decisions / f"{item.decision_id}.json").write_bytes(
            json.dumps(item.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        )
    for decision_id in tracked:
        _git(root, "add", "-f", "--", f".auto-pm/decisions/{decision_id}.json")
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "bind decisions",
    )
    works.create_work(
        work_id="WORK-TARGET",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Historical target",
        owner="legacy-agent",
        scope_paths=["auto_pm/core/a.py"],
        source_fingerprint="sha256:target",
        idempotency_key="create-target-work",
    )
    works.authorize("WORK-TARGET", ORIGINAL_DECISION, "authorize-target-work")
    _start(
        execution,
        run_id="RUN-TARGET",
        work_id="WORK-TARGET",
        executor_id="legacy-agent",
        lease_token="target-secret",
        lease_seconds=60,
        idempotency_key="create-target-run",
    )
    _start_evidence(
        execution,
        run_id="RUN-TARGET",
        owner_id="legacy-agent",
        lease_token="target-secret",
        idempotency_key="record-target-start",
    )
    if terminal:
        execution.transition_run(
            "RUN-TARGET", RunState.FAILED, "legacy-agent", "target-secret", "fail-target"
        )
        # 模拟旧实现：终态后 lease 令牌从未被 RELEASED 标记。
        with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
            conn.execute(
                "UPDATE execution_leases SET lease_token='legacy-token' WHERE run_id='RUN-TARGET'"
            )
            conn.commit()
    if expired:
        clock.value += timedelta(seconds=61)
    works.create_work(
        work_id="WORK-RECOVERY",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Authorized fence",
        owner="recovery-agent",
        scope_paths=canonical,
        source_fingerprint="sha256:recovery",
        idempotency_key="create-recovery-work",
    )
    works.authorize("WORK-RECOVERY", FENCE_DECISION, "authorize-recovery-work")
    works.transition("WORK-RECOVERY", WorkState.IN_PROGRESS, "start-recovery-work")
    _start(
        execution,
        run_id="RUN-RECOVERY",
        work_id="WORK-RECOVERY",
        executor_id="recovery-agent",
        lease_token=RECOVERY_TOKEN,
        lease_seconds=900,
        idempotency_key="create-recovery-run",
        owned_paths=canonical,
    )
    _start_evidence(
        execution,
        run_id="RUN-RECOVERY",
        owner_id="recovery-agent",
        lease_token=RECOVERY_TOKEN,
        idempotency_key="record-recovery-start",
    )
    return execution, works


def _fence(execution: ContinuityExecutionService, **changes: Any) -> Any:
    evidence = execution.legacy_terminal_lease_evidence("RUN-TARGET")
    values: dict[str, Any] = {
        "target_run_id": "RUN-TARGET",
        "expected_run_state": evidence.state,
        "expected_run_version": evidence.version,
        "expected_lease_version": evidence.lease_version,
        "expected_terminal_evidence_kind": evidence.terminal_evidence_kind,
        "expected_event_set_sha256": evidence.event_set_sha256,
        "expected_checkpoint_set_sha256": evidence.checkpoint_set_sha256,
        "recovery_run_id": "RUN-RECOVERY",
        "recovery_owner_id": "recovery-agent",
        "recovery_lease_token": RECOVERY_TOKEN,
        "decision_id": FENCE_DECISION,
        "reason": "Expired legacy terminal token invalidated; Run history preserved.",
        "idempotency_key": "fence-target-lease",
    }
    values.update(changes)
    return execution.fence_legacy_terminal_lease(**values)


def _snapshot(root: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return {
            "runs": conn.execute("SELECT * FROM run_items ORDER BY run_id").fetchall(),
            "leases": conn.execute("SELECT * FROM execution_leases ORDER BY run_id").fetchall(),
            "checkpoints": conn.execute("SELECT * FROM checkpoints ORDER BY rowid").fetchall(),
            "events": conn.execute("SELECT * FROM events ORDER BY rowid").fetchall(),
        }


def test_legacy_terminal_evidence_is_read_only_and_reports_exact_bindings(tmp_path: Path) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    before = _snapshot(tmp_path)

    evidence = execution.legacy_terminal_lease_evidence("RUN-TARGET")

    assert _snapshot(tmp_path) == before
    assert evidence.fenceable and evidence.blockers == ()
    assert evidence.state == "FAILED" and evidence.lease_released is False
    assert evidence.terminal_evidence_kind in {"RUN_TRANSITIONED_V2", "RUN_TRANSITIONED_LEGACY"}
    assert "RUN_CREATED" in evidence.event_types
    assert len(evidence.event_set_sha256) == 64 and len(evidence.checkpoint_set_sha256) == 64


def test_fence_invalidates_token_and_preserves_run_history(tmp_path: Path) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    before = _snapshot(tmp_path)
    lease_before = execution._store.get_lease("RUN-TARGET").version

    run = _fence(execution)

    after = _snapshot(tmp_path)
    assert run.state is RunState.FAILED
    assert [row for row in after["runs"] if row[0] == "RUN-TARGET"] == [
        row for row in before["runs"] if row[0] == "RUN-TARGET"
    ]
    assert after["checkpoints"] == before["checkpoints"]
    assert after["events"][: len(before["events"])] == before["events"]
    appended = after["events"][len(before["events"]) :]
    assert len(appended) == 1 and appended[0][3] == "RUN_LEGACY_LEASE_FENCED"
    assert RECOVERY_TOKEN not in appended[0][4] and "legacy-token" not in appended[0][4]
    fenced = execution._store.get_lease("RUN-TARGET")
    assert fenced.lease_token.startswith("RELEASED:") and fenced.version == lease_before + 1
    # 只有被围栏的 lease 行发生变化。
    changed = [
        (old[0], new[0])
        for old, new in zip(before["leases"], after["leases"], strict=True)
        if old != new
    ]
    assert changed == [("RUN-TARGET", "RUN-TARGET")]
    assert not execution.legacy_terminal_lease_evidence("RUN-TARGET").fenceable


def test_fence_replay_is_idempotent_and_rejects_semantic_drift(tmp_path: Path) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    evidence = execution.legacy_terminal_lease_evidence("RUN-TARGET")
    first = _fence(execution)
    events = _snapshot(tmp_path)["events"]

    replay = execution.fence_legacy_terminal_lease(
        target_run_id="RUN-TARGET",
        expected_run_state=evidence.state,
        expected_run_version=evidence.version,
        expected_lease_version=evidence.lease_version,
        expected_terminal_evidence_kind=evidence.terminal_evidence_kind,
        expected_event_set_sha256=evidence.event_set_sha256,
        expected_checkpoint_set_sha256=evidence.checkpoint_set_sha256,
        recovery_run_id="RUN-RECOVERY",
        recovery_owner_id="recovery-agent",
        recovery_lease_token=RECOVERY_TOKEN,
        decision_id=FENCE_DECISION,
        reason="Expired legacy terminal token invalidated; Run history preserved.",
        idempotency_key="fence-target-lease",
    )

    assert replay == first and _snapshot(tmp_path)["events"] == events
    with pytest.raises(ContinuityExecutionError):
        _fence_with_reason(execution, evidence, "A different reason under the same key.")


def _fence_with_reason(
    execution: ContinuityExecutionService, evidence: Any, reason: str
) -> Any:
    return execution.fence_legacy_terminal_lease(
        target_run_id="RUN-TARGET",
        expected_run_state=evidence.state,
        expected_run_version=evidence.version,
        expected_lease_version=evidence.lease_version,
        expected_terminal_evidence_kind=evidence.terminal_evidence_kind,
        expected_event_set_sha256=evidence.event_set_sha256,
        expected_checkpoint_set_sha256=evidence.checkpoint_set_sha256,
        recovery_run_id="RUN-RECOVERY",
        recovery_owner_id="recovery-agent",
        recovery_lease_token=RECOVERY_TOKEN,
        decision_id=FENCE_DECISION,
        reason=reason,
        idempotency_key="fence-target-lease",
    )


def test_fence_rejects_unexpired_lease_and_non_terminal_run(tmp_path: Path) -> None:
    live, _works = _legacy_fence_ready(tmp_path / "live", Clock(), expired=False)
    before = _snapshot(tmp_path / "live")
    with pytest.raises(ContinuityExecutionError, match="尚未过期"):
        _fence(live)
    assert _snapshot(tmp_path / "live") == before

    running, _works = _legacy_fence_ready(tmp_path / "running", Clock(), terminal=False)
    evidence = running.legacy_terminal_lease_evidence("RUN-TARGET")
    assert any("不是终态" in item for item in evidence.blockers)
    with pytest.raises(ContinuityExecutionError, match="不是终态"):
        _fence(running)


def test_fence_rejects_already_released_lease_and_missing_terminal_evidence(
    tmp_path: Path,
) -> None:
    execution, _works = _legacy_fence_ready(tmp_path / "one", Clock())
    _fence(execution)
    with pytest.raises(ContinuityExecutionError, match="已释放"):
        _fence(execution, idempotency_key="fence-again")

    projection_only, _works = _legacy_fence_ready(tmp_path / "two", Clock(), terminal=False)
    with closing(sqlite3.connect(tmp_path / "two" / ".auto-pm" / "continuity.db")) as conn:
        # 仅投影行被改成终态、没有任何终态事件：必须拒绝，不得据投影反推历史。
        conn.execute("UPDATE run_items SET state='FAILED' WHERE run_id='RUN-TARGET'")
        conn.commit()
    evidence = projection_only.legacy_terminal_lease_evidence("RUN-TARGET")
    assert evidence.terminal_evidence_kind == "NONE"
    with pytest.raises(ContinuityExecutionError, match="缺少可绑定的终态证据"):
        _fence(projection_only)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"expected_run_version": 1}, "冲突"),
        ({"expected_lease_version": 9}, "冲突"),
        ({"expected_terminal_evidence_kind": "RUN_EXPIRED_SETTLED"}, "摘要"),
        ({"expected_event_set_sha256": "0" * 64}, "摘要"),
        ({"expected_checkpoint_set_sha256": "0" * 64}, "摘要"),
        ({"recovery_lease_token": "wrong-token"}, "恢复"),
        ({"recovery_owner_id": "someone-else"}, "恢复"),
    ],
)
def test_fence_binds_versions_digests_and_recovery_lease(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    before = _snapshot(tmp_path)

    with pytest.raises(ContinuityExecutionError, match=message):
        _fence(execution, **change)

    assert _snapshot(tmp_path) == before


def test_fence_requires_exact_independent_decision_authority(tmp_path: Path) -> None:
    other, _works = _legacy_fence_ready(
        tmp_path / "other", Clock(), capability_targets=("RUN-OTHER",)
    )
    with pytest.raises(ContinuityExecutionError, match="未精确授权"):
        _fence(other)

    conditional, _works = _legacy_fence_ready(
        tmp_path / "cond", Clock(), decision_conditions=["only if reviewed"]
    )
    with pytest.raises(ContinuityExecutionError, match="无条件"):
        _fence(conditional)

    same_chain, _works = _legacy_fence_ready(
        tmp_path / "chain", Clock(), reuse_original_chain=True
    )
    with pytest.raises(ContinuityExecutionError, match="独立于目标 Work 的原 CHG"):
        _fence(same_chain)


def test_fence_rejects_expired_recovery_lease_and_secret_reason(tmp_path: Path) -> None:
    clock = Clock()
    execution, _works = _legacy_fence_ready(tmp_path, clock)
    with pytest.raises(ContinuityExecutionError, match="token"):
        _fence(execution, reason=f"leaks {RECOVERY_TOKEN}")
    clock.value += timedelta(seconds=901)
    with pytest.raises(ContinuityExecutionError, match="恢复"):
        _fence(execution)


def test_fence_rolls_back_release_when_event_append_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    before = _snapshot(tmp_path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise ContinuityStoreError("simulated event failure")

    monkeypatch.setattr(execution._store, "_append_event", broken)
    with pytest.raises(ContinuityExecutionError, match="simulated"):
        _fence(execution)
    monkeypatch.undo()

    assert _snapshot(tmp_path) == before
    assert not execution._store.get_lease("RUN-TARGET").lease_token.startswith("RELEASED:")


# M2-GOV-ADJ B2 (card 026 §4, §6 G2): the legacy terminal lease fence binds the target Work's
# original Decision and the fence Decision to the recovery Run's control-root commit; replay first.

_H11_FENCE_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "target_run_id",
        "expected_run_state",
        "expected_run_version",
        "expected_lease_version",
        "expected_terminal_evidence_kind",
        "expected_event_set_sha256",
        "expected_checkpoint_set_sha256",
        "recovery_run_id",
        "expected_recovery_run_version",
        "expected_recovery_lease_version",
        "recovery_work_id",
        "expected_recovery_work_version",
        "recovery_owner_id",
        "decision_id",
        "decision_sha256",
        "reason",
    }
)
_FENCE_REASON = "Expired legacy terminal token invalidated; Run history preserved."


def _git_out(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def _advance_head(root: Path) -> None:
    _git(
        root,
        "-c",
        "user.name=Continuity Test",
        "-c",
        "user.email=continuity@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "advance control-root HEAD",
    )


def _fence_payloads(root: Path) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        rows = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='RUN_LEGACY_LEASE_FENCED' "
            "ORDER BY rowid"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _assert_not_fenced(root: Path, execution: ContinuityExecutionService, before: Any) -> None:
    assert _snapshot(root) == before
    assert not execution._store.get_lease("RUN-TARGET").lease_token.startswith("RELEASED:")


@pytest.mark.parametrize(
    "tracked",
    [(FENCE_DECISION,), (ORIGINAL_DECISION,)],
    ids=["original-untracked", "fence-untracked"],
)
def test_fence_rejects_untracked_decision_and_rolls_back(
    tmp_path: Path, tracked: tuple[str, ...]
) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock(), tracked=tracked)
    before = _snapshot(tmp_path)
    evidence = execution.legacy_terminal_lease_evidence("RUN-TARGET")
    if ORIGINAL_DECISION not in tracked:
        assert any("未被控制根 Git 跟踪" in item for item in evidence.blockers)

    # An untracked file makes `git ls-files --error-unmatch` itself fail (same fail-closed path
    # as settle_expired_run); a tracked-but-not-exact path reports 精确跟踪.
    with pytest.raises(ContinuityExecutionError, match="Decision Git commit/blob 不存在|精确跟踪"):
        _fence(execution)

    _assert_not_fenced(tmp_path, execution, before)


@pytest.mark.parametrize(
    "decision_id", [ORIGINAL_DECISION, FENCE_DECISION], ids=["original", "fence"]
)
def test_fence_rejects_decision_dirty_against_head(tmp_path: Path, decision_id: str) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    path = tmp_path / ".auto-pm" / "decisions" / f"{decision_id}.json"
    # Same JSON content, different bytes: the file no longer matches the committed blob.
    path.write_text(
        json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    before = _snapshot(tmp_path)

    with pytest.raises(ContinuityExecutionError, match="脏改"):
        _fence(execution)

    _assert_not_fenced(tmp_path, execution, before)


def test_fence_rejects_control_root_head_moved_before_first_execution(tmp_path: Path) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    _advance_head(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(ContinuityExecutionError, match="精确匹配恢复 Run git_head"):
        _fence(execution)

    _assert_not_fenced(tmp_path, execution, before)


def test_fence_rejects_decision_drift_during_recheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    store = execution._store
    real_snapshot = store._decision_snapshot
    calls = {"count": 0}

    def drifting(decision_id: str) -> Any:
        dto, digest = real_snapshot(decision_id)
        calls["count"] += 1
        # The two post-check re-reads observe different bytes than the two pre-check reads.
        return (dto, "f" * 64) if calls["count"] > 2 else (dto, digest)

    before = _snapshot(tmp_path)
    monkeypatch.setattr(store, "_decision_snapshot", drifting)
    with pytest.raises(ContinuityExecutionError, match="漂移"):
        _fence(execution)
    monkeypatch.undo()

    _assert_not_fenced(tmp_path, execution, before)


def test_fence_records_git_authority_and_keeps_request_fields(tmp_path: Path) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    head = _git_out(tmp_path, "rev-parse", "HEAD")
    assert execution._store.get_run("RUN-RECOVERY").git_head == head

    _fence(execution)

    payload = _fence_payloads(tmp_path)[-1]
    assert set(payload["request"]) == _H11_FENCE_REQUEST_KEYS
    assert payload["authority"] == {
        "schema_version": "decision-git-binding.v1",
        "git_head": head,
        "original_decision_id": ORIGINAL_DECISION,
        "original_decision_blob": _git_out(
            tmp_path, "rev-parse", f"{head}:.auto-pm/decisions/{ORIGINAL_DECISION}.json"
        ),
        "decision_id": FENCE_DECISION,
        "decision_blob": _git_out(
            tmp_path, "rev-parse", f"{head}:.auto-pm/decisions/{FENCE_DECISION}.json"
        ),
    }


def test_fence_replay_survives_head_moving_forward(tmp_path: Path) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    evidence = execution.legacy_terminal_lease_evidence("RUN-TARGET")
    first = _fence_with_reason(execution, evidence, _FENCE_REASON)
    events = _snapshot(tmp_path)["events"]
    _advance_head(tmp_path)

    replay = _fence_with_reason(execution, evidence, _FENCE_REASON)

    assert replay == first
    assert _snapshot(tmp_path)["events"] == events


def test_fence_replay_accepts_h11_event_without_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    store = execution._store
    evidence = execution.legacy_terminal_lease_evidence("RUN-TARGET")
    real_append = store._append_event

    def h11_writer(
        conn: Any, aggregate_id: str, event_type: str, payload: Any, *args: Any, **kwargs: Any
    ) -> Any:
        # Reproduce the pre-binding (H11C) event shape: no ``authority`` sub-object.
        if event_type == "RUN_LEGACY_LEASE_FENCED":
            payload = {key: value for key, value in payload.items() if key != "authority"}
        return real_append(conn, aggregate_id, event_type, payload, *args, **kwargs)

    monkeypatch.setattr(store, "_append_event", h11_writer)
    first = _fence_with_reason(execution, evidence, _FENCE_REASON)
    monkeypatch.undo()
    assert "authority" not in _fence_payloads(tmp_path)[-1]
    events = _snapshot(tmp_path)["events"]
    _advance_head(tmp_path)

    replay = _fence_with_reason(execution, evidence, _FENCE_REASON)

    assert replay == first
    assert _snapshot(tmp_path)["events"] == events
