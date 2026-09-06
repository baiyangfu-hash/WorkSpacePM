"""Dogfood 隔离 CLI 的最小冒烟测试。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def test_dogfood_review_cli_reports_stable_side_verdict(tmp_path: Path) -> None:
    source = tmp_path / "00_Infrastructure" / "auto_pm"
    source.mkdir(parents=True)
    (source / "version.txt").write_text("stable\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('stable')\n", encoding="utf-8")
    candidate = tmp_path / ".auto-pm" / "worktrees" / "candidate"
    candidate.mkdir(parents=True)
    candidate_source = candidate / "00_Infrastructure" / "auto_pm"
    candidate_source.mkdir(parents=True)
    (candidate_source / "version.txt").write_text("candidate\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "dogfood",
            "review",
            "--candidate-path",
            str(candidate),
            "--no-report",
            "--json-output",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["reviewer"] == "stable-control-plane"
    assert payload["passed"] is True


def test_dogfood_inspect_cli_rejects_non_isolated_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    result = CliRunner().invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "dogfood",
            "inspect",
            "--candidate-path",
            str(candidate),
        ],
    )

    assert result.exit_code == 1
    assert "隔离目录" in result.output
