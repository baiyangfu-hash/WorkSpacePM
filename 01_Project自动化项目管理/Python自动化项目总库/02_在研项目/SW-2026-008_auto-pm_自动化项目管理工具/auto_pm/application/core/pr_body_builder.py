"""Fill ``.github/pull_request_template.md`` for ``main.py pr open``.

The section headings and the line-leading keywords (``任务卡:``, ``安全回路:``, ``- <path>``) are the ones
``reviews/tools/pr_scope_check.py`` (pr-gate) and ``reviews/tools/safety_zone_check.py`` (safety-gate) read;
``reviews/tools/test_pr_template.py`` keeps the template and those readers in step, and
``tests/core/test_pr_body_builder.py`` runs the readers on what this module writes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

TD_ID = re.compile(r"TD-(?:SW008-)?\d{2,4}", re.ASCII)
_HEADER_LINE = re.compile(r"^>\s*(关联\s*TD|WBS|安全回路)\s*[:：]\s*(.*)$")
_SAFETY_VALUE = re.compile(r"^`?(是|否)`?$")
_TRAILER = re.compile(r"^(Co-Authored-By|Claude-Session)\s*:.*$", re.IGNORECASE | re.MULTILINE)
_GOAL_HEADING = re.compile(r"^##\s*\d*[.、]?\s*(?:单一目标|目标)")
NONE_WORD = "无"
UNPROVIDED = "未提供（由审计者自行核验）"


@dataclass(frozen=True)
class CardFields:
    """What the card itself says; every field is optional because old cards have no such lines."""

    title: str
    goal: str
    tds: tuple[str, ...]
    wbs: str
    safety: str | None


def read_card_fields(card_text: str, fallback_title: str) -> CardFields:
    title = fallback_title
    tds: list[str] = []
    wbs = ""
    safety: str | None = None
    lines = card_text.splitlines()
    for line in lines:
        if line.startswith("# ") and title == fallback_title:
            title = line[2:].strip()
        header = _HEADER_LINE.match(line)
        if not header:
            continue
        key, value = header.group(1).replace(" ", ""), header.group(2).strip()
        if key == "关联TD":
            tds.extend(TD_ID.findall(value))
        elif key == "WBS" and value and value != NONE_WORD:
            wbs = value.strip("`")
        elif key == "安全回路":
            found = _SAFETY_VALUE.match(value)
            safety = found.group(1) if found else safety
    return CardFields(
        title=title,
        goal=_goal_sentence(lines),
        tds=tuple(dict.fromkeys(tds)),
        wbs=wbs,
        safety=safety,
    )


def _goal_sentence(lines: Sequence[str]) -> str:
    for index, line in enumerate(lines):
        if not _GOAL_HEADING.match(line):
            continue
        for body in lines[index + 1 :]:
            if body.startswith("#"):
                break
            text = body.strip()
            if text:
                return text[:200]
    return ""


def signature_lines(commit_messages: Sequence[str]) -> list[str]:
    """The attribution trailers of the newest commit that has any, verbatim (template: 署名)."""
    for message in reversed(commit_messages):
        found = [m.group(0).strip() for m in _TRAILER.finditer(message)]
        if found:
            return found
    return []


def build_body(
    *,
    task_card: str,
    fields: CardFields,
    scope_paths: Sequence[str],
    safety_circuit: str,
    chg_numbers: Sequence[str],
    commits: Sequence[tuple[str, str]],
    evidence: Sequence[str],
    sweep: str | None,
    tds: Sequence[str],
    head_sha: str,
) -> str:
    out: list[str] = []
    signature = signature_lines([message for _sha, message in commits])
    if signature:
        out += ["## 署名", "", *signature, ""]
    summary = fields.title + (f"：{fields.goal}" if fields.goal else "")
    out += ["## 做了什么", "", summary, ""]
    out += ["## 可改范围", "", f"任务卡: {task_card}", ""]
    out += [f"- {path}" for path in scope_paths]
    out += ["", "## 安全回路", "", f"安全回路: {safety_circuit}", ""]
    out += ["## 证据", ""]
    out += [f"- 变更单: {'、'.join(chg_numbers)}"]
    out += [f"- 提交 {sha[:8]} {message.splitlines()[0] if message else ''}" for sha, message in commits]
    out += [f"- {item}" for item in evidence] or [f"- {UNPROVIDED}"]
    out += ["", "## 同类排查", "", sweep or UNPROVIDED, ""]
    out += ["## 关联 TD", "", "、".join(tds) if tds else NONE_WORD, ""]
    out += ["## WBS", "", f"WBS: {fields.wbs}" if fields.wbs else NONE_WORD, ""]
    suggestion = (
        "；".join(f"{td} 已偿还，证据 提交号 {head_sha[:8]}（待审计与合并）" for td in tds)
        if tds
        else NONE_WORD
    )
    out += ["## 建议回写", "", suggestion, ""]
    out += ["由 `main.py pr open` 按 `.github/pull_request_template.md` 生成；只开不合，合并按 AUD-001 独立审计。"]
    return "\n".join(out) + "\n"
