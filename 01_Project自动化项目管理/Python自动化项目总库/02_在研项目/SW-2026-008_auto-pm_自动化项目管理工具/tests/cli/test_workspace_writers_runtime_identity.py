"""TD-SW008-214: spec / delivery / clean / constraint / vartable - the commands that write refuse a runtime-identity conflict.

None of these commands belongs to one project, so the check is the workspace-level one
(``require_runtime_identity_for_workspace``).  The reading forms (``--dry-run``, ``--verify-only``, no ``--output`` ...)
must not ask the guard anything: they are what a person runs when the identity is in doubt.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import clean as clean_cli
from auto_pm.ui.cli import constraint as constraint_cli
from auto_pm.ui.cli import delivery as delivery_cli
from auto_pm.ui.cli import spec as spec_cli
from auto_pm.ui.cli import vartable as vartable_cli
from auto_pm.ui.cli.clean import clean_cmd
from auto_pm.ui.cli.constraint import constraint_group
from auto_pm.ui.cli.delivery import delivery_group
from auto_pm.ui.cli.spec import spec_group
from auto_pm.ui.cli.vartable import vartable_group

MODULES = (clean_cli, constraint_cli, delivery_cli, spec_cli, vartable_cli)

# group -> (commands that can write, commands that only read)
CLASSIFIED = {
    "spec": ({"check", "index", "frontmatter", "report", "sync"}, {"lint"}),
    "constraint": ({"guard", "heal"}, {"list", "check", "verify"}),
    "delivery": ({"build", "package", "archive clean"}, {"status", "archive list"}),
    "vartable": (
        {"convert"},
        {
            "parse",
            "batch-parse",
            "detect-encoding",
            "detect-format",
            "list-encodings",
            "list-formats",
        },
    ),
}


def _names(group: click.Group) -> set[str]:
    names: set[str] = set()
    for name, command in group.commands.items():
        if isinstance(command, click.Group):
            names.update(f"{name} {sub}" for sub in command.commands)
        else:
            names.add(name)
    return names


def test_every_command_in_these_groups_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    for name, group in (
        ("spec", spec_group),
        ("constraint", constraint_group),
        ("delivery", delivery_group),
        ("vartable", vartable_group),
    ):
        writes, reads = CLASSIFIED[name]
        assert _names(group) == writes | reads, name


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    record: list[str] = []

    def refuse(_ctx: click.Context) -> None:
        record.append("asked")
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    for module in MODULES:
        monkeypatch.setattr(module, "require_runtime_identity_for_workspace", refuse)
    monkeypatch.setattr(
        spec_cli, "refuse_agent_approval", lambda *_a, **_k: None
    )  # a separate gate, covered by its own tests
    return record


def _run(command: click.Command, tmp_path: Path, argv: list[str]) -> Any:
    obj = SimpleNamespace(control_root=str(tmp_path), workspace_root=str(tmp_path))
    return CliRunner().invoke(command, argv, obj=obj)


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        (spec_group, ["check", "--fix"]),
        (spec_group, ["index"]),
        (spec_group, ["frontmatter", "--fix"]),
        (spec_group, ["report"]),
        (spec_group, ["sync"]),
        (clean_cmd, []),
        (constraint_group, ["guard", "{file}"]),
        (constraint_group, ["heal", "--all"]),
        (delivery_group, ["build", "--version", "V1.0.1"]),
        (delivery_group, ["package", "--version", "V1.0.1"]),
        (delivery_group, ["archive", "clean"]),
        (vartable_group, ["convert", "{file}", "--output", "{out}"]),
    ],
    ids=[
        "spec-check-fix",
        "spec-index",
        "spec-frontmatter-fix",
        "spec-report-into-library",
        "spec-sync",
        "clean",
        "constraint-guard",
        "constraint-heal",
        "delivery-build",
        "delivery-package",
        "delivery-archive-clean",
        "vartable-convert-to-file",
    ],
)
def test_a_write_is_refused_on_an_identity_conflict(
    command: click.Command, argv: list[str], asked: list[str], tmp_path: Path
) -> None:
    sample = tmp_path / "io_points.csv"
    sample.write_text("name,address\nA,1\n", encoding="utf-8")
    argv = [
        a.replace("{file}", str(sample)).replace("{out}", str(tmp_path / "out.csv")) for a in argv
    ]
    # ``clean`` only reaches the guard once there is something to remove or the cache flag asks for a sweep
    if command is clean_cmd:
        argv = ["--cache"]
    result = _run(command, tmp_path, argv)
    assert "已拒绝写入" in result.output, result.output
    assert asked == ["asked"]


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        (spec_group, ["check"]),
        (spec_group, ["check", "--fix", "--dry-run"]),
        (spec_group, ["lint"]),
        (clean_cmd, ["--cache", "--dry-run"]),
        (constraint_group, ["heal", "--all", "--dry-run"]),
        (constraint_group, ["list"]),
        (delivery_group, ["package", "--version", "V1.0.1", "--verify-only"]),
        (delivery_group, ["archive", "clean", "--dry-run"]),
        (delivery_group, ["status"]),
        (vartable_group, ["convert", "{file}"]),
        (vartable_group, ["parse", "{file}"]),
    ],
    ids=[
        "spec-check",
        "spec-check-fix-dry-run",
        "spec-lint",
        "clean-dry-run",
        "constraint-heal-dry-run",
        "constraint-list",
        "delivery-package-verify-only",
        "delivery-archive-clean-dry-run",
        "delivery-status",
        "vartable-convert-to-stdout",
        "vartable-parse",
    ],
)
def test_reading_forms_do_not_ask_the_guard(
    command: click.Command, argv: list[str], asked: list[str], tmp_path: Path
) -> None:
    sample = tmp_path / "io_points.csv"
    sample.write_text("name,address\nA,1\n", encoding="utf-8")
    _run(
        command, tmp_path, [a.replace("{file}", str(sample)) for a in argv]
    )  # whatever the command then does, it did not ask
    assert asked == []
