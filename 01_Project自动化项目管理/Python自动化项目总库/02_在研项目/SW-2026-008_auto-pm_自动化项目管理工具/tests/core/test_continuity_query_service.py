"""V05-A: the shared, versioned, capability-flagged query behind resume, orient and the SDK."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from auto_pm.core.continuity_query_service import ContinuityQueryError, ContinuityQueryService
from auto_pm.core.continuity_resume_service import ContinuityResumeService
from auto_pm.core.pm_facade_service import PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryService
from pydantic import ValidationError

from auto_pm.api import CockpitClient
from auto_pm.contracts import continuity_query as query_contract
from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.continuity_query import ActionCapability, RuntimeCapabilities
from auto_pm.contracts.continuity_resume import ContinuityResume

PROJECT = "SW-2026-008"
UNSUPPORTED_ACTIONS = ("PARK", "RESUME_PARKED", "PREEMPT")


def _workspace(root: Path) -> Path:
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md", ".gitignore"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Query Test", "-c", "user.email=query@example.invalid", "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
    )
    project = root / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(f"project_id: {PROJECT}\nproject_name: Query Test\nstack: python\n", encoding="utf-8")
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": PROJECT, "project_root": PROJECT, "development_root": PROJECT}],
            }
        ),
        encoding="utf-8",
    )
    return project


def _work(root: Path, work_id: str) -> None:
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.initialize("test")
    service.create_work(
        work_id=work_id,
        subject_project_id=PROJECT,
        kind=WorkKind.GOVERNANCE,
        title=work_id,
        owner="architect",
        scope_paths=["auto_pm/a.py"],
        source_fingerprint="sha256:abc",
        idempotency_key=f"create-{work_id}",
        read_only=True,
    )


def _snapshot(root: Path) -> dict[str, str]:
    """Every file below the workspace except Git's own metadata, with its SHA-256."""

    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _query(root: Path, requested_action: str = "") -> ContinuityResume:
    return cast(ContinuityResume, ContinuityQueryService(root).query(project_id=PROJECT, requested_action=requested_action))


def test_the_query_block_declares_versions_both_flags_false_and_three_unsupported_actions(tmp_path: Path) -> None:
    _workspace(tmp_path)
    block = _query(tmp_path).query
    assert block is not None
    assert block.schema_version == "continuity-query.v1"
    assert block.capabilities.contract_version == "runtime-capabilities.v1"
    assert block.capabilities.parking_supported is False
    assert block.capabilities.preemption_supported is False
    assert [(a.action.value, a.status) for a in block.capabilities.actions] == [(name, "UNSUPPORTED") for name in UNSUPPORTED_ACTIONS]
    assert all(a.reason for a in block.capabilities.actions)
    assert block.requested_action is None
    assert block.evidence_id.startswith("QUERY-")


def test_the_identity_fields_copy_the_resolved_context_and_the_producer_is_hashed_from_its_loaded_bytes(tmp_path: Path) -> None:
    _workspace(tmp_path)
    resume = _query(tmp_path)
    block, context = resume.query, resume.context
    assert block is not None
    assert (block.control_root, block.execution_root, block.candidate_commit) == (context.control_root, context.execution_root, context.candidate_commit)
    assert (block.configured_release_id, block.effective_release_id) == (context.configured_release_id, context.effective_release_id)
    assert (block.runtime_load_path, block.runtime_fallback_reason) == (context.runtime_load_path, context.runtime_fallback_reason)
    import auto_pm.application.core.continuity_query_service as producer

    digest = hashlib.sha256()
    for loaded in (Path(producer.__file__), Path(query_contract.__file__)):
        digest.update(loaded.read_bytes())
        digest.update(b"\0")
    assert Path(block.producer_load_path) == Path(producer.__file__).resolve()
    assert block.producer_sha256 == digest.hexdigest()


@pytest.mark.parametrize("action", UNSUPPORTED_ACTIONS)
def test_every_known_asked_action_is_answered_unsupported_and_changes_nothing_else(tmp_path: Path, action: str) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-Q-001")
    plain, asked = _query(tmp_path), _query(tmp_path, requested_action=action)
    assert asked.query is not None and asked.query.requested_action is not None
    assert (asked.query.requested_action.action.value, asked.query.requested_action.status) == (action, "UNSUPPORTED")
    assert asked.query.requested_action.reason
    # the answer is information only: the execution chain, the next action and the resume evidence stay exactly the same
    assert asked.model_dump(exclude={"query"}) == plain.model_dump(exclude={"query"})
    assert asked.work is not None and plain.work is not None and asked.work.state == plain.work.state


