"""New-format implementation cards: basis, change order and one change order with several cards.

Plan "实施卡与变更单定位与存放方案" §4.3/§4.4 and acceptance §6 cases 1 and 2.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

from auto_pm.application.core.implementation_card_precheck import (
    PrecheckReport,
    precheck_markdown_card,
    scopes_outside_card,
)
from auto_pm.ui.cli.implementation_card import command_tree_of

TREE = command_tree_of(cli)
PROJECT = "0100_PLC自动化/DJ-2099-001_测试"
MONITOR = f"{PROJECT}/11_监控/01_变更管理"
DRAWER = f"{MONITOR}/03_实施卡"
OTHER = "0100_PLC自动化/DJ-2099-002_别的项目"

BC_TABLE = """# 业务变更记录

| 编号 | 提出日期 | 改了什么 | 批准人 | 状态 | 关联 CHG / 提交 |
|---|---|---|---|---|---|
| BC-DJ-2099-001-001 | 2099-01-01 | 主控换型 | 待补 | 待补（程序在写） | 待补 |
| BC-DJ-2099-001-002 | 2099-01-02 | 握手改 Modbus TCP | baiyang | 已批（文档已更新） | 待补 |
| BC-DJ-2099-001-003 | 2099-01-03 | 外部交互层 | baiyang | 已实施（未现场验证） | 待补 |
| BC-DJ-2099-001-2099_01_000 | 2099-01-04 09:30 | 报警汇总 | baiyang | 已批 | 待补 |
| BC-DJ-2099-001-2098_12_000 | 2099-01-04 09:30 | 编号年月写错 | baiyang | 已批 | 待补 |
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _workspace(root: Path) -> str:
    files = {
        "README.md": "root\n",
        f"{PROJECT}/02_PLC程序/OB1.scl": "baseline\n",
        f"{PROJECT}/02_PLC程序/FB_3001.scl": "baseline\n",
        f"{PROJECT}/00_项目管理/020_需求说明_REQ.md": "## 6. 验收\n\n| A3 | 握手中途断线 |\n",
        f"{MONITOR}/02_变更记录/02_业务变更记录.md": BC_TABLE,
        f"{MONITOR}/02_变更记录/01_版本变更台账.md": "# 台账\n",
        f"{MONITOR}/01_变更单/CHG-PLC/CHG-PLC-2099-001.md": "# CHG\n",
        f"{OTHER}/11_监控/01_变更管理/01_变更单/CHG-PLC/CHG-PLC-2099-009.md": "# 别的项目\n",
        f"{DRAWER}/README.md": "drawer\n",
    }
    _git(root, "init")
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    return _git(root, "rev-parse", "HEAD")


def _card(
    root: Path,
    name: str,
    *,
    baseline: str,
    basis: str | None = "`BC-DJ-2099-001-002`",
    change: str | None = "`无`",
    rows: tuple[tuple[str, str], ...] = (("02_PLC程序/OB1.scl", "存在（只加调用）"),),
    extra: str = "",
    drawer: str = DRAWER,
) -> Path:
    header = [f"# 实施卡 {name}", ""]
    if basis is not None:
        header.append(f"> 依据：{basis}")
    if change is not None:
        header.append(f"> 变更单：{change}")
    header.append(f"> 隔离基线：`{baseline}`")
    if extra:
        header.append(extra)
    table = "\n".join(f"| {index} | `{path}` | {state} |" for index, (path, state) in enumerate(rows, 1))
    text = "\n".join(header) + (
        "\n\n## 3. 路径表\n\n| # | 路径（相对项目根） | 基线状态 |\n|---|---|---|\n" f"{table}\n"
    )
    card = root / drawer / f"{name}_测试.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(text, encoding="utf-8")
    return card


def _check(root: Path, card: Path, project_id: str | None = None) -> PrecheckReport:
    return precheck_markdown_card(card, workspace_root=root, command_tree=TREE, project_id=project_id)


