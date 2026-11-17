"""plc check 对导入 TIA 的工程按用户实测补的规矩（CHG-SCPT-2026-704）。

用户 2026-11-16 在 TIA V19 实测：TON_TIME、R_TRIG 在 FB 静态区做多重实例能编译，SysLib 的 FB_TON 一类 TIA 里没有；
外部源文件导入时 OB 里同一 FB 调用几次就要事先建几个背景 DB；块名要带项目标记、不能叫 Main。规范已回写
（LSP-903、LSP-905 §4.9/§4.11、CHG-SPEC-2026-023），这里把它们变成 plc check 的失败项。
用户 2026-11-17：“为什么一次不做完？”——规范改了检查没跟着改，漏一处 FB_TON 也查不出来。

基线是驾驶舱 PLC 标准模板按三工位生成的工程（用户实测过的结构），每条用例在它上面改一处，看对应的项变红。
只在临时目录里生成和改文件。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.plc.checker import (
    SCL_GLOBAL_DB_FB_ITEM,
    TIA_BLOCK_NAME_ITEM,
    TIA_DB_FOLDER_ITEM,
    TIA_OB_DB_ITEM,
    TIA_WRAPPER_ITEM,
    PlcChecker,
)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
TIA_ITEMS = (
    TIA_WRAPPER_ITEM,
    TIA_OB_DB_ITEM,
    TIA_DB_FOLDER_ITEM,
    TIA_BLOCK_NAME_ITEM,
    SCL_GLOBAL_DB_FB_ITEM,
)
BOM = b"\xef\xbb\xbf"


@pytest.fixture(scope="module")
def template_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("tia_rules") / "DJ-2026-901"
    TemplateService(str(TEMPLATES_DIR)).copy_template(
        "plc-standard-project",
        str(dest),
        {
            "project_id": "DJ-2026-901",
            "project_name": "TIA规矩",
            "station_instances": ["Station1", "Station2", "Station3"],
        },
    )
    return dest


@pytest.fixture
def project(template_project: Path, tmp_path: Path) -> Path:
    copy = tmp_path / "DJ-2026-901"
    shutil.copytree(template_project, copy)
    return copy


def _plc_st(project: Path) -> Path:
    return project / "02_PLC程序" / "PLC_ST"


def _status(project: Path) -> dict[str, tuple[str, list[str]]]:
    result = PlcChecker(str(project.parent)).check_project(str(project))
    return {i.item: (i.status, list(i.details or [])) for i in result.items if i.item in TIA_ITEMS}


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_bytes().decode("utf-8")
    assert old in text, (path.name, old)
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def test_the_tested_three_station_template_passes_every_tia_rule(project: Path) -> None:
    status = _status(project)
    assert {item: s for item, (s, _) in status.items()} == dict.fromkeys(TIA_ITEMS, "pass")


def test_a_syslib_wrapper_type_fails(project: Path) -> None:
    _edit(
        _plc_st(project) / "02_工位_动作机构" / "FB_1001_Station1.scl",
        "fb_tProcess     : TON_TIME;",
        "fb_tProcess     : FB_TON;",
    )
    status, details = _status(project)[TIA_WRAPPER_ITEM]
    assert status == "fail"
    assert any("FB_1001_Station1.scl" in d and "FB_TON" in d for d in details)


def test_an_ob_calling_the_same_background_db_twice_fails(project: Path) -> None:
    ob = _plc_st(project) / "00_主程序" / "OB123.scl"
    _edit(ob, '"DB_1001_Station2_DJ2026901"(', '"DB_1001_Station1_DJ2026901"(')
    status, details = _status(project)[TIA_OB_DB_ITEM]
    assert status == "fail"
    assert any("两次" in d for d in details)


def test_an_ob_call_without_its_background_db_file_fails(project: Path) -> None:
    (_plc_st(project) / "02_工位_动作机构" / "DB_1001_Station3.scl").unlink()
    status, details = _status(project)[TIA_OB_DB_ITEM]
    assert status == "fail"
    assert any("DB_1001_Station3_DJ2026901" in d and "没有对应的背景 DB" in d for d in details)


def test_a_background_db_away_from_its_fb_fails(project: Path) -> None:
    src = _plc_st(project) / "02_工位_动作机构" / "DB_1001_Station2.scl"
    src.rename(_plc_st(project) / "05_公共报警" / "DB_1001_Station2.scl")
    status, details = _status(project)[TIA_DB_FOLDER_ITEM]
    assert status == "fail"
    assert any("DB_1001_Station2_DJ2026901" in d for d in details)


def test_an_untagged_fb_name_and_an_ob_named_main_fail(project: Path) -> None:
    _edit(
        _plc_st(project) / "06_公共函数" / "FC_4001_ScaleAnalog.scl",
        "FUNCTION FC_4001_ScaleAnalog",
        "FUNCTION FC_4001_ScaleAnalog",
    )
    ob = _plc_st(project) / "00_主程序" / "OB123.scl"
    _edit(ob, '"DJ2026901_Main"', '"Main"')
    fb = _plc_st(project) / "05_公共报警" / "FB_2001_CommonAlarm_AllStation.scl"
    _edit(
        fb,
        "FUNCTION_BLOCK FB_2001_CommonAlarm_AllStation_DJ2026901",
        "FUNCTION_BLOCK FB_2001_CommonAlarm_AllStation",
    )
    status, details = _status(project)[TIA_BLOCK_NAME_ITEM]
    assert status == "fail"
    assert any("Main" in d and "撞名" in d for d in details)
    assert any("FB_2001_CommonAlarm_AllStation " in d and "项目标记" in d for d in details)
    assert not any("FC_4001" in d for d in details), (
        "FC 不要求带项目标记（模板的 FC_4001 已实测过）"
    )


def test_a_fb_instance_in_the_global_db_fails_in_a_tia_project(project: Path) -> None:
    gv = _plc_st(project) / "00_全局数据" / "GlobalVars.db"
    _edit(gv, "BEGIN", "    fbBad : FB_1001_Station1_DJ2026901;\nBEGIN")
    status, details = _status(project)[SCL_GLOBAL_DB_FB_ITEM]
    assert status == "fail"
    assert details


def test_a_project_without_bom_is_not_a_tia_project(project: Path) -> None:
    for path in _plc_st(project).rglob("*"):
        if path.suffix in {".scl", ".db"}:
            data = path.read_bytes()
            path.write_bytes(data[len(BOM) :] if data.startswith(BOM) else data)
    _edit(
        _plc_st(project) / "02_工位_动作机构" / "FB_1001_Station1.scl",
        "fb_tProcess     : TON_TIME;",
        "fb_tProcess     : FB_TON;",
    )
    status = _status(project)
    for item in (TIA_WRAPPER_ITEM, TIA_OB_DB_ITEM, TIA_DB_FOLDER_ITEM, TIA_BLOCK_NAME_ITEM):
        assert item not in status, f"不带 BOM 的老工程不该出 {item}"


def test_a_background_db_with_a_non_retain_header_still_counts(project: Path) -> None:
    """审计 #855：DATA_BLOCK 和 FB 名之间有 NON_RETAIN 行时，FB 名照样认得出，不误报缺背景 DB。"""
    db = _plc_st(project) / "02_工位_动作机构" / "DB_1001_Station1.scl"
    text = db.read_bytes().decode("utf-8")
    head, sep, rest = text.partition('DATA_BLOCK "DB_1001_Station1_DJ2026901"')
    assert sep
    db.write_bytes((head + sep + "\nNON_RETAIN" + rest).encode("utf-8"))
    status = _status(project)
    assert status[TIA_OB_DB_ITEM][0] == "pass", status[TIA_OB_DB_ITEM]
    assert status[TIA_DB_FOLDER_ITEM][0] == "pass", status[TIA_DB_FOLDER_ITEM]
    # 认出的必须是真正的 FB：把这个 DB 挪走，文件夹一项要红，并且点名它的 FB
    db.rename(_plc_st(project) / "05_公共报警" / db.name)
    status, details = _status(project)[TIA_DB_FOLDER_ITEM]
    assert status == "fail"
    assert any("FB_1001_Station1_DJ2026901" in d for d in details), details


def test_an_ob_calling_a_function_needs_no_background_db(project: Path) -> None:
    """审计 #855：OB 里调 FC 不需要背景 DB，不误报。"""
    ob = _plc_st(project) / "00_主程序" / "OB123.scl"
    _edit(
        ob,
        "END_ORGANIZATION_BLOCK",
        '    "FC_4001_ScaleAnalog"(i_iRaw := 0);\nEND_ORGANIZATION_BLOCK',
    )
    assert _status(project)[TIA_OB_DB_ITEM][0] == "pass"


def test_a_wrapper_type_inside_a_block_comment_is_not_reported(project: Path) -> None:
    fb = _plc_st(project) / "02_工位_动作机构" / "FB_1001_Station1.scl"
    _edit(
        fb,
        "    fb_tProcess     : TON_TIME;",
        "    (* 旧写法:\n    fb_tOld : FB_TON;\n    *)\n    fb_tProcess     : TON_TIME;",
    )
    assert _status(project)[TIA_WRAPPER_ITEM][0] == "pass"
