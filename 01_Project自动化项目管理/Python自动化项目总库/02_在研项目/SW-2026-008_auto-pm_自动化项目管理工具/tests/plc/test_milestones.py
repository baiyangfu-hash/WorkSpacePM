"""里程碑表读取与检查：新项目计划日期没填拦住，老项目迁入只提示，格式能被程序读出。"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.plc import milestones as ms

ROOT = Path(__file__).resolve().parents[6]
TEMPLATE = ROOT / "0100_PLC自动化" / "00_通用规范" / "项目文档模板" / "11_里程碑表模板.md"

FILLED = """---
project_id: "DJ-2026-MS"
项目来源: {origin}
---

| 阶段 | 计划日期 | 实际日期 | 状态 | 备注 |
|---|---|---|---|---|
| 需求 | 2026-10-01 | 2026-10-03 | 已完成 | |
| 设计 | 2026-10-20 | | 进行中 | |
| 编程 | 2026-11-05 | | 未开始 | |
| 仿真 | 2026-11-15 | | 未开始 | |
| 现场 | | | 不适用 | 纯测试套件 |
| 收尾 | 2026-12-01 | | 未开始 | |
"""


def write(project: Path, text: str, name: str = "004_DJ-2026-MS_里程碑表.md") -> Path:
    path = project / "00_项目管理" / "01_立项与需求" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def kinds(table: ms.MilestoneTable) -> list[tuple[str, str, str]]:
    return [(f.kind, f.variable, f.severity) for f in table.findings]


def test_m01_filled_table_has_no_findings_and_rows_are_readable(tmp_path: Path) -> None:
    write(tmp_path, FILLED.format(origin="新项目"))
    table = ms.check_project(str(tmp_path))
    assert table.findings == []
    assert [r.stage for r in table.rows] == list(ms.STAGES)
    assert table.rows[0].planned == "2026-10-01" and table.rows[0].actual == "2026-10-03"
    assert table.rows[4].status == "不适用" and table.rows[4].planned == ""


def test_m02_new_project_with_empty_planned_date_fails(tmp_path: Path) -> None:
    write(tmp_path, FILLED.format(origin="新项目").replace("| 编程 | 2026-11-05 |", "| 编程 | 待填 |"))
    table = ms.check_project(str(tmp_path))
    assert kinds(table) == [("planned", "编程", "fail")]
    assert table.findings[0].doc_loc.endswith("_里程碑表.md:10")


def test_m03_migrated_project_with_empty_planned_date_only_warns(tmp_path: Path) -> None:
    write(tmp_path, FILLED.format(origin="老项目迁入").replace("| 编程 | 2026-11-05 |", "| 编程 | |"))
    assert kinds(ms.check_project(str(tmp_path))) == [("planned", "编程", "warn")]


def test_m04_missing_or_unknown_origin_is_treated_as_new_project(tmp_path: Path) -> None:
    write(tmp_path, FILLED.format(origin="老项目").replace("| 收尾 | 2026-12-01 |", "| 收尾 | - |"))
    table = ms.check_project(str(tmp_path))
    assert table.strict
    assert kinds(table) == [("origin", "", "fail"), ("planned", "收尾", "fail")]


def test_m05_no_milestone_file_only_warns(tmp_path: Path) -> None:
    table = ms.check_project(str(tmp_path))
    assert table.path is None and kinds(table) == [("missing", "", "warn")]


def test_m06_bad_dates_status_and_stages_are_reported(tmp_path: Path) -> None:
    text = (FILLED.format(origin="新项目")
            .replace("| 需求 | 2026-10-01 | 2026-10-03 | 已完成 |", "| 需求 | 2026/10/01 | | 已完成 |")
            .replace("| 设计 | 2026-10-20 | | 进行中 |", "| 设计 | 2026-02-30 | 昨天 | 做了一半 |")
            .replace("| 仿真 | 2026-11-15 | | 未开始 | |\n", "")
            + "| 调试 | 2026-12-05 | | 未开始 | |\n")
    write(tmp_path, text)
    got = kinds(ms.check_project(str(tmp_path)))
    assert ("stage", "调试", "fail") in got
    assert ("stage", "仿真", "fail") in got
    assert ("planned", "需求", "fail") in got and ("actual", "需求", "fail") in got
    assert ("planned", "设计", "fail") in got and ("actual", "设计", "fail") in got
    assert ("status", "设计", "fail") in got


def test_m07_wrong_order_and_duplicates_are_reported(tmp_path: Path) -> None:
    lines = FILLED.format(origin="新项目").splitlines()
    swapped = lines[:7] + [lines[8], lines[7]] + lines[9:]
    write(tmp_path, "\n".join(swapped) + "\n")
    assert ("stage", "", "fail") in kinds(ms.check_project(str(tmp_path)))
    write(tmp_path, FILLED.format(origin="新项目") + "| 需求 | 2026-10-02 | | 未开始 | |\n")
    assert ("stage", "需求", "fail") in kinds(ms.check_project(str(tmp_path)))


def test_m08_no_table_and_two_files_are_reported(tmp_path: Path) -> None:
    write(tmp_path, "---\n项目来源: 新项目\n---\n\n# 空\n")
    assert kinds(ms.check_project(str(tmp_path))) == [("table", "", "fail")]
    write(tmp_path, FILLED.format(origin="新项目"), name="005_另一份_里程碑表.md")
    assert ("duplicate", "", "fail") in kinds(ms.check_project(str(tmp_path)))


def test_m09_archive_folders_are_ignored(tmp_path: Path) -> None:
    archived = tmp_path / "_archive" / "004_旧_里程碑表.md"
    archived.parent.mkdir()
    archived.write_text(FILLED.format(origin="新项目"), encoding="utf-8")
    assert kinds(ms.check_project(str(tmp_path))) == [("missing", "", "warn")]


def test_m10_the_shipped_template_parses_and_is_blocked_until_dates_are_filled(tmp_path: Path) -> None:
    write(tmp_path, TEMPLATE.read_text(encoding="utf-8"))
    table = ms.check_project(str(tmp_path))
    assert table.origin == ms.ORIGIN_NEW
    assert [r.stage for r in table.rows] == list(ms.STAGES)
    assert kinds(table) == [("planned", stage, "fail") for stage in ms.STAGES]


def test_m11_shared_libraries_are_not_checked(tmp_path: Path) -> None:
    (tmp_path / ".plc.json").write_text('{"name": "SysLib", "project_type": "library"}', encoding="utf-8")
    table = ms.check_project(str(tmp_path))
    assert not table.applicable and table.findings == []
    (tmp_path / ".plc.json").write_text('{"name": "DJ-2026-MS", "project_type": "single_machine"}', encoding="utf-8")
    assert kinds(ms.check_project(str(tmp_path))) == [("missing", "", "warn")]


def test_m12_generated_shared_libraries_are_recognised_by_their_copier_mode(tmp_path: Path) -> None:
    (tmp_path / ".plc.json").write_text('{"name": "MyLib", "libraries": []}', encoding="utf-8")
    (tmp_path / ".copier-answers.yml").write_text("library_name: MyLib\nstack: plc\nmode: shared-library\n",
                                                  encoding="utf-8")
    assert not ms.check_project(str(tmp_path)).applicable
    (tmp_path / ".copier-answers.yml").write_text("project_id: DJ-2026-MS\nmode: standard-project\n",
                                                  encoding="utf-8")
    assert kinds(ms.check_project(str(tmp_path))) == [("missing", "", "warn")]
    (tmp_path / ".copier-answers.yml").unlink()
    (tmp_path / ".plc.json").write_text('{"name": "MyLib", "project_type": "shared_library"}', encoding="utf-8")
    assert not ms.check_project(str(tmp_path)).applicable


def test_m13_dates_fromisoformat_accepts_but_the_template_forbids_are_rejected(tmp_path: Path) -> None:
    # Python 3.11+ date.fromisoformat also takes basic and week forms; only YYYY-MM-DD is allowed.
    text = (FILLED.format(origin="新项目")
            .replace("| 编程 | 2026-11-05 |", "| 编程 | 20261105 |")
            .replace("| 仿真 | 2026-11-15 |", "| 仿真 | 2026-W46-1 |")
            .replace("| 需求 | 2026-10-01 | 2026-10-03 |", "| 需求 | 2026-10-01 | 2026-276 |"))
    write(tmp_path, text)
    assert kinds(ms.check_project(str(tmp_path))) == [
        ("actual", "需求", "fail"), ("planned", "编程", "fail"), ("planned", "仿真", "fail")]
