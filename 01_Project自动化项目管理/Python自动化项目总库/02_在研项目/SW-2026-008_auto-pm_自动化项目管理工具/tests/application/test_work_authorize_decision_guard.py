"""Work 授权的另两道关卡：Decision 未批准、Work 范围超出 Decision 批准的文件，都必须拒绝（TD-SW008-025 审计 158 补充）。"""

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


def test_authorize_with_a_decision_that_is_not_approved_is_refused(tmp_path: Path) -> None:
    _write_decision(tmp_path, project_id="SW-TEST-001", conclusion="rejected")
    service, work_id = _planned_work(tmp_path, project_id="SW-TEST-001")

    with pytest.raises(WorkRegistryError, match="Decision 未批准"):
        service.authorize(work_id, DECISION_ID, "td025-authorize")

    assert service.get_work(work_id).state is WorkState.PLANNED


def test_authorize_with_a_conditionally_approved_decision_works(tmp_path: Path) -> None:
    _write_decision(tmp_path, project_id="SW-TEST-001", conclusion="conditionally_approved")
    service, work_id = _planned_work(tmp_path, project_id="SW-TEST-001")

    assert service.authorize(work_id, DECISION_ID, "td025-authorize").state is WorkState.READY


def test_authorize_when_the_work_scope_exceeds_the_decision_is_refused(tmp_path: Path) -> None:
    _write_decision(tmp_path, project_id="SW-TEST-001")
    _repository(tmp_path)
    service = WorkRegistryService(tmp_path)
    service.initialize("test")
    work = service.create_work(
        work_id="WORK-TD025-002",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.BUG,
        title="scope guard",
        owner="tester",
        scope_paths=["README.md", "other.txt"],
        source_fingerprint="sha256:td025",
        idempotency_key="td025-scope-create",
    )

    with pytest.raises(WorkRegistryError, match="超出 Decision approved_files"):
        service.authorize(work.work_id, DECISION_ID, "td025-scope-authorize")
