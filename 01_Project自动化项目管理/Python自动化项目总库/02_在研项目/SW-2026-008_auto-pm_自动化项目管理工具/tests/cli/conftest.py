from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing a Click CLI test runner"""
    return CliRunner(env={})


@pytest.fixture
def mock_logger() -> logging.Logger:
    """Fixture providing a test logger"""
    return Mock(spec=logging.Logger)


@pytest.fixture
def cli_env(mock_logger: logging.Logger) -> Generator[None, None, None]:
    """Fixture that patches client creation and logger setup"""
    with patch("auto_pm.app_context.setup_logger", return_value=mock_logger):
        yield


# ── V0.5.2 步骤3：公共辅助 fixture ──────────────────────────────


@pytest.fixture
def plc_project_factory(tmp_path: Path) -> Callable[..., Path]:
    """创建轻量 PLC 项目的工厂函数（绕过 Copier，快）

    返回 factory 函数，调用方式：
        project_dir = plc_project_factory(project_id="DJ-2026-TEST", name="测试")

    识别方式：.plc.json 标志文件（与 tests/cli/test_plc.py _make_plc_project 一致）
    """
    import json

    def _create(
        project_id: str = "DJ-2026-TEST",
        name: str = "测试项目",
        with_pm_session: bool = False,
        with_std_dirs: bool = False,
    ) -> Path:
        project_dir = tmp_path / f"{project_id}_{name}"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {"name": project_id, "version": "V1.0.0", "description": name},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if with_pm_session:
            (project_dir / f"PM_SESSION_{project_id}.md").write_text(
                "# PM_SESSION\n", encoding="utf-8"
            )
        if with_std_dirs:
            for d in [
                "01_启动", "02_PLC程序", "03_HMI设计",
                "04_现场调试", "05_测试与验证", "06_文档与交付",
                "07_技术支持", "08_备件管理", "09_项目总结", "10_知识库",
                "11_监控", "12_驱动器与设备",
            ]:
                (project_dir / d).mkdir(exist_ok=True)
            chg_dir = project_dir / "11_监控" / "01_变更管理"
            (chg_dir / "01_变更单").mkdir(parents=True, exist_ok=True)
            (chg_dir / "02_变更记录").mkdir(parents=True, exist_ok=True)
            (chg_dir / "02_变更记录" / "01_版本变更台帐.md").write_text("# 台账\n", encoding="utf-8")
            (project_dir / "04_现场调试" / "现场调试计划.md").write_text("# 调试计划\n", encoding="utf-8")
            (project_dir / "06_文档与交付" / "验收交付清单.md").write_text("# 验收\n", encoding="utf-8")
        return project_dir

    return _create


@pytest.fixture
def python_project_factory(tmp_path: Path) -> Callable[..., Path]:
    """创建轻量 Python 项目的工厂函数

    返回 factory 函数，调用方式：
        project_dir = python_project_factory(project_id="SW-2026-PYT", name="工具")

    识别方式：.copier-answers.yml 含 stack=python（与 tests/cli/test_python.py _make_python_project 一致）
    """

    def _create(
        project_id: str = "SW-2026-PYT",
        name: str = "Python工具",
        complete: bool = True,
    ) -> Path:
        project_dir = tmp_path / f"{project_id}_{name}"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / ".copier-answers.yml").write_text(
            f"project_id: {project_id}\n"
            f"project_name: {name}\n"
            "stack: python\n"
            "_src_path: templates/python-tool\n",
            encoding="utf-8",
        )
        (project_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{project_id.lower()}"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11"\n',
            encoding="utf-8",
        )
        if complete:
            for f in ["README.md", ".ruff.toml", ".pre-commit-config.yaml", "Taskfile.yml"]:
                (project_dir / f).write_text(f"# {f}\n", encoding="utf-8")
            (project_dir / "tests").mkdir(exist_ok=True)
            (project_dir / "tests" / "conftest.py").write_text("# conftest\n", encoding="utf-8")
            (project_dir / "01_启动").mkdir(exist_ok=True)
            (project_dir / f"PM_SESSION_{project_id}.md").write_text(
                "# PM_SESSION\n", encoding="utf-8"
            )
        return project_dir

    return _create
