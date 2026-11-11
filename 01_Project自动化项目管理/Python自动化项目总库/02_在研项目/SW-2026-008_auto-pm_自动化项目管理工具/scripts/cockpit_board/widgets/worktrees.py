"""工作树与分支页（CHG-SCPT-2026-628 骨架 D）：每个工位的分支和干净程度、哪些可以清理。

读 `worktree list --json` 和 `worktree sweep --json --no-fetch`（只列，不带 --apply）。
命令里写 null 的字段（没查过）显示“没检查”，不当成“没有”。这里没有清理按钮。
"""

from __future__ import annotations

from typing import Any

from cockpit_board import shell
from cockpit_board.widgets import common as c

LISTED = 12


def _station(row: dict[str, Any]) -> str:
    parts = [str(row.get("branch") or "（没有分支）")]
    if row.get("broken"):
        parts.append("坏了：" + str(row["broken"]))
    if not row.get("checked"):
        parts.append("改动和推送" + c.STATES["unchecked"])
    else:
        parts.append(c.flag_text(row.get("dirty"), "有未提交", "无未提交"))
        parts.append(c.flag_text(row.get("unpushed"), "有未推送", "都已推送"))
        parts.append(c.flag_text(row.get("merged"), "已并进 main", "没并进 main"))
    if row.get("stale"):
        parts.append(f"闲了 {row.get('idle_days')} 天")
    return " · ".join(parts)


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    if reader == "worktree_list":
        stations = data.get("stations") or []
        rows = [("工位", c.count_text(stations, "个"))]
        rows += [(str(row.get("name")), _station(row)) for row in stations[:LISTED]]
        return rows
    if reader == "worktree_sweep":
        items = data.get("items") or []
        rows = [("可清理", c.count_text(items, "项") + "（只列出，没清）")]
        if data.get("fetch_warning"):
            rows.append(("注意", str(data["fetch_warning"])))
        rows += [(str(row.get("target")), f"{row.get('category')} · {row.get('reason') or ''}".rstrip(" ·")) for row in items[:LISTED]]
        return rows
    return []


def is_empty(reader: str, data: dict[str, Any]) -> bool | None:
    """工位列表是空的才算空；清理清单不参与判空（“没有可清理的”不代表“没有工位”）。"""
    if reader == "worktree_list":
        return not data.get("stations")
    return None


class WorktreesPage(c.ReadPage):
    def __init__(self) -> None:
        empty_text, error_text = shell.page_texts()["worktrees"]
        super().__init__("worktrees", "工作树与分支", "每个 AI 的工位干不干净、哪些可以收", (
            ("收工位、清理", "会删东西，骨架不放按钮；在控制根终端里跑 main.py worktree close / sweep --apply", ""),
        ), empty_text, error_text)

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        return is_empty(reader, data)
