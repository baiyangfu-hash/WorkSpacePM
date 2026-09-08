"""plc CLI 命令测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def _make_plc_project(
    workspace: Path,
    project_id: str,
    name: str = "测试项目",
    with_std_dirs: bool = False,
    with_pm_session: bool = False,
    with_prd: bool = False,
) -> Path:
    """创建一个由 .plc.json 识别的 PLC 项目（供 CLI 测试使用）

    Args:
        workspace: 工作空间根目录
        project_id: 项目编号（如 DJ-2026-REPAIR）
        name: 项目名称（目录后缀）
        with_std_dirs: 是否创建 12 个标准目录
        with_pm_session: 是否创建 PM_SESSION 文件
        with_prd: 是否创建 PRD 目录
    """
    project_dir = workspace / f"{project_id}_{name}"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": project_id,
                "version": "V1.0.0",
                "description": name,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if with_pm_session:
        (project_dir / f"PM_SESSION_{project_id}.md").write_text(
            "# PM_SESSION\n", encoding="utf-8"
        )
    if with_prd:
        (project_dir / "PRD").mkdir()
    if with_std_dirs:
        for d in [
            "00_项目管理", "01_需求与设计", "02_PLC程序", "03_HMI设计",
            "04_现场调试", "12_驱动器与设备", "05_测试与验证", "06_文档与交付",
            "07_技术支持", "08_备件管理", "09_项目总结", "10_知识库",
        ]:
            (project_dir / d).mkdir()
    return project_dir


# ── check 命令测试 ──────────────────────────────────────


def test_plc_check_all(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 plc check --all"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "plc", "check", "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "DJ-2026-TEST" in result.output


def test_plc_check_project(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 plc check <ID>"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "plc", "check", "DJ-2026-TEST"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "检查结果" in result.output


def test_plc_check_not_found(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 check 不存在的项目"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "plc", "check", "NOT-EXIST"],
    )
    assert result.exit_code == 1


def test_plc_check_substance(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc check <ID> --substance（文档实质化检查）"""
    project_id = "DJ-2026-SUB"
    project_dir = _make_plc_project(
        tmp_path,
        project_id,
        with_pm_session=True,
        with_std_dirs=True,
    )
    # 创建 PRD 目录 + 空壳文档（含占位符）
    prd_dir = project_dir / "PRD"
    prd_dir.mkdir()
    (prd_dir / "需求分析文档_REQ.md").write_text(
        "# 需求分析\n\n待补充", encoding="utf-8"
    )

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "check", project_id, "--substance"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "检查结果" in result.output


