"""C05 tests for atomic, replay-safe Continuity v2 closure preparation."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.pm_closure_service import (
    ClosureState,
    ClosureStepKind,
    ClosureStepState,
    PmClosureError,
    PmClosureService,
)

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
