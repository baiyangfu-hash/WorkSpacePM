"""Safe-default routing and lazy crash-log tests for `auto-pm gui`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli import gui as gui_module
from auto_pm.ui.cli.__main__ import cli


def test_gui_defaults_to_the_read_only_boss_cockpit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def run_boss(workspace: str, debug: bool) -> int:
        calls.append(("boss", workspace))
        return 0

    def run_legacy(workspace: str, debug: bool) -> int:
        calls.append(("legacy", workspace))
        return 0

    monkeypatch.setattr(gui_module, "_install_crash_handler", lambda: None)
    monkeypatch.setattr(gui_module, "_run_boss_cockpit", run_boss)
    monkeypatch.setattr(gui_module, "_run_qml_gui", run_legacy)

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "gui"])

    assert result.exit_code == 0
    assert calls == [("boss", str(tmp_path))]


def test_gui_opens_the_old_workbench_only_when_explicitly_requested(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def run_boss(workspace: str, debug: bool) -> int:
        calls.append("boss")
        return 0

    def run_legacy(workspace: str, debug: bool) -> int:
        calls.append("legacy")
        return 0

    monkeypatch.setattr(gui_module, "_install_crash_handler", lambda: None)
    monkeypatch.setattr(gui_module, "_run_boss_cockpit", run_boss)
    monkeypatch.setattr(gui_module, "_run_qml_gui", run_legacy)

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "gui", "--advanced"])

    assert result.exit_code == 0
    assert calls == ["legacy"]


def test_crash_log_directory_is_not_created_until_an_actual_crash(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    previous_hook = sys.excepthook

    class _PathForTest:
        @staticmethod
        def home() -> Path:
            return home

    monkeypatch.setattr(gui_module, "Path", _PathForTest)
    try:
        gui_module._install_crash_handler()
        assert not home.exists()
    finally:
        sys.excepthook = previous_hook


def test_default_window_never_imports_legacy_write_side_effects() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "auto_pm"
        / "ui"
        / "boss_qml_window.py"
    ).read_text(encoding="utf-8")

    for prohibited in (
        "DatabaseManager",
        "sync_to_cache",
        "LedgerReconciler",
        "FileWatcherBridge",
        "qml_main_window",
    ):
        assert prohibited not in source


def test_advanced_gui_refuses_a_database_path_as_workspace_without_a_traceback(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """TD-SW008-183：`-w` 指到 .db 路径时专业工作台给人话并返回非零，不抛堆栈，也不在里面建 .auto-pm。"""
    from auto_pm.ui.qml_main_window import run_qml_gui

    bad = tmp_path / "auto-pm.db"
    bad.mkdir()
    assert run_qml_gui(str(bad)) == 2
    assert "工作空间根目录不能是数据库文件" in capsys.readouterr().err
    assert not (bad / ".auto-pm").exists()
