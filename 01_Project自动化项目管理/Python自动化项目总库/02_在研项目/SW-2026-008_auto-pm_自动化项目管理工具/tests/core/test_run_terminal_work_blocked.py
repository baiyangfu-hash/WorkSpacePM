"""D-109 层 3：Run 以 FAILED/CANCELLED 结束、Work 再没有活 Run 时，同一事务里 Work 进 BLOCKED

以前 Run 进失败终态不带动 Work，Work 一直停在 IN_PROGRESS 没人收口（11-03 REL7-001/REL71-001 就是这样留了四天）。
BLOCKED 是现有合法状态；SUCCEEDED 不动（要走验收）；Work 不在 IN_PROGRESS 或还有别的活 Run 时不动。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionError
from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_continuity_execution_service import Clock, _services, _start, _start_evidence


def _in_progress(tmp_path: Path):  # noqa: ANN202 - test helper
    work, service = _services(tmp_path, Clock())
    _start(service)
    _start_evidence(service)
    work.transition("WORK-001", WorkState.IN_PROGRESS, "work-in-progress")
    assert work.get_work("WORK-001").state is WorkState.IN_PROGRESS
    return work, service


@pytest.mark.parametrize("terminal", [RunState.FAILED, RunState.CANCELLED])
def test_failed_or_cancelled_run_blocks_its_in_progress_work(
    tmp_path: Path, terminal: RunState
) -> None:
    work, service = _in_progress(tmp_path)
    if terminal is RunState.FAILED:
        service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "verify")
    else:
        service.transition_run("RUN-001", RunState.BLOCKED, "agent-a", "lease-secret", "block")
        assert (
            work.get_work("WORK-001").state is WorkState.IN_PROGRESS
        )  # a live (BLOCKED) Run still holds the Work
    service.transition_run("RUN-001", terminal, "agent-a", "lease-secret", "end")
    assert work.get_work("WORK-001").state is WorkState.BLOCKED


def test_succeeded_run_leaves_work_for_acceptance(tmp_path: Path) -> None:
    work, service = _in_progress(tmp_path)
    service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "verify")
    service.transition_run("RUN-001", RunState.SUCCEEDED, "agent-a", "lease-secret", "ok")
    assert work.get_work("WORK-001").state is WorkState.IN_PROGRESS


def test_blocked_work_is_cleared_by_the_ordinary_cancel_and_leaves_a_trace(tmp_path: Path) -> None:
    work, service = _in_progress(tmp_path)
    service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "verify")
    service.transition_run("RUN-001", RunState.FAILED, "agent-a", "lease-secret", "end")
    work.transition("WORK-001", WorkState.CANCELLED, "retire-1")
    assert work.get_work("WORK-001").state is WorkState.CANCELLED
    with closing(sqlite3.connect(tmp_path / ".auto-pm" / "continuity.db")) as conn:
        states = [
            row[0]
            for row in conn.execute(
                "SELECT json_extract(payload_json,'$.state') FROM events "
                "WHERE aggregate_id='WORK-001' AND event_type='WORK_TRANSITIONED' ORDER BY rowid"
            )
        ]
    assert states[-2:] == ["BLOCKED", "CANCELLED"]


def test_run_event_and_work_block_commit_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work, service = _in_progress(tmp_path)
    service.transition_run("RUN-001", RunState.VERIFYING, "agent-a", "lease-secret", "verify")
    store = service._store
    real = store._append_event

    def fail_on_work_event(conn, aggregate_id, event_type, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if event_type == "WORK_TRANSITIONED":
            raise ContinuityStoreError("injected")
        return real(conn, aggregate_id, event_type, *args, **kwargs)

    monkeypatch.setattr(store, "_append_event", fail_on_work_event)
    with pytest.raises(ContinuityExecutionError, match="injected"):
        service.transition_run("RUN-001", RunState.FAILED, "agent-a", "lease-secret", "end")
    assert store.get_run("RUN-001").state is RunState.VERIFYING
    assert work.get_work("WORK-001").state is WorkState.IN_PROGRESS
