"""Real-Git, real-checker proofs for the V01 PLC static quality gate.

The synthetic PLC projects here are deliberately tiny: they are committed to a
throw-away repository so the gate never depends on a live workspace project.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionError,
    EvidenceCollectionService,
    PlcQualityReceipt,
)
from auto_pm.contracts.continuity import RunItem, RunState
from auto_pm.infrastructure.control_root_guard import clean_git_environment
from tests.git_support import git_out

_TIMESTAMP = "2026-10-03T00:00:00+00:00"
PROJECT = "0100_PLC/DJ-TEST-001"
# a minimal valid block: the structure rule (LSP-905-STRUCT-NO-BLOCK, M3-PLUGIN) rejects bare statements without a block header
GOOD_SCL = '// OB1\nORGANIZATION_BLOCK OB1\nBEGIN\n    ;\nEND_ORGANIZATION_BLOCK\n'
BAD_SCL = "FUNCTION_BLOCK FB_Bad\nVAR_INPUT\n    Start : Bool;\nEND_VAR\nEND_FUNCTION_BLOCK\n"
_PRD_FILES = (
    "需求分析文档_REQ.md",
    "接口文档_INT.md",
    "详细设计说明书_DSN.md",
    "技术方案文档_TEC.md",
)


def git(root: Path, *arguments: str) -> str:
    return git_out(root, *arguments, env=clean_git_environment())


def write_plc_project(root: Path, relative: str, *, scl_dir: str = "OB1") -> Path:
    """Create one minimal PLC project that the existing checker accepts."""

    project = root / relative
    name = project.name
    (project / scl_dir).mkdir(parents=True)
    (project / "PRD").mkdir()
    (project / ".plc.json").write_text(
        json.dumps({"name": name, "description": "synthetic", "version": "V1.0.0"}),
        encoding="utf-8",
    )
    (project / f"PM_SESSION_{name}.md").write_text(
        f"# PM_SESSION_{name}\n\n## 0. Meta\n- project_id: {name}\n", encoding="utf-8"
    )
    for file_name in _PRD_FILES:
        (project / "PRD" / file_name).write_text(f"# {file_name}\n", encoding="utf-8")
    (project / scl_dir / "OB1.scl").write_text(GOOD_SCL, encoding="utf-8")
    return project


def plc_workspace(
    tmp_path: Path,
    *,
    extra: tuple[str, ...] = (),
    second_project: bool = False,
    nested: bool = False,
) -> tuple[Path, Path, str]:
    """Commit PLC projects (and any ``extra`` files) and add a Run candidate worktree."""

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    git(workspace, "init")
    (workspace / ".gitignore").write_text(".auto-pm/\n*.cache\n", encoding="utf-8")
    write_plc_project(workspace, PROJECT)
    if second_project:
        write_plc_project(workspace, "0100_PLC/DJ-TEST-002")
    if nested:
        inner = workspace / PROJECT / "02_PLC程序" / "PLC_ST"
        inner.mkdir(parents=True)
        (inner / ".plc.json").write_text(
            json.dumps({"name": "nested", "description": "n", "version": "V1"}),
            encoding="utf-8",
        )
        (inner / "FB.scl").write_text(GOOD_SCL, encoding="utf-8")
        (workspace / ".plc.json").write_text("{}", encoding="utf-8")
    for relative in extra:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
    git(workspace, "add", ".")
    git(
        workspace,
        "-c", "user.name=PLC Gate Test",
        "-c", "user.email=plc-gate@example.invalid",
        "commit", "-m", "baseline",
    )
    baseline = git(workspace, "rev-parse", "HEAD")
    candidate = workspace / ".auto-pm" / "worktrees" / "plc-run"
    candidate.parent.mkdir(parents=True)
    git(workspace, "worktree", "add", "-b", "codex/plc-run", str(candidate), baseline)
    return workspace, candidate, baseline


def commit(root: Path, message: str) -> None:
    git(root, "add", ".")
    git(
        root,
        "-c", "user.name=PLC Gate Test",
        "-c", "user.email=plc-gate@example.invalid",
        "commit", "-m", message,
    )


def plc_run(candidate: Path, baseline: str, owned: tuple[str, ...]) -> RunItem:
    return RunItem(
        run_id="RUN-SW008-PMF-V01-001",
        work_id="WORK-SW008-PMF-V01-001",
        state=RunState.RUNNING,
        executor_id="codex",
        adapter="codex",
        owned_paths=owned,
        declared_dirty_paths=(),
        git_head=baseline,
        worktree_path=str(candidate.resolve()),
        version=1,
        created_at=_TIMESTAMP,
        updated_at=_TIMESTAMP,
    )


SCL = f"{PROJECT}/OB1/OB1.scl"
INT_DOC = f"{PROJECT}/PRD/接口文档_INT.md"


def _service(workspace: Path) -> EvidenceCollectionService:
    return EvidenceCollectionService(workspace)


def _gate_receipt(
    tmp_path: Path, *, scl_text: str | None = None, owned: tuple[str, ...] = (SCL,)
) -> tuple[EvidenceCollectionService, Path, RunItem, PlcQualityReceipt]:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    if scl_text is not None:
        (candidate / SCL).write_text(scl_text, encoding="utf-8")
    run = plc_run(candidate, baseline, owned)
    service = _service(workspace)
    return service, candidate, run, service.run_plc_checkpoint_quality_gates(run, candidate)


def test_p01_a_compliant_project_passes_with_check_and_lint_gates_bound_to_the_run(
    tmp_path: Path,
) -> None:
    service, candidate, run, receipt = _gate_receipt(tmp_path, scl_text=GOOD_SCL + "// edit\n")

    assert receipt.status == "PASS"
    assert [gate.name for gate in receipt.gates] == ["plc-check", "scl-lint"]
    assert all(gate.exit_code == 0 and gate.output_digest for gate in receipt.gates)
    assert receipt.project_roots == (str((candidate / PROJECT).resolve()),)
    assert receipt.owned_plc_paths == (SCL,)
    assert receipt.evidence_current is True
    assert receipt.baseline_git_head == run.git_head
    assert service.plc_quality_receipt_is_current(run, candidate, receipt)
    collection = service.collect(run)
    envelope = json.loads(service.build_checkpoint_evidence(collection, receipt))
    assert envelope["schema_version"] == "checkpoint-evidence.v3"
    assert envelope["quality_receipt"]["domain"] == "plc"
    assert service.checkpoint_evidence_is_current(
        service.build_checkpoint_evidence(collection, receipt), collection, run, candidate
    )


def test_p02_a_violating_owned_scl_fails_both_gates_and_names_file_and_line(
    tmp_path: Path,
) -> None:
    service, candidate, run, receipt = _gate_receipt(tmp_path, scl_text=BAD_SCL)

    assert receipt.status == "FAIL"
    assert [gate.exit_code for gate in receipt.gates] == [1, 1]
    lint = receipt.gates[1]
    assert "OB1/OB1.scl:3" in lint.output_summary
    assert "i_" in lint.output_summary
    assert "OB1.scl:3" in receipt.gates[0].output_summary
    head = receipt.gates[0].output_summary.splitlines()
    assert head[0].startswith("和 Run 开工基线 ") and "新增失败 1 条" in head[0]
    assert head[1].startswith("new | SCL 规范 · OB1/OB1.scl [")
    with pytest.raises(EvidenceCollectionError, match="不一致"):
        service.build_checkpoint_evidence(service.collect(run), receipt)
    assert not service.plc_quality_receipt_is_current(run, candidate, receipt)


def test_p03_a_violation_already_in_a_non_owned_scl_at_the_baseline_does_not_block(
    tmp_path: Path,
) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    other = candidate / PROJECT / "OB2"
    other.mkdir()
    # Committed baseline content cannot be produced after the fact, so build it on the
    # baseline worktree itself and re-pin the Run baseline to that commit.
    (other / "OB2.scl").write_text(BAD_SCL, encoding="utf-8")
    commit(candidate, "pre-existing violation")
    baseline = git(candidate, "rev-parse", "HEAD")
    run = plc_run(candidate, baseline, (SCL,))

    receipt = _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)

    assert receipt.status == "PASS"
    assert [(gate.name, gate.exit_code) for gate in receipt.gates] == [
        ("plc-check", 0),
        ("scl-lint", 0),
    ]
    summary = receipt.gates[0].output_summary
    assert "新增失败 0 条" in summary and "基线已有失败 1 条" in summary
    assert "known | SCL 规范 · OB2/OB2.scl [" in summary
    assert "fail | SCL 代码规范" in summary  # still shown, never hidden


def test_p04_a_checker_crash_or_not_applicable_verdict_is_a_failing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.plc.checker import PlcChecker
    from auto_pm.plc.models import CheckResult

    workspace, candidate, baseline = plc_workspace(tmp_path)
    run = plc_run(candidate, baseline, (INT_DOC,))
    service = _service(workspace)

    def crash(self: PlcChecker, project_path: str) -> CheckResult:
        raise RuntimeError("checker exploded")

    monkeypatch.setattr(PlcChecker, "check_project", crash)
    crashed = service.run_plc_checkpoint_quality_gates(run, candidate)
    assert crashed.status == "FAIL"
    assert crashed.gates[0].exit_code is None
    assert "launch error: checker exploded" in crashed.gates[0].output_summary

    def not_applicable(self: PlcChecker, project_path: str) -> CheckResult:
        result = CheckResult(project_path=project_path)
        result.not_applicable = True
        result.not_applicable_reason = "forced"
        return result

    monkeypatch.setattr(PlcChecker, "check_project", not_applicable)
    skipped = service.run_plc_checkpoint_quality_gates(run, candidate)
    assert skipped.status == "FAIL"
    assert skipped.gates[0].exit_code is None
    assert "不适用" in skipped.gates[0].output_summary


def test_p05_profile_is_plc_generic_or_refused_for_mixed_runs(tmp_path: Path) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path, extra=("tools/helper.py",))
    service = _service(workspace)

    assert service.checkpoint_profile_for_run(plc_run(candidate, baseline, (SCL, INT_DOC))) == "plc"
    assert service.checkpoint_profile_for_run(plc_run(candidate, baseline, ("tools/helper.py",))) == "generic"
    with pytest.raises(EvidenceCollectionError, match="一个 Run 只验证一个领域"):
        service.checkpoint_profile_for_run(plc_run(candidate, baseline, (SCL, "tools/helper.py")))
    with pytest.raises(EvidenceCollectionError, match="一个 Run 只验证一个领域"):
        service.run_plc_checkpoint_quality_gates(
            plc_run(candidate, baseline, (SCL, "tools/helper.py")), candidate
        )


def test_p06_project_root_is_the_highest_plc_json_directory_below_the_candidate(
    tmp_path: Path,
) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path, nested=True)
    nested_scl = f"{PROJECT}/02_PLC程序/PLC_ST/FB.scl"

    receipt = _service(workspace).run_plc_checkpoint_quality_gates(
        plc_run(candidate, baseline, (nested_scl, f"{PROJECT}/02_PLC程序/PLC_ST/.plc.json")),
        candidate,
    )

    assert receipt.project_roots == (str((candidate / PROJECT).resolve()),)
    assert receipt.gates[1].command[1:] == ("02_PLC程序/PLC_ST/FB.scl",)
    assert receipt.status == "PASS"


def test_p07_an_owned_directory_lints_every_scl_inside_it(tmp_path: Path) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    (candidate / PROJECT / "OB1" / "OB2.scl").write_text(BAD_SCL, encoding="utf-8")
    run = plc_run(candidate, baseline, (f"{PROJECT}/OB1",))

    receipt = _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)

    assert receipt.status == "FAIL"
    assert receipt.gates[1].command[1:] == ("OB1/OB1.scl", "OB1/OB2.scl")
    assert receipt.gates[1].exit_code == 1


def test_p08_two_plc_projects_get_separate_ordered_gates(tmp_path: Path) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path, second_project=True)
    run = plc_run(candidate, baseline, ("0100_PLC/DJ-TEST-002/OB1/OB1.scl", SCL))

    receipt = _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)

    assert receipt.status == "PASS"
    assert [gate.cwd for gate in receipt.gates] == [
        str((candidate / "0100_PLC" / project).resolve())
        for project in ("DJ-TEST-001", "DJ-TEST-001", "DJ-TEST-002", "DJ-TEST-002")
    ]
    assert [gate.name for gate in receipt.gates] == ["plc-check", "scl-lint"] * 2


def test_p09_missing_owned_scl_uncovered_root_and_no_plc_path_are_refused(
    tmp_path: Path,
) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path, extra=("tools/helper.py",))
    service = _service(workspace)

    with pytest.raises(EvidenceCollectionError, match="owned SCL path 不存在"):
        service.run_plc_checkpoint_quality_gates(
            plc_run(candidate, baseline, (f"{PROJECT}/OB1/Missing.scl",)), candidate
        )
    elsewhere = candidate / "0100_PLC" / "elsewhere"
    elsewhere.mkdir()
    with pytest.raises(EvidenceCollectionError, match="未覆盖 Run owned PLC path"):
        service.validate_plc_checkpoint_project_root(
            plc_run(candidate, baseline, (SCL,)), elsewhere
        )
    with pytest.raises(EvidenceCollectionError, match="缺少 PLC 工程内的 owned path"):
        service.validate_plc_checkpoint_project_root(
            plc_run(candidate, baseline, ("tools/helper.py",)), candidate
        )


def test_p10_foreign_dirty_paths_are_refused_before_any_gate_runs(tmp_path: Path) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    (candidate / PROJECT / "PRD" / "接口文档_INT.md").write_text("# edited\n", encoding="utf-8")
    run = plc_run(candidate, baseline, (SCL,))

    with pytest.raises(EvidenceCollectionError, match="超出 owned_paths"):
        _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)


def test_p11_a_receipt_goes_stale_when_an_owned_file_changes(tmp_path: Path) -> None:
    service, candidate, run, receipt = _gate_receipt(tmp_path, owned=(SCL, INT_DOC))
    assert service.plc_quality_receipt_is_current(run, candidate, receipt)

    (candidate / INT_DOC).write_text("# 接口文档\nI-001 changed\n", encoding="utf-8")

    assert not service.plc_quality_receipt_is_current(run, candidate, receipt)


def test_p12_a_changed_git_ignored_input_invalidates_a_receipt_git_cannot_see(
    tmp_path: Path,
) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    cache = candidate / PROJECT / "OB1" / "scan.cache"
    cache.write_text("v1", encoding="utf-8")
    run = plc_run(candidate, baseline, (SCL,))
    service = _service(workspace)
    receipt = service.run_plc_checkpoint_quality_gates(run, candidate)
    before = service.collect(run).content_hash
    assert service.plc_quality_receipt_is_current(run, candidate, receipt)

    cache.write_text("v2", encoding="utf-8")

    assert service.collect(run).content_hash == before
    assert not service.plc_quality_receipt_is_current(run, candidate, receipt)
    envelope = service.build_checkpoint_evidence(service.collect(run), receipt)
    assert not service.checkpoint_evidence_is_current(
        envelope, service.collect(run), run, candidate
    )


def test_p13_an_input_changed_during_the_gate_run_is_not_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    run = plc_run(candidate, baseline, (SCL,))
    service = _service(workspace)
    original = EvidenceCollectionService._run_plc_gate

    def mutating(*args: Any, **kwargs: Any) -> Any:
        (candidate / PROJECT / "OB1" / "late.cache").write_text("late", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(EvidenceCollectionService, "_run_plc_gate", staticmethod(mutating))

    receipt = service.run_plc_checkpoint_quality_gates(run, candidate)

    assert receipt.evidence_current is False
    assert receipt.status == "FAIL"
    assert receipt.evidence_error is not None and "PLC 输入已变化" in receipt.evidence_error


def test_p14_a_different_checker_build_makes_the_stored_evidence_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, candidate, run, receipt = _gate_receipt(tmp_path)
    collection = service.collect(run)
    envelope = service.build_checkpoint_evidence(collection, receipt)
    assert service.checkpoint_evidence_is_current(envelope, collection, run, candidate)
    assert len(receipt.checker_digest) == 64

    monkeypatch.setattr(
        EvidenceCollectionService, "_plc_checker_digest", staticmethod(lambda: "0" * 64)
    )

    assert not service.plc_quality_receipt_is_current(run, candidate, receipt)
    assert not service.checkpoint_evidence_is_current(envelope, collection, run, candidate)


def _resign(envelope: dict[str, Any]) -> str:
    """Re-sign a tampered envelope so only the semantic checks can reject it."""

    from auto_pm.application.core.evidence_collection_service import (
        _canonical_json_payload,
        _sha256_payload,
    )

    unsigned = {key: value for key, value in envelope.items() if key != "envelope_hash"}
    receipt = {k: v for k, v in envelope["quality_receipt"].items() if k != "status"}
    unsigned["receipt_hash"] = _sha256_payload(receipt)
    return _canonical_json_payload({**unsigned, "envelope_hash": _sha256_payload(unsigned)})


@pytest.mark.parametrize(
    "tamper",
    [
        "failing_exit_code",
        "dropped_gate",
        "foreign_project_root",
        "wrong_domain",
        "empty_output_digest",
        "unsigned_edit",
    ],
)
def test_p15_tampered_v3_evidence_is_rejected_even_when_re_signed(
    tmp_path: Path, tamper: str
) -> None:
    service, candidate, run, receipt = _gate_receipt(tmp_path)
    collection = service.collect(run)
    serialized = service.build_checkpoint_evidence(collection, receipt)
    envelope = json.loads(serialized)
    quality = envelope["quality_receipt"]
    if tamper == "failing_exit_code":
        quality["gates"][0]["exit_code"] = 1
    elif tamper == "dropped_gate":
        quality["gates"] = quality["gates"][:1]
    elif tamper == "foreign_project_root":
        quality["project_roots"] = [str(candidate)]
    elif tamper == "wrong_domain":
        quality["domain"] = "python"
    elif tamper == "empty_output_digest":
        quality["gates"][1]["output_digest"] = ""
    if tamper == "unsigned_edit":
        quality["owned_plc_paths"] = ["x"]
        tampered = json.dumps(envelope, ensure_ascii=False)
    else:
        tampered = _resign(envelope)

    assert not service.checkpoint_evidence_is_current(tampered, collection, run, candidate)
    assert service.checkpoint_evidence_is_current(serialized, collection, run, candidate)


def test_p16_warnings_do_not_fail_the_gate_but_stay_in_the_recorded_output(
    tmp_path: Path,
) -> None:
    _, _, _, receipt = _gate_receipt(tmp_path)

    assert receipt.status == "PASS"
    assert "warn | .plc.json libraries" in receipt.gates[0].output_summary
    assert "fail=0" in receipt.gates[0].output_summary


def test_p15_a_wedged_gate_fails_with_a_timeout_instead_of_hanging_the_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from auto_pm.application.core import evidence_collection_service as module

    release = threading.Event()
    workspace, candidate, baseline = plc_workspace(tmp_path)
    run = plc_run(candidate, baseline, (SCL,))

    def wedged(*_: Any, **__: Any) -> tuple[str, int | None]:
        release.wait(30)
        return "never", 0

    monkeypatch.setattr(module, "_scl_lint_output", wedged)
    monkeypatch.setenv("AUTO_PM_QUALITY_GATE_TIMEOUT_SECONDS", "0.3")
    try:
        receipt = _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)
    finally:
        release.set()

    lint = next(gate for gate in receipt.gates if gate.name == "scl-lint")
    assert lint.exit_code is None
    assert "timeout" in lint.output_summary and "0.3" in lint.output_summary
    assert receipt.status == "FAIL"


@pytest.mark.parametrize("raw", ["", "abc", "0", "-5"])
def test_p16_an_unusable_timeout_setting_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    from auto_pm.application.core import evidence_collection_service as module

    monkeypatch.setenv("AUTO_PM_QUALITY_GATE_TIMEOUT_SECONDS", raw)

    assert module._quality_gate_timeout_seconds() == module._QUALITY_GATE_TIMEOUT_DEFAULT_SECONDS


def test_p17_a_gate_that_raises_still_reports_a_launch_error_not_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core import evidence_collection_service as module

    workspace, candidate, baseline = plc_workspace(tmp_path)
    run = plc_run(candidate, baseline, (SCL,))

    def broken(*_: Any, **__: Any) -> tuple[str, int | None]:
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "_scl_lint_output", broken)
    receipt = _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)

    lint = next(gate for gate in receipt.gates if gate.name == "scl-lint")
    assert lint.exit_code is None and "launch error: boom" in lint.output_summary


def test_p18_a_python_quality_command_that_never_ends_fails_with_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setenv("AUTO_PM_QUALITY_GATE_TIMEOUT_SECONDS", "0.5")
    gate = EvidenceCollectionService._run_quality_gate(
        "pytest", (sys.executable, "-c", "import time; time.sleep(60)"), tmp_path, None
    )

    assert gate.exit_code is None and not gate.passed
    assert "timeout" in gate.output_summary


def test_p19_a_git_evidence_call_is_bounded_and_a_timeout_is_a_clear_collection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    from auto_pm.application.core import evidence_collection_service as module

    seen: dict[str, Any] = {}

    def hung(command: list[str], **kwargs: Any) -> Any:
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", hung)

    with pytest.raises(EvidenceCollectionError, match="超时回执"):
        EvidenceCollectionService._git_output(tmp_path, "status")

    assert seen["timeout"] == module._GIT_EVIDENCE_TIMEOUT_SECONDS > 0