@pytest.mark.parametrize("asked", ["park", "PAUSE", "NONE", "READY", "PARKED"])
def test_an_unknown_asked_action_is_refused_and_writes_nothing(tmp_path: Path, asked: str) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    with pytest.raises(ContinuityQueryError):
        _query(tmp_path, requested_action=asked)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".auto-pm").exists()


def test_a_workspace_without_a_store_gets_a_query_and_nothing_is_created(tmp_path: Path) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    resume = _query(tmp_path, requested_action="PREEMPT")
    assert resume.query is not None and resume.work is None and resume.run is None
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".auto-pm").exists()


def test_an_existing_store_and_the_work_tree_stay_byte_identical_after_a_query(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-Q-002")
    before = _snapshot(tmp_path)
    assert any(name.endswith("continuity.db") for name in before)
    for action in ("", "PARK", "RESUME_PARKED", "PREEMPT"):
        _query(tmp_path, requested_action=action)
    assert _snapshot(tmp_path) == before


def test_resume_and_orient_are_one_producer_that_differ_only_by_the_asked_action(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-Q-003")
    facade = PmFacadeService(tmp_path)
    resumed = facade.resume(project_id=PROJECT)
    oriented = facade.orient(project_id=PROJECT)
    assert resumed.model_dump() == oriented.model_dump()
    asked = facade.orient(project_id=PROJECT, requested_action="PARK")
    assert asked.model_dump(exclude={"query"}) == resumed.model_dump(exclude={"query"})
    assert resumed.query is not None and asked.query is not None
    assert asked.query.requested_action is not None and asked.query.evidence_id != resumed.query.evidence_id
    assert asked.query.model_dump(exclude={"requested_action", "evidence_id"}) == resumed.query.model_dump(exclude={"requested_action", "evidence_id"})


def test_the_query_evidence_is_deterministic_and_follows_the_resume_evidence_without_changing_it(tmp_path: Path) -> None:
    _workspace(tmp_path)
    first, second = _query(tmp_path), _query(tmp_path)
    assert first.query is not None and second.query is not None
    assert first.query.evidence_id == second.query.evidence_id
    assert first.evidence_id == ContinuityResumeService(tmp_path).collect(project_id=PROJECT).evidence_id  # resume's own evidence is untouched
    _work(tmp_path, "WORK-Q-004")
    third = _query(tmp_path)
    assert third.query is not None
    assert third.evidence_id != first.evidence_id and third.query.evidence_id != first.query.evidence_id


def test_the_resume_v2_payload_stays_compatible_for_older_readers(tmp_path: Path) -> None:
    _workspace(tmp_path)
    resume = _query(tmp_path)
    payload = json.loads(resume.model_dump_json())
    assert payload["schema_version"] == "continuity-resume.v2" and payload["query"]["schema_version"] == "continuity-query.v1"
    for old_field in ("context", "mission", "work", "work_candidates", "run", "run_candidates", "checkpoint", "lease", "conflicts", "next_legal_action", "read_set", "intake", "evidence_id"):
        assert old_field in payload
    stripped = {key: value for key, value in payload.items() if key != "query"}
    assert ContinuityResume.model_validate(stripped).query is None
    assert "lease_token" not in resume.model_dump_json()


def test_the_contract_cannot_express_support_or_a_ready_status() -> None:
    with pytest.raises(ValidationError):
        RuntimeCapabilities.model_validate({"parking_supported": True, "actions": []})
    with pytest.raises(ValidationError):
        RuntimeCapabilities.model_validate({"preemption_supported": True, "actions": []})
    for status in ("READY", "NONE", "SUPPORTED", ""):
        with pytest.raises(ValidationError):
            ActionCapability.model_validate({"action": "PARK", "status": status})
    with pytest.raises(ValidationError):
        ActionCapability.model_validate({"action": "PAUSE"})


def test_the_sdk_orient_returns_what_the_facade_returns_and_writes_nothing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-Q-005")
    before = _snapshot(tmp_path)
    client = CockpitClient(tmp_path, PROJECT)
    via_sdk = client.orient(requested_action="PREEMPT")
    via_facade = PmFacadeService(tmp_path).orient(project_id=PROJECT, invocation_path=str(tmp_path), requested_action="PREEMPT")
    assert via_sdk.model_dump() == via_facade.model_dump()
    assert via_sdk.query is not None and via_sdk.query.requested_action is not None
    assert via_sdk.query.requested_action.status == "UNSUPPORTED"
    assert _snapshot(tmp_path) == before
