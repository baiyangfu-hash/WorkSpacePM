"""TD-SW008-316（D-50）：块里读自己的输出引脚（TIA 报“参数无法初始化”），检查器第一阶段一律只报警告。

真工程上的命中（SysLib 的 FB_TaktGenerator、FB_CTUD、FB_CTU、FB_CTD 等，000 的 FB_ValveControl）是真命中，
只列清单、不在本批修；升成失败另立技术债。
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.domain.plc.checker import SCL_OUTPUT_READBACK_ITEM, PlcChecker
from auto_pm.domain.plc.scl_linter import SclLinter

_FB = """FUNCTION_BLOCK "FB_9106_Out"
   VAR_INPUT
      i_bIn : Bool;
   END_VAR
   VAR_OUTPUT
      q_bOut : Bool;
      o_iCnt : Int;
      o_stSts : Struct
         a : Bool;
      END_STRUCT;
   END_VAR
   VAR
      fb_Ton : TON_TIME;
      s_bOut : Bool;
   END_VAR

BEGIN
{body}
END_FUNCTION_BLOCK
"""


def _hits(body: str) -> list[int]:
    text = _FB.format(body=body)
    report = SclLinter.lint_text(text, file_path="out.scl")
    return [v.line_number for v in report.violations if v.rule_id == SclLinter.OUTPUT_READBACK_RULE]


def _at(body: str, needle: str) -> int:
    return _FB.format(body=body).splitlines().index(needle) + 1


def test_r01_writing_outputs_is_not_reading_them() -> None:
    body = (
        "   #q_bOut := #i_bIn;\n"
        "   #o_iCnt := 1;\n"
        "   #o_stSts.a := TRUE;\n"
        "   #fb_Ton(IN := #i_bIn, PT := T#1S, Q => #q_bOut);\n"
        "   #s_bOut := NOT #s_bOut;\n"
        "   #q_bOut := #s_bOut;"
    )
    assert _hits(body) == []


def test_r02_toggling_an_output_reads_it() -> None:
    body = "   #q_bOut := NOT #q_bOut;"
    assert _hits(body) == [_at(body, body)]


def test_r03_conditions_inputs_and_members_on_the_right_are_reads() -> None:
    body = "   IF #q_bOut THEN\n      ;\n   END_IF;\n   #fb_Ton(IN := #o_stSts.a, PT := T#1S);\n   #o_iCnt := #o_iCnt + 1;"
    assert _hits(body) == [
        _at(body, "   IF #q_bOut THEN"),
        _at(body, "   #fb_Ton(IN := #o_stSts.a, PT := T#1S);"),
        _at(body, "   #o_iCnt := #o_iCnt + 1;"),
    ]


def test_r04_it_is_only_a_warning() -> None:
    report = SclLinter.lint_text(_FB.format(body="   #q_bOut := NOT #q_bOut;"), file_path="out.scl")
    found = [v for v in report.violations if v.rule_id == SclLinter.OUTPUT_READBACK_RULE]
    assert [v.severity for v in found] == ["WARNING"]


def _project(tmp_path: Path, body: str) -> Path:
    project = tmp_path / "DJ-2026-963_输出"
    (project / "02_PLC程序").mkdir(parents=True)
    (project / ".plc.json").write_text(json.dumps({"name": "DJ-2026-963", "version": "V1.0.0", "description": "x"}), encoding="utf-8")
    (project / "02_PLC程序" / "FB_9106_Out.scl").write_text(_FB.format(body=body), encoding="utf-8")
    return project


def test_r05_the_checker_warns_with_file_and_line_and_keeps_the_verdict(tmp_path: Path) -> None:
    body = "   #q_bOut := NOT #q_bOut;"
    result = PlcChecker(str(tmp_path)).check_project(str(_project(tmp_path, body)))
    item = next(i for i in result.items if i.item == SCL_OUTPUT_READBACK_ITEM)
    assert item.status == "warn"
    assert item.details == [f"02_PLC程序/FB_9106_Out.scl:{_at(body, body)} " + item.details[0].split(" ", 1)[1]]
    assert "q_bOut" in item.details[0]
    scl = next(i for i in result.items if i.item == "SCL 代码规范")
    assert not any("输出引脚" in d for d in scl.details)  # 不重复记进 SCL 代码规范


def test_r06_the_checker_item_passes_without_readback(tmp_path: Path) -> None:
    result = PlcChecker(str(tmp_path)).check_project(str(_project(tmp_path, "   #q_bOut := #i_bIn;")))
    assert next(i for i in result.items if i.item == SCL_OUTPUT_READBACK_ITEM).status == "pass"


def _repo_plc_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "0100_PLC自动化").is_dir():
            return parent / "0100_PLC自动化"
    return None


def test_r07_the_known_real_hits_are_in_syslib_and_000_only() -> None:
    """真工程命中清单（逐条标过“真命中”）：只在 SysLib 和 000，005、009、011 里没有。新增命中要人看过再改这里。"""
    root = _repo_plc_root()
    if root is None:
        import pytest

        pytest.skip("这份克隆里没有 0100_PLC自动化")
    files = {
        str(path.relative_to(root)).replace("\\", "/"): sum(
            1 for v in SclLinter.lint_file(path).violations if v.rule_id == SclLinter.OUTPUT_READBACK_RULE
        )
        for path in sorted(root.rglob("*.scl"))
    }
    assert {k: v for k, v in files.items() if v} == {
        "01_SharedLibraries/SysLib/counter/FB_CTD.scl": 3,
        "01_SharedLibraries/SysLib/counter/FB_CTU.scl": 3,
        "01_SharedLibraries/SysLib/counter/FB_CTUD.scl": 6,
        "01_SharedLibraries/SysLib/pulse/FB_TaktGenerator.scl": 10,
        "01_SharedLibraries/SysLib/timer/FB_TON.scl": 1,
        "01_SharedLibraries/SysLib/timer/FB_TONR.scl": 1,
        "DJ-2026-000/FB100/FB_ValveControl.scl": 4,
    }