def _messages(report: PrecheckReport) -> str:
    return "\n".join(f"{item.rule}|{item.subject}|{item.message}" for item in report.findings)


def test_new_card_with_an_approved_bc_passes_and_paths_are_project_relative(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline)

    report = _check(tmp_path, card, project_id="DJ-2099-001")

    assert report.passed, _messages(report)
    assert report.card_format == "new" and report.change == ""
    assert report.basis == ("BC-DJ-2099-001-002",)
    assert report.path_root == PROJECT
    assert [item.path for item in report.paths] == [f"{PROJECT}/02_PLC程序/OB1.scl"]
    assert scopes_outside_card([f"{PROJECT}/02_PLC程序/OB1.scl"], report) == []
    assert report.to_dict()["card_format"] == "new"


def test_card_without_basis_is_rejected(tmp_path: Path) -> None:
    """Acceptance §6 case 1: no basis line, no Work."""
    baseline = _workspace(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis=None)

    report = _check(tmp_path, card)

    assert not report.passed and "缺少机器可读头部 `依据：`" in _messages(report)


def test_basis_must_exist_belong_to_the_project_and_be_approved(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    cases = {
        "`BC-DJ-2099-001-001`": "必须是“已批”",
        "`BC-DJ-2099-001-099`": "业务变更记录表里没有这一条",
        "`BC-DJ-2099-002-001`": "不属于本项目",
        "`BC-DJ-2099-1`": "格式应为",
        "`BC-DJ-2099-001-2099_13_000`": "格式应为",
        "`BC-DJ-2099-001-2099_01_1000`": "格式应为",
        "`BC-DJ-2099-001-2099_01_001`": "业务变更记录表里没有这一条",
        "`BC-DJ-2099-001-2098_12_000`": "与提出时间不符",
        "`CHG-PLC-2099-001`": "不能当作依据",
        "`<BC-…>`": "占位符",
    }
    for basis, fragment in cases.items():
        card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis=basis)
        report = _check(tmp_path, card)
        assert not report.passed and fragment in _messages(report), (basis, _messages(report))


def test_month_numbered_bc_is_accepted(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis="`BC-DJ-2099-001-2099_01_000`")

    report = _check(tmp_path, card)

    assert report.passed, _messages(report)
    assert report.basis == ("BC-DJ-2099-001-2099_01_000",)


REQ_ID = "REQ-DJ-2099-001-2099_01_000"


def _req(root: Path, *, status: str = "已确认", version: str = "V2", drawer: str = f"{MONITOR}/00_需求核对单") -> None:
    target = root / drawer / f"{REQ_ID}_报警汇总.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"# 需求核对单 {REQ_ID}：报警汇总\n\n> 状态：{status}\n\n## 8. 用户确认（由驾驶舱写入，AI 不填）\n\n"
        f"| 项 | 内容 |\n|---|---|\n| 确认的版本 | {version} |\n| 内容指纹 | ab12 |\n",
        encoding="utf-8",
    )


def test_confirmed_requirement_checklist_counts_as_basis(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    _req(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis=f"`{REQ_ID} V2`")

    report = _check(tmp_path, card)

    assert report.passed, _messages(report)


def test_requirement_checklist_basis_must_be_confirmed_for_that_version(tmp_path: Path) -> None:
    cases = {
        (f"`{REQ_ID} V1`", "已确认", "V2", "00_需求核对单"): "用户确认的是 V2",
        (f"`{REQ_ID} V2`", "待核对", "（由驾驶舱写入）", "00_需求核对单"): "还没有经用户确认",
        (f"`{REQ_ID} V2`", "待核对", "V2", "00_需求核对单"): "还没有经用户确认",
        (f"`{REQ_ID} V2`", "已确认", "V2", "别处"): "应恰有一份",
        (f"`{REQ_ID}`", "已确认", "V2", "00_需求核对单"): "写法应为",
        ("`REQ-DJ-2099-002-2099_01_000 V2`", "已确认", "V2", "00_需求核对单"): "不属于本项目",
    }
    for index, ((basis, status, version, drawer), fragment) in enumerate(cases.items()):
        root = tmp_path / f"case{index}"
        root.mkdir()
        baseline = _workspace(root)
        _req(root, status=status, version=version, drawer=f"{MONITOR}/{drawer}")
        card = _card(root, "CARD-DJ-2099-001-001", baseline=baseline, basis=basis)
        report = _check(root, card)
        assert not report.passed and fragment in _messages(report), (basis, _messages(report))


def test_checklist_is_not_searched_as_a_requirement_document(tmp_path: Path) -> None:
    """An unconfirmed checklist that happens to mention an item id must not stand in for the 需求说明."""
    baseline = _workspace(tmp_path)
    target = tmp_path / MONITOR / "00_需求核对单" / f"{REQ_ID}_报警汇总.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("| B7 | AI 自己写的条目 |\n", encoding="utf-8")
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis="`B7`")

    report = _check(tmp_path, card)

    assert not report.passed and "需求条目在本项目的需求说明" in _messages(report)