def test_plc_check_fix(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc check <ID> --fix（检查后自动修复）"""
    project_id = "DJ-2026-FIX"
    # 创建缺少标准目录的项目（仅有 .plc.json）
    project_dir = _make_plc_project(tmp_path, project_id)

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "check", project_id, "--fix"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 修复后应创建标准目录（检查其中一个，CHG-SCPT-2026-146: 01_启动）
    assert (project_dir / "01_启动").is_dir()


# ── V0.4.1 Step 3: Python 项目不适用口径 CLI 集成测试 ──────


def _make_python_project(
    workspace: Path,
    project_id: str,
    name: str = "Python工具",
) -> Path:
    """创建一个 Python 项目（有 pyproject.toml 无 .plc.json）

    V0.4.1 Step 3: 供 plc check Python 项目 CLI 集成测试使用。
    项目通过 .copier-answers.yml 识别为 stack='python'，无 .plc.json，
    PlcChecker.check_project 应返回 not_applicable=True。
    """
    project_dir = workspace / f"{project_id}_{name}"
    project_dir.mkdir()
    # .copier-answers.yml（stack='python'，让 ProjectScanner 识别为 Python 项目）
    (project_dir / ".copier-answers.yml").write_text(
        f"project_id: {project_id}\n"
        f"project_name: {name}\n"
        "stack: python\n"
        "_src_path: templates/python-tool\n",
        encoding="utf-8",
    )
    # pyproject.toml（让 PlcChecker 触发 not_applicable 分支）
    (project_dir / "pyproject.toml").write_text(
        f'[project]\nname = "{project_id.lower()}"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    # 不创建 .plc.json（关键：触发 not_applicable）
    return project_dir


def test_plc_check_python_project_friendly_output(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """V0.4.1 Step 3: plc check <Python 项目> 输出友好提示"""
    project_id = "SW-2026-PYT"
    _make_python_project(tmp_path, project_id)

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "check", project_id],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 输出应包含友好提示
    assert "PLC 检查不适用" in result.output
    assert project_id in result.output
    assert "Python 项目" in result.output
    # 不应该有「检查结果」表格（因为没跑检查）
    assert "检查结果:" not in result.output
    # 不应该有 FAIL 项
    assert "FAIL" not in result.output


def test_plc_check_python_project_json(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """V0.4.1 Step 3: plc check <Python 项目> --json 输出 not_applicable=True"""
    project_id = "SW-2026-PYJ"
    _make_python_project(tmp_path, project_id)

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "check", project_id, "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 解析 JSON 输出
    data = json.loads(result.output)
    assert data["not_applicable"] is True
    assert "Python 项目" in data["not_applicable_reason"]
    assert data["fail_count"] == 0
    assert len(data["items"]) == 0


def test_plc_check_all_skips_python_project(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """V0.4.1 Step 3: plc check --all 不应将 Python 项目误报为 FAIL

    场景：工作空间同时有 PLC 项目和 Python 项目
    预期：--all 只扫描 PLC 项目（_is_project_dir 排除 pyproject.toml 项目），
    Python 项目不出现在 PLC 检查摘要中
    """
    # PLC 项目（会被 _is_project_dir 识别）
    _make_plc_project(tmp_path, "DJ-2026-001", "PLC项目")
    # Python 项目（应被 _is_project_dir 排除，不出现在 --all 结果中）
    _make_python_project(tmp_path, "SW-2026-PYT", "Python工具")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "check", "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # PLC 项目应出现在检查摘要中
    assert "DJ-2026-001" in result.output
    # Python 项目不应出现在检查摘要中（_is_project_dir 已排除）
    # 注意：SW-2026-PYT 是 project_id，目录名是 SW-2026-PYT_Python工具
    # 如果误扫描到，会显示 project_id 或目录名
    assert "SW-2026-PYT" not in result.output
    # 不应该有 FAIL 标记（PLC 项目应通过检查，Python 项目被跳过）
    # 注意：PLC 项目可能因缺少 PM_SESSION 等 fail，但 Python 项目不应是失败原因


def test_plc_check_python_project_does_not_pollute_dashboard(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """V0.4.1 Step 3: Python 项目 PLC 检查不适用不应污染驾驶舱统计

    场景：工作空间仅有 Python 项目（无 PLC 项目）
    预期：plc check --all 应输出「未发现 PLC 项目」而非 FAIL
    """
    # 仅创建 Python 项目
    _make_python_project(tmp_path, "SW-2026-ONLY", "仅Python项目")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "check", "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 应输出「未发现 PLC 项目」（_is_project_dir 已排除 Python 项目）
    assert "未发现 PLC 项目" in result.output
    # 不应误报 Python 项目为 FAIL
    assert "SW-2026-ONLY" not in result.output
    assert "FAIL" not in result.output


# ── init 命令测试 ──────────────────────────────────────


@pytest.mark.parametrize("mode", ["standard-project", "test-suite"])
def test_plc_init(cli_runner: CliRunner, tmp_path: Path, mode: str) -> None:
    """测试 plc init <ID> --mode（创建 PLC 项目骨架）

    project_id 必须匹配 copier 模板验证规则: ^[A-Z]+-\\d{4}-\\d{3}$
    """
    project_id = "DJ-2026-100"
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "plc", "init", project_id,
            "--name", "初始化项目",
            "--mode", mode,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    project_dir = tmp_path / f"{project_id}_初始化项目"
    assert project_dir.is_dir()
    # 应生成 .copier-answers.yml（Copier 答案文件）
    assert (project_dir / ".copier-answers.yml").is_file()


def test_plc_init_default_mode(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc init 默认使用 standard-project 模式"""
    project_id = "DJ-2026-101"
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "plc", "init", project_id,
            "--name", "默认模式项目",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    project_dir = tmp_path / f"{project_id}_默认模式项目"
    assert project_dir.is_dir()
    # standard-project 模板生成 12 个标准目录
    # CHG-SCPT-2026-146: 模板已迁移到5大过程组，01_启动 替代 00_项目管理
    assert (project_dir / "01_启动").is_dir()
    assert (project_dir / "02_PLC程序").is_dir()


def test_plc_init_shared_library_fails(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """测试 plc init --mode shared-library 因模板变量不匹配而失败

    shared-library 模板期望 library_name 变量，但 CLI 传入 project_id/project_name，
    导致 Copier 渲染失败。此为已知限制，验证 CLI 优雅退出（exit_code=1）。
    """
    project_id = "DJ-2026-LIB"
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "plc", "init", project_id,
            "--name", "共享库项目",
            "--mode", "shared-library",
        ],
    )
    assert result.exit_code == 1


