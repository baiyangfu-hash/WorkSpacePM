"""Real-file proofs for the PLC document/code consistency checks, auto-fill and confirm (V01B)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from auto_pm.domain.plc import doc_consistency as dc

FB_SCL = """FUNCTION_BLOCK FB_Pump
VAR_INPUT
    i_bStart : BOOL; // 启动命令
    i_aTemps : ARRAY[1..4] OF REAL; // 四路温度
END_VAR
VAR_OUTPUT
    q_bRunning : BOOL; // 运行中
END_VAR
VAR_IN_OUT
    io_stCfg : ST_PumpCfg; // 泵配置
END_VAR
VAR
    s_iStep : INT;
END_VAR
END_FUNCTION_BLOCK
"""
UDT_SCL = """TYPE ST_PumpCfg :
STRUCT
    i_rSpeed : REAL := 0.0; // 目标转速
    i_bEnable : BOOL; // 使能
END_STRUCT;
END_TYPE
"""
DB_SRC = """DATA_BLOCK GlobalVars
VAR
    stCfg : ST_PumpCfg; // 泵配置
    stLine : STRUCT // 产线
        i_bRun : BOOL; // 运行
    END_STRUCT;
END_VAR
END_DATA_BLOCK
"""
IFC_DOC = """# 接口文档 FB_Pump

## 1. 概述

泵控制。

## 2. VAR_INPUT

| 名称 | 类型 | 说明 |
|---|---|---|
| `i_bStart` | BOOL | 启动命令 |
| `i_aTemps[1..4]` | REAL[1..4] | 四路温度 |

## 3. VAR_OUTPUT

| 名称 | 类型 | 说明 |
|---|---|---|
| q_bRunning | BOOL | 运行中 |

## 4. VAR_IN_OUT

| 名称 | 类型 | 说明 |
|---|---|---|
| io_stCfg | ST_PumpCfg | 泵配置 |

## 5. 报警码

| 优先级 | 码 | 含义 |
|---|---|---|
| 1 | 101 | 过载 |
"""
VAR_DOC = """# 变量定义文档

## 变量表

### ST_PumpCfg（结构体）

| 名称 | 类型 | 说明 |
|---|---|---|
| i_rSpeed | REAL | 目标转速 |
| i_bEnable | BOOL | 使能 |

### GlobalVars（数据块）

