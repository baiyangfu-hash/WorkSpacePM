"""D1: a document-only Run reaches (or is kept from) the acceptance gate through the ``docs`` profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import docs_checkpoint
from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.evidence_collection_service import EvidenceCollectionService
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import RunState, WorkKind
from auto_pm.contracts.mission import MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_continuity_execution_service import Clock, _start
from tests.core.test_plc_checkpoint_chain import _append_plc, _plc_continuity_service, _plc_env
from tests.core.test_plc_quality_gate import plc_workspace
from tests.core.test_pm_run_e2e import NOT_VERIFIED_SENTENCE, VERIFIED_SENTENCE

DOC = "specs/plc.md"
EDITED_DOC = "# 规范\n\n新增一行说明。\n"


def _service_for(tmp_path: Path, owned: tuple[str, ...]) -> tuple[Path, ContinuityExecutionService]:
    workspace, candidate, baseline = plc_workspace(tmp_path, extra=(DOC, "tools/helper.py"))
    clock = Clock()
    work = WorkRegistryService(workspace, now=lambda: clock().isoformat())
    work.initialize("test")
    work.create_work(
        work_id="WORK-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="D1 docs automatic checkpoint",
        owner="architect",
        scope_paths=list(owned),
        source_fingerprint="sha256:d1",
        idempotency_key="create-d1-work",
        read_only=True,
    )
    service = ContinuityExecutionService(
        workspace, store=ContinuityStore(workspace, _clock=clock), now=clock
    )
    _start(
        service,
        owned_paths=list(owned),
        worktree_path=str(candidate),
        git_head=baseline,
        declared_dirty_paths=[],
        observed_dirty_paths=[],
    )
    return candidate, service


def _docs_service(
    tmp_path: Path, *, owned: tuple[str, ...] = (DOC,), text: str | None = EDITED_DOC
) -> tuple[Path, ContinuityExecutionService]:
    candidate, service = _service_for(tmp_path, owned)
    if text is not None:
        (candidate / DOC).write_text(text, encoding="utf-8")
    return candidate, service


def _append_docs(service: ContinuityExecutionService, root: Path, **changes: Any) -> Any:
    return _append_plc(service, root, profile="docs", checkpoint_id="CP-DOCS-001", **changes)


def test_d01_a_document_only_run_is_verified_and_opens_the_acceptance_gate(tmp_path: Path) -> None:
    env = _plc_env(tmp_path, files={DOC: EDITED_DOC}, scope=(DOC,))

    outcome = env.run()

    assert outcome.verified is True, outcome
    assert outcome.message == VERIFIED_SENTENCE
    assert outcome.mission_state is MissionState.ACCEPTANCE_PENDING
    checkpoint = env.store.get_checkpoint(outcome.checkpoint_id)
    envelope = json.loads(checkpoint.evidence[0])
    assert envelope["schema_version"] == "checkpoint-evidence.v4"
    assert [gate["name"] for gate in envelope["quality_receipt"]["gates"]] == [
        "docs-encoding",
        "docs-syntax",
    ]
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""
    assert env.facade.accept(outcome.mission_id).mission_state is MissionState.ACCEPTED


def test_d02_a_non_utf8_document_is_not_verified_and_keeps_the_scene(tmp_path: Path) -> None:
    env = _plc_env(tmp_path, files={DOC: EDITED_DOC}, scope=(DOC,))
    original = env.run
    # Break the file after the executor wrote it: write bytes that are not UTF-8.
    outcome = original()
    worktree = Path(env.store.get_run(outcome.run_id).worktree_path)
    (worktree / DOC).write_bytes("规范".encode("gbk"))

    assert env.facade.acceptance_gate_reason(outcome.mission_id) != ""
    assert env.latest_run()[1] is RunState.VERIFYING


def test_d03_a_document_changed_after_verification_closes_the_gate(tmp_path: Path) -> None:
    env = _plc_env(tmp_path, files={DOC: EDITED_DOC}, scope=(DOC,))
    outcome = env.run()
    worktree = Path(env.store.get_run(outcome.run_id).worktree_path)

    (worktree / DOC).write_text(EDITED_DOC + "sneaked in\n", encoding="utf-8")

    assert env.facade.acceptance_gate_reason(outcome.mission_id) != ""


def test_d04_json_syntax_and_conflict_markers_fail_the_syntax_gate(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path, text="# t\n<<<<<<< HEAD\nx\n>>>>>>> other\n")

    with pytest.raises(ContinuityExecutionError, match="docs-syntax"):
        _append_docs(service, candidate)
    assert service._store.latest_checkpoint("RUN-001") is None


def test_d05_non_utf8_fails_the_encoding_gate(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path, text=None)
    (candidate / DOC).write_bytes("规范".encode("gbk"))

    with pytest.raises(ContinuityExecutionError, match="docs-encoding"):
        _append_docs(service, candidate)


def test_d06_the_docs_profile_refuses_code_files_so_it_is_no_way_around_the_gates(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path, owned=(DOC, "tools/helper.py"))

    with pytest.raises(ContinuityExecutionError, match="只收文档/图纸/配置类文件"):
        _append_docs(service, candidate)
    # An owned directory that holds a code file is refused the same way.
    candidate, service = _docs_service(tmp_path / "dir", owned=("tools",), text=None)
    with pytest.raises(ContinuityExecutionError, match="只收文档/图纸/配置类文件"):
        _append_docs(service, candidate)


REFUSED_NAMES = (
    "tools/q.sql", "tools/a.rb", "tools/a.go", "tools/A.java", "tools/a.rs", "tools/a.php",
    "tools/a.pl", "tools/a.lua", "tools/a.vb", "tools/a.exe", "tools/a.dll", "tools/a.pyc",
    "tools/a.ps1", "tools/a.scl", "tools/a.st", "tools/a.bat", "tools/Makefile", "tools/Dockerfile",
)


@pytest.mark.parametrize("name", REFUSED_NAMES)
def test_d06b_only_known_document_suffixes_are_accepted_everything_else_is_refused(
    tmp_path: Path, name: str
) -> None:
    candidate, service = _docs_service(tmp_path, owned=(DOC, name))
    (candidate / name).parent.mkdir(parents=True, exist_ok=True)
    (candidate / name).write_bytes(b"echo not a document\n")

    with pytest.raises(ContinuityExecutionError, match="只收文档/图纸/配置类文件"):
        _append_docs(service, candidate)
    assert service._store.latest_checkpoint("RUN-001") is None


def test_d06c_binary_office_and_drawing_files_are_accepted_by_digest_only(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path, owned=(DOC, "drawings/a.dwg", "docs/b.pdf"))
    for name in ("drawings/a.dwg", "docs/b.pdf"):
        (candidate / name).parent.mkdir(parents=True, exist_ok=True)
        (candidate / name).write_bytes(b"\x00\xff binary payload \x00")

    checkpoint = _append_docs(service, candidate)

    receipt = json.loads(checkpoint.evidence[0])["quality_receipt"]
    assert {item["path"] for item in receipt["input_digests"]} == {DOC, "drawings/a.dwg", "docs/b.pdf"}
    assert receipt["gates"][0]["exit_code"] == 0  # NUL in binary files is not a text problem


def test_d05b_a_nul_byte_in_a_markdown_file_fails_the_encoding_gate(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path, text=None)
    (candidate / DOC).write_bytes(b"# title\nbody\x00more\n")

    with pytest.raises(ContinuityExecutionError, match="docs-encoding"):
        _append_docs(service, candidate)
    assert service._store.latest_checkpoint("RUN-001") is None


def test_d07b_a_gitignored_owned_file_is_bound_by_its_input_digest(tmp_path: Path) -> None:
    ignored = "specs/ignored.md"
    candidate, service = _docs_service(tmp_path, owned=(DOC, ignored))
    exclude = service._root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(ignored + "\n", encoding="utf-8")
    (candidate / ignored).write_text("# 被忽略的文档\n", encoding="utf-8")
    collector = EvidenceCollectionService(service._root)
    run = service._store.get_run("RUN-001")
    first = _append_docs(service, candidate)
    git_view = collector.collect(run).content_hash
    assert _append_docs(service, candidate) == first  # untouched: replays

    (candidate / ignored).write_text("# 被忽略的文档\n\n悄悄改了一行\n", encoding="utf-8")

    # Git cannot see the edit at all ...
    assert collector.collect(run).content_hash == git_view
    # ... so only the per-file input digest can stop the stored checkpoint from replaying.
    with pytest.raises(ContinuityExecutionError, match="identity.*不一致"):
        _append_docs(service, candidate)


def test_d07c_a_stored_checkpoint_dies_when_the_checker_rules_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, service = _docs_service(tmp_path)
    first = _append_docs(service, candidate)
    assert _append_docs(service, candidate) == first

    # Same documents, same Git evidence, but the rules that produced the verdict changed.
    monkeypatch.setattr(docs_checkpoint, "checker_digest", lambda: "f" * 64)

    with pytest.raises(ContinuityExecutionError, match="identity.*不一致"):
        _append_docs(service, candidate)


def test_d07_a_stored_docs_checkpoint_replays_and_dies_with_the_document(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path)
    first = _append_docs(service, candidate)
    assert _append_docs(service, candidate) == first

    (candidate / DOC).write_text(EDITED_DOC + "later\n", encoding="utf-8")

    with pytest.raises(ContinuityExecutionError, match="identity.*不一致"):
        _append_docs(service, candidate)


def test_d08_profile_is_chosen_by_what_the_run_owns(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path)
    run = service._store.get_run("RUN-001")
    collector = EvidenceCollectionService(service._root)
    assert collector.checkpoint_profile_for_run(run) == "docs"
    candidate2, service2 = _docs_service(tmp_path / "py", owned=(DOC, "tools/helper.py"))
    assert (
        EvidenceCollectionService(service2._root).checkpoint_profile_for_run(
            service2._store.get_run("RUN-001")
        )
        == "generic"
    )
    candidate3, service3 = _plc_continuity_service(tmp_path / "plc")
    assert (
        EvidenceCollectionService(service3._root).checkpoint_profile_for_run(
            service3._store.get_run("RUN-001")
        )
        == "plc"
    )
    assert NOT_VERIFIED_SENTENCE


def test_d3_d4_a_foreign_dirty_file_and_a_moved_head_explain_what_to_do(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path)
    (candidate / "elsewhere.md").write_text("register wrote me\n", encoding="utf-8")
    with pytest.raises(ContinuityExecutionError, match=r"超出 owned_paths.*隔离工位"):
        _append_docs(service, candidate)
    (candidate / "elsewhere.md").unlink()

    import subprocess  # noqa: PLC0415

    subprocess.run(["git", "-C", str(candidate), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(candidate), "-c", "user.name=t", "-c", "user.email=t@e.invalid",
         "commit", "-qm", "work commit"],
        check=True,
    )
    with pytest.raises(ContinuityExecutionError, match=r"HEAD 不一致.*continuity run start"):
        _append_docs(service, candidate)
