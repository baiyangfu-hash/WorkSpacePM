"""TD-071 card 4: the cockpit shows each project's cards in four read-only columns 在干 / 等你 / 搁着 / 已关."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from auto_pm.application.core.pm_cockpit_service import PmCockpitService
from auto_pm.contracts.mission import OPEN_MISSION_SOFT_LIMIT, MissionState
from auto_pm.contracts.pm_cockpit import PmCockpitMissionBoard
from auto_pm.contracts.workspace_context import WorkspaceProjectMapping
from tests.core.test_mission_park_store import PROJECT
from tests.core.test_mission_switch_service import Switch, sw  # noqa: F401  (fixture)
from tests.core.test_pm_cockpit_dual_root import PROJECT as DUAL_PROJECT
from tests.core.test_pm_cockpit_dual_root import _roots, _work

MAPPING = WorkspaceProjectMapping(
    project_id=PROJECT, project_root=f"{PROJECT}_示例项目", development_root=PROJECT
)


def _board(scene: Switch) -> PmCockpitMissionBoard:
    service = PmCockpitService(scene.root, store=scene.store, now=scene.clock)
    return service._board(MAPPING, scene.store.list_missions_by_board(PROJECT))


def test_a_parked_card_shows_why_it_was_put_down_and_where_it_stopped(sw: Switch) -> None:  # noqa: F811
    sw.second_card()
    sw.park_a()

    board = _board(sw)

    assert (board.open_count, board.open_limit, board.project_name) == (
        2,
        OPEN_MISSION_SOFT_LIMIT,
        "示例项目",
    )
    assert board.active == () and [card.mission_id for card in board.waiting] == ["MISSION-B"]
    parked = board.parked[0]
    assert parked.mission_id == "MISSION-A" and parked.state_label == "搁着（断点已记）"
    assert (
        "客户急改 IO 表" in parked.note and "OB1 改完，差测试" in parked.note and not parked.stale
    )
    assert "lease" not in board.model_dump_json()


def test_a_card_parked_for_more_than_seven_days_is_flagged(sw: Switch) -> None:  # noqa: F811
    sw.park_a()
    sw.clock.value = sw.clock.value + timedelta(days=8)

    parked = _board(sw).parked[0]

    assert parked.stale and "超过 7 天" in parked.note


def test_a_card_parked_exactly_seven_days_is_not_yet_flagged(sw: Switch) -> None:  # noqa: F811
    sw.park_a()
    sw.clock.value = sw.clock.value + timedelta(days=7)

    assert _board(sw).parked[0].stale is False


def test_the_card_in_hand_is_in_the_first_column(sw: Switch) -> None:  # noqa: F811
    board = _board(sw)
    assert [card.mission_id for card in board.active] == ["MISSION-A"] and board.parked == ()


def test_only_the_latest_closed_cards_are_listed(sw: Switch) -> None:  # noqa: F811
    for number in range(7):
        mission = sw.missions.create(
            mission_id=f"MISSION-OLD{number}",
            subject_project_id=PROJECT,
            title=f"old {number}",
            objective="done long ago",
            acceptance_criteria=["closed"],
            authority=sw.store.get_mission("MISSION-A").authority,
            created_by="test",
            idempotency_key=f"create-old-{number}",
        )
        sw.clock.value = sw.clock.value + timedelta(minutes=1)
        sw.missions.transition(
            mission_id=mission.mission_id,
            expected_version=mission.version,
            new_state=MissionState.CANCELLED,
            root_work_id=None,
            idempotency_key=f"cancel-old-{number}",
        )

    board = _board(sw)

    assert len(board.closed) == 5 and board.closed_hidden == 2
    assert board.closed[0].mission_id == "MISSION-OLD6"  # newest first


def test_the_snapshot_carries_one_board_per_registered_project(tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)
    _work(main, "WORK-BOARD-001")

    snapshot = PmCockpitService(main).snapshot()

    assert [board.project_id for board in snapshot.boards] == [DUAL_PROJECT]
    assert snapshot.boards[0].open_count == 0 and snapshot.boards[0].active == ()
