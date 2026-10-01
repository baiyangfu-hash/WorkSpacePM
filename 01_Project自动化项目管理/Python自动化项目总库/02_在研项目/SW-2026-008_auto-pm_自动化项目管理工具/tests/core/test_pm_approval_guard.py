"""U09B: a first approval is refused, before any write, while the project already has an unfinished task.

Real ContinuityStore, real ChangeService, real Git temp repository. Scenario numbers (g01..g05) follow card 039 section 5.3.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from auto_pm.contracts.mission import MissionState
from tests.core.test_pm_pending_scope_card import (
    OTHER_PROJECT,
    _add_project,
    _Env,
    _env,
)
from tests.core.test_pm_run_e2e import PROJECT_ID

if TYPE_CHECKING:
    from auto_pm.application.core.pm_facade_service import PmFacadeError
else:
    from auto_pm.core.pm_facade_service import PmFacadeError

_REFUSAL = "未终结的任务"


def _two_requests(tmp_path: Path) -> tuple[_Env, str, str]:
    """Two drafts of the same project, each with a persisted scope card."""

    env = _env(tmp_path)
    env.draft("REQ-GUARD-A")
    env.draft("REQ-GUARD-B")
    first = env.submit("REQ-GUARD-A").card
    second = env.submit("REQ-GUARD-B", risks=("risk of b",)).card
    return env, first.plan_hash, second.plan_hash


def _cancel_mission(env: _Env, mission_id: str, key: str) -> None:
    mission = env.store.get_mission(mission_id)
    env.facade._missions.transition(
        mission_id=mission_id,
        expected_version=mission.version,
        new_state=MissionState.CANCELLED,
        root_work_id=None,
        idempotency_key=key,
    )


def _snapshot(env: _Env, change_id: str) -> tuple[object, ...]:
    return (
        env.state(),
        env.chg_status(change_id),
        env.count("planning_draft_decision_bindings"),
        env.count("mission_items"),
        env.count("work_items"),
    )


def test_g01_a_second_approval_is_refused_while_the_first_task_is_open_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    env, first_hash, second_hash = _two_requests(tmp_path)
    env.approve("REQ-GUARD-A", first_hash)
    second_card = env.store.get_submitted_planning_scope_card("REQ-GUARD-B", second_hash).card
    before = _snapshot(env, second_card.change_id)

    with pytest.raises(PmFacadeError, match=_REFUSAL) as refused:
        env.approve("REQ-GUARD-B", second_hash)

    assert "MISSION-" not in str(refused.value)
    assert "WORK-" not in str(refused.value)
    assert _snapshot(env, second_card.change_id) == before
    pending = env.facade.list_pending_planning_scope_cards(PROJECT_ID)
    assert [item.card.request_id for item in pending] == ["REQ-GUARD-B"]
    overview = {item.draft.request_id: item.approved for item in env.facade.list_planning_drafts(PROJECT_ID)}
    assert overview == {"REQ-GUARD-A": True, "REQ-GUARD-B": False}
    assert env.chain_is_intact()


def test_g02_the_open_tasks_own_request_still_replays_idempotently(tmp_path: Path) -> None:
    env, first_hash, _second_hash = _two_requests(tmp_path)
    first = env.approve("REQ-GUARD-A", first_hash)
    counts = {
        table: env.count(table)
        for table in ("planning_draft_decision_bindings", "mission_items", "work_items", "events")
    }

    replay = env.approve("REQ-GUARD-A", first_hash)

    assert replay == first
    assert {table: env.count(table) for table in counts} == counts


def test_g03_after_the_first_task_is_cancelled_the_second_approval_builds_the_whole_chain(
    tmp_path: Path,
) -> None:
    env, first_hash, second_hash = _two_requests(tmp_path)
    first = env.approve("REQ-GUARD-A", first_hash)
    with pytest.raises(PmFacadeError, match=_REFUSAL):
        env.approve("REQ-GUARD-B", second_hash)
    _cancel_mission(env, first.mission_id, "u09b-g03-cancel")

    second = env.approve("REQ-GUARD-B", second_hash)

    assert second.request_id == "REQ-GUARD-B"
    assert second.mission_id != first.mission_id
    assert env.store.get_mission(second.mission_id).state is MissionState.DRAFT
    assert env.chg_status(second.change_id) == "approved"
    assert env.facade.recover_planning_scope_card(second.mission_id).plan_hash == second_hash
    assert env.facade.list_pending_planning_scope_cards(PROJECT_ID) == ()


def test_g04_an_open_task_of_another_project_does_not_block_this_project(tmp_path: Path) -> None:
    env = _env(tmp_path)
    _add_project(env.root, OTHER_PROJECT)
    # CHG numbers are allocated per project; advance the other project's sequence so the two cards
    # do not compete for the same globally unique candidate identifier.
    env.changes.create_change_request(
        project_id=OTHER_PROJECT,
        domain="SCPT",
        business_nature="DEF",
        impact_scope=["MODULE"],
        applicant="PM Facade",
        background="filler change that advances the sequence",
        necessity="isolate the two projects' candidate identifiers",
    )
    env.draft("REQ-GUARD-OTHER", project=OTHER_PROJECT)
    env.draft("REQ-GUARD-MINE")
    theirs = env.submit("REQ-GUARD-OTHER").card
    mine = env.submit("REQ-GUARD-MINE").card
    env.approve("REQ-GUARD-OTHER", theirs.plan_hash)
    assert len(env.store.list_missions(OTHER_PROJECT)) == 1

    approved = env.approve("REQ-GUARD-MINE", mine.plan_hash)

    assert approved.subject_project_id == PROJECT_ID
    assert len(env.store.list_missions(PROJECT_ID)) == 1
    assert len(env.store.list_missions(OTHER_PROJECT)) == 1


def test_g05_the_guard_runs_before_the_change_moves_and_a_later_approval_completes_the_steps(
    tmp_path: Path,
) -> None:
    env, first_hash, second_hash = _two_requests(tmp_path)
    first = env.approve("REQ-GUARD-A", first_hash)
    second_card = env.store.get_submitted_planning_scope_card("REQ-GUARD-B", second_hash).card
    assert env.chg_status(second_card.change_id) == "draft"

    with pytest.raises(PmFacadeError, match=_REFUSAL):
        env.approve("REQ-GUARD-B", second_hash)
    assert env.chg_status(second_card.change_id) == "draft"

    _cancel_mission(env, first.mission_id, "u09b-g05-cancel")
    env.approve("REQ-GUARD-B", second_hash)

    assert env.chg_status(second_card.change_id) == "approved"
