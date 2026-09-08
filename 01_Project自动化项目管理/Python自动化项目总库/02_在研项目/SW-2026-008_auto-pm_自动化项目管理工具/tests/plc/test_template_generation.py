"""模板生成正确性测试

验证 3 套 PLC 模板生成的项目结构正确性:
- .plc.json 位置正确
- libraries 路径有效
- 目录结构完整

不依赖 copier 实际渲染，仅验证模板文件结构。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from auto_pm.core.template_service import TemplateService


class TestTemplateGeneration:
    """模板生成正确性测试"""

    @pytest.fixture
    def template_service(self) -> TemplateService:
        """获取项目的 TemplateService（模板在项目根的 templates/ 下）"""
        project_root = Path(__file__).parent.parent.parent
        templates_dir = project_root / "templates"
        return TemplateService(str(templates_dir))

    def test_list_templates_includes_3_plc_templates(
        self, template_service: TemplateService
    ) -> None:
        """list_templates 应包含 3 套 PLC 模板"""
        templates = template_service.list_templates()
        assert "plc-shared-library" in templates
        assert "plc-test-suite" in templates
        assert "plc-standard-project" in templates

    def test_plc_shared_library_template_structure(
        self, template_service: TemplateService
    ) -> None:
        """plc-shared-library 模板结构正确"""
        path = template_service.get_template_path("plc-shared-library")
        # 验证 copier.yml 存在
        assert os.path.isfile(os.path.join(path, "copier.yml"))
        # 验证 template/ 目录存在
        assert os.path.isdir(os.path.join(path, "template"))
        # 验证 .plc.json.jinja 存在（根级）
        assert os.path.isfile(os.path.join(path, "template", ".plc.json.jinja"))

    def test_plc_test_suite_template_structure(
        self, template_service: TemplateService
    ) -> None:
        """plc-test-suite 模板结构正确"""
        path = template_service.get_template_path("plc-test-suite")
        assert os.path.isfile(os.path.join(path, "copier.yml"))
        assert os.path.isdir(os.path.join(path, "template"))
        assert os.path.isfile(os.path.join(path, "template", ".plc.json.jinja"))
        # 验证扁平结构（DB1/OB1 在根级）
        assert os.path.isdir(os.path.join(path, "template", "DB1"))
        assert os.path.isdir(os.path.join(path, "template", "OB1"))

    def test_plc_standard_project_template_structure(
        self, template_service: TemplateService
    ) -> None:
        """plc-standard-project 模板结构正确（含根级 .plc.json 与 02_PLC程序 资产）"""
        path = template_service.get_template_path("plc-standard-project")
        assert os.path.isfile(os.path.join(path, "copier.yml"))
        # 验证根级 .plc.json.jinja
        assert os.path.isfile(os.path.join(path, "template", ".plc.json.jinja"))
        # 验证 .plc.json.jinja 在 02_PLC程序/PLC_ST/ 下
        plc_json_jinja = os.path.join(
            path, "template", "02_PLC程序", "PLC_ST", ".plc.json.jinja"
        )
        assert os.path.isfile(plc_json_jinja)

    def test_plc_standard_project_has_12_std_dirs(
        self, template_service: TemplateService
    ) -> None:
        """plc-standard-project 模板含 12 个标准目录（CHG-SCPT-2026-146: 01_启动 替代 00_项目管理）"""
        from auto_pm.plc.models import PM_DIR_CANDIDATES, STD_DIRS

        path = template_service.get_template_path("plc-standard-project")
        template_dir = os.path.join(path, "template")
        for d in STD_DIRS:
            # 项目管理目录：接受任一候选（01_启动 或 00_项目管理）
            if d in PM_DIR_CANDIDATES or d in ("00_项目管理", "01_启动"):
                assert any(
                    os.path.isdir(os.path.join(template_dir, c))
                    for c in PM_DIR_CANDIDATES
                ), f"缺少项目管理目录（候选: {PM_DIR_CANDIDATES}）"
            else:
                assert os.path.isdir(os.path.join(template_dir, d)), f"缺少标准目录: {d}"

    def test_plc_standard_project_includes_week2_assets_and_overview(
        self, template_service: TemplateService
    ) -> None:
        """plc-standard-project 模板包含工程资产样例与立项表"""
        path = template_service.get_template_path("plc-standard-project")
        template_dir = os.path.join(path, "template")

        has_proj_file = os.path.isfile(
            os.path.join(
                template_dir, "01_启动", "003_{{ project_id }}_项目立项表_PROJ.md.jinja"
            )
        ) or os.path.isfile(
            os.path.join(
                template_dir, "00_项目管理", "01_立项与需求", "003_{{ project_id }}_项目立项表_PROJ.md.jinja"
            )
        )
        assert has_proj_file, "缺少项目立项表模板文件"
        for asset_name in (
            "README.md.jinja",
            "io_points.csv.jinja",
            "program_blocks.yml.jinja",
            "communications.yml.jinja",
        ):
            assert os.path.isfile(
                os.path.join(template_dir, "02_PLC程序", "工程资产", asset_name)
            ), f"缺少工程资产样例: {asset_name}"
