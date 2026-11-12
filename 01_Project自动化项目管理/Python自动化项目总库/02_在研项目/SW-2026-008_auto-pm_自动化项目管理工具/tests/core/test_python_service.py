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


# ── TD-SW008-566（D-301）：repair 不留占位符，check 查内容 ─────────────

import re  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_JINJA = re.compile(r"\{\{-?\s*(?!\.)[^{}\n]*\}\}|\{%.*?%\}")


def _imported_repo(tmp_path: Path, *, with_package: str = "") -> Path:
    """像 Gemini-test 那样导进来的 Python 仓库：有代码和 tests/，没有 pyproject 等规范文件"""
    proj = tmp_path / "SW-2026-952_Gemini-test"
    (proj / "core").mkdir(parents=True)
    (proj / "core" / "engine.py").write_text("X = 1\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "test_engine.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    if with_package:
        (proj / with_package).mkdir()
        (proj / with_package / "__init__.py").write_text("", encoding="utf-8")
    (proj / ".copier-answers.yml").write_text(
        "project_id: SW-2026-952\nproject_name: Gemini-test\nstack: python\n_src_path: templates/python-tool\n", encoding="utf-8"
    )
    return proj


def test_repair_renders_every_file_without_leftover_placeholders(tmp_path: Path) -> None:
    proj = _imported_repo(tmp_path)
    svc = PythonProjectService(str(tmp_path), templates_dir=str(TEMPLATES))
    repaired = svc.repair_project_spec(str(proj), "SW-2026-952")
    assert not [i for i in repaired if i.startswith("Not repaired")], repaired
    written = [p for p in proj.rglob("*") if p.is_file() and p.suffix in (".toml", ".yml", ".yaml", ".md", ".py")]
    assert [p.name for p in written if p.name.startswith("PM_SESSION_")] == ["PM_SESSION_SW-2026-952.md"]
    left = {str(p.relative_to(proj)): _JINJA.findall(p.read_text(encoding="utf-8")) for p in written}
    assert {k: v for k, v in left.items() if v} == {}
    pyproject = (proj / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.1.0"' in pyproject and 'name = "gemini_test"' in pyproject
    assert (proj / "gemini_test" / "__init__.py").is_file()  # 声明的包真的存在
    result = svc.check_project_spec(str(proj), "SW-2026-952")
    assert [c["name"] for c in result["checks"] if not c["ok"]] == []


def test_repair_uses_the_only_existing_package_instead_of_inventing_one(tmp_path: Path) -> None:
    proj = _imported_repo(tmp_path, with_package="gemini")
    PythonProjectService(str(tmp_path), templates_dir=str(TEMPLATES)).repair_project_spec(str(proj), "SW-2026-952")
    assert 'packages = ["gemini"]' in (proj / "pyproject.toml").read_text(encoding="utf-8")
    assert not (proj / "gemini_test").exists()


def test_check_reports_leftover_placeholders_and_missing_packages(tmp_path: Path) -> None:
    proj = _imported_repo(tmp_path)
    svc = PythonProjectService(str(tmp_path), templates_dir=str(TEMPLATES))
    svc.repair_project_spec(str(proj), "SW-2026-952")
    pyproject = proj / "pyproject.toml"
    pyproject.write_text(pyproject.read_text(encoding="utf-8").replace('"0.1.0"', '"{{ version }}"'), encoding="utf-8")
    (proj / "gemini_test" / "__init__.py").unlink()
    (proj / "gemini_test").rmdir()
    failed = {c["name"]: c["detail"] for c in svc.check_project_spec(str(proj), "SW-2026-952")["checks"] if not c["ok"]}
    assert failed == {
        "没渲染的模板占位符": "pyproject.toml 1 处（如 {{ version }}）",
        "pyproject.toml: 声明的包目录存在": "声明了不存在的包目录: gemini_test",
    }


def test_go_task_variables_are_not_placeholders(tmp_path: Path) -> None:
    proj = _imported_repo(tmp_path)
    svc = PythonProjectService(str(tmp_path), templates_dir=str(TEMPLATES))
    svc.repair_project_spec(str(proj), "SW-2026-952")
    taskfile = proj / "Taskfile.yml"
    taskfile.write_text(taskfile.read_text(encoding="utf-8") + "  run:\n    cmds:\n      - echo {{.CLI_ARGS}}\n", encoding="utf-8")
    checks = {c["name"]: c["ok"] for c in svc.check_project_spec(str(proj), "SW-2026-952")["checks"]}
    assert checks["没渲染的模板占位符"] is True
