"""TD-071 technical debt (audit 78, 5): the cockpit refresh no longer reads every project's whole history.

The board reads every open card but only the five most recently closed ones (the rest are counted); the project card,
activity feed and pending cards are built from the open cards, the latest closed one and the shown card's Work only.
What the user sees must be the same as when the whole history is read.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from auto_pm.application.core.pm_cockpit_service import _BOARD_CLOSED_SHOWN, PmCockpitService
from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.mission import MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from tests.core.test_mission_park_store import PROJECT
from tests.core.test_mission_switch_service import Switch, sw  # noqa: F401  (fixture)
from tests.core.test_pm_cockpit_mission_board import MAPPING


def _close_old_cards(scene: Switch, count: int) -> None:
    for number in range(count):
        mission = scene.missions.create(
            mission_id=f"MISSION-OLD{number}",
            subject_project_id=PROJECT,
            title=f"old {number}",
            objective="done long ago",
            acceptance_criteria=["closed"],
            authority=scene.store.get_mission("MISSION-A").authority,
            created_by="test",
            idempotency_key=f"create-old-{number}",
        )
        scene.clock.value = scene.clock.value + timedelta(minutes=1)
        scene.missions.transition(
            mission_id=mission.mission_id,
            expected_version=mission.version,
            new_state=MissionState.CANCELLED,
            root_work_id=None,
            idempotency_key=f"cancel-old-{number}",
        )


def _service(scene: Switch) -> PmCockpitService:
    return PmCockpitService(scene.root, store=scene.store, now=scene.clock)


def _counting_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    read: list[str] = []
    original = ContinuityStore._get_mission

    def counted(conn: Any, mission_id: str) -> Any:
        read.append(mission_id)
        return original(conn, mission_id)

    monkeypatch.setattr(ContinuityStore, "_get_mission", staticmethod(counted))
    return read


# ------------------------------------------------------------------ the board


def test_the_board_reads_only_the_latest_closed_cards_and_counts_the_rest(
    sw: Switch, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    sw.second_card()
    sw.park_a()
    _close_old_cards(sw, 12)
    full = sw.store.list_missions_by_board(PROJECT)
    read = _counting_reads(monkeypatch)

    limited = sw.store.list_missions_by_board(PROJECT, closed_limit=_BOARD_CLOSED_SHOWN)

    assert len(read) == 2 + _BOARD_CLOSED_SHOWN  # two open cards and five closed ones, not fourteen
    assert (limited.active, limited.waiting, limited.parked) == (full.active, full.waiting, full.parked)
    assert limited.closed == full.closed[:_BOARD_CLOSED_SHOWN] and limited.closed_hidden == 7
    assert full.closed_hidden == 0 and limited.open_count == full.open_count == 2


def test_the_cockpit_board_is_the_same_as_from_the_whole_history(
    sw: Switch, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    _close_old_cards(sw, 7)
    service = _service(sw)
    monkeypatch.setattr(service, "_mappings", lambda: (MAPPING,))

    full = service._board(MAPPING, sw.store.list_missions_by_board(PROJECT))
    limited = service._board(
        MAPPING, sw.store.list_missions_by_board(PROJECT, closed_limit=_BOARD_CLOSED_SHOWN)
    )

    assert limited == full and (len(limited.closed), limited.closed_hidden) == (5, 2)
    read = _counting_reads(monkeypatch)
    assert service.snapshot().boards[0] == full
    # The refresh never opens the old closed cards that are only counted, neither for the board nor the project card.
    assert read and not {"MISSION-OLD0", "MISSION-OLD1"} & set(read)


@pytest.mark.parametrize("closed", [0, 3, 5])
def test_nothing_is_hidden_when_there_are_no_more_closed_cards_than_shown(
    sw: Switch, closed: int  # noqa: F811
) -> None:
    _close_old_cards(sw, closed)
    board = sw.store.list_missions_by_board(PROJECT, closed_limit=_BOARD_CLOSED_SHOWN)
    assert (len(board.closed), board.closed_hidden) == (closed, 0)


# ------------------------------------------------------------------ the store's history limit


def test_the_terminal_limit_keeps_every_open_card_and_the_newest_finished_ones(sw: Switch) -> None:  # noqa: F811
    sw.second_card()
    _close_old_cards(sw, 4)
    full = sw.store.list_missions(PROJECT, include_terminal=True)

    for limit in (0, 1, 2, 10):
        limited = sw.store.list_missions(PROJECT, include_terminal=True, terminal_limit=limit)
        finished = [item for item in full if item.state is MissionState.CANCELLED][:limit]
        expected = [item for item in full if item.state is not MissionState.CANCELLED or item in finished]
        assert list(limited) == expected  # same order as the full history


@pytest.mark.parametrize("bad", [-1, True, 1.5])
def test_a_bad_terminal_limit_is_refused(sw: Switch, bad: Any) -> None:  # noqa: F811
    with pytest.raises(ContinuityStoreError, match="terminal_limit"):
        sw.store.list_missions(PROJECT, include_terminal=True, terminal_limit=bad)
    with pytest.raises(ContinuityStoreError, match="terminal_limit"):
        sw.store.list_works(PROJECT, include_terminal=True, terminal_limit=bad)


# ------------------------------------------------------------------ the project card


def _same_screen(scene: Switch) -> None:
    service = _service(scene)
    full = service._facts(PROJECT)
    focused = service._snapshot_facts(PROJECT)
    notices_full: list[str] = []
    notices_focused: list[str] = []

    assert service._card(MAPPING, focused) == service._card(MAPPING, full)
    assert service._activities(PROJECT, focused) == service._activities(PROJECT, full)
    assert service._pending_cards(MAPPING, focused, notices_focused) == service._pending_cards(
        MAPPING, full, notices_full
    )
    assert notices_focused == notices_full


def test_the_project_card_is_the_same_with_a_card_in_hand(sw: Switch) -> None:  # noqa: F811
    _close_old_cards(sw, 6)
    _same_screen(sw)


def test_the_project_card_is_the_same_with_a_card_parked_and_another_waiting(sw: Switch) -> None:  # noqa: F811
    sw.second_card()
    sw.park_a()
    _close_old_cards(sw, 6)
    _same_screen(sw)


def test_the_project_card_is_the_same_after_switching_to_another_card(sw: Switch) -> None:  # noqa: F811
    sw.b_in_hand()
    _close_old_cards(sw, 3)
    _same_screen(sw)


def test_the_project_card_is_the_same_when_every_card_is_closed(sw: Switch) -> None:  # noqa: F811
    _close_old_cards(sw, 3)
    mission = sw.store.get_mission("MISSION-A")
    sw.store.transition_mission(
        mission.mission_id, mission.version, MissionState.CANCELLED, mission.root_work_id,
        "cancel-a", sw.clock().isoformat(),
    )
    sw.clock.value = sw.clock.value + timedelta(minutes=1)
    focused = _service(sw)._snapshot_facts(PROJECT)
    assert [item.mission_id for item in focused.missions] == ["MISSION-A"]  # only the newest closed card is read
    _same_screen(sw)


def test_the_project_card_is_the_same_when_the_shown_cards_work_is_finished_too(sw: Switch) -> None:  # noqa: F811
    """The closed card's root Work is no longer an unfinished Work, so the snapshot reads it by id."""

    sw.execution.transition_run("RUN-001", RunState.FAILED, "agent-a", "lease-secret", "fail-run-1")
    sw.works.transition("WORK-001", WorkState.CANCELLED, "cancel-work-1")
    mission = sw.store.get_mission("MISSION-A")
    sw.store.transition_mission(
        mission.mission_id, mission.version, MissionState.CANCELLED, mission.root_work_id,
        "cancel-a", sw.clock().isoformat(),
    )
    focused = _service(sw)._snapshot_facts(PROJECT)
    assert [work.work_id for work in focused.works] == ["WORK-001"] and set(focused.runs_by_work) == {"WORK-001"}
    _same_screen(sw)


def test_the_snapshot_reads_only_the_runs_of_the_shown_work(sw: Switch) -> None:  # noqa: F811
    sw.b_in_hand()
    focused = _service(sw)._snapshot_facts(PROJECT)
    full = _service(sw)._facts(PROJECT)
    assert set(full.runs_by_work) == {"WORK-001", "WORK-002"}
    assert set(focused.runs_by_work) == {"WORK-002"}
