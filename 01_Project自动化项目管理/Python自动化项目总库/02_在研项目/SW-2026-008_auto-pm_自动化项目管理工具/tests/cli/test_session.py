"""PM_SESSION CLI 命令组测试 - CHG-088 Stage 2

测试 auto_pm/cli/session.py 中的 pm-session check/archive/view 子命令。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.cli.session import pm_session_group
from click.testing import CliRunner

SAMPLE_PM_SESSION = """# PM_SESSION_TEST

## 0. Meta

- project_id: TEST-001
- last_updated: 2026-07-04

## 1. Positioning

- one_liner: 测试项目

## 2. Current Focus

- current_focus: 当前焦点

## 3. Status Summary

- in_progress: 测试中

## 4. Artifacts Index

- req: doc.md

## 5. Logs

- change_log: 测试日志

## 6. Implementation Log

- 2026-07-04 测试实施记录

## 8. Handoff Notes

- current_state: 测试状态

## 9. Next Actions

- [待启动] 测试下一步
"""


@pytest.fixture
def workspace_with_pm_session(tmp_path: Path) -> Path:
    """创建包含 PM_SESSION 文件的工作空间"""
    f = tmp_path / "PM_SESSION_TEST-001.md"
    f.write_text(SAMPLE_PM_SESSION, encoding="utf-8")
    return tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestPmSessionCheck:
    def test_check_healthy_file(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            ["check", "-w", str(workspace_with_pm_session)],
        )
        assert result.exit_code == 0
        assert "健康" in result.output or "✅" in result.output

    def test_check_with_project_id(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            ["check", "-w", str(workspace_with_pm_session), "--project-id", "TEST-001"],
        )
        assert result.exit_code == 0

    def test_check_quiet_mode(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            ["check", "-w", str(workspace_with_pm_session), "--quiet"],
        )
        assert result.exit_code == 0

    def test_check_no_pm_session_file(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            ["check", "-w", str(tmp_path)],
        )
        assert result.exit_code == 2
        assert "未找到" in result.output or "错误" in result.output

    def test_check_no_workspace(self, runner: CliRunner) -> None:
        result = runner.invoke(pm_session_group, ["check"])
        assert result.exit_code == 1


class TestPmSessionArchive:
    def test_archive_dry_run(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            [
                "archive",
                "-w",
                str(workspace_with_pm_session),
                "--section",
                "6",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        # 主文件未被修改
        content = (workspace_with_pm_session / "PM_SESSION_TEST-001.md").read_text(
            encoding="utf-8"
        )
        assert "## 6. Implementation Log" in content

    def test_archive_actual_run(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            [
                "archive",
                "-w",
                str(workspace_with_pm_session),
                "--section",
                "6",
                "--no-backup",
            ],
        )
        assert result.exit_code == 0
        assert "归档完成" in result.output or "✅" in result.output
        # 主文件 §6 已被归档
        content = (workspace_with_pm_session / "PM_SESSION_TEST-001.md").read_text(
            encoding="utf-8"
        )
        assert "## 6. Implementation Log" not in content
        # 归档文件已创建
        archive_files = list(
            (workspace_with_pm_session / "05_收尾" / "PM_SESSION归档").glob("*.md")
        )
        assert len(archive_files) > 0

    def test_archive_nonexistent_section(
        self, runner: CliRunner, workspace_with_pm_session: Path
    ) -> None:
        result = runner.invoke(
            pm_session_group,
            [
                "archive",
                "-w",
                str(workspace_with_pm_session),
                "--section",
                "99",
                "--dry-run",
            ],
        )
        assert result.exit_code == 2

    def test_archive_with_custom_output(
        self, runner: CliRunner, workspace_with_pm_session: Path
    ) -> None:
        custom_archive = workspace_with_pm_session / "custom_archive.md"
        result = runner.invoke(
            pm_session_group,
            [
                "archive",
                "-w",
                str(workspace_with_pm_session),
                "--section",
                "6",
                "--archive-file",
                str(custom_archive),
                "--no-backup",
            ],
        )
        assert result.exit_code == 0
        assert custom_archive.exists()


class TestPmSessionView:
    def test_view_to_stdout(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            ["view", "-w", str(workspace_with_pm_session)],
        )
        assert result.exit_code == 0
        assert "PM_SESSION 只读视图" in result.output
        assert "§2" in result.output
        assert "§3" in result.output

    def test_view_to_file(self, runner: CliRunner, workspace_with_pm_session: Path) -> None:
        output_file = workspace_with_pm_session / "view_output.md"
        result = runner.invoke(
            pm_session_group,
            ["view", "-w", str(workspace_with_pm_session), "-o", str(output_file)],
        )
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "PM_SESSION 只读视图" in content

    def test_view_no_pm_session(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            pm_session_group,
            ["view", "-w", str(tmp_path)],
        )
        assert result.exit_code == 2


class TestPmSessionGroupRegistration:
    def test_group_has_check_command(self) -> None:
        assert "check" in pm_session_group.commands

    def test_group_has_archive_command(self) -> None:
        assert "archive" in pm_session_group.commands

    def test_group_has_view_command(self) -> None:
        assert "view" in pm_session_group.commands

    def test_group_name(self) -> None:
        assert pm_session_group.name == "pm-session"
