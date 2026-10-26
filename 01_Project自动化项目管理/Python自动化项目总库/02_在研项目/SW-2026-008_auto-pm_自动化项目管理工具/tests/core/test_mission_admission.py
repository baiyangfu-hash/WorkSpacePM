"""TD-071 card 3: a project admits up to eight open cards; a colliding or a ninth card needs the user's word.

Pure admission rules, the cockpit's choice of the card it shows, and the overlap reminder when a card is picked back up.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from auto_pm.core.mission_admission import admission_verdict, scope_overlaps
from auto_pm.core.pm_cockpit_service import PmCockpitService

from auto_pm.contracts.mission import OPEN_MISSION_SOFT_LIMIT, Mission, MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStoreError
from tests.core.test_mission_park_store import APPROVAL
from tests.core.test_mission_switch_service import A_FILE, Switch, sw  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("identity_guard_off")


def _card(
    mission_id: str, state: MissionState = MissionState.DRAFT, *paths: str, title: str = ""
) -> Mission:
    return cast(
        Mission,
        SimpleNamespace(
            mission_id=mission_id,
            title=title or mission_id,
            state=state,
            authority=SimpleNamespace(scope_paths=paths),
        ),
    )


# ------------------------------------------------------------------ admission rules


def test_the_soft_limit_is_eight_and_the_ninth_card_needs_the_users_word() -> None:
    assert OPEN_MISSION_SOFT_LIMIT == 8
    seven = [_card(f"M-{n}", MissionState.DRAFT, f"src/{n}.py") for n in range(7)]
    assert not admission_verdict(seven, ["src/new.py"]).needs_user_release
    eight = [*seven, _card("M-7", MissionState.PARKED, "src/7.py")]
    verdict = admission_verdict(eight, ["src/new.py"])
    assert verdict.over_limit and verdict.needs_user_release and verdict.overlaps == ()
    assert "8 张" in verdict.reason() and "放行" in verdict.reason()


def test_closed_cards_do_not_count_and_do_not_collide() -> None:
    finished = [
        _card(f"M-{state.value}", state, "src/a.py")
        for state in (MissionState.ACCEPTED, MissionState.CLOSED, MissionState.CANCELLED)
    ]
    verdict = admission_verdict(finished, ["src/a.py"])
    assert verdict.open_count == 0 and verdict.overlaps == () and not verdict.needs_user_release


@pytest.mark.parametrize(
    ("new", "mine", "hit"),
    [
        ("src/a.py", "src/a.py", True),
        ("src", "src/a.py", True),  # a folder covers the files inside it, both ways round
        ("src/a.py", "src", True),
        ("src/ab.py", "src/a.py", False),  # a shared prefix of a name is not an overlap
        ("src2/a.py", "src/a.py", False),
        ("docs/a.md", "src/a.py", False),
        ("src2", "src", False),
    ],
)
def test_overlap_is_by_whole_path_parts_in_both_directions(new: str, mine: str, hit: bool) -> None:
    assert bool(scope_overlaps([new], _card("M-OPEN", MissionState.ACTIVE, mine))) is hit


def test_a_collision_names_every_open_card_it_hits_in_a_stable_order() -> None:
    open_cards = [
        _card("M-B", MissionState.PARKED, "src/a.py", title="急改 IO 表"),
        _card("M-A", MissionState.ACTIVE, "src", title="报警汇总"),
        _card("M-C", MissionState.ACTIVE, "docs"),
    ]
    verdict = admission_verdict(open_cards, ["src/a.py", "tests/test_a.py"])
    assert [(item.mission_id, item.paths) for item in verdict.overlaps] == [
        ("M-A", ("src/a.py",)),
        ("M-B", ("src/a.py",)),
    ]
    assert (
        "报警汇总" in verdict.reason()
        and "急改 IO 表" in verdict.reason()
        and not verdict.over_limit
    )


# ------------------------------------------------------------------ the cockpit's card


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (
            (MissionState.CLOSED, MissionState.PARKED, MissionState.DRAFT, MissionState.ACTIVE),
            "M-3",
        ),
        ((MissionState.CLOSED, MissionState.PARKED, MissionState.BLOCKED), "M-2"),
        ((MissionState.CLOSED, MissionState.PARKED), "M-1"),
        ((MissionState.CLOSED, MissionState.CANCELLED), "M-0"),
    ],
)
def test_the_cockpit_shows_the_card_in_hand_then_one_waiting_then_a_parked_one(
    states: tuple[MissionState, ...], expected: str
) -> None:
    missions = tuple(_card(f"M-{n}", state) for n, state in enumerate(states))
    chosen = PmCockpitService._primary_mission(missions)
    assert chosen is not None and chosen.mission_id == expected


# ------------------------------------------------------------------ overlap reminder on unpark


def _release_b_over_a(scene: Switch) -> None:
    scene.store.record_mission_admission(
        mission_id="MISSION-B",
        open_count=1,
        over_limit=False,
        overlaps=(("MISSION-A", (A_FILE,)),),
        release_ref="user-confirmation:TD071-OVERLAP",
        idempotency_key="admit-MISSION-B",
        now=scene.clock.value.isoformat(),
    )


def test_picking_a_card_back_up_reminds_to_sync_the_card_it_overlaps(sw: Switch) -> None:  # noqa: F811
    sw.second_card()
    _release_b_over_a(sw)
    _release_b_over_a(sw)  # the same release again is a no-op
    assert sw.store.list_mission_overlaps("MISSION-A") == (("MISSION-B", (A_FILE,)),)
    assert sw.store.list_mission_overlaps("MISSION-B") == (("MISSION-A", (A_FILE,)),)
    sw.park_a()

    outcome = sw.service.unpark(
        mission_id="MISSION-A", as_owner="claude:local", approval_evidence_ref=APPROVAL
    )

    assert outcome.overlaps == (("MISSION-B", (A_FILE,)),)


def test_the_cli_prints_the_overlap_note_on_unpark(sw: Switch) -> None:  # noqa: F811
    sw.second_card()
    _release_b_over_a(sw)
    sw.park_a()
    back = sw.cli(
        "pm",
        "unpark",
        "--mission-id",
        "MISSION-A",
        "--as",
        "claude:local",
        "--approval-evidence-ref",
        APPROVAL,
        "--holder-pid",
        "none",
    )
    assert back.exit_code == 0, back.output
    notes: list[Any] = json.loads(back.output)["overlap_note"]
    assert len(notes) == 1 and "MISSION-B" in notes[0] and A_FILE in notes[0]


def test_a_release_record_cannot_be_replayed_with_other_content(sw: Switch) -> None:  # noqa: F811
    sw.second_card()
    _release_b_over_a(sw)
    with pytest.raises(ContinuityStoreError, match="语义不一致"):
        sw.store.record_mission_admission(
            mission_id="MISSION-B",
            open_count=9,
            over_limit=True,
            overlaps=(),
            release_ref="user-confirmation:OTHER-0001",
            idempotency_key="admit-MISSION-B",
            now=sw.clock.value.isoformat(),
        )
    with pytest.raises(ContinuityStoreError):
        sw.store.record_mission_admission(
            mission_id="MISSION-B",
            open_count=1,
            over_limit=False,
            overlaps=(),
            release_ref="",
            idempotency_key="admit-MISSION-B-empty",
            now=sw.clock.value.isoformat(),
        )


def test_overlap_follows_the_host_casing_rule() -> None:
    open_card = _card("M-OPEN", MissionState.ACTIVE, "src/Alarm.st")
    assert scope_overlaps(["SRC/alarm.ST"], open_card, windows=True) == (
        "SRC/alarm.ST",
    )  # Windows: one file
    assert scope_overlaps(["SRC/alarm.ST"], open_card, windows=False) == ()  # elsewhere: two files
