"""template CLI 命令测试 - V0.5.2 步骤2

覆盖 template_group 2 个子命令：
- list                列出可用模板
- update <ID>         对已有项目执行 Copier 模板增量更新

测试策略：
- list 无需项目数据，验证模板列表输出
- update 需要已存在的项目（含 .copier-answers.yml），验证增量更新

3 个用例分布：
- list: 1（从 test_plc.py 迁移，统一组织）
- update: 2（不存在项目/正常更新或缺少 .copier-answers.yml）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

# ── list 命令测试（1 用例，从 test_plc.py 迁移）──────────────────────────────


@pytest.mark.cli
def test_template_list(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 template list 列出可用模板"""
    result = cli_runner.invoke(
        cli,
        ["template", "list"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


# ── update 命令测试（2 用例）──────────────────────────────


@pytest.mark.cli
def test_template_update_nonexistent_project(cli_runner: CliRunner, tmp_path: Path) -> None:
    """update 不存在的项目 exit_code=1"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "template", "update", "DJ-2026-NOTEXIST"],
    )
    assert result.exit_code == 1
    assert "项目不存在" in result.output


@pytest.mark.cli
def test_template_update_missing_copier_answers(cli_runner: CliRunner, tmp_path: Path) -> None:
    """update 项目缺少 .copier-answers.yml 时 exit_code=1

    Copier 增量更新依赖 .copier-answers.yml，缺少时报错。
    """
    # 创建一个 PLC 项目（仅有 .plc.json，无 .copier-answers.yml）
    project_dir = tmp_path / "DJ-2026-NOANS_无答案项目"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps({"name": "DJ-2026-NOANS", "version": "V1.0.0"}),
        encoding="utf-8",
    )

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "template", "update", "DJ-2026-NOANS"],
    )
    assert result.exit_code == 1
    # 缺少 .copier-answers.yml 的错误信息
    assert ".copier-answers.yml" in result.output or "更新失败" in result.output
