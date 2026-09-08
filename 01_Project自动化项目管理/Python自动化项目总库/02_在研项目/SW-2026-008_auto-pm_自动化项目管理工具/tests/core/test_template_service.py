"""TemplateService 单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.core.template_service import TemplateService


class TestListTemplates:
    """模板列表测试"""

    def test_list_templates_empty_dir(self, tmp_path: Path) -> None:
        """空目录返回空列表"""
        svc = TemplateService(str(tmp_path))
        assert svc.list_templates() == []

    def test_list_templates_nonexistent_dir(self, tmp_path: Path) -> None:
        """不存在的目录返回空列表"""
        svc = TemplateService(str(tmp_path / "nonexistent"))
        assert svc.list_templates() == []

    def test_list_templates_with_valid_template(self, tmp_path: Path) -> None:
        """有 copier.yml 的子目录被识别为模板"""
        tpl_dir = tmp_path / "plc-standard"
        tpl_dir.mkdir()
        (tpl_dir / "copier.yml").write_text("project_id: test\n", encoding="utf-8")

        svc = TemplateService(str(tmp_path))
        templates = svc.list_templates()

        assert "plc-standard" in templates

    def test_list_templates_ignores_files(self, tmp_path: Path) -> None:
        """非目录文件被忽略"""
        (tmp_path / "readme.txt").write_text("not a template\n", encoding="utf-8")

        svc = TemplateService(str(tmp_path))
        templates = svc.list_templates()

        assert "readme.txt" not in templates

    def test_list_templates_ignores_no_copier_yml(self, tmp_path: Path) -> None:
        """无 copier.yml 的子目录被忽略"""
        no_yml_dir = tmp_path / "no-copier"
        no_yml_dir.mkdir()

        svc = TemplateService(str(tmp_path))
        templates = svc.list_templates()

        assert "no-copier" not in templates


class TestGetTemplatePath:
    """模板路径查询测试"""

    def test_get_template_path_exists(self, tmp_path: Path) -> None:
        """存在的模板返回路径"""
        tpl_dir = tmp_path / "plc-standard"
        tpl_dir.mkdir()
        (tpl_dir / "copier.yml").write_text("project_id: test\n", encoding="utf-8")

        svc = TemplateService(str(tmp_path))
        path = svc.get_template_path("plc-standard")

        assert path == str(tpl_dir)

    def test_get_template_path_not_found(self, tmp_path: Path) -> None:
        """不存在的模板抛出 FileNotFoundError"""
        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="模板不存在"):
            svc.get_template_path("nonexistent")

    def test_get_template_path_no_copier_yml(self, tmp_path: Path) -> None:
        """目录存在但无 copier.yml 抛出 FileNotFoundError"""
        tpl_dir = tmp_path / "no-copier"
        tpl_dir.mkdir()

        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="模板不存在"):
            svc.get_template_path("no-copier")


class TestCopyTemplate:
    """模板复制测试"""

    def test_copy_template_not_found(self, tmp_path: Path) -> None:
        """模板不存在时抛出 FileNotFoundError"""
        svc = TemplateService(str(tmp_path))
        dest = str(tmp_path / "dest")

        with pytest.raises(FileNotFoundError, match="模板不存在"):
            svc.copy_template("nonexistent", dest, {"project_id": "TEST"})

    def test_copy_template_dest_exists(self, tmp_path: Path) -> None:
        """目标路径已存在时抛出 FileExistsError"""
        tpl_dir = tmp_path / "plc-standard"
        tpl_dir.mkdir()
        (tpl_dir / "copier.yml").write_text("project_id: test\n", encoding="utf-8")

        dest = tmp_path / "dest"
        dest.mkdir()

        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileExistsError, match="目标路径已存在"):
            svc.copy_template("plc-standard", str(dest), {"project_id": "TEST"})


class TestUpdateTemplate:
    """模板更新测试"""

    def test_update_template_no_answers(self, tmp_path: Path) -> None:
        """缺少 .copier-answers.yml 时抛出 FileNotFoundError"""
        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="缺少 .copier-answers.yml"):
            svc.update_template(str(tmp_path))
