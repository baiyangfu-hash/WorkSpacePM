"""项目周期规范推日期：数字只从规范文档读，只填空着的计划日期。"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.plc import cycle_plan as cp
from auto_pm.plc import milestones as ms
from click.testing import CliRunner

from tests.plc.test_milestones import FILLED, write

ROOT = Path(__file__).resolve().parents[6]
SPEC = ROOT / cp.SPEC_RELATIVE
D = dt.date(2026, 10, 10)

MINI_SPEC = """---
version: "V9"
---
| 规模 | 判据 | 系数 |
|---|---|---|
| 单机 | 1 台 | 1.0 |
| 小线 | 2～5 台 | 2 |

| 阶段 | 纯电气 | 机电协作 | 加上位机 | 加机器人 | 说明 |
|---|---|---|---|---|---|
| 需求 | 0 | 0 | 0 | 0 | |
| 设计 | 1 | 4 | 1 | 2 | |
| 编程 | 2 | 3 | 1 | 2 | |
| 仿真 | 1 | 2 | 0.5 | 1 | |
| 现场 | 4 | 4 | 0.5 | 1 | |
| 收尾 | 2 | 2 | 0 | 0 | |

| 衔接 | 间隔（周） | 说明 |
|---|---|---|
| 电气初稿确认 → 开始编程 | 1 | |
"""


def spec_file(tmp_path: Path, text: str = MINI_SPEC) -> cp.CycleSpec:
    path = tmp_path / "spec.md"
    path.write_text(text, encoding="utf-8")
    return cp.read_spec(str(path))


def test_c01_the_repository_spec_reproduces_its_own_dj009_example() -> None:
    spec = cp.read_spec(str(SPEC))
    assert spec.version == "V0.2" and spec.scales == {"单机": 1.0, "小线": 1.5, "整线": 2.5}
    dates = cp.plan(spec, D, "机电协作", (), "单机")
    assert {k: v.isoformat() for k, v in dates.items()} == {
        "需求": "2026-10-10", "设计": "2026-11-07", "编程": "2026-11-14",
        "仿真": "2026-11-28", "现场": "2026-12-26", "收尾": "2027-01-09"}


def test_c02_addons_and_scale_multiply_stage_weeks_but_not_the_gap(tmp_path: Path) -> None:
    spec = spec_file(tmp_path)
    dates = cp.plan(spec, D, "纯电气", ("上位机", "机器人"), "小线")
    # 设计 (1+1+2)*2=8 周；电气初稿 1*2=2 周；编程 初稿 + 间隔 1 周 + (2+1+2)*2=10 周 = 13 周；
    # 仿真 从编程和设计较晚者起 (1+0.5+1)*2=5 周；现场 (4+0.5+1)*2=11 周；收尾 4 周
    assert dates["设计"] == D + dt.timedelta(weeks=8)
    assert dates["编程"] == D + dt.timedelta(weeks=13)
    assert dates["仿真"] == dates["编程"] + dt.timedelta(weeks=5)
    assert dates["现场"] == dates["仿真"] + dt.timedelta(weeks=11)
    assert dates["收尾"] == dates["现场"] + dt.timedelta(weeks=4)


def test_c03_half_weeks_round_up_to_whole_days(tmp_path: Path) -> None:
    spec = spec_file(tmp_path, MINI_SPEC.replace("| 设计 | 1 |", "| 设计 | 0.5 |"))
    assert cp.plan(spec, D, "纯电气", (), "单机")["设计"] == D + dt.timedelta(days=4)


def test_c04_changing_a_number_in_the_spec_changes_the_dates(tmp_path: Path) -> None:
    before = cp.plan(spec_file(tmp_path), D, "机电协作", (), "单机")
    after = cp.plan(spec_file(tmp_path, MINI_SPEC.replace("| 设计 | 1 | 4 |", "| 设计 | 1 | 6 |")),
                    D, "机电协作", (), "单机")
    assert after["设计"] - before["设计"] == dt.timedelta(weeks=2)


@pytest.mark.parametrize(("old", "new", "message"), [
    ("| 仿真 | 1 | 2 | 0.5 | 1 | |\n", "", "缺阶段 仿真"),
    ("| 编程 | 2 |", "| 编程 | 两 |", "不是数字"),
    ("| 电气初稿确认 → 开始编程 | 1 | |\n", "", "电气初稿确认 → 开始编程"),
    ("| 规模 | 判据 | 系数 |", "| 级别 | 判据 | 系数 |", "规模表"),
    ("| 加机器人 |", "| 机器人 |", "缺列"),
    ("| 编程 | 2 |", "| 编程 | -2 |", "超出范围"),
    ("| 编程 | 2 |", "| 编程 | nan |", "超出范围"),
    ("| 编程 | 2 |", "| 编程 | inf |", "超出范围"),
    ("| 单机 | 1 台 | 1.0 |", "| 单机 | 1 台 | 0 |", "超出范围"),
    ("| 单机 | 1 台 | 1.0 |", "| 单机 | 1 台 | -1 |", "超出范围"),
    ("| 电气初稿确认 → 开始编程 | 1 |", "| 电气初稿确认 → 开始编程 | -1 |", "超出范围"),
])
def test_c05_a_broken_spec_is_refused_with_the_reason(tmp_path: Path, old: str, new: str, message: str) -> None:
    with pytest.raises(cp.CycleSpecError, match=message):
        spec_file(tmp_path, MINI_SPEC.replace(old, new))


def test_c06_unknown_type_addon_or_scale_is_refused(tmp_path: Path) -> None:
    spec = spec_file(tmp_path)
    for args in (("研发", (), "单机"), ("纯电气", ("视觉",), "单机"), ("纯电气", (), "整线")):
        with pytest.raises(cp.CycleSpecError):
            cp.plan(spec, D, *args)


def test_c07_fill_only_touches_empty_planned_dates_and_keeps_not_applicable(tmp_path: Path) -> None:
    text = (FILLED.format(origin="老项目迁入")
            .replace("| 编程 | 2026-11-05 |", "| 编程 | 待填 |")
            .replace("| 收尾 | 2026-12-01 |", "| 收尾 | |"))
    path = write(tmp_path, text)
    dates = cp.plan(spec_file(tmp_path), D, "机电协作", (), "单机")

    preview = cp.fill_milestone_file(str(path), dates, "按规范推算", write=False)
    assert preview.filled == ["编程", "收尾"] and path.read_text(encoding="utf-8") == text
    assert set(preview.kept) == {"需求", "设计", "仿真", "现场"}

    cp.fill_milestone_file(str(path), dates, "按规范推算", write=True)
    table = ms.read_milestones(str(path))
    by_stage = {r.stage: r for r in table.rows}
    assert by_stage["编程"].planned == "2026-11-14" and by_stage["编程"].note == "按规范推算"
    assert by_stage["收尾"].planned == "2027-01-09"
    assert by_stage["设计"].planned == "2026-10-20"  # existing date untouched
    assert by_stage["现场"].planned == "" and by_stage["现场"].status == "不适用"
    assert by_stage["现场"].note == "纯测试套件"
    assert table.findings == []


def test_c08_find_spec_walks_up_from_the_project(tmp_path: Path) -> None:
    target = tmp_path / cp.SPEC_RELATIVE
    target.parent.mkdir(parents=True)
    target.write_text(MINI_SPEC, encoding="utf-8")
    project = tmp_path / "0100_PLC自动化" / "DJ-2026-X"
    project.mkdir()
    assert cp.find_spec(str(project)) == str(target)
    elsewhere = tmp_path.parent / f"{tmp_path.name}_无规范"
    elsewhere.mkdir()
    assert cp.find_spec(str(elsewhere)) != str(target)


def invoke(workspace: Path, *args: str) -> tuple[int, str]:
    result = CliRunner(env={}).invoke(cli, ["-w", str(workspace), "plc", "docs", "plan", *args],
                                      catch_exceptions=False)
    return result.exit_code, result.output


def test_c09_cli_previews_by_default_writes_with_flag_and_rejects_bad_dates(tmp_path: Path) -> None:
    spec = tmp_path / cp.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(MINI_SPEC, encoding="utf-8")
    project = tmp_path / "0100_PLC自动化" / "DJ-2026-X"
    project.mkdir()
    (project / ".plc.json").write_text(json.dumps({"name": "DJ-2026-X"}), encoding="utf-8")
    base = ["--project-path", str(project), "--type", "机电协作", "--scale", "单机"]

    code, output = invoke(tmp_path, *base, "--start", "2026-10-10")
    assert code == 0 and "设计  2026-11-07" in output and "没有里程碑表" in output

    path = write(project, FILLED.format(origin="新项目").replace("| 仿真 | 2026-11-15 |", "| 仿真 | |"))
    code, output = invoke(tmp_path, *base, "--start", "2026-10-10")
    assert code == 0 and "预览" in output and "仿真" in output
    assert "| 仿真 | |" in path.read_text(encoding="utf-8")
    code, output = invoke(tmp_path, *base, "--start", "2026-10-10", "--write")
    assert code == 0 and "已写入 1 个" in output
    assert "| 仿真 | 2026-11-28 |" in path.read_text(encoding="utf-8")
    assert "V9" in path.read_text(encoding="utf-8")

    for bad in ("20261010", "2026-W41-6", "2026-13-01"):
        assert invoke(tmp_path, *base, "--start", bad)[0] == 2
    assert invoke(tmp_path, *base[:4], "--scale", "巨线", "--start", "2026-10-10")[0] == 1


def test_c10_programming_runs_parallel_to_design_and_simulation_waits_for_both(tmp_path: Path) -> None:
    # 编程从电气初稿（纯电气设计 1 周）+ 间隔 1 周开始、3 周后完成，共 5 周；设计拉长到 8 周时仿真要等设计。
    spec = spec_file(tmp_path, MINI_SPEC.replace("| 设计 | 1 | 4 |", "| 设计 | 1 | 8 |"))
    dates = cp.plan(spec, D, "机电协作", (), "单机")
    assert dates["编程"] == D + dt.timedelta(weeks=5)
    assert dates["设计"] == D + dt.timedelta(weeks=8)
    assert dates["仿真"] == dates["设计"] + dt.timedelta(weeks=2)
