"""U09B / TD-071 card 3: a second approval is refused, before any write, while an open task changes the same files.

Card 039 refused any second open task; TD-071 card 3 admits up to eight open cards per project and stops only a card that
collides with an open one (or one past the soft limit) until the user's own word releases it. Both requests here change the
same files, so the old scenarios still hold as collision refusals. Real ContinuityStore, real ChangeService, real Git temp
repository. Scenario numbers (g01..g05) follow card 039 section 5.3; g06..g08 are card 3's.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
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

_REFUSAL = "要改同一批文件"
RELEASE = "user-confirmation:TD071-CARD3-RELEASE"


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

    # the refusal names the open card it collides with (so the user can switch to it) and nothing new was created
    first_mission = env.store.list_missions(PROJECT_ID)[0].mission_id
    assert first_mission in str(refused.value) and "SW-TEST-001/src/calc.py" in str(refused.value)
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


def test_g06_the_users_release_admits_the_colliding_card_and_records_the_overlap(tmp_path: Path) -> None:
    env, first_hash, second_hash = _two_requests(tmp_path)
    first = env.approve("REQ-GUARD-A", first_hash)

    second = env.approve("REQ-GUARD-B", second_hash, release=RELEASE)

    assert second.mission_id != first.mission_id
    assert {m.mission_id for m in env.store.list_missions(PROJECT_ID)} == {first.mission_id, second.mission_id}
    released = env.events("MISSION_ADMISSION_RELEASED")
    assert [aggregate for _kind, aggregate, _payload in released] == [second.mission_id]
    assert RELEASE in released[0][2] and first.mission_id in released[0][2]
    # the overlap is readable from both cards: unpark of either one reminds the agent to sync the other's changes
    assert [other for other, _paths in env.store.list_mission_overlaps(second.mission_id)] == [first.mission_id]
    assert [other for other, _paths in env.store.list_mission_overlaps(first.mission_id)] == [second.mission_id]


def test_g07_a_retry_of_a_released_approval_is_not_blocked_by_its_own_mission(tmp_path: Path) -> None:
    env, first_hash, second_hash = _two_requests(tmp_path)
    env.approve("REQ-GUARD-A", first_hash)
    second = env.approve("REQ-GUARD-B", second_hash, release=RELEASE)
    counts = {table: env.count(table) for table in ("mission_items", "work_items", "events")}

    assert env.approve("REQ-GUARD-B", second_hash) == second  # no release needed for the same request again
    assert {table: env.count(table) for table in counts} == counts


def test_g08_the_release_does_not_let_a_card_start_while_another_is_active(tmp_path: Path) -> None:
    from auto_pm.core.mission_service import MissionServiceError

    env, first_hash, second_hash = _two_requests(tmp_path)
    first = env.approve("REQ-GUARD-A", first_hash)
    second = env.approve("REQ-GUARD-B", second_hash, release=RELEASE)
    store = env.store

    roots = {first.mission_id: first.work_id, second.mission_id: second.work_id}

    def step(mission_id: str, state: MissionState, key: str) -> None:
        mission = store.get_mission(mission_id)
        env.facade._missions.transition(
            mission_id=mission_id,
            expected_version=mission.version,
            new_state=state,
            root_work_id=roots[mission_id] if state is MissionState.ACTIVE else None,
            idempotency_key=key,
        )

    step(first.mission_id, MissionState.AWAITING_APPROVAL, "g08-a-submit")
    step(first.mission_id, MissionState.ACTIVE, "g08-a-start")
    step(second.mission_id, MissionState.AWAITING_APPROVAL, "g08-b-submit")
    other = store.get_mission(second.mission_id)
    with pytest.raises(MissionServiceError, match=first.mission_id):
        env.facade._missions.transition(
            mission_id=other.mission_id,
            expected_version=other.version,
            new_state=MissionState.ACTIVE,
            root_work_id=second.work_id,
            idempotency_key="g08-b",
        )
    assert store.get_mission(second.mission_id).state is not MissionState.ACTIVE


def test_g09_past_the_soft_limit_the_users_release_admits_one_more_card(tmp_path: Path) -> None:
    from auto_pm.contracts.mission import OPEN_MISSION_SOFT_LIMIT

    env = _env(tmp_path)
    hashes = {}
    for number in range(OPEN_MISSION_SOFT_LIMIT + 1):
        request = f"REQ-LIMIT-{number}"
        env.draft(request)
        hashes[request] = env.submit(request, risks=(f"risk {number}",)).card.plan_hash
    for number in range(OPEN_MISSION_SOFT_LIMIT):  # all change the same files, so each one after the first needs the word
        env.approve(f"REQ-LIMIT-{number}", hashes[f"REQ-LIMIT-{number}"], release=RELEASE)
    ninth = f"REQ-LIMIT-{OPEN_MISSION_SOFT_LIMIT}"
    with pytest.raises(PmFacadeError, match=f"上限 {OPEN_MISSION_SOFT_LIMIT} 张"):
        env.approve(ninth, hashes[ninth])

    admitted = env.approve(ninth, hashes[ninth], release=RELEASE)

    assert len(env.store.list_missions(PROJECT_ID)) == OPEN_MISSION_SOFT_LIMIT + 1
    released = [payload for _kind, aggregate, payload in env.events("MISSION_ADMISSION_RELEASED") if aggregate == admitted.mission_id]
    assert len(released) == 1 and json.loads(released[0])["over_limit"] is True


OTHER_FILE = f"{PROJECT_ID}/docs/notes.md"


def test_g10_a_second_card_that_changes_other_files_needs_no_release(tmp_path: Path) -> None:
    """The positive control of g01: only a collision (or the limit) stops a second card, not the open card itself."""

    env = _env(tmp_path)
    env.draft("REQ-FREE-A")
    env.draft("REQ-FREE-B")
    first = env.approve("REQ-FREE-A", env.submit("REQ-FREE-A").card.plan_hash)
    second_hash = env.submit("REQ-FREE-B", risks=("risk of b",), scope=(OTHER_FILE,)).card.plan_hash

    second = env.approve("REQ-FREE-B", second_hash)

    assert second.mission_id != first.mission_id
    assert len(env.store.list_missions(PROJECT_ID)) == 2
    assert env.events("MISSION_ADMISSION_RELEASED") == []


def test_g11_a_retry_that_now_carries_the_release_records_it(tmp_path: Path) -> None:
    """If the release was not recorded when the card was created, the same approval with the release fills it in."""

    env, first_hash, second_hash = _two_requests(tmp_path)
    first = env.approve("REQ-GUARD-A", first_hash)
    second = env.approve("REQ-GUARD-B", second_hash, release=RELEASE)
    with closing(sqlite3.connect(env.db)) as conn, conn:
        conn.execute("DELETE FROM events WHERE event_type='MISSION_ADMISSION_RELEASED'")
    assert env.store.list_mission_overlaps(second.mission_id) == ()

    assert env.facade.materialize_planning_mission(
        env.store.get_submitted_planning_scope_card("REQ-GUARD-B", second_hash).card, admission_release_ref=RELEASE
    ).mission_id == second.mission_id

    assert [other for other, _paths in env.store.list_mission_overlaps(second.mission_id)] == [first.mission_id]


def test_g12_a_release_that_is_not_the_users_own_words_is_refused(tmp_path: Path) -> None:
    env, first_hash, second_hash = _two_requests(tmp_path)
    env.approve("REQ-GUARD-A", first_hash)
    second_card = env.store.get_submitted_planning_scope_card("REQ-GUARD-B", second_hash).card
    before = _snapshot(env, second_card.change_id)
    for words in ("agent-claude 自己放行", "user-confirmation:agent-claude-ok", "user-confirmation:x"):
        with pytest.raises(PmFacadeError, match="放行凭据不合格"):
            env.approve("REQ-GUARD-B", second_hash, release=words)
    assert _snapshot(env, second_card.change_id) == before
