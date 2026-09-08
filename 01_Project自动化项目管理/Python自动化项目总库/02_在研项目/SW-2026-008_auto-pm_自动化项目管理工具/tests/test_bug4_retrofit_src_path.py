"""Bug-4 回归测试: retrofit 命令 _src_path 推断错误

问题: retrofit 命令对 python 项目写入 ``templates/python-standard``，
      实际模板是 ``python-tool``；plc 项目应为 ``plc-standard-project``。
修复: 使用与 cmd_create/GuiApi.STACK_TEMPLATE_MAP 一致的映射:
      plc → plc-standard-project, python → python-tool。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from auto_pm.cli.__main__ import cli
from auto_pm.models import ProjectInfo
from click.testing import CliRunner


def _make_plc_project(workspace: Path, project_id: str, name: str) -> Path:
    """创建一个由 .plc.json 识别的 PLC 项目（无 .copier-answers.yml）"""
    project_dir = workspace / f"{project_id}_{name}"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {"name": project_id, "version": "V1.0.0", "description": name},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_dir


class TestRetrofitPlcSrcPath:
    """retrofit 对 PLC 项目的 _src_path 推断"""

    def test_retrofit_plc_writes_plc_standard(self, tmp_path: Path) -> None:
        """PLC 项目 retrofit 应写入 templates/plc-standard-project"""
        workspace = tmp_path
        project_id = "DJ-2026-001"
        _make_plc_project(workspace, project_id, "测试项目")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "retrofit", project_id],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # 读取生成的 .copier-answers.yml
        answers_path = workspace / f"{project_id}_测试项目" / ".copier-answers.yml"
        assert answers_path.exists()
        answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
        assert answers["_src_path"] == "templates/plc-standard-project"


class TestRetrofitPythonSrcPath:
    """retrofit 对 Python 项目的 _src_path 推断"""

    @patch("auto_pm.cli.project.ProjectService")
    def test_retrofit_python_writes_python_tool(
        self, mock_svc_class: MagicMock, tmp_path: Path
    ) -> None:
        """Python 项目 retrofit 应写入 templates/python-tool（而非 python-standard）"""
        workspace = tmp_path
        project_id = "SW-2026-010"
        project_dir = workspace / f"{project_id}_测试项目"
        project_dir.mkdir()

        # ProjectService 无法在无 .copier-answers.yml 时识别 python 技术栈，
        # 因此 mock get_project 返回 stack="python" 的项目
        mock_svc = mock_svc_class.return_value
        mock_svc.get_project.return_value = ProjectInfo(
            project_id=project_id,
            name="测试项目",
            path=str(project_dir),
            stack="python",
            version="V1.0.0",
            description="测试项目",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "retrofit", project_id],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        answers_path = project_dir / ".copier-answers.yml"
        assert answers_path.exists()
        answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
        # 修复前: templates/python-standard（错误）
        # 修复后: templates/python-tool（正确）
        assert answers["_src_path"] == "templates/python-tool"

    @patch("auto_pm.cli.project.ProjectService")
    def test_retrofit_python_not_python_standard(
        self, mock_svc_class: MagicMock, tmp_path: Path
    ) -> None:
        """Python 项目 retrofit 不应写入 templates/python-standard"""
        workspace = tmp_path
        project_id = "SW-2026-011"
        project_dir = workspace / f"{project_id}_测试项目"
        project_dir.mkdir()

        mock_svc = mock_svc_class.return_value
        mock_svc.get_project.return_value = ProjectInfo(
            project_id=project_id,
            name="测试项目",
            path=str(project_dir),
            stack="python",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "retrofit", project_id],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        answers_path = project_dir / ".copier-answers.yml"
        answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
        assert answers["_src_path"] != "templates/python-standard"


class TestRetrofitSkipExisting:
    """retrofit 在已有 .copier-answers.yml 时跳过"""

    def test_retrofit_skips_when_answers_exist(self, tmp_path: Path) -> None:
        """项目已有 .copier-answers.yml 时应跳过"""
        workspace = tmp_path
        project_id = "DJ-2026-002"
        project_dir = _make_plc_project(workspace, project_id, "已有项目")
        # 预先创建 .copier-answers.yml
        (project_dir / ".copier-answers.yml").write_text(
            "_src_path: templates/existing\n", encoding="utf-8"
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "retrofit", project_id],
        )
        assert result.exit_code == 0
        # H-8: .copier-answers.yml 已存在时跳过该步骤（继续补全 PLC 标志文件）
        assert "跳过" in result.output
