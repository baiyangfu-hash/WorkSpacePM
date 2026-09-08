"""项目 CRUD 单元测试

覆盖 ProjectService 新方法与 CLI project 命令增强：
- retrofit_project_by_path: 补全 .copier-answers.yml
- CLI project import: 导入外部目录
- CLI project list: --business-line / --stack 筛选
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from auto_pm.cli.__main__ import cli
from auto_pm.core.project_service import ProjectService
from click.testing import CliRunner

# ── retrofit_project_by_path 测试 ────────────────────────


class TestRetrofitProjectByPath:
    """ProjectService.retrofit_project_by_path 测试"""

    def test_retrofit_plc_project(self, tmp_path: Path) -> None:
        """PLC 项目（含 .plc.json）补全 .copier-answers.yml"""
        project_dir = tmp_path / "DJ-2026-001_测试PLC项目"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {
                    "name": "DJ-2026-001",
                    "version": "V1.0.0",
                    "description": "PLC测试项目",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = ProjectService(str(tmp_path))
        result_path = svc.retrofit_project_by_path(str(project_dir))

        assert os.path.isfile(result_path)
        answers = yaml.safe_load(
            (project_dir / ".copier-answers.yml").read_text(encoding="utf-8")
        )
        # 应从 .plc.json 提取元数据
        assert answers["project_id"] == "DJ-2026-001"
        assert answers["project_name"] == "DJ-2026-001"
        assert answers["description"] == "PLC测试项目"
        assert answers["version"] == "V1.0.0"
        # PLC 项目模板路径
        assert answers["_src_path"] == "templates/plc-standard-project"

    def test_retrofit_python_project(self, tmp_path: Path) -> None:
        """非 PLC 项目（无 .plc.json）补全 .copier-answers.yml"""
        project_dir = tmp_path / "SW-2026-010_测试Python项目"
        project_dir.mkdir()

        svc = ProjectService(str(tmp_path))
        result_path = svc.retrofit_project_by_path(str(project_dir))

        assert os.path.isfile(result_path)
        answers = yaml.safe_load(
            (project_dir / ".copier-answers.yml").read_text(encoding="utf-8")
        )
        # 无 .plc.json 时从目录名提取 project_id
        assert answers["project_id"] == "SW-2026-010"
        assert answers["project_name"] == "SW-2026-010_测试Python项目"
        # 无 .plc.json → stack="unknown" → template="unknown"
        assert answers["_src_path"] == "templates/unknown"

    def test_retrofit_with_pm_session(self, tmp_path: Path) -> None:
        """含 PM_SESSION_*.md 的项目补全时从文件名提取 project_id"""
        project_dir = tmp_path / "自定义目录名"
        project_dir.mkdir()
        (project_dir / "PM_SESSION_ZD-2026-005.md").write_text(
            "# 会话\n", encoding="utf-8"
        )

        svc = ProjectService(str(tmp_path))
        svc.retrofit_project_by_path(str(project_dir))

        answers = yaml.safe_load(
            (project_dir / ".copier-answers.yml").read_text(encoding="utf-8")
        )
        # 应从 PM_SESSION 文件名提取 project_id
        assert answers["project_id"] == "ZD-2026-005"

    def test_retrofit_existing_answers_raises(self, tmp_path: Path) -> None:
        """已有 .copier-answers.yml 时应抛 FileExistsError"""
        project_dir = tmp_path / "DJ-2026-002_已有项目"
        project_dir.mkdir()
        existing_content = "_src_path: templates/existing\nproject_id: DJ-2026-002\n"
        (project_dir / ".copier-answers.yml").write_text(
            existing_content, encoding="utf-8"
        )

        svc = ProjectService(str(tmp_path))
        with pytest.raises(FileExistsError, match="已存在"):
            svc.retrofit_project_by_path(str(project_dir))

        # 原文件不应被覆盖
        assert (
            (project_dir / ".copier-answers.yml").read_text(encoding="utf-8")
            == existing_content
        )

    def test_retrofit_invalid_path_raises(self, tmp_path: Path) -> None:
        """无效路径应抛 FileNotFoundError"""
        svc = ProjectService(str(tmp_path))
        with pytest.raises(FileNotFoundError, match="项目目录不存在"):
            svc.retrofit_project_by_path(str(tmp_path / "nonexistent"))

    def test_retrofit_appends_shc014_index_for_nested_plc_json(
        self, tmp_path: Path
    ) -> None:
        """C Fix: 嵌套 .plc.json + PM_SESSION §4 时，retrofit 自动追加 SHC-014 兼容索引

        验证：存量 PLC 项目（.plc.json 在子目录）接管后，PM_SESSION §4 被注入
        req/int/tec/dsn 标准索引条目，使 SHC-014 门禁可通过。
        """
        project_dir = tmp_path / "DJ-2026-SHC"
        project_dir.mkdir()

        # 嵌套 .plc.json（适配 02_PLC程序/PLC_ST/ 结构）
        plc_st = project_dir / "02_PLC程序" / "PLC_ST"
        plc_st.mkdir(parents=True)
        (plc_st / ".plc.json").write_text(
            json.dumps(
                {"name": "DJ-2026-SHC", "version": "V1.0.0", "description": "测试"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # 文档文件（含标准后缀）
        doc_dir = project_dir / "00_doc"
        doc_dir.mkdir()
        (doc_dir / "001_DJ-2026-SHC_需求分析_REQ.md").write_text("# REQ", encoding="utf-8")
        (doc_dir / "002_DJ-2026-SHC_技术方案_TEC.md").write_text("# TEC", encoding="utf-8")

        prd_dir = plc_st / "PRD"
        prd_dir.mkdir()
        (prd_dir / "接口文档_INT.md").write_text("# INT", encoding="utf-8")
        (prd_dir / "详细设计说明书_DSN.md").write_text("# DSN", encoding="utf-8")

        # PM_SESSION 含 §4
        (project_dir / "PM_SESSION_DJ-2026-SHC.md").write_text(
            "## 4. Artifacts Index\n- arc: some_arc.md\n\n## 5. Change Records\n",
            encoding="utf-8",
        )

        svc = ProjectService(str(tmp_path))
        svc.retrofit_project_by_path(str(project_dir))

        pm_content = (project_dir / "PM_SESSION_DJ-2026-SHC.md").read_text(encoding="utf-8")

        # 验证四类条目全部注入
        assert "- req:" in pm_content
        assert "- int:" in pm_content
        assert "- tec:" in pm_content
        assert "- dsn:" in pm_content
        # 验证标记存在（幂等保护）
        assert "auto-pm SHC-014" in pm_content
        # 验证条目在 §4 和 §5 之间（插入点正确）
        sec4_pos = pm_content.index("## 4.")
        sec5_pos = pm_content.index("## 5.")
        req_pos = pm_content.index("- req:")
        assert sec4_pos < req_pos < sec5_pos

        # 同时验证 .copier-answers.yml stack=plc
        answers = yaml.safe_load(
            (project_dir / ".copier-answers.yml").read_text(encoding="utf-8")
        )
        assert answers["_src_path"] == "templates/plc-standard-project"

    def test_retrofit_shc014_index_is_idempotent(self, tmp_path: Path) -> None:
        """C Fix 幂等性：重复 retrofit 时不重复追加 SHC-014 条目"""
        project_dir = tmp_path / "DJ-2026-IDEM"
        project_dir.mkdir()

        (project_dir / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-IDEM", "version": "V1.0.0"}),
            encoding="utf-8",
        )
        (project_dir / "001_需求_REQ.md").write_text("# REQ", encoding="utf-8")
        (project_dir / "PM_SESSION_DJ-2026-IDEM.md").write_text(
            "## 4. Artifacts Index\n\n## 5. Other\n",
            encoding="utf-8",
        )

        svc = ProjectService(str(tmp_path))
        svc.retrofit_project_by_path(str(project_dir))

        pm_after_first = (project_dir / "PM_SESSION_DJ-2026-IDEM.md").read_text(
            encoding="utf-8"
        )
        req_count_first = pm_after_first.count("- req:")

        # 删除 .copier-answers.yml 再次 retrofit（模拟重复操作）
        (project_dir / ".copier-answers.yml").unlink()
        svc2 = ProjectService(str(tmp_path))
        svc2.retrofit_project_by_path(str(project_dir))

        pm_after_second = (project_dir / "PM_SESSION_DJ-2026-IDEM.md").read_text(
            encoding="utf-8"
        )
        req_count_second = pm_after_second.count("- req:")

        # 条目数量不应增加
        assert req_count_second == req_count_first


class TestInitProjectPmFramework:
    """ProjectService.init_project_pm_framework 测试"""

    def test_init_pm_plc(self, tmp_path: Path) -> None:
        """初始化 PLC 项目的 PM 框架"""
        project_dir = tmp_path / "DJ-2026-000_测试项目"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {
                    "name": "DJ-2026-000",
                    "version": "V1.0.0",
                    "description": "测试",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = ProjectService(str(tmp_path))
        svc.init_project_pm_framework(
            project_path=str(project_dir),
            project_id="DJ-2026-000",
            project_name="测试项目",
            stack_type="plc",
            author="plc_test_author",
        )

        # 1. 验证 .copier-answers.yml 补齐
        assert (project_dir / ".copier-answers.yml").exists()

        # 2. 验证 PLC 专属目录和立项表生成
        proj_doc = project_dir / "01_启动" / "DJ-2026-000_PROJ.md"
        assert proj_doc.exists()
        content = proj_doc.read_text(encoding="utf-8")
        assert "Westwell PLC 项目立项需求说明书" in content

        # 3. 验证 PM_SESSION 生成
        session_file = project_dir / "PM_SESSION_DJ-2026-000.md"
        assert session_file.exists()
        session_content = session_file.read_text(encoding="utf-8")
        assert "## 0. Meta" in session_content
        assert "技术栈 | plc" in session_content
        assert "## 7. Risk & Decision Log" in session_content

        # 4. 测试显式控制主设计人，避免依赖执行环境身份
        assert "**主设计人**：plc_test_author" in content

    def test_init_pm_python(self, tmp_path: Path) -> None:
        """初始化 Python 项目的 PM 框架"""
        project_dir = tmp_path / "SW-2026-001_测试项目"
        project_dir.mkdir()

        svc = ProjectService(str(tmp_path))
        svc.init_project_pm_framework(
            project_path=str(project_dir),
            project_id="SW-2026-001",
            project_name="测试项目",
            stack_type="python",
            author="python_test_author",
        )

        # 1. 验证 .copier-answers.yml 补齐
        assert (project_dir / ".copier-answers.yml").exists()

        # 2. 验证 Python 专属目录和立项表生成
        proj_doc = project_dir / "01_启动" / "SW-2026-001_PM.md"
        assert proj_doc.exists()
        content = proj_doc.read_text(encoding="utf-8")
        assert "Westwell Python 项目立项表" in content
        assert "**主设计人**：python_test_author" in content

        # 3. 验证 PM_SESSION 生成
        session_file = project_dir / "PM_SESSION_SW-2026-001.md"
        assert session_file.exists()
        session_content = session_file.read_text(encoding="utf-8")
        assert "## 7. Risk & Decision Log" in session_content

    def test_init_pm_custom_author(self, tmp_path: Path) -> None:
        """自定义 author 参数"""
        project_dir = tmp_path / "SW-2026-002_作者测试"
        project_dir.mkdir()

        svc = ProjectService(str(tmp_path))
        svc.init_project_pm_framework(
            project_path=str(project_dir),
            project_id="SW-2026-002",
            project_name="作者测试",
            stack_type="python",
            author="test_user",
        )

        proj_doc = project_dir / "01_启动" / "SW-2026-002_PM.md"
        content = proj_doc.read_text(encoding="utf-8")
        assert "**主设计人**：test_user" in content
        assert "fubai" not in content


# ── CLI project import 测试 ──────────────────────────────


class TestCliProjectImport:
    """CLI project import 命令测试"""

    def test_import_copy(self, tmp_path: Path) -> None:
        """导入外部目录（复制模式）"""
        workspace = tmp_path
        # 创建外部源目录
        source = tmp_path / "external" / "DJ-2026-IMP_导入项目"
        source.mkdir(parents=True)
        (source / ".plc.json").write_text(
            json.dumps(
                {"name": "DJ-2026-IMP", "version": "V1.0.0", "description": "导入测试"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (source / "README.md").write_text("# 导入项目\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "import", str(source)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "项目已复制" in result.output

        # 目标路径应存在
        dest = workspace / "02_在研项目" / "DJ-2026-IMP_导入项目"
        assert dest.is_dir()
        assert (dest / "README.md").exists()

        # 源目录应仍存在（复制模式）
        assert source.is_dir()

        # 应自动补全 .copier-answers.yml
        assert (dest / ".copier-answers.yml").exists()

    def test_import_move(self, tmp_path: Path) -> None:
        """导入外部目录（移动模式 --move）"""
        workspace = tmp_path
        source = tmp_path / "external" / "SW-2026-MV_移动项目"
        source.mkdir(parents=True)
        (source / ".plc.json").write_text(
            json.dumps({"name": "SW-2026-MV"}, ensure_ascii=False),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "import", str(source), "--move"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "项目已移动" in result.output

        # 目标路径应存在
        dest = workspace / "02_在研项目" / "SW-2026-MV_移动项目"
        assert dest.is_dir()

        # 源目录应已不存在（移动模式）
        assert not source.exists()

    def test_import_business_line_option(self, tmp_path: Path) -> None:
        """--business-line 选项应正常执行"""
        workspace = tmp_path
        source = tmp_path / "external" / "DJ-2026-BL_业务线项目"
        source.mkdir(parents=True)
        (source / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-BL"}, ensure_ascii=False),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "-w",
                str(workspace),
                "project",
                "import",
                str(source),
                "--business-line",
                "DJ",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # 业务线与编号前缀一致时无警告
        assert "不一致" not in result.output

    def test_import_business_line_mismatch_warning(self, tmp_path: Path) -> None:
        """--business-line 与编号前缀不一致时应输出警告"""
        workspace = tmp_path
        source = tmp_path / "external" / "DJ-2026-MM_业务线不匹配"
        source.mkdir(parents=True)
        (source / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-MM"}, ensure_ascii=False),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "-w",
                str(workspace),
                "project",
                "import",
                str(source),
                "-bl",
                "SW",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "不一致" in result.output

    def test_import_auto_retrofit_copier_answers(self, tmp_path: Path) -> None:
        """导入后应自动补全 .copier-answers.yml"""
        workspace = tmp_path
        source = tmp_path / "external" / "XT-2026-RT_自动补全"
        source.mkdir(parents=True)
        # 无 .copier-answers.yml，有 .plc.json
        (source / ".plc.json").write_text(
            json.dumps(
                {"name": "XT-2026-RT", "version": "V2.0.0", "description": "自动补全测试"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(workspace), "project", "import", str(source)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        dest = workspace / "02_在研项目" / "XT-2026-RT_自动补全"
        answers_path = dest / ".copier-answers.yml"
        assert answers_path.exists()
        answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
        assert answers["project_id"] == "XT-2026-RT"
        assert answers["version"] == "V2.0.0"


# ── CLI project list 增强测试 ────────────────────────────


class TestCliProjectListFilter:
    """CLI project list --business-line / --stack 筛选测试"""

    def test_list_with_business_line_filter(self, tmp_workspace: Path) -> None:
        """--business-line DJ 应显示 DJ 项目"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(tmp_workspace), "project", "list", "--business-line", "DJ"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "DJ-2026-TEST" in result.output or "DJ-2026" in result.output

    def test_list_with_business_line_no_match(self, tmp_workspace: Path) -> None:
        """--business-line SW 无匹配时应提示未发现"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(tmp_workspace), "project", "list", "--business-line", "SW"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "未发现项目" in result.output

    def test_list_with_stack_filter(self, tmp_workspace: Path) -> None:
        """--stack plc 应显示 PLC 项目"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(tmp_workspace), "project", "list", "--stack", "plc"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "DJ-2026-TEST" in result.output or "DJ-2026" in result.output

    def test_list_with_stack_no_match(self, tmp_workspace: Path) -> None:
        """--stack python 无匹配时应提示未发现"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(tmp_workspace), "project", "list", "--stack", "python"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "未发现项目" in result.output

    def test_list_with_business_line_short_option(self, tmp_workspace: Path) -> None:
        """-bl 短选项应与 --business-line 等效"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["-w", str(tmp_workspace), "project", "list", "-bl", "DJ"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "DJ-2026-TEST" in result.output or "DJ-2026" in result.output
