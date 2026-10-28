"""收口准备之后不能手工把 Run/Work 推到终态；旧版本留下的提前终态由 C08 接纳（M3-ADOPT）

D08 第 1 道重做时，执行方在收口准备好之后自己把 Run 转为 SUCCEEDED、Work 转为 CLOSED，
C08 要求 Run 仍在 VERIFYING、Work 仍在 IN_PROGRESS，Mission 永远停在 ACCEPTED。
现在：收口准备好以后，底层命令拒绝单独推进这两个终态；已经发生的、在准备之后由同一
Run/Work 到达的提前终态，C08 照常关闭 Mission 并记一条 ``CLOSURE_LINEAGE_ADOPTED``。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_pm.application.core.pm_closure_service import (
    ClosureCompletionState,
    PmClosureError,
    PmClosureService,
)
from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.mission import MissionState
from auto_pm.domain.change.ledger_reconciler import ReconcileDiff
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from tests.core.test_pm_closure_service import (
    _DECISION_ID,
    _MISSION_ID,
    _RUN_ID,
    _WORK_ID,
    _accepted_lineage,
    _lineage_states,
    _ProjectionReconciler,
)

_PREPARED_AT = datetime(2026, 9, 20, 12, 10, tzinfo=UTC)


def _prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ContinuityStore, Path, PmClosureService, str]:
    store, database = _accepted_lineage(tmp_path)
    service = PmClosureService(
        tmp_path,
        now=lambda: _PREPARED_AT,
        store=store,
        ledger_reconciler=_ProjectionReconciler(ReconcileDiff()),
    )
    closure_id = service.prepare_closure(
        _MISSION_ID, idempotency_key="adopt-prepare"
    ).closure.closure_id
    monkeypatch.setattr(
        service, "inject_prepared_change_substance", lambda _cid: tmp_path / "CHG.md"
    )
    return store, database, service, closure_id


def _legacy_early_terminal(database: Path, *, run: bool = True, work: bool = True, at: str) -> None:
    """What the old release let an executor do by hand after the closure was prepared."""

    with closing(sqlite3.connect(database)) as conn, conn:
        conn.row_factory = sqlite3.Row
        if run:
            conn.execute(
                "UPDATE run_items SET state='SUCCEEDED', version=version+1 WHERE run_id=?",
                (_RUN_ID,),
            )
            ContinuityStore._append_event(
                conn,
                _RUN_ID,
                "RUN_TRANSITIONED",
                {
                    "schema_version": "run-transition.v2",
                    "expected_version": 3,
                    "new_state": "SUCCEEDED",
                    "result_version": 4,
                },
                "legacy-run-succeeded",
                at,
                aggregate_type="run",
            )
        if work:
            for state in ("VERIFYING", "ACCEPTED", "CLOSED"):
                conn.execute(
                    "UPDATE work_items SET state=?, version=version+1 WHERE work_id=?",
                    (state, _WORK_ID),
                )
                ContinuityStore._append_event(
                    conn,
                    _WORK_ID,
                    "WORK_TRANSITIONED",
                    {"state": state, "authorization_ref": _DECISION_ID},
                    f"legacy-work-{state.lower()}",
                    at,
                )


def _versions(database: Path) -> tuple[int, int]:
    with closing(sqlite3.connect(database)) as conn:
        run = conn.execute("SELECT version FROM run_items WHERE run_id=?", (_RUN_ID,)).fetchone()[0]
        work = conn.execute(
            "SELECT version FROM work_items WHERE work_id=?", (_WORK_ID,)
        ).fetchone()[0]
    return int(run), int(work)


def test_work_cannot_be_closed_by_hand_once_the_closure_is_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, database, _service, closure_id = _prepared(tmp_path, monkeypatch)
    work = store.get_work(_WORK_ID)
    for state in ("VERIFYING", "ACCEPTED", "CLOSED"):
        with pytest.raises(ContinuityStoreError, match=f"收口 {closure_id} 已准备"):
            store.transition(
                _WORK_ID,
                work.version,
                state,
                _DECISION_ID,
                f"hand-{state}",
                _PREPARED_AT.isoformat(),
            )
    assert store.get_work(_WORK_ID).state is WorkState.IN_PROGRESS


def test_run_cannot_succeed_by_hand_once_the_closure_is_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _database, _service, closure_id = _prepared(tmp_path, monkeypatch)
    run = store.get_run(_RUN_ID)
    with pytest.raises(ContinuityStoreError, match=f"收口 {closure_id} 已准备"):
        store.transition_run(
            _RUN_ID,
            run.version,
            "SUCCEEDED",
            "hand-run",
            _PREPARED_AT.isoformat(),
            owner_id="c05-test",
            lease_token="closure-secret",
            expected_epoch=1,
        )
    assert store.get_run(_RUN_ID).state is RunState.VERIFYING


def test_the_closure_still_closes_everything_through_c08(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store, database, service, closure_id = _prepared(tmp_path, monkeypatch)
    receipt = service.complete_closure(closure_id, idempotency_key="adopt-complete")
    assert receipt.state is ClosureCompletionState.COMPLETED
    assert _lineage_states(database)[:3] == ("SUCCEEDED", "CLOSED", "CLOSED")


def test_c08_adopts_an_early_terminal_reached_after_the_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store, database, service, closure_id = _prepared(tmp_path, monkeypatch)
    _legacy_early_terminal(database, at=datetime(2026, 9, 20, 12, 19, tzinfo=UTC).isoformat())
    before = _versions(database)

    receipt = service.complete_closure(closure_id, idempotency_key="adopt-complete")
    replay = service.complete_closure(closure_id, idempotency_key="adopt-complete")

    assert receipt.state is ClosureCompletionState.COMPLETED
    assert receipt.mission_state is MissionState.CLOSED
    assert replay == receipt
    assert _versions(database) == before
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
    with closing(sqlite3.connect(database)) as conn:
        events = [
            str(row[0])
            for row in conn.execute(
                "SELECT event_type FROM events WHERE idempotency_key LIKE 'adopt-complete%' ORDER BY rowid"
            )
        ]
    assert events == ["CLOSURE_LINEAGE_ADOPTED", "MISSION_TRANSITIONED", "CLOSURE_COMPLETED"]


def test_c08_refuses_a_terminal_reached_before_the_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store, database, service, closure_id = _prepared(tmp_path, monkeypatch)
    _legacy_early_terminal(database, at=datetime(2026, 9, 20, 12, 5, tzinfo=UTC).isoformat())
    with pytest.raises(PmClosureError, match="只接纳收口准备之后"):
        service.complete_closure(closure_id, idempotency_key="adopt-complete")
    assert _lineage_states(database)[2:4] == ("ACCEPTED", "PREPARED")


def test_c08_still_refuses_when_only_the_run_is_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store, database, service, closure_id = _prepared(tmp_path, monkeypatch)
    _legacy_early_terminal(
        database, work=False, at=datetime(2026, 9, 20, 12, 19, tzinfo=UTC).isoformat()
    )
    with pytest.raises(PmClosureError, match="C08 要求 Run 仍处于 VERIFYING"):
        service.complete_closure(closure_id, idempotency_key="adopt-complete")
    assert _lineage_states(database)[1:4] == ("IN_PROGRESS", "ACCEPTED", "PREPARED")
