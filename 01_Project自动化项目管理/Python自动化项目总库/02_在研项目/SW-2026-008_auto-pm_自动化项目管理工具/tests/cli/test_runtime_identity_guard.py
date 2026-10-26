"""TD-SW008-174: every ``pm`` write command refuses while the runtime identity has a conflict, like the thin SDK."""

from __future__ import annotations

import inspect
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
        "resume",
        "workflow",
    }
)
# Helpers that already call ``require_runtime_identity`` for the command that uses them.
GUARDING_HELPERS = ("require_runtime_identity", "_guarded_mission", "_emit_card", "_resolve_filing")


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


@pytest.mark.parametrize("name", sorted(WRITE_COMMANDS))
def test_every_write_command_reaches_the_identity_guard(name: str) -> None:
    command = dict(_walk(pm_group))[name]
    assert command.callback is not None

    source = inspect.getsource(command.callback)

    assert any(helper in source for helper in GUARDING_HELPERS), f"pm {name} 没有运行身份校验"


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
    from auto_pm.core.workspace_context_service import WorkspaceContextError

    code, output = _invoke_guard(monkeypatch, tmp_path, WorkspaceContextError("Workspace Registry 不存在"))

    assert code != 0 and "written" not in output and "Workspace Registry 不存在" in output


def test_a_clean_identity_lets_the_write_continue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    code, output = _invoke_guard(monkeypatch, tmp_path, _context(()))

    assert code == 0 and "written" in output
