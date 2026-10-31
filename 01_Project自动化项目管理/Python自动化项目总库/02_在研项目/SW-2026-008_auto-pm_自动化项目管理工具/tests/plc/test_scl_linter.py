"""SCL 静态规范检查器单元测试 (LSP-905 规范)"""

from __future__ import annotations

import pytest

from auto_pm.domain.plc.scl_linter import SclLinter


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


@pytest.mark.parametrize(
    "file_path",
    [
        "X" + _LEGACY_FILE.removeprefix("0100_PLC自动化/"),  # a name glued in front of the listed path is another folder
        "0100_PLC自动化/" + "X" + _LEGACY_FILE.removeprefix("0100_PLC自动化/"),
        _LEGACY_FILE + "/Other.scl",  # the listed path as a middle segment is not the listed file
        _LEGACY_FILE.replace("FC_LogMsg.scl", "FC_LogMsg2.scl"),  # a neighbour in the same folder
        _LEGACY_FILE.replace("FC_LogMsg.scl", "fc_logmsg.scl"),  # the match is case sensitive
        _LEGACY_FILE.replace(".scl", ".scl.bak"),
    ],
    ids=["glued-prefix", "glued-after-root", "middle-segment", "neighbour-file", "case", "other-suffix"],
)
def test_legacy_match_is_by_whole_path_segments_only(file_path: str) -> None:
    # TD-SW008-217: the list matches by path tail; a near miss must stay an ERROR, never ride on the warning
    assert _lower_bound_hits(_LEGACY_DECL, file_path) == ["ERROR"]


@pytest.mark.parametrize(
    "declaration",
    [
        "LogBuffer   : ARRAY[0..31] OF STRING[256];  x := 1;",  # something else on the same line
        "logbuffer   : ARRAY[0..31] OF STRING[256];",
        "LogBuffer   : ARRAY[0..31] OF STRING[255];",
        "LogBuffer   : ARRAY [0 .. 31] OF STRING[256];",  # only runs of blanks are squeezed; new blanks inside the brackets are an edit
    ],
    ids=["trailing-code", "name-case", "element-type", "spacing-in-brackets"],
)
def test_legacy_match_needs_the_declaration_text_to_be_the_same(declaration: str) -> None:
    assert _lower_bound_hits(declaration, _LEGACY_FILE) == ["ERROR"]


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


def _cross(body: str) -> list[str]:
    return [r for r in _region_rules(body) if r == "LSP-905-REGION-CROSS-BLOCK"]


def test_region_fully_inside_or_around_control_structures_is_fine() -> None:
    inside = "    IF s_iStep = 1 THEN\n        REGION 01_a\n            s_iStep := 2;\n        END_REGION\n    END_IF;"
    around = "    REGION 01_a\n        IF s_iStep = 1 THEN\n            s_iStep := 2;\n        END_IF;\n    END_REGION"
    case = (
        "    REGION 01_a\n        CASE s_iStep OF\n            1:\n                REGION 02_b\n"
        "                    s_iStep := 2;\n                END_REGION\n            ELSE\n                s_iStep := 0;\n"
        "        END_CASE;\n    END_REGION"
    )
    loops = "    REGION 01_a\n        FOR s_iStep := 1 TO 3 DO\n            s_iStep := s_iStep;\n        END_FOR;\n    END_REGION"
    for body in (inside, around, case, loops):
        assert _cross(body) == [], body


def test_region_end_inside_an_if_is_rejected() -> None:
    body = "    REGION 01_a\n        IF s_iStep = 1 THEN\n            s_iStep := 2;\n    END_REGION\n    END_IF;"
    assert _cross(body) == ["LSP-905-REGION-CROSS-BLOCK"]


def test_region_start_inside_an_if_that_ends_before_the_region_is_rejected() -> None:
    body = "    IF s_iStep = 1 THEN\n        REGION 01_a\n            s_iStep := 2;\n    END_IF;\n    END_REGION"
    assert _cross(body) == ["LSP-905-REGION-CROSS-BLOCK"]


def test_region_cut_through_a_case_is_rejected() -> None:
    body = (
        "    REGION 01_a\n        CASE s_iStep OF\n            1:\n                s_iStep := 2;\n"
        "            ELSE\n                s_iStep := 0;\n    END_REGION\n        END_CASE;"
    )
    assert _cross(body) == ["LSP-905-REGION-CROSS-BLOCK"]


