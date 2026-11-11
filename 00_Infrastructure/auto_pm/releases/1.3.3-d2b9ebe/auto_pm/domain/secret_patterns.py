"""密钥格式识别（纯函数，无 I/O）：提交钩子与 PR 越界检查共用同一份规则。

只认“长得像真密钥”的固定前缀格式，命中时只报标签和路径，绝不回显命中的原文。
已吊销、历史上留在 Git 里的 blob 列入 ``ALLOWED_SECRET_BLOBS``，按完整 blob 标识放行。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "GitHub 令牌": re.compile(
        r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"
    ),
    "API 密钥": re.compile(
        r"\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}"
    ),
    "私钥": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

# 已吊销的历史 blob（完整 40 位）：gittoken.txt，早期提交 ec31f6a3 / b1934cb7 里出现过，令牌已在 GitHub 吊销。
ALLOWED_SECRET_BLOBS: frozenset[str] = frozenset({"25c80b56e781562bb51a3aa5a6449ebcf914b77d"})


@dataclass(frozen=True)
class SecretFinding:
    path: str
    label: str


def secret_labels(text: str) -> list[str]:
    """一行（或一段）文本里命中的密钥类别。"""
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def scan_unified_diff(
    diff_text: str, allowed_blobs: Iterable[str] | None = None
) -> list[SecretFinding]:
    """扫描 ``git diff --no-abbrev`` 输出里的新增行；每个（文件，类别）只报一次。

    文件头（``diff --git`` 到第一个 ``@@``）里的 ``+++`` 不是内容；新文件 blob 在放行清单里的整份跳过。
    """
    allowed = ALLOWED_SECRET_BLOBS if allowed_blobs is None else frozenset(allowed_blobs)
    findings: dict[tuple[str, str], SecretFinding] = {}
    path = ""
    in_hunk = False
    skip_file = False
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            in_hunk = False
            skip_file = False
            path = ""
            continue
        if not in_hunk:
            if raw.startswith("index "):
                new_id = raw[6:].split()[0].partition("..")[2]
                skip_file = new_id in allowed
            elif raw.startswith("+++ "):
                target = raw[4:].strip()
                path = "" if target == "/dev/null" else target.removeprefix("b/")
            elif raw.startswith("@@"):
                in_hunk = True
            continue
        if raw.startswith("@@"):
            continue
        if skip_file or not raw.startswith("+"):
            continue
        for label in secret_labels(raw[1:]):
            findings.setdefault((path, label), SecretFinding(path, label))
    return list(findings.values())
