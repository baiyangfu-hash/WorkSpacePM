"""The cloud full gate lets a run that has started finish (CHG-SCPT-2026-713).

With ``cancel-in-progress: true`` every merge into ``main`` cancelled the run still going for the previous merge.  A full
run takes about 43 minutes, so on a day with several merges no run reached a verdict.  The user decided (2026-11-17T12:44:24Z)
that the running round is never cancelled; GitHub then keeps at most one waiting run per group and a newer merge replaces it.
These checks read the workflow file and fail when that setting or the per-branch group is changed back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parents[3]
WORKFLOW = WORKSPACE / ".github" / "workflows" / "gate-full.yml"


def _concurrency() -> dict[str, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    concurrency = loaded["concurrency"]
    assert isinstance(concurrency, dict), (
        f"gate-full.yml: concurrency must be a mapping, got {concurrency!r}"
    )
    return concurrency


def test_a_running_gate_full_round_is_not_cancelled_by_a_newer_one() -> None:
    assert _concurrency().get("cancel-in-progress") is False


def test_gate_full_runs_are_grouped_per_branch() -> None:
    group = _concurrency().get("group")
    assert isinstance(group, str)
    assert "github.ref" in group
