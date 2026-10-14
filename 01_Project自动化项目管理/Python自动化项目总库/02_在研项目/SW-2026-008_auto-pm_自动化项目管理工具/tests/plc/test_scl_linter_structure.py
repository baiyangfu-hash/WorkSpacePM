"""SCL 结构完整性规则（LSP-905-STRUCT-*，M3-PLUGIN）：插件命令行对空文件与乱码单文件报 0 诊断，由这里补。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.plc.scl_linter import SclLinter

GOOD_FB = """FUNCTION_BLOCK FB_1001_Demo
VAR_INPUT
    i_bStart : BOOL;
END_VAR
VAR
    s_iStep : INT;
END_VAR
BEGIN
    s_iStep := 0;
END_FUNCTION_BLOCK
"""


def _rules(text: str) -> list[str]:
    return [v.rule_id for v in SclLinter.lint_text(text).violations if v.rule_id.startswith("LSP-905-STRUCT")]


def test_st01_a_normal_function_block_has_no_structure_violation() -> None:
    assert _rules(GOOD_FB) == []


@pytest.mark.parametrize("text", ["", "   \n\n", "THIS IS NOT SCL )))\n", "// only a comment\n(* and a block comment *)\n", "IF \"FirstScan\" THEN\n    ;\nEND_IF;\n"], ids=["empty", "blank", "garbage", "comments-only", "bare-statements"])
def test_st02_a_file_without_any_block_or_type_declaration_is_an_error(text: str) -> None:
    report = SclLinter.lint_text(text)
    assert _rules(text) == ["LSP-905-STRUCT-NO-BLOCK"]
    assert report.errors_count >= 1 and not report.is_clean


def test_st03_a_truncated_block_is_an_error() -> None:
    truncated = GOOD_FB.replace("END_FUNCTION_BLOCK\n", "")
    assert _rules(truncated) == ["LSP-905-STRUCT-UNCLOSED"]


def test_st04_organization_block_data_block_and_type_files_are_recognised() -> None:
    assert _rules("ORGANIZATION_BLOCK OB1\nBEGIN\nEND_ORGANIZATION_BLOCK\n") == []
    assert _rules("DATA_BLOCK GlobalVars\nVAR\n    a : INT;\nEND_VAR\nEND_DATA_BLOCK\n") == []
    assert _rules("TYPE ST_X :\nSTRUCT\n    a : INT;\nEND_STRUCT;\nEND_TYPE\n") == []
    assert _rules("TYPE ST_X :\nSTRUCT\n    a : INT;\nEND_STRUCT;\n") == ["LSP-905-STRUCT-UNCLOSED"]


def test_st05_keywords_in_comments_do_not_count() -> None:
    text = "// FUNCTION_BLOCK FB_commented\n(* ORGANIZATION_BLOCK OB9 *)\n" + GOOD_FB
    assert _rules(text) == []


def test_st06_a_function_is_not_confused_with_a_function_block() -> None:
    text = "FUNCTION FC_Add : INT\nVAR_INPUT\n    i_iA : INT;\nEND_VAR\nBEGIN\n    FC_Add := i_iA;\nEND_FUNCTION\n"
    assert _rules(text) == []


def test_st07_the_shipped_template_and_shared_library_sources_have_no_structure_violation() -> None:
    root = Path(__file__).resolve().parents[2] / "templates" / "plc-standard-project" / "template"
    files = list(root.rglob("*.scl"))
    assert files, "the template ships static .scl files"
    for path in files:
        assert _rules(path.read_text(encoding="utf-8")) == [], path.name
