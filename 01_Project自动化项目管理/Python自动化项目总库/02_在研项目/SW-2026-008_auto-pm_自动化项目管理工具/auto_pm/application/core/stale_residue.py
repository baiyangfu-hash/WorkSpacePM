"""D-109 layer 1: tell an old leftover Work apart from a real conflict (read-only, no ledger write).

A Work still in an execution state although every Run it ever had has ended is a leftover (11-03 REL7-001/REL71-001 stayed
four days).  It must not be counted as "several active Works" or block ``orient``, but it must never be silent either:
``orient`` lists it as a warning.  A real conflict stays a conflict: a Work with a live Run, a lease that has not expired, or
a Run that ended less than ``STALE_AFTER`` ago is never classed as a leftover.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from auto_pm.contracts.continuity import (
    RunItem,
    RunState,
    WorkItem,
    WorkState,
)
from auto_pm.contracts.continuity_resume import ResumeResidue

STALE_AFTER = timedelta(
    hours=24
)  # coordinator ruling 2026-11-07: the last Run ended more than 24 hours ago
# READY is waiting for a (re)start, VERIFYING waits for a verdict: neither is a card nobody is working on.
_LEFTOVER_WORK_STATES = frozenset({WorkState.IN_PROGRESS, WorkState.BLOCKED})
_TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})


def classify_residue(
    work: WorkItem,
    runs: Sequence[RunItem],
    lease_expiries: Mapping[str, datetime | None],
    now: datetime,
) -> ResumeResidue | None:
    """``runs`` must be every Run of ``work`` (terminal ones included); ``lease_expiries`` maps run_id to its lease expiry or
    None when the Run has no lease.  Returns None unless all four conditions hold."""

    if work.state not in _LEFTOVER_WORK_STATES or not runs:
        return None
    if any(run.state not in _TERMINAL_RUN_STATES for run in runs):
        return None
    if any((expiry := lease_expiries.get(run.run_id)) is not None and expiry > now for run in runs):
        return None
    last = max(runs, key=lambda run: run.updated_at)
    ended = datetime.fromisoformat(last.updated_at)
    if now - ended <= STALE_AFTER:
        return None
    return ResumeResidue(
        work_id=work.work_id,
        work_state=work.state.value,
        last_run_id=last.run_id,
        last_run_state=last.state.value,
        last_run_ended_at=last.updated_at,
    )
