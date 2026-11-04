"""Triage desk, full version: the suggested order, the next legal step and the promise that it only reads (TD-SW008-066).

The inbox side runs on a real workspace with a real Continuity Store; the card side is a stub board, so each rule
can be driven without building missions.  ``tests/cli/test_pm_triage.py`` drives the same service with real cards.
"""

from __future__ import annotations

import importlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from auto_pm.application.core.mission_switch_service import MissionSwitchError, MissionSwitchService
from auto_pm.application.core.pm_triage_service import (
    PmTriageError,
    PmTriageService,
    suggested_order_key,
)
from auto_pm.contracts.intake import Disposition, IntakeItem, IntakeKind, UrgentCriterion
from auto_pm.contracts.triage import CONFIRMED_STALE_DAYS, PROPOSED_STALE_DAYS

_intake_tests = importlib.import_module("tests.core.test_pm_intake_service")
Desk = _intake_tests.Desk
_build_desk = _intake_tests._build_desk
PROJECT = _intake_tests.PYTHON_PROJECT

pytestmark = pytest.mark.usefixtures("identity_guard_off")


def _card(mission_id: str, state: str = "ACTIVE", title: str = "第1道收尾") -> Any:
    return SimpleNamespace(mission_id=mission_id, title=title, state=SimpleNamespace(value=state))


def _parked(mission_id: str, parked_at: datetime) -> Any:
    return SimpleNamespace(
        mission=_card(mission_id, "PARKED", "搁着的卡"), park=SimpleNamespace(parked_at=parked_at)
    )


class _Board:
    """The only thing the triage service asks the card side: the four columns of one project."""

    def __init__(self, *, active: tuple[Any, ...] = (), waiting: tuple[Any, ...] = (), parked: tuple[Any, ...] = ()) -> None:
        self.active = active
        self.waiting = waiting
        self.parked = parked

    def board(self, _project_id: str) -> Any:
        return self


@pytest.fixture
def desk(tmp_path: Path) -> Any:
    return _build_desk(tmp_path)


def _service(desk: Any, board: _Board | None = None, *, days_later: float = 0) -> PmTriageService:
    return PmTriageService(
        desk.root,
        intake=desk.service,
        switch=cast(MissionSwitchService, board or _Board()),
        now=lambda: datetime.now(UTC) + timedelta(days=days_later),
    )


def _urgent(desk: Any, title: str = "急停按钮失效") -> IntakeItem:
    return cast(
        IntakeItem,
        desk.propose(
            title,
            kind=IntakeKind.URGENT,
            impact_scope=("SAFE",),
            ticket=desk.ticket(
                urgent_criterion=UrgentCriterion.SAFETY,
                disposition=Disposition.INTERRUPT_NOW,
                rationale="设备安全",
            ),
        ),
    )


def test_t01_an_empty_desk_reports_nothing_waiting(desk: Any) -> None:
    report = _service(desk).report(PROJECT)

    assert report.project_id == PROJECT
    assert (report.focus, report.decide_now, report.ready_queue, report.hints) == ((), (), (), ())


def test_t02_the_order_is_disposition_then_kind_then_first_come(desk: Any) -> None:
    change = desk.propose("改画面", kind=IntakeKind.CHANGE)
    bug = desk.propose("白屏", kind=IntakeKind.BUG)
    debt = desk.propose("清死代码", kind=IntakeKind.DEBT)
    iteration = desk.propose("做第 2 道", kind=IntakeKind.ITERATION)
    urgent = _urgent(desk)
    waits = desk.propose(
        "整理日志", kind=IntakeKind.BUG, ticket=desk.ticket(disposition=Disposition.INBOX_WAIT, rationale="不急")
    )
    rejected = desk.propose(
        "重复需求", kind=IntakeKind.BUG, ticket=desk.ticket(disposition=Disposition.REJECT, rationale="与旧条目重复")
    )

    report = _service(desk).report(PROJECT)

    # Same disposition (after_current): bug < iteration < debt < change; then inbox_wait; the recommended rejection last.
    assert [entry.item_id for entry in report.decide_now] == [
        urgent.item_id, bug.item_id, iteration.item_id, debt.item_id, change.item_id, waits.item_id, rejected.item_id,
    ]
    assert [entry.rank for entry in report.decide_now] == list(range(1, 8))
    assert report.ready_queue == ()