| 名称 | 类型 | 说明 |
|---|---|---|
| stCfg | ST_PumpCfg | 泵配置 |
| stLine.i_bRun | BOOL | 运行 |
"""


def build(tmp_path: Path, *, ifc: str | None = IFC_DOC, var: str | None = VAR_DOC, scl: str = FB_SCL) -> Path:
    project = tmp_path / "DJ-TEST-001"
    module = project / "02_PLC程序" / "PLC_ST" / "01_泵"
    (module / "PRD").mkdir(parents=True)
    (project / "02_PLC程序" / "PLC_ST" / "00_全局数据").mkdir(parents=True)
    (module / "FB_Pump.scl").write_text(scl, encoding="utf-8")
    (module / "ST_PumpCfg.scl").write_text(UDT_SCL, encoding="utf-8")
    (project / "02_PLC程序" / "PLC_ST" / "00_全局数据" / "GlobalVars.db").write_text(DB_SRC, encoding="utf-8")
    if ifc is not None:
        (module / "PRD" / "接口文档_IFC-FB_Pump.md").write_text(ifc, encoding="utf-8")
    if var is not None:
        doc = project / "02_PLC程序" / "程序文档" / dc.VAR_DOC_NAME
        doc.parent.mkdir(parents=True)
        doc.write_text(var, encoding="utf-8")
    return project


def kinds(project: Path) -> list[str]:
    return sorted(f.kind for f in dc.analyze_project(str(project)).findings)


def ifc_path(project: Path) -> Path:
    return project / "02_PLC程序" / "PLC_ST" / "01_泵" / "PRD" / "接口文档_IFC-FB_Pump.md"


def var_path(project: Path) -> Path:
    return project / "02_PLC程序" / "程序文档" / dc.VAR_DOC_NAME


def code_digest(project: Path) -> dict[str, str]:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob("*") if p.suffix.lower() in {".scl", ".db"}}


def test_d01_source_parser_reads_interfaces_fields_inline_structs_and_trailing_comments() -> None:
    objects = {o.name: o for o in dc.parse_scl_text(FB_SCL + UDT_SCL + DB_SRC, "x.scl")}
    fb = objects["FB_Pump"]
    assert fb.kind == "FB"
    assert [(v.name, v.direction, v.comment) for v in fb.variables] == [
        ("i_bStart", "VAR_INPUT", "启动命令"), ("i_aTemps", "VAR_INPUT", "四路温度"),
        ("q_bRunning", "VAR_OUTPUT", "运行中"), ("io_stCfg", "VAR_IN_OUT", "泵配置")]
    assert fb.variables[1].type == "ARRAY[1..4] OF REAL"
    assert [v.name for v in objects["ST_PumpCfg"].variables] == ["i_rSpeed", "i_bEnable"]
    assert objects["ST_PumpCfg"].kind == "UDT" and objects["ST_PumpCfg"].variables[0].type == "REAL"
    assert [v.name for v in objects["GlobalVars"].variables] == ["stCfg", "stLine.i_bRun"]
    assert objects["GlobalVars"].kind == "DB"
    assert all(v.name != "s_iStep" for v in fb.variables)


def test_d02_parser_handles_block_comments_multi_names_ob_locals_and_unparsable_lines() -> None:
    text = """(* header
VAR_INPUT
   i_bFake : BOOL;
*)
ORGANIZATION_BLOCK OB1
VAR_TEMP
    t_iA, t_iB : INT; (* 两个临时量 *)
    broken line without colon
