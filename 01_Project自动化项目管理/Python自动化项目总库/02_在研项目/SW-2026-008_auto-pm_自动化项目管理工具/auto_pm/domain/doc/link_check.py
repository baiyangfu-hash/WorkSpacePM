"""项目文档里 Markdown 相对链接的死链检查（TD-SW008-606，D-341）。

只查“链到的文件或目录在不在”：``[文字](相对路径)``、``![图](相对路径)`` 和引用式定义 ``[名]: 相对路径``。
不查的：网址和其它带协议的链接（``https:``、``mailto:``、``file:`` 等）、只写 ``#锚点`` 的同页链接、以 ``/`` 开头的
路径、模板占位 ``{{ … }}``、Obsidian 的 ``[[双链]]``；锚点 ``#…`` 和 ``?…`` 去掉后只核文件。代码块和行内代码里的不算链接。
归档目录（名字以 ``.`` 或 ``_`` 开头、或含“归档”“archive”“trash”）整个跳过：里面的旧文档链接坏了不算现行问题。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"`+[^`]*`+")
_INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+(?:\([^)\s]*\)[^)\s]*)*)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
_REFERENCE_DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class DeadLink:
    """一条死链：项目内相对路径（正斜杠）、行号、链接原文。"""

    file: str
    line: int
    target: str


def skips_folder(name: str) -> bool:
    """这个目录要不要整个跳过（归档、隐藏、缓存目录）。"""
    lower = name.lower()
    return name.startswith((".", "_")) or "归档" in name or "archive" in lower or "trash" in lower


def _file_part(target: str) -> str:
    """链接里要核对存在的那部分；不需要核的返回空串。"""
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or target.startswith(("#", "/", "\\")) or _SCHEME.match(target) or "{{" in target or "{%" in target:
        return ""
    target = re.split(r"[#?]", target, maxsplit=1)[0]
    return unquote(target)


def links_of(text: str) -> list[tuple[int, str]]:
    """(行号, 链接原文)：代码块和行内代码里的不算。"""
    found: list[tuple[int, str]] = []
    fence = ""
    for number, line in enumerate(text.splitlines(), start=1):
        opened = _FENCE.match(line)
        if fence:
            if opened and opened.group(1) == fence:
                fence = ""
            continue
        if opened:
            fence = opened.group(1)
            continue
        code_free = _INLINE_CODE.sub("", line)
        found.extend((number, m.group(1)) for m in _INLINE_LINK.finditer(code_free))
        definition = _REFERENCE_DEFINITION.match(code_free)
        if definition:
            found.append((number, definition.group(1)))
    return found


def _read(path: Path) -> str | None:
    """UTF-8（可带 BOM）读不了就按 GBK 读（老文档）；都读不了、或读文件出错，返回 None，由调用方报“读不了”。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


@dataclass
class LinkCheckReport:
    """查过的 .md 文件数、死链、读不了的文件（读不了不算通过，要报出来）。"""

    scanned: int = 0
    dead: list[DeadLink] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.dead and not self.unreadable


def dead_links(project_root: Path | str) -> LinkCheckReport:
    """扫一个项目目录；死链按文件、行号排好。"""
    root = Path(project_root)
    scanned = 0
    dead: list[DeadLink] = []
    unreadable: list[str] = []
    for folder, subfolders, files in os.walk(root):
        subfolders[:] = sorted(d for d in subfolders if not skips_folder(d))
        for name in sorted(files):
            if not name.lower().endswith(".md"):
                continue
            path = Path(folder) / name
            text = _read(path)
            if text is None:
                unreadable.append(path.relative_to(root).as_posix())
                continue
            scanned += 1
            relative = path.relative_to(root).as_posix()
            for number, target in links_of(text):
                part = _file_part(target)
                if part and not (path.parent / part).exists():
                    dead.append(DeadLink(file=relative, line=number, target=target))
    return LinkCheckReport(scanned=scanned, dead=dead, unreadable=unreadable)