def test_t03_equal_kinds_keep_first_come_first_served(desk: Any) -> None:
    first = desk.propose("白屏 A")
    second = desk.propose("白屏 B")
    third = desk.propose("白屏 C")

    report = _service(desk).report(PROJECT)

    assert [entry.item_id for entry in report.decide_now] == [first.item_id, second.item_id, third.item_id]
    assert sorted(
        (third, first, second), key=suggested_order_key
    ) == [first, second, third]


def test_t04_an_unconfirmed_item_is_the_users_call_and_names_the_exact_hash(desk: Any) -> None:
    item = desk.propose()

    entry = _service(desk).report(PROJECT).decide_now[0]

    assert entry.needs_user is True
    assert entry.ticket_hash == item.ticket_hash
    assert f"inbox confirm {item.item_id} --ticket-hash {item.ticket_hash}" in entry.command
    assert "user-confirmation:<" in entry.command  # a placeholder: the desk never invents the user's words
    assert "用户的决定" not in entry.next_step and "等你决定" in entry.next_step


def test_t05_a_recommended_rejection_is_offered_as_reject_never_as_confirm(desk: Any) -> None:
    item = desk.propose(
        "重复需求", ticket=desk.ticket(disposition=Disposition.REJECT, rationale="与旧条目重复")
    )

    entry = _service(desk).report(PROJECT).decide_now[0]

    assert f"inbox reject {item.item_id}" in entry.command and "inbox confirm" not in entry.command


def test_t06_a_confirmed_item_moves_to_the_ready_queue_with_a_plan_step_when_nothing_is_running(desk: Any) -> None:
    item = desk.confirm(desk.propose())

    report = _service(desk).report(PROJECT)

    assert report.decide_now == ()
    entry = report.ready_queue[0]
    assert (entry.item_id, entry.needs_user) == (item.item_id, False)
    assert f"--inbox-id {item.item_id}" in entry.command and f"--project-id {PROJECT}" in entry.command


def test_t07_while_a_card_runs_a_normal_item_waits_and_has_no_command(desk: Any) -> None:
    desk.confirm(desk.propose())

    entry = _service(desk, _Board(active=(_card("MISSION-A"),))).report(PROJECT).ready_queue[0]

    assert "MISSION-A" in entry.next_step and "收口之后" in entry.next_step
    assert (entry.command, entry.needs_user) == ("", False)


def test_t08_an_urgent_item_may_interrupt_only_with_the_users_word(desk: Any) -> None:
    item = desk.confirm(_urgent(desk))

    entry = _service(desk, _Board(active=(_card("MISSION-A"),))).report(PROJECT).ready_queue[0]

    assert entry.item_id == item.item_id and entry.needs_user is True
    assert "先做它" in entry.next_step and "pm switch" in entry.next_step
    assert "--inbox-id" in entry.command
    assert "SAFETY" in entry.reason  # the objective criterion travels with the suggestion


def test_t09_the_confirmed_items_are_ordered_like_the_proposed_ones(desk: Any) -> None:
    bug = desk.confirm(desk.propose("白屏", kind=IntakeKind.BUG))
    change = desk.confirm(desk.propose("改画面", kind=IntakeKind.CHANGE))
    urgent = desk.confirm(_urgent(desk))

    report = _service(desk).report(PROJECT)

    assert [entry.item_id for entry in report.ready_queue] == [urgent.item_id, bug.item_id, change.item_id]


