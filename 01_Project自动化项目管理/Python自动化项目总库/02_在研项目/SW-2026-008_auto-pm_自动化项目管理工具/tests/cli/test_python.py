"""python CLI 命令测试 - V0.5.2 步骤2

覆盖 python_group 2 个子命令：
- init <ID> --name <NAME> [--desc] [--package] [--author] [--dry-run]
- check <ID> | --all [--json]

测试策略：
- init dry-run 不需要真实 Copier 模板，验证预览输出
- init 实际创建需要真实 Copier python-tool 模板，验证项目结构生成
- check 验证必需文件/目录检查逻辑

10 个用例分布：
- init: 4（dry-run 预览/实际创建/中文名默认包名/已存在路径），另有默认包名推导参数化用例
- check: 7（正常/--json/不存在/非 Python/--all/无 Python 项目/缺参）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from auto_pm.application.core.python_service import derive_package_name
from auto_pm.ui.cli.__main__ import cli


def _make_python_project(
    workspace: Path,
    project_id: str = "SW-2026-PYT",
    name: str = "Python工具",
    complete: bool = True,
) -> Path:
    """创建一个 Python 项目（有 pyproject.toml 无 .plc.json）

    Args:
        workspace: 工作空间根目录
        project_id: 项目编号
        name: 项目名称（目录后缀）
        complete: 是否创建完整的 Python 项目结构（含必需文件/目录）
    """
    project_dir = workspace / f"{project_id}_{name}"
    project_dir.mkdir(parents=True, exist_ok=True)
    # .copier-answers.yml（stack='python'，让 ProjectScanner 识别为 Python 项目）
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
        # 创建必需文件
        for f in ["README.md", ".ruff.toml", ".pre-commit-config.yaml", "Taskfile.yml"]:
            (project_dir / f).write_text(f"# {f}\n", encoding="utf-8")
        # 创建必需目录
        (project_dir / "tests").mkdir(exist_ok=True)
        (project_dir / "tests" / "conftest.py").write_text("# conftest\n", encoding="utf-8")
        (project_dir / "01_启动").mkdir(exist_ok=True)
        # PM_SESSION 文件
        (project_dir / f"PM_SESSION_{project_id}.md").write_text(
            "# PM_SESSION\n", encoding="utf-8"
        )
    return project_dir


# ── init 命令测试（3 用例）──────────────────────────────


@pytest.mark.cli
def test_python_init_dry_run(cli_runner: CliRunner, tmp_path: Path) -> None:
    """init --dry-run 预览模式不实际创建项目"""
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "python", "init", "SW-2026-INIT",
            "--name", "初始化测试",
            "--dry-run",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "[DRY-RUN]" in result.output
    assert "SW-2026-INIT" in result.output
    assert "初始化测试" in result.output
    # 预览模式不应创建目录
    assert not (tmp_path / "SW-2026-INIT_初始化测试").exists()


@pytest.mark.cli
def test_python_init_actual_create(cli_runner: CliRunner, tmp_path: Path) -> None:
    """init 实际创建 Python 项目骨架

    依赖项目根的 Copier python-tool 模板；模板随仓库提交，缺失即失败（路径写旧曾让本测试静默跳过）。
    输入须过模板校验：项目号“字母-年份-三位序号”，包名“小写字母开头、仅含小写字母/数字/下划线”
    （这里显式给 --package，测“给定包名能生成骨架”；不给包名的情形见下面的中文名用例）。
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    template_dir = project_root / "templates" / "python-tool"
    assert template_dir.is_dir(), f"python-tool 模板缺失: {template_dir}"

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "python", "init", "SW-2026-901",
            "--name", "初始化测试",
            "--package", "init_test",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    project_dir = tmp_path / "SW-2026-901_初始化测试"
    assert project_dir.is_dir()
    # 应生成 .copier-answers.yml
    assert (project_dir / ".copier-answers.yml").is_file()


@pytest.mark.cli
def test_python_init_chinese_name_default_package(cli_runner: CliRunner, tmp_path: Path) -> None:
    """中文项目名、不给 --package 也能创建：默认包名取项目号（与 project create 一致）"""
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "python", "init", "SW-2026-902",
            "--name", "中文测试",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    project_dir = tmp_path / "SW-2026-902_中文测试"
    answers = yaml.safe_load((project_dir / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert answers["package_name"] == "sw_2026_902"
    assert answers["cli_command"] == "sw-2026-902"
    assert (project_dir / "sw_2026_902").is_dir()


@pytest.mark.parametrize(
    ("project_name", "expected"),
    [
        ("Data Tool", "data_tool"),
        ("data-tool", "data_tool"),
        ("初始化测试", "sw_2026_901"),
        ("Data 工具", "sw_2026_901"),
        ("2026tool", "sw_2026_901"),
    ],
)
def test_derive_package_name(project_name: str, expected: str) -> None:
    """项目名能当包名就沿用，否则退回项目号"""
    assert derive_package_name(project_name, "SW-2026-901") == expected


@pytest.mark.cli
def test_python_init_existing_path(cli_runner: CliRunner, tmp_path: Path) -> None:
    """init 目标路径已存在时 exit_code=1"""
    # 预先创建同名目录
    (tmp_path / "SW-2026-EXISTS_已存在").mkdir()
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "python", "init", "SW-2026-EXISTS",
            "--name", "已存在",
        ],
    )
    assert result.exit_code == 1
    assert "已存在" in result.output


