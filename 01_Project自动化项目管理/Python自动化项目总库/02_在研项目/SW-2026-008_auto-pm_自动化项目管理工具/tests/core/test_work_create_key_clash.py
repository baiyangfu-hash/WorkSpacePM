"""F15: creating a Work under a taken id with a different idempotency key is a clean refusal, not a raw sqlite3.IntegrityError."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.work_registry_service import WorkRegistryError, WorkRegistryService
from auto_pm.contracts.continuity import WorkKind
from tests.git_support import git_do


def _service(root: Path) -> WorkRegistryService:
    git_do(root, "init")
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.initialize("test")
    return service


def _create(service: WorkRegistryService, work_id: str, key: str) -> object:
    return service.create_work(
        work_id=work_id,
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Clash",
        owner="agent-a",
        scope_paths=["auto_pm/core/example.py"],
        source_fingerprint="sha256:abc",
        idempotency_key=key,
        read_only=True,
    )


def test_the_same_work_id_with_a_new_key_is_refused_cleanly(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service, "WORK-CLASH", "key-1")
    with pytest.raises(WorkRegistryError) as caught:
        _create(service, "WORK-CLASH", "key-2")
    message = str(caught.value)
    assert "WORK-CLASH" in message and "幂等键" in message and "已存在" in message


def test_a_retry_with_the_original_key_still_replays(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _create(service, "WORK-CLASH", "key-1")
    assert _create(service, "WORK-CLASH", "key-1") == first


def test_the_same_key_for_another_work_id_is_still_refused(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service, "WORK-A", "key-1")
    with pytest.raises(WorkRegistryError, match="idempotency_key"):
        _create(service, "WORK-B", "key-1")


def test_the_clash_leaves_the_first_work_untouched(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = _create(service, "WORK-CLASH", "key-1")
    with pytest.raises(WorkRegistryError):
        _create(service, "WORK-CLASH", "key-2")
    assert _create(service, "WORK-CLASH", "key-1") == first
