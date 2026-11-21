"""The gate CI driver: merging per-group summaries must never turn a missing or failing group into a pass."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.gate_run_service import GROUPS, GateRunError
from tests.tools.sw008_ci import gate_run_ci as ci


def part(name: str, **over: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "commit": "a" * 40,
        "commit_end": "a" * 40,
        "git_dirty": False,
        "git_dirty_end": False,
        "manifest_sha256": "m",
        "ignored_code": [],
        "reasons": ["组不齐全"],
        "results": {name: {"exit": 0}},
    }
    base.update(over)
    return base


def test_merge_collects_all_groups_and_drops_incomplete_reason() -> None:
    merged = ci.merge_summaries([part(g.name) for g in GROUPS])
    assert set(merged["results"]) == {g.name for g in GROUPS}
    assert merged["reasons"] == []
    assert merged["groups_run"] == [g.name for g in GROUPS]


def test_merge_refuses_mixed_commits() -> None:
    with pytest.raises(GateRunError):
        ci.merge_summaries([part("core"), part("cli", commit="b" * 40)])


def test_merge_refuses_duplicate_group() -> None:
    with pytest.raises(GateRunError):
        ci.merge_summaries([part("core"), part("core")])


def test_merge_keeps_dirty_flag_and_real_reasons() -> None:
    merged = ci.merge_summaries(
        [part("core"), part("cli", git_dirty=True, reasons=["坏了", "组不齐全"])]
    )
    assert merged["git_dirty"] is True
    assert merged["reasons"] == ["坏了"]


def test_missing_group_is_listed_in_failures(tmp_path: Path) -> None:
    from auto_pm.application.core.gate_run_service import GateSummary

    lines = ci.failure_lines(tmp_path, GateSummary())
    assert len(lines) == len(GROUPS)
    assert all("没有产出" in line for line in lines)


def test_merge_without_inputs_is_refused(tmp_path: Path) -> None:
    args = argparse.Namespace(inputs=[str(tmp_path / "none")], out=str(tmp_path / "o"), worktree="")
    assert ci.cmd_merge(args) == 2


def test_plugin_failure_keeps_the_published_verdict_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.gate_run_service import SUMMARY_FILE, GateRunService, GateSummary

    source = tmp_path / "core"
    source.mkdir()
    (source / SUMMARY_FILE).write_text(json.dumps(part("core")), encoding="utf-8")
    monkeypatch.setattr(GateRunService, "judge_dir", lambda *_args, **_kwargs: GateSummary(verdict="PASS"))
    out = tmp_path / "out"
    result = ci.main(["merge", "--in", str(source), "--out", str(out), "--plugin-result", "failure"])
    assert result == 1
    published = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert published["verdict"] == "FAIL"
    assert "Siemens LSP" in published["reasons"][0]
