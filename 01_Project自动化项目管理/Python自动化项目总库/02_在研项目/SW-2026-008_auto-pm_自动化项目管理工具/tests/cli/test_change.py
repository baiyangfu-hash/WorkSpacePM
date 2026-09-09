"""change CLI 命令测试 - V0.5.2 步骤1

覆盖 change_group 5 个子命令：
- list <PID> [--status] [--domain] [--full]
- show <CHG-NUM>
- create --pid --domain --nature --scope --applicant --background --necessity
- transition <CHG-NUM> --to <STATUS> [--approver] [--comment]
- edit <CHG-NUM> --background ... --risk-level ...

测试策略：
- 使用 _make_plc_project 创建轻量项目（绕过 Copier，快）
- 通过 CLI create 创建变更单后验证 list/show/transition/edit
- 边界用例：缺参/不存在项目/非法状态流转/编辑不存在变更单/无字段更新
- 测试后清理变更单文件，避免 session 污染

17 个用例分布：
- list: 5（空列表/有变更单/--status 筛选/--domain 筛选/--full）
- show: 2（正常/不存在）
- create: 3（正常/缺参/不存在项目）
- transition: 4（draft→submitted/非法状态/不存在变更单/draft 直接到 completed 不可达）
- edit: 3（正常更新/不存在变更单/无字段更新）
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

logger = logging.getLogger(__name__)

# ── 测试隔离：记录本模块创建的变更单，autouse fixture 在每个测试后清理 ──
_created_change_numbers: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup_test_changes(tmp_path: Path) -> Generator[None, None, None]:
    """每个测试后清理本测试创建的变更单文件和台帐条目

    避免变更单文件残留导致后续测试的 list/show 断言误判。
    使用 tmp_path 作为工作空间（每个测试独立隔离，无需跨测试清理），
    但保留清理逻辑作为防御性措施（防止 fixture 升级为 session 级时残留）。
    """
    yield
    workspace_root = str(tmp_path)
    cs = ChangeService(workspace_root)
    ledger_updater = cs._get_ledger_updater()
    for change_number in _created_change_numbers:
        try:
            file_path = cs._locator.find_change_file(change_number)
            # find_change_file 可能返回 str 或 Path，统一转为 Path
            fp = Path(file_path) if file_path else None
            if fp and fp.exists():
                project_path = cs._find_project_root_from_path(str(fp))
                if project_path:
                    from auto_pm.change.path_resolver import find_ledger_file

                    ledger_path = find_ledger_file(project_path)
                    if ledger_path:
                        ledger_updater.remove(ledger_path, change_number)
                fp.unlink()
        except (OSError, PermissionError, ValueError, KeyError) as e:
            logger.warning("清理变更单 %s 失败: %s: %s", change_number, type(e).__name__, e)
    _created_change_numbers.clear()


# ── 辅助函数 ──────────────────────────────────────────────


def _make_plc_project_for_change(
    workspace: Path,
    project_id: str = "DJ-2026-CHG",
    name: str = "变更测试项目",
) -> Path:
    """创建一个由 .plc.json 识别的 PLC 项目（供 change CLI 测试使用）

    复用 tests/cli/test_plc.py 的 _make_plc_project 设计，但本项目内联实现
    避免跨模块导入私有函数。
    """
    project_dir = workspace / f"{project_id}_{name}"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {"name": project_id, "version": "V1.0.0", "description": name},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_dir


def _create_change_via_cli(
    runner: CliRunner,
    workspace: Path,
    project_id: str = "DJ-2026-CHG",
) -> str:
    """通过 CLI 创建一个变更单，返回 change_number

    用于 transition/edit 测试的前置数据准备。
    """
    result = runner.invoke(
        cli,
        [
            "-w", str(workspace),
            "change", "create",
            "--pid", project_id,
            "--domain", "PLC",
            "--nature", "DEF",
            "--scope", "LOCAL",
            "--applicant", "cli_test",
            "--background", "CLI 测试变更背景",
            "--necessity", "CLI 测试变更必要性",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"创建变更单失败: {result.output}"
    # 从输出解析 change_number（格式：变更单创建成功: CHG-PLC-2026-XXX）
    import re

    m = re.search(r"变更单创建成功:\s*(CHG-\S+)", result.output)
    assert m, f"无法从输出解析 change_number: {result.output}"
    change_number = m.group(1)
    _created_change_numbers.append(change_number)
    return change_number


# ── list 命令测试（5 用例）──────────────────────────────


@pytest.mark.cli
def test_change_list_empty(cli_runner: CliRunner, tmp_path: Path) -> None:
    """list 项目无变更单时输出「未发现变更单」"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-EMPTY")
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "list", "DJ-2026-EMPTY"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "未发现变更单" in result.output


