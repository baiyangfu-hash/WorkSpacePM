"""D-133: an argument that reached Python with a lone surrogate is refused at the door, naming which argument it is."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli
from auto_pm.ui.cli.argv_guard import ARGV_EXIT_CODE, broken_argument_message
from tests.cli.test_change import _create_change_via_cli, _make_plc_project_for_change

BROKEN = "测试/路径\ude64.py"  # a low surrogate with no high half: what a cut-off 4-byte character leaves behind


def test_sound_arguments_pass_including_chinese_and_astral_characters() -> None:
    assert broken_argument_message(["change", "edit", "CHG-1", "--file", "测试/路径.py", "--file", "a/𠮷.py"]) is None
    assert broken_argument_message([]) is None


def test_the_message_names_the_argument_and_its_place_among_the_repeated_option() -> None:
    args = ["change", "edit", "CHG-1", "--file", "a.py", "--file", "b.py", "--file", BROKEN, "--file", "d.py"]

    message = broken_argument_message(args)

    assert message is not None
    assert "第 9 个命令行参数" in message
    assert "第 3 个 --file 的值" in message
    assert "\\ude64" in message  # shown through ascii(), so the line itself can always be printed
    assert "没有改动任何文件" in message


def test_a_broken_argument_that_is_not_an_option_value_is_still_named_by_position() -> None:
    message = broken_argument_message(["change", BROKEN])

    assert message is not None and "第 2 个命令行参数" in message and "个 --" not in message


@pytest.mark.cli
@pytest.mark.usefixtures("identity_guard_off")
def test_change_edit_with_a_broken_file_argument_is_refused_before_anything_is_written(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")
    record = next(tmp_path.rglob(f"{change_number}.md"))
    before = record.read_bytes()

    result = cli_runner.invoke(
        cli, ["-w", str(tmp_path), "change", "edit", change_number, "--file", "ok.py", "--file", BROKEN]
    )

    assert result.exit_code == ARGV_EXIT_CODE
    assert "第 2 个 --file 的值" in result.output
    assert "codec" not in result.output  # not the old failure from deep inside the write
    assert record.read_bytes() == before


@pytest.mark.cli
@pytest.mark.usefixtures("identity_guard_off")
def test_other_commands_with_path_options_are_refused_the_same_way(cli_runner: CliRunner, tmp_path: Path) -> None:
    for command in (["claim", "open", "x", "--paths", BROKEN], ["continuity", "run", "start", "--owned", BROKEN]):
        result = cli_runner.invoke(cli, ["-w", str(tmp_path), *command])
        assert result.exit_code == ARGV_EXIT_CODE, command
        assert "命令行参数的编码损坏" in result.output, command
