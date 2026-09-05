"""Unit tests for PLC SCL LSP-905 rule checker (CHG-SCPT-2026-162)."""

from auto_pm.domain.plc.scl_linter import SclLinter


def test_goto_syntax_violation():
    scl_code = """
FUNCTION_BLOCK FB_Test
VAR
    s_nStep : INT;
END_VAR
    IF s_nStep = 0 THEN
        GOTO ErrorLabel;
    END_IF;
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(scl_code)
    rule_ids = [v.rule_id for v in report.violations]
    assert any("GOTO" in rid for rid in rule_ids)


def test_repeat_syntax_violation():
    scl_code = """
FUNCTION_BLOCK FB_Test
VAR
    s_nCount : INT;
END_VAR
    REPEAT
        s_nCount := s_nCount + 1;
    UNTIL s_nCount > 10
    END_REPEAT;
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(scl_code)
    rule_ids = [v.rule_id for v in report.violations]
    assert any("REPEAT" in rid for rid in rule_ids)


def test_pointer_syntax_violation():
    scl_code = """
FUNCTION_BLOCK FB_Test
VAR
    s_pData : REF_TO INT;
END_VAR
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(scl_code)
    rule_ids = [v.rule_id for v in report.violations]
    assert any("POINTER" in rid for rid in rule_ids)


def test_time_literal_violation():
    scl_code = """
FUNCTION_BLOCK FB_Test
VAR
    s_fbTimer : FB_TON;
END_VAR
    s_fbTimer(IN := TRUE, PT := T#5s);
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(scl_code)
    rule_ids = [v.rule_id for v in report.violations]
    assert any("TIME" in rid or "TIMER" in rid for rid in rule_ids)


def test_case_no_else_violation():
    scl_code = """
FUNCTION_BLOCK FB_StateMachine
VAR
    s_nStep : INT;
END_VAR
    CASE s_nStep OF
        0:
            s_nStep := 10;
        10:
            s_nStep := 20;
    END_CASE;
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(scl_code)
    rule_ids = [v.rule_id for v in report.violations]
    assert any("CASE" in rid or "ELSE" in rid for rid in rule_ids)


def test_var_prefix_violations():
    scl_code = """
FUNCTION_BLOCK FB_PrefixTest
VAR_INPUT
    badInputName : BOOL;
END_VAR
VAR_OUTPUT
    badOutputName : BOOL;
END_VAR
VAR
    badStaticName : DINT;
END_VAR
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(scl_code)
    rule_ids = [v.rule_id for v in report.violations]
    assert any("PREFIX" in rid or "VAR" in rid for rid in rule_ids)


def test_clean_scl_passes():
    clean_code = """
FUNCTION_BLOCK FB_PerfectBlock
VAR_INPUT
    i_bStart : BOOL;
    i_nTargetSpeed : DINT;
END_VAR
VAR_OUTPUT
    q_bRunning : BOOL;
    q_bDone : BOOL;
END_VAR
VAR
    s_fbTimer : FB_TON;
    s_nStep : INT;
END_VAR
    // Timers unconditional call
    s_fbTimer(IN := i_bStart, PT := 5000);

    CASE s_nStep OF
        0:
            IF i_bStart THEN
                s_nStep := 10;
            END_IF;
        10:
            q_bRunning := TRUE;
            IF s_fbTimer.Q THEN
                s_nStep := 20;
            END_IF;
        20:
            q_bDone := TRUE;
        ELSE
            s_nStep := 0;
    END_CASE;
END_FUNCTION_BLOCK
"""
    report = SclLinter.lint_text(clean_code)
    assert report.is_clean is True
    assert report.errors_count == 0