def test_implemented_bc_also_counts_as_approved(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis="`BC-DJ-2099-001-003`")

    assert _check(tmp_path, card).passed


def test_requirement_items_are_looked_up_in_the_project_req_files(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    named = _card(
        tmp_path, "CARD-DJ-2099-001-001", baseline=baseline,
        basis="需求说明验收项 `A3`（`00_项目管理/020_需求说明_REQ.md` 第 6 节）",
    )
    assert _check(tmp_path, named).passed, _messages(_check(tmp_path, named))

    searched = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis="`A3`")
    assert _check(tmp_path, searched).passed

    missing = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis="`A9`")
    assert "需求条目在本项目的需求说明" in _messages(_check(tmp_path, missing))

    no_file = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, basis="`A3`（`00_项目管理/无此文件.md`）")
    assert "引用的需求文件不存在" in _messages(_check(tmp_path, no_file))


def test_guarded_paths_need_a_change_order(tmp_path: Path) -> None:
    """Acceptance §6 case 2: a core ledger in the path table with 变更单 无 is rejected."""
    baseline = _workspace(tmp_path)
    rows = (("11_监控/01_变更管理/02_变更记录/01_版本变更台账.md", "存在"),)
    without = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, rows=rows)
    assert "变更单不能写“无”" in _messages(_check(tmp_path, without))

    spec = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline,
                 extra="> 路径根：`.`", rows=(("00_Obsidian_Base全局规范文件仓库/x.md", "计划新增"),))
    assert "变更单不能写“无”" in _messages(_check(tmp_path, spec))

    with_change = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, rows=rows,
                        change="`CHG-PLC-2099-001`")
    report = _check(tmp_path, with_change)
    assert report.passed, _messages(report)
    assert report.change == "CHG-PLC-2099-001"


def test_change_order_is_looked_up_only_in_the_cards_own_project(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    foreign = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, change="`CHG-PLC-2099-009`")
    assert "找不到这张变更单" in _messages(_check(tmp_path, foreign))

    two = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline,
                change="`CHG-PLC-2099-001`、`CHG-PLC-2099-002`")
    assert "最多挂一张变更单" in _messages(_check(tmp_path, two))

    missing = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, change=None)
    assert "缺少机器可读头部 `变更单：`" in _messages(_check(tmp_path, missing))


def test_card_must_sit_in_its_projects_drawer_and_match_the_work_project(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    stray = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, drawer=f"{PROJECT}/02_规划",
                  extra="> 路径根：`.`", rows=(("README.md", "存在"),))
    assert "必须放在本项目的" in _messages(_check(tmp_path, stray))

    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline)
    assert "与 Work 的项目 SW-2026-008 不一致" in _messages(_check(tmp_path, card, "SW-2026-008"))

    wrong_name = _card(tmp_path, "CARD-DJ-2099-002-001", baseline=baseline)
    assert "卡号前缀应为 CARD-DJ-2099-001-" in _messages(_check(tmp_path, wrong_name))


