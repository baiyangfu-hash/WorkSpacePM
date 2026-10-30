"""PythonProjectService 单元测试"""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.python_service import PythonProjectService


def test_python_project_check_not_ok(tmp_path: Path) -> None:
    """测试空文件夹下检查规范返回 False"""
    svc = PythonProjectService(str(tmp_path))
    proj_dir = tmp_path / "SW-2026-PYT_Python项目"
    proj_dir.mkdir()

    result = svc.check_project_spec(str(proj_dir), "SW-2026-PYT")
    assert result["all_ok"] is False
    assert result["passed"] < result["total"]


def test_python_project_check_and_repair(tmp_path: Path) -> None:
    """测试 Python 规范检查和物理修复流程"""
    # 模拟 templates/python-tool/template 目录结构，用于测试 repair
    templates_dir = tmp_path / "templates"
    tpl_path = templates_dir / "python-tool" / "template"
    tpl_path.mkdir(parents=True)

    # 写入一些模拟模板文件
    (tpl_path / ".pre-commit-config.yaml").write_text("pre-commit content\n", encoding="utf-8")
    (tpl_path / ".ruff.toml").write_text("ruff content\n", encoding="utf-8")
    (tpl_path / ".copier-answers.yml.jinja").write_text("project_id: {{ project_id }}\n", encoding="utf-8")
    (tpl_path / "Taskfile.yml.jinja").write_text("taskfile for {{ project_name }}\n", encoding="utf-8")
    (tpl_path / "README.md.jinja").write_text("# {{ project_name }}\n", encoding="utf-8")
    (tpl_path / "pyproject.toml.jinja").write_text("[project]\nname = \"{{ package_name }}\"\nversion = \"0.1.0\"\nrequires-python = \">=3.11\"\n", encoding="utf-8")
    (tpl_path / "PM_SESSION_{{ project_id }}.md.jinja").write_text("# PM SESSION {{ project_id }}\n", encoding="utf-8")

    # 创建要修复的项目
    svc = PythonProjectService(str(tmp_path), templates_dir=str(templates_dir))
    proj_dir = tmp_path / "SW-2026-PYT_Python项目"
    proj_dir.mkdir()

    # 1. 检查应该是不通过的
    res = svc.check_project_spec(str(proj_dir), "SW-2026-PYT")
    assert res["all_ok"] is False

    # 2. 运行 repair (dry_run=True) 不改变实际文件，但返回修复列表
    repaired_preview = svc.repair_project_spec(str(proj_dir), "SW-2026-PYT", dry_run=True)
    assert len(repaired_preview) > 0
    assert not (proj_dir / ".ruff.toml").exists()

    # 3. 运行 repair (dry_run=False) 实际写入文件
    repaired_actual = svc.repair_project_spec(str(proj_dir), "SW-2026-PYT", dry_run=False)
    assert len(repaired_actual) > 0
    assert (proj_dir / ".ruff.toml").exists()
    assert (proj_dir / "pyproject.toml").exists()
    assert (proj_dir / "tests" / "conftest.py").exists()
    assert (proj_dir / "01_启动").exists()
    assert (proj_dir / "PM_SESSION_SW-2026-PYT.md").exists()

    # 4. 再次运行 check，应该完全通过
    res2 = svc.check_project_spec(str(proj_dir), "SW-2026-PYT")
    assert res2["all_ok"] is True
    assert res2["passed"] == res2["total"]
