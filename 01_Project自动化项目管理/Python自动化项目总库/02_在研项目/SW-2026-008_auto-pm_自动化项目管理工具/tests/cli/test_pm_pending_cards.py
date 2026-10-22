"""U09B: the ``pm`` command line lists drafts, persists scope cards and approves them by plan hash.

Every test drives the real ``auto-pm`` entry point on a temporary Git workspace with a real Continuity Store.
Scenario numbers (c01..c15) follow card 039 section 5.3.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner, Result

from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import (
    PlanningDraft,
    PlanningExecutionGrant,
    PmIntent,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore

if TYPE_CHECKING:
    from auto_pm.application.core.mission_service import MissionService
    from auto_pm.application.core.pm_facade_service import PmFacadeService
else:
    from auto_pm.core.mission_service import MissionService
    from auto_pm.core.pm_facade_service import PmFacadeService

# Reuse the existing PM CLI fixtures; imported dynamically so that this file is type-checked on its own.
_pm_facade_tests = importlib.import_module("tests.cli.test_pm_facade")
_git = _pm_facade_tests._git
_planning_args = _pm_facade_tests._planning_args
_setup_planning = _pm_facade_tests._setup_planning

PROJECT = "SW-TEST-001"
COCKPIT = "REQ-COCKPIT-0123456789ABCDEF0123456789ABCDEF"
SECOND = "REQ-COCKPIT-FEDCBA9876543210FEDCBA9876543210"
EVIDENCE = "user-confirmation:U09B-TEST-001"
SCOPE = [
    "--scope",
    "auto_pm/example.py",
    "--risk",
    "scope drift",
    "--non-goal",
    "no execution before approval",
    "--adapter",
    "codex",
    "--approved-model",
    "gpt-approved",
    "--declared-dirty",
    "auto_pm/example.py",
    "--kind",
    "bug",
    "--domain",
    "SCPT",
]
FORBIDDEN_KEYS = {"mission_id", "decision_id", "work_id"}


def _run(cli_runner: CliRunner, root: Path, *args: str) -> Result:
    return cli_runner.invoke(cli, ["-w", str(root), "pm", *args])


def _json(result: Result) -> Any:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def _cockpit_draft(
    root: Path,
    request_id: str = COCKPIT,
    *,
    project: str = PROJECT,
    objective: str = "Created from the cockpit",
) -> None:
    ContinuityStore(root).create_planning_draft(
        PlanningDraft.from_intent(
            PmIntent(
                request_id=request_id,
                subject_project_id=project,
                objective=objective,
                acceptance_criteria=("A card is returned.",),
            )
        )
    )


def _count(root: Path, table: str) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _state(root: Path) -> tuple[int, int, int]:
    """(scope card rows, event rows, draft rows) - what every refusal must leave unchanged."""

    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning_scope_cards'"
        ).fetchone()
        cards = conn.execute("SELECT COUNT(*) FROM planning_scope_cards").fetchone()[0] if has_table else 0
        events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        drafts = conn.execute("SELECT COUNT(*) FROM planning_drafts").fetchone()[0]
    return int(cards), int(events), int(drafts)


def _submitted_events(root: Path, request_id: str) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='PLANNING_SCOPE_CARD_SUBMITTED' AND aggregate_id=?",
                (request_id,),
            ).fetchone()[0]
        )


def _chg_status(root: Path, change_id: str) -> str:
    change = ChangeService(str(root)).get_change_request(change_id, project_id=PROJECT)
    assert change is not None
    return str(change.status)


def _approve_args(request_id: str, plan_hash: str, *extra: str) -> list[str]:
    return [
        "approve",
        "--request-id",
        request_id,
        "--plan-hash",
        plan_hash,
        "--approver",
        "fubai",
        "--approval-evidence-ref",
        EVIDENCE,
        *extra,
    ]


def _planned(cli_runner: CliRunner, root: Path, request_id: str = COCKPIT) -> dict[str, Any]:
    """Create a cockpit-shaped draft and persist its scope card through the draft form."""

    _cockpit_draft(root, request_id)
    card: dict[str, Any] = _json(_run(cli_runner, root, "plan", "--request-id", request_id, *SCOPE))
    return card


def _pending(cli_runner: CliRunner, root: Path) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = _json(_run(cli_runner, root, "pending", "--project-id", PROJECT))["cards"]
    return cards


# --------------------------------------------------------------------------- c01 / c02 / c03 / c04: drafts, plan, pending


def test_c01_drafts_lists_cockpit_drafts_with_their_stage(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    empty = _json(_run(cli_runner, tmp_path, "drafts", "--project-id", PROJECT))
    assert empty == {"schema_version": "pm-planning-drafts.v1", "project_id": PROJECT, "drafts": []}

    _cockpit_draft(tmp_path)
    _cockpit_draft(tmp_path, "REQ-OTHER-PROJECT-001", project="SW-OTHER-001")
    listed = _json(_run(cli_runner, tmp_path, "drafts", "--project-id", PROJECT))

    assert listed["schema_version"] == "pm-planning-drafts.v1"
    assert listed["project_id"] == PROJECT
    assert len(listed["drafts"]) == 1
    entry = listed["drafts"][0]
    assert entry["draft"]["request_id"] == COCKPIT
    assert entry["draft"]["objective"] == "Created from the cockpit"
    assert entry["draft"]["acceptance_criteria"] == ["A card is returned."]
    assert (entry["card_revision"], entry["approved"], entry["change_id"]) == (0, False, "")
    assert entry["created_at"]
    assert not FORBIDDEN_KEYS & _all_keys(listed)


def test_c02_the_draft_form_persists_a_scope_card_for_a_saved_draft(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    card = _planned(cli_runner, tmp_path)

    assert card["schema_version"] == "planning-scope-card.v1"
    assert card["request_id"] == COCKPIT
    assert card["executable"] is False
    assert not FORBIDDEN_KEYS & set(card)
    cards = _pending(cli_runner, tmp_path)
    assert len(cards) == 1
    assert cards[0]["card"] == card
    assert (cards[0]["revision"], cards[0]["submitted_by"], cards[0]["superseded"]) == (1, "pm-cli", False)
    assert cards[0]["objective"] == "Created from the cockpit"
    assert not FORBIDDEN_KEYS & _all_keys(cards)


def test_c03_replaying_the_same_plan_is_identical_and_adds_no_revision(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)
    first = _planned(cli_runner, tmp_path)

    replayed = _json(_run(cli_runner, tmp_path, "plan", "--request-id", COCKPIT, *SCOPE))

    assert replayed == first
    assert [card["revision"] for card in _pending(cli_runner, tmp_path)] == [1]
    assert _submitted_events(tmp_path, COCKPIT) == 1


def test_c04_a_changed_scope_is_a_new_revision_that_supersedes_the_old_one(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)
    first = _planned(cli_runner, tmp_path)
    changed = ["scope drift v2" if item == "scope drift" else item for item in SCOPE]

    second = _json(_run(cli_runner, tmp_path, "plan", "--request-id", COCKPIT, *changed, "--submitted-by", "PM (Claude)"))

    assert second["plan_hash"] != first["plan_hash"]
    cards = _pending(cli_runner, tmp_path)
    assert [(card["revision"], card["submitted_by"], card["card"]["plan_hash"]) for card in cards] == [
        (2, "PM (Claude)", second["plan_hash"])
    ]
    assert _submitted_events(tmp_path, COCKPIT) == 2


# --------------------------------------------------------------------------- c05 / c06: refusals write nothing


def test_c05_an_unknown_draft_is_refused_without_writes(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    _cockpit_draft(tmp_path)
    before = _state(tmp_path)

    result = _run(cli_runner, tmp_path, "plan", "--request-id", "REQ-UNKNOWN-001", *SCOPE)

    assert result.exit_code == 1
    assert "不存在" in result.output
    assert _state(tmp_path) == before


def test_c06_missing_parameters_are_listed_per_form_and_nothing_is_written(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)
    _cockpit_draft(tmp_path)
    before = _state(tmp_path)

    draft_form = _run(cli_runner, tmp_path, "plan", "--request-id", COCKPIT, "--scope", "x/y.py")
    full_form = _run(cli_runner, tmp_path, "plan", "--request-id", COCKPIT, "--objective", "only an objective")

    assert draft_form.exit_code == 1
    assert "按已保存草稿提交范围卡缺少必填参数: --risk, --non-goal, --adapter, --approved-model" in draft_form.output
    assert full_form.exit_code == 1
    assert (
        "新需求 plan 缺少必填参数: --project-id, --acceptance, --scope, --risk, --non-goal, "
        "--adapter, --approved-model"
    ) in full_form.output
    assert _state(tmp_path) == before


# --------------------------------------------------------------------------- c07: the original full form


def test_c07_the_full_form_persists_the_card_and_keeps_its_output(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup_planning(tmp_path)

    planned = _json(_run(cli_runner, tmp_path, "plan", *_planning_args()))
    replayed = _json(_run(cli_runner, tmp_path, "plan", *_planning_args()))

    assert replayed == planned
    assert planned["schema_version"] == "planning-scope-card.v1"
    assert planned["request_id"] == "REQ-P11-001"
    assert planned["executable"] is False
    assert not FORBIDDEN_KEYS & set(planned)
    cards = _pending(cli_runner, tmp_path)
    assert [(card["card"], card["revision"]) for card in cards] == [(planned, 1)]
    drafts = _json(_run(cli_runner, tmp_path, "drafts", "--project-id", PROJECT))["drafts"]
    assert [(item["draft"]["request_id"], item["card_revision"], item["approved"]) for item in drafts] == [
        ("REQ-P11-001", 1, False)
    ]


# --------------------------------------------------------------------------- c08 / c09 / c10: approval by hash


def test_c08_the_short_form_approves_the_saved_card_by_plan_hash(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    card = _planned(cli_runner, tmp_path)

    approved = _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, card["plan_hash"])))

    assert approved == {
        "schema_version": "pm-plan-approval.v1",
        "request_id": COCKPIT,
        "subject_project_id": PROJECT,
        "change_id": card["change_id"],
        "plan_hash": card["plan_hash"],
        "authorization_status": "AUTHORIZED",
        "work_state": "READY",
    }
    assert _chg_status(tmp_path, card["change_id"]) == "approved"
    assert _pending(cli_runner, tmp_path) == []
    assert (_count(tmp_path, "planning_draft_decision_bindings"), _count(tmp_path, "mission_items"), _count(tmp_path, "work_items")) == (1, 1, 1)
    drafts = _json(_run(cli_runner, tmp_path, "drafts", "--project-id", PROJECT))["drafts"]
    assert [(item["card_revision"], item["approved"]) for item in drafts] == [(1, True)]


def test_c09_replaying_the_short_form_changes_nothing(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup_planning(tmp_path)
    card = _planned(cli_runner, tmp_path)
    first = _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, card["plan_hash"])))
    counts = {table: _count(tmp_path, table) for table in ("planning_draft_decision_bindings", "mission_items", "work_items", "events")}

    second = _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, card["plan_hash"])))

    assert second == first
    assert {table: _count(tmp_path, table) for table in counts} == counts


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("superseded-hash", "取代"),
        ("unknown-hash", "不存在"),
        ("model-signed", "自签"),
        ("not-a-user-confirmation", "user-confirmation"),
        ("missing-flags", "新需求批准缺少必填参数: --plan-hash, --approver, --approval-evidence-ref"),
        ("owner-with-short-form", "--owner"),
        ("mission-id-mixed", "--mission-id 不能与新需求批准参数混用"),
    ],
)
def test_c10_refused_approvals_write_nothing(
    cli_runner: CliRunner, tmp_path: Path, case: str, expected: str
) -> None:
    _setup_planning(tmp_path)
    first = _planned(cli_runner, tmp_path)
    changed = ["scope drift v2" if item == "scope drift" else item for item in SCOPE]
    latest = _json(_run(cli_runner, tmp_path, "plan", "--request-id", COCKPIT, *changed))
    arguments: dict[str, list[str]] = {
        "superseded-hash": _approve_args(COCKPIT, first["plan_hash"]),
        "unknown-hash": _approve_args(COCKPIT, "a" * 64),
        "model-signed": [
            "approve", "--request-id", COCKPIT, "--plan-hash", latest["plan_hash"], "--approver", "gpt-5",
            "--approval-evidence-ref", EVIDENCE,
        ],
        "not-a-user-confirmation": [
            "approve", "--request-id", COCKPIT, "--plan-hash", latest["plan_hash"], "--approver", "fubai",
            "--approval-evidence-ref", "chat-said-ok-123",
        ],
        "missing-flags": ["approve", "--request-id", COCKPIT],
        "owner-with-short-form": _approve_args(COCKPIT, latest["plan_hash"], "--owner", "someone"),
        "mission-id-mixed": ["approve", "--mission-id", "MISSION-X", "--request-id", COCKPIT],
    }
    before, status = _state(tmp_path), _chg_status(tmp_path, latest["change_id"])

    result = _run(cli_runner, tmp_path, *arguments[case])

    assert result.exit_code == 1
    assert expected in result.output
    assert "Traceback" not in result.output
    assert (_state(tmp_path), _chg_status(tmp_path, latest["change_id"])) == (before, status)
    assert _count(tmp_path, "planning_draft_decision_bindings") == 0
    assert [card["card"]["plan_hash"] for card in _pending(cli_runner, tmp_path)] == [latest["plan_hash"]]


# --------------------------------------------------------------------------- c11: the old full-form approve is unchanged


def test_c11_the_full_form_approve_still_works_with_and_without_a_persisted_card(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    persisted = tmp_path / "persisted"
    persisted.mkdir()
    _setup_planning(persisted)
    planned = _json(_run(cli_runner, persisted, "plan", *_planning_args()))
    assert len(_pending(cli_runner, persisted)) == 1

    approved = _json(_run(cli_runner, persisted, "approve", *_planning_args(), "--plan-hash", planned["plan_hash"],
                          "--approver", "fubai", "--approval-evidence-ref", EVIDENCE))

    assert (approved["authorization_status"], approved["work_state"]) == ("AUTHORIZED", "READY")
    assert not FORBIDDEN_KEYS & set(approved)
    assert _pending(cli_runner, persisted) == []

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _setup_planning(fresh)
    card = PmFacadeService(fresh).create_planning_scope_card(
        PmIntent(
            request_id="REQ-P11-001",
            subject_project_id=PROJECT,
            objective="Expose a user-facing planning entry.",
            acceptance_criteria=("A deterministic scope card is returned.",),
        ),
        scope_paths=("auto_pm/example.py",),
        risks=("scope drift",),
        non_goals=("no execution before approval",),
        execution_grant=PlanningExecutionGrant(
            adapter=ExecutionAdapterKind.CODEX,
            approved_model="gpt-approved",
            declared_dirty_paths=("auto_pm/example.py",),
        ),
    )
    assert PmFacadeService(fresh).list_pending_planning_scope_cards(PROJECT) == ()

    unpersisted = _json(_run(cli_runner, fresh, "approve", *_planning_args(), "--plan-hash", card.plan_hash,
                             "--approver", "fubai", "--approval-evidence-ref", EVIDENCE))

    assert (unpersisted["authorization_status"], unpersisted["work_state"]) == ("AUTHORIZED", "READY")
    assert unpersisted["plan_hash"] == card.plan_hash


# --------------------------------------------------------------------------- c12: no plan after approval


@pytest.mark.parametrize("form", ["draft", "full"])
def test_c12_planning_again_after_approval_is_refused_without_writes(
    cli_runner: CliRunner, tmp_path: Path, form: str
) -> None:
    _setup_planning(tmp_path)
    if form == "draft":
        card = _planned(cli_runner, tmp_path)
        _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, card["plan_hash"])))
        again = ["plan", "--request-id", COCKPIT, *SCOPE]
    else:
        card = _json(_run(cli_runner, tmp_path, "plan", *_planning_args()))
        _json(_run(cli_runner, tmp_path, "approve", *_planning_args(), "--plan-hash", card["plan_hash"],
                   "--approver", "fubai", "--approval-evidence-ref", EVIDENCE))
        again = ["plan", *_planning_args()]
    before = _state(tmp_path)

    result = _run(cli_runner, tmp_path, *again)

    assert result.exit_code == 1
    assert "已批准" in result.output
    assert _state(tmp_path) == before


# --------------------------------------------------------------------------- c13: linked worktrees are refused


def test_c13_a_linked_worktree_is_refused_for_every_new_form(cli_runner: CliRunner, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _setup_planning(root)
    card = _planned(cli_runner, root)
    linked = tmp_path / "linked"
    _git(root, "worktree", "add", "--detach", str(linked), "HEAD")

    for arguments in (
        ["drafts", "--project-id", PROJECT],
        ["pending", "--project-id", PROJECT],
        ["plan", "--request-id", COCKPIT, *SCOPE],
        _approve_args(COCKPIT, card["plan_hash"]),
    ):
        result = _run(cli_runner, linked, *arguments)
        assert result.exit_code == 1, arguments
        assert "linked worktree" in result.output
    assert not (linked / ".auto-pm").exists()


# --------------------------------------------------------------------------- c14: the old workflow entry delegates


def test_c14_workflow_delegates_plan_and_approve_but_not_the_new_listings(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)
    _cockpit_draft(tmp_path)

    via_workflow = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", "plan", "--request-id", COCKPIT, *SCOPE])
    via_pm = _run(cli_runner, tmp_path, "plan", "--request-id", COCKPIT, *SCOPE)
    card = json.loads(via_workflow.output)
    approved = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", *_approve_args(COCKPIT, card["plan_hash"])])

    assert via_workflow.exit_code == 0 and via_pm.exit_code == 0
    assert via_workflow.output == via_pm.output
    assert approved.exit_code == 0, approved.output
    assert json.loads(approved.output)["authorization_status"] == "AUTHORIZED"
    for name in ("drafts", "pending"):
        refused = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", name, "--project-id", PROJECT])
        assert refused.exit_code == 2
        assert "旧 workflow 动作" in refused.output


# --------------------------------------------------------------------------- c15: the open-mission guard through the CLI


def test_c15_a_first_approval_is_refused_while_another_task_is_open_and_works_after_it_ends(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)
    first = _planned(cli_runner, tmp_path, COCKPIT)
    second = _planned(cli_runner, tmp_path, SECOND)
    _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, first["plan_hash"])))
    before, status = _state(tmp_path), _chg_status(tmp_path, second["change_id"])
    bindings = _count(tmp_path, "planning_draft_decision_bindings")

    refused = _run(cli_runner, tmp_path, *_approve_args(SECOND, second["plan_hash"]))

    assert refused.exit_code == 1
    assert "要改同一批文件" in refused.output and "--admission-release-ref" in refused.output
    assert (_state(tmp_path), _chg_status(tmp_path, second["change_id"])) == (before, status)
    assert _count(tmp_path, "planning_draft_decision_bindings") == bindings == 1
    assert [card["card"]["request_id"] for card in _pending(cli_runner, tmp_path)] == [SECOND]

    mission = ContinuityStore(tmp_path).list_missions(PROJECT)[0]
    MissionService(tmp_path).transition(
        mission_id=mission.mission_id,
        expected_version=mission.version,
        new_state=MissionState.CANCELLED,
        root_work_id=None,
        idempotency_key="u09b-c15-cancel",
    )
    approved = _json(_run(cli_runner, tmp_path, *_approve_args(SECOND, second["plan_hash"])))

    assert approved["authorization_status"] == "AUTHORIZED"
    assert _pending(cli_runner, tmp_path) == []


def test_c16_the_users_release_on_the_command_line_admits_a_colliding_card(cli_runner: CliRunner, tmp_path: Path) -> None:
    """TD-071 card 3: ``--admission-release-ref`` carries the user's own word past a collision; it is recorded."""

    _setup_planning(tmp_path)
    first = _planned(cli_runner, tmp_path, COCKPIT)
    second = _planned(cli_runner, tmp_path, SECOND)
    _json(_run(cli_runner, tmp_path, *_approve_args(COCKPIT, first["plan_hash"])))
    release = "user-confirmation:TD071-C16"

    approved = _json(_run(cli_runner, tmp_path, *_approve_args(SECOND, second["plan_hash"], "--admission-release-ref", release)))

    assert approved["authorization_status"] == "AUTHORIZED"
    missions = ContinuityStore(tmp_path).list_missions(PROJECT)
    assert len(missions) == 2
    store = ContinuityStore(tmp_path)
    overlaps = {mission.mission_id: store.list_mission_overlaps(mission.mission_id) for mission in missions}
    assert all(len(found) == 1 for found in overlaps.values())
