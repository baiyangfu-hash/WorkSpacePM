"""TD-SW008-022: an old, finished Mission that the current model cannot read must not fail the Mission listings."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing

import pytest

from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_cockpit_snapshot_history_limit import _close_old_cards
from tests.core.test_mission_park_store import PROJECT
from tests.core.test_mission_switch_service import Switch, sw  # noqa: F401  (fixture)

OLD = "MISSION-OLD0"


def _break_record(scene: Switch, mission_id: str) -> None:
    """Make the stored authority of a Mission something the Mission model rejects (a record older than the model)."""
    with closing(sqlite3.connect(scene.store.db_path)) as conn:
        conn.execute("UPDATE mission_items SET authority_json=? WHERE mission_id=?", ('{"obsolete": true}', mission_id))
        conn.commit()


def _ids(missions: tuple[object, ...]) -> list[str]:
    return sorted(str(getattr(mission, "mission_id")) for mission in missions)  # noqa: B009


def test_a_finished_mission_that_no_longer_validates_is_left_out_of_the_listing(
    sw: Switch, caplog: pytest.LogCaptureFixture  # noqa: F811
) -> None:
    _close_old_cards(sw, 3)
    _break_record(sw, OLD)

    with caplog.at_level(logging.WARNING, logger="auto_pm.infrastructure.continuity_store"):
        listed = sw.store.list_missions(PROJECT, include_terminal=True)

    assert OLD not in _ids(listed)
    assert {"MISSION-A", "MISSION-OLD1", "MISSION-OLD2"} <= set(_ids(listed))
    assert any(OLD in record.getMessage() for record in caplog.records)


def test_the_limited_history_listing_survives_it_too(sw: Switch) -> None:  # noqa: F811
    _close_old_cards(sw, 4)
    _break_record(sw, OLD)

    listed = sw.store.list_missions(PROJECT, include_terminal=True, terminal_limit=10)

    assert OLD not in _ids(listed) and "MISSION-A" in _ids(listed)


def test_the_board_survives_it_and_shows_the_cards_that_do_validate(sw: Switch) -> None:  # noqa: F811
    _close_old_cards(sw, 3)
    _break_record(sw, OLD)

    board = sw.store.list_missions_by_board(PROJECT)
    limited = sw.store.list_missions_by_board(PROJECT, closed_limit=10)

    for shown in (board, limited):
        assert OLD not in _ids(tuple(shown.closed))
        assert {"MISSION-OLD1", "MISSION-OLD2"} <= set(_ids(tuple(shown.closed)))


def test_an_unfinished_mission_that_no_longer_validates_still_fails_the_listing(sw: Switch) -> None:  # noqa: F811
    _break_record(sw, "MISSION-A")

    with pytest.raises(ValueError):
        sw.store.list_missions(PROJECT)
    with pytest.raises(ValueError):
        sw.store.list_missions_by_board(PROJECT)


def test_reading_one_unreadable_finished_mission_directly_still_fails(sw: Switch) -> None:  # noqa: F811
    """Only the listings tolerate history; asking for that very Mission is still an error, never a silent gap."""
    _close_old_cards(sw, 1)
    _break_record(sw, OLD)

    with pytest.raises(ValueError):
        sw.store.get_mission(OLD)


def test_nothing_is_skipped_when_every_record_validates(sw: Switch) -> None:  # noqa: F811
    _close_old_cards(sw, 3)

    listed = sw.store.list_missions(PROJECT, include_terminal=True)

    assert {OLD, "MISSION-OLD1", "MISSION-OLD2", "MISSION-A"} <= set(_ids(listed))
    assert isinstance(sw.store, ContinuityStore)
