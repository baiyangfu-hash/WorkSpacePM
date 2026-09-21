"""C05 tests for atomic, replay-safe Continuity v2 closure preparation."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.change.ledger_reconciler import ReconcileDiff
from auto_pm.core.pm_closure_service import (
    ClosureCompletionState,
    ClosureState,
    ClosureStepKind,
    ClosureStepState,
    LedgerProjectionState,
    PmClosureError,
    PmClosureService,
)

from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, Mission, MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

_MISSION_ID = "MISSION-C05-001"
_WORK_ID = "WORK-C05-001"
_RUN_ID = "RUN-C05-001"
_CHECKPOINT_ID = "CP-C05-001"
_CHANGE_ID = "CHG-SCPT-2026-280"
_DECISION_ID = "DEC-20260920-4BAC1FE5"


def _git_root(root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "init"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _accepted_lineage(root: Path) -> tuple[ContinuityStore, Path]:
    _git_root(root)
    database = root / ".auto-pm" / "c05-closure.db"
    store = ContinuityStore(root, database)
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    timestamp = now.isoformat()
    store.initialize(timestamp, "test")
    store.create_work(
        {
            "work_id": _WORK_ID,
            "subject_project_id": "SW-2026-008",
            "kind": "WBS",
            "title": "C05 accepted root work",
            "state": "IN_PROGRESS",
            "owner": "Codex",
            "read_only": 0,
            "authorization_ref": _DECISION_ID,
            "scope_json": json.dumps(["auto_pm/core/target.py"]),
            "scope_hash": "a" * 64,
            "source_fingerprint": f"sha256:{'b' * 64}",
            "version": 3,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "c05-work-create",
        timestamp,
    )
    authority = AuthorityEnvelope(
        envelope_id="AUTH-C05-001",
        subject_project_id="SW-2026-008",
        change_id=_CHANGE_ID,
        decision_id=_DECISION_ID,
        scope_paths=("auto_pm/core/target.py",),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'c' * 64}",
        ),
    )
    mission = Mission(
        mission_id=_MISSION_ID,
        subject_project_id="SW-2026-008",
        title="C05 closure preparation",
        objective="Prepare closure state without external effects.",
        state=MissionState.ACCEPTED,
        root_work_id=_WORK_ID,
        acceptance_criteria=("The latest passing checkpoint was accepted.",),
        authority=authority,
        version=5,
        created_by="Codex PM",
        created_at=now,
        updated_at=now,
    )
    mission_values = mission.model_dump(mode="json")
    mission_values.pop("schema_version")
    mission_values["acceptance_criteria_json"] = json.dumps(
        mission_values.pop("acceptance_criteria"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    mission_values["authority_json"] = json.dumps(
        mission_values.pop("authority"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    store.create_mission(mission_values, "c05-mission-create", timestamp)

    with sqlite3.connect(database) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """INSERT INTO run_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _RUN_ID,
                _WORK_ID,
                "VERIFYING",
                "c05-test",
                "test",
                json.dumps(["auto_pm/core/target.py"]),
                "[]",
                "d" * 40,
                str(root.resolve()),
                3,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _CHECKPOINT_ID,
                _RUN_ID,
                1,
                "latest passing C03 evidence",
                "d" * 40,
                "[]",
                json.dumps(["verified quality evidence"]),
                timestamp,
            ),
        )
    return store, database


def _table_counts(database: Path) -> dict[str, int]:
    with sqlite3.connect(database) as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("closure_items", "closure_steps", "closure_outbox")
        } | {
            "closure_events": int(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type='CLOSURE_PREPARED'"
                ).fetchone()[0]
            )
        }


def _lineage_states(database: Path) -> tuple[str, str, str, str, int, str, int, bool]:
    with sqlite3.connect(database) as conn:
        run_state = str(
            conn.execute("SELECT state FROM run_items WHERE run_id=?", (_RUN_ID,)).fetchone()[0]
        )
        work_state = str(
            conn.execute("SELECT state FROM work_items WHERE work_id=?", (_WORK_ID,)).fetchone()[0]
        )
        mission_state = str(
            conn.execute(
                "SELECT state FROM mission_items WHERE mission_id=?", (_MISSION_ID,)
            ).fetchone()[0]
        )
        closure_state, closure_version = conn.execute(
            "SELECT state, version FROM closure_items"
        ).fetchone()
        step_state, attempt_count = conn.execute(
            "SELECT state, attempt_count FROM closure_steps"
        ).fetchone()
        published_at = conn.execute("SELECT published_at FROM closure_outbox").fetchone()[0]
    return (
        run_state,
        work_state,
        mission_state,
        str(closure_state),
        int(closure_version),
        str(step_state),
        int(attempt_count),
        published_at is not None,
    )


