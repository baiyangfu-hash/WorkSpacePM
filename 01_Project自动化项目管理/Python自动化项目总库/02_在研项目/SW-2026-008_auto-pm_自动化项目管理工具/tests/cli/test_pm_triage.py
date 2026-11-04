"""``pm triage`` on the command line: the real entry point, real inbox items and real cards (TD-SW008-066, full version)."""

from __future__ import annotations

import importlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from auto_pm.contracts.intake import (
    Disposition,
    IntakeClassification,
    IntakeKind,
    IntakeStatus,
    TriageTicket,
    UrgentCriterion,
)
from auto_pm.infrastructure.intake_store import IntakeStore
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")

_inbox = importlib.import_module("tests.cli.test_pm_inbox")
_facade = importlib.import_module("tests.cli.test_pm_facade")
_switch_tests = importlib.import_module("tests.core.test_mission_switch_service")
PROJECT = _inbox.PROJECT


def _triage(runner: CliRunner, root: Path, project: str = PROJECT, *extra: str) -> Result:
    return runner.invoke(cli, ["-w", str(root), "pm", "triage", project, *extra])


def _report(runner: CliRunner, root: Path, project: str = PROJECT) -> dict[str, Any]:
    result = _triage(runner, root, project, "--json")
    assert result.exit_code == 0, result.output
    report: dict[str, Any] = json.loads(result.output)
    assert report["schema_version"] == "pm-triage.v1"
    return report


def _events(root: Path) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    _facade._setup_planning(tmp_path)
    return tmp_path


def test_c01_the_command_is_registered_and_documents_that_it_only_reads(cli_runner: CliRunner, workspace: Path) -> None:
    helped = cli_runner.invoke(cli, ["-w", str(workspace), "pm", "triage", "--help"])

    assert helped.exit_code == 0
    assert "只读" in helped.output and "--json" in helped.output


def test_c02_items_added_through_the_cli_come_back_in_suggested_order(cli_runner: CliRunner, workspace: Path) -> None:
    change = _inbox._item(_inbox._add(cli_runner, workspace, request_id="R1", title="改画面", kind="change", change_action="modify"))
    bug = _inbox._item(_inbox._add(cli_runner, workspace, request_id="R2", title="白屏", kind="bug"))
    urgent = _inbox._item(
        _inbox._add(
            cli_runner, workspace, request_id="R3", title="急停失效", kind="urgent", urgent_criterion="safety",
            impact_scope=["SAFE"], disposition="interrupt_now", rationale="设备安全",
        )
    )
    _inbox._decide(cli_runner, workspace, "confirm", bug)

    report = _report(cli_runner, workspace)

    assert [entry["item_id"] for entry in report["decide_now"]] == [urgent["item_id"], change["item_id"]]
    assert [entry["item_id"] for entry in report["ready_queue"]] == [bug["item_id"]]
    assert report["decide_now"][0]["ticket_hash"] == urgent["ticket_hash"]
    assert report["focus"] == []


def test_c03_the_text_view_lists_rank_reason_and_next_step_in_plain_words(cli_runner: CliRunner, workspace: Path) -> None:
    item = _inbox._item(_inbox._add(cli_runner, workspace))

    result = _triage(cli_runner, workspace)

    assert result.exit_code == 0, result.output
    text = result.output
    assert f"1. {item['item_id']} [bug 修复] 登录页偶发白屏" in text
    assert "理由:" in text and "下一步:" in text and "【用户的决定】" in text
    assert f"inbox confirm {item['item_id']} --ticket-hash {item['ticket_hash']}" in text
    assert "已确认待排的条目: 无" in text and "开着的卡: 无" in text
    assert "这只是建议" in text


def test_c04_triage_writes_nothing_and_leaves_every_item_undecided(cli_runner: CliRunner, workspace: Path) -> None:
    item = _inbox._item(_inbox._add(cli_runner, workspace))
    events = _events(workspace)

    _triage(cli_runner, workspace)
    _triage(cli_runner, workspace, PROJECT, "--json")

    assert _events(workspace) == events
    assert _inbox._listed(cli_runner, workspace)[0]["status"] == IntakeStatus.PROPOSED.value
    assert _inbox._item(_inbox._run(cli_runner, workspace, "inbox", "show", item["item_id"]))["status"] == "PROPOSED"


def test_c05_another_project_sees_none_of_the_items(cli_runner: CliRunner, workspace: Path) -> None:
    _inbox._add(cli_runner, workspace)

    report = _report(cli_runner, workspace, "SW-OTHER-001")

    assert report["decide_now"] == [] and report["ready_queue"] == []


def test_c06_a_fresh_workspace_is_answered_without_creating_the_ledger(cli_runner: CliRunner, workspace: Path) -> None:
    (workspace / ".auto-pm" / "continuity.db").unlink()

    result = _triage(cli_runner, workspace)

    assert result.exit_code == 0, result.output
    assert not (workspace / ".auto-pm" / "continuity.db").exists()
    assert "开着的卡: 无" in result.output and "等你决定的条目: 无" in result.output


def test_c07_real_cards_show_up_beside_the_items_and_a_normal_item_waits_for_the_running_card(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in _switch_tests.AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)
    scene = _switch_tests.Switch(tmp_path / "ws")
    project = _switch_tests.PROJECT
    store = IntakeStore(scene.root)
    bug, _ = store.add_item(
        request_id="REQ-T-1", project_id=project, title="白屏", proposed_by="pm-test",
        classification=IntakeClassification(kind=IntakeKind.BUG, domain="SCPT"),
        ticket=_ticket(Disposition.AFTER_CURRENT),
    )
    urgent, _ = store.add_item(
        request_id="REQ-T-2", project_id=project, title="急停失效", proposed_by="pm-test",
        classification=IntakeClassification(kind=IntakeKind.URGENT, domain="PLC", impact_scope=("SAFE",)),
        ticket=_ticket(Disposition.INTERRUPT_NOW, urgent_criterion=UrgentCriterion.SAFETY),
    )
    for item in (bug, urgent):
        store.decide_item(
            item.item_id, status=IntakeStatus.CONFIRMED, ticket_hash=item.ticket_hash,
            decided_by="fubai", decision_ref="user-confirmation:chat-1",
        )

    running = _report(cli_runner, scene.root, project)
    scene.park_a()
    parked = _report(cli_runner, scene.root, project)

    assert [(card["mission_id"], card["column"]) for card in running["focus"]] == [("MISSION-A", "ACTIVE")]
    assert [entry["item_id"] for entry in running["ready_queue"]] == [urgent.item_id, bug.item_id]
    urgent_step, bug_step = (entry["next_step"] for entry in running["ready_queue"])
    assert "先做它" in urgent_step and "MISSION-A" in bug_step and "收口之后" in bug_step
    assert [(card["mission_id"], card["column"]) for card in parked["focus"]] == [("MISSION-A", "PARKED")]
    # Nothing runs any more, so both are ready to be planned.
    assert all("--inbox-id" in entry["command"] for entry in parked["ready_queue"])


def _ticket(disposition: Disposition, **changes: Any) -> TriageTicket:
    values: dict[str, Any] = {
        "original_words": "登录页偶发白屏",
        "affects": "SW-2026-008 登录页",
        "duplicate_check": "查过台账与收件箱，没有同类条目",
        "evidence": ("file:README.md",),
        "disposition": disposition,
        "rationale": "分诊建议",
        "alternatives": ("并入下个迭代",),
        "cost_risk": "半天；低风险",
    }
    values.update(changes)
    return TriageTicket(**values)
