"""SCL 静态规范检查器单元测试 (LSP-905 规范)"""

from __future__ import annotations

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
        s_arrMesAlarmQueue : ARRAY[0..9] OF INT;
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
        s_aiMesAlarmQueue : ARRAY[0..9] OF INT;
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
