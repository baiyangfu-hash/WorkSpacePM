"""TD-SW008-025：Work 授权时必须校验 Work 与 Decision 的项目一致，写错项目立即拒绝并说清原因。"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_pm.application.core.work_registry_service import WorkRegistryError, WorkRegistryService
from auto_pm.contracts.continuity import WorkKind, WorkState

DECISION_ID = "DEC-20261025-TD025A01"


def _repository(root: Path) -> None:
    """控制根必须是真 Git 仓库（Store 初始化要采集 Git 事实）。"""
    git = ["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    subprocess.run([*git, "add", "README.md", ".gitignore"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "baseline"], check=True, capture_output=True)


def _write_decision(root: Path, *, project_id: str, conclusion: str = "approved") -> None:
    path = root / ".auto-pm" / "decisions" / f"{DECISION_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "decision_package.v1",
                "decision_id": DECISION_ID,
                "project_id": project_id,
                "change_id": "CHG-SCPT-2026-900",
                "approved_scope": "MODULE",
                "approved_files": ["README.md"],
                "approver": "tester",
                "approved_at": datetime.now(UTC).isoformat(),
                "decision_conclusion": conclusion,
            }
        ),
        encoding="utf-8",
    )


def _planned_work(root: Path, *, project_id: str) -> tuple[WorkRegistryService, str]:
    _repository(root)
    service = WorkRegistryService(root)
    service.initialize("test")
    work = service.create_work(
        work_id="WORK-TD025-001",
        subject_project_id=project_id,
        kind=WorkKind.BUG,
        title="project guard",
        owner="tester",
        scope_paths=["README.md"],
        source_fingerprint="sha256:td025",
        idempotency_key="td025-create",
    )
    assert work.state is WorkState.PLANNED
    return service, work.work_id


def test_authorize_with_a_decision_of_another_project_is_refused_with_a_clear_reason(tmp_path: Path) -> None:
    _write_decision(tmp_path, project_id="SW-TEST-OTHER")
    service, work_id = _planned_work(tmp_path, project_id="SW-TEST-001")

    with pytest.raises(WorkRegistryError, match="Decision 项目与 Work subject 不一致"):
        service.authorize(work_id, DECISION_ID, "td025-authorize")

    assert service.get_work(work_id).state is WorkState.PLANNED


def test_authorize_with_the_decision_of_the_same_project_still_works(tmp_path: Path) -> None:
    _write_decision(tmp_path, project_id="SW-TEST-001")
    service, work_id = _planned_work(tmp_path, project_id="SW-TEST-001")

    assert service.authorize(work_id, DECISION_ID, "td025-authorize").state is WorkState.READY


def test_authorize_with_a_missing_decision_names_the_decision(tmp_path: Path) -> None:
    service, work_id = _planned_work(tmp_path, project_id="SW-TEST-001")

    with pytest.raises(WorkRegistryError, match=DECISION_ID):
        service.authorize(work_id, DECISION_ID, "td025-authorize")
