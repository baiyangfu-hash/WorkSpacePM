"""P3-8: ai_context.json 自动生成测试（CLI 层）

测试 auto_pm.cli.write_ai_context 函数及 CLI 命令（project show / plc check）
执行后自动生成 .auto-pm/ai_context.json 的行为。

覆盖：
- write_ai_context 文件生成与内容结构
- 静默降级（写入失败返回 False 不抛异常）
- 二次调用覆盖（非追加）
- project show / plc check 后自动生成
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from auto_pm.cli import write_ai_context
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


class TestWriteAiContext:
    """write_ai_context 函数单元测试"""

    def test_write_ai_context_creates_file(self, tmp_path: Path) -> None:
        """调用后应生成 .auto-pm/ai_context.json 文件"""
        result = write_ai_context(
            str(tmp_path), "DJ-2026-005", "输送线", "plc", "commissioning"
        )
        assert result is True
        ctx_file = tmp_path / ".auto-pm" / "ai_context.json"
        assert ctx_file.exists()

    def test_write_ai_context_content_structure(self, tmp_path: Path) -> None:
        """生成的 JSON 应包含完整字段结构"""
        write_ai_context(
            str(tmp_path), "DJ-2026-005", "输送线", "plc", "commissioning"
        )
        ctx_file = tmp_path / ".auto-pm" / "ai_context.json"
        content = json.loads(ctx_file.read_text(encoding="utf-8"))

        assert "generated_at" in content
        assert content["source"] == "auto-pm CLI"
        assert "workspace_root" in content
        assert content["entry_mode"] == "direct"
        assert content["intent"] == "plc_review"
        assert content["target_skill"] == "plc-electrical-engineer"
        assert isinstance(content["request_id"], str)
        assert content["request_id"].startswith("CLI-")
        assert content["active_project"] == {
            "id": "DJ-2026-005",
            "name": "输送线",
            "stack": "plc",
            "phase": "commissioning",
        }
        assert content["active_change"] is None
        assert content["active_page"] == "workspace"
        assert content["product_context"]["goal_ref"] == "PM_SESSION_DJ-2026-005.md#product-goal"
        assert content["product_context"]["hypothesis_ref"] == "PM_SESSION_DJ-2026-005.md#hypothesis-ledger"
        assert content["product_context"]["active_hypothesis"] == {}

    def test_write_ai_context_silent_degradation(self, tmp_path: Path) -> None:
        """写入失败时应返回 False，不抛异常（静默降级）"""
        # 使用一个不可能写入的路径（父目录是文件而非目录）
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file", encoding="utf-8")
        invalid_workspace = blocker / "sub"  # 父路径是文件，mkdir 会失败
        result = write_ai_context(
            str(invalid_workspace), "DJ-2026-005", "测试", "plc", "developing"
        )
        assert result is False

    def test_write_ai_context_overwrite(self, tmp_path: Path) -> None:
        """二次调用应覆盖旧文件（非追加）"""
        write_ai_context(str(tmp_path), "DJ-2026-001", "项目一", "plc", "developing")
        ctx_file = tmp_path / ".auto-pm" / "ai_context.json"
        first_content = ctx_file.read_text(encoding="utf-8")

        # 二次调用，改项目编号
        write_ai_context(str(tmp_path), "DJ-2026-002", "项目二", "plc", "production")
        second_content = ctx_file.read_text(encoding="utf-8")

        # 文件应被覆盖（项目编号变化）
        assert first_content != second_content
        second_data = json.loads(second_content)
        assert second_data["active_project"]["id"] == "DJ-2026-002"
        assert second_data["active_project"]["name"] == "项目二"


class TestCliAutoGenerateAiContext:
    """CLI 命令自动生成 ai_context.json 测试"""

    def test_plc_check_generates_ai_context(
        self, cli_runner: CliRunner, tmp_workspace: Path
    ) -> None:
        """plc check <ID> 后应自动生成 ai_context.json"""
        result = cli_runner.invoke(
            cli,
            ["-w", str(tmp_workspace), "plc", "check", "DJ-2026-TEST"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        ctx_file = tmp_workspace / ".auto-pm" / "ai_context.json"
        assert ctx_file.exists(), "plc check 后应自动生成 ai_context.json"
        content = json.loads(ctx_file.read_text(encoding="utf-8"))
        assert content["active_project"]["id"] == "DJ-2026-TEST"
        assert content["source"] == "auto-pm CLI"
        assert content["target_skill"] == "plc-electrical-engineer"

    def test_plc_check_python_project_no_ai_context(
        self, cli_runner: CliRunner, python_project_factory: Callable[..., Path]
    ) -> None:
        """Python 项目（PLC 检查不适用）不应生成 ai_context.json"""
        project_dir = python_project_factory(project_id="SW-2026-PYT", name="工具")
        workspace = project_dir.parent
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "plc", "check", "SW-2026-PYT"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # not_applicable 时不调用 write_ai_context
        ctx_file = workspace / ".auto-pm" / "ai_context.json"
        assert not ctx_file.exists(), "Python 项目 PLC 检查不适用时不应生成 ai_context.json"
