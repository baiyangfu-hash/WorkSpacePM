"""TD-SW008-174: every ``pm`` write command refuses while the runtime identity has a conflict, like the thin SDK."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import runtime_identity_guard as guard
from auto_pm.ui.cli.pm import pm_group

# A command is a write when it can change the ledger, a draft, an inbox item or a lease.
WRITE_COMMANDS = frozenset(
    {
        "accept",
        "approve",
        "close",
        "confirm-start",
        "execute",
        "handoff",
        "inbox add",
        "inbox confirm",
        "inbox reject",
        "park",
        "plan",
        "sign-risk",
        "switch",
        "takeover",
        "unpark",
        "verify",
    }
)
# Reads, plus the user's own PIN setup, which does not touch the ledger.
NOT_WRITE_COMMANDS = frozenset(
    {
        "approver-pin init",
        "approver-pin status",
        "context",
        "drafts",
        "inbox list",
        "inbox show",
        "missions",
        "orient",
        "pending",
        "recover-status",
        "resume",
        "workflow",
    }
)
def _walk(group: click.Group, prefix: str = "") -> Iterator[tuple[str, click.Command]]:
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            yield from _walk(command, f"{prefix}{name} ")
        else:
            yield f"{prefix}{name}", command


def test_every_pm_command_is_classified_as_write_or_not() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    found = {name for name, _ in _walk(pm_group)}

    assert found == WRITE_COMMANDS | NOT_WRITE_COMMANDS
    assert not WRITE_COMMANDS & NOT_WRITE_COMMANDS


class _Untouchable:
    """Stands in for every collaborator that writes; any use after the refusal is recorded and fails the test."""

    def __init__(self, touched: list[str], label: str) -> None:
        self._touched = touched
        self._label = label

    def __getattr__(self, name: str) -> object:
        self._touched.append(f"{self._label}.{name}")
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {self._label}.{name}")


class _Case:
    """One way of reaching a write command's guard: the arguments, what the command looks the project up from, and the project it must hand the guard."""

    def __init__(self, command: str, args: tuple[str, ...], project: str, setup: str = "mission") -> None:
        self.command = command
        self.args = args
        self.project = project
        self.setup = setup

    def __repr__(self) -> str:
        return f"{self.command}[{self.setup}]"


NEW_REQUEST = (
    "--project-id", "P-NEW", "--request-id", "REQ-1", "--objective", "o", "--acceptance", "a",
    "--scope", "f.py", "--risk", "r", "--non-goal", "n", "--adapter", "manual", "--approved-model", "m",
)  # fmt: skip
CASES = (
    _Case("accept", ("--mission-id", "M-1"), "P-MISSION"),
    _Case("approve", ("--mission-id", "M-1"), "P-MISSION"),
    _Case("approve", ("--request-id", "REQ-1", "--plan-hash", "H", "--approver", "u", "--approval-evidence-ref", "user-confirmation:1"), "P-SAVED", "by-hash"),
    _Case("approve", (*NEW_REQUEST, "--plan-hash", "H", "--approver", "u", "--approval-evidence-ref", "user-confirmation:1"), "P-NEW", "new-request"),
    _Case("close", ("--mission-id", "M-1"), "P-CLOSURE", "closure"),
    _Case("confirm-start", ("--mission-id", "M-1"), "P-MISSION"),
    _Case("execute", ("--request-id", "REQ-1", "--card-json", "{}", "--plan-hash", "H", "--lease-token-env", "TOKEN_ENV"), "P-CARD", "execute"),
    _Case("handoff", ("--run-id", "R-1", "--to", "claude:local"), "P-RUN", "run"),
    _Case("inbox add", ("--project-id", "P-INBOX", "--request-id", "REQ-1", "--title", "t", "--kind", "bug", "--original-words", "w", "--affects", "a", "--duplicate-check", "c", "--disposition", "reject", "--rationale", "r", "--cost-risk", "c"), "P-INBOX", "inbox"),
    _Case("inbox confirm", ("ITEM-1", "--ticket-hash", "H", "--approver", "u", "--approval-evidence-ref", "user-confirmation:1"), "P-ITEM", "inbox"),
    _Case("inbox reject", ("ITEM-1", "--ticket-hash", "H", "--approver", "u", "--approval-evidence-ref", "user-confirmation:1"), "P-ITEM", "inbox"),
    _Case("park", ("--mission-id", "M-1", "--reason", "r", "--summary", "s"), "P-MISSION", "switch"),
    _Case("plan", ("--mission-id", "M-1"), "P-MISSION"),
    _Case("plan", (*NEW_REQUEST, "--kind", "iteration"), "P-NEW", "new-request"),
    _Case("plan", ("--request-id", "REQ-1", "--scope", "f.py", "--risk", "r", "--non-goal", "n", "--adapter", "manual", "--approved-model", "m", "--kind", "iteration"), "P-DRAFT", "draft"),
    _Case("sign-risk", ("--run-id", "R-1", "--claimant", "claude:local"), "P-RUN", "run"),
    _Case("switch", ("--pid", "P-SWITCH", "--to", "M-2"), "P-SWITCH", "switch"),
    _Case("takeover", ("--handoff-id", "HO-1", "--as", "claude:local"), "P-HANDOFF", "takeover"),
    _Case("unpark", ("--mission-id", "M-1", "--as", "claude:local"), "P-MISSION", "switch"),
    _Case("verify", ("--mission-id", "M-1", "--lease-wallet"), "P-CLOSURE", "closure"),
)  # fmt: skip