def test_plc_init_invalid_mode(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """测试 plc init --mode 无效值被 click Choice 拒绝"""
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "plc", "init", "DJ-2026-BAD",
            "--name", "无效模式",
            "--mode", "invalid-mode",
        ],
    )
    assert result.exit_code != 0


def test_plc_init_existing_path(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """测试 plc init 目标路径已存在时退出码 1"""
    project_id = "DJ-2026-EXISTS"
    # 预先创建同名目录
    (tmp_path / f"{project_id}_已存在项目").mkdir()
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "plc", "init", project_id,
            "--name", "已存在项目",
        ],
    )
    assert result.exit_code == 1


# ── repair 命令测试 ──────────────────────────────────────


def test_plc_repair(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc repair <ID>（自动修复项目结构）"""
    project_id = "DJ-2026-REPAIR"
    # 创建缺少标准目录和 PM_SESSION 的项目
    project_dir = _make_plc_project(tmp_path, project_id)

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "repair", project_id],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 修复后应创建标准目录和 PM_SESSION（CHG-SCPT-2026-146: 01_启动）
    assert (project_dir / "01_启动").is_dir()
    assert (project_dir / f"PM_SESSION_{project_id}.md").is_file()


def test_plc_repair_dry_run(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc repair <ID> --dry-run（仅预览不执行）"""
    project_id = "DJ-2026-DRY"
    project_dir = _make_plc_project(tmp_path, project_id)

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "repair", project_id, "--dry-run"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # dry_run 模式不应创建目录（CHG-SCPT-2026-146: 01_启动）
    assert not (project_dir / "01_启动").exists()


def test_plc_repair_not_found(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 repair 不存在的项目"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "plc", "repair", "NOT-EXIST"],
    )
    assert result.exit_code == 1


# ── standardize 命令测试 ────────────────────────────────


def test_plc_standardize_preview(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc standardize <ID>（预览模式，默认）"""
    project_id = "DJ-2026-STD"
    project_dir = _make_plc_project(
        tmp_path,
        project_id,
        with_pm_session=True,
        with_std_dirs=True,
    )
    # 创建 PRD 目录 + 非标准命名文档
    prd_dir = project_dir / "PRD"
    prd_dir.mkdir()
    (prd_dir / "接口文档_IFC-001.md").write_text("# 接口文档\n", encoding="utf-8")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "standardize", project_id],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 预览模式：原文件仍存在
    assert (prd_dir / "接口文档_IFC-001.md").exists()


def test_plc_standardize_apply(cli_runner: CliRunner, tmp_path: Path) -> None:
    """测试 plc standardize <ID> --apply（执行重命名）"""
    project_id = "DJ-2026-APPLY"
    project_dir = _make_plc_project(
        tmp_path,
        project_id,
        with_pm_session=True,
        with_std_dirs=True,
    )
    prd_dir = project_dir / "PRD"
    prd_dir.mkdir()
    (prd_dir / "接口文档_IFC-001.md").write_text("# 接口文档\n", encoding="utf-8")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "plc", "standardize", project_id, "--apply"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 执行模式：标准文件应存在
    assert (prd_dir / "接口文档_INT.md").exists()


def test_plc_standardize_no_change(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 standardize 对已标准化的项目无需操作"""
    # tmp_workspace 的项目无 PRD 文档，standardize 应正常返回
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "plc", "standardize", "DJ-2026-TEST"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_plc_standardize_not_found(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 standardize 不存在的项目"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "plc", "standardize", "NOT-EXIST"],
    )
    assert result.exit_code == 1


# 注：test_template_list 已迁移到 tests/cli/test_template.py（V0.5.2 步骤2 统一组织）