def test_same_depth_but_different_structures_is_still_a_crossing() -> None:
    body = (
        "    IF s_iStep = 1 THEN\n        REGION 01_a\n            s_iStep := 2;\n    END_IF;\n"
        "    IF s_iStep = 3 THEN\n        END_REGION\n        s_iStep := 4;\n    END_IF;"
    )
    assert "LSP-905-REGION-CROSS-BLOCK" in _cross(body)


def test_keywords_in_region_names_comments_and_longer_words_do_not_count() -> None:
    body = (
        "    REGION 01_If_Case_For 处理 IF 和 CASE\n        // IF in a comment\n        s_iElsif := 1;\n"
        "    END_REGION"
    )
    assert _cross(body) == []


def test_keywords_inside_string_literals_do_not_count() -> None:
    body = (
        "    REGION 01_a\n        s_sMsg := 'IF x THEN';\n        s_sMsg := 'WAITING FOR PART';\n"
        "        s_sMsg := 'it''s a CASE OF WHILE';\n    END_REGION"
    )
    assert _cross(body) == []


def test_region_cut_through_for_and_while_is_rejected() -> None:
    for_body = "    REGION 01_a\n        FOR s_iStep := 1 TO 3 DO\n            s_iStep := 2;\n    END_REGION\n        END_FOR;"
    while_body = "    REGION 01_a\n        WHILE s_iStep < 3 DO\n            s_iStep := 2;\n    END_REGION\n        END_WHILE;"
    assert _cross(for_body) == ["LSP-905-REGION-CROSS-BLOCK"]
    assert _cross(while_body) == ["LSP-905-REGION-CROSS-BLOCK"]


def test_region_cut_through_repeat_is_rejected_and_whole_repeat_inside_is_fine() -> None:
    cut = "    REGION 01_a\n        REPEAT\n            s_iStep := 2;\n    END_REGION\n        UNTIL s_iStep > 3 END_REPEAT;"
    whole = "    REGION 01_a\n        REPEAT\n            s_iStep := 2;\n        UNTIL s_iStep > 3 END_REPEAT;\n    END_REGION"
    assert _cross(cut) == ["LSP-905-REGION-CROSS-BLOCK"]
    assert _cross(whole) == []


def test_lowercase_repeat_is_recognized_when_a_region_cuts_it() -> None:
    cut = "    region 01_a\n        repeat\n            s_iStep := 2;\n    end_region\n        until s_iStep > 3 end_repeat;"
    whole = "    region 01_a\n        repeat\n            s_iStep := 2;\n        until s_iStep > 3 end_repeat;\n    end_region"
    assert _cross(cut) == ["LSP-905-REGION-CROSS-BLOCK"]
    assert _cross(whole) == []


def test_lowercase_keywords_are_recognized_when_a_region_cuts_a_structure() -> None:
    body = "    region 01_a\n        if s_iStep = 1 then\n            s_iStep := 2;\n    end_region\n        end_if;"
    assert _cross(body) == ["LSP-905-REGION-CROSS-BLOCK"]


def test_one_crossing_is_reported_once_and_the_next_region_is_judged_on_its_own() -> None:
    cut = "    REGION 01_a\n        IF s_iStep = 1 THEN\n            s_iStep := 2;\n    END_REGION\n        END_IF;\n"
    good = "    REGION 02_b\n        IF s_iStep = 3 THEN\n            s_iStep := 4;\n        END_IF;\n    END_REGION"
    assert _cross(cut + good) == ["LSP-905-REGION-CROSS-BLOCK"]
    assert _cross(good + "\n" + cut) == ["LSP-905-REGION-CROSS-BLOCK"]


@pytest.mark.parametrize("name", ["01_A 取料; 放料", "01_A 令 s_x := 1"])
def test_region_name_with_statement_or_comment_symbols_is_rejected(name: str) -> None:
    body = f"    REGION {name}\n        s_iStep := 1;\n    END_REGION"
    assert _region_rules(body) == ["LSP-905-REGION-NAME-CHARS"]


def test_region_name_with_ordinary_punctuation_is_fine() -> None:
    body = "    REGION 06_SafeZone 安全区 (R-CONV-03): 自动 = 不在 S22 / S23, Z <= 待机点\n        s_iStep := 1;\n    END_REGION"
    assert _region_rules(body) == []


