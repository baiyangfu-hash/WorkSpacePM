"""SCL 静态规范检查器单元测试 (LSP-905 规范)"""

from __future__ import annotations

import pytest
from auto_pm.plc.scl_linter import SclLinter


def test_scl_linter_detects_valid_clean_code() -> None:
    valid_scl = """
    FUNCTION_BLOCK FB_1001_Test
    VAR_INPUT
        i_bStart : BOOL;
        i_rSpeed : REAL;
    END_VAR
    VAR_OUTPUT
        o_bRunning : BOOL;
    END_VAR
    VAR
        s_iStep : INT;
        s_arrMesAlarmQueue : ARRAY[1..10] OF INT;
    END_VAR
    BEGIN
        CASE s_iStep OF
            0:
                s_iStep := 10;
            ELSE
                s_iStep := 0;
        END_CASE;
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(valid_scl, file_path="test_clean.scl")
    assert report.is_clean
    assert report.errors_count == 0
    assert report.total_violations == 0


def test_scl_linter_detects_invalid_array_type_identifier() -> None:
    bad_array_scl = """
    FUNCTION_BLOCK FB_1001_ArrayPrefix
    VAR
        s_iStep : INT;
        s_aiMesAlarmQueue : ARRAY[1..10] OF INT;
    END_VAR
    BEGIN
        CASE s_iStep OF
            0:
                ;
            ELSE
                ;
        END_CASE;
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(bad_array_scl, file_path="bad_array_prefix.scl")
    assert any(v.rule_id == "LSP-905-VAR-ARRAY-TYPE-PREFIX" for v in report.violations)


def test_scl_linter_detects_missing_prefixes() -> None:
    bad_prefix_scl = """
    FUNCTION_BLOCK FB_1001_BadPrefix
    VAR_INPUT
        bStart : BOOL; // 缺少 i_
    END_VAR
    VAR_OUTPUT
        RunningState : BOOL; // 缺少 o_
    END_VAR
    BEGIN
        CASE s_Step OF
            0:
                s_Step := 1;
            ELSE
                s_Step := 0;
        END_CASE;
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(bad_prefix_scl, file_path="bad_prefix.scl")
    assert not report.is_clean
    assert report.errors_count >= 2

    rule_ids = {v.rule_id for v in report.violations}
    assert "LSP-905-VAR-INPUT-PREFIX" in rule_ids
    assert "LSP-905-VAR-OUTPUT-PREFIX" in rule_ids


def test_scl_linter_detects_goto_syntax() -> None:
    goto_scl = """
    FUNCTION_BLOCK FB_1001_Goto
    VAR_INPUT
        i_bStart : BOOL;
    END_VAR
    BEGIN
        IF i_bStart THEN
            GOTO Step10;
        END_IF;
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(goto_scl, file_path="goto.scl")
    assert not report.is_clean
    assert any(v.rule_id == "LSP-905-SYNTAX-GOTO" for v in report.violations)


