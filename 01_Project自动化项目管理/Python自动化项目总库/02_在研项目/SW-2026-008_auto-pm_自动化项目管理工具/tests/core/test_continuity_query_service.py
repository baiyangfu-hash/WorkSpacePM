"""V05-A: the shared, versioned, capability-flagged query behind resume, orient and the SDK."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from auto_pm.core.continuity_query_service import ContinuityQueryError, ContinuityQueryService
from auto_pm.core.continuity_resume_service import ContinuityResumeService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryService
from pydantic import ValidationError

from auto_pm.api import CockpitApiError, CockpitClient
from auto_pm.contracts import continuity_query as query_contract
from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.continuity_query import (
    ActionCapability,
    ContinuityQuery,
    RuntimeCapabilities,
    validate_runtime_capabilities,
)
from auto_pm.contracts.continuity_resume import ContinuityResume, validate_query_resume

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


# ---------------------------------------------------------------------------------------------- F02: both versions are stated, and every consumer checks them again
_DELETE = object()
_BROKEN_QUERIES: list[tuple[str, tuple[str, ...], object]] = [
    ("schema-version-missing", ("query", "schema_version"), _DELETE),
    ("capability-version-missing", ("query", "capabilities", "contract_version"), _DELETE),
    ("schema-version-v2", ("query", "schema_version"), "continuity-query.v2"),
    ("schema-version-empty", ("query", "schema_version"), ""),
    ("schema-version-none", ("query", "schema_version"), None),
    ("schema-version-number", ("query", "schema_version"), 1),
    ("schema-version-upper-case", ("query", "schema_version"), "CONTINUITY-QUERY.V1"),
    ("capability-version-v2", ("query", "capabilities", "contract_version"), "runtime-capabilities.v2"),
    ("capability-version-empty", ("query", "capabilities", "contract_version"), ""),
    ("capability-version-none", ("query", "capabilities", "contract_version"), None),
    ("capability-version-number", ("query", "capabilities", "contract_version"), 1),
    ("capability-version-upper-case", ("query", "capabilities", "contract_version"), "RUNTIME-CAPABILITIES.V1"),
    ("evidence-id-missing", ("query", "evidence_id"), _DELETE),
    ("capabilities-missing", ("query", "capabilities"), _DELETE),
    ("query-block-empty", ("query",), {}),
]


def _payload(root: Path) -> dict[str, Any]:
    """The complete, legal Resume v2 the real producer returns, as plain data."""

    return _query(root).model_dump(mode="python")


def _mutated(payload: dict[str, Any], path: tuple[str, ...], value: object) -> dict[str, Any]:
    changed = copy.deepcopy(payload)
    node = changed
    for key in path[:-1]:
        node = node[key]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return changed


def _unversioned_capabilities(version: object = _DELETE) -> RuntimeCapabilities:
    """A capability block that was never validated; without a version, or with a wrong one."""

    fields: dict[str, Any] = {"actions": ()}
    if version is not _DELETE:
        fields["contract_version"] = version
    return RuntimeCapabilities.model_construct(**fields)


def _unvalidated(root: Path, kind: str) -> ContinuityResume:
    """A Resume that was never validated: ``model_construct`` skips the checks, ``model_copy`` does not run them."""

    good = _query(root)
    assert good.query is not None
    if kind == "no-query-block":
        return good.model_copy(update={"query": None})
    fields = {name: getattr(good.query, name) for name in ContinuityQuery.model_fields if name != "schema_version"}
    return good.model_copy(update={"query": ContinuityQuery.model_construct(**fields)})


def test_both_versions_are_required_and_the_complete_legal_payload_is_accepted(tmp_path: Path) -> None:
    _workspace(tmp_path)
    payload = _payload(tmp_path)
    accepted = validate_query_resume(payload, require_query=True)  # the positive control: the same path accepts what the real producer returned
    assert accepted.model_dump(mode="python") == payload and accepted.query is not None
    assert validate_runtime_capabilities(accepted.query.capabilities) == accepted.query.capabilities
    assert validate_runtime_capabilities(payload["query"]["capabilities"]) == accepted.query.capabilities
    with pytest.raises(ValidationError):
        RuntimeCapabilities.model_validate({"actions": []})  # no default version is filled in any more
    with pytest.raises(ValidationError):
        ContinuityQuery.model_validate(_mutated(payload, ("query", "schema_version"), _DELETE)["query"])


@pytest.mark.parametrize("require_query", [True, False])
@pytest.mark.parametrize(("name", "path", "value"), _BROKEN_QUERIES, ids=[item[0] for item in _BROKEN_QUERIES])
def test_a_broken_query_block_is_refused_whatever_the_reader_asks_for(tmp_path: Path, name: str, path: tuple[str, ...], value: object, require_query: bool) -> None:
    _workspace(tmp_path)
    payload = _payload(tmp_path)
    with pytest.raises(ValueError, match="未通过校验"):
        validate_query_resume(_mutated(payload, path, value), require_query=require_query)


def test_a_capability_block_is_refused_without_a_valid_version_and_never_repaired() -> None:
    legal = {"contract_version": "runtime-capabilities.v1", "actions": []}
    assert validate_runtime_capabilities(legal).contract_version == "runtime-capabilities.v1"
    for version in (_DELETE, None, "", "runtime-capabilities.v2", 1, "RUNTIME-CAPABILITIES.V1"):
        broken: dict[str, Any] = {key: value for key, value in legal.items() if not (key == "contract_version" and version is _DELETE)}
        if version is not _DELETE:
            broken["contract_version"] = version
        with pytest.raises(ValueError, match="未通过校验"):
            validate_runtime_capabilities(broken)
    for not_a_block in ("runtime-capabilities.v1", 3, None):
        with pytest.raises(ValueError):
            validate_runtime_capabilities(not_a_block)


def test_a_missing_query_block_is_only_the_historical_read(tmp_path: Path) -> None:
    _workspace(tmp_path)
    payload = _payload(tmp_path)
    for old_style in ({key: value for key, value in payload.items() if key != "query"}, _mutated(payload, ("query",), None)):
        assert validate_query_resume(old_style, require_query=False).query is None  # the old reader still works
        with pytest.raises(ValueError, match="缺少 query"):
            validate_query_resume(old_style, require_query=True)  # a modern entry never downgrades to it


def test_model_construct_and_model_copy_cannot_get_past_the_check(tmp_path: Path) -> None:
    _workspace(tmp_path)
    broken = _unvalidated(tmp_path, "no-schema-version")
    assert broken.query is not None and not hasattr(broken.query, "schema_version")  # the object really lacks the version
    with pytest.raises(ValueError, match="未通过校验"):
        validate_query_resume(broken, require_query=True)
    for capabilities in (_unversioned_capabilities(), _unversioned_capabilities("runtime-capabilities.v2")):
        with pytest.raises(ValueError, match="未通过校验"):
            validate_runtime_capabilities(capabilities)


def test_the_producer_refuses_to_answer_with_a_capability_block_that_has_no_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _workspace(tmp_path)
    before = _snapshot(tmp_path)
    monkeypatch.setattr(ContinuityQueryService, "capabilities", staticmethod(_unversioned_capabilities))
    with pytest.raises(ContinuityQueryError, match="未通过校验"):
        _query(tmp_path)
    assert _snapshot(tmp_path) == before and not (tmp_path / ".auto-pm").exists()


@pytest.mark.parametrize("kind", ["no-schema-version", "no-query-block"])
def test_the_facade_refuses_what_a_replaced_producer_returns_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-Q-006")
    broken, before = _unvalidated(tmp_path, kind), _snapshot(tmp_path)
    monkeypatch.setattr(ContinuityQueryService, "query", lambda self, **_kwargs: broken)
    facade = PmFacadeService(tmp_path)
    calls: list[Callable[[], object]] = [lambda: facade.resume(project_id=PROJECT), lambda: facade.orient(project_id=PROJECT, requested_action="PARK")]
    for call in calls:
        with pytest.raises(PmFacadeError, match="未通过校验|缺少 query"):
            call()
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("kind", ["no-schema-version", "no-query-block"])
def test_the_sdk_refuses_what_an_injected_facade_returns(tmp_path: Path, kind: str) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-Q-007")
    broken, before = _unvalidated(tmp_path, kind), _snapshot(tmp_path)

    class _ReplacedFacade:
        def orient(
            self, *, project_id: str = "", invocation_path: str | None = None, work_id: str = "", run_id: str = "", requested_action: str = ""
        ) -> ContinuityResume:
            return broken

    client = CockpitClient(tmp_path, PROJECT, facade=cast(PmFacadeService, _ReplacedFacade()))
    with pytest.raises(CockpitApiError, match="未通过校验|缺少 query"):
        client.orient(requested_action="PARK")
    assert _snapshot(tmp_path) == before