# ── check 命令测试（7 用例）──────────────────────────────


@pytest.mark.cli
def test_python_check_normal(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check 正常检查完整的 Python 项目"""
    _make_python_project(tmp_path, "SW-2026-PYT", complete=True)
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check", "SW-2026-PYT"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "Python 项目检查" in result.output
    assert "SW-2026-PYT" in result.output


@pytest.mark.cli
def test_python_check_json(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check --json 输出 JSON 格式结果"""
    _make_python_project(tmp_path, "SW-2026-PYT", complete=True)
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check", "SW-2026-PYT", "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["project_id"] == "SW-2026-PYT"
    assert "checks" in data[0]
    assert "passed" in data[0]
    assert "total" in data[0]


@pytest.mark.cli
def test_python_check_nonexistent_project(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check 不存在的项目 exit_code=1"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check", "SW-2026-NOTEXIST"],
    )
    assert result.exit_code == 1
    assert "项目不存在" in result.output


@pytest.mark.cli
def test_python_check_non_python_project(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check 非 Python 项目（PLC 项目）exit_code=1"""
    # 创建一个 PLC 项目（有 .plc.json 无 .copier-answers.yml stack=python）
    project_dir = tmp_path / "DJ-2026-PLC_PLC项目"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps({"name": "DJ-2026-PLC", "version": "V1.0.0"}),
        encoding="utf-8",
    )
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check", "DJ-2026-PLC"],
    )
    assert result.exit_code == 1
    assert "不是 Python 项目" in result.output


@pytest.mark.cli
def test_python_check_all(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check --all 检查工作空间所有 Python 项目"""
    _make_python_project(tmp_path, "SW-2026-001", "项目1", complete=True)
    _make_python_project(tmp_path, "SW-2026-002", "项目2", complete=True)
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check", "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 应检查 2 个项目
    assert "SW-2026-001" in result.output
    assert "SW-2026-002" in result.output


@pytest.mark.cli
def test_python_check_all_no_python_projects(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check --all 无 Python 项目时输出提示"""
    # 仅创建 PLC 项目
    project_dir = tmp_path / "DJ-2026-PLC_PLC项目"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps({"name": "DJ-2026-PLC", "version": "V1.0.0"}),
        encoding="utf-8",
    )
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check", "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "未发现 Python 项目" in result.output


@pytest.mark.cli
def test_python_check_missing_argument(cli_runner: CliRunner, tmp_path: Path) -> None:
    """check 未指定项目编号且未用 --all 时 exit_code=1"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "python", "check"],
    )
    assert result.exit_code == 1
    assert "请指定项目编号" in result.output or "--all" in result.output


@pytest.mark.cli
def test_python_repair_dry_run(cli_runner: CliRunner, tmp_path: Path) -> None:
    """repair --dry-run 预览模式不实际执行修复"""
    _make_python_project(tmp_path, "SW-2026-PYT", complete=False)
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "python", "repair", "SW-2026-PYT",
            "--dry-run",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "[DRY-RUN]" in result.output
    assert not (tmp_path / "SW-2026-PYT_Python工具" / ".pre-commit-config.yaml").exists()


@pytest.mark.cli
def test_python_repair_actual(cli_runner: CliRunner, tmp_path: Path) -> None:
    """repair 实际修复缺少的规范文件"""
    _make_python_project(tmp_path, "SW-2026-PYT", complete=False)

    # 模拟 templates 目录
    project_root = Path(__file__).resolve().parent.parent.parent
    template_dir = project_root / "templates" / "python-tool"
    if not template_dir.exists():
        # 如果不是标准开发目录，我们可以 mock 或者跳过物理修复测试
        pytest.skip("python-tool 模板不存在，跳过物理修复测试")

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "python", "repair", "SW-2026-PYT",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    proj_dir = tmp_path / "SW-2026-PYT_Python工具"
    assert (proj_dir / ".pre-commit-config.yaml").is_file()

