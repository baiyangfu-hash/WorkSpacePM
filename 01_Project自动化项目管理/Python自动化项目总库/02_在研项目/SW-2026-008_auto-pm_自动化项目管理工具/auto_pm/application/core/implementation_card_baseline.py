"""Card CI-baseline gate (TD-SW008-125): a card that changes a test the Linux CI baseline lists as a known failure must refresh the baseline in the same card.

``tests/tools/sw008_ci/baseline.linux.json`` lists the test ids that are allowed to fail on Linux.  ``compare_baseline.py`` judges a listed id that now passes
as FAIL (a stale baseline), so fixing such a test without refreshing the list turns the next CI run red (cards 107 and 111).  The card's path table is what
tells the precheck which files a card changes: when it contains a test file that has ids in the baseline, it must also contain the baseline file, or state
the reason in a header line ``> 基线例外：<reason>``.  A missing baseline file means this repository has no such list and nothing is judged; one that exists
but cannot be read is refused (fail closed), never skipped.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

PROJECT_RELATIVE = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"
BASELINE_RELATIVE = f"{PROJECT_RELATIVE}/tests/tools/sw008_ci/baseline.linux.json"
_EXCEPTION = re.compile(r"^>\s*基线例外[：:]\s*(\S.*)$")


def _listed_files(workspace_root: Path) -> tuple[set[str], str]:
    """Workspace-relative test files that have ids in the baseline, plus an error text (empty when readable or absent)."""

    source = workspace_root / BASELINE_RELATIVE
    if not source.is_file():
        return set(), ""
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
        ids = document["ids"]
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise ValueError("`ids` must be a list of strings")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return set(), f"{type(error).__name__}: {error}"
    return {f"{PROJECT_RELATIVE}/{item.split('::', 1)[0]}" for item in ids}, ""


def baseline_findings(
    lines: Sequence[str], change_paths: Iterable[str], *, workspace_root: Path
) -> list[tuple[str, str, str]]:
    """``(rule, subject, message)`` findings; empty when no changed test is listed in the baseline, the baseline file is in the card, or an exception is stated."""

    paths = set(change_paths)
    tests = {path for path in paths if path.startswith(f"{PROJECT_RELATIVE}/tests/")}
    if not tests:
        return []
    listed, error = _listed_files(workspace_root)
    if error:
        return [("baseline", "CI 基线", f"卡改了测试文件，但 CI 基线 {BASELINE_RELATIVE} 读不出，无法核对：{error}")]
    hit = sorted(tests & listed)
    if not hit or BASELINE_RELATIVE in paths:
        return []
    if any(_EXCEPTION.match(line) for line in lines):
        return []
    return [
        (
            "baseline",
            "CI 基线",
            f"卡改了登记在 CI 基线里的测试文件 {', '.join(hit)}，但路径表没有 {BASELINE_RELATIVE}；"
            "修好基线内的测试却不刷新基线，下一次 CI 会因“基线条目意外通过”变红。请把基线文件列进路径表，或写 `> 基线例外：<原因>`",
        )
    ]
