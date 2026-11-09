"""D-140: ``change edit --files-from`` reads the §5 file list from a text file instead of the command line."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli
from tests.cli.test_change import _create_change_via_cli, _make_plc_project_for_change

pytestmark = [pytest.mark.cli, pytest.mark.usefixtures("identity_guard_off")]


def _new_change(cli_runner: CliRunner, tmp_path: Path) -> tuple[str, Path]:
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")
    return number, next(tmp_path.rglob(f"{number}.md"))


def _edit(cli_runner: CliRunner, tmp_path: Path, number: str, *args: str):  # type: ignore[no-untyped-def]
    return cli_runner.invoke(cli, ["-w", str(tmp_path), "change", "edit", number, *args])


def test_files_from_writes_the_listed_paths_into_section_five(cli_runner: CliRunner, tmp_path: Path) -> None:
    number, record = _new_change(cli_runner, tmp_path)
    listing = tmp_path / "files.txt"
    listing.write_text("# 范围\n测试/路径一.py\n\n  a/b.py  \n𠮷/c.py\n", encoding="utf-8")

    result = _edit(cli_runner, tmp_path, number, "--files-from", str(listing))

    assert result.exit_code == 0, result.output
    text = record.read_text(encoding="utf-8")
    for path in ("测试/路径一.py", "a/b.py", "𠮷/c.py"):
        assert path in text
    assert "# 范围" not in text


def test_files_from_accepts_a_powershell_bom_and_merges_with_file_without_duplicates(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    number, record = _new_change(cli_runner, tmp_path)
    listing = tmp_path / "files.txt"
    listing.write_bytes(b"\xef\xbb\xbfa/b.py\r\nx/y.py\r\n")

    result = _edit(cli_runner, tmp_path, number, "--file", "a/b.py", "--files-from", str(listing))

    assert result.exit_code == 0, result.output
    assert "改后: a/b.py, x/y.py" in result.output  # BOM did not stick to the first path; a/b.py listed once


def test_files_from_refuses_an_empty_list_and_leaves_the_record_alone(cli_runner: CliRunner, tmp_path: Path) -> None:
    number, record = _new_change(cli_runner, tmp_path)
    before = record.read_bytes()
    listing = tmp_path / "empty.txt"
    listing.write_text("# only a comment\n\n", encoding="utf-8")

    result = _edit(cli_runner, tmp_path, number, "--files-from", str(listing))

    assert result.exit_code == 2
    assert "没有任何路径" in result.output
    assert record.read_bytes() == before


def test_files_from_refuses_a_file_that_is_not_utf8(cli_runner: CliRunner, tmp_path: Path) -> None:
    number, record = _new_change(cli_runner, tmp_path)
    before = record.read_bytes()
    listing = tmp_path / "gbk.txt"
    listing.write_bytes("测试/路径.py".encode("gbk"))

    result = _edit(cli_runner, tmp_path, number, "--files-from", str(listing))

    assert result.exit_code == 2
    assert "不是有效的 UTF-8" in result.output
    assert record.read_bytes() == before


def test_files_from_a_missing_file_is_rejected_by_the_option(cli_runner: CliRunner, tmp_path: Path) -> None:
    number, _ = _new_change(cli_runner, tmp_path)

    result = _edit(cli_runner, tmp_path, number, "--files-from", str(tmp_path / "nope.txt"))

    assert result.exit_code == 2


def test_a_relative_files_from_path_means_the_callers_folder_not_the_release_folder(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher runs the release from its own folder and exports the caller's folder (TD-SW008-232)."""

    number, _ = _new_change(cli_runner, tmp_path)
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "files.txt").write_text("a/b.py\n", encoding="utf-8")
    release = tmp_path / "release"
    release.mkdir()
    monkeypatch.chdir(release)
    monkeypatch.setenv("AUTO_PM_CALLER_CWD", str(caller))

    result = _edit(cli_runner, tmp_path, number, "--files-from", "files.txt")

    assert result.exit_code == 0, result.output
    assert "改后: a/b.py" in result.output
