"""Real-process proofs for the thin Cockpit SDK and its runtime-identity write guard."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from auto_pm.change.ledger_reconciler import LedgerReconciler

import auto_pm
from auto_pm.api import CockpitApiError, CockpitClient
from auto_pm.application.core.local_execution_orchestrator import LocalExecutionOrchestrator
from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.mission import MissionState
from auto_pm.contracts.pm_cockpit import PmCockpitCompletionState
from auto_pm.contracts.pm_facade import PlanningScopeCard, PmRunOutcome
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.infrastructure.local_executor import LocalCodexExecutor
from tests.core.test_pm_run_e2e import (
    CALC,
    CALC_TEST,
    FIXED_CALC,
    GOOD_TESTS,
    PROJECT_ID,
    _build_workspace,
    _helper_source,
)
from tests.plan_checklist_support import full_checklist

APPROVER = "fubai"
EVIDENCE = "user-confirmation:U07C-E2E-001"
_REFUSED = "运行身份未通过校验，SDK 已拒绝写入"
_ALREADY_VERIFIED = "该需求已执行并验证，等待验收；请直接确认验收，不要重复执行。"
_PLACEHOLDERS = ("（待填写）", "(待填写)", "待补充", "[在此填写", "[___________]")


def _snapshot(root: Path) -> dict[str, str]:
    """Every file under the workspace (except Git internals) mapped to its content hash."""

    result: dict[str, str] = {}
    for current, directories, files in os.walk(root):
        directories[:] = [item for item in directories if item != ".git"]
        for name in files:
            path = Path(current) / name
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _with_runtime_registry(root: Path) -> None:
    """Register a runtime_root whose active release is ``rel-a`` (``rel-b`` also exists)."""

    control = root / "SYS-2026-001_WorkspaceGovernance"
    (control / "PM_SESSION_SYS-2026-001.md").write_text("control\n", encoding="utf-8")
    runtime = root / "00_Infrastructure" / "auto_pm"
    for release in ("rel-a", "rel-b"):
        package = runtime / "releases" / release / "auto_pm"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
    (runtime / "active_release.json").write_text(json.dumps({"release_id": "rel-a"}), encoding="utf-8")
    (control / "workspace_registry.json").write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": PROJECT_ID,
                        "project_root": PROJECT_ID,
                        "development_root": PROJECT_ID,
                        "control_project_id": "SYS-2026-001",
                        "control_pm_session": (
                            "SYS-2026-001_WorkspaceGovernance/PM_SESSION_SYS-2026-001.md"
                        ),
                        "runtime_root": "00_Infrastructure/auto_pm",
                    },
                    {
                        "project_id": "SYS-2026-001",
                        "project_root": "SYS-2026-001_WorkspaceGovernance",
                        "development_root": "SYS-2026-001_WorkspaceGovernance",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


@dataclass
class _Workspace:
    root: Path
    store: ContinuityStore
    facade: PmFacadeService
    counter: Path

    def starts(self) -> int:
        return len(self.counter.read_text(encoding="utf-8").splitlines()) if self.counter.exists() else 0

    def events(self) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def client(
        self, provider: Callable[[], str | Path | None] | None = None
    ) -> CockpitClient:
        return CockpitClient(
            self.root, PROJECT_ID, facade=self.facade, package_file_provider=provider
        )


def _workspace(base: Path, *, runtime: bool = False) -> _Workspace:
    root = (base / "ws").resolve()
    _build_workspace(root)
    if runtime:
        _with_runtime_registry(root)
    counter = base / "starts.txt"
    helper = base / "fake_codex.py"
    helper.write_text(
        _helper_source(calc=FIXED_CALC, tests=GOOD_TESTS, exit_code=0, counter=counter),
        encoding="utf-8",
    )
    store = ContinuityStore(root)
    store.initialize(datetime.now(UTC).isoformat(), "u07c-e2e")
    executor = LocalCodexExecutor(command_prefix=(sys.executable, str(helper)))
    facade = PmFacadeService(
        root,
        store=store,
        local_orchestrator=LocalExecutionOrchestrator(root, store=store, executor=executor),
    )
    return _Workspace(root, store, facade, counter)


def _plan(client: CockpitClient, request_id: str = "REQ-U07C-E2E") -> PlanningScopeCard:
    return client.plan(
        request_id=request_id,
        objective="Fix add()",
        acceptance=("add(2, 3) == 5",),
        scope_paths=(CALC, CALC_TEST),
        risks=("改错文件导致回归",),
        non_goals=("no refactor",),
        adapter=ExecutionAdapterKind.CODEX,
        approved_model="agent-a",
        declared_dirty_paths=(CALC, CALC_TEST),
        plan_checklist=full_checklist(),
    )


def _token_locations(root: Path, token: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                for column, value in zip(columns, row, strict=True):
                    if token in str(value):
                        found.add((table, column))
    return found


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@dataclass
class _RealFlow:
    workspace: _Workspace
    card: PlanningScopeCard
    decision_id: str
    first: PmRunOutcome
    replay: PmRunOutcome
    starts_after_replay: int
    refused_text: str
    events_before_refusal: int
    events_after_refusal: int
    accepted_state: MissionState
    completion_state: PmCockpitCompletionState
    final_state: MissionState
    change_text: str
    source_calc_before: str
    source_calc_after: str
    ledger_clean: bool
    token_locations_after_run: set[tuple[str, str]]
    token_locations_after_close: set[tuple[str, str]]
    outcome_json: str
    log_text: str
    error_texts: list[str]


@pytest.fixture(scope="module")
def real_flow(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_RealFlow]:
    base = tmp_path_factory.mktemp("u07c-real")
    workspace = _workspace(base)
    capture = _Capture()
    logging.getLogger().addHandler(capture)
    previous_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.DEBUG)
    outside = base / "elsewhere"
    outside.mkdir()
    previous_cwd = Path.cwd()
    os.chdir(outside)
    try:
        client = workspace.client()
        source_before = (workspace.root / CALC).read_text(encoding="utf-8")
        card = _plan(client)
        decision = client.approve_plan(card, approver=APPROVER, approval_evidence_ref=EVIDENCE)
        first = client.run(card)
        replay = client.run(card)
        token = next(iter(client._leases.values()))
        locations_after_run = _token_locations(workspace.root, token)
        starts = workspace.starts()
        events_before = workspace.events()
        error_texts: list[str] = []
        try:
            workspace.client().run(card)
            refused = ""
        except CockpitApiError as error:
            refused = str(error)
            error_texts.append(refused)
        events_after = workspace.events()
        accepted = workspace.client().accept(first.mission_id)
        completion = client.close(first.mission_id)
        change = next(workspace.root.glob(f"**/{card.change_id}.md"))
        yield _RealFlow(
            workspace=workspace,
            card=card,
            decision_id=decision.decision_id,
            first=first,
            replay=replay,
            starts_after_replay=starts,
            refused_text=refused,
            events_before_refusal=events_before,
            events_after_refusal=events_after,
            accepted_state=accepted.mission_state,
            completion_state=completion.state,
            final_state=client.mission_state(first.mission_id),
            change_text=change.read_text(encoding="utf-8"),
            source_calc_before=source_before,
            source_calc_after=(workspace.root / CALC).read_text(encoding="utf-8"),
            ledger_clean=LedgerReconciler().reconcile(str(workspace.root)).is_clean,
            token_locations_after_run=locations_after_run,
            token_locations_after_close=_token_locations(workspace.root, token),
            outcome_json=first.model_dump_json() + replay.model_dump_json() + completion.model_dump_json(),
            log_text="\n".join(capture.lines),
            error_texts=error_texts + [token],
        )
    finally:
        os.chdir(previous_cwd)
        logging.getLogger().removeHandler(capture)
        logging.getLogger().setLevel(previous_level)


def test_full_real_flow_from_a_new_goal_to_a_closed_mission(real_flow: _RealFlow) -> None:
    flow = real_flow
    assert flow.decision_id.startswith("DEC-")
    assert flow.first.verified is True
    assert flow.first.mission_state is MissionState.ACCEPTANCE_PENDING
    assert flow.accepted_state is MissionState.ACCEPTED
    assert flow.completion_state is PmCockpitCompletionState.COMPLETED
    assert flow.final_state is MissionState.CLOSED
    assert not [item for item in _PLACEHOLDERS if item in flow.change_text]
    assert any(line.startswith("| **验证结论**") for line in flow.change_text.splitlines())
    assert flow.ledger_clean is True
    assert flow.source_calc_after == flow.source_calc_before
    assert flow.source_calc_before != FIXED_CALC


def test_replay_in_one_process_is_equal_and_starts_no_second_process(real_flow: _RealFlow) -> None:
    assert real_flow.replay == real_flow.first
    assert real_flow.starts_after_replay == 1


def test_a_second_client_cannot_re_run_a_verified_mission(real_flow: _RealFlow) -> None:
    assert real_flow.refused_text == _ALREADY_VERIFIED
    assert real_flow.events_after_refusal == real_flow.events_before_refusal


def test_the_lease_token_exists_only_in_the_stores_own_column(real_flow: _RealFlow) -> None:
    token = real_flow.error_texts[-1]
    # While the lease is live the store keeps it only in its own column; closing releases it.
    assert real_flow.token_locations_after_run == {("execution_leases", "lease_token")}
    assert real_flow.token_locations_after_close == set()
    for text in (real_flow.outcome_json, real_flow.log_text, *real_flow.error_texts[:-1]):
        assert token not in text


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("editable", "RUNTIME_IDENTITY_UNVERIFIED"),
        ("outside", "RUNTIME_IDENTITY_UNVERIFIED"),
        ("divergent", "RUNTIME_IDENTITY_DIVERGENCE"),
    ],
)
def test_a_wrong_runtime_identity_refuses_every_write_and_writes_nothing(
    tmp_path: Path, label: str, expected: str
) -> None:
    workspace = _workspace(tmp_path, runtime=True)
    runtime = workspace.root / "00_Infrastructure" / "auto_pm" / "releases"
    good = runtime / "rel-a" / "auto_pm" / "__init__.py"
    card = _plan(workspace.client(lambda: good))
    elsewhere = tmp_path / "elsewhere.py"
    elsewhere.write_text("", encoding="utf-8")
    bad: dict[str, Path] = {
        "editable": workspace.root / CALC,
        "outside": elsewhere,
        "divergent": runtime / "rel-b" / "auto_pm" / "__init__.py",
    }
    client = workspace.client(lambda: bad[label])
    before = _snapshot(workspace.root)

    assert client.identity.writable is False
    assert expected in client.identity.conflicts
    writes: list[Callable[[], object]] = [
        lambda: _plan(client, "REQ-U07C-OTHER"),
        lambda: client.approve_plan(card, approver=APPROVER, approval_evidence_ref=EVIDENCE),
        lambda: client.run(card),
        lambda: client.accept("MISSION-NOT-THERE"),
        lambda: client.close("MISSION-NOT-THERE"),
    ]
    for write in writes:
        with pytest.raises(CockpitApiError, match=_REFUSED) as refusal:
            write()
        assert expected in str(refusal.value)

    assert _snapshot(workspace.root) == before
    assert client.identity.conflicts
    with pytest.raises(CockpitApiError) as read_error:
        client.mission_state("MISSION-NOT-THERE")
    assert _REFUSED not in str(read_error.value)


def test_the_identity_is_rechecked_on_every_write_not_only_at_construction(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, runtime=True)
    runtime = workspace.root / "00_Infrastructure" / "auto_pm" / "releases"
    location = {"path": runtime / "rel-a" / "auto_pm" / "__init__.py"}
    client = workspace.client(lambda: location["path"])

    assert client.identity.writable is True
    assert client.identity.configured_release_id == "rel-a"
    assert client.identity.effective_release_id == "rel-a"
    card = _plan(client)
    assert card.change_id

    location["path"] = workspace.root / CALC
    with pytest.raises(CockpitApiError, match=_REFUSED):
        _plan(client, "REQ-U07C-SECOND")
    assert client.identity.writable is False


def test_a_project_without_a_runtime_mapping_is_writable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    client = workspace.client()

    assert client.identity.conflicts == ()
    assert client.identity.writable is True
    assert client.identity.project_id == PROJECT_ID
    assert client.identity.workspace_root == str(workspace.root)


def test_an_approval_that_is_not_a_real_human_confirmation_writes_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    client = workspace.client()
    card = _plan(client)
    change_file = next(workspace.root.glob(f"**/{card.change_id}.md"))
    change_before = change_file.read_bytes()
    decisions = workspace.root / ".auto-pm" / "decisions"
    decisions_before = sorted(path.name for path in decisions.glob("*")) if decisions.exists() else []

    for approver, evidence in (("codex-agent", EVIDENCE), (APPROVER, "confirmed"), (APPROVER, "")):
        with pytest.raises(CockpitApiError):
            client.approve_plan(card, approver=approver, approval_evidence_ref=evidence)

    assert change_file.read_bytes() == change_before
    after = sorted(path.name for path in decisions.glob("*")) if decisions.exists() else []
    assert after == decisions_before
    parameters = CockpitClient.approve_plan.__annotations__
    assert "approver" in parameters and "approval_evidence_ref" in parameters
    # approver and evidence have no default; only the release may be left out (it then means "no release")
    assert CockpitClient.approve_plan.__kwdefaults__ == {"admission_release_ref": ""}


def test_unknown_missions_and_projects_raise_only_the_sdk_error(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    client = workspace.client()

    for call in (
        lambda: client.accept("MISSION-NOT-THERE"),
        lambda: client.close("MISSION-NOT-THERE"),
        lambda: client.mission_state("MISSION-NOT-THERE"),
    ):
        with pytest.raises(CockpitApiError):
            call()
    with pytest.raises(CockpitApiError):
        CockpitClient(workspace.root, "SW-NOT-REGISTERED", facade=workspace.facade)


def test_importing_the_package_does_not_load_the_sdk_but_exports_it_lazily() -> None:
    root = Path(auto_pm.__file__).resolve().parent.parent
    script = (
        "import json, sys, auto_pm\n"
        "before = 'auto_pm.api' in sys.modules\n"
        "client = auto_pm.CockpitClient\n"
        "same = client is sys.modules['auto_pm.api'].CockpitClient\n"
        "try:\n"
        "    auto_pm.NotAThing\n"
        "    missing = False\n"
        "except AttributeError:\n"
        "    missing = True\n"
        "print(json.dumps([before, same, missing]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )

    assert json.loads(result.stdout.strip().splitlines()[-1]) == [False, True, True]
    assert re.fullmatch(r"\[false, true, true\]", result.stdout.strip().splitlines()[-1]) is not None
    assert auto_pm.CockpitClient is CockpitClient
    assert auto_pm.CockpitApiError is CockpitApiError
    unknown = "NotAThing"
    with pytest.raises(AttributeError):
        getattr(auto_pm, unknown)


def test_the_sdk_admits_a_colliding_card_only_with_the_users_release(tmp_path: Path) -> None:
    """TD-071 card 3: approve_plan refuses before any write; run cannot slip a colliding card in either."""

    workspace = _workspace(tmp_path)
    client = workspace.client()
    first = _plan(client, "REQ-SDK-A")
    client.approve_plan(first, approver=APPROVER, approval_evidence_ref=EVIDENCE)
    PmFacadeService(workspace.root).materialize_planning_mission(first)
    second = _plan(client, "REQ-SDK-B")
    change_file = next(workspace.root.glob(f"**/{second.change_id}.md"))
    change_before = change_file.read_bytes()

    with pytest.raises(CockpitApiError, match="要改同一批文件"):
        client.approve_plan(second, approver=APPROVER, approval_evidence_ref=EVIDENCE)
    assert change_file.read_bytes() == change_before

    client.approve_plan(second, approver=APPROVER, approval_evidence_ref=EVIDENCE, admission_release_ref="user-confirmation:SDK-B-0001")
    with pytest.raises(CockpitApiError, match="要改同一批文件"):
        client.run(second)  # the Mission is created on run, and is admitted again there
    assert len(ContinuityStore(workspace.root).list_missions(PROJECT_ID)) == 1
