"""PM front desk on the command line: the inbox, the triage ticket and the classified plan (card CARD-SW008-M2-P1, scenarios cx01-cx12).

Every test drives the real ``auto-pm`` entry point on a temporary Git workspace with a real Continuity Store.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner, Result

from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli.__main__ import cli
from tests.plan_checklist_support import checklist_args

pytestmark = pytest.mark.usefixtures("identity_guard_off")

# Reuse the existing PM CLI fixtures; imported dynamically so that this file is type-checked on its own.
_pm_facade_tests = importlib.import_module("tests.cli.test_pm_facade")
_git = _pm_facade_tests._git
_planning_args = _pm_facade_tests._planning_args
_setup_planning = _pm_facade_tests._setup_planning

PROJECT = "SW-TEST-001"
ANCHORED = "SW-2026-904"
APPROVER = "fubai"
CONFIRMATION = "user-confirmation:chat-20261005-c1"
SCOPE = [
    "--scope", "auto_pm/example.py", "--risk", "scope drift", "--non-goal", "no execution before approval",
    "--adapter", "codex", "--approved-model", "gpt-approved", "--declared-dirty", "auto_pm/example.py",
    *checklist_args(original="登录页有时候是白的，刷新才好"),
]
KIND_NATURE = {"iteration": "OPT", "bug": "DEF", "change": "REQ", "urgent": "EMRG", "debt": "OPT"}


def _run(runner: CliRunner, root: Path, *args: str) -> Result:
    return runner.invoke(cli, ["-w", str(root), "pm", *args])


def _json(result: Result) -> Any:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _options(**overrides: Any) -> list[str]:
    """The arguments of ``pm inbox add``; a value of None drops the option, a list repeats it."""

    values: dict[str, Any] = {
        "--project-id": PROJECT,
        "--request-id": "REQ-INBOX-001",
        "--title": "登录页偶发白屏",
        "--kind": "bug",
        "--domain": "SCPT",
        "--original-words": "登录页有时候是白的，刷新才好",
        "--affects": "SW-TEST-001 登录页",
        "--duplicate-check": "查过台账与收件箱，没有同类条目",
        "--evidence": ["file:README.md"],
        "--disposition": "after_current",
        "--rationale": "不阻塞当前卡，当前卡收口后处理",
        "--alternative": ["并入下个迭代"],
        "--cost-risk": "半天；低风险",
    }
    values.update({"--" + key.replace("_", "-"): value for key, value in overrides.items()})
    flattened: list[str] = []
    for option, value in values.items():
        if value is None:
            continue
        for entry in value if isinstance(value, list) else [value]:
            flattened.extend([option, str(entry)])
    return flattened


def _add(runner: CliRunner, root: Path, **overrides: Any) -> Result:
    return _run(runner, root, "inbox", "add", *_options(**overrides))


def _item(result: Result) -> dict[str, Any]:
    payload = _json(result)
    assert payload["schema_version"] == "pm-inbox-item.v1"
    item: dict[str, Any] = payload["item"]
    return item


def _decide(runner: CliRunner, root: Path, verb: str, item: dict[str, Any], *extra: str) -> Result:
    return _run(
        runner, root, "inbox", verb, item["item_id"], "--ticket-hash", item["ticket_hash"],
        "--approver", APPROVER, "--approval-evidence-ref", CONFIRMATION, *extra,
    )


def _events(root: Path) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def _count(root: Path, table: str) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if has else 0


def _listed(runner: CliRunner, root: Path, *statuses: str) -> list[dict[str, Any]]:
    arguments = ["inbox", "list", "--project-id", PROJECT]
    for status in statuses:
        arguments.extend(["--status", status])
    payload = _json(_run(runner, root, *arguments))
    assert payload["schema_version"] == "pm-inbox.v1" and payload["project_id"] == PROJECT
    items: list[dict[str, Any]] = payload["items"]
    return items


def _change(root: Path, change_id: str) -> Any:
    change = ChangeService(str(root)).get_change_request(change_id, project_id=PROJECT)
    assert change is not None
    return change


def _plan(runner: CliRunner, root: Path, request_id: str, *extra: str) -> Result:
    return _run(
        runner, root, "plan", "--project-id", PROJECT, "--request-id", request_id, "--objective", "Plan the classified work",
        "--acceptance", "A scope card is returned.", *SCOPE, *extra,
    )



# The exact refusal each single invalid contract field must produce (``plan`` side).
_INVALID_REASON = {
    "scope": "scope_paths must be explicit and must not contain wildcards",
    "risk": "risks and non_goals must be explicit",
    "non_goal": "risks and non_goals must be explicit",
    "grant": "declared_dirty_paths must be an exact subset of scope_paths",
}


@pytest.mark.parametrize("invalid", ["scope", "risk", "non_goal", "grant"])
def test_audit_f01_cli_invalid_planning_contract_keeps_confirmed_item(
    cli_runner: CliRunner,
    root: Path,
    invalid: str,
) -> None:
    """``plan`` side only; the ``approve`` side needs a saved card first (see the TD-093 test below)."""
    verb = "plan"
    item = _item(_add(cli_runner, root))
    _decide(cli_runner, root, "confirm", item)
    scope = list(SCOPE)
    option, value = {
        "scope": ("--scope", "auto_pm/*"),
        "risk": ("--risk", " "),
        "non_goal": ("--non-goal", " "),
        "grant": ("--declared-dirty", "outside.py"),
    }[invalid]
    scope[scope.index(option) + 1] = value
    args = [
        verb,
        "--project-id",
        PROJECT,
        "--request-id",
        "REQ-AUDIT-INVALID",
        "--objective",
        "Contract validation",
        "--acceptance",
        "Card persists",
        *scope,
        "--inbox-id",
        item["item_id"],
    ]
    result = _run(cli_runner, root, *args)
    assert result.exit_code != 0
    assert _INVALID_REASON[invalid] in result.output
    listed = _listed(cli_runner, root)
    assert listed[0]["status"] == "CONFIRMED" and listed[0]["plan_request_id"] == ""
    assert _count(root, "planning_draft_intake_bindings") == 0
    assert _count(root, "planning_scope_cards") == 0
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type IN "
                "('INTAKE_ITEM_PLANNED', 'PLANNING_DRAFT_INTAKE_BOUND', 'PLANNING_SCOPE_CARD_SUBMITTED')"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("source", ["direct", "inbox"])
@pytest.mark.parametrize("field", ["kind", "action", "domain", "scope", "project"])
def test_audit_f05_cli_bound_replay_refuses_explicit_conflicts_before_writes(
    cli_runner: CliRunner,
    root: Path,
    source: str,
    field: str,
) -> None:
    if source == "inbox":
        item = _item(_add(cli_runner, root, kind="change", change_action="add"))
        _decide(cli_runner, root, "confirm", item)
        options = ["--inbox-id", item["item_id"]]
    else:
        options = ["--kind", "change", "--change-action", "add", "--domain", "SCPT"]
    card = _json(_plan(cli_runner, root, "REQ-AUDIT-REPLAY", *options))
    change = _change(root, card["change_id"])
    before_bytes = Path(change.file_path).read_bytes()
    before_events = _events(root)
    conflicts = {
        "kind": ["--kind", "bug"],
        "action": ["--change-action", "remove"],
        "domain": ["--domain", "PLC"],
        "scope": ["--impact-scope", "SYSTEM"],
        "project": ["--project-id", "SW-OTHER-002"],
    }
    failed = _plan(cli_runner, root, "REQ-AUDIT-REPLAY", *conflicts[field])
    assert failed.exit_code != 0 and ("不一致" in failed.output or "同一项目" in failed.output)
    assert _events(root) == before_events
    assert Path(change.file_path).read_bytes() == before_bytes
    assert _count(root, "planning_scope_cards") == 1
    assert _json(_plan(cli_runner, root, "REQ-AUDIT-REPLAY")) == card
    assert (
        _json(
            _plan(
                cli_runner,
                root,
                "REQ-AUDIT-REPLAY",
                "--kind",
                "change",
                "--change-action",
                "add",
                "--domain",
                "SCPT",
                "--impact-scope",
                "MODULE",
            )
        )
        == card
    )
    assert _events(root) == before_events


@pytest.mark.parametrize(
    "evidence", [["file:directory"], ["file:README.md", "file:directory"], ["file:missing.txt"]]
)
def test_audit_f06_cli_file_negatives_leave_no_trace(
    cli_runner: CliRunner,
    root: Path,
    evidence: list[str],
) -> None:
    (root / "directory").mkdir()
    before = _events(root)
    failed = _add(cli_runner, root, evidence=evidence)
    assert failed.exit_code != 0 and "取证" in failed.output
    assert _events(root) == before and _count(root, "intake_items") == 0
    assert _item(_add(cli_runner, root))["ticket"]["evidence"] == ["file:README.md"]


def test_audit_f08_cli_full_approve_reuses_the_durable_success_boundary(
    cli_runner: CliRunner,
    root: Path,
) -> None:
    item = _item(_add(cli_runner, root))
    _decide(cli_runner, root, "confirm", item)
    card = _json(_plan(cli_runner, root, "REQ-AUDIT-APPROVE", "--inbox-id", item["item_id"]))
    for state in ("submitted", "under_review", "approved"):
        ChangeService(str(root)).transition_status(
            card["change_id"],
            state,
            project_id=PROJECT,
            approver=APPROVER,
            comment="Human review",
        )
    args = [
        "approve",
        "--project-id",
        PROJECT,
        "--request-id",
        "REQ-AUDIT-APPROVE",
        "--objective",
        "Plan the classified work",
        "--acceptance",
        "A scope card is returned.",
        *SCOPE,
        "--plan-hash",
        card["plan_hash"],
        "--approver",
        APPROVER,
        "--approval-evidence-ref",
        CONFIRMATION,
    ]
    approved = _json(_run(cli_runner, root, *args))
    assert _json(_run(cli_runner, root, *args)) == approved
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        for event in (
            "INTAKE_ITEM_PLANNED",
            "PLANNING_DRAFT_INTAKE_BOUND",
            "PLANNING_SCOPE_CARD_SUBMITTED",
        ):
            assert (
                conn.execute("SELECT COUNT(*) FROM events WHERE event_type=?", (event,)).fetchone()[
                    0
                ]
                == 1
            )
    assert _count(root, "planning_scope_cards") == 1 and _count(root, "run_items") == 0



@pytest.fixture
def root(tmp_path: Path) -> Path:
    _setup_planning(tmp_path)
    return tmp_path


def _urgent_options(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {"kind": "urgent", "urgent_criterion": "wrong_output", "disposition": "interrupt_now", "title": "紧急：输出了错误数据"}
    values.update(overrides)
    return values


def test_cx01_add_list_and_show_round_trip_the_triage_ticket(cli_runner: CliRunner, root: Path) -> None:
    created = _json(_add(cli_runner, root))
    assert created["created"] is True
    item = created["item"]
    assert item["item_id"] == "INBOX-SW-TEST-001-0001" and item["status"] == "PROPOSED"
    assert len(item["ticket_hash"]) == 64 and item["proposed_by"] == "pm-cli"
    assert item["classification"] == {"kind": "BUG", "change_action": None, "domain": "SCPT", "impact_scope": ["MODULE"]}
    assert item["ticket"]["evidence"] == ["file:README.md"] and item["ticket"]["disposition"] == "AFTER_CURRENT"
    assert _listed(cli_runner, root) == [item]
    shown = _json(_run(cli_runner, root, "inbox", "show", item["item_id"]))
    assert shown == {"schema_version": "pm-inbox-item.v1", "item": item}
    replay = _json(_add(cli_runner, root))
    assert replay["created"] is False and replay["item"] == item
    assert _count(root, "intake_items") == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"evidence": None},
        {"evidence": ["note:it felt wrong"]},
        {"evidence": ["file:docs/not-there.md"]},
        {"evidence": ["file:../outside.md"]},
        {"alternative": None},
        {"rationale": "  "},
        {"urgent_criterion": "safety"},
        {"disposition": "interrupt_now"},
        {"kind": "urgent", "disposition": "interrupt_now"},
        {"kind": "urgent", "urgent_criterion": "safety", "disposition": "interrupt_now"},
        {"kind": "urgent", "urgent_criterion": "data_loss", "disposition": "inbox_wait"},
        {"kind": "change"},
        {"change_action": "add"},
        {"domain": "XXXX"},
        {"domain": None},
        {"impact_scope": ["GLOBAL"]},
        {"duplicate_of": ["whatever"]},
        {"project_id": "SW-GHOST-001"},
        {"title": "x" * 121},
    ],
    ids=lambda overrides: ",".join(f"{key}={value}" for key, value in overrides.items()),
)
def test_cx02_a_ticket_that_is_not_professional_enough_leaves_no_trace(
    cli_runner: CliRunner, root: Path, overrides: dict[str, Any]
) -> None:
    before = (_events(root), _count(root, "intake_items"))
    result = _add(cli_runner, root, **overrides)
    assert result.exit_code != 0, result.output
    assert (_events(root), _count(root, "intake_items")) == (before[0], 0)
    assert _listed(cli_runner, root) == []


@pytest.mark.parametrize(
    ("overrides", "flag"),
    [({"evidence": None}, "--evidence"), ({"alternative": None}, "--alternative")],
    ids=["evidence", "alternative"],
)
def test_td261_d7_a_missing_required_list_is_named_in_plain_words(
    cli_runner: CliRunner, root: Path, overrides: dict[str, Any], flag: str
) -> None:
    result = _add(cli_runner, root, **overrides)
    assert result.exit_code != 0
    assert f"入箱必须带 {flag}" in result.output
    assert "ValidationError" not in result.output and "a triage ticket needs" not in result.output


def test_td261_d7_the_help_marks_the_two_required_lists(cli_runner: CliRunner, root: Path) -> None:
    result = _run(cli_runner, root, "inbox", "add", "--help")
    flat = " ".join(result.output.split())
    assert "【必填，至少一条】取证" in flat and "【必填，至少一个】备选方案" in flat


@pytest.mark.parametrize("action", ["add", "modify", "reduce", "freeze", "remove"])
def test_cx03_a_feature_change_is_not_only_an_addition(cli_runner: CliRunner, root: Path, action: str) -> None:
    item = _item(_add(cli_runner, root, kind="change", change_action=action, request_id=f"REQ-ACT-{action}", title=f"功能变更：{action}"))
    assert item["classification"]["kind"] == "CHANGE" and item["classification"]["change_action"] == action.upper()


def test_cx04_confirm_and_reject_need_the_exact_hash_a_human_and_external_evidence(cli_runner: CliRunner, root: Path) -> None:
    first = _item(_add(cli_runner, root))
    second = _item(_add(cli_runner, root, request_id="REQ-INBOX-002", title="另一条"))
    events = _events(root)
    refusals = [
        _run(cli_runner, root, "inbox", "confirm", first["item_id"], "--ticket-hash", "0" * 64, "--approver", APPROVER, "--approval-evidence-ref", CONFIRMATION),
        _run(cli_runner, root, "inbox", "confirm", first["item_id"], "--ticket-hash", first["ticket_hash"], "--approver", "claude", "--approval-evidence-ref", CONFIRMATION),
        _run(cli_runner, root, "inbox", "confirm", first["item_id"], "--ticket-hash", first["ticket_hash"], "--approver", APPROVER, "--approval-evidence-ref", "i said yes"),
        _run(cli_runner, root, "inbox", "confirm", first["item_id"], "--ticket-hash", first["ticket_hash"], "--approver", APPROVER),
        _run(cli_runner, root, "inbox", "confirm", "INBOX-SW-TEST-001-0099", "--ticket-hash", first["ticket_hash"], "--approver", APPROVER, "--approval-evidence-ref", CONFIRMATION),
    ]
    assert all(result.exit_code != 0 for result in refusals) and _events(root) == events
    confirmed = _item(_decide(cli_runner, root, "confirm", first, "--note", "确认，按建议排"))
    assert confirmed["status"] == "CONFIRMED" and confirmed["decided_by"] == APPROVER and confirmed["note"] == "确认，按建议排"
    rejected = _item(_decide(cli_runner, root, "reject", second))
    assert rejected["status"] == "REJECTED"
    assert [item["item_id"] for item in _listed(cli_runner, root)] == [first["item_id"]]
    assert [item["item_id"] for item in _listed(cli_runner, root, "rejected")] == [second["item_id"]]
    assert {item["status"] for item in _listed(cli_runner, root, "proposed", "confirmed", "rejected", "planned")} == {"CONFIRMED", "REJECTED"}
    assert _decide(cli_runner, root, "reject", first).exit_code != 0
    assert _item(_decide(cli_runner, root, "confirm", first)) == confirmed


@pytest.mark.parametrize("kind", ["iteration", "bug", "change", "urgent", "debt"])
def test_cx05_a_confirmed_item_becomes_a_plan_filed_under_its_own_classification(
    cli_runner: CliRunner, root: Path, kind: str
) -> None:
    overrides: dict[str, Any] = {"kind": kind, "request_id": f"REQ-ITEM-{kind}", "title": f"条目 {kind}", "impact_scope": ["MODULE", "SYSTEM"]}
    if kind == "change":
        overrides["change_action"] = "freeze"
    if kind == "urgent":
        overrides.update(_urgent_options(request_id=f"REQ-ITEM-{kind}", impact_scope=["MODULE", "SYSTEM"]))
    item = _item(_add(cli_runner, root, **overrides))
    assert _plan(cli_runner, root, "REQ-PLAN-X", "--inbox-id", item["item_id"]).exit_code != 0
    _item(_decide(cli_runner, root, "confirm", item))
    card = _json(_plan(cli_runner, root, "REQ-PLAN-X", "--inbox-id", item["item_id"]))
    change = _change(root, card["change_id"])
    assert change.business_nature == KIND_NATURE[kind] and change.domain == "SCPT"
    assert list(change.impact_scope) == ["MODULE", "SYSTEM"]
    assert change.urgency == ("urgent" if kind == "urgent" else "normal")
    assert f"intake_kind={kind.upper()}" in change.references and f"intake_item={item['item_id']}" in change.references
    assert ("change_action=FREEZE" in change.references) is (kind == "change")
    assert [(entry["item_id"], entry["status"], entry["plan_request_id"]) for entry in _listed(cli_runner, root, "planned")] == [
        (item["item_id"], "PLANNED", "REQ-PLAN-X")
    ]
    assert _listed(cli_runner, root) == []


@pytest.mark.parametrize("action", ["add", "modify", "reduce", "freeze", "remove"])
def test_cx06_every_feature_change_action_files_as_a_requirement_change(
    cli_runner: CliRunner, root: Path, action: str
) -> None:
    card = _json(_plan(cli_runner, root, f"REQ-DIRECT-{action}", "--kind", "change", "--change-action", action, "--domain", "DOCU"))
    change = _change(root, card["change_id"])
    assert (change.business_nature, change.domain, list(change.impact_scope)) == ("REQ", "DOCU", ["MODULE"])
    assert f"change_action={action.upper()}" in change.references


def test_cx07_a_new_request_that_nothing_classifies_is_refused_and_a_binding_makes_a_replay_work(
    cli_runner: CliRunner, root: Path
) -> None:
    before = (_events(root), _count(root, "planning_drafts"), _count(root, "planning_draft_intake_bindings"))
    unclassified = _plan(cli_runner, root, "REQ-NOKIND")
    assert unclassified.exit_code != 0 and "分类" in unclassified.output
    assert (_events(root), _count(root, "planning_drafts"), _count(root, "planning_draft_intake_bindings")) == before
    ContinuityStore(root).create_planning_draft(
        PlanningDraft.from_intent(
            PmIntent(subject_project_id=PROJECT, request_id="REQ-COCKPIT-DRAFT", objective="Saved by the cockpit", acceptance_criteria=("A card exists.",))
        )
    )
    draft_form = _run(cli_runner, root, "plan", "--request-id", "REQ-COCKPIT-DRAFT", *SCOPE)
    assert draft_form.exit_code != 0 and "分类" in draft_form.output and _count(root, "planning_draft_intake_bindings") == 0
    classified = _json(_run(cli_runner, root, "plan", "--request-id", "REQ-COCKPIT-DRAFT", *SCOPE, "--kind", "iteration", "--domain", "SCPT"))
    assert _change(root, classified["change_id"]).business_nature == "OPT"
    replay = _json(_run(cli_runner, root, "plan", "--request-id", "REQ-COCKPIT-DRAFT", *SCOPE))
    assert replay["change_id"] == classified["change_id"] and replay["plan_hash"] == classified["plan_hash"]
    different = _run(cli_runner, root, "plan", "--request-id", "REQ-COCKPIT-DRAFT", *SCOPE, "--kind", "bug", "--domain", "SCPT")
    assert different.exit_code != 0 and "已绑定" in different.output
    assert _count(root, "planning_draft_intake_bindings") == 1


def test_cx08_an_item_that_is_not_confirmed_or_does_not_match_cannot_feed_a_plan(cli_runner: CliRunner, root: Path) -> None:
    proposed = _item(_add(cli_runner, root, title="尚未确认"))
    confirmed = _item(_add(cli_runner, root, request_id="REQ-INBOX-002", title="已确认", kind="debt"))
    _decide(cli_runner, root, "confirm", confirmed)
    before = (_events(root), _count(root, "planning_drafts"))
    for request, extra in (
        ("REQ-P-A", ["--inbox-id", proposed["item_id"]]),
        ("REQ-P-B", ["--inbox-id", confirmed["item_id"], "--kind", "bug"]),
        ("REQ-P-C", ["--inbox-id", confirmed["item_id"], "--domain", "PLC"]),
        ("REQ-P-D", ["--inbox-id", confirmed["item_id"], "--impact-scope", "SYSTEM"]),
        ("REQ-P-E", ["--inbox-id", confirmed["item_id"], "--kind", "debt", "--change-action", "add"]),
        ("REQ-P-F", ["--inbox-id", "INBOX-SW-TEST-001-0099"]),
    ):
        result = _plan(cli_runner, root, request, *extra)
        assert result.exit_code != 0, (request, result.output)
    assert (_events(root), _count(root, "planning_drafts")) == before
    _json(_plan(cli_runner, root, "REQ-P-OK", "--inbox-id", confirmed["item_id"]))
    again = _plan(cli_runner, root, "REQ-P-OTHER", "--inbox-id", confirmed["item_id"])
    assert again.exit_code != 0 and "已确认" in again.output


def test_cx09_replaying_a_plan_from_an_item_changes_nothing(cli_runner: CliRunner, root: Path) -> None:
    item = _item(_add(cli_runner, root))
    _decide(cli_runner, root, "confirm", item)
    first = _json(_plan(cli_runner, root, "REQ-REPLAY", "--inbox-id", item["item_id"]))
    events = _events(root)
    second = _json(_plan(cli_runner, root, "REQ-REPLAY", "--inbox-id", item["item_id"]))
    third = _json(_plan(cli_runner, root, "REQ-REPLAY", "--kind", "bug", "--domain", "SCPT"))
    assert first == second == third and _events(root) == events
    assert _count(root, "planning_draft_intake_bindings") == 1


def test_cx10_legacy_and_short_forms_do_not_take_classification_and_approve_full_form_needs_one(
    cli_runner: CliRunner, root: Path
) -> None:
    mixed = _run(cli_runner, root, "plan", "--mission-id", "MISSION-NONE", "--kind", "bug")
    assert mixed.exit_code != 0 and "混用" in mixed.output
    card = _json(_plan(cli_runner, root, "REQ-APPROVE", "--kind", "change", "--change-action", "reduce", "--domain", "SCPT"))
    short = _run(
        cli_runner, root, "approve", "--request-id", "REQ-APPROVE", "--plan-hash", card["plan_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", CONFIRMATION, "--kind", "bug",
    )
    assert short.exit_code != 0 and "分类参数" in short.output
    full_args = ["approve", *_planning_args()[:-4], "--plan-hash", "0" * 64, "--approver", APPROVER, "--approval-evidence-ref", CONFIRMATION]
    no_kind = _run(cli_runner, root, *full_args)
    assert no_kind.exit_code != 0 and "分类" in no_kind.output


def test_cx11_resume_shows_the_inbox_without_changing_the_focus(cli_runner: CliRunner, root: Path) -> None:
    (root / ANCHORED).mkdir()
    (root / ANCHORED / ".copier-answers.yml").write_text(f"project_id: {ANCHORED}\nproject_name: Intake CLI\nstack: python\n", encoding="utf-8")
    registry_path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["projects"].append({"project_id": ANCHORED, "project_root": ANCHORED, "development_root": ANCHORED})
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    empty = _json(_run(cli_runner, root, "resume", ANCHORED, "--json"))
    assert empty["intake"] == {"schema_version": "intake-summary.v1", "awaiting_confirmation": 0, "confirmed_waiting": 0, "queue": []}
    assert "收件箱" not in _run(cli_runner, root, "resume", ANCHORED).output
    assert "pm triage" not in _run(cli_runner, root, "resume", ANCHORED).output
    first = _item(_add(cli_runner, root, project_id=ANCHORED, domain=None, title="普通 bug"))
    urgent = _item(_add(cli_runner, root, project_id=ANCHORED, domain=None, request_id="REQ-URGENT", **_urgent_options()))
    _decide(cli_runner, root, "confirm", first)
    after = _json(_run(cli_runner, root, "resume", ANCHORED, "--json"))
    assert (after["intake"]["awaiting_confirmation"], after["intake"]["confirmed_waiting"]) == (1, 1)
    assert [entry["item_id"] for entry in after["intake"]["queue"]] == [first["item_id"], urgent["item_id"]]
    assert after["intake"]["queue"][1] == {
        "item_id": urgent["item_id"], "kind": "URGENT", "title": "紧急：输出了错误数据", "status": "PROPOSED", "disposition": "INTERRUPT_NOW",
    }
    assert after["evidence_id"] != empty["evidence_id"]
    assert {key: after[key] for key in ("mission", "work", "run", "checkpoint", "conflicts", "next_legal_action")} == {
        key: empty[key] for key in ("mission", "work", "run", "checkpoint", "conflicts", "next_legal_action")
    }
    text = _run(cli_runner, root, "resume", ANCHORED).output
    assert "收件箱: 待确认 1 条 | 已确认待排 1 条" in text
    assert "python main.py pm triage <项目编号>" in text  # the full-version desk (TD-SW008-066) is one line away
    assert f"{first['item_id']} [BUG] 普通 bug（CONFIRMED，建议 AFTER_CURRENT）" in text
    assert f"{urgent['item_id']} [URGENT] 紧急：输出了错误数据（PROPOSED，建议 INTERRUPT_NOW）" in text


def test_cx13_an_item_recommended_for_rejection_can_only_be_rejected(cli_runner: CliRunner, root: Path) -> None:
    item = _item(_add(cli_runner, root, disposition="reject", title="建议驳回的条目"))
    refused = _decide(cli_runner, root, "confirm", item)
    assert refused.exit_code != 0 and "reject" in refused.output
    assert [entry["status"] for entry in _listed(cli_runner, root)] == ["PROPOSED"]
    assert _item(_decide(cli_runner, root, "reject", item))["status"] == "REJECTED"


def test_cx12_the_inbox_commands_refuse_a_linked_worktree(cli_runner: CliRunner, root: Path) -> None:
    _json(_add(cli_runner, root))
    linked = root.parent / f"{root.name}-linked"
    _git(root, "worktree", "add", "--detach", str(linked), "HEAD")
    results = [
        _run(cli_runner, linked, "inbox", "list", "--project-id", PROJECT),
        _run(cli_runner, linked, "inbox", "show", "INBOX-SW-TEST-001-0001"),
        _add(cli_runner, linked, request_id="REQ-LINKED", title="来自关联工作树"),
        _plan(cli_runner, linked, "REQ-LINKED", "--kind", "bug", "--domain", "SCPT"),
    ]
    for result in results:
        assert result.exit_code != 0 and "linked worktree" in result.output, result.output
    assert not (linked / ".auto-pm").exists()


# ``approve`` re-checks the same fields; a blank risk is stopped earlier by the plan checklist guard (field ⑥).
_APPROVE_REASON = {
    "scope": "scope_paths must be explicit and must not contain wildcards",
    "risk": "计划防呆未通过，缺 1 栏：⑥风险",
    "non_goal": "risks and non_goals must be explicit",
    "grant": "declared_dirty_paths must be an exact subset of scope_paths",
}


def _approve_args(request_id: str, plan_hash: str, scope: list[str]) -> list[str]:
    return [
        "approve", "--project-id", PROJECT, "--request-id", request_id,
        "--objective", "Plan the classified work", "--acceptance", "A scope card is returned.",
        *scope, "--plan-hash", plan_hash, "--approver", APPROVER, "--approval-evidence-ref", CONFIRMATION,
    ]


@pytest.mark.parametrize("invalid", ["scope", "risk", "non_goal", "grant"])
def test_td093_approve_refuses_each_invalid_contract_field_for_its_own_reason(
    cli_runner: CliRunner, root: Path, invalid: str
) -> None:
    """With a legal saved card and its real hash, changing exactly one field must hit that field's own guard.

    Before TD-093 the approve branch had no saved card, so every sample died on "PlanningDraft 不存在" and
    proved nothing about the field guards.
    """
    request_id = "REQ-TD093"
    item = _item(_add(cli_runner, root))
    _decide(cli_runner, root, "confirm", item)
    card = _json(_plan(cli_runner, root, request_id, "--inbox-id", item["item_id"]))
    baseline = _approve_args(request_id, card["plan_hash"], list(SCOPE))
    option, value = {
        "scope": ("--scope", "auto_pm/*"),
        "risk": ("--risk", " "),
        "non_goal": ("--non-goal", " "),
        "grant": ("--declared-dirty", "outside.py"),
    }[invalid]
    scope = list(SCOPE)
    scope[scope.index(option) + 1] = value
    before_events = _events(root)
    before_cards = _count(root, "planning_scope_cards")
    result = _run(cli_runner, root, *_approve_args(request_id, card["plan_hash"], scope), "--inbox-id", item["item_id"])
    assert result.exit_code != 0
    assert "PlanningDraft 不存在" not in result.output, result.output
    assert _APPROVE_REASON[invalid] in result.output, result.output
    assert _events(root) == before_events
    assert _count(root, "planning_scope_cards") == before_cards
    # Control: the very same saved card and hash with the legal fields is approvable, so the refusals above
    # were caused by the one changed field and not by a missing prerequisite.
    for state in ("submitted", "under_review", "approved"):
        ChangeService(str(root)).transition_status(
            card["change_id"], state, project_id=PROJECT, approver=APPROVER, comment="Human review"
        )
    assert _run(cli_runner, root, *baseline, "--inbox-id", item["item_id"]).exit_code == 0


def test_td261_d11_plan_help_says_a_confirmed_inbox_item_needs_no_retyping(cli_runner: CliRunner, root: Path) -> None:
    result = _run(cli_runner, root, "plan", "--help")
    assert "分类（--kind 等）直接取自条目，不用重填" in " ".join(result.output.split())


_RAW_DUMP_MARKS = ("validation error for", "errors.pydantic.dev", "input_value", "[type=")


@pytest.mark.parametrize(
    ("overrides", "said"),
    [
        ({"change_action": "modify"}, "--change-action 只用于 --kind change；--kind bug 不要给 --change-action"),
        ({"kind": "change", "change_action": None}, "--kind change 必须带 --change-action（add|modify|reduce|freeze|remove）"),
        ({"title": "长" * 121}, "--title: text must not exceed 120 characters"),
    ],
)
def test_td571_inbox_add_refuses_a_wrong_option_in_plain_words_and_records_nothing(
    cli_runner: CliRunner, root: Path, overrides: dict[str, Any], said: str
) -> None:
    result = _add(cli_runner, root, **overrides)
    assert result.exit_code == 1
    assert said in result.output
    assert not [mark for mark in _RAW_DUMP_MARKS if mark in result.output], result.output
    assert _listed(cli_runner, root) == []


def test_td571_inbox_add_help_says_change_action_is_only_for_a_change(cli_runner: CliRunner, root: Path) -> None:
    assert _run(cli_runner, root, "inbox", "add", "--help").exit_code == 0
    pm_group = cli.commands["pm"]
    assert isinstance(pm_group, click.Group)
    inbox = pm_group.commands["inbox"]
    assert isinstance(inbox, click.Group)
    helps = [param.help or "" for param in inbox.commands["add"].params if isinstance(param, click.Option) and "--change-action" in param.opts]
    assert helps == ["只用于 --kind change，且这时必填：add|modify|reduce|freeze|remove；其他类别不要给"]


def _option_help(command: str, flag: str) -> str:
    pm_group = cli.commands["pm"]
    assert isinstance(pm_group, click.Group)
    for param in pm_group.commands[command].params:
        if isinstance(param, click.Option) and flag in param.opts:
            return param.help or ""
    raise AssertionError(f"pm {command} 没有 {flag}")


def test_td572_every_option_plan_refuses_to_go_without_is_marked_required_in_its_help(
    cli_runner: CliRunner, root: Path
) -> None:
    """The help is checked against what ``pm plan`` actually refuses, so the two cannot drift apart."""

    refused = _run(
        cli_runner, root, "plan", "--project-id", PROJECT, "--request-id", "REQ-HELP", "--objective", "o", "--acceptance", "a"
    )
    assert refused.exit_code == 1 and "新需求 plan 缺少必填参数: " in refused.output
    missing = refused.output.split("新需求 plan 缺少必填参数: ", 1)[1].strip().split(", ")
    assert missing == ["--scope", "--risk", "--non-goal", "--adapter", "--approved-model"]
    checklist = ["--original-request", "--declared-dirty", "--safety-circuit", "--check", "--rollback"]
    for flag in [*missing, *checklist, "--request-id"]:
        assert _option_help("plan", flag).startswith("【必填】"), flag
    for flag in ("--project-id", "--objective", "--acceptance"):
        assert _option_help("plan", flag).startswith("【新需求必填】"), flag
    for flag in ("--mission-id", "--submitted-by", "--dry-run"):
        assert "必填" not in _option_help("plan", flag), flag


def test_td572_approve_marks_say_they_apply_only_when_approving_with_the_full_arguments() -> None:
    for flag in ("--project-id", "--scope", "--risk", "--non-goal", "--adapter", "--approved-model", "--declared-dirty", "--original-request", "--rollback"):
        assert _option_help("approve", flag).startswith("【带全参数批准时必填】"), flag
    assert _option_help("approve", "--plan-hash").startswith("【必填】")
    assert _option_help("approve", "--request-id").startswith("【必填】")


# ---------------------------------------------------------------- D-357: raw notes (pm inbox note, --from-note)

WORDS = "登录页有时候是白的，刷新才好"
AGENT_ENV = ("AUTO_PM_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT")


def _caller(monkeypatch: pytest.MonkeyPatch, marker: str = "") -> None:
    """Make the command see exactly this caller: no agent marker at all, or ``AUTO_PM_AGENT=<marker>``."""

    import os

    for name in (*AGENT_ENV, *(key for key in os.environ if key.upper().startswith("CODEX_"))):
        monkeypatch.delenv(name, raising=False)
    if marker:
        monkeypatch.setenv("AUTO_PM_AGENT", marker)


def _note(runner: CliRunner, root: Path, *extra: str, title: str = "登录页偶发白屏", words: str = WORDS, project: str = PROJECT) -> Result:
    return _run(runner, root, "inbox", "note", "--project-id", project, "--title", title, "--original-words", words, *extra)


def _noted(result: Result) -> dict[str, Any]:
    payload = _json(result)
    assert payload["schema_version"] == "pm-inbox-note.v1"
    note: dict[str, Any] = payload["note"]
    return note


def _inbox(runner: CliRunner, root: Path, *extra: str) -> dict[str, Any]:
    payload: dict[str, Any] = _json(_run(runner, root, "inbox", "list", "--project-id", PROJECT, *extra))
    return payload


def _event_types(root: Path) -> list[str]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return [str(row[0]) for row in conn.execute("SELECT event_type FROM events ORDER BY rowid")]


def test_d357_a_note_round_trips_and_a_replay_records_nothing_twice(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 2：记一条回 NOTE-<项目>-0001、RAW；同号同内容重放不重复记；同号不同内容拒绝。"""
    _caller(monkeypatch)
    first = _json(_note(cli_runner, root, "--request-id", "REQ-NOTE-1"))
    note = first["note"]
    assert first["schema_version"] == "pm-inbox-note.v1" and first["created"] is True
    assert (note["note_id"], note["status"], note["schema_version"]) == (f"NOTE-{PROJECT}-0001", "RAW", "intake-note.v1")
    assert (note["title"], note["original_words"], note["kind_hint"]) == ("登录页偶发白屏", WORDS, "ITERATION")
    assert (note["item_id"], note["triaged_by"], note["triaged_at"]) == ("", "", "")
    assert _event_types(root)[-1] == "INTAKE_NOTE_RECORDED"
    events = _events(root)

    again = _json(_note(cli_runner, root, "--request-id", "REQ-NOTE-1"))
    assert again["created"] is False and again["note"] == note
    assert _count(root, "intake_notes") == 1 and _events(root) == events

    other = _note(cli_runner, root, "--request-id", "REQ-NOTE-1", words="换了一句话")
    assert other.exit_code != 0 and "request_id 已绑定不同内容" in other.output
    assert _count(root, "intake_notes") == 1 and _events(root) == events
    assert _count(root, "intake_items") == 0


