"""D-141 (part 1): pin what the #646 audit found unguarded in ``RetireService`` -- the order, the resume path and the waiting check."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from auto_pm.application.core.mission_service import MissionService, MissionServiceError
from auto_pm.contracts.continuity import WorkState
from auto_pm.contracts.mission import MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_continuity_resume_service import _workspace
from tests.core.test_resume_residue import _leftover
from tests.core.test_retire_service import PROJECT, _mission, _service


def test_a_waiting_mission_in_the_middle_or_at_the_end_still_blocks_the_whole_card(tmp_path: Path) -> None:
    """The check must look at every Mission, not only the first one in the list."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    first = _mission(tmp_path, "WORK-OLD", suffix="-A", activate=False)
    middle = _mission(tmp_path, "WORK-OLD", suffix="-B", expired=False, final=MissionState.ACCEPTANCE_PENDING)
    last = _mission(tmp_path, "WORK-OLD", suffix="-C", activate=False)
    plan = _service(tmp_path).plan(PROJECT)
    assert list(plan.items[0].mission_ids) == sorted([first, middle, last])  # waiting one is not first in the list
    assert plan.items[0].mission_ids[0] != middle
    assert middle in plan.items[0].blocked_reason

    results, _ = _service(tmp_path).apply(PROJECT, [])

    assert [r.outcome for r in results] == ["skipped"]
    store = ContinuityStore(tmp_path)
    assert store.get_mission(middle).state is MissionState.ACCEPTANCE_PENDING
    assert store.get_mission(first).state is MissionState.AWAITING_APPROVAL
    assert store.get_mission(last).state is MissionState.AWAITING_APPROVAL
    assert store.get_work("WORK-OLD").state is WorkState.BLOCKED


def test_a_failure_halfway_leaves_the_work_open_and_a_second_run_finishes_the_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missions are cancelled before the Work, so a card that stopped midway is still listed as a leftover and can be finished."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    first = _mission(tmp_path, "WORK-OLD", suffix="-A")
    second = _mission(tmp_path, "WORK-OLD", suffix="-B", activate=False)
    original = MissionService.transition
    calls = 0

    def fail_on_the_second_mission(self: MissionService, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MissionServiceError("simulated failure on the second Mission")
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(MissionService, "transition", fail_on_the_second_mission)
    results, _ = _service(tmp_path).apply(PROJECT, [])

    assert [r.outcome for r in results] == ["skipped"] and "simulated failure" in results[0].detail
    store = ContinuityStore(tmp_path)
    assert store.get_work("WORK-OLD").state is WorkState.BLOCKED  # the Work is cancelled last, so it is still open
    assert [store.get_mission(first).state, store.get_mission(second).state].count(MissionState.CANCELLED) == 1  # one done, one not
    assert _service(tmp_path).plan(PROJECT).items  # still listed as a leftover
    # D-149: the result tells which of the planned Missions really are cancelled
    assert len(results[0].mission_ids) == 2 and results[0].cancelled_mission_ids == (first,)

    monkeypatch.setattr(MissionService, "transition", original)
    retried, _ = _service(tmp_path).apply(PROJECT, [])

    assert [r.outcome for r in retried] == ["retired"]
    assert retried[0].mission_ids == retried[0].cancelled_mission_ids == (second,)  # the first one was already cancelled and is no longer planned
    assert store.get_mission(first).state is MissionState.CANCELLED
    assert store.get_mission(second).state is MissionState.CANCELLED
    assert store.get_work("WORK-OLD").state is WorkState.CANCELLED