class _ProjectionReconciler:
    def __init__(self, result: ReconcileDiff | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def project_change(self, project_path: str, change_number: str) -> ReconcileDiff:
        self.calls.append((project_path, change_number))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_prepare_closure_atomically_persists_state_step_outbox_and_event(tmp_path: Path) -> None:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 5, tzinfo=UTC),
        store=store,
    )

    prepared = service.prepare_closure(_MISSION_ID, idempotency_key="c05-prepare")

    assert prepared.closure.state is ClosureState.PREPARED
    assert prepared.closure.mission_id == _MISSION_ID
    assert prepared.closure.work_id == _WORK_ID
    assert prepared.closure.run_id == _RUN_ID
    assert prepared.closure.checkpoint_id == _CHECKPOINT_ID
    assert prepared.closure.change_id == _CHANGE_ID
    assert prepared.closure.decision_id == _DECISION_ID
    assert prepared.step.step_kind is ClosureStepKind.CHANGE_SUBSTANCE
    assert prepared.step.state is ClosureStepState.PENDING
    assert prepared.step.attempt_count == 0
    assert prepared.outbox.artifact_kind is ClosureStepKind.CHANGE_SUBSTANCE
    assert prepared.outbox.published_at is None
    assert prepared.outbox.payload["operation"] == "CHANGE_SUBSTANCE"
    assert prepared.outbox.payload["checkpoint_id"] == _CHECKPOINT_ID
    assert _table_counts(database) == {
        "closure_items": 1,
        "closure_steps": 1,
        "closure_outbox": 1,
        "closure_events": 1,
    }


def test_prepare_closure_same_key_and_payload_returns_original_without_duplicates(
    tmp_path: Path,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(tmp_path, store=store)

    first = service.prepare_closure(_MISSION_ID, idempotency_key="c05-replay")
    second = service.prepare_closure(_MISSION_ID, idempotency_key="c05-replay")

    assert second == first
    assert _table_counts(database) == {
        "closure_items": 1,
        "closure_steps": 1,
        "closure_outbox": 1,
        "closure_events": 1,
    }


def test_prepare_closure_rejects_same_key_with_different_payload_without_writes(
    tmp_path: Path,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(tmp_path, store=store)
    first = service.prepare_closure(_MISSION_ID, idempotency_key="c05-key-conflict")
    before = _table_counts(database)

    with pytest.raises(PmClosureError, match="语义不一致"):
        service.prepare_closure("MISSION-C05-DIFFERENT", idempotency_key="c05-key-conflict")

    assert first.closure.mission_id == _MISSION_ID
    assert _table_counts(database) == before


def test_prepare_closure_injected_failure_rolls_back_all_rows_and_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(tmp_path, store=store)
    append_event = ContinuityStore._append_event

    def fail_after_event(*args: object, **kwargs: object) -> None:
        append_event(*args, **kwargs)  # type: ignore[arg-type]
        raise ContinuityStoreError("injected before closure commit")

    monkeypatch.setattr(ContinuityStore, "_append_event", staticmethod(fail_after_event))

    with pytest.raises(PmClosureError, match="injected"):
        service.prepare_closure(_MISSION_ID, idempotency_key="c05-rollback")

    assert _table_counts(database) == {
        "closure_items": 0,
        "closure_steps": 0,
        "closure_outbox": 0,
        "closure_events": 0,
    }


def test_prepare_closure_requires_an_accepted_mission_and_writes_nothing(tmp_path: Path) -> None:
    store, database = _accepted_lineage(tmp_path)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "UPDATE mission_items SET state='ACCEPTANCE_PENDING' WHERE mission_id=?",
            (_MISSION_ID,),
        )
    service = PmClosureService(tmp_path, store=store)

    with pytest.raises(PmClosureError, match="已验收 Mission"):
        service.prepare_closure(_MISSION_ID, idempotency_key="c05-not-accepted")

    assert _table_counts(database) == {
        "closure_items": 0,
        "closure_steps": 0,
        "closure_outbox": 0,
        "closure_events": 0,
    }


def test_initialize_adds_closure_tables_to_an_existing_current_store(tmp_path: Path) -> None:
    store, database = _accepted_lineage(tmp_path)
    with sqlite3.connect(database) as conn:
        conn.execute("DROP TABLE closure_outbox")
        conn.execute("DROP TABLE closure_steps")
        conn.execute("DROP TABLE closure_items")

    PmClosureService(tmp_path, store=store).initialize("c05-test")

    with sqlite3.connect(database) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                """SELECT name FROM sqlite_master WHERE type='table'
                AND name LIKE 'closure_%'"""
            )
        }
        version = str(conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0])
    assert tables == {"closure_items", "closure_steps", "closure_outbox"}
    assert version == "continuity-store.v7"


