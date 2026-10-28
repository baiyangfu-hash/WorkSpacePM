"""Store-level guarantees for planning spec bindings and Work administrative adjudication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import WorkState
from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from tests.core.test_work_registry_service import (
    ADJ_DECISION,
    ADJ_RECOVERY_TOKEN,
    _adjudication_ready,
)


def test_planning_spec_bindings_are_readable_and_fail_closed(tmp_path: Path) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    store = ContinuityStore(tmp_path, tmp_path / ".auto-pm" / "continuity.db")
    store.initialize("2026-09-28T00:00:00+00:00", "test")
    draft = PlanningDraft.from_intent(
        PmIntent(
            request_id="REQ-U03A-001",
            subject_project_id="SW-2026-008",
            objective="Start only the approved execution.",
            acceptance_criteria=("Real RUN_STARTED evidence is required.",),
        )
    )
    store.create_planning_draft(draft)

    with pytest.raises(ContinuityStoreError, match="尚未绑定"):
        store.get_planning_draft_specs(draft.request_id)

    expected = (("DEV-300", "specs/dev-300.md", "V1"),)
    store.bind_planning_draft_specs(draft.request_id, expected)

    assert store.get_planning_draft_specs(draft.request_id) == expected


def _decision_sha256(store: ContinuityStore, decision_id: str) -> str:
    """Real byte digest of one Decision file: first execution binds these bytes to Git."""

    path = store.workspace_root / ".auto-pm" / "decisions" / f"{decision_id}.json"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _store_kwargs(works: WorkRegistryService, store: ContinuityStore) -> dict[str, Any]:
    evidence = store.work_adjudication_evidence("WORK-TARGET")
    recovery = store.get_run("RUN-RECOVERY")
    recovery_work = store.get_work("WORK-RECOVERY")
    return {
        "target_work_id": "WORK-TARGET",
        "expected_work_version": evidence.version,
        "expected_original_decision_id": evidence.authorization_ref,
        "original_decision_sha256": _decision_sha256(store, evidence.authorization_ref),
        "expected_run_set_sha256": evidence.run_set_sha256,
        "expected_lease_set_sha256": evidence.lease_set_sha256,
        "recovery_run_id": "RUN-RECOVERY",
        "expected_recovery_run_version": recovery.version,
        "expected_recovery_lease_version": store.get_lease("RUN-RECOVERY").version,
        "recovery_work_id": "WORK-RECOVERY",
        "expected_recovery_work_version": recovery_work.version,
        "expected_recovery_work_scope_hash": store.authority_paths_hash(recovery_work.scope_paths),
        "expected_recovery_owned_paths_hash": store.authority_paths_hash(recovery.owned_paths),
        "recovery_owner_id": "recovery-agent",
        "recovery_lease_token": ADJ_RECOVERY_TOKEN,
        "decision_id": ADJ_DECISION,
        "decision_sha256": _decision_sha256(store, ADJ_DECISION),
        "decision_change_id": "CHG-SCPT-2026-214",
        "decision_project_id": "SW-2026-008",
        "decision_approved_paths": ("auto_pm/core/a.py", ".auto-pm/continuity.db"),
        "runtime_target_path": store.runtime_target_path(),
        "outcome": "CANCELLED",
        "reason": "store-level adjudication",
        "idempotency_key": "store-adjudicate",
    }


def test_store_adjudication_is_a_single_cas_transition_plus_one_event(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        events_before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    item = store.adjudicate_blocked_work(**_store_kwargs(works, store))

    assert item.state is WorkState.CANCELLED and item.authorization_ref == ADJ_DECISION
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == events_before + 1
        payload = conn.execute(
            "SELECT payload_json FROM events WHERE event_type='WORK_ADJUDICATED'"
        ).fetchone()[0]
    assert ADJ_RECOVERY_TOKEN not in payload
    assert json.loads(payload)["target"]["previous_state"] == "BLOCKED"


def test_store_rejects_drifted_recovery_chain_inside_the_transaction(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    values = _store_kwargs(works, store)
    values["expected_recovery_work_version"] = 999

    with pytest.raises(ContinuityStoreError, match="授权链已漂移"):
        store.adjudicate_blocked_work(**values)
    assert store.get_work("WORK-TARGET").state is WorkState.BLOCKED


def test_store_never_adjudicates_a_terminal_or_self_authorized_work(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    same = _store_kwargs(works, store)
    same["recovery_work_id"] = "WORK-TARGET"
    with pytest.raises(ContinuityStoreError, match="必须不同"):
        store.adjudicate_blocked_work(**same)

    store.adjudicate_blocked_work(**_store_kwargs(works, store))
    again = _store_kwargs(works, store)
    again["idempotency_key"] = "store-adjudicate-second"
    with pytest.raises(ContinuityStoreError, match="不满足行政裁决前置"):
        store.adjudicate_blocked_work(**again)


def test_store_rejects_non_cancelled_outcome_and_secret_reason(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    bad_outcome = _store_kwargs(works, store)
    bad_outcome["outcome"] = "CLOSED"
    with pytest.raises(ContinuityStoreError, match="CANCELLED"):
        store.adjudicate_blocked_work(**bad_outcome)
    leaked = _store_kwargs(works, store)
    leaked["reason"] = f"contains {ADJ_RECOVERY_TOKEN}"
    with pytest.raises(ContinuityStoreError, match="token"):
        store.adjudicate_blocked_work(**leaked)


def test_store_legacy_terminal_evidence_never_writes_and_lists_blockers(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock
    from tests.core.test_legacy_terminal_lease_fence import _legacy_fence_ready, _snapshot

    execution, _works = _legacy_fence_ready(tmp_path, Clock(), expired=False)
    before = _snapshot(tmp_path)

    evidence = execution._store.legacy_terminal_lease_evidence("RUN-TARGET")

    assert _snapshot(tmp_path) == before
    assert not evidence.fenceable
    assert any("尚未过期" in item for item in evidence.blockers)


def test_store_rejects_drifted_recovery_authority_for_legacy_fence(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock
    from tests.core.test_legacy_terminal_lease_fence import (
        FENCE_DECISION,
        RECOVERY_TOKEN,
        _legacy_fence_ready,
    )

    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    store = execution._store
    evidence = store.legacy_terminal_lease_evidence("RUN-TARGET")
    recovery = store.get_run("RUN-RECOVERY")
    recovery_work = store.get_work("WORK-RECOVERY")
    values: dict[str, Any] = {
        "target_run_id": "RUN-TARGET",
        "expected_run_state": evidence.state,
        "expected_run_version": evidence.version,
        "expected_lease_version": evidence.lease_version,
        "expected_terminal_evidence_kind": evidence.terminal_evidence_kind,
        "expected_event_set_sha256": evidence.event_set_sha256,
        "expected_checkpoint_set_sha256": evidence.checkpoint_set_sha256,
        "recovery_run_id": "RUN-RECOVERY",
        "expected_recovery_run_version": recovery.version,
        "expected_recovery_lease_version": store.get_lease("RUN-RECOVERY").version,
        "recovery_work_id": "WORK-RECOVERY",
        "expected_recovery_work_version": 999,
        "expected_recovery_work_scope_hash": store.authority_paths_hash(recovery_work.scope_paths),
        "expected_recovery_owned_paths_hash": store.authority_paths_hash(recovery.owned_paths),
        "recovery_owner_id": "recovery-agent",
        "recovery_lease_token": RECOVERY_TOKEN,
        "decision_id": FENCE_DECISION,
        "decision_sha256": _decision_sha256(store, FENCE_DECISION),
        "decision_change_id": "CHG-SCPT-2026-214",
        "decision_project_id": "SW-2026-008",
        "decision_approved_paths": ("auto_pm/core/a.py", ".auto-pm/continuity.db"),
        "runtime_target_path": store.runtime_target_path(),
        "reason": "store-level fence",
        "idempotency_key": "store-fence",
        "original_decision_id": store.get_work("WORK-TARGET").authorization_ref,
        "original_decision_sha256": _decision_sha256(
            store, store.get_work("WORK-TARGET").authorization_ref
        ),
    }

    with pytest.raises(ContinuityStoreError, match="授权链已漂移"):
        store.fence_legacy_terminal_lease(**values)
    assert not store.get_lease("RUN-TARGET").lease_token.startswith("RELEASED:")


# M2-GOV-ADJ (card 026 §6 G2 scenario 5): a caller-bound SHA-256 that differs from the Decision
# blob at the recovery Run's commit is rejected inside the transaction, with nothing written.


def _events_and_state(root: Path, store: ContinuityStore) -> tuple[Any, ...]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        events = conn.execute("SELECT * FROM events ORDER BY rowid").fetchall()
    return events, store.get_work("WORK-TARGET").state, store.get_lease("RUN-TARGET").lease_token


@pytest.mark.parametrize("field", ["original_decision_sha256", "decision_sha256"])
def test_store_adjudication_rejects_sha_not_bound_to_head_blob(tmp_path: Path, field: str) -> None:
    from tests.core.test_continuity_execution_service import Clock

    works, execution = _adjudication_ready(tmp_path, Clock())
    store = execution._store
    values = _store_kwargs(works, store)
    values[field] = "0" * 64
    before = _events_and_state(tmp_path, store)

    with pytest.raises(ContinuityStoreError, match="未绑定恢复 Run git_head"):
        store.adjudicate_blocked_work(**values)

    assert _events_and_state(tmp_path, store) == before


def _fence_store_kwargs(store: ContinuityStore) -> dict[str, Any]:
    from tests.core.test_legacy_terminal_lease_fence import FENCE_DECISION, RECOVERY_TOKEN

    evidence = store.legacy_terminal_lease_evidence("RUN-TARGET")
    recovery = store.get_run("RUN-RECOVERY")
    recovery_work = store.get_work("WORK-RECOVERY")
    original = store.get_work("WORK-TARGET").authorization_ref
    return {
        "target_run_id": "RUN-TARGET",
        "expected_run_state": evidence.state,
        "expected_run_version": evidence.version,
        "expected_lease_version": evidence.lease_version,
        "expected_terminal_evidence_kind": evidence.terminal_evidence_kind,
        "expected_event_set_sha256": evidence.event_set_sha256,
        "expected_checkpoint_set_sha256": evidence.checkpoint_set_sha256,
        "recovery_run_id": "RUN-RECOVERY",
        "expected_recovery_run_version": recovery.version,
        "expected_recovery_lease_version": store.get_lease("RUN-RECOVERY").version,
        "recovery_work_id": "WORK-RECOVERY",
        "expected_recovery_work_version": recovery_work.version,
        "expected_recovery_work_scope_hash": store.authority_paths_hash(recovery_work.scope_paths),
        "expected_recovery_owned_paths_hash": store.authority_paths_hash(recovery.owned_paths),
        "recovery_owner_id": "recovery-agent",
        "recovery_lease_token": RECOVERY_TOKEN,
        "decision_id": FENCE_DECISION,
        "decision_sha256": _decision_sha256(store, FENCE_DECISION),
        "decision_change_id": "CHG-SCPT-2026-214",
        "decision_project_id": "SW-2026-008",
        "decision_approved_paths": ("auto_pm/core/a.py", ".auto-pm/continuity.db"),
        "runtime_target_path": store.runtime_target_path(),
        "reason": "store-level fence",
        "idempotency_key": "store-fence",
        "original_decision_id": original,
        "original_decision_sha256": _decision_sha256(store, original),
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("original_decision_sha256", "0" * 64, "未绑定恢复 Run git_head"),
        ("decision_sha256", "0" * 64, "未绑定恢复 Run git_head"),
        ("original_decision_id", "DEC-20260910-OTHER001", "原授权引用与围栏绑定不一致"),
    ],
)
def test_store_legacy_fence_rejects_unbound_decision_facts(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    from tests.core.test_continuity_execution_service import Clock
    from tests.core.test_legacy_terminal_lease_fence import _legacy_fence_ready

    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    store = execution._store
    values = _fence_store_kwargs(store)
    values[field] = value
    before = _events_and_state(tmp_path, store)

    with pytest.raises(ContinuityStoreError, match=message):
        store.fence_legacy_terminal_lease(**values)

    assert _events_and_state(tmp_path, store) == before


def test_store_legacy_fence_succeeds_with_exact_git_binding(tmp_path: Path) -> None:
    from tests.core.test_continuity_execution_service import Clock
    from tests.core.test_legacy_terminal_lease_fence import _legacy_fence_ready

    execution, _works = _legacy_fence_ready(tmp_path, Clock())
    store = execution._store

    store.fence_legacy_terminal_lease(**_fence_store_kwargs(store))

    assert store.get_lease("RUN-TARGET").lease_token.startswith("RELEASED:")
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        payload = json.loads(
            conn.execute(
                "SELECT payload_json FROM events WHERE event_type='RUN_LEGACY_LEASE_FENCED'"
            ).fetchone()[0]
        )
    assert payload["authority"]["git_head"] == store.get_run("RUN-RECOVERY").git_head
    assert "original_decision_id" not in payload["request"]
