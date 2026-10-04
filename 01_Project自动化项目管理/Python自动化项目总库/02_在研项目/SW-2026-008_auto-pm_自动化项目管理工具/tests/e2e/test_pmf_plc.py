"""Real-process, real-Git, real-gate proofs: a new PLC requirement on the pinned, healed benchmark DJ-2026-005 (V02).

The benchmark is materialised byte-for-byte from the pinned commit into a throw-away repository, so the live workspace is never touched.
The execution agent is a scripted stand-in for ``codex exec`` (a real child process that speaks the handshake and writes real SCL and
documents); everything else - approval chain, isolated worktree, the V01 PLC static gate with the V01B document/code consistency check,
the acceptance gate, the closure and the ledger - is the production code. Nothing here compiles or downloads to a controller.
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import textwrap
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.ledger_reconciler import LedgerReconciler
from auto_pm.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.plc import doc_consistency as dc

from auto_pm.contracts.continuity import RunState, WorkState
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PmIntent
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from tests.core.test_pm_run_e2e import NOT_VERIFIED_SENTENCE, VERIFIED_SENTENCE, _Env

if TYPE_CHECKING:
    from auto_pm.application.core.pm_closure_service import ClosureCompletionState, PmClosureService
    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
else:
    from auto_pm.core.pm_closure_service import ClosureCompletionState, PmClosureService
    from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

PIN_COMMIT = "1e1ef760c6f9c8814dbe47d681da760c887d28ee"
PIN_TREE = "ae8ff3a787936702a6d5df5ce3aadaecc3cb4eed"
PROJECT_ID = "DJ-2026-005"
PROJECT = "0100_PLC自动化/DJ-2026-005"
ALARM_DIR = f"{PROJECT}/02_PLC程序/PLC_ST/05_公共报警"
STRUCT = f"{ALARM_DIR}/ST_CommonAlarm.scl"
BLOCK = f"{ALARM_DIR}/FB_2001_CommonAlarm_AllStation.scl"
VAR_DOC = f"{PROJECT}/02_PLC程序/程序文档/{dc.VAR_DOC_NAME}"
SCOPE = tuple(sorted((STRUCT, BLOCK, VAR_DOC)))

STRUCT_ANCHOR = "    o_bNewAlarmFlag             : BOOL := FALSE;   // 新报警标志\n"
STRUCT_ADDED = "    o_bBuzzer                   : BOOL := FALSE;   // 报警蜂鸣器输出（任意报警激活时置位）\n"
BLOCK_ANCHOR = "s_wPrevGlobalAlarmWord := io_stGlobal.o_wGlobalAlarmWord;\n"
BLOCK_ADDED = "\n(* 10. 蜂鸣器输出：任意报警激活时置位 *)\nio_stGlobal.o_bBuzzer := io_stGlobal.o_bAnyAlarmActive;\n"
DOC_ANCHOR = "| o_bAnyAlarmActive | BOOL | 任意报警激活 |\n"
DOC_ADDED = "| o_bBuzzer | BOOL | 报警蜂鸣器输出（任意报警激活时置位） |\n"

Mutation = Callable[[dict[str, str]], dict[str, str]]


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false", *arguments],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def benchmark_tar() -> bytes:
    """The pinned benchmark directory as a tar stream; the tree SHA proves it is the approved content."""

    repository = Path(git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel"))
    observed = git(repository, "rev-parse", f"{PIN_COMMIT}:{PROJECT}")
    assert observed == PIN_TREE, f"benchmark drifted or the pinned commit is unavailable: {observed}"
    return subprocess.run(
        ["git", "-C", str(repository), "archive", "--format=tar", PIN_COMMIT, PROJECT], check=True, capture_output=True
    ).stdout


def build_workspace(root: Path, benchmark: bytes) -> None:
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "V02 Test")
    git(root, "config", "user.email", "v02@example.invalid")
    # The production repository fixes line endings the same way; without it Git prints CRLF warnings that the governed snapshot refuses.
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.safecrlf", "false")
    (root / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8", newline="\n")
    with tarfile.open(fileobj=io.BytesIO(benchmark)) as archive:
        archive.extractall(root, filter="data")
    # The benchmark brings its own project marker; ChangeFileLocator finds the project through it, so prove it is really there.
    assert os.path.isfile(os.path.join(str(root), PROJECT, ".plc.json"))
    (root / "specs").mkdir()
    (root / "specs" / "plc.md").write_text("plc", encoding="utf-8")
    (root / "specs" / "python.md").write_text("python", encoding="utf-8")
    registry = root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "specs": {
                    "DEV-TEST": {"domain": "python", "lifecycle": "stable", "canonical_path": "specs/python.md", "version": "V1"},
                    "LSP-TEST": {"domain": "plc", "lifecycle": "active", "canonical_path": "specs/plc.md", "version": "V1"},
                }
            }
        ),
        encoding="utf-8",
    )
    workspace = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    workspace.parent.mkdir(parents=True)
    workspace.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [{"project_id": PROJECT_ID, "project_root": PROJECT, "development_root": PROJECT}],
            }
        ),
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(".auto-pm/\n__pycache__/\n*.cache\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "baseline")


def requirement_files(root: Path, *, document: bool = True) -> dict[str, str]:
    """The new requirement: the common alarm block gets a buzzer output that follows 'any alarm active'."""

    struct = (root / STRUCT).read_text(encoding="utf-8")
    block = (root / BLOCK).read_text(encoding="utf-8")
    assert struct.count(STRUCT_ANCHOR) == 1 and block.count(BLOCK_ANCHOR) == 1
    files = {
        STRUCT: struct.replace(STRUCT_ANCHOR, STRUCT_ANCHOR + STRUCT_ADDED),
        BLOCK: block.replace(BLOCK_ANCHOR, BLOCK_ANCHOR + BLOCK_ADDED),
    }
    if document:
        doc = (root / VAR_DOC).read_text(encoding="utf-8")
        assert doc.count(DOC_ANCHOR) == 1
        files[VAR_DOC] = doc.replace(DOC_ANCHOR, DOC_ANCHOR + DOC_ADDED)
    return files


def helper_source(files: dict[str, str], counter: Path) -> str:
    """A real child process that speaks the handshake, writes real files and exits."""

    return textwrap.dedent(
        f"""\
        import json, pathlib, sys, time
        repo = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])
        with open({str(counter)!r}, 'a', encoding='utf-8') as handle:
            handle.write('start\\n')
        print(json.dumps({{'type': 'thread.started', 'thread_id': 'thread-v02'}}), flush=True)
        for relative, text in {files!r}.items():
            (repo / relative).write_text(text, encoding='utf-8', newline='\\n')
        time.sleep(0.15)
        sys.exit(0)
        """
    )


def plc_env(
    tmp_path: Path,
    benchmark: bytes,
    *,
    document: bool = True,
    mutate: Mutation | None = None,
    scope: tuple[str, ...] = SCOPE,
) -> _Env:
    root = (tmp_path / "ws").resolve()
    build_workspace(root, benchmark)
    files = requirement_files(root, document=document)
    if mutate is not None:
        files = mutate(files)
    counter = tmp_path / "starts.txt"
    helper = tmp_path / "fake_codex.py"
    helper.write_text(helper_source(files, counter), encoding="utf-8")
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "v02-e2e")
    changes = ChangeService(str(root))
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))
    facade = PmFacadeService(
        root,
        store=store,
        change_service=changes,
        local_orchestrator=LocalExecutionOrchestrator(root, store=store, executor=executor),
    )
    grant = PlanningExecutionGrant(adapter=ExecutionAdapterKind.CODEX, approved_model="agent-a", declared_dirty_paths=scope)
    card = facade.create_planning_scope_card(
        PmIntent(
            request_id="REQ-V02-BUZZER",
            subject_project_id=PROJECT_ID,
            objective="公共报警新增蜂鸣器输出：任意报警激活时置位",
            acceptance_criteria=("ST_CommonAlarm 新增 o_bBuzzer", "FB_2001 在任意报警激活时置位 o_bBuzzer", "变量定义文档同步"),
        ),
        scope_paths=scope,
        risks=("none",),
        non_goals=("no hardware download",),
        execution_grant=grant,
    )
    for state in ("submitted", "under_review", "approved"):
        changes.transition_status(card.change_id, state, approver="fubai", comment="human", project_id=PROJECT_ID)
    facade.approve_planning_scope_card(
        card, expected_plan_hash=card.plan_hash, approver="fubai", approval_evidence_ref="user-confirmation:V02-PLC-E2E"
    )
    return _Env(root, store, facade, changes, card, counter, secrets.token_urlsafe(32))


def candidate(env: _Env, run_id: str) -> Path:
    return Path(env.store.get_run(run_id).worktree_path)


def test_p01_a_new_plc_requirement_runs_to_acceptance_closure_and_a_clean_ledger(tmp_path: Path, benchmark_tar: bytes) -> None:
    env = plc_env(tmp_path, benchmark_tar)

    outcome = env.run()

    assert outcome.verified is True
    assert outcome.message == VERIFIED_SENTENCE
    assert outcome.mission_state is MissionState.ACCEPTANCE_PENDING
    checkpoint = env.store.get_checkpoint(outcome.checkpoint_id)
    assert json.loads(checkpoint.evidence[0])["schema_version"] == "checkpoint-evidence.v3"
    worktree = candidate(env, outcome.run_id)
    assert STRUCT_ADDED in (worktree / STRUCT).read_text(encoding="utf-8")
    assert "io_stGlobal.o_bBuzzer := io_stGlobal.o_bAnyAlarmActive;" in (worktree / BLOCK).read_text(encoding="utf-8")
    analysis = dc.analyze_project(str(worktree / PROJECT))
    assert [f for f in analysis.findings if f.severity == "fail"] == [] and analysis.marked_rows == []
    assert git(env.root, "diff", "--name-only", "--", *SCOPE) == ""  # the control root still holds the benchmark bytes
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""

    assert env.facade.accept(outcome.mission_id).mission_state is MissionState.ACCEPTED
    service = PmClosureService(env.root, store=env.store)
    preparation = service.prepare_closure(outcome.mission_id, idempotency_key="v02-prepare")
    receipt = service.complete_closure(preparation.closure.closure_id, idempotency_key="v02-complete")

    assert receipt.state is ClosureCompletionState.COMPLETED
    assert receipt.run_state is RunState.SUCCEEDED
    assert receipt.work_state is WorkState.CLOSED
    assert receipt.mission_state is MissionState.CLOSED
    change = next(env.root.glob(f"**/{env.card.change_id}.md")).read_text(encoding="utf-8")
    assert outcome.checkpoint_id in change and STRUCT in change and BLOCK in change and VAR_DOC in change
    assert LedgerReconciler().reconcile(str(env.root)).is_clean


def test_p02_scl_changed_without_its_document_is_not_verified(tmp_path: Path, benchmark_tar: bytes) -> None:
    env = plc_env(tmp_path, benchmark_tar, document=False, scope=(BLOCK, STRUCT))

    outcome = env.run()

    assert outcome.verified is False
    assert outcome.message == NOT_VERIFIED_SENTENCE
    assert env.mission_state() is MissionState.ACTIVE
    assert env.latest_run()[1] is RunState.VERIFYING
    assert env.checkpoint_count() == 0
    with pytest.raises(PmFacadeError):
        env.facade.accept(outcome.mission_id)


def test_p03_a_document_row_with_the_wrong_type_is_not_verified(tmp_path: Path, benchmark_tar: bytes) -> None:
    def wrong_type(files: dict[str, str]) -> dict[str, str]:
        files[VAR_DOC] = files[VAR_DOC].replace("| o_bBuzzer | BOOL |", "| o_bBuzzer | INT |")
        return files

    env = plc_env(tmp_path, benchmark_tar, mutate=wrong_type)

    outcome = env.run()

    assert outcome.verified is False
    assert env.checkpoint_count() == 0
    assert env.mission_state() is MissionState.ACTIVE


def test_p04_a_forbidden_scl_statement_is_not_verified(tmp_path: Path, benchmark_tar: bytes) -> None:
    def add_goto(files: dict[str, str]) -> dict[str, str]:
        files[BLOCK] = files[BLOCK].replace(BLOCK_ADDED, BLOCK_ADDED + "GOTO lbl;\n")
        return files

    env = plc_env(tmp_path, benchmark_tar, mutate=add_goto)

    outcome = env.run()

    assert outcome.verified is False
    assert env.checkpoint_count() == 0
    with pytest.raises(PmFacadeError):
        env.facade.accept(outcome.mission_id)


def test_p05_a_scope_declared_out_of_alphabetical_order_is_still_accepted(tmp_path: Path, benchmark_tar: bytes) -> None:
    unsorted_scope = (STRUCT, BLOCK, VAR_DOC)
    assert unsorted_scope != tuple(sorted(unsorted_scope))
    env = plc_env(tmp_path, benchmark_tar, scope=unsorted_scope)

    outcome = env.run()

    assert outcome.verified is True
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""
    assert env.facade.accept(outcome.mission_id).mission_state is MissionState.ACCEPTED


def test_p06_a_declared_file_the_agent_never_touched_is_not_verified(tmp_path: Path, benchmark_tar: bytes) -> None:
    def skip_document(files: dict[str, str]) -> dict[str, str]:
        files.pop(VAR_DOC)
        return files

    env = plc_env(tmp_path, benchmark_tar, mutate=skip_document)

    outcome = env.run()

    assert outcome.verified is False
    assert env.checkpoint_count() == 0


def test_p07_replaying_a_verified_run_adds_no_second_process_or_evidence(tmp_path: Path, benchmark_tar: bytes) -> None:
    env = plc_env(tmp_path, benchmark_tar)
    first = env.run()
    events, checkpoints, starts = env.event_count(), env.checkpoint_count(), env.starts()

    second = env.run()

    assert second == first
    assert (env.event_count(), env.checkpoint_count(), env.starts()) == (events, checkpoints, starts)


def test_p08_a_change_after_verification_closes_the_acceptance_gate(tmp_path: Path, benchmark_tar: bytes) -> None:
    env = plc_env(tmp_path, benchmark_tar)
    outcome = env.run()
    assert env.facade.acceptance_gate_reason(outcome.mission_id) == ""
    worktree = candidate(env, outcome.run_id)

    with (worktree / STRUCT).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("// sneaked in after verification\n")

    assert env.facade.acceptance_gate_reason(outcome.mission_id) != ""
    with pytest.raises(PmFacadeError):
        env.facade.accept(outcome.mission_id)
    assert re.search(r"sneaked", (worktree / STRUCT).read_text(encoding="utf-8")) is not None
