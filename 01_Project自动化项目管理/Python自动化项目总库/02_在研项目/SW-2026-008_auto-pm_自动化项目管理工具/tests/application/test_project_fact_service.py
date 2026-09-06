"""Regression coverage for the C1 read-only project fact package."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.core.project_fact_service import ProjectFactService


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        text=True,
    )
    return result.stdout


def _create_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    project_dir = workspace / "SW-2026-008_事实包测试"
    project_dir.mkdir(parents=True)
    (project_dir / ".copier-answers.yml").write_text(
        "\n".join(
            [
                "project_id: SW-2026-008",
                "project_name: auto-pm",
                "stack: python",
                "version: V1.2.3",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "PM_SESSION_SW-2026-008.md").write_text(
        "\n".join(
            [
                "# PM_SESSION_SW-2026-008",
                "",
                "- runtime_root: 00_Infrastructure/auto_pm",
                "",
                "## Spec Snapshot",
                "",
                "| 规范编号 | 版本号 |",
                "|---|---|",
                "| PM-042 | V2.4.0 |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    change_dir = project_dir / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    change_dir.mkdir(parents=True)
    (change_dir / "CHG-SCPT-2026-156.md").write_text(
        "| 字段 | 内容 |\n|---|---|\n| 变更状态 | draft |\n",
        encoding="utf-8",
    )

    registry_dir = workspace / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir()
    (registry_dir / "spec_registry.json").write_text(
        json.dumps(
            {
                "specs": {
                    "PM-042": {"version": "V2.4.0"},
                    "DEV-300": {"version": "V1.0.0"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runtime = workspace / "00_Infrastructure" / "auto_pm"
    for layer in ("contracts", "domain", "infrastructure", "application", "ui"):
        (runtime / "auto_pm" / layer).mkdir(parents=True, exist_ok=True)
    (runtime / "auto_pm" / "application" / "service.py").write_text(
        "from __future__ import annotations\n", encoding="utf-8"
    )
    (runtime / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")

    _git(workspace, "init")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "fixture")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "fixture")
    return workspace


def test_collects_traceable_facts_without_mutating_git(tmp_path: Path) -> None:
    workspace = _create_workspace(tmp_path)
    service = ProjectFactService(str(workspace))

    snapshot = service.collect("SW-2026-008")

    assert snapshot.evidence_id.startswith("FACT-")
    assert snapshot.git.head
    assert snapshot.git.status == []
    assert snapshot.pm_session.sha256
    assert snapshot.open_changes[0].change_number == "CHG-SCPT-2026-156"
    assert snapshot.spec_snapshot.registry_versions["DEV-300"] == "V1.0.0"
    assert snapshot.code_structure.clean_architecture_layers == [
        "contracts",
        "domain",
        "infrastructure",
        "application",
        "ui",
    ]
    assert {check.check_id for check in snapshot.available_checks} >= {
        "doctor",
        "mypy",
        "pytest",
        "python-check",
        "ruff",
        "spec-check",
    }
    assert _git(workspace, "status", "--porcelain") == ""


def test_validation_rejects_expired_identity_mismatch_and_tampering(tmp_path: Path) -> None:
    workspace = _create_workspace(tmp_path)
    service = ProjectFactService(str(workspace))
    snapshot = service.collect("SW-2026-008")

    expired = snapshot.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    expired_result = service.validate(expired, "SW-2026-008")
    assert expired_result.valid is False
    assert any("过期" in failure for failure in expired_result.failures)

    identity_result = service.validate(snapshot, "DJ-2026-005")
    assert identity_result.valid is False
    assert any("项目身份不一致" in failure for failure in identity_result.failures)

    missing = snapshot.model_copy(
        update={"pm_session": snapshot.pm_session.model_copy(update={"sha256": ""})}
    )
    missing_result = service.validate(missing, "SW-2026-008")
    assert missing_result.valid is False
    assert any("缺少PM_SESSION 指纹" in failure for failure in missing_result.failures)

    tampered = snapshot.model_copy(
        update={"project_path": str(workspace / "unexpected")}
    )
    tampered_result = service.validate(tampered, "SW-2026-008")
    assert tampered_result.valid is False
    assert any("完整性指纹" in failure for failure in tampered_result.failures)


def test_validation_rejects_worktree_drift(tmp_path: Path) -> None:
    workspace = _create_workspace(tmp_path)
    service = ProjectFactService(str(workspace))
    snapshot = service.collect("SW-2026-008")

    (workspace / "unreviewed_change.py").write_text("value = 1\n", encoding="utf-8")

    result = service.validate(snapshot, "SW-2026-008")

    assert result.valid is False
    assert any("Git 工作树状态" in failure for failure in result.failures)
