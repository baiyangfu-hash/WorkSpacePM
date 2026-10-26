"""V05-B: the cockpit reads and writes through the governed control root while it runs from a linked candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from auto_pm.core.pm_cockpit_service import PmCockpitService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.pm_facade import PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.git_support import git_do

PROJECT = "SW-2026-008"


def _git(root: Path, *args: str) -> None:
    git_do(root, *args, config=['user.name=Dual Root', 'user.email=dual@example.invalid'])


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    """A governed main root and a linked candidate worktree of it, both holding the registry."""

    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init")
    (main / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    project = main / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(f"project_id: {PROJECT}\nproject_name: Dual Root\nstack: python\n", encoding="utf-8")
    registry = main / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
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
    _git(main, "add", "-A")
    _git(main, "commit", "-m", "baseline")
    candidate = tmp_path / "candidate"
    _git(main, "worktree", "add", "--detach", str(candidate))
    return main, candidate


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


def _intent(request_id: str) -> PmIntent:
    return PmIntent(
        request_id=request_id,
        subject_project_id=PROJECT,
        objective="dual root draft",
        acceptance_criteria=("the draft lands in the control root",),
    )


def _store_files(root: Path) -> dict[str, str]:
    base = root / ".auto-pm"
    if not base.exists():
        return {}
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()}


def test_the_service_reads_the_registry_and_the_store_of_the_control_root_and_creates_nothing_in_the_candidate(tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    _work(main, "WORK-DUAL-001")
    service = PmCockpitService(candidate, control_root=main)
    snapshot = service.snapshot()
    assert [card.project_id for card in snapshot.projects] == [PROJECT]
    assert service._store.db_path == ContinuityStore(main).db_path
    try:
        read_set = service.evidence(PROJECT).read_set
    except ValueError as error:  # a path presented relative to the wrong root
        read_set = (f"raised: {error}",)
    assert read_set == (
        "SYS-2026-001_WorkspaceGovernance/workspace_registry.json",
        ContinuityStore(main).db_path.relative_to(main.resolve()).as_posix(),
    )
    assert not (candidate / ".auto-pm").exists()


def test_without_a_control_root_the_service_behaves_exactly_as_before(tmp_path: Path) -> None:
    main, _candidate = _roots(tmp_path)
    service = PmCockpitService(main)
    assert service._control_root == service._workspace_root == main.resolve()
    assert [card.project_id for card in service.snapshot().projects] == [PROJECT]


def test_the_real_facade_is_built_on_the_control_root_with_the_candidate_as_execution_root(tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    facade = PmCockpitService(candidate, control_root=main)._real_facade()
    assert isinstance(facade, PmFacadeService)
    assert facade._workspace_root == main.resolve()
    assert facade._execution_root == candidate.resolve()


def test_a_write_through_the_dual_root_facade_lands_in_the_control_root_only(tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    _work(main, "WORK-DUAL-003")  # initialises the control store
    facade = PmCockpitService(candidate, control_root=main)._real_facade()
    draft = facade.create_planning_draft(_intent("REQ-DUAL-001"))
    assert draft.subject_project_id == PROJECT
    assert ContinuityStore(main).get_planning_draft("REQ-DUAL-001") == draft
    assert not (candidate / ".auto-pm").exists()


def test_swapped_roots_are_refused_and_nothing_is_written_anywhere(tmp_path: Path) -> None:
    main, candidate = _roots(tmp_path)
    _work(main, "WORK-DUAL-002")
    before_main = _store_files(main)
    facade = PmCockpitService(main, control_root=candidate)._real_facade()
    with pytest.raises(PmFacadeError):
        facade.create_planning_draft(_intent("REQ-DUAL-002"))
    assert _store_files(main) == before_main
    assert not (candidate / ".auto-pm").exists()
    assert ContinuityStore(main).list_planning_drafts(PROJECT) == ()