def test_d357_a_note_without_a_request_id_gets_one_and_the_kind_is_only_a_hint(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _caller(monkeypatch)
    one = _noted(_note(cli_runner, root, "--kind", "bug"))
    two = _noted(_note(cli_runner, root, title="另一件事"))
    assert one["kind_hint"] == "BUG" and two["kind_hint"] == "ITERATION"
    assert one["request_id"] and two["request_id"] and one["request_id"] != two["request_id"]
    assert [one["note_id"], two["note_id"]] == [f"NOTE-{PROJECT}-0001", f"NOTE-{PROJECT}-0002"]


def test_d357_duplicate_titles_are_refused_and_the_refusal_names_what_it_hit(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 3：记录和记录、记录和未处理的正式条目、正式条目和记录，三个方向都查重。"""
    _caller(monkeypatch)
    note = _noted(_note(cli_runner, root))
    same = _note(cli_runner, root, title="登录页偶发白屏 ".upper(), words="另一句")
    assert same.exit_code != 0 and f"已有同名待整理记录: {note['note_id']}" in same.output

    item = _item(_add(cli_runner, root, title="导出按钮没反应", request_id="REQ-ITEM-1"))
    against_item = _note(cli_runner, root, title="导出按钮没反应")
    assert against_item.exit_code != 0 and f"已有同名未处理条目: {item['item_id']}" in against_item.output

    plain_add = _add(cli_runner, root, request_id="REQ-ITEM-2")  # same title as the raw note, no --from-note
    assert plain_add.exit_code != 0
    assert f"已有同名待整理记录: {note['note_id']}；要转正它请加 --from-note {note['note_id']}" in plain_add.output
    assert _count(root, "intake_notes") == 1 and _count(root, "intake_items") == 1


def test_d357_who_recorded_is_never_stated_by_the_caller_and_never_says_user(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 4：没有自报选项；没带标记记成 no-agent-marker；认得出的记基名；认不出的记 unknown-agent。"""
    help_text = _run(cli_runner, root, "inbox", "note", "--help").output
    assert "--recorded-by" not in help_text and "--triaged-by" not in _run(cli_runner, root, "inbox", "add", "--help").output
    refused = _note(cli_runner, root, "--recorded-by", "user")
    assert refused.exit_code != 0 and _count(root, "intake_notes") == 0

    _caller(monkeypatch)
    bare = _noted(_note(cli_runner, root, title="没带标记"))
    _caller(monkeypatch, "trae:cn")
    named = _noted(_note(cli_runner, root, title="带了名册里的标记"))
    _caller(monkeypatch, "nobody-on-the-roster")
    unknown = _noted(_note(cli_runner, root, title="带了认不出的标记"))
    assert [bare["recorded_by"], named["recorded_by"], unknown["recorded_by"]] == ["no-agent-marker", "trae", "unknown-agent"]

    _caller(monkeypatch, "cursor")
    item = _item(_add_from(cli_runner, root, named["note_id"], title="带了名册里的标记", proposed_by="随便写"))
    assert item["proposed_by"] == "随便写"
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        stored = [json.loads(row[0]) for row in conn.execute("SELECT note_json FROM intake_notes ORDER BY seq")]
    assert stored[1]["triaged_by"] == "cursor" and stored[1]["recorded_by"] == "trae"
    assert all("user" not in (note["recorded_by"], note["triaged_by"]) for note in stored)


def test_d357_a_note_turned_by_a_terminal_without_marker_is_not_signed_as_user(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _caller(monkeypatch, "claude")
    note = _noted(_note(cli_runner, root))
    _caller(monkeypatch)
    _item(_add_from(cli_runner, root, note["note_id"]))
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        stored = json.loads(conn.execute("SELECT note_json FROM intake_notes").fetchone()[0])
    assert (stored["recorded_by"], stored["triaged_by"]) == ("claude", "no-agent-marker")


def _add_from(runner: CliRunner, root: Path, note_id: str, **overrides: Any) -> Result:
    return _run(runner, root, "inbox", "add", *_options(**overrides), "--from-note", note_id)


def test_d357_from_note_refuses_changed_words_a_second_turn_and_another_project(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 5：三条硬规矩各一条；三种情况下 intake_items 行数都不变。"""
    _caller(monkeypatch, "claude")
    note = _noted(_note(cli_runner, root))

    changed = _add_from(cli_runner, root, note["note_id"], original_words=WORDS + "。")
    assert changed.exit_code != 0 and "不逐字相同" in changed.output
    assert _count(root, "intake_items") == 0 and _inbox(cli_runner, root)["notes"][0]["status"] == "RAW"

    missing = _add_from(cli_runner, root, f"NOTE-{PROJECT}-0009")
    assert missing.exit_code != 0 and f"待整理记录不存在: NOTE-{PROJECT}-0009" in missing.output
    assert _count(root, "intake_items") == 0

    (root / ANCHORED).mkdir()
    (root / ANCHORED / ".copier-answers.yml").write_text(f"project_id: {ANCHORED}\nproject_name: Other\nstack: python\n", encoding="utf-8")
    registry_path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["projects"].append({"project_id": ANCHORED, "project_root": ANCHORED, "development_root": ANCHORED})
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    elsewhere = _add_from(cli_runner, root, note["note_id"], project_id=ANCHORED, domain=None)
    assert elsewhere.exit_code != 0 and f"属于项目 {PROJECT}" in elsewhere.output
    assert _count(root, "intake_items") == 0

    item = _item(_add_from(cli_runner, root, note["note_id"]))
    again = _add_from(cli_runner, root, note["note_id"], request_id="REQ-INBOX-002", title="换个标题再转一次")
    assert again.exit_code != 0 and f"已经转成 {item['item_id']}" in again.output
    assert _count(root, "intake_items") == 1


def test_d357_turning_a_note_writes_the_item_and_the_note_in_one_transaction(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 6：事件依次是条目入箱、记录转正；写记录那一步失败，正式条目也没写进去。"""
    from auto_pm.infrastructure.intake_store import IntakeStore

    _caller(monkeypatch, "claude")
    note = _noted(_note(cli_runner, root))
    before = (_events(root), _count(root, "intake_items"))
    real = IntakeStore._store_note

    def broken(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.OperationalError("disk I/O error (test)")

    monkeypatch.setattr(IntakeStore, "_store_note", staticmethod(broken))
    failed = _add_from(cli_runner, root, note["note_id"])
    assert failed.exit_code != 0
    assert (_events(root), _count(root, "intake_items")) == before
    assert _inbox(cli_runner, root)["notes"][0]["status"] == "RAW"

    monkeypatch.setattr(IntakeStore, "_store_note", staticmethod(real))
    item = _item(_add_from(cli_runner, root, note["note_id"]))
    assert item["status"] == "PROPOSED" and item["ticket"]["original_words"] == WORDS
    assert _event_types(root)[-2:] == ["INTAKE_ITEM_RECORDED", "INTAKE_NOTE_TRIAGED"]
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        row = conn.execute("SELECT status, item_id, note_json FROM intake_notes").fetchone()
    stored = json.loads(row[2])
    assert (row[0], row[1]) == ("TRIAGED", item["item_id"])
    assert (stored["status"], stored["item_id"], stored["triaged_by"]) == ("TRIAGED", item["item_id"], "claude")
    assert stored["triaged_at"] and stored["original_words"] == WORDS

    events = _events(root)
    replay = _json(_add_from(cli_runner, root, note["note_id"]))  # same request id: the note already points at this item
    assert replay["created"] is False and replay["item"] == item and _events(root) == events

    second = _noted(_note(cli_runner, root, title="另一件事", words="另一句"))
    crossed = _add_from(cli_runner, root, second["note_id"])  # same request id, but that item came from the first note
    assert crossed.exit_code != 0 and f"不是由待整理记录 {second['note_id']} 转来的" in crossed.output
    assert _events(root) == events + 1  # only the second note itself was recorded
    assert _inbox(cli_runner, root, "--notes-only")["notes"][0]["note_id"] == second["note_id"]


def test_d357_inbox_list_keeps_items_as_they_were_and_adds_the_notes(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 7：items 的内容和顺序不变，多一栏 notes；--notes-only 时 items 为空；已转正的记录不再列。"""
    _caller(monkeypatch, "claude")
    item = _item(_add(cli_runner, root, title="导出按钮没反应"))
    before = _listed(cli_runner, root)
    assert before == [item]
    waiting = _noted(_note(cli_runner, root))
    turned = _noted(_note(cli_runner, root, title="已经整理过的", words="另一句"))
    made = _item(_add_from(cli_runner, root, turned["note_id"], request_id="REQ-INBOX-002", title="已经整理过的", original_words="另一句"))

    full = _inbox(cli_runner, root)
    assert list(full) == ["schema_version", "project_id", "items", "notes"] and full["schema_version"] == "pm-inbox.v1"
    assert full["items"] == [item, made] and full["notes"] == [waiting]
    only = _inbox(cli_runner, root, "--notes-only")
    assert only["items"] == [] and only["notes"] == [waiting]
    assert _inbox(cli_runner, root, "--status", "rejected")["notes"] == [waiting]


def test_d357_read_commands_never_create_the_table_or_the_ledger(
    cli_runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验收 12（收件箱这两条）：老账本没有 intake_notes 表时只读命令不建表、账本字节不变；没有账本时不新建。"""
    import hashlib
    import shutil

    _caller(monkeypatch)
    shutil.rmtree(root / ".auto-pm")  # a workspace that never had a ledger
    for arguments in (("inbox", "list", "--project-id", PROJECT), ("inbox", "list", "--project-id", PROJECT, "--notes-only")):
        payload = _json(_run(cli_runner, root, *arguments))
        assert payload["items"] == [] and payload["notes"] == []
        assert not (root / ".auto-pm").exists()

    item = _item(_add(cli_runner, root))
    db = root / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("DROP TABLE intake_notes")
        conn.commit()
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    for arguments in (("inbox", "list", "--project-id", PROJECT), ("inbox", "list", "--project-id", PROJECT, "--notes-only")):
        payload = _json(_run(cli_runner, root, *arguments))
        assert payload["notes"] == [] and payload["items"] == ([] if "--notes-only" in arguments else [item])
        assert hashlib.sha256(db.read_bytes()).hexdigest() == digest
    assert _count(root, "intake_notes") == 0
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='intake_notes'").fetchone() is None
