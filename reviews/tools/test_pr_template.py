"""PR 模板和检查要的字段保持一致：模板里的行首关键词必须能被 pr-gate 和 safety-gate 读出来。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import pr_scope_check as gate
import safety_zone_check as safety

TEMPLATE = TOOLS.parents[1] / ".github" / "pull_request_template.md"
REQUIRED_HEADINGS = ("署名", "做了什么", "可改范围", "安全回路", "证据", "同类排查")
SUGGESTED_HEADINGS = ("关联 TD", "WBS", "建议回写")


def text() -> str:
    return TEMPLATE.read_text(encoding="utf-8", errors="replace")


def headings() -> list[str]:
    return [line[3:].strip() for line in text().splitlines() if line.startswith("## ")]


def test_t01_the_template_exists_where_github_looks_for_it() -> None:
    assert TEMPLATE.is_file()


def section(name: str) -> str:
    """标题恰好是 ``## <name>`` 的那一节正文（到下一个二级标题为止）。"""
    lines = text().splitlines()
    start = lines.index(f"## {name}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1 : end])


def test_t02_every_section_is_present_with_its_required_or_suggested_label() -> None:
    required = ("做了什么", "可改范围", "安全回路", "证据", "同类排查")
    for name in required:
        assert "必填" in section(name), name
    for name in SUGGESTED_HEADINGS:
        assert "建议填" in section(name), name
    assert section("署名")


def test_t03_the_scope_heading_is_exactly_the_one_pr_gate_reads() -> None:
    """标题带任何后缀都会让 pr-gate 读不到范围，所以模板里的标题必须原样可用，不用人改。"""
    assert "## 可改范围" in text().splitlines()
    assert gate.SCOPE_HEADER.match("## 可改范围")


def test_t04_the_scope_placeholders_are_list_items_pr_gate_reads_and_stop_at_the_next_heading() -> None:
    assert gate.declared_scope(text()) == ["<完整路径", "<完整路径"]


def test_t05_the_template_never_contains_a_line_that_parses_as_a_task_card() -> None:
    """未填的模板若有顶格的“任务卡: …”行，会把没有任务卡的 PR 强制按卡判范围。"""
    assert gate.card_path_from_body(text()) is None


def test_t06_the_safety_line_is_read_and_rejected_until_filled() -> None:
    value, problems = safety.plan_declaration(text())
    assert value is None and problems, "未改的模板必须被 safety-gate 判不通过"
    for answer in ("是", "否"):
        filled = re.sub(r"^安全回路:.*$", f"安全回路: {answer}", text(), flags=re.MULTILINE)
        assert safety.plan_declaration(filled) == (answer, [])


def test_t07_the_safety_signature_goes_in_a_comment_not_the_body() -> None:
    template = text()
    assert "安全签字写在评论里，不写在正文" in template
    # 正文里不能有一行真的会被当成签字行的写法；签字行只认评论
    assert not any(safety.SIGN_LINE.match(line) for line in template.splitlines())


def test_t08_the_attribution_block_comes_first_with_two_lines() -> None:
    lines = text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## 署名"))
    assert all(not line.startswith("## ") for line in lines[:start]) and start < 8
    placeholders = [line for line in lines[start + 1 :] if line.startswith("<署名行")]
    assert len(placeholders) == 2
