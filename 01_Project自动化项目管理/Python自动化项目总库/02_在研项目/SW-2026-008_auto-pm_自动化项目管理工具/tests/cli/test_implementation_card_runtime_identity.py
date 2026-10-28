"""TD-SW008-214: implementation-card write commands refuse a runtime-identity conflict before they write."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import implementation_card as card_cli
from auto_pm.ui.cli import runtime_identity_guard as guard
from auto_pm.ui.cli.implementation_card import implementation_card_group

WRITE_COMMANDS = {"create", "approve", "dispatch", "verify"}
NOT_WRITE_COMMANDS = {"precheck", "by-change", "validate"}


def test_every_implementation_card_command_is_classified() -> None:
    """A new command fails here until someone decides whether it needs the identity guard."""

    assert set(implementation_card_group.commands) == WRITE_COMMANDS | NOT_WRITE_COMMANDS


class _Untouchable:
    def __init__(self, touched: list[str]) -> None:
        self._touched = touched

    def __getattr__(self, name: str) -> object:
        self._touched.append(name)
        raise RuntimeError(f"写入路径在运行身份被拒绝之后仍被使用: {name}")


CREATE_ARGS = [
    "--card-id", "CARD-1", "--pid", "P-1", "--wbs-item-id", "W", "--milestone-id", "M", "--source-ref", "WBS:x",
    "--intent", "GOVERNANCE", "--base-commit", "a" * 40, "--worktree", "C:/c", "--owned-path", "a.py",
    "--commit-evidence-path", "e.md", "--decision-id", "DEC-1", "--work-id", "WORK-1", "--run-id", "RUN-1",
    "--max-runs", "2", "--max-healing-attempts", "1", "--deadline-utc", "2026-09-29T00:00:00Z",
    "--quota-stop-remaining-percent", "30",
]  # fmt: skip
CASES = (
    ("create", CREATE_ARGS, ["P-1"]),
    ("approve", ["CARD-1", "--approver", "u", "--approval-evidence", "user-confirmation:chat-1"], ["card"]),
    ("dispatch", ["CARD-1"], ["card"]),
    ("verify", ["CARD-1", "--checkpoint-id", "CP-1", "--final-commit", "b" * 40], ["card"]),
)


@pytest.mark.parametrize(("command", "args", "expected"), CASES, ids=[case[0] for case in CASES])
def test_a_refused_identity_stops_the_command_before_a_write(
    command: str, args: list[str], expected: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order: list[str] = []
    touched: list[str] = []

    def refuse(_ctx: click.Context, project: str) -> None:
        order.append(f"identity:{project}")
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    def refuse_card(_ctx: click.Context, card_id: str) -> None:
        order.append(f"identity:card:{card_id}")
        raise click.ClickException("运行身份未通过校验，已拒绝写入：测试")

    monkeypatch.setattr(card_cli, "require_runtime_identity", refuse)
    monkeypatch.setattr(card_cli, "require_runtime_identity_for_card", refuse_card)
    monkeypatch.setattr(card_cli, "ImplementationCardService", lambda *_a, **_k: _Untouchable(touched))
    monkeypatch.setattr(card_cli, "require_approval_pin", lambda *_a, **_k: order.append("pin"))

    result = CliRunner().invoke(
        implementation_card_group, [command, *args], obj=SimpleNamespace(control_root=str(tmp_path), workspace_root=str(tmp_path))
    )

    assert result.exit_code != 0
    assert "已拒绝写入" in result.output
    assert touched == []
    assert order[-1].startswith("identity:")
    if command == "approve":
        assert order == ["pin", "identity:card:CARD-1"]


def _lookup(monkeypatch: pytest.MonkeyPatch, card: object) -> list[str]:
    asked: list[str] = []

    class _Service:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def load(self, _card_id: str) -> object:
            if isinstance(card, Exception):
                raise card
            return card

    monkeypatch.setattr("auto_pm.application.core.implementation_card_service.ImplementationCardService", _Service)
    monkeypatch.setattr(guard, "require_runtime_identity", lambda _ctx, project: asked.append(project))
    return asked


def _ctx(tmp_path: Path) -> click.Context:
    return click.Context(click.Command("x"), obj=SimpleNamespace(control_root=tmp_path, workspace_root=tmp_path))


def test_the_card_names_the_project_to_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _lookup(monkeypatch, SimpleNamespace(project_id="P-FROM-CARD"))
    guard.require_runtime_identity_for_card(_ctx(tmp_path), "CARD-1")
    assert asked == ["P-FROM-CARD"]


def test_a_card_that_cannot_be_read_has_nothing_to_refuse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _lookup(monkeypatch, RuntimeError("missing"))
    guard.require_runtime_identity_for_card(_ctx(tmp_path), "CARD-1")
    assert asked == []
