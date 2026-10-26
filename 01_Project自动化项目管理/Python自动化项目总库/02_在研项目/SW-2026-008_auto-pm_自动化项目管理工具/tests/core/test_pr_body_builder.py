"""``pr open`` 填出来的说明：用 pr-gate 和 safety-gate 自己的解析函数读，而不是自己再解析一遍。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from auto_pm.application.core.pr_body_builder import build_body, read_card_fields, signature_lines

REPO = Path(__file__).resolve().parents[2].parents[3]
sys.path.insert(0, str(REPO / "reviews" / "tools"))

import pr_scope_check as gate  # noqa: E402
import safety_zone_check as safety  # noqa: E402

TEMPLATE = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8", errors="replace")
CARD = "plans/cards/CARD-9.md"
SCOPE = ["a/b/one.py", "a/b/tests", "docs/two.md"]
COMMITS = [
    (
        "a" * 40,
        "fix(TD-100): x [CHG-SCPT-2026-500]\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_x",
    )
]
CARD_TEXT = (
    "# CARD-9｜演示\n\n> 关联TD：`TD-SW008-100`、TD-SW008-046\n> WBS：SW-2026-008/M3-9\n"
    "> 安全回路：否\n\n## 2. 单一目标与完成定义\n\n快照记录模式。\n\n## 3. 其他\n"
)


def body(**over: object) -> str:
    fields = read_card_fields(CARD_TEXT, "CARD-9")
    kwargs: dict[str, object] = {
        "task_card": CARD,
        "fields": fields,
        "scope_paths": SCOPE,
        "safety_circuit": "否",
        "chg_numbers": ["CHG-SCPT-2026-500"],
        "commits": COMMITS,
        "evidence": ["pytest => 0"],
        "sweep": None,
        "tds": fields.tds,
        "head_sha": "b" * 40,
    }
    kwargs.update(over)
    return build_body(**kwargs)  # type: ignore[arg-type]


def test_b01_pr_gate_reads_the_task_card_line() -> None:
    assert gate.card_path_from_body(body()) == CARD


def test_b02_without_the_card_line_pr_gate_still_reads_every_full_path() -> None:
    without = "\n".join(line for line in body().splitlines() if not line.startswith("任务卡:"))
    assert gate.declared_scope(without) == SCOPE


@pytest.mark.parametrize("answer", ["是", "否"])
def test_b03_safety_gate_reads_the_declaration(answer: str) -> None:
    assert safety.plan_declaration(body(safety_circuit=answer)) == (answer, [])


def test_b04_headings_are_template_headings_in_template_order() -> None:
    template = [line[3:].strip() for line in TEMPLATE.splitlines() if line.startswith("## ")]
    filled = [line[3:].strip() for line in body().splitlines() if line.startswith("## ")]
    assert filled == template


def test_b05_no_signature_trailers_means_no_signature_section() -> None:
    assert "## 署名" not in body(commits=[("a" * 40, "fix: x [CHG-SCPT-2026-500]")])


def test_b06_no_line_of_the_body_can_be_read_as_a_safety_signature() -> None:
    assert not any(safety.SIGN_LINE.match(line) for line in body().splitlines())


def test_b07_card_fields_are_read_from_header_lines() -> None:
    fields = read_card_fields(CARD_TEXT, "x")
    assert fields.tds == ("TD-SW008-100", "TD-SW008-046")
    assert fields.wbs == "SW-2026-008/M3-9"
    assert fields.safety == "否"
    assert fields.goal == "快照记录模式。"
    assert fields.title == "CARD-9｜演示"


def test_b08_a_card_without_those_lines_gives_none_not_a_guess() -> None:
    fields = read_card_fields("# T\n\n正文提到 TD-SW008-999 但不是头部行\n", "x")
    assert (fields.tds, fields.wbs, fields.safety) == ((), "", None)
    text = body(fields=fields, tds=())
    assert "## 关联 TD\n\n无" in text and "## 建议回写\n\n无" in text


def test_b09_a_safety_value_with_a_parenthesis_is_not_accepted() -> None:
    assert read_card_fields("> 安全回路：否（待定）\n", "x").safety is None


def test_b10_suggested_writeback_names_every_td_and_the_head() -> None:
    text = body()
    assert "TD-SW008-100 已偿还，证据 提交号 bbbbbbbb" in text
    assert "TD-SW008-046 已偿还" in text


def test_b11_signature_lines_come_from_the_newest_commit_that_has_them() -> None:
    commits = [("1" * 40, "x\n\nCo-Authored-By: A"), ("2" * 40, "y")]
    assert signature_lines([m for _s, m in commits]) == ["Co-Authored-By: A"]


def test_b12_sweep_text_is_written_when_given() -> None:
    assert "根因X" in body(sweep="根因X")