def _array_rules(body: str) -> list[tuple[int, str, str]]:
    text = f"FUNCTION_BLOCK FB_A\nVAR\n{body}\nEND_VAR\nBEGIN\nEND_FUNCTION_BLOCK\n"
    return [(v.line_number, v.rule_id, v.severity) for v in SclLinter.lint_text(text, "x.scl").violations if v.rule_id == "LSP-905-ARRAY-LOWER-BOUND"]


def test_array_bounds_split_over_lines_are_still_checked_and_reported_on_the_first_line() -> None:
    assert _array_rules("    s_arrA : ARRAY[\n        0..9\n    ] OF INT;") == [(3, "LSP-905-ARRAY-LOWER-BOUND", "ERROR")]
    assert _array_rules("    s_arrA : ARRAY[1..4,\n        0..2] OF INT;") == [(3, "LSP-905-ARRAY-LOWER-BOUND", "ERROR")]


def test_array_bounds_split_over_lines_with_lower_bound_one_are_fine() -> None:
    assert _array_rules("    s_arrA : ARRAY[\n        1..9\n    ] OF INT;") == []


def test_closed_array_on_the_line_is_checked_even_when_a_second_one_continues_on_the_next_line() -> None:
    assert _array_rules("    s_arrA : STRUCT a : ARRAY[0..3] OF INT; b : ARRAY[\n  1..2] OF INT; END_STRUCT;") == [(3, "LSP-905-ARRAY-LOWER-BOUND", "ERROR")]


def test_state_is_cleared_after_a_multiline_array_closes() -> None:
    body = "    s_arrA : ARRAY[\n        0..9\n    ] OF INT;\n    s_iX : INT;\n    s_arrB : ARRAY[0..2] OF INT;\n    s_arrC : ARRAY[1..2] OF INT;"
    # 只有第 3 行（多行数组起始行）和第 7 行（单行数组）各报一次；中间的普通变量和后面合法数组不受拼接状态影响
    assert _array_rules(body) == [(3, "LSP-905-ARRAY-LOWER-BOUND", "ERROR"), (7, "LSP-905-ARRAY-LOWER-BOUND", "ERROR")]


def test_array_bounds_split_over_three_or_more_lines_are_checked_and_comment_semicolons_do_not_cut_them() -> None:
    # 三行以上续行：下界在中间行，仍按起始行报；续行末尾的 // 注释里带分号不能把拼接截断
    three = "    s_arrA : ARRAY[\n        0..4,  // 先列 a; 再列 b\n        1..2\n    ] OF INT;"
    assert _array_rules(three) == [(3, "LSP-905-ARRAY-LOWER-BOUND", "ERROR")]
    four = "    s_arrA : ARRAY[\n        1..4,\n        1..2,\n        0..3\n    ] OF INT;"
    assert _array_rules(four) == [(3, "LSP-905-ARRAY-LOWER-BOUND", "ERROR")]
    assert _array_rules("    s_arrA : ARRAY[\n        1..4,  // a; b\n        1..2\n    ] OF INT;") == []


def test_every_legacy_array_entry_still_matches_a_real_declaration() -> None:
    """存量清单只许变短：条目对应的声明改成 1 起（或文件删了/改名）后必须同时从清单删掉，不留不再生效的死项（TD-236）。"""

    import re
    import subprocess
    from pathlib import Path

    from auto_pm.domain.plc.array_lower_bound_legacy import LEGACY_ARRAY_LOWER_BOUND

    here = Path(__file__).resolve()
    repo = next(p for p in here.parents if (p / "0100_PLC自动化").is_dir())
    names = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", "0100_PLC自动化"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split("\0")
    declarations: set[tuple[str, str]] = set()
    for name in names:
        if not name.endswith(".scl"):
            continue
        relative = name.removeprefix("0100_PLC自动化/")
        for line in (repo / name).read_text(encoding="utf-8", errors="replace").splitlines():
            declarations.add((relative, re.sub(r"\s+", " ", line.split("//")[0]).strip()))
    dead = sorted(entry for entry in LEGACY_ARRAY_LOWER_BOUND if entry not in declarations)
    assert dead == [], f"清单里有不再对应任何声明的死项，请删除：{dead}"
