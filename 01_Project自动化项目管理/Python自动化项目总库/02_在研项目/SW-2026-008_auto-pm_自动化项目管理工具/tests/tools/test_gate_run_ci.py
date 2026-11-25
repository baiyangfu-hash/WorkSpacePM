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
    assert published["tier"] == "L3"
    assert published["plugin_result"] == "failure"
    assert "Siemens LSP" in published["reasons"][0]


def test_merge_writes_l3_tier_and_plugin_success_and_passes_release_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core.gate_run_service import (
        SUMMARY_FILE,
        GateRunService,
        GateSummary,
        GroupResult,
    )
    from auto_pm.application.core.release_deploy_check import validate_full_gate_verdict

    source = tmp_path / "merged"
    source.mkdir()
    commit = "a" * 40
    merged_input = {
        "schema": "gate-run.v1",
        "commit": commit,
        "commit_end": commit,
        "git_dirty": False,
        "git_dirty_end": False,
        "manifest_sha256": "b" * 64,
        "ignored_code": [],
        "reasons": [],
        "groups_run": [g.name for g in GROUPS],
        "results": {g.name: {"exit": 0} for g in GROUPS},
    }
    (source / SUMMARY_FILE).write_text(json.dumps(merged_input), encoding="utf-8")
    judged = GateSummary(
        commit=commit,
        commit_end=commit,
        git_dirty=False,
        git_dirty_end=False,
        manifest_sha256="b" * 64,
        groups_run=[g.name for g in GROUPS],
        complete=True,
        verdict="PASS",
        reasons=[],
        results={g.name: GroupResult(g.name, [], "", exit=0, verdict="PASS") for g in GROUPS},
    )
    monkeypatch.setattr(GateRunService, "judge_dir", lambda *_args, **_kwargs: judged)
    out = tmp_path / "out"
    result = ci.main(["merge", "--in", str(source), "--out", str(out), "--plugin-result", "success"])
    assert result == 0
    published = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert published["tier"] == "L3"
    assert published["plugin_result"] == "success"
    ok, detail = validate_full_gate_verdict(published, commit)
    assert ok is True, detail


def test_merge_l2_accepts_expected_groups_keeps_incomplete_false_and_rejected_by_release_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core.gate_run_service import (
        SUMMARY_FILE,
        GateRunService,
        GateSummary,
        GroupResult,
    )
    from auto_pm.application.core.release_deploy_check import validate_full_gate_verdict

    source = tmp_path / "app"
    source.mkdir()
    commit = "a" * 40
    part_payload = {
        "schema": "gate-run.v1",
        "commit": commit,
        "commit_end": commit,
        "git_dirty": False,
        "git_dirty_end": False,
        "manifest_sha256": "m" * 64,
        "ignored_code": [],
        "reasons": [ci.INCOMPLETE],
        "results": {"application": {"exit": 0}},
    }
    (source / SUMMARY_FILE).write_text(json.dumps(part_payload), encoding="utf-8")
    judged = GateSummary(
        commit=commit,
        commit_end=commit,
        git_dirty=False,
        git_dirty_end=False,
        manifest_sha256="m" * 64,
        groups_run=["application"],
        complete=False,
        verdict="PARTIAL",
        reasons=[ci.INCOMPLETE],
        results={"application": GroupResult("application", [], "", exit=0, verdict="PASS")},
    )
    monkeypatch.setattr(GateRunService, "judge_dir", lambda *_args, **_kwargs: judged)
    monkeypatch.setattr(ci, "manifest_sha256", lambda: "m" * 64)

    out = tmp_path / "out_l2"
    code = ci.main(
        [
            "merge",
            "--in",
            str(source),
            "--out",
            str(out),
            "--tier",
            "L2",
            "--expected-groups",
            "application",
            "--plugin-result",
            "skipped",
        ]
    )
    assert code == 0
    published = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert published["tier"] == "L2"
    assert published["expected_groups"] == ["application"]
    assert published["complete"] is False
    assert published["verdict"] == "PASS"
    assert published["reasons"] == []
    assert "没有产出" not in (out / "failures.md").read_text(encoding="utf-8")
    ok, detail = validate_full_gate_verdict(published, commit)
    assert ok is False and ("L2" in detail or "complete=False" in detail)


def test_merge_l2_rejects_missing_expected_group_or_dirty_tree_or_manifest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core.gate_run_service import (
        SUMMARY_FILE,
        GateRunService,
        GateSummary,
        GroupResult,
    )

    source = tmp_path / "app"
    source.mkdir()
    commit = "a" * 40
    (source / SUMMARY_FILE).write_text(
        json.dumps(
            {
                "schema": "gate-run.v1",
                "commit": commit,
                "commit_end": commit,
                "git_dirty": False,
                "git_dirty_end": False,
                "manifest_sha256": "wrong" + "0" * 59,
                "ignored_code": [],
                "reasons": [ci.INCOMPLETE],
                "results": {"application": {"exit": 0}},
            }
        ),
        encoding="utf-8",
    )
    judged = GateSummary(
        commit=commit,
        commit_end=commit,
        git_dirty=True,
        git_dirty_end=False,
        manifest_sha256="wrong" + "0" * 59,
        groups_run=["application", "cli"],
        complete=False,
        verdict="FAIL",
        reasons=["工作树不干净（含未跟踪文件）或读不出", ci.INCOMPLETE],
        results={"application": GroupResult("application", [], "", exit=0, verdict="PASS")},
    )
    monkeypatch.setattr(GateRunService, "judge_dir", lambda *_args, **_kwargs: judged)
    monkeypatch.setattr(ci, "manifest_sha256", lambda: "m" * 64)

    out = tmp_path / "out_l2_bad"
    code = ci.main(
        [
            "merge",
            "--in",
            str(source),
            "--out",
            str(out),
            "--tier",
            "L2",
            "--expected-groups",
            "application,cli",
            "--plugin-result",
            "skipped",
        ]
    )
    assert code == 1
    published = json.loads((out / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert published["verdict"] == "FAIL"
    joined = " | ".join(published["reasons"])
    assert "工作树不干净" in joined
    assert "manifest_sha256" in joined
    assert "缺失预期测试组: cli" in joined
