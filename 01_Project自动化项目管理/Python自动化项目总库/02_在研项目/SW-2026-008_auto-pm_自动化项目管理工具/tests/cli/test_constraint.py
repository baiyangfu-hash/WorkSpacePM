"""constraint CLI 命令测试 - CHG-SCPT-2026-137 Phase 1 收尾

测试 constraint list / check / guard / verify / heal
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from auto_pm.cli.constraint import constraint_group
from auto_pm.constraint.guard import BOM
from click.testing import CliRunner

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """临时工作空间"""
    return tmp_path


@pytest.mark.cli
class TestConstraintCLI:
    def test_help(self, cli_runner: CliRunner) -> None:
        """--help 显示子命令"""
        result = cli_runner.invoke(constraint_group, ["--help"])
        assert result.exit_code == 0
        assert "约束管理" in result.output
        assert "list" in result.output
        assert "check" in result.output
        assert "guard" in result.output
        assert "verify" in result.output
        assert "heal" in result.output

    def test_list_constraints(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """constraint list 正确列出已加载的约束"""
        monkeypatch.setattr("auto_pm.cli.constraint._resolve_workspace", lambda ctx: temp_workspace)

        result = cli_runner.invoke(constraint_group, ["list"])
        assert result.exit_code == 0
        assert "CST-FILE-001" in result.output
        assert "CST-FILE-002" in result.output
        assert "共 10 个约束定义" in result.output

    def test_check_clean(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """constraint check 没有违规"""
        monkeypatch.setattr("auto_pm.cli.constraint._resolve_workspace", lambda ctx: temp_workspace)

        # 创建一个无 BOM 的干净文件
        clean_file = temp_workspace / "clean.md"
        clean_file.write_text("# Hello", encoding="utf-8")

        result = cli_runner.invoke(constraint_group, ["check"])
        assert result.exit_code == 0
        assert "所有约束检查通过" in result.output

    def test_check_violations(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """constraint check 检测到违规"""
        monkeypatch.setattr("auto_pm.cli.constraint._resolve_workspace", lambda ctx: temp_workspace)

        # 创建一个带 5 个 BOM 的违规文件
        bad_file = temp_workspace / "bad.md"
        bad_file.write_bytes(BOM * 5 + b"# Bad")

        result = cli_runner.invoke(constraint_group, ["check"])
        # 不加 --gate 默认 exit_code 是 0
        assert result.exit_code == 0
        assert "发现 1 个违规" in result.output
        assert "CST-FILE-002" in result.output

        # 加 --gate 时 exit_code 应为 1
        result_gate = cli_runner.invoke(constraint_group, ["check", "--gate"])
        assert result_gate.exit_code != 0

    def test_check_json_output(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """constraint check --json 格式化输出"""
        monkeypatch.setattr("auto_pm.cli.constraint._resolve_workspace", lambda ctx: temp_workspace)

        bad_file = temp_workspace / "bad.md"
        bad_file.write_bytes(BOM * 5 + b"# Bad")

        result = cli_runner.invoke(constraint_group, ["check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["violations_count"] == 1
        assert data["violations"][0]["constraint_id"] == "CST-FILE-002"

    def test_guard_and_verify(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """constraint guard 登记快照 + verify 校验"""
        monkeypatch.setattr("auto_pm.cli.constraint._resolve_workspace", lambda ctx: temp_workspace)

        test_file = temp_workspace / "test.md"
        test_file.write_text("# Hello", encoding="utf-8")

        # guard 登记
        result_guard = cli_runner.invoke(constraint_group, ["guard", str(test_file)])
        assert result_guard.exit_code == 0
        assert "快照已登记" in result_guard.output

        # verify 验证
        result_verify = cli_runner.invoke(constraint_group, ["verify", str(test_file)])
        assert result_verify.exit_code == 0
        assert "文件完整，未检测到外部修改" in result_verify.output

        # 外部修改
        test_file.write_text("# Modified", encoding="utf-8")
        result_verify_fail = cli_runner.invoke(constraint_group, ["verify", str(test_file)])
        assert result_verify_fail.exit_code != 0
        assert "文件已被修改" in result_verify_fail.output

    def test_heal_command(self, cli_runner: CliRunner, temp_workspace: Path, monkeypatch: MonkeyPatch) -> None:
        """constraint heal 自愈命令"""
        monkeypatch.setattr("auto_pm.cli.constraint._resolve_workspace", lambda ctx: temp_workspace)

        bad_file = temp_workspace / "bad.md"
        bad_file.write_bytes(BOM * 5 + b"# Bad")

        # heal --file dry-run
        result_dry = cli_runner.invoke(constraint_group, ["heal", "--file", "bad.md", "--dry-run"])
        assert result_dry.exit_code == 0
        assert "将剥离" in result_dry.output
        assert bad_file.read_bytes().startswith(BOM * 5)

        # heal --file
        result_heal = cli_runner.invoke(constraint_group, ["heal", "--file", "bad.md"])
        assert result_heal.exit_code == 0
        assert "剥离" in result_heal.output
        assert bad_file.read_bytes() == b"# Bad"

        # heal --all
        bad_file2 = temp_workspace / "bad2.md"
        bad_file2.write_bytes(BOM * 5 + b"# Bad2")
        result_all = cli_runner.invoke(constraint_group, ["heal", "--all"])
        assert result_all.exit_code == 0
        assert "修复 1 个文件" in result_all.output
        assert bad_file2.read_bytes() == b"# Bad2"