def test_project_prepared_ledger_is_idempotent_without_new_closure_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(ReconcileDiff())
    service = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="c07-project")
    injected: list[str] = []

    def record_substance(closure_id: str) -> Path:
        injected.append(closure_id)
        return tmp_path / "CHG.md"

    monkeypatch.setattr(
        service,
        "inject_prepared_change_substance",
        record_substance,
    )
    monkeypatch.setattr(service, "get", lambda closure_id: preparation)

    first = service.project_prepared_ledger(preparation.closure.closure_id)
    second = service.project_prepared_ledger(preparation.closure.closure_id)

    assert first == second
    assert first.state is LedgerProjectionState.PROJECTED
    assert injected == [preparation.closure.closure_id, preparation.closure.closure_id]
    assert reconciler.calls == [
        (str(tmp_path), _CHANGE_ID),
        (str(tmp_path), _CHANGE_ID),
    ]
    assert _table_counts(database)["closure_events"] == 1


def test_project_prepared_ledger_keeps_projection_failure_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(OSError("ledger unavailable"))
    service = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="c07-pending")
    monkeypatch.setattr(
        service,
        "inject_prepared_change_substance",
        lambda closure_id: tmp_path / f"{closure_id}.md",
    )
    monkeypatch.setattr(service, "get", lambda closure_id: preparation)

    receipt = service.project_prepared_ledger(preparation.closure.closure_id)

    assert receipt.state is LedgerProjectionState.PENDING_SYNC
    assert receipt.pending_reason == "ledger unavailable"
    assert _table_counts(database)["closure_events"] == 1


def test_complete_closure_orders_terminal_states_after_successful_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(ReconcileDiff())
    service = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="c08-prepare")
    injected: list[str] = []

    def record_substance(closure_id: str) -> Path:
        injected.append(closure_id)
        return tmp_path / "CHG.md"

    monkeypatch.setattr(service, "inject_prepared_change_substance", record_substance)

    receipt = service.complete_closure(
        preparation.closure.closure_id,
        idempotency_key="c08-complete",
    )

    assert receipt.state is ClosureCompletionState.COMPLETED
    assert receipt.projection_state is LedgerProjectionState.PROJECTED
    assert receipt.run_state is RunState.SUCCEEDED
    assert receipt.work_state is WorkState.CLOSED
    assert receipt.mission_state is MissionState.CLOSED
    assert injected == [preparation.closure.closure_id]
    assert reconciler.calls == [(str(tmp_path), _CHANGE_ID)]
    assert _lineage_states(database) == (
        "SUCCEEDED",
        "CLOSED",
        "CLOSED",
        "COMPLETED",
        2,
        "COMPLETED",
        1,
        True,
    )

    with sqlite3.connect(database) as conn:
        closure = conn.execute(
            "SELECT state, version FROM closure_items WHERE closure_id=?",
            (preparation.closure.closure_id,),
        ).fetchone()
        step = conn.execute(
            "SELECT state, attempt_count FROM closure_steps WHERE closure_id=?",
            (preparation.closure.closure_id,),
        ).fetchone()
        outbox = conn.execute(
            "SELECT published_at FROM closure_outbox WHERE closure_id=?",
            (preparation.closure.closure_id,),
        ).fetchone()
        ordered_events = [
            str(row[0])
            for row in conn.execute(
                "SELECT event_type FROM events WHERE idempotency_key LIKE 'c08-complete%' "
                "ORDER BY rowid"
            )
        ]
    assert closure == ("COMPLETED", 2)
    assert step == ("COMPLETED", 1)
    assert outbox is not None and outbox[0] is not None
    assert ordered_events == [
        "RUN_TRANSITIONED",
        "WORK_TRANSITIONED",
        "WORK_TRANSITIONED",
        "WORK_TRANSITIONED",
        "MISSION_TRANSITIONED",
        "CLOSURE_COMPLETED",
    ]


