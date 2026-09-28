"""CLI creation and validation exercise real artifact files."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from auto_pm.ui.cli.implementation_card import implementation_card_group


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
    assert card_path.read_bytes() == before
    assert runner.invoke(implementation_card_group, args, obj=context).exit_code != 0
    verification = runner.invoke(
        implementation_card_group,
        ["verify", "CARD-TEST-003", "--checkpoint-id", "CP-TEST-003",
         "--final-commit", "a" * 40], obj=context,
    )
    assert verification.exit_code != 0
    assert card_path.read_bytes() == before
