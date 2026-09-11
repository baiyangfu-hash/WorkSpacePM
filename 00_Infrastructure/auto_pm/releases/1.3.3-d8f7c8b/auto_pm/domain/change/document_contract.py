"""CHG Markdown document structure contract.

This module is the project-local source of truth for headings consumed by the
generator, parser, editor, and closing gate.  It deliberately describes the
rendered document only; the global Obsidian template remains outside this
change's authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChgSection:
    """One required CHG document section and its compatible heading pattern."""

    number: str
    name: str
    levels: tuple[int, ...] = (2, 3)

    def heading_pattern(self) -> str:
        """Return a multiline regex accepting canonical and legacy headings."""
        alternatives = "|".join("#" * level for level in sorted(self.levels, reverse=True))
        return rf"^(?:{alternatives})\s*§?\s*{re.escape(self.number)}\b"


REQUIRED_SECTION_3_SUBSECTIONS: tuple[str, ...] = (
    "3.0",
    "3.1",
    "3.2",
    "3.3",
    "3.4",
)

CLOSURE_REQUIRED_SECTIONS: tuple[ChgSection, ...] = (
    ChgSection("5", "§5 变更前后"),
    ChgSection("6.1", "§6.1 五大约束影响"),
    ChgSection("6.2", "§6.2 跨领域影响"),
    ChgSection("6.3", "§6.3 变更传播链"),
    ChgSection("7", "§7 实施计划"),
    ChgSection("8.1", "§8.1 审批流程"),
    ChgSection("8.2", "§8.2 审批结论"),
    ChgSection("9", "§9 变更实施记录"),
    ChgSection("10.1", "§10.1 验证项清单"),
    ChgSection("10.2", "§10.2 跨领域联动验证"),
    ChgSection("10.3", "§10.3 验证结论"),
    ChgSection("11", "§11 版本详细变更说明"),
    ChgSection("12", "§12 附录"),
)


def subsection_pattern(number: str) -> str:
    """Return the parser pattern for a level-three subsection."""
    return rf"###\s*§?\s*{re.escape(number)}\s*[.、：:]*(.*?)(?=\n###|\n##|\Z)"


def heading_pattern(number: str, *, levels: tuple[int, ...] = (2, 3)) -> str:
    """Return a compatible heading pattern for a known CHG section number."""
    return ChgSection(number, number, levels).heading_pattern()


def assert_generated_document_contract(content: str) -> None:
    """Fail immediately when the generator drifts from the closing contract."""
    missing = [
        section.name
        for section in CLOSURE_REQUIRED_SECTIONS
        if not re.search(section.heading_pattern(), content, re.MULTILINE)
    ]
    if missing:
        raise ValueError("生成的 CHG 文档缺少契约章节: " + ", ".join(missing))