def test_t10_old_items_are_flagged_but_never_expired(desk: Any) -> None:
    waiting = desk.propose("等了很久的")
    confirmed = desk.confirm(desk.propose("确认后没人排的"))

    fresh = _service(desk).report(PROJECT)
    late = _service(desk, days_later=CONFIRMED_STALE_DAYS + 1).report(PROJECT)

    assert not any(entry.stale for entry in fresh.decide_now + fresh.ready_queue) and fresh.hints == ()
    assert late.decide_now[0].stale and late.ready_queue[0].stale
    assert late.decide_now[0].waiting_days == CONFIRMED_STALE_DAYS + 1
    assert any(waiting.item_id in hint and str(PROPOSED_STALE_DAYS) in hint for hint in late.hints)
    assert any(confirmed.item_id in hint for hint in late.hints)
    # The limit itself is not "over": exactly 3 days (7 for a confirmed item) is still fine.
    edge = _service(desk, days_later=PROPOSED_STALE_DAYS).report(PROJECT)
    assert not edge.decide_now[0].stale and edge.hints == ()
    assert not _service(desk, days_later=CONFIRMED_STALE_DAYS).report(PROJECT).ready_queue[0].stale
    # Between the two limits only the item waiting for a decision is flagged.
    middle = _service(desk, days_later=PROPOSED_STALE_DAYS + 1).report(PROJECT)
    assert middle.decide_now[0].stale and not middle.ready_queue[0].stale


def test_t11_the_cards_are_listed_by_column_and_stale_parked_ones_get_a_hint(desk: Any) -> None:
    now = datetime.now(UTC)
    board = _Board(
        active=(_card("MISSION-A"),),
        waiting=(_card("MISSION-W", "BLOCKED"),),
        parked=(_parked("MISSION-P", now - timedelta(days=9)), _parked("MISSION-Q", now - timedelta(days=2))),
    )

    report = _service(desk, board).report(PROJECT)

    assert [(card.mission_id, card.column, card.stale) for card in report.focus] == [
        ("MISSION-A", "ACTIVE", False),
        ("MISSION-W", "WAITING", False),
        ("MISSION-P", "PARKED", True),
        ("MISSION-Q", "PARKED", False),
    ]
    assert report.focus[2].parked_days == 9
    assert any("MISSION-P" in hint and "不要自己作废" in hint for hint in report.hints)
    assert any("MISSION-W" in hint for hint in report.hints)
    assert not any("MISSION-Q" in hint for hint in report.hints)


def test_t12_two_running_cards_are_reported_not_resolved(desk: Any) -> None:
    board = _Board(active=(_card("MISSION-A"), _card("MISSION-B")))

    report = _service(desk, board).report(PROJECT)

    assert any("MISSION-A" in hint and "MISSION-B" in hint and "不要自己判断" in hint for hint in report.hints)


def test_t13_reading_never_changes_a_single_row(desk: Any) -> None:
    desk.propose("A")
    desk.confirm(desk.propose("B"))
    db = desk.root / ".auto-pm" / "continuity.db"

    def dump() -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(db)) as conn:
            names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return [(name, *conn.execute(f"SELECT * FROM {name}").fetchall()) for name in names]  # noqa: S608

    before = dump()
    service = _service(desk, days_later=30)
    first = service.report(PROJECT)
    again = service.report(PROJECT)

    assert dump() == before
    assert first == again


def test_t14_a_workspace_without_a_ledger_has_no_cards_and_no_items(tmp_path: Path) -> None:
    service = PmTriageService(tmp_path)

    report = service.report("SW-2026-901")

    assert report.focus == () and report.decide_now == () and report.ready_queue == ()
    assert not (tmp_path / ".auto-pm" / "continuity.db").exists()


def test_t15_an_unreadable_board_is_a_refusal_not_an_empty_view(desk: Any) -> None:
    class _Broken:
        def board(self, _project_id: str) -> Any:
            raise MissionSwitchError("未知或未来 Continuity Store schema: 9.9")

    service = PmTriageService(desk.root, intake=desk.service, switch=cast(MissionSwitchService, _Broken()))

    with pytest.raises(PmTriageError, match="schema"):
        service.report(PROJECT)
