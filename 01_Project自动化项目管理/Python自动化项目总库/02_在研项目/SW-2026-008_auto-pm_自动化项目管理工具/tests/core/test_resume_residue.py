"""D-109 layer 1: an old leftover Work is a warning in orient/resume, never a conflict; a real conflict stays one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.application.core.continuity_resume_service import ContinuityResumeService
from auto_pm.application.core.stale_residue import STALE_AFTER, classify_residue
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import RunItem, RunState, WorkItem, WorkKind, WorkState
from auto_pm.contracts.execution_adapter import ExecutionStartEvidence
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli import pm as pm_module
from tests.core.test_continuity_resume_service import _git_head, _work, _workspace

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _start(
    root: Path, work_id: str, run_id: str, at: datetime, lease_seconds: int = 900
) -> ContinuityExecutionService:
    execution = ContinuityExecutionService(
        root, store=ContinuityStore(root, _clock=lambda: at), now=lambda: at
    )
    execution.start_run(
        run_id=run_id,
        work_id=work_id,
        executor_id="agent-a",
        adapter="codex",
        owned_paths=["auto_pm/a.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=_git_head(root),
        worktree_path=str(root),
        lease_token=f"token-{run_id}",
        lease_seconds=lease_seconds,
        idempotency_key=f"create-{run_id}",
    )
    execution.record_start_evidence(
        run_id=run_id,
        owner_id="agent-a",
        lease_token=f"token-{run_id}",
        evidence=ExecutionStartEvidence(
            process_id=1001, session_id=f"session-{run_id}", started_at=at
        ),
        idempotency_key=f"evidence-{run_id}",
    )
    return execution


def _in_progress(root: Path, work_id: str) -> None:
    WorkRegistryService(root, now=lambda: "2026-11-01T00:00:00+00:00").transition(
        work_id, WorkState.IN_PROGRESS, f"start-{work_id}"
    )


def _leftover(root: Path, work_id: str, ended_ago: timedelta) -> None:
    """A Work whose only Run failed ``ended_ago`` before NOW and nobody closed it."""

    _work(root, work_id)
    started = NOW - ended_ago - timedelta(minutes=5)
    _start(root, work_id, f"RUN-{work_id}", started)
    _in_progress(root, work_id)
    ended = NOW - ended_ago
    finisher = ContinuityExecutionService(
        root, store=ContinuityStore(root, _clock=lambda: ended), now=lambda: ended
    )
    finisher.transition_run(
        f"RUN-{work_id}", RunState.FAILED, "agent-a", f"token-RUN-{work_id}", f"fail-{work_id}"
    )


def _live(root: Path, work_id: str) -> None:
    """A Work with a Run that is running now and holds an unexpired lease."""

    _work(root, work_id)
    _start(root, work_id, f"RUN-{work_id}", NOW - timedelta(minutes=1), lease_seconds=3600)
    _in_progress(root, work_id)


def _collect(root: Path):  # type: ignore[no-untyped-def]
    return ContinuityResumeService(root, now=lambda: NOW).collect(project_id="SW-2026-008")


def test_an_old_leftover_is_a_warning_not_a_conflict(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    result = _collect(tmp_path)
    assert [item.work_id for item in result.residue] == ["WORK-OLD"]
    assert (
        result.residue[0].last_run_id == "RUN-WORK-OLD"
        and result.residue[0].last_run_state == "FAILED"
    )
    assert result.conflicts == ()


def test_a_recent_failure_is_not_yet_a_leftover(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-NEW", timedelta(hours=1))
    assert _collect(tmp_path).residue == ()


def test_a_leftover_does_not_make_several_active_works(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    _live(tmp_path, "WORK-LIVE")
    result = _collect(tmp_path)
    assert result.work is not None and result.work.work_id == "WORK-LIVE"
    assert "MULTIPLE_ACTIVE_WORKS" not in result.conflicts
    assert [item.work_id for item in result.residue] == ["WORK-OLD"]


def test_two_live_works_are_still_a_conflict(tmp_path: Path) -> None:
    """Counterexample: the classification must not swallow a real conflict."""

    _workspace(tmp_path)
    _live(tmp_path, "WORK-A")
    _live(tmp_path, "WORK-B")
    result = _collect(tmp_path)
    assert result.conflicts == ("MULTIPLE_ACTIVE_WORKS",) and result.residue == ()


def test_two_old_leftovers_are_two_warnings_and_no_conflict(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD-1", timedelta(days=4))
    _leftover(tmp_path, "WORK-OLD-2", timedelta(days=2))
    result = _collect(tmp_path)
    assert [item.work_id for item in result.residue] == ["WORK-OLD-1", "WORK-OLD-2"]
    assert result.conflicts == ()


# ── the rule itself, with every way to trick it ──


def _work_item(state: WorkState = WorkState.IN_PROGRESS) -> WorkItem:
    return WorkItem(
        work_id="W", subject_project_id="P", kind=WorkKind.GOVERNANCE, title="t", state=state, owner="o",
        read_only=False, authorization_ref="d", scope_paths=(), scope_hash="h", source_fingerprint="f",
        version=1, created_at="2026-11-01T00:00:00+00:00", updated_at="2026-11-01T00:00:00+00:00",
    )  # fmt: skip


def _run_item(run_id: str, state: RunState, ended: datetime) -> RunItem:
    return RunItem(
        run_id=run_id, work_id="W", state=state, executor_id="e", adapter="a", owned_paths=(),
        declared_dirty_paths=(), git_head="h", worktree_path="w", version=1,
        created_at=ended.isoformat(), updated_at=ended.isoformat(),
    )  # fmt: skip


OLD = NOW - STALE_AFTER - timedelta(minutes=1)


def test_the_rule_flags_only_a_fully_ended_old_work() -> None:
    assert (
        classify_residue(_work_item(), [_run_item("R", RunState.FAILED, OLD)], {}, NOW) is not None
    )
    assert (
        classify_residue(
            _work_item(WorkState.BLOCKED), [_run_item("R", RunState.CANCELLED, OLD)], {}, NOW
        )
        is not None
    )


@pytest.mark.parametrize(
    "live",
    [RunState.RUNNING, RunState.BLOCKED, RunState.VERIFYING, RunState.PENDING, RunState.READY],
)
def test_one_live_run_among_ended_ones_is_never_a_leftover(live: RunState) -> None:
    runs = [_run_item("R1", RunState.FAILED, OLD), _run_item("R2", live, OLD)]
    assert classify_residue(_work_item(), runs, {}, NOW) is None


def test_an_unexpired_lease_on_an_ended_run_is_never_a_leftover() -> None:
    runs = [_run_item("R", RunState.FAILED, OLD)]
    assert classify_residue(_work_item(), runs, {"R": NOW + timedelta(minutes=5)}, NOW) is None
    assert classify_residue(_work_item(), runs, {"R": NOW - timedelta(minutes=5)}, NOW) is not None


def test_a_work_without_any_run_is_not_a_leftover() -> None:
    assert classify_residue(_work_item(), [], {}, NOW) is None


def test_the_24_hour_edge() -> None:
    edge = NOW - STALE_AFTER
    assert classify_residue(_work_item(), [_run_item("R", RunState.FAILED, edge)], {}, NOW) is None
    assert (
        classify_residue(
            _work_item(), [_run_item("R", RunState.FAILED, edge - timedelta(seconds=1))], {}, NOW
        )
        is not None
    )


def test_the_newest_run_decides_the_age() -> None:
    runs = [
        _run_item("R1", RunState.FAILED, OLD),
        _run_item("R2", RunState.CANCELLED, NOW - timedelta(hours=2)),
    ]
    assert classify_residue(_work_item(), runs, {}, NOW) is None


@pytest.mark.parametrize(
    "state", [WorkState.ACCEPTED, WorkState.CANCELLED, WorkState.READY, WorkState.VERIFYING]
)
def test_only_execution_states_can_be_leftovers(state: WorkState) -> None:
    assert (
        classify_residue(_work_item(state), [_run_item("R", RunState.FAILED, OLD)], {}, NOW) is None
    )


def test_orient_text_lists_the_leftover_as_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The leftover must be visible in what the user reads, not only in the data."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    pm_module._echo_resume_text(_collect(tmp_path))
    text = capsys.readouterr().out
    assert "陈年残留" in text and "WORK-OLD" in text and "冲突:" not in text


def test_orient_text_has_no_residue_line_when_there_is_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _workspace(tmp_path)
    _live(tmp_path, "WORK-LIVE")
    pm_module._echo_resume_text(_collect(tmp_path))
    assert "陈年残留" not in capsys.readouterr().out


# --- audit 1 of #628: an unreadable or zone-less time in an old ledger row must never crash orient -------------------------

NAIVE = "2026-11-01T00:00:00"  # no time zone
BAD_TIMES = [NAIVE, "not-a-date", ""]


def _with(run: RunItem, **changes: str) -> RunItem:
    return run.model_copy(update=changes)


@pytest.mark.parametrize("bad", BAD_TIMES)
def test_rule_run_end_time_unreadable_or_zoneless_is_not_a_leftover_and_does_not_raise(bad: str) -> None:
    runs = [_with(_run_item("R", RunState.FAILED, OLD), updated_at=bad)]
    assert classify_residue(_work_item(), runs, {}, NOW) is None
    mixed = [_run_item("R1", RunState.FAILED, OLD), _with(_run_item("R2", RunState.FAILED, OLD), updated_at=bad)]
    assert classify_residue(_work_item(), mixed, {}, NOW) is None  # one bad row spoils the proof for the whole Work


def test_rule_lease_time_without_zone_counts_as_not_expired_and_does_not_raise() -> None:
    runs = [_run_item("R", RunState.FAILED, OLD)]
    assert classify_residue(_work_item(), runs, {"R": datetime(2026, 11, 1)}, NOW) is None


def _break(root: Path, table: str, column: str, run_id: str, value: str) -> None:
    import sqlite3

    with sqlite3.connect(root / ".auto-pm" / "continuity.db") as conn:
        cursor = conn.execute(f"UPDATE {table} SET {column}=? WHERE run_id=?", (value, run_id))  # noqa: S608
        assert cursor.rowcount == 1, (table, column)


@pytest.mark.parametrize("bad", BAD_TIMES)
@pytest.mark.parametrize(("table", "column"), [("execution_leases", "expires_at"), ("run_items", "updated_at")])
def test_ledger_a_bad_time_on_an_old_run_does_not_crash_and_that_work_stays_active(
    tmp_path: Path, table: str, column: str, bad: str
) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-BAD", timedelta(days=3))
    _leftover(tmp_path, "WORK-GOOD", timedelta(days=3))
    _break(tmp_path, table, column, "RUN-WORK-BAD", bad)

    result = _collect(tmp_path)  # must not raise

    assert [item.work_id for item in result.residue] == ["WORK-GOOD"]
    assert result.conflicts == ()
    assert result.work is not None and result.work.work_id == "WORK-BAD"  # still counted active, as before this change