def test_every_write_command_has_a_behavioural_case() -> None:
    assert {case.command for case in CASES} == WRITE_COMMANDS


@pytest.mark.parametrize("case", CASES, ids=repr)
def test_a_refused_identity_stops_every_write_command_before_it_writes(
    case: _Case, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Run the real command with the guard refusing: it must be asked about the right project, exit non-zero, and write nothing.

    Source matching cannot tell a live guard call from dead code, a comment, or a call that names the wrong project.
    """
    from auto_pm.ui.cli import pm, pm_closure, pm_handoff, pm_switch

    touched: list[str] = []
    asked: list[str] = []

    def refuse(_ctx: click.Context, project_id: str) -> None:
        asked.append(project_id)
        raise click.ClickException("GUARD-REFUSED")

    def untouchable(label: str) -> _Untouchable:
        return _Untouchable(touched, label)

    for module in (pm, pm_closure, pm_handoff, pm_switch):
        monkeypatch.setattr(module, "require_runtime_identity", refuse)
    for module in (pm, pm_switch):
        monkeypatch.setattr(module, "project_of_mission", lambda _ctx, _mission_id: "P-MISSION")
    monkeypatch.setattr(pm_handoff, "project_of_run", lambda _ctx, _run_id: "P-RUN")
    monkeypatch.setattr(pm, "_require_control_root", lambda _ctx: None)
    monkeypatch.setattr(pm, "_facade", lambda _ctx: untouchable("facade"))
    monkeypatch.setattr(pm, "_control_root_path", lambda _ctx: tmp_path)
    monkeypatch.setattr(pm, "approval_pin_enforced", lambda _root: False)

    def pin(*_a: object, **_k: object) -> str:
        touched.append("read_approval_pin")
        return ""

    monkeypatch.setattr(pm, "read_approval_pin", pin)
    monkeypatch.setattr(pm_switch, "read_approval_pin", pin)
    monkeypatch.setattr(pm_switch, "_service", lambda *_a, **_k: untouchable("switch service"))
    monkeypatch.setattr(pm_handoff, "_service", lambda *_a, **_k: untouchable("handoff service"))
    monkeypatch.setattr(pm_handoff, "_store", lambda *_a, **_k: untouchable("handoff store"))
    monkeypatch.setattr(pm, "_intake", lambda _ctx: untouchable("intake"))
    monkeypatch.setattr(pm, "PmIntakeService", lambda *_a, **_k: untouchable("intake service"))
    if case.setup == "by-hash":
        monkeypatch.setattr(pm, "project_of_planning_request", lambda _ctx, _request_id: "P-SAVED")
    if case.setup == "draft":
        draft = SimpleNamespace(subject_project_id="P-DRAFT")
        store = SimpleNamespace(get_planning_draft=lambda _request_id: draft)
        monkeypatch.setattr(pm, "ContinuityStore", lambda *_a, **_k: store)
    if case.setup == "closure":
        mission = SimpleNamespace(subject_project_id="P-CLOSURE", mission_id="M-1", root_work_id="W-1")
        monkeypatch.setattr(pm_closure, "WorktreePolicyService", lambda *_a, **_k: SimpleNamespace(require_control_root=lambda: None))
        monkeypatch.setattr(pm_closure, "ContinuityStore", lambda *_a, **_k: SimpleNamespace(get_mission=lambda _mission_id: mission))
        monkeypatch.setattr(pm_closure, "PmCockpitService", lambda *_a, **_k: untouchable("cockpit"))
    if case.setup == "execute":
        monkeypatch.setenv("TOKEN_ENV", "secret")
        card = SimpleNamespace(request_id="REQ-1", subject_project_id="P-CARD")
        monkeypatch.setattr("auto_pm.ui.cli.pm.PlanningScopeCard.model_validate_json", classmethod(lambda _cls, _text: card))
    if case.setup == "inbox" and case.command != "inbox add":
        monkeypatch.setattr(
            pm,
            "_intake",
            lambda _ctx: SimpleNamespace(
                get=lambda _item_id: SimpleNamespace(project_id="P-ITEM"),
                confirm=lambda *_a, **_k: touched.append("intake.confirm"),
                reject=lambda *_a, **_k: touched.append("intake.reject"),
            ),
        )
    if case.setup == "run" and case.command == "sign-risk":
        monkeypatch.setattr("auto_pm.ui.cli.pm_handoff.LeaseHandoverService.signature_refusal", classmethod(lambda _cls, *_a, **_k: ""))
    if case.setup == "takeover":
        handoff = SimpleNamespace(work_id="W-1", run_id="R-1")
        monkeypatch.setattr(pm_handoff, "_service", lambda *_a, **_k: SimpleNamespace(get_handoff=lambda _handoff_id: handoff))
        monkeypatch.setattr(
            pm_handoff, "_store", lambda *_a, **_k: SimpleNamespace(get_work=lambda _work_id: SimpleNamespace(subject_project_id="P-HANDOFF"))
        )

    result = CliRunner().invoke(
        pm_group,
        [*case.command.split(), *case.args],
        obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path),
    )

    assert asked == [case.project], f"pm {case.command} 没有按 {case.project} 做运行身份校验: {asked}\n{result.output}"
    assert result.exit_code != 0 and "GUARD-REFUSED" in result.output, result.output
    assert touched == [], f"拒绝之后仍在写: {touched}"


def _context(conflicts: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(conflicts=conflicts)


def _invoke_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: object) -> tuple[int, str]:
    """Run ``require_runtime_identity`` under click with a scripted ``WorkspaceContextService.resolve``."""

    class FakeService:
        def __init__(self, *_: object, **__: object) -> None: ...

        def resolve(self, **_: object) -> object:
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(guard, "WorkspaceContextService", FakeService)

    @click.command()
    @click.pass_context
    def probe(ctx: click.Context) -> None:
        guard.require_runtime_identity(ctx, "SW-1")
        click.echo("written")

    result = CliRunner().invoke(probe, obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path))
    return result.exit_code, result.output


def test_a_conflict_in_the_runtime_identity_refuses_the_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, output = _invoke_guard(monkeypatch, tmp_path, _context(("RUNTIME_IDENTITY_DIVERGENCE",)))

    assert code != 0 and "written" not in output
    assert "运行身份未通过校验" in output and "RUNTIME_IDENTITY_DIVERGENCE" in output


def test_an_unverified_runtime_identity_also_refuses_the_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, output = _invoke_guard(monkeypatch, tmp_path, _context(("RUNTIME_IDENTITY_UNVERIFIED",)))

    assert code != 0 and "RUNTIME_IDENTITY_UNVERIFIED" in output


def test_an_unresolvable_identity_refuses_the_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.application.core.workspace_context_service import WorkspaceContextError

    code, output = _invoke_guard(monkeypatch, tmp_path, WorkspaceContextError("Workspace Registry 不存在"))

    assert code != 0 and "written" not in output and "Workspace Registry 不存在" in output


def test_a_clean_identity_lets_the_write_continue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, output = _invoke_guard(monkeypatch, tmp_path, _context(()))

    assert code == 0 and "written" in output
