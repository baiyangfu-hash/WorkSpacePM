"""TD-SW008-214: ``worktree`` and ``pr`` - writes refuse a runtime-identity conflict, listings and checks ask nothing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import pr as pr_cli
from auto_pm.ui.cli import worktree as worktree_cli
from auto_pm.ui.cli.pr import pr_group
from auto_pm.ui.cli.runtime_identity_guard import COCKPIT_PROJECT_ID
from auto_pm.ui.cli.worktree import worktree_group

WORKTREE_WRITES = {"open", "close", "release"}  # sweep and reclaim write only with --apply
WORKTREE_READS = {"list"}
PR_WRITES = {"open"}  # open writes unless --dry-run
PR_READS = {"ready", "settle-scan"}


def test_every_worktree_and_pr_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(worktree_group.commands) == WORKTREE_WRITES | WORKTREE_READS | {"sweep", "reclaim", "heartbeat"}
    assert set(pr_group.commands) == PR_WRITES | PR_READS


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __call__(self, *_a: object, **_k: object) -> object:
        self._touched.append("constructed")
        raise RuntimeError("服务在运行身份被拒绝之后仍被使用")


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    record: dict[str, list[Any]] = {"asked": [], "touched": []}

    def refuse(_ctx: click.Context) -> None:
        record["asked"].append("asked")
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    for module in (worktree_cli, pr_cli):
        monkeypatch.setattr(module, "require_runtime_identity_for_workspace", refuse)
    monkeypatch.setattr(worktree_cli, "AgentWorktreeService", _Untouchable(record["touched"]))
    monkeypatch.setattr(pr_cli, "PrOpenService", _Untouchable(record["touched"]))
    return record


def _invoke(group: click.Group, tmp_path: Path, argv: list[str]) -> Any:
    return CliRunner().invoke(
        group, argv, obj=SimpleNamespace(control_root=str(tmp_path), workspace_root=str(tmp_path))
    )


@pytest.mark.parametrize(
    ("group", "argv"),
    [
        (worktree_group, ["open", "claude", "T-1"]),
        (worktree_group, ["close", "claude"]),
        (worktree_group, ["sweep", "--apply"]),
        (pr_group, ["open", "claude", "T-1", "--task-card", "cards/t.md"]),
    ],
    ids=["worktree-open", "worktree-close", "worktree-sweep-apply", "pr-open"],
)
def test_a_station_write_is_refused_before_anything_is_touched(
    group: click.Group, argv: list[str], seen: dict[str, list[Any]], tmp_path: Path
) -> None:
    result = _invoke(group, tmp_path, argv)
    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert seen["asked"] == ["asked"]
    assert seen["touched"] == []


@pytest.mark.parametrize(
    ("group", "argv"),
    [
        (worktree_group, ["sweep"]),
        (worktree_group, ["sweep", "--dry-run"]),
        (pr_group, ["open", "claude", "T-1", "--task-card", "cards/t.md", "--dry-run"]),
    ],
    ids=["sweep-listing", "sweep-dry-run", "pr-open-dry-run"],
)
def test_a_listing_or_dry_run_does_not_ask_the_guard(
    group: click.Group, argv: list[str], seen: dict[str, list[Any]], tmp_path: Path
) -> None:
    _invoke(
        group, tmp_path, argv
    )  # the stub service then raises: only the guard question matters here
    assert seen["asked"] == []


def test_the_workspace_guard_asks_about_the_cockpit_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from auto_pm.ui.cli import runtime_identity_guard as guard

    asked: list[str] = []
    monkeypatch.setattr(
        guard, "require_runtime_identity", lambda _ctx, project, *_a: asked.append(project)
    )
    guard.require_runtime_identity_for_workspace(click.Context(click.Command("x")))
    assert asked == [COCKPIT_PROJECT_ID]


def test_the_cockpit_project_id_is_pinned() -> None:
    """The assertion above compares the guard with the constant itself; this pins the constant, so a typo cannot pass both."""
    assert COCKPIT_PROJECT_ID == "SW-2026-008"
