"""Card tier gate (TD-SW008-124): a card may not declare a gate tier lower than the machine classifier computes.

The rule document says the tier comes from the highest-risk real path and is never chosen by the executor. A hand-written card declares it in a header line
``> 档次：文档档；…`` (also written ``**核心档**`` or just ``核心``). When that line is present, the card's path table (paths marked runtime state are not
changes and are left out) is run through ``tests/tools/tier_classifier.py`` and a lower declared tier is refused. A card without the line is refused when it is new (not part of ``CARD_TIER_FROZEN_COMMIT``) and not judged when it is old.
The classifier is loaded by file path so the product package does not import the test tree; if it cannot be loaded while a tier is declared, that is refused
too (fail closed), never skipped.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType

CLASSIFIER_RELATIVE = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/tier_classifier.py"
_DECLARED = re.compile(r"^>\s*档次[：:]\s*[*`\s]*(文档|测试|产品|核心)")
_TIER_OF = {"文档": "docs", "测试": "tests", "产品": "product", "核心": "core"}
# Cards that exist in this frozen main commit are old and need not declare a tier; every other card is new and must (coordinator ruling, user's go-ahead
# 2026-10-29).  Membership in a fixed commit cannot be forged the way a Git date can: a new card cannot be made to appear in a commit that already exists.
# A commit that cannot be read, or a card path that cannot be resolved, counts as new (fail closed).
CARD_TIER_FROZEN_COMMIT = "de7e6085455e159d6bf2d90cb7d9b8809508f1e5"
_LABEL_OF = {"docs": "文档档", "tests": "测试档", "product": "产品档", "core": "核心档"}


def declared_tiers(lines: Sequence[str]) -> list[str]:
    """Tier names declared by ``> 档次：`` lines; a line that names no known tier counts as an empty entry so it is refused rather than ignored."""

    result: list[str] = []
    for line in lines:
        if re.match(r"^>\s*档次[：:]", line):
            match = _DECLARED.match(line)
            result.append(_TIER_OF[match.group(1)] if match else "")
    return result


def card_is_new(card_file: Path) -> bool:
    """False only when the card file is part of ``CARD_TIER_FROZEN_COMMIT``; anything else, including any failure to find out, is new."""

    try:
        done = subprocess.run(
            ["git", "-C", str(card_file.parent), "cat-file", "-e", f"{CARD_TIER_FROZEN_COMMIT}:./{card_file.name}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        return done.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return True


def _load_classifier(workspace_root: Path) -> ModuleType:
    source = workspace_root / CLASSIFIER_RELATIVE
    spec = importlib.util.spec_from_file_location("_card_tier_classifier", source)
    if spec is None or spec.loader is None or not source.is_file():
        raise FileNotFoundError(str(source))
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules.setdefault(spec.name, module)  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def tier_findings(
    lines: Sequence[str], change_paths: Iterable[str], *, workspace_root: Path, card_file: Path | None = None
) -> list[tuple[str, str, str]]:
    """``(rule, subject, message)`` findings; empty when the card declares no tier or declares one that is not lower than the computed tier."""

    declared = declared_tiers(lines)
    if not declared:
        if card_file is not None and card_is_new(card_file):
            return [("tier", "档次", "新卡头部必须写 `> 档次：文档档/测试档/产品档/核心档`（不在冻结提交里的卡不写档次即拒）")]
        return []
    if len(declared) > 1:
        return [("tier", "档次", f"头部字段 `档次：` 出现 {len(declared)} 次，只能写一次")]
    if declared[0] == "":
        return [("tier", "档次", "`档次：` 之后要先写 文档档/测试档/产品档/核心档 之一")]
    paths = list(change_paths)
    if not paths:
        return []
    try:
        classifier = _load_classifier(workspace_root)
        computed = classifier.classify_paths(paths, classifier.load_rules()).tier
    except Exception as error:  # noqa: BLE001 - any failure to compute the tier must refuse, never pass
        return [("tier", "档次", f"卡声明了档次，但分档器不可用，无法核对：{type(error).__name__}: {error}")]
    tiers: tuple[str, ...] = classifier.TIERS
    if tiers.index(declared[0]) < tiers.index(computed):
        return [
            (
                "tier",
                "档次",
                f"卡声明 {_LABEL_OF[declared[0]]}，分档器按真实路径算出 {_LABEL_OF[computed]}；档次取各路径中最高的，执行者不得自选更低档",
            )
        ]
    return []
