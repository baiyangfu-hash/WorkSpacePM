"""方案级接口文档（FB 实例表、FC 调用表、交换区契约）与代码的存在性对照（M3-PRDLAYOUT 第 2 张）。

只警告、不失败；块的参数明细不在这里（见 ``test_doc_consistency``）。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.plc.scheme_doc import (
    ITEM_CONTRACT,
    ITEM_FB,
    ITEM_FC,
    find_scheme_int_doc,
    scheme_items,
)

NL = chr(10)

GLOBAL_DB = NL.join(
    [
        "DATA_BLOCK GlobalVars",
        "VAR",
        "    stExternal : ST_ExternalDevice;",
        "    fbStation1 : FB_1001_Station1;",
        "    fbAlarm : FB_2001_CommonAlarm;",
        "END_VAR",
        "END_DATA_BLOCK",
        "",
    ]
)
FB_STATION = NL.join(["FUNCTION_BLOCK FB_1001_Station1", "VAR_INPUT", "    i_bGo : BOOL;", "END_VAR", "BEGIN", "END_FUNCTION_BLOCK", ""])
FB_ALARM = NL.join(["FUNCTION_BLOCK FB_2001_CommonAlarm", "VAR_INPUT", "    i_bGo : BOOL;", "END_VAR", "BEGIN", "END_FUNCTION_BLOCK", ""])
FC_SCALE = NL.join(["FUNCTION FC_4001_ScaleAnalog : REAL", "VAR_INPUT", "    i_iRaw : INT;", "END_VAR", "BEGIN", "    FC_4001_ScaleAnalog := 0.0;", "END_FUNCTION", ""])
OB1_PLAIN = NL.join(["ORGANIZATION_BLOCK OB1", "VAR_TEMP", "    t_iX : INT;", "END_VAR", "BEGIN", "    // nothing is called here", "END_ORGANIZATION_BLOCK", ""])
OB1_CALLS_FC = NL.join(
    ["ORGANIZATION_BLOCK OB1", "VAR_TEMP", "    t_rY : REAL;", "END_VAR", "BEGIN", "    #t_rY := FC_4001_ScaleAnalog(i_iRaw := 100);", "END_ORGANIZATION_BLOCK", ""]
)


def _doc(fb_rows: list[str], fc_rows: list[str] | None = None, contract_rows: list[str] | None = None, fb_header: bool = True) -> str:
    lines = ["# 方案级接口文档（INT）", ""]
    if fb_header:
        lines += ["## 1. FB 实例表", "", "| FB 类型名 | 实例名 | 一句话用途 | 块级接口文档 |", "| :--- | :--- | :--- | :--- |", *fb_rows, ""]
    if fc_rows is not None:
        lines += ["## 2. FC 调用表", "", "| FC 名 | 一句话用途 | 被谁调用 | 块级接口文档 |", "| :--- | :--- | :--- | :--- |", *fc_rows, ""]
    if contract_rows is not None:
        lines += [
            "## 3. 跨系统交换区契约",
            "",
            "| 对象（方向） | 协议（开放列表） | 地址区间 | 总量 | 单位 | 本机写区 | 对方写区 | 本机侧承载的变量 | 负责的块 |",
            "| :--- | :--- | :--- | :---: | :---: | :--- | :--- | :--- | :--- |",
            *contract_rows,
            "",
        ]
    return NL.join(lines)


def _project(tmp_path: Path, doc: str, *, ob1: str = OB1_PLAIN, fc: bool = True) -> Path:
    project = tmp_path / "DJ-2026-777"
    st = project / "02_PLC程序" / "PLC_ST"
    (st / "00_程序方案").mkdir(parents=True)
    (st / "00_程序方案" / "接口文档_INT.md").write_text(doc, encoding="utf-8")
    (st / "00_全局数据").mkdir()
    (st / "00_全局数据" / "GlobalVars.db").write_text(GLOBAL_DB, encoding="utf-8")
    (st / "00_主程序").mkdir()
    (st / "00_主程序" / "OB1.scl").write_text(ob1, encoding="utf-8")
    (st / "01_工位1").mkdir()
    (st / "01_工位1" / "FB_1001_Station1.scl").write_text(FB_STATION, encoding="utf-8")
    (st / "05_报警").mkdir()
    (st / "05_报警" / "FB_2001_CommonAlarm.scl").write_text(FB_ALARM, encoding="utf-8")
    if fc:
        (st / "06_公共函数").mkdir()
        (st / "06_公共函数" / "FC_4001_ScaleAnalog.scl").write_text(FC_SCALE, encoding="utf-8")
    return project


FB_GOOD = [
    "| `FB_1001_Station1` | `GlobalVars.fbStation1` | 工位1 | `01_工位1/PRD/接口文档_IFC-FB1001.md` |",
    "| `FB_2001_CommonAlarm` | `GlobalVars.fbAlarm` | 公共报警 | `05_报警/PRD/接口文档_IFC-FB2001.md` |",
]
FC_LISTED = ["| `FC_4001_ScaleAnalog` | 模拟量换算 | 默认未被调用 | `06_公共函数/PRD/接口文档_IFC-FC4001.md` |"]


def _by_item(items: list[tuple[str, str, str]]) -> dict[str, tuple[str, str]]:
    return {name: (status, message) for name, status, message in items}


def test_a_document_that_matches_the_code_passes_and_nothing_is_a_failure(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED))
    items = _by_item(scheme_items(str(project)))
    assert items[ITEM_FB][0] == "pass" and "2 个 FB 实例" in items[ITEM_FB][1]
    assert items[ITEM_FC][0] == "pass"
    assert ITEM_CONTRACT not in items
    assert {status for status, _ in items.values()} == {"pass"}


def test_an_instance_in_the_code_that_the_table_does_not_list_is_named(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD[:1], FC_LISTED))
    status, message = _by_item(scheme_items(str(project)))[ITEM_FB]
    assert status == "warn" and "代码有、文档无" in message and "GlobalVars.fbAlarm" in message and "文档有、代码无" not in message


def test_an_instance_in_the_table_that_the_code_does_not_declare_is_named(tmp_path: Path) -> None:
    ghost = "| `FB_1001_Station1` | `GlobalVars.fbStation9` | 不存在 | `x.md` |"
    project = _project(tmp_path, _doc([*FB_GOOD, ghost], FC_LISTED))
    status, message = _by_item(scheme_items(str(project)))[ITEM_FB]
    assert status == "warn" and "文档有、代码无" in message and "GlobalVars.fbStation9" in message


def test_a_wrong_type_name_for_an_instance_is_a_difference_in_both_directions(tmp_path: Path) -> None:
    wrong = ["| `FB_2001_CommonAlarm` | `GlobalVars.fbStation1` | 工位1 | `x.md` |", FB_GOOD[1]]
    project = _project(tmp_path, _doc(wrong, FC_LISTED))
    status, message = _by_item(scheme_items(str(project)))[ITEM_FB]
    assert status == "warn" and "代码有、文档无" in message and "文档有、代码无" in message


def test_a_document_without_an_instance_table_is_warned_when_the_code_has_instances(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc([], FC_LISTED, fb_header=False))
    status, message = _by_item(scheme_items(str(project)))[ITEM_FB]
    assert status == "warn" and "没有 FB 实例表" in message


def test_a_called_fc_that_the_table_does_not_list_is_named(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD, []), ob1=OB1_CALLS_FC)
    status, message = _by_item(scheme_items(str(project)))[ITEM_FC]
    assert status == "warn" and "代码调用、表里未登记" in message and "FC_4001_ScaleAnalog" in message


def test_a_listed_fc_without_a_definition_is_named(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED), fc=False)
    status, message = _by_item(scheme_items(str(project)))[ITEM_FC]
    assert status == "warn" and "表里有、项目里没有定义" in message


def test_a_defined_but_never_called_fc_that_is_listed_is_not_a_difference(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED), ob1=OB1_PLAIN)
    assert _by_item(scheme_items(str(project)))[ITEM_FC][0] == "pass"


def test_a_call_inside_a_comment_is_not_a_call(tmp_path: Path) -> None:
    commented = NL.join(["ORGANIZATION_BLOCK OB1", "BEGIN", "    // FC_4001_ScaleAnalog(i_iRaw := 1);", "END_ORGANIZATION_BLOCK", ""])
    project = _project(tmp_path, _doc(FB_GOOD, []), ob1=commented)
    assert ITEM_FC not in _by_item(scheme_items(str(project)))


def test_the_contract_block_and_carried_variable_must_exist_but_placeholders_are_skipped(tmp_path: Path) -> None:
    good = [
        "| 上游 | 按项目填写 | `D0–D127` | 128 | word16 | 前 64 个 | 后 64 个 | `GlobalVars.stExternal.stUpstream` | `FB_1001_Station1` |",
        "| 机器人或其他 | 同上 | `Dxxx–Dyyy`（按项目填写） | 128 | word16 | 前 64 个 | 后 64 个 | 按项目填写 | 按项目填写 |",
    ]
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED, good))
    status, message = _by_item(scheme_items(str(project)))[ITEM_CONTRACT]
    assert status == "pass" and "2 个" in message


def test_a_missing_block_or_data_block_in_the_contract_is_named(tmp_path: Path) -> None:
    bad = [
        "| 上游 | PROFINET | `D0–D127` | 128 | word16 | 前 64 个 | 后 64 个 | `GlobalVars.stNoSuchField.x` | `FB_9999_Missing` |",
        "| 下游 | OPC UA | `D200–D327` | 128 | word16 | 前 64 个 | 后 64 个 | `NoSuchDb.stX` | `FB_1001_Station1` |",
    ]
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED, bad))
    status, message = _by_item(scheme_items(str(project)))[ITEM_CONTRACT]
    assert status == "warn"
    assert "FB_9999_Missing" in message and "stNoSuchField" in message and "NoSuchDb" in message


def test_no_document_means_no_items(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD))
    (project / "02_PLC程序" / "PLC_ST" / "00_程序方案" / "接口文档_INT.md").unlink()
    assert find_scheme_int_doc(str(project)) is None
    assert scheme_items(str(project)) == []


def test_the_program_scheme_directory_wins_over_a_root_prd_directory(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED))
    (project / "PRD").mkdir()
    (project / "PRD" / "接口文档_INT.md").write_text(_doc([]), encoding="utf-8")
    found = find_scheme_int_doc(str(project))
    assert found is not None and Path(found).parent.name == "00_程序方案"


def test_a_legacy_project_with_only_a_root_prd_document_is_still_compared(tmp_path: Path) -> None:
    project = _project(tmp_path, _doc(FB_GOOD, FC_LISTED))
    scheme = project / "02_PLC程序" / "PLC_ST" / "00_程序方案" / "接口文档_INT.md"
    (project / "PRD").mkdir()
    (project / "PRD" / "接口文档_INT.md").write_text(scheme.read_text(encoding="utf-8"), encoding="utf-8")
    scheme.unlink()
    found = find_scheme_int_doc(str(project))
    assert found is not None and Path(found).parent.name == "PRD"
    assert _by_item(scheme_items(str(project)))[ITEM_FB][0] == "pass"
