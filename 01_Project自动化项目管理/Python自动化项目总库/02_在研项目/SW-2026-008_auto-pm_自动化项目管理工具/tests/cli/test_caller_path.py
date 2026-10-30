"""TD-SW008-232: relative path arguments mean the caller's folder, not the release folder the launcher runs in."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.caller_path import CALLER_CWD_ENV, CallerPath, anchor_to_caller


def _echo_command() -> click.Command:
    @click.command()
    @click.argument("target", type=CallerPath(exists=True, dir_okay=False, path_type=Path))
    def command(target: Path) -> None:
        click.echo(str(target))

    return command


def test_a_relative_argument_is_anchored_to_the_caller_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    caller = tmp_path / "caller"
    (caller / "backups").mkdir(parents=True)
    (caller / "backups" / "x.db").write_text("x", encoding="utf-8")
    elsewhere = tmp_path / "release"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # what the launcher does: the process runs in the release folder
    monkeypatch.setenv(CALLER_CWD_ENV, str(caller))

    result = CliRunner().invoke(_echo_command(), ["backups/x.db"])

    assert result.exit_code == 0, result.output
    assert Path(result.output.strip()) == caller / "backups" / "x.db"


def test_the_same_argument_is_not_found_without_the_caller_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "caller").mkdir()
    (tmp_path / "caller" / "x.db").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CALLER_CWD_ENV, raising=False)

    result = CliRunner().invoke(_echo_command(), ["x.db"])

    assert result.exit_code == 2 and "does not exist" in result.output  # direct runs keep the plain behaviour


def test_an_absolute_argument_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "abs.db"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setenv(CALLER_CWD_ENV, str(tmp_path / "other"))

    assert anchor_to_caller(str(target)) == str(target)
    assert CliRunner().invoke(_echo_command(), [str(target)]).exit_code == 0


def test_a_path_object_stays_a_path_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CALLER_CWD_ENV, str(tmp_path))

    assert anchor_to_caller(Path("a/b")) == tmp_path / "a" / "b"


def test_no_command_line_path_argument_bypasses_the_caller_anchor() -> None:
    """The sweep: every ``click.Path`` in the CLI package went through ``CallerPath``; a new bare one would resolve against the release folder again."""

    root = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "cli"
    bare = [str(path.relative_to(root)) for path in root.rglob("*.py") if "click.Path(" in path.read_text(encoding="utf-8", errors="strict")]

    assert bare == []