@pytest.mark.cli
def test_change_list_with_changes(cli_runner: CliRunner, tmp_path: Path) -> None:
    """list 项目有变更单时显示变更单列表"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "list", "DJ-2026-CHG"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "变更单列表" in result.output
    assert "CHG-PLC-" in result.output


@pytest.mark.cli
def test_change_list_filter_by_status(cli_runner: CliRunner, tmp_path: Path) -> None:
    """list --status 按状态筛选"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")
    # 刚创建的变更单状态为 draft，用 --status draft 应能查到
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "list", "DJ-2026-CHG",
            "--status", "draft",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert change_number in result.output


@pytest.mark.cli
def test_change_list_filter_by_domain(cli_runner: CliRunner, tmp_path: Path) -> None:
    """list --domain 按领域筛选"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "list", "DJ-2026-CHG",
            "--domain", "PLC",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "CHG-PLC-" in result.output

    # 筛选其他领域应无结果
    result_other = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "list", "DJ-2026-CHG",
            "--domain", "SCPT",
        ],
        catch_exceptions=False,
    )
    assert result_other.exit_code == 0
    assert "未发现变更单" in result_other.output


@pytest.mark.cli
def test_change_list_full_mode(cli_runner: CliRunner, tmp_path: Path) -> None:
    """list --full 完整模式不截断标题"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "list", "DJ-2026-CHG", "--full"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "变更单列表" in result.output


# ── show 命令测试（2 用例）──────────────────────────────


@pytest.mark.cli
def test_change_show_normal(cli_runner: CliRunner, tmp_path: Path) -> None:
    """show 正常显示变更单详情"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "show", change_number],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "变更编号:" in result.output
    assert change_number in result.output
    assert "项目编号:" in result.output
    assert "DJ-2026-CHG" in result.output
    assert "变更背景:" in result.output
    assert "CLI 测试变更背景" in result.output


@pytest.mark.cli
def test_change_show_not_found(cli_runner: CliRunner, tmp_path: Path) -> None:
    """show 不存在的变更单报错 exit_code=1"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "show", "CHG-PLC-2026-NOTEXIST"],
    )
    assert result.exit_code == 1
    assert "变更单不存在" in result.output


# ── create 命令测试（3 用例）──────────────────────────────


@pytest.mark.cli
def test_change_create_normal(cli_runner: CliRunner, tmp_path: Path) -> None:
    """create 正常创建变更单"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "create",
            "--pid", "DJ-2026-CHG",
            "--domain", "PLC",
            "--nature", "DEF",
            "--scope", "LOCAL",
            "--scope", "SYSTEM",
            "--applicant", "cli_test",
            "--background", "测试背景",
            "--necessity", "测试必要性",
            "--urgency", "urgent",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "变更单创建成功" in result.output
    assert "CHG-PLC-" in result.output
    # 记录到清理列表
    import re

    m = re.search(r"变更单创建成功:\s*(CHG-\S+)", result.output)
    if m:
        _created_change_numbers.append(m.group(1))


@pytest.mark.cli
def test_change_create_accepts_spec_domain(cli_runner: CliRunner, tmp_path: Path) -> None:
    """规范治理单使用 SPEC 领域时可创建并被读取。"""
    _make_plc_project_for_change(tmp_path, "SYS-2026-SPEC")
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "create",
            "--pid", "SYS-2026-SPEC",
            "--domain", "SPEC",
            "--nature", "DEF",
            "--scope", "SYSTEM",
            "--applicant", "cli_test",
            "--background", "规范治理兼容测试",
            "--necessity", "确保历史规范变更可读",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "CHG-SPEC-" in result.output

    import re

    match = re.search(r"变更单创建成功:\s*(CHG-\S+)", result.output)
    assert match
    change_number = match.group(1)
    _created_change_numbers.append(change_number)

    listed = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "list", "SYS-2026-SPEC", "--domain", "SPEC"],
        catch_exceptions=False,
    )
    assert listed.exit_code == 0
    assert change_number in listed.output


@pytest.mark.cli
def test_change_create_missing_required_option(cli_runner: CliRunner, tmp_path: Path) -> None:
    """create 缺少必填选项时 click 报错 exit_code != 0"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    # 缺少 --nature
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "create",
            "--pid", "DJ-2026-CHG",
            "--domain", "PLC",
            # --nature 缺失
            "--scope", "LOCAL",
            "--applicant", "cli_test",
            "--background", "测试",
            "--necessity", "测试",
        ],
    )
    assert result.exit_code != 0
    # click 缺参错误信息
    assert "Missing option" in result.output or "缺少" in result.output


