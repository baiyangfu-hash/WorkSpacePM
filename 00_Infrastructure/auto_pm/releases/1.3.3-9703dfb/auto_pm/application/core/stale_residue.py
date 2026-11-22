"""D-109 layer 1: tell an old leftover Work apart from a real conflict (read-only, no ledger write).

A Work still in an execution state although every Run it ever had has ended is a leftover (11-03 REL7-001/REL71-001 stayed
four days).  It must not be counted as "several active Works" or block ``orient``, but it must never be silent either:
``orient`` lists it as a warning.  A real conflict stays a conflict: a Work with a live Run, a lease that has not expired, or
a Run that ended less than ``STALE_AFTER`` ago is never classed as a leftover.

D-339 (CHG-SCPT-2026-647): an *orphan card* is the other way a card is left behind: the Mission is still open but the Work
under it was already CANCELLED and every Run has ended.  ``classify_residue`` does not see it (its Work is terminal), so it
has its own judgement, ``is_orphan_mission``; the four leftover conditions above are not touched.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timedelta

from auto_pm.contracts.continuity import (
    RunItem,
    RunState,
    WorkItem,
    WorkState,
)
from auto_pm.contracts.continuity_resume import ResumeResidue
from auto_pm.contracts.mission import Mission, MissionState

STALE_AFTER = timedelta(
    hours=24
)  # coordinator ruling 2026-11-07: the last Run ended more than 24 hours ago
# READY is waiting for a (re)start, VERIFYING waits for a verdict: neither is a card nobody is working on.
_LEFTOVER_WORK_STATES = frozenset({WorkState.IN_PROGRESS, WorkState.BLOCKED})
_TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})


def _aware_time(text: str) -> datetime | None:
    """The time with a zone, or None when ``text`` is not a time or has no zone (old ledger rows may be either)."""

    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


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
    for run in runs:
        expiry = lease_expiries.get(run.run_id)
        if expiry is None:
            continue
        # A lease time without a time zone cannot be compared with ``now``: treat it as "not expired" (cannot prove a leftover).
        if expiry.tzinfo is None or expiry > now:
            return None
    ended_at: dict[str, datetime] = {}
    for run in runs:
        parsed = _aware_time(run.updated_at)
        if parsed is None:  # unreadable or zone-less end time: cannot prove it is old, never raise
            return None
        ended_at[run.run_id] = parsed
    last = max(runs, key=lambda run: ended_at[run.run_id])
    if now - ended_at[last.run_id] <= STALE_AFTER:
        return None
    return ResumeResidue(
        work_id=work.work_id,
        work_state=work.state.value,
        last_run_id=last.run_id,
        last_run_state=last.state.value,
        last_run_ended_at=last.updated_at,
    )


def is_orphan_mission(
    mission: Mission,
    work: WorkItem | None,
    runs: Sequence[RunItem],
    open_states: Collection[MissionState],
) -> bool:
    """D-339: the Mission is in one of ``open_states`` (still open, cancellable), it has a root Work, that Work is CANCELLED,
    and every Run under it (``runs`` must be all of them, terminal ones included) has ended.  A single Run that has not ended
    means somebody may still be working: not an orphan."""

    if mission.state not in open_states or not mission.root_work_id or work is None:
        return False
    if work.work_id != mission.root_work_id or work.state is not WorkState.CANCELLED:
        return False
    return all(run.state in _TERMINAL_RUN_STATES for run in runs)