def test_scl_linter_detects_missing_case_else() -> None:
    no_else_scl = """
    FUNCTION_BLOCK FB_1001_NoElse
    VAR
        s_iStep : INT;
    END_VAR
    BEGIN
        CASE s_iStep OF
            0:
                s_iStep := 10;
            10:
                s_iStep := 20;
        END_CASE;
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(no_else_scl, file_path="no_else.scl")
    assert not report.is_clean
    assert any(v.rule_id == "LSP-905-CASE-NO-ELSE" for v in report.violations)


def test_scl_linter_detects_time_literal() -> None:
    time_lit_scl = """
    FUNCTION_BLOCK FB_1001_TimeLit
    VAR
        fb_tAction : FB_TON;
        s_bDone : BOOL;
        s_diElapsed : DINT;
    END_VAR
    BEGIN
        fb_tAction(IN := TRUE, PT := T#500ms, Q => s_bDone, ET => s_diElapsed);
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(time_lit_scl, file_path="time_lit.scl")
    assert not report.is_clean
    assert any(v.rule_id == "LSP-906-TIMER-TIME-LITERAL" for v in report.violations)


def test_scl_linter_detects_chinese_punctuation() -> None:
    chinese_punct_scl = """
    FUNCTION_BLOCK FB_1001_ChinesePunct
    VAR_INPUT
        i_bStart : BOOL； // 中文分号
    END_VAR
    BEGIN
        IF i_bStart THEN
            i_bStart := FALSE;
        END_IF;
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(chinese_punct_scl, file_path="chinese_punct.scl")
    assert not report.is_clean
    assert any(v.rule_id == "LSP-905-CHINESE-PUNCTUATION" for v in report.violations)


def test_scl_linter_detects_missing_timer_q() -> None:
    missing_q_scl = """
    FUNCTION_BLOCK FB_1001_MissingQ
    VAR
        fb_tAction : FB_TON;
        s_diElapsed : DINT;
    END_VAR
    BEGIN
        fb_tAction(IN := TRUE, PT := 500, Q => , ET => s_diElapsed);
    END_FUNCTION_BLOCK
    """
    report = SclLinter.lint_text(missing_q_scl, file_path="missing_q.scl")
    assert not report.is_clean
    assert any(v.rule_id == "LSP-906-TIMER-MISSING-Q" for v in report.violations)


def _array_scl(declaration: str) -> str:
    return f"""
    FUNCTION_BLOCK FB_1001_ArrayBound
    VAR
        {declaration}
    END_VAR
    BEGIN
        ;
    END_FUNCTION_BLOCK
    """


@pytest.mark.parametrize(
    "declaration",
    [
        "s_arrQueue : ARRAY[0..9] OF INT;",
        "s_arrQueue : ARRAY [ 0 .. 9 ] OF INT;",
        "s_arrQueue : array[2..9] of INT;",
        "s_arrQueue : ARRAY[-1..8] OF INT;",
        "s_arrGrid : ARRAY[1..3, 0..4] OF INT;",
        "s_arrGrid : ARRAY[0..3, 0..4] OF INT;",
    ],
)
def test_scl_linter_rejects_array_lower_bound_other_than_one(declaration: str) -> None:
    report = SclLinter.lint_text(_array_scl(declaration), file_path="array_bound.scl")

    hits = [v for v in report.violations if v.rule_id == "LSP-905-ARRAY-LOWER-BOUND"]
    assert hits and all(v.severity == "ERROR" for v in hits)
    assert not report.is_clean


@pytest.mark.parametrize(
    "declaration",
    [
        "s_arrQueue : ARRAY[1..10] OF INT;",
        "s_arrGrid : ARRAY[1..3, 1..4] OF INT;",
        "s_arrQueue : ARRAY[1..C_SIZE] OF INT;",
        "s_arrQueue : ARRAY[C_LOW..C_HIGH] OF INT;",
        "s_iCount : INT;  // 注释里写 ARRAY[0..9] 不算",
        "s_iCount : INT;  (* ARRAY[0..9] *)",
    ],
)
def test_scl_linter_accepts_array_lower_bound_one_or_symbolic(declaration: str) -> None:
    report = SclLinter.lint_text(_array_scl(declaration), file_path="array_bound.scl")

    hits = [v for v in report.violations if v.rule_id == "LSP-905-ARRAY-LOWER-BOUND"]
    assert hits == []


_LEGACY_FILE = "0100_PLC自动化/01_SharedLibraries/SysLib/log/FC_LogMsg.scl"
_LEGACY_DECL = "LogBuffer   : ARRAY[0..31] OF STRING[256];"


def _lower_bound_hits(declaration: str, file_path: str) -> list[str]:
    text = f"FUNCTION_BLOCK FB_1003_Legacy\nVAR\n    {declaration}\nEND_VAR\nBEGIN\nEND_FUNCTION_BLOCK\n"
    report = SclLinter.lint_text(text, file_path=file_path)
    return [v.severity for v in report.violations if v.rule_id == "LSP-905-ARRAY-LOWER-BOUND"]


def test_listed_legacy_declaration_is_only_a_warning() -> None:
    assert _lower_bound_hits(_LEGACY_DECL, _LEGACY_FILE) == ["WARNING"]
    assert _lower_bound_hits(_LEGACY_DECL + "  // 注释变了也还是同一条", "C:\\repo\\" + _LEGACY_FILE.replace("/", "\\")) == [
        "WARNING"
    ]


def test_new_or_changed_declarations_stay_errors() -> None:
    assert _lower_bound_hits(_LEGACY_DECL, "0100_PLC自动化/DJ-9999/02_PLC程序/PLC_ST/New.scl") == ["ERROR"]
    assert _lower_bound_hits("LogBuffer   : ARRAY[0..63] OF STRING[256];", _LEGACY_FILE) == ["ERROR"]
    assert _lower_bound_hits(_LEGACY_DECL, "") == ["ERROR"]


def test_repository_plc_sources_have_no_new_array_lower_bound_errors() -> None:
    """全仓库已入库的 PLC 源码：下界非 1 的只允许是清单里的存量（WARNING），清单外的新增一律 ERROR。"""

    import subprocess
    from pathlib import Path

    here = Path(__file__).resolve()
    repo = next(p for p in here.parents if (p / "0100_PLC自动化").is_dir())
    names = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", "0100_PLC自动化"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split("\0")
    errors: list[str] = []
    warnings = 0
    for name in names:
        if not name.endswith(".scl"):
            continue
        report = SclLinter.lint_text((repo / name).read_text(encoding="utf-8", errors="replace"), file_path=name)
        for v in report.violations:
            if v.rule_id == "LSP-905-ARRAY-LOWER-BOUND":
                if v.severity == "ERROR":
                    errors.append(f"{name}:{v.line_number}")
                else:
                    warnings += 1
    assert errors == []
    assert warnings > 0  # 清单不是摆设：存量还在时它们确实被识别为 WARNING


_REGION_FB = """
FUNCTION_BLOCK FB_1002_Region
VAR
    s_iStep : INT;
END_VAR
BEGIN
{body}
END_FUNCTION_BLOCK
"""


def _region_rules(body: str) -> list[str]:
    report = SclLinter.lint_text(_REGION_FB.format(body=body), file_path="region.scl")
    return [v.rule_id for v in report.violations]


def test_region_end_region_form_is_clean() -> None:
    body = "    REGION 01_Input 输入映射\n        s_iStep := 1;\n    END_REGION"
    assert _region_rules(body) == []


def test_hash_region_is_rejected_as_unsupported_by_the_lsp() -> None:
    body = "    #REGION 01_Input\n        s_iStep := 1;\n    #END_REGION"
    rules = _region_rules(body)
    assert rules.count("LSP-905-REGION-HASH") == 2
    for variant in ("#region 01_Input", "# REGION 01_Input", "#ENDREGION", "#END_REGION"):
        assert "LSP-905-REGION-HASH" in _region_rules(f"    {variant}")


def test_hash_prefixed_variable_that_only_starts_with_region_is_not_a_region() -> None:
    assert _region_rules("    #region_x := 1;") == []


def test_unbalanced_region_is_rejected() -> None:
    assert _region_rules("    REGION 01_A\n        s_iStep := 1;") == ["LSP-905-REGION-UNBALANCED"]
    assert _region_rules("    s_iStep := 1;\n    END_REGION") == ["LSP-905-REGION-UNBALANCED"]


def test_region_marker_in_comment_is_not_code() -> None:
    assert _region_rules("    // #REGION old style\n    (* #END_REGION *)\n    s_iStep := 1;") == []


def test_905_long_region_example_passes_the_linter() -> None:
    """The spec's own example must stay clean; read it from the spec so the doc cannot rot."""

    import re
    from pathlib import Path

    here = Path(__file__).resolve()
    spec = next(
        (parent / "00_Obsidian_Base全局规范文件仓库" / "03_PLC自动化域" / "905_SCL编程规范_LSP.md")
        for parent in here.parents
        if (parent / "00_Obsidian_Base全局规范文件仓库" / "03_PLC自动化域" / "905_SCL编程规范_LSP.md").is_file()
    )
    text = spec.read_text(encoding="utf-8")
    section = text[text.index("### 6.3 折叠区段 REGION") :]
    blocks = re.findall(r"```scl\n(.*?)```", section, re.S)
    assert blocks
    report = SclLinter.lint_text(blocks[0], file_path="905_example.scl")
    assert report.violations == []
    example = blocks[0]
    assert example.count("REGION ") >= 6 and "ARRAY[1..4]" in example
    # 定时器写法与 LSP-905 §2 / LSP-906 §1 一致：FB_TON、fb_ 前缀、调用集中在 FB 顶部第一个区段里
    assert ": FB_TON;" in example and ": TON;" not in example
    assert "s_fb" not in example
    first_region_end = example.index("END_REGION")
    assert example.index("fb_tStepTimer(") < first_region_end
    assert example.count("fb_tStepTimer(") == 1
    assert "#REGION" not in blocks[0].upper()


def test_lowercase_region_opener_is_paired_and_hash_inside_block_comment_is_ignored() -> None:
    assert _region_rules("    region 01_a\n        s_iStep := 1;\n    END_REGION") == []
    assert _region_rules("    region 01_a\n        s_iStep := 1;") == ["LSP-905-REGION-UNBALANCED"]
    assert _region_rules("    (*\n    #REGION old\n    #END_REGION\n    *)\n    s_iStep := 1;") == []
