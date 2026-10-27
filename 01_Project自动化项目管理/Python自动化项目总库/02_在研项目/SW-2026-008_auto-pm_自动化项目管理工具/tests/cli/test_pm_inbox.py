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

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner, Result

from auto_pm.contracts.pm_facade import PlanningDraft, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore
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
