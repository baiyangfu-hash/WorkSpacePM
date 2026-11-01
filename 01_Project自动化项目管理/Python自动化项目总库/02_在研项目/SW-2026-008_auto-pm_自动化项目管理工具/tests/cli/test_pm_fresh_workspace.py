"""D6: the first PM command on a fresh clone must work without a hidden "initialise the store" step.

Every other CLI test calls ``ContinuityStore(root).initialize`` in its fixture, which is exactly why a fresh
workspace (no ``.auto-pm/continuity.db``) was never exercised.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.usefixtures("identity_guard_off")

_inbox = importlib.import_module("tests.cli.test_pm_inbox")
_facade = importlib.import_module("tests.cli.test_pm_facade")


@pytest.fixture
def fresh(tmp_path: Path) -> Path:
    """A planning workspace exactly as ``_setup_planning`` builds it, minus the store."""

    _facade._setup_planning(tmp_path)
    (tmp_path / ".auto-pm" / "continuity.db").unlink()
    return tmp_path


def test_d6_inbox_add_on_a_fresh_workspace_creates_the_store(cli_runner: CliRunner, fresh: Path) -> None:
    assert not (fresh / ".auto-pm" / "continuity.db").exists()

    result = _inbox._add(cli_runner, fresh)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["created"] is True
    assert (fresh / ".auto-pm" / "continuity.db").is_file()
    # Same request again is a replay, not a second item: initialising twice is harmless.
    again = _inbox._add(cli_runner, fresh)
    assert json.loads(again.output)["created"] is False


def test_d6_read_only_inbox_commands_do_not_create_the_store(cli_runner: CliRunner, fresh: Path) -> None:
    listed = _inbox._run(cli_runner, fresh, "inbox", "list", "--project-id", _inbox.PROJECT)

    assert not (fresh / ".auto-pm" / "continuity.db").exists()
    assert listed.exit_code == 0, listed.output


def test_d6_plan_straight_after_a_fresh_inbox_add_works(cli_runner: CliRunner, fresh: Path) -> None:
    item = _inbox._item(_inbox._add(cli_runner, fresh))
    _inbox._decide(cli_runner, fresh, "confirm", item)

    planned = _inbox._plan(cli_runner, fresh, "REQ-FRESH-PLAN", "--inbox-id", item["item_id"])

    assert planned.exit_code == 0, planned.output


@pytest.mark.parametrize(
    "command",
    [
        ["drafts", "--project-id", _inbox.PROJECT],
        ["pending", "--project-id", _inbox.PROJECT],
        ["resume", _inbox.PROJECT, "--json"],
    ],
)
def test_d6_other_pm_commands_on_a_fresh_workspace_never_crash(
    cli_runner: CliRunner, fresh: Path, command: list[str]
) -> None:
    result = _inbox._run(cli_runner, fresh, *command)

    assert "Traceback" not in result.output
    assert not isinstance(result.exception, (KeyError, AttributeError, TypeError)), result.output


def test_d6_a_direct_plan_on_a_fresh_workspace_works(cli_runner: CliRunner, fresh: Path) -> None:
    planned = _inbox._plan(cli_runner, fresh, "REQ-FRESH-DIRECT", "--kind", "bug", "--domain", "SCPT")

    assert planned.exit_code == 0, planned.output
