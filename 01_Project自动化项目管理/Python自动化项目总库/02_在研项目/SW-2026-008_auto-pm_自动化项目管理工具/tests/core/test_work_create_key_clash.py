"""F15: creating a Work under a taken id with a different idempotency key is a clean refusal, not a raw sqlite3.IntegrityError."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.work_registry_service import WorkRegistryError, WorkRegistryService
from auto_pm.contracts.continuity import WorkKind
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _services, _start
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


# --- Run, Checkpoint and Handoff entries (audit 463): the same clash under a new key is a clean refusal there too. ---

CLEAN_TAIL = "重试同一次创建要沿用原来的幂等键；要新建请换一个编号"


def _execution(root: Path) -> tuple[WorkRegistryService, ContinuityExecutionService]:
    return _services(root, Clock())


def test_a_taken_run_id_under_a_new_key_is_refused_cleanly(tmp_path: Path) -> None:
    _, service = _execution(tmp_path)
    first = _start(service)
    with pytest.raises(ContinuityExecutionError, match="原 idempotency_key"):
        _start(service, idempotency_key="create-run-other-key")
    assert service._store.get_run(first.run_id) == first


def test_a_lease_token_already_in_use_under_a_new_key_is_refused_cleanly(tmp_path: Path) -> None:
    """The second Run passes every earlier check and meets the UNIQUE lease token, so the insert itself must refuse cleanly."""

    work, service = _execution(tmp_path)
    work.create_work(
        work_id="WORK-002",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Second",
        owner="architect",
        scope_paths=["auto_pm/core/b.py"],
        source_fingerprint="sha256:def",
        idempotency_key="create-work-2",
        read_only=True,
    )
    first = _start(service)
    with pytest.raises(ContinuityExecutionError) as caught:
        _start(
            service,
            run_id="RUN-002",
            work_id="WORK-002",
            owned_paths=["auto_pm/core/b.py"],
            idempotency_key="create-run-2",
        )
    message = str(caught.value)
    assert "RUN-002" in message and "已存在或与已有记录冲突" in message and CLEAN_TAIL in message
    assert service._store.get_run(first.run_id) == first
    assert [run.run_id for run in service._store.list_runs("WORK-002")] == []  # the failed Run left nothing behind


def test_a_taken_checkpoint_id_under_a_new_key_is_refused_cleanly(tmp_path: Path) -> None:
    _, service = _execution(tmp_path)
    _start(service)
    first = _checkpoint(service)
    with pytest.raises(ContinuityExecutionError) as caught:
        _checkpoint(service, idempotency_key="checkpoint-other-key")
    message = str(caught.value)
    assert "CP-001" in message and "已存在或与已有记录冲突" in message and CLEAN_TAIL in message
    assert service._store.get_checkpoint(first.checkpoint_id) == first
    assert _checkpoint(service) == first  # the original key still replays


def test_a_second_handoff_of_the_same_checkpoint_under_a_new_key_is_refused_cleanly(tmp_path: Path) -> None:
    _, service = _execution(tmp_path)
    _start(service)
    checkpoint = _checkpoint(service)

    def _handoff(key: str) -> object:
        return service.create_handoff(
            handoff_id="HO-CLASH",
            checkpoint_id=checkpoint.checkpoint_id,
            from_owner="agent-a",
            to_owner="agent-b",
            lease_token="lease-secret",
            idempotency_key=key,
        )

    first = _handoff("handoff-1")
    with pytest.raises(ContinuityExecutionError) as caught:
        _handoff("handoff-other-key")
    message = str(caught.value)
    assert "HO-CLASH" in message and "已存在或与已有记录冲突" in message and CLEAN_TAIL in message
    assert _handoff("handoff-1") == first  # the original key still replays
