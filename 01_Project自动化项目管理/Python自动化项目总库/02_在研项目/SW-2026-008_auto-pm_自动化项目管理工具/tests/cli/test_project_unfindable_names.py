"""TD-SW008-619（D-354）：项目文件夹名带“归档”“备份”、archive、trash、backup，或以 . _ 开头时，
扫描器和登记表都会跳过它；project create、project import 先拒绝，不建出找不到的项目。"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.project_scanner import scan_skips_folder, unfindable_project_folder
from auto_pm.application.core.project_service import ProjectService
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")

RESEARCH = ("01_Project自动化项目管理", "Python自动化项目总库", "02_在研项目")


@pytest.mark.parametrize(
    "name",
    ["DJ-2026-031_历史归档", "SW-2026-031_Archive", "SW-2026-031_trash工具", "SW-2026-031_备份", "SW-2026-031_backup", "_old", ".hidden"],
)
def test_names_the_scan_or_the_registry_would_skip_are_named(name: str) -> None:
    assert unfindable_project_folder(name)


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("DJ-2026-031_历史归档", "带“归档”字样"),
        ("SW-2026-031_Archive", "带“archive”字样"),
        ("SW-2026-031_trash工具", "带“trash”字样"),
        ("SW-2026-031_备份", "带“备份”字样"),
        ("SW-2026-031_BackUp", "带“backup”字样"),
        ("SW-2026-031_备份archive", "带“备份”“archive”字样"),
        ("_old", "以 _ 开头"),
        (".hidden", "以 . 开头"),
    ],
)
def test_the_refusal_names_the_exact_reason(name: str, reason: str) -> None:
    """提示只说这个名字真犯的那一条，不把五种原因一股脑列出来。"""
    message = unfindable_project_folder(name)
    assert f"项目文件夹名 {name} {reason}，" in message
    assert "这类字样" not in message


@pytest.mark.parametrize(
    "name",
    [
        "_x",
        "__x",
        ".x",
        "a归档",
        "xArchive",
        "TRASH",
        "SW-2026-031_ARCHIVE备份",
        "DJ-2026-031_trash",
        "DJ-2026-031_边框缓存机",
        "SW-2026-031_auto-pm",
    ],
)
def test_every_name_the_scanner_skips_is_refused(name: str) -> None:
    """扫描器会跳过的名字，这里一定拒（拒的判断直接调 scan_skips_folder，不另抄一份规则）。"""
    if scan_skips_folder(name):
        assert unfindable_project_folder(name)


def test_refusal_follows_the_scanner_rule_not_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    """扫描器以后多跳过一类名字，这里不用跟着改也会拒：拒的判断调的就是 scan_skips_folder。"""
    from auto_pm.application.core import project_scanner

    monkeypatch.setattr(project_scanner, "scan_skips_folder", lambda name: name == "SW-2026-031_新规则")
    message = project_scanner.unfindable_project_folder("SW-2026-031_新规则")
    assert "是扫描器会跳过的名字" in message and "建出来也找不到" in message


@pytest.mark.parametrize("name", ["DJ-2026-031_边框缓存机", "SW-2026-031_auto-pm"])
def test_ordinary_names_pass(name: str) -> None:
    assert unfindable_project_folder(name) == ""
    assert not scan_skips_folder(name)


def test_the_scanner_rule_is_unchanged() -> None:
    """扫描器原来的跳过规则一条不多一条不少（backup、备份只在登记表那边拒，扫描照旧能看到）。"""
    for name in ("_x", "__x", ".x", "a归档", "xArchive", "TRASH"):
        assert scan_skips_folder(name)
    for name in ("SW-2026-031_backup", "SW-2026-031_备份"):
        assert not scan_skips_folder(name)


def test_project_create_refuses_a_name_the_scan_would_skip(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.joinpath(*RESEARCH).mkdir(parents=True)
    result = CliRunner().invoke(
        cli,
        ["-w", str(ws), "project", "create", "--stack", "python", "--id", "SW-2026-031", "--name", "历史归档"],
        catch_exceptions=False,
    )
    assert result.exit_code == 1, result.output
    assert "建出来也找不到" in result.output
    assert not any(ws.joinpath(*RESEARCH).iterdir())


def test_project_import_refuses_a_source_folder_the_scan_would_skip(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.joinpath(*RESEARCH).mkdir(parents=True)
    src = tmp_path / "incoming" / "SW-2026-032_archive"
    (src / "core").mkdir(parents=True)
    (src / "core" / "a.py").write_text("X = 1\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["-w", str(ws), "project", "import", str(src)], catch_exceptions=False)
    assert result.exit_code == 1, result.output
    assert "建出来也找不到" in result.output
    assert not any(ws.joinpath(*RESEARCH).iterdir())


def test_window_import_refuses_the_same_names(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.joinpath(*RESEARCH).mkdir(parents=True)
    src = tmp_path / "incoming" / "SW-2026-033_备份"
    (src / "core").mkdir(parents=True)
    (src / "core" / "a.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="建出来也找不到"):
        ProjectService(str(ws)).import_project(str(src))
    assert not any(ws.joinpath(*RESEARCH).iterdir())