END_VAR
END_ORGANIZATION_BLOCK
"""
    (ob,) = dc.parse_scl_text(text, "ob.scl")
    assert ob.kind == "OB"
    assert [(v.name, v.comment) for v in ob.variables] == [("t_iA", "两个临时量"), ("t_iB", "两个临时量")]
    assert [number for number, _ in ob.unparsed] == [8]


def test_d03_document_parser_reads_directions_columns_markers_archives_and_skips_other_tables() -> None:
    lines = IFC_DOC.splitlines() + [
        "", "## 6. 方向列表", "", "| 变量名 | 数据类型 | 方向 | 说明 |", "|---|---|---|---|",
        f"| a | INT | 输出 | {dc.MARKER}说明 |", "", "## 附：代码中已不存在的旧条目", "",
        "| 名称 | 类型 | 说明 |", "|---|---|---|", "| old | INT | 旧 |"]
    _headings, tables = dc.parse_doc_lines(lines)
    by_heading = {t.heading: t for t in tables}
    assert "5. 报警码" not in by_heading
    assert by_heading["2. VAR_INPUT"].direction_hint == "VAR_INPUT"
    assert [r.name for r in by_heading["2. VAR_INPUT"].rows] == ["i_bStart", "i_aTemps"]
    direction_table = by_heading["6. 方向列表"]
    assert direction_table.rows[0].direction == "VAR_OUTPUT" and direction_table.rows[0].marked
    assert by_heading["附：代码中已不存在的旧条目"].archive is True


def test_d04_type_and_description_normalisation_ignore_notation_but_not_content() -> None:
    assert dc.normalize_type("ARRAY[1..4] OF BOOL") == dc.normalize_type("BOOL[1..4]")
    assert dc.normalize_type('"ST_X"') == dc.normalize_type("st_x")
    assert dc.normalize_type("STRING[32]") != dc.normalize_type("ARRAY[32] OF STRING")
    assert dc.normalize_type("BOOL") != dc.normalize_type("INT")
    assert dc.normalize_description(f"{dc.MARKER} 启动，命令  ") == dc.normalize_description("启动,命令")
    assert dc.normalize_description("启动命令") != dc.normalize_description("停止命令")


def test_d05_a_consistent_project_has_no_findings(tmp_path: Path) -> None:
    analysis = dc.analyze_project(str(build(tmp_path)))
    assert analysis.findings == []
    assert {r.obj.name: r.status for r in analysis.reports} == {
        "FB_Pump": "pass", "ST_PumpCfg": "pass", "GlobalVars": "pass"}
    assert dc.consistency_items(str(build(tmp_path / "again")))[0][1] == "pass"


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (("| `i_bStart` | BOOL | 启动命令 |", "| i_bStart | INT | 启动命令 |"), "type"),
        (("| `i_bStart` | BOOL | 启动命令 |", "| i_bStart | BOOL | 起动命令 |"), "comment"),
        (("| `i_bStart` | BOOL | 启动命令 |\n", ""), "code_not_in_doc"),
        (("| q_bRunning | BOOL | 运行中 |", "| q_bRunning | BOOL | 运行中 |\n| q_bGhost | BOOL | 幽灵 |"), "doc_not_in_code"),
        (("| q_bRunning | BOOL | 运行中 |", "| q_bRunning | BOOL | 运行中 |\n| q_bRunning | BOOL | 重复 |"), "doc_duplicate"),
    ],
)
def test_d06_every_kind_of_difference_fails_with_variable_and_location(
    tmp_path: Path, edit: tuple[str, str], expected: str
) -> None:
    project = build(tmp_path, ifc=IFC_DOC.replace(*edit))
    findings = [f for f in dc.analyze_project(str(project)).findings if f.kind == expected]
    assert findings and all(f.severity == "fail" for f in findings)
    assert findings[0].obj == "FB_Pump"
    rendered = findings[0].render()
    assert "FB_Pump." in rendered and (".md" in rendered or ".scl" in rendered)


def test_d07_direction_from_the_heading_is_checked_and_a_missing_direction_fails(tmp_path: Path) -> None:
    wrong = IFC_DOC.replace("## 3. VAR_OUTPUT", "## 3. VAR_INPUT")
    findings = [f for f in dc.analyze_project(str(build(tmp_path, ifc=wrong))).findings if f.kind == "direction"]
    assert [f.variable for f in findings] == ["q_bRunning"]
    assert "VAR_OUTPUT" in findings[0].message and "VAR_INPUT" in findings[0].message
    nodir = IFC_DOC.replace("## 3. VAR_OUTPUT", "## 3. 输出")
    other = dc.analyze_project(str(build(tmp_path / "x", ifc=nodir))).findings
    assert any(f.kind == "direction" and "无法确定方向" in f.message for f in other)


def test_d08_a_code_variable_without_a_comment_fails_even_when_the_document_has_one(tmp_path: Path) -> None:
    project = build(tmp_path, scl=FB_SCL.replace("q_bRunning : BOOL; // 运行中", "q_bRunning : BOOL;"))
    findings = [f for f in dc.analyze_project(str(project)).findings if f.kind == "no_comment"]
    assert [f.variable for f in findings] == ["q_bRunning"] and findings[0].severity == "fail"


def test_d09_missing_documents_warn_and_do_not_fail(tmp_path: Path) -> None:
    analysis = dc.analyze_project(str(build(tmp_path, ifc=None, var=None)))
    assert {f.kind for f in analysis.findings} == {"missing_doc"}
    assert all(f.severity == "warn" for f in analysis.findings)
    assert {r.doc_state for r in analysis.reports} == {"missing"}
    no_section = build(tmp_path / "b", var="# 变量定义文档\n\n## 变量表\n")
    assert {f.obj for f in dc.analyze_project(str(no_section)).findings if f.kind == "missing_doc"} == {
        "ST_PumpCfg", "GlobalVars"}
    prose = build(tmp_path / "c", ifc="# 接口文档\n\n只有叙述，没有表格。\n")
    assert [f.kind for f in dc.analyze_project(str(prose)).findings if f.obj == "FB_Pump"] == ["unparsable_doc"]


def test_d10_two_function_blocks_in_one_module_use_their_own_headed_tables(tmp_path: Path) -> None:
    project = build(tmp_path, ifc=IFC_DOC.replace("## 2. VAR_INPUT", "## FB_Pump 2. VAR_INPUT")
                    .replace("## 3. VAR_OUTPUT", "## FB_Pump 3. VAR_OUTPUT")
                    .replace("## 4. VAR_IN_OUT", "## FB_Pump 4. VAR_IN_OUT"))
    module = project / "02_PLC程序" / "PLC_ST" / "01_泵"
    (module / "FB_Fan.scl").write_text(
        "FUNCTION_BLOCK FB_Fan\nVAR_INPUT\n    i_bOn : BOOL; // 开\nEND_VAR\nEND_FUNCTION_BLOCK\n", encoding="utf-8")
    findings = dc.analyze_project(str(project)).findings
    assert {f.obj for f in findings} == {"FB_Fan"} and findings[0].kind == "missing_doc"


def test_d11_sync_creates_missing_documents_marks_rows_and_never_touches_the_code(tmp_path: Path) -> None:
    project = build(tmp_path, ifc=None, var=None)
    before = code_digest(project)

    result = dc.sync_project(str(project))

    assert len(result.created) == 2 and result.added_rows == 4 + 2 + 2
    assert code_digest(project) == before
    text = ifc_path(project).read_text(encoding="utf-8")
    assert f"| i_bStart | BOOL | {dc.MARKER}启动命令 |" in text and "## VAR_IN_OUT" in text
    analysis = dc.analyze_project(str(project))
    assert analysis.findings == [] and len(analysis.marked_rows) == 8
    again = dc.sync_project(str(project))
    assert again.written == [] and again.created == [] and again.added_rows == 0


def test_d12_sync_adds_only_missing_rows_and_keeps_human_text_byte_for_byte(tmp_path: Path) -> None:
    human = IFC_DOC.replace("| `i_bStart` | BOOL | 启动命令 |\n", "").replace("泵控制。", "泵控制，人写的说明。")
    project = build(tmp_path, ifc=human)
    dc.sync_project(str(project))
    new = ifc_path(project).read_text(encoding="utf-8")
    assert "泵控制，人写的说明。" in new and "| 优先级 | 码 | 含义 |" in new
    assert new.splitlines().count("| q_bRunning | BOOL | 运行中 |") == 1
    added = [line for line in new.splitlines() if dc.MARKER in line]
    assert added == [f"| i_bStart | BOOL | {dc.MARKER}启动命令 |"]
    kept = [line for line in human.splitlines() if line.strip()]
    assert all(line in new.splitlines() for line in kept)


def test_d13_apply_suggestions_rewrites_differences_and_archives_stale_rows_without_deleting_them(
    tmp_path: Path,
) -> None:
    messy = (IFC_DOC.replace("| `i_bStart` | BOOL | 启动命令 |", "| i_bStart | INT | 起动命令 |")
             .replace("| q_bRunning | BOOL | 运行中 |",
                      "| q_bRunning | BOOL | 运行中 |\n| q_bGhost | BOOL | 幽灵信号 |\n| io_stCfg | ST_PumpCfg | 放错方向 |"))
    project = build(tmp_path, ifc=messy)
    assert dc.sync_project(str(project)).applied == 0
    assert {"type", "comment", "doc_not_in_code"} <= {f.kind for f in dc.analyze_project(str(project)).findings}

    result = dc.sync_project(str(project), apply_suggestions=True)

    assert result.applied >= 3
    text = ifc_path(project).read_text(encoding="utf-8")
    assert "幽灵信号" in text and dc.ARCHIVE_HEADING in text
    assert dc.analyze_project(str(project)).findings == []
    assert dc.sync_project(str(project), apply_suggestions=True).applied == 0


def test_d17_apply_suggestions_keeps_human_text_when_the_code_has_no_comment_to_copy(tmp_path: Path) -> None:
    project = build(
        tmp_path,
        scl=FB_SCL.replace("i_bStart : BOOL; // 启动命令", "i_bStart : DINT;"),
        ifc=IFC_DOC.replace("| `i_bStart` | BOOL | 启动命令 |", "| i_bStart | BOOL | 人写的说明 |"),
    )
    dc.sync_project(str(project), apply_suggestions=True)
    row = next(line for line in ifc_path(project).read_text(encoding="utf-8").splitlines() if "i_bStart" in line)
    assert "DINT" in row and "人写的说明" in row and dc.MARKER in row


def test_d14_confirm_strips_the_marker_only_from_rows_that_now_match_the_code(tmp_path: Path) -> None:
    project = build(tmp_path, ifc=None, var=None)
    dc.sync_project(str(project))
    ifc = ifc_path(project)
    ifc.write_text(ifc.read_text(encoding="utf-8").replace(f"| q_bRunning | BOOL | {dc.MARKER}运行中 |",
                                                           f"| q_bRunning | INT | {dc.MARKER}运行中 |"), encoding="utf-8")

    result = dc.confirm_project(str(project))

    assert any("q_bRunning" in line for line in result.skipped)
    text = ifc.read_text(encoding="utf-8")
    assert f"| q_bRunning | INT | {dc.MARKER}运行中 |" in text
    assert "| i_bStart | BOOL | 启动命令 |" in text
    assert [x for x in text.splitlines() if x.startswith("|") and dc.MARKER in x] == [
        f"| q_bRunning | INT | {dc.MARKER}运行中 |"]
    assert len(dc.analyze_project(str(project)).marked_rows) == 1


def test_d15_consistency_items_summarise_each_object_and_report_unconfirmed_rows(tmp_path: Path) -> None:
    project = build(tmp_path, ifc=IFC_DOC.replace("| `i_bStart` | BOOL | 启动命令 |", f"| i_bStart | BOOL | {dc.MARKER}启动命令 |"))
    items = dc.consistency_items(str(project))
    by_name = {name: (status, message) for name, status, message in items}
    assert by_name["文档一致性 [功能块 FB_Pump]"][0] == "pass"
    assert by_name["文档待确认标记"][0] == "warn" and "1 行" in by_name["文档待确认标记"][1]
    broken = build(tmp_path / "b", ifc=IFC_DOC.replace("| `i_bStart` | BOOL | 启动命令 |", "| i_bStart | INT | 启动命令 |"))
    status, message = {n: (s, m) for n, s, m in dc.consistency_items(str(broken))}["文档一致性 [功能块 FB_Pump]"]
    assert status == "fail" and "类型不同 1" in message and "plc docs check" in message
    assert dc.consistency_items(str(tmp_path / "empty-dir-that-is-not-there")) == []


def test_d16_binary_db_files_and_archive_directories_are_ignored(tmp_path: Path) -> None:
    project = build(tmp_path)
    (project / "history.db").write_bytes(b"SQLite format 3\0" + bytes(range(256)))
    (project / "archive").mkdir()
    (project / "archive" / "FB_Old.scl").write_text(
        "FUNCTION_BLOCK FB_Old\nVAR_INPUT\n    i_bX : BOOL; // x\nEND_VAR\nEND_FUNCTION_BLOCK\n", encoding="utf-8")
    assert {r.obj.name for r in dc.analyze_project(str(project)).reports} == {"FB_Pump", "ST_PumpCfg", "GlobalVars"}


def two_fb_module(tmp_path: Path, *, second_doc: str | None) -> tuple[Path, Path]:
    """A module with two function blocks, each with its own interface document named after it."""

    project = tmp_path / "DJ-TEST-002"
    module = project / "02_PLC程序" / "PLC_ST" / "01_入料"
    (module / "PRD").mkdir(parents=True)
    for name in ("FB_1001_DualInfeed", "FB_1001_InfeedBatching"):
        source = "\n".join(
            [f"FUNCTION_BLOCK {name}", "VAR_INPUT", "    i_bStart : BOOL; // 启动", "END_VAR", "END_FUNCTION_BLOCK", ""])
        (module / f"{name}.scl").write_text(source, encoding="utf-8")
    table = "\n".join(["# 接口文档", "", "## VAR_INPUT", "", "| 名称 | 类型 | 说明 |", "|---|---|---|",
                       "| i_bStart | {kind} | 启动 |", ""])
    (module / "PRD" / "接口文档_IFC-FB1001-DualInfeed.md").write_text(table.format(kind="BOOL"), encoding="utf-8")
    if second_doc is not None:
        (module / "PRD" / "接口文档_IFC-FB1001-InfeedBatching.md").write_text(
            table.format(kind=second_doc), encoding="utf-8")
    return project, module / "PRD"


def test_d18_each_function_block_of_a_module_is_compared_with_the_document_named_after_it(tmp_path: Path) -> None:
    project, _prd = two_fb_module(tmp_path, second_doc="INT")
    findings = dc.analyze_project(str(project)).findings
    assert [(f.obj, f.kind, f.variable) for f in findings] == [("FB_1001_InfeedBatching", "type", "i_bStart")]
    assert "InfeedBatching.md" in findings[0].doc_loc


def test_d20_sync_in_a_shared_document_adds_rows_only_under_the_function_blocks_own_section(tmp_path: Path) -> None:
    fan_section_text = "## FB_Fan 2. VAR_INPUT\n\n| 名称 | 类型 | 说明 |\n|---|---|---|\n| i_bOn | BOOL | 开 |\n\n"
    shared = (IFC_DOC.replace("## 2. VAR_INPUT", fan_section_text + "## FB_Pump 2. VAR_INPUT")
              .replace("## 3. VAR_OUTPUT", "## FB_Pump 3. VAR_OUTPUT")
              .replace("## 4. VAR_IN_OUT", "## FB_Pump 4. VAR_IN_OUT"))
    project = build(tmp_path, ifc=shared)
    module = project / "02_PLC程序" / "PLC_ST" / "01_泵"
    (module / "FB_Fan.scl").write_text(
        "\n".join(["FUNCTION_BLOCK FB_Fan", "VAR_INPUT", "    i_bOn : BOOL; // 开", "    i_rSpeed : REAL; // 转速",
                   "END_VAR", "END_FUNCTION_BLOCK", ""]), encoding="utf-8")
    assert dc.analyze_project(str(project)).findings[0].kind == "code_not_in_doc"
    pump_rows = [line for line in shared.splitlines() if line.startswith("| `i_") or line.startswith("| q_")]

    dc.sync_project(str(project))

    lines = ifc_path(project).read_text(encoding="utf-8").splitlines()
    fan_section = lines.index("## FB_Fan 2. VAR_INPUT")
    pump_section = lines.index("## FB_Pump 2. VAR_INPUT")
    speed = next(i for i, line in enumerate(lines) if "i_rSpeed" in line)
    assert fan_section < speed < pump_section
    assert [line for line in lines[pump_section:] if line.startswith("| `i_") or line.startswith("| q_")] == pump_rows
    assert dc.analyze_project(str(project)).findings == []


def test_d19_sync_never_writes_one_function_blocks_rows_into_a_siblings_document(tmp_path: Path) -> None:
    project, prd = two_fb_module(tmp_path, second_doc=None)
    first = prd / "接口文档_IFC-FB1001-DualInfeed.md"
    before = first.read_bytes()
    assert [(f.obj, f.kind) for f in dc.analyze_project(str(project)).findings] == [
        ("FB_1001_InfeedBatching", "missing_doc")]

    result = dc.sync_project(str(project))

    assert first.read_bytes() == before
    assert [Path(p).name for p in result.created] == ["接口文档_IFC-FB_1001_InfeedBatching.md"]
    assert dc.analyze_project(str(project)).findings == []

