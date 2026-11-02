"""The mutation script must be able to start: every mutant's original text occurs exactly once in the source.

``tests/core/agent_worktree_mutants.py`` (run by hand) rewrites ``agent_worktree_service.py`` once per mutant.  When a
source edit makes one anchor appear twice or not at all the script used to stop at that mutant (audit 540).  This test
runs only the cheap anchor check on every test run, so CI breaks on the edit that breaks the script.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).with_name("agent_worktree_mutants.py")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("agent_worktree_mutants", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_mutant_anchor_occurs_exactly_once_in_the_source() -> None:
    mutants = _load()

    broken = mutants.bad_anchors(mutants.SOURCE.read_text(encoding="utf-8"))

    assert broken == [], f"变异脚本有 {len(broken)} 条原文不唯一或没变化：{broken}"


def test_the_anchor_check_reports_an_ambiguous_original() -> None:
    mutants = _load()

    twice = "if x:\n" * 2

    assert mutants.bad_anchors(twice) != [], "原文出现两次的变异必须被报出来"
