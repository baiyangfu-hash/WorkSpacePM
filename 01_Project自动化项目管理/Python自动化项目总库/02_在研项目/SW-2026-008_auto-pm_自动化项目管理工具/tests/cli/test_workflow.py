"""workflow CLI 命令测试 - Phase 2

测试 workflow list / run / status / history 命令
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from auto_pm.cli.workflow import workflow_group
from click.testing import CliRunner

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.cli
class TestWorkflowCLI:
    def test_help(self, cli_runner: CliRunner) -> None:
        """--help 显示子命令"""
        result = cli_runner.invoke(workflow_group, ["--help"])
        assert result.exit_code == 0
        assert "工作流编排与执行管理" in result.output
        assert "list" in result.output
        assert "run" in result.output
        assert "status" in result.output
        assert "history" in result.output

    def test_list_workflows(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """workflow list 列出工作流"""
        monkeypatch.setattr("auto_pm.cli.workflow._resolve_workspace", lambda ctx: temp_workspace)

        result = cli_runner.invoke(workflow_group, ["list"])
        assert result.exit_code == 0
        assert "file-modify" in result.output
        assert "pre-commit" in result.output

    def test_run_file_modify(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """workflow run file-modify 成功运行"""
        monkeypatch.setattr("auto_pm.cli.workflow._resolve_workspace", lambda ctx: temp_workspace)

        test_file = temp_workspace / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        result = cli_runner.invoke(workflow_group, ["run", "file-modify", "--file", str(test_file)])
        assert result.exit_code == 0
        assert "执行成功" in result.output

    def test_workflow_history_and_status(
        self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """workflow history 和 status"""
        monkeypatch.setattr("auto_pm.cli.workflow._resolve_workspace", lambda ctx: temp_workspace)

        test_file = temp_workspace / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        # 运行一次记录
        cli_runner.invoke(workflow_group, ["run", "file-modify", "--file", str(test_file)])

        # 查看 history
        hist_res = cli_runner.invoke(workflow_group, ["history"])
        assert hist_res.exit_code == 0
        assert "file-modify" in hist_res.output
