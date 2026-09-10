"""Safe-default routing and lazy crash-log tests for `auto-pm gui`."""

from __future__ import annotations

import sys
from pathlib import Path

from auto_pm.cli import gui as gui_module
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def test_gui_defaults_to_the_read_only_boss_cockpit(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_module, "_install_crash_handler", lambda: None)
    monkeypatch.setattr(
        gui_module,
        "_run_boss_cockpit",
        lambda workspace, debug: calls.append(("boss", workspace)) or 0,
    )
    monkeypatch.setattr(
        gui_module,
        "_run_qml_gui",
        lambda workspace, debug: calls.append(("legacy", workspace)) or 0,
    )

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "gui"])

    assert result.exit_code == 0
    assert calls == [("boss", str(tmp_path))]


def test_gui_opens_the_old_workbench_only_when_explicitly_requested(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    monkeypatch.setattr(gui_module, "_install_crash_handler", lambda: None)
    monkeypatch.setattr(gui_module, "_run_boss_cockpit", lambda workspace, debug: calls.append("boss") or 0)
    monkeypatch.setattr(gui_module, "_run_qml_gui", lambda workspace, debug: calls.append("legacy") or 0)

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
