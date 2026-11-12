"""TD-SW008-560 方案②（D-295）：不依赖西门子插件的轻量语法层——控制结构闭合、本块 #变量已声明。

没有插件时，没闭合的 IF、没声明的变量以前一条也查不出（plc check 退出码 0）。这一层只管这两类；类型错不查，归插件。
误报口径：仓库里全部真实 .scl（0100_PLC自动化 下 90 个，含 SysLib、005、009、011、000、_archive）一条也不许报。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.domain.plc.checker import SCL_SYNTAX_ITEM, PlcChecker
from auto_pm.domain.plc.scl_linter import SclLinter

pytestmark = pytest.mark.external_reads  # D-200: l12 reads real files outside the project

_FB = """FUNCTION_BLOCK "FB_9102_Lite"
VERSION : 0.1
   VAR_INPUT
      i_bStart : Bool;
   END_VAR
   VAR_OUTPUT
      o_bDone : Bool;
   END_VAR
   VAR
      s_iStep : Int;
      s_arrBuf : Array[1..4] of Int;
      st_Data : Struct
         a : Int;
      END_STRUCT;
   END_VAR
   VAR_TEMP
      t_i : Int;
   END_VAR

BEGIN
{body}
END_FUNCTION_BLOCK
"""

_CLEAN = """   IF #i_bStart THEN
      #s_iStep := 16#0A + DINT_TO_INT(DINT#1);
   ELSIF #s_iStep > 3 THEN
      #o_bDone := TRUE;
   END_IF;
   CASE #s_iStep OF
      1: #st_Data.a := 1;
   ELSE
      ;
   END_CASE;
   FOR #t_i := 1 TO 4 DO
      #s_arrBuf[#t_i] := 0;  // #NotAVariable 在注释里
   END_FOR;
   WHILE FALSE DO
      ;
   END_WHILE;
   REGION 步骤 #1 说明
      "GlobalDB".x := '#notvar IF';
   END_REGION"""


def _rules(body: str) -> list[tuple[str, int]]:
    report = SclLinter.lint_text(_FB.format(body=body), file_path="lite.scl")
    return [(v.rule_id, v.line_number) for v in report.violations if v.rule_id in SclLinter.SYNTAX_RULES]


def _line(body: str, needle: str) -> int:
    return _FB.format(body=body).splitlines().index(needle) + 1


def test_l01_a_clean_block_has_no_hits() -> None:
    assert _rules(_CLEAN) == []


def test_l02_an_if_without_end_if_is_unclosed() -> None:
    body = _CLEAN.replace("   END_IF;\n", "", 1)
    assert _rules(body) == [("SCL-SYN-UNCLOSED", _line(body, "   IF #i_bStart THEN"))]


@pytest.mark.parametrize("opener", ["CASE #s_iStep OF", "FOR #t_i := 1 TO 4 DO", "WHILE FALSE DO"])
def test_l03_case_for_while_without_end_are_unclosed(opener: str) -> None:
    closer = {"CASE": "   END_CASE;\n", "FOR": "   END_FOR;\n", "WHILE": "   END_WHILE;\n"}[opener.split()[0]]
    body = _CLEAN.replace(closer, "", 1)
    assert [r for r, _ in _rules(body)] == ["SCL-SYN-UNCLOSED"]


def test_l04_an_extra_end_if_is_reported() -> None:
    body = _CLEAN + "\n   END_IF;"
    assert [r for r, _ in _rules(body)] == ["SCL-SYN-UNCLOSED"]


def test_l05_crossed_control_structures_name_the_skipped_one() -> None:
    body = "   FOR #t_i := 1 TO 4 DO\n      IF #i_bStart THEN\n         ;\n   END_FOR;\n   END_IF;"
    hits = _rules(body)
    assert ("SCL-SYN-UNCLOSED", _line(body, "      IF #i_bStart THEN")) in hits


def test_l06_an_undeclared_local_is_reported_once_per_line() -> None:
    body = _CLEAN + "\n   #xNotDeclared := #xNotDeclared OR TRUE;"
    assert _rules(body) == [("SCL-SYN-UNDECLARED", _line(body, "   #xNotDeclared := #xNotDeclared OR TRUE;"))]


def test_l07_declarations_with_attributes_quotes_and_lists_count() -> None:
    fb = _FB.replace(
        "      s_iStep : Int;\n",
        '      s_iStep : Int;\n      s_bA {{ ExternalAccessible := \'False\'}} : Bool;\n      "s_bQuoted" : Bool;\n      s_x1, s_x2 : Int;\n',
    )
    report = SclLinter.lint_text(fb.format(body="   #s_bA := #s_bQuoted;\n   #s_x1 := #s_x2;"), file_path="lite.scl")
    assert [v for v in report.violations if v.rule_id in SclLinter.SYNTAX_RULES] == []


def test_l08_function_return_by_name_and_locals_of_each_block_are_separate() -> None:
    text = (
        'FUNCTION "FC_9103_Ret" : Int\n   VAR_INPUT\n      i_a : Int;\n   END_VAR\nBEGIN\n   #FC_9103_Ret := #i_a;\nEND_FUNCTION\n\n'
        'FUNCTION "FC_9104_Other" : Int\n   VAR_INPUT\n      i_b : Int;\n   END_VAR\nBEGIN\n   FC_9104_Other := #i_a;\nEND_FUNCTION\n'
    )
    hits = [(v.rule_id, v.line_number) for v in SclLinter.lint_text(text, file_path="fc.scl").violations if v.rule_id in SclLinter.SYNTAX_RULES]
    assert hits == [("SCL-SYN-UNDECLARED", 14)]  # i_a 只在第一个块里声明


def test_l09_db_and_udt_files_are_not_checked(tmp_path: Path) -> None:
    db = tmp_path / "DB_9105.db"
    db.write_text('DATA_BLOCK "DB_9105"\nBEGIN\n   IF := 1;\nEND_DATA_BLOCK\n', encoding="utf-8")
    assert [v for v in SclLinter.lint_file(db).violations if v.rule_id in SclLinter.SYNTAX_RULES] == []


def _project(tmp_path: Path, body: str) -> Path:
    project = tmp_path / "DJ-2026-962_轻量"
    (project / "02_PLC程序").mkdir(parents=True)
    (project / ".plc.json").write_text(json.dumps({"name": "DJ-2026-962", "version": "V1.0.0", "description": "x"}), encoding="utf-8")
    (project / "02_PLC程序" / "FB_9102_Lite.scl").write_text(_FB.format(body=body), encoding="utf-8")
    return project


def test_l10_the_checker_item_fails_and_lists_file_and_line(tmp_path: Path) -> None:
    body = _CLEAN.replace("   END_IF;\n", "", 1) + "\n   #xNotDeclared := TRUE;"
    result = PlcChecker(str(tmp_path)).check_project(str(_project(tmp_path, body)))
    item = next(i for i in result.items if i.item == SCL_SYNTAX_ITEM)
    assert item.status == "fail" and not result.all_pass
    assert [d.split(" ", 1)[0] for d in item.details] == [
        f"02_PLC程序/FB_9102_Lite.scl:{_line(body, '   IF #i_bStart THEN')}",
        f"02_PLC程序/FB_9102_Lite.scl:{_line(body, '   #xNotDeclared := TRUE;')}",
    ]
    scl = next(i for i in result.items if i.item == "SCL 代码规范")
    assert not any("没闭合" in d or "没有声明" in d for d in scl.details)  # 不重复记进 SCL 代码规范


def test_l11_the_checker_item_passes_on_clean_code(tmp_path: Path) -> None:
    result = PlcChecker(str(tmp_path)).check_project(str(_project(tmp_path, _CLEAN)))
    assert next(i for i in result.items if i.item == SCL_SYNTAX_ITEM).status == "pass"


def _repo_plc_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "0100_PLC自动化"
        if candidate.is_dir():
            return candidate
    return None


def test_l12_no_false_positive_on_any_real_scl_in_the_repository() -> None:
    root = _repo_plc_root()
    if root is None:
        pytest.skip("这份克隆里没有 0100_PLC自动化")
    files = sorted(root.rglob("*.scl"))
    assert len(files) >= 80  # 防止目录挪走后这条空跑
    hits = [
        f"{path.relative_to(root)}:{v.line_number} {v.rule_id}"
        for path in files
        for v in SclLinter.lint_file(path).violations
        if v.rule_id in SclLinter.SYNTAX_RULES
    ]
    assert hits == []