def test_complete_closure_exact_replay_skips_projection_and_duplicate_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(ReconcileDiff())
    service = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=reconciler,
    )
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="c08-replay-prepare")
    injected: list[str] = []

    def record_substance(closure_id: str) -> Path:
        injected.append(closure_id)
        return tmp_path / "CHG.md"

    monkeypatch.setattr(service, "inject_prepared_change_substance", record_substance)

    first = service.complete_closure(
        preparation.closure.closure_id,
        idempotency_key="c08-replay",
    )
    with sqlite3.connect(database) as conn:
        event_count = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    second = service.complete_closure(
        preparation.closure.closure_id,
        idempotency_key="c08-replay",
    )

    assert second == first
    assert injected == [preparation.closure.closure_id]
    assert reconciler.calls == [(str(tmp_path), _CHANGE_ID)]
    with sqlite3.connect(database) as conn:
        assert int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]) == event_count
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type='CLOSURE_COMPLETED'"
                ).fetchone()[0]
            )
            == 1
        )


def test_complete_closure_projection_failure_leaves_lineage_non_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    reconciler = _ProjectionReconciler(OSError("ledger unavailable"))
    service = PmClosureService(tmp_path, store=store, ledger_reconciler=reconciler)
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="c08-pending-prepare")
    monkeypatch.setattr(
        service,
        "inject_prepared_change_substance",
        lambda closure_id: tmp_path / f"{closure_id}.md",
    )

    receipt = service.complete_closure(
        preparation.closure.closure_id,
        idempotency_key="c08-pending",
    )

    assert receipt.state is ClosureCompletionState.PENDING_SYNC
    assert receipt.projection_state is LedgerProjectionState.PENDING_SYNC
    assert receipt.pending_reason == "ledger unavailable"
    assert _lineage_states(database) == (
        "VERIFYING",
        "IN_PROGRESS",
        "ACCEPTED",
        "PREPARED",
        1,
        "PENDING",
        0,
        False,
    )
    with sqlite3.connect(database) as conn:
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type='CLOSURE_COMPLETED'"
                ).fetchone()[0]
            )
            == 0
        )


def test_finalize_closure_rejects_pending_projection_without_state_changes(tmp_path: Path) -> None:
    store, database = _accepted_lineage(tmp_path)
    preparation = PmClosureService(tmp_path, store=store).prepare_closure(
        _MISSION_ID,
        idempotency_key="c08-reject-prepare",
    )

    with pytest.raises(ContinuityStoreError, match="成功必要投影"):
        store.finalize_closure(
            preparation.closure.closure_id,
            {
                "closure_id": preparation.closure.closure_id,
                "change_id": _CHANGE_ID,
                "state": "PENDING_SYNC",
                "pending_reason": "ledger unavailable",
            },
            "c08-reject-pending",
            datetime(2026, 9, 20, 12, 10, tzinfo=UTC).isoformat(),
        )

    assert _lineage_states(database) == (
        "VERIFYING",
        "IN_PROGRESS",
        "ACCEPTED",
        "PREPARED",
        1,
        "PENDING",
        0,
        False,
    )


def test_complete_closure_failure_rolls_back_every_lifecycle_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(
        tmp_path,
        now=lambda: datetime(2026, 9, 20, 12, 10, tzinfo=UTC),
        store=store,
        ledger_reconciler=_ProjectionReconciler(ReconcileDiff()),
    )
    preparation = service.prepare_closure(_MISSION_ID, idempotency_key="c08-rollback-prepare")
    monkeypatch.setattr(
        service,
        "inject_prepared_change_substance",
        lambda closure_id: tmp_path / f"{closure_id}.md",
    )
    append_event = ContinuityStore._append_event

    def fail_on_completion_event(*args: object, **kwargs: object) -> None:
        append_event(*args, **kwargs)  # type: ignore[arg-type]
        if len(args) > 2 and args[2] == "CLOSURE_COMPLETED":
            raise ContinuityStoreError("injected before C08 commit")

    monkeypatch.setattr(ContinuityStore, "_append_event", staticmethod(fail_on_completion_event))

    with pytest.raises(PmClosureError, match="injected"):
        service.complete_closure(
            preparation.closure.closure_id,
            idempotency_key="c08-rollback",
        )

    assert _lineage_states(database) == (
        "VERIFYING",
        "IN_PROGRESS",
        "ACCEPTED",
        "PREPARED",
        1,
        "PENDING",
        0,
        False,
    )
    with sqlite3.connect(database) as conn:
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE idempotency_key LIKE 'c08-rollback%'"
                ).fetchone()[0]
            )
            == 1
        )