def test_new_card_without_baseline_is_told_to_fill_it_at_dispatch(tmp_path: Path) -> None:
    _workspace(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline="x")
    card.write_text(card.read_text(encoding="utf-8").replace("> 隔离基线：`x`\n", ""), encoding="utf-8")

    assert "派工前要在卡片头部填 `隔离基线：`" in _messages(_check(tmp_path, card))


def test_one_change_order_with_several_cards(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    change = "`CHG-PLC-2099-001`"
    first = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, change=change,
                  extra="> 状态：已派工")
    disjoint = _card(tmp_path, "CARD-DJ-2099-001-002", baseline=baseline, change=change,
                     rows=(("02_PLC程序/FB_3001.scl", "存在"),))
    assert _check(tmp_path, first).passed and _check(tmp_path, disjoint).passed

    overlapping = _card(tmp_path, "CARD-DJ-2099-001-003", baseline=baseline, change=change,
                        rows=(("02_PLC程序", "存在"),))
    assert "CARD-DJ-2099-001-001" in _messages(_check(tmp_path, overlapping))
    assert "排定先后" in _messages(_check(tmp_path, first))

    ordered = _card(tmp_path, "CARD-DJ-2099-001-003", baseline=baseline, change=change,
                    rows=(("02_PLC程序", "存在"),),
                    extra="> 前置卡：`CARD-DJ-2099-001-001`、`CARD-DJ-2099-001-002`")
    assert _check(tmp_path, ordered).passed, _messages(_check(tmp_path, ordered))

    # A sibling that is already accepted no longer competes for the files.
    _card(tmp_path, "CARD-DJ-2099-001-003", baseline=baseline, change=change,
          rows=(("02_PLC程序", "存在"),), extra="> 状态：已验收")
    assert _check(tmp_path, first).passed


def test_by_change_lists_the_cards_of_one_project_only(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    change = "`CHG-PLC-2099-001`"
    _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline, change=change, extra="> 状态：已派工")
    _card(tmp_path, "CARD-DJ-2099-001-002", baseline=baseline, change=change,
          extra="> 状态：已验收（2099-01-05）")
    _card(tmp_path, "CARD-DJ-2099-001-003", baseline=baseline)
    _card(tmp_path, "CARD-DJ-2099-002-001", baseline=baseline, change=change,
          drawer=f"{OTHER}/11_监控/01_变更管理/03_实施卡")
    before = sorted(str(path) for path in tmp_path.rglob("*") if ".git" not in path.parts)

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "implementation-card", "by-change",
                                      "--change", "CHG-PLC-2099-001", "--project-dir", PROJECT])

    assert result.exit_code == 0, result.output
    cards = json.loads(result.output)["cards"]
    assert [(item["card_id"], item["state"], item["open"]) for item in cards] == [
        ("CARD-DJ-2099-001-001", "已派工", True),
        ("CARD-DJ-2099-001-002", "已验收", False),
    ]
    assert sorted(str(path) for path in tmp_path.rglob("*") if ".git" not in path.parts) == before


def test_precheck_command_takes_the_work_project(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    card = _card(tmp_path, "CARD-DJ-2099-001-001", baseline=baseline)

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "implementation-card", "precheck",
                                      "--card-file", str(card), "--pid", "DJ-2099-002"])

    assert result.exit_code == 1
    assert "不一致" in result.output


def test_legacy_card_outside_the_drawer_keeps_the_old_rules(tmp_path: Path) -> None:
    baseline = _workspace(tmp_path)
    card = tmp_path / "SW-PLAN" / "165_legacy.md"
    card.parent.mkdir()
    card.write_text(
        f"> 隔离基线：`{baseline}`\n> 路径根：`.`\n\n| # | 路径 | 基线状态 |\n|---|---|---|\n"
        "| 1 | `README.md` | 存在 |\n",
        encoding="utf-8",
    )

    report = _check(tmp_path, card)

    assert report.passed and report.card_format == "legacy"
