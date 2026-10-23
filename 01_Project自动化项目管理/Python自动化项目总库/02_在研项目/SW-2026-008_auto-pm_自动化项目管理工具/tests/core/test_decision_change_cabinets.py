"""Approval finds a registered project's CHG under ``04_监控`` or the PLC template's ``11_监控`` (D09 onboarding N2)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.domain.change.decision_service import DecisionService, DecisionValidationError
from auto_pm.ui.cli.decision import _runtime_capability

PROJECT_ID = "DJ-2026-901"
PROJECT_ROOT = "0100_PLC自动化/DJ-2026-901"
CHANGE_ID = "CHG-PLC-2026-001"
CHG_TEXT = f"""# {CHANGE_ID}
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | {CHANGE_ID} |
| 项目编号 | {PROJECT_ID} |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
"""


def _write_change(root: Path, monitor: str) -> Path:
    chg_dir = root / PROJECT_ROOT / monitor / "01_变更管理" / "01_变更单" / "CHG-PLC"
    chg_dir.mkdir(parents=True, exist_ok=True)
    path = chg_dir / f"{CHANGE_ID}.md"
    path.write_text(CHG_TEXT, encoding="utf-8")
    return path


def _repository(root: Path, *monitors: str) -> None:
    for monitor in monitors:
        _write_change(root, monitor)
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {"project_id": PROJECT_ID, "project_root": PROJECT_ROOT, "development_root": PROJECT_ROOT}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-qm", "base"],
        check=True,
    )


def _planning(service: DecisionService) -> DecisionPackageDTO:
    return service.create_decision(
        CHANGE_ID,
        "fubai",
        project_id=PROJECT_ID,
        approved_files=["02_PLC程序/PLC_ST/FB_3001.scl"],
        decision_id="DEC-20261020-A1B2C3D4",
        planning_plan_hash="a" * 64,
        approval_evidence_ref="user-confirmation:D09-N2-TEST",
    )


def _runtime(service: DecisionService) -> DecisionPackageDTO:
    return service.create_decision(
        CHANGE_ID,
        "fubai",
        project_id=PROJECT_ID,
        approved_files=["02_PLC程序/PLC_ST/FB_3001.scl"],
        decision_id="DEC-20261020-B1B2C3D4",
        runtime_capability=_runtime_capability(("settle_expired_run",), ("RUN-DJ901-OLD",), (), ("CANCELLED",)),
    )


@pytest.mark.parametrize("monitor", ["04_监控", "11_监控"])
@pytest.mark.parametrize("create", [_planning, _runtime], ids=["planning", "runtime"])
def test_approval_reads_the_chg_from_either_change_cabinet(
    tmp_path: Path, monitor: str, create: Callable[[DecisionService], DecisionPackageDTO]
) -> None:
    _repository(tmp_path, monitor)

    decision = create(DecisionService(tmp_path))

    assert decision.change_id == CHANGE_ID
    assert decision.project_id == PROJECT_ID


@pytest.mark.parametrize("create", [_planning, _runtime], ids=["planning", "runtime"])
def test_a_chg_in_both_cabinets_is_ambiguous_and_refused(
    tmp_path: Path, create: Callable[[DecisionService], DecisionPackageDTO]
) -> None:
    _repository(tmp_path, "04_监控", "11_监控")

    with pytest.raises(DecisionValidationError, match="04_监控 与 11_监控 下各有一份"):
        create(DecisionService(tmp_path))

    assert not (tmp_path / ".auto-pm" / "decisions").exists() or not any(
        (tmp_path / ".auto-pm" / "decisions").iterdir()
    )


def test_a_missing_chg_is_still_reported_as_missing(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / PROJECT_ROOT).mkdir(parents=True, exist_ok=True)

    with pytest.raises(DecisionValidationError, match="未找到指定项目的 Planning CHG 真源"):
        _planning(DecisionService(tmp_path))


def test_an_archived_copy_is_not_a_second_cabinet(tmp_path: Path) -> None:
    _repository(tmp_path, "11_监控")
    archived = tmp_path / PROJECT_ROOT / "11_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC" / "archive"
    archived.mkdir()
    (archived / f"{CHANGE_ID}.md").write_text(CHG_TEXT, encoding="utf-8")

    decision = _planning(DecisionService(tmp_path))

    assert decision.change_id == CHANGE_ID