@pytest.mark.cli
def test_change_create_nonexistent_project(cli_runner: CliRunner, tmp_path: Path) -> None:
    """create 项目不存在时 exit_code=1"""
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "create",
            "--pid", "DJ-2026-NOTEXIST",
            "--domain", "PLC",
            "--nature", "DEF",
            "--scope", "LOCAL",
            "--applicant", "cli_test",
            "--background", "测试",
            "--necessity", "测试",
        ],
    )
    assert result.exit_code == 1


# ── transition 命令测试（4 用例）──────────────────────────────


@pytest.mark.cli
def test_change_transition_draft_to_submitted(cli_runner: CliRunner, tmp_path: Path) -> None:
    """transition draft → submitted 正常流转"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "transition", change_number,
            "--to", "submitted",
            "--approver", "approver_test",
            "--comment", "CLI 流转测试",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "状态流转成功" in result.output
    assert "已提交" in result.output


@pytest.mark.cli
def test_change_transition_invalid_status(cli_runner: CliRunner, tmp_path: Path) -> None:
    """transition 非法目标状态被 click Choice 拒绝"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "transition", change_number,
            "--to", "invalid-status",
        ],
    )
    assert result.exit_code != 0


@pytest.mark.cli
def test_change_transition_nonexistent_change(cli_runner: CliRunner, tmp_path: Path) -> None:
    """transition 不存在的变更单 exit_code=1"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "transition", "CHG-PLC-2026-NOTEXIST",
            "--to", "submitted",
        ],
    )
    assert result.exit_code == 1
    assert "变更单不存在" in result.output


@pytest.mark.cli
def test_change_transition_unreachable_status(cli_runner: CliRunner, tmp_path: Path) -> None:
    """transition 不可达状态（draft 直接到 completed）应失败

    状态机约束：draft 只能到 submitted，不能直接到 completed。
    """
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "transition", change_number,
            "--to", "completed",
        ],
    )
    assert result.exit_code == 1
    assert "流转失败" in result.output or "不可达" in result.output or "非法" in result.output


# ── edit 命令测试（3 用例）──────────────────────────────


@pytest.mark.cli
def test_change_edit_normal(cli_runner: CliRunner, tmp_path: Path) -> None:
    """edit 正常更新变更单字段"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "edit", change_number,
            "--background", "更新后的背景",
            "--risk-level", "medium",
            "--mitigation", "缓解措施",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "变更单已更新" in result.output
    assert "background" in result.output or "背景" in result.output

    # 验证字段已实际更新
    show_result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "show", change_number],
        catch_exceptions=False,
    )
    assert show_result.exit_code == 0
    assert "更新后的背景" in show_result.output


@pytest.mark.cli
def test_change_edit_nonexistent_change(cli_runner: CliRunner, tmp_path: Path) -> None:
    """edit 不存在的变更单 exit_code=1"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    result = cli_runner.invoke(
        cli,
        [
            "-w", str(tmp_path),
            "change", "edit", "CHG-PLC-2026-NOTEXIST",
            "--background", "测试",
        ],
    )
    assert result.exit_code == 1
    assert "变更单不存在" in result.output


@pytest.mark.cli
def test_change_edit_no_fields_specified(cli_runner: CliRunner, tmp_path: Path) -> None:
    """edit 未指定任何更新字段时 exit_code=1"""
    _make_plc_project_for_change(tmp_path, "DJ-2026-CHG")
    change_number = _create_change_via_cli(cli_runner, tmp_path, "DJ-2026-CHG")

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "change", "edit", change_number],
    )
    assert result.exit_code == 1
    assert "未指定要更新的字段" in result.output
