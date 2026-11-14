"""TD-SW008-596（D-331）：全局 DB 里放 FB 实例（LSP-905 §4.11 第 1 条，导入 TIA 时这个 DB 生成不出），检查器第一阶段只报警告。

真工程上的命中（005 的 GlobalVars 9 处，另有 009 的 4 处、000 的 6 处）是真命中，只列清单、不在本批改工程；升成失败另立技术债。
005 那 9 处的测试放在 tests/plc/test_scl_linter.py（已登记读项目外的真文件，本文件不读）。
背景 DB（``DATA_BLOCK "DB_X"`` 下一行只写 ``"FB_X"``）和调用方 FB 里的多重实例是合法写法，不报。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.plc.checker import SCL_GLOBAL_DB_FB_ITEM, PlcChecker
from auto_pm.domain.plc.scl_linter import SclLinter

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

_GLOBAL_DB = """DATA_BLOCK GlobalVars
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
NON_RETAIN
VAR
    bStart      : BOOL;                     // FB_1001 的启动按钮（注释里的 FB_ 不算）
    stConv      : ST_Conveyor;
    tDelay      : TON_TIME;
    fbMode      : FB_1001_MachineMode;      // 模式
    "fbQuoted"  : "FB_1002_Quoted";
    arrFb       : ARRAY[1..4] OF FB_1003_Layer;
    fbAttr {S7_SetPoint := 'False'} : FB_1004_Attr;
END_VAR

BEGIN
    bStart := FALSE;
END_DATA_BLOCK
"""


def _hits(text: str, file_path: str = "GlobalVars.db") -> list[int]:
    report = SclLinter.lint_text(text, file_path=file_path)
    return [v.line_number for v in report.violations if v.rule_id == SclLinter.GLOBAL_DB_FB_INSTANCE_RULE]


def _at(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.splitlines(), start=1) if needle in line)


def test_g01_fb_typed_members_of_a_global_db_are_reported_with_their_line() -> None:
    assert _hits(_GLOBAL_DB) == [_at(_GLOBAL_DB, n) for n in ("fbMode", '"fbQuoted"', "arrFb", "fbAttr")]


def test_g02_basic_types_structs_system_timers_and_comments_are_not_reported() -> None:
    text = _GLOBAL_DB.replace("    fbMode", "//  fbMode").replace('    "fbQuoted"', "//  q").replace("    arrFb", "//  a").replace(
        "    fbAttr", "//  b"
    )
    assert _hits(text) == []


@pytest.mark.parametrize(
    "instance_db",
    [
        'DATA_BLOCK "DB_TestBench"\n"FB_9001_TestBench"\nBEGIN\nEND_DATA_BLOCK\n',
        "DATA_BLOCK DB_TimerTest\nFB_TimerTest\nBEGIN\nEND_DATA_BLOCK\n",
        "DATA_BLOCK \"DB_1001_StationA\"\n{ S7_Optimized_Access := 'TRUE' }\nVERSION : 0.1\nNON_RETAIN\n\"FB_1001_Station\"\nBEGIN\nEND_DATA_BLOCK\n",
    ],
)
def test_g03_instance_dbs_are_legal_and_not_reported(instance_db: str) -> None:
    assert _hits(instance_db, "DB_X.scl") == []


def test_g04_multi_instances_inside_a_calling_fb_are_legal_and_not_reported() -> None:
    fb = 'FUNCTION_BLOCK "FB_9001_Bench"\nVAR\n    fbInner : FB_1001_Inner;\nEND_VAR\nBEGIN\n    #fbInner();\nEND_FUNCTION_BLOCK\n'
    assert _hits(fb, "FB_9001_Bench.scl") == []


def test_g05_it_is_only_a_warning_and_survives_the_db_file_filter(tmp_path: Path) -> None:
    path = tmp_path / "GlobalVars.db"
    path.write_text(_GLOBAL_DB, encoding="utf-8")
    found = [v for v in SclLinter.lint_file(path).violations if v.rule_id == SclLinter.GLOBAL_DB_FB_INSTANCE_RULE]
    assert [v.severity for v in found] == ["WARNING"] * 4
    assert "FB_1001_MachineMode" in found[0].message and "§4.11" in found[0].message


def _project(tmp_path: Path, db_text: str) -> Path:
    project = tmp_path / "DJ-2026-964_全局DB"
    (project / "02_PLC程序").mkdir(parents=True)
    (project / ".plc.json").write_text(json.dumps({"name": "DJ-2026-964", "version": "V1.0.0", "description": "x"}), encoding="utf-8")
    (project / "02_PLC程序" / "GlobalVars.db").write_text(db_text, encoding="utf-8")
    return project


def test_g06_the_checker_warns_with_file_and_line_and_keeps_the_verdict(tmp_path: Path) -> None:
    result = PlcChecker(str(tmp_path)).check_project(str(_project(tmp_path, _GLOBAL_DB)))
    item = next(i for i in result.items if i.item == SCL_GLOBAL_DB_FB_ITEM)
    assert item.status == "warn"
    assert [d.split(" ", 1)[0] for d in item.details] == [
        f"02_PLC程序/GlobalVars.db:{_at(_GLOBAL_DB, n)}" for n in ("fbMode", '"fbQuoted"', "arrFb", "fbAttr")
    ]
    scl = next(i for i in result.items if i.item == "SCL 代码规范")
    assert not any("FB 实例" in d for d in scl.details)  # 不重复记进 SCL 代码规范
    clean = _GLOBAL_DB.split("    fbMode")[0] + "END_VAR\n\nBEGIN\nEND_DATA_BLOCK\n"
    other = tmp_path / "clean"
    other.mkdir()
    result = PlcChecker(str(other)).check_project(str(_project(other, clean)))
    assert next(i for i in result.items if i.item == SCL_GLOBAL_DB_FB_ITEM).status == "pass"


def test_g07_a_new_template_project_has_none(tmp_path: Path) -> None:
    """005 真工程上的 9 处在 tests/plc/test_scl_linter.py（那份已登记读项目外的真文件）。"""
    project = tmp_path / "DJ-2026-964"
    TemplateService(str(TEMPLATES_DIR)).copy_template("plc-standard-project", str(project), {"project_id": "DJ-2026-964", "project_name": "全局DB"})
    item = next(i for i in PlcChecker(str(tmp_path)).check_project(str(project)).items if i.item == SCL_GLOBAL_DB_FB_ITEM)
    assert (item.status, item.details) == ("pass", [])
