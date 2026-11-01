"""TD-SW008-214: ``pm-session``, ``dogfood``, ``git-hook`` and ``workflow`` - the commands that write refuse a runtime-identity conflict."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import dogfood as dogfood_cli
from auto_pm.ui.cli import git_hook as git_hook_cli
from auto_pm.ui.cli import session as session_cli
from auto_pm.ui.cli import workflow as workflow_cli
from auto_pm.ui.cli.dogfood import dogfood_group
from auto_pm.ui.cli.git_hook import git_hook_group
from auto_pm.ui.cli.pm import pm_group
from auto_pm.ui.cli.session import pm_session_group
from auto_pm.ui.cli.workflow import _DELEGATED_TO_PM, workflow_group

MODULES = (dogfood_cli, git_hook_cli, session_cli, workflow_cli)

# group -> (commands that can write, commands that only read)
CLASSIFIED = {
    "pm-session": ({"archive", "view"}, {"check"}),
    "dogfood": ({"prepare", "review"}, {"inspect"}),
    "git-hook": ({"install"}, {"pre-commit", "release-gate", "commit-msg", "preflight"}),
    "workflow": ({"run"}, {"list", "history", "status"}),
}


def test_every_command_in_these_groups_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    groups = {
        "pm-session": pm_session_group,
        "dogfood": dogfood_group,
        "git-hook": git_hook_group,
        "workflow": workflow_group,
    }
    for name, group in groups.items():
        writes, reads = CLASSIFIED[name]
        native = (
            set(group.commands) - set(_DELEGATED_TO_PM)
            if name == "workflow"
            else set(group.commands)
        )
        assert native == writes | reads, name


def test_the_workflow_aliases_of_pm_commands_are_the_pm_commands_themselves() -> None:
    """They inherit every pm guard only because they are the same objects: a copy would silently drop the guard."""

    for name in _DELEGATED_TO_PM:
        assert workflow_group.commands[name] is pm_group.commands[name], name


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    record: list[str] = []

    def refuse(_ctx: click.Context) -> None:
        record.append("asked")
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    for module in MODULES:
        monkeypatch.setattr(module, "require_runtime_identity_for_workspace", refuse)
    return record


def _run(command: click.Command, tmp_path: Path, argv: list[str]) -> Any:
    obj = SimpleNamespace(control_root=str(tmp_path), workspace_root=str(tmp_path))
    return CliRunner().invoke(command, argv, obj=obj)


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        (pm_session_group, ["archive", "--section", "7"]),
        (pm_session_group, ["archive", "--auto"]),
        (pm_session_group, ["view", "--output", "{out}"]),
        (dogfood_group, ["prepare", "--candidate-path", "{cand}"]),
        (dogfood_group, ["review", "--candidate-path", "{tmp}"]),
        (git_hook_group, ["install"]),
        (workflow_group, ["run", "anything"]),
    ],
    ids=[
        "session-archive",
        "session-archive-auto",
        "session-view-to-file",
        "dogfood-prepare",
        "dogfood-review",
        "git-hook-install",
        "workflow-run",
    ],
)
def test_a_write_is_refused_on_an_identity_conflict(
    command: click.Command, argv: list[str], asked: list[str], tmp_path: Path
) -> None:
    argv = [
        a.replace("{out}", str(tmp_path / "v.md"))
        .replace("{cand}", str(tmp_path / "cand"))
        .replace("{tmp}", str(tmp_path))
        for a in argv
    ]
    result = _run(command, tmp_path, argv)
    assert "已拒绝写入" in result.output, result.output
    assert asked == ["asked"]


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        (pm_session_group, ["archive", "--auto", "--dry-run"]),
        (pm_session_group, ["view"]),
        (pm_session_group, ["check"]),
        (dogfood_group, ["review", "--candidate-path", "{tmp}", "--no-report"]),
        (git_hook_group, ["pre-commit"]),
        (workflow_group, ["list"]),
        (workflow_group, ["history"]),
    ],
    ids=[
        "session-archive-dry-run",
        "session-view-to-stdout",
        "session-check",
        "dogfood-review-no-report",
        "git-hook-pre-commit",
        "workflow-list",
        "workflow-history",
    ],
)
def test_reading_forms_do_not_ask_the_guard(
    command: click.Command, argv: list[str], asked: list[str], tmp_path: Path
) -> None:
    _run(
        command, tmp_path, [a.replace("{tmp}", str(tmp_path)) for a in argv]
    )  # whatever the command then does, it did not ask
    assert asked == []
