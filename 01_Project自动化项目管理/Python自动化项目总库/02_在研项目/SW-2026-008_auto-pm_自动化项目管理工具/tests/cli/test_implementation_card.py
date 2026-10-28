"""CLI creation and validation exercise real artifact files."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.implementation_card import implementation_card_group
from tests.git_support import git_out

pytestmark = pytest.mark.usefixtures("identity_guard_off")


def test_create_then_validate_is_read_only(tmp_path: Path) -> None:
    runner = CliRunner()
    args = [
        "create", "--card-id", "CARD-TEST-003", "--pid", "SW-2026-008",
        "--wbs-item-id", "M2-GOV-IC01", "--milestone-id", "M2",
        "--source-ref", "WBS:plans/WBS.md",
        "--intent", "GOVERNANCE", "--base-commit", "a" * 40,
        "--worktree", "C:/candidate", "--owned-path", "project/file.py",
        "--commit-evidence-path", "governance/evidence.md",
        "--decision-id", "DEC-20260928-8D72B667", "--work-id", "WORK-1",
        "--run-id", "RUN-1", "--max-runs", "2", "--max-healing-attempts", "1",
        "--deadline-utc", "2026-09-29T00:00:00Z",
        "--quota-stop-remaining-percent", "30",
    ]
    context = SimpleNamespace(control_root=str(tmp_path))
    created = runner.invoke(implementation_card_group, args, obj=context)
    assert created.exit_code == 0, created.output
    card_path = tmp_path / ".auto-pm" / "implementation-cards" / "CARD-TEST-003.json"
    before = card_path.read_bytes()
    payload = json.loads(before)
    assert payload["wbs_item_id"] == "M2-GOV-IC01"
    assert payload["milestone_id"] == "M2"
    assert payload["source_refs"] == ["WBS:plans/WBS.md"]
    assert payload["owned_paths"] == ["project/file.py"]
    assert payload["commit_evidence_paths"] == ["governance/evidence.md"]
    review = card_path.with_suffix(".md").read_text(encoding="utf-8", errors="replace")
    assert "Product: `project/file.py`" in review
    assert "Commit evidence: `governance/evidence.md`" in review
    validation = runner.invoke(implementation_card_group, ["validate", "CARD-TEST-003"], obj=context)
    assert validation.exit_code != 0
    assert "problem statement is incomplete or stories are forbidden" in validation.output
    assert card_path.read_bytes() == before
    duplicate = runner.invoke(implementation_card_group, args, obj=context)
    assert duplicate.exit_code != 0
    assert "card artifacts already exist" in duplicate.output
    verification = runner.invoke(
        implementation_card_group,
        ["verify", "CARD-TEST-003", "--checkpoint-id", "CP-TEST-003",
         "--final-commit", "a" * 40], obj=context,
    )
    assert verification.exit_code != 0
    assert "verify requires DISPATCHED card" in verification.output
    assert card_path.read_bytes() == before


def _markdown_card(root: Path, baseline: str, body: str = "") -> Path:
    card = root / "card.md"
    card.write_text(
        f"> 隔离基线：`{baseline}`\n> 路径根：`.`\n\n| # | 路径 | 基线状态 |\n|---|---|---|\n"
        f"| 1 | `README.md` | 存在 |\n| 2 | `new.md` | 计划新增 |\n\n{body}\n",
        encoding="utf-8",
    )
    return card


def _control_root(root: Path) -> str:

    def git(*args: str) -> str:
        return git_out(root, *args)

    git("init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    git("add", "README.md")
    git("-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    return git("rev-parse", "HEAD")


def test_precheck_command_passes_a_valid_card_and_is_read_only(tmp_path: Path) -> None:
    from auto_pm.cli.__main__ import cli

    baseline = _control_root(tmp_path)
    card = _markdown_card(tmp_path, baseline, "`main.py continuity work create --work-id W`")
    before = sorted(str(path) for path in tmp_path.rglob("*") if ".git" not in path.parts)

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "implementation-card", "precheck",
                                      "--card-file", str(card)])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["passed"] is True and report["baseline"] == baseline
    assert report["commands"] == ["continuity work create"]
    assert sorted(str(path) for path in tmp_path.rglob("*") if ".git" not in path.parts) == before


def test_precheck_command_exits_nonzero_with_findings(tmp_path: Path) -> None:
    from auto_pm.cli.__main__ import cli

    baseline = _control_root(tmp_path)
    card = _markdown_card(tmp_path, baseline, "`main.py doc check --strict`")

    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "implementation-card", "precheck",
                                      "--card-file", str(card)])

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["passed"] is False
    assert any("--strict" in item["message"] for item in report["findings"])
