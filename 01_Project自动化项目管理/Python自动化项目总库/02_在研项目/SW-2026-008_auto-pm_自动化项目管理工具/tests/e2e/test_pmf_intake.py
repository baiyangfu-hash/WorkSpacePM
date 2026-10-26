"""Real-process proofs for the PM front desk: a new item never disturbs the running work (card CARD-SW008-M2-P1, scenarios e01-e05).

Every actor is a real child process running the real ``pm`` or ``continuity`` commands against a real Continuity Store that holds a live Run,
its lease and a checkpoint. The test process only observes the database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.work_registry_service import WorkRegistryService

import auto_pm
from auto_pm.contracts.continuity import RunState, WorkKind
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _start
from tests.git_support import git_do
from tests.plan_checklist_support import checklist_args, full_checklist

LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""
PROJECT = "SW-2026-905"
RUN_ID, OWNER, TOKEN = "RUN-001", "agent-a", "token-of-agent-a-5c1e"
APPROVER = "fubai"
GUARDED = ("work_items", "run_items", "execution_leases", "checkpoints", "mission_items", "handoffs_v2")


def _git(root: Path, *args: str) -> None:
    git_do(root, *args)


def _specs(root: Path) -> None:
    specs = root / "00_Obsidian_Base全局规范文件仓库"
    specs.mkdir()
    (specs / "python.md").write_text("python spec\n", encoding="utf-8", errors="replace")
    (specs / "plc.md").write_text("plc spec\n", encoding="utf-8", errors="replace")
    entries = {
        "DEV-TEST": ("python", "stable", "python.md"),
        "LSP-TEST": ("plc", "active", "plc.md"),
    }
    (specs / "spec_registry.json").write_text(
        json.dumps(
            {
                "specs": {
                    name: {
                        "domain": domain,
                        "lifecycle": lifecycle,
                        "canonical_path": f"00_Obsidian_Base全局规范文件仓库/{path}",
                        "version": "V1",
                    }
                    for name, (domain, lifecycle, path) in entries.items()
                }
            }
        ),
        encoding="utf-8",
    )


@dataclass
class Scene:
    root: Path
    launcher: Path
    execution: ContinuityExecutionService
    counter: int = 0

    def child(self, *arguments: str, group: str = "pm") -> subprocess.CompletedProcess[str]:
        return self.start(*arguments, group=group).wait_result()

    def start(self, *arguments: str, group: str = "pm") -> Child:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        process = subprocess.Popen(
            [sys.executable, str(self.launcher), "-w", str(self.root), group, *arguments],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=environment,
        )
        return Child(process)

    def add(self, request_id: str, title: str, *extra: str, kind: str = "bug", disposition: str = "after_current") -> subprocess.CompletedProcess[str]:
        return self.child(
            "inbox", "add", "--project-id", PROJECT, "--request-id", request_id, "--title", title, "--kind", kind, "--domain", "SCPT",
            "--original-words", "刚才发现的问题", "--affects", "当前卡之外的模块", "--duplicate-check", "查过台账与收件箱，没有同类条目",
            "--evidence", "file:README.md", "--disposition", disposition, "--rationale", "不阻塞当前卡", "--alternative", "忽略",
            "--cost-risk", "半天；低风险", *extra,
        )

    def snapshot(self) -> dict[str, list[tuple[Any, ...]]]:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in GUARDED}

    def run_events(self) -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return [
                tuple(row)
                for row in conn.execute("SELECT * FROM events WHERE aggregate_id IN (?, 'WORK-001') ORDER BY rowid", (RUN_ID,))
            ]

    def resume(self) -> dict[str, Any]:
        result = self.child("resume", PROJECT, "--json")
        assert result.returncode == 0, result.stderr + result.stdout
        payload: dict[str, Any] = json.loads(result.stdout)
        return payload

    def item(self, result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        assert result.returncode == 0, result.stderr + result.stdout
        item: dict[str, Any] = json.loads(result.stdout)["item"]
        return item

    def confirm(self, item: dict[str, Any]) -> dict[str, Any]:
        return self.item(
            self.child(
                "inbox", "confirm", item["item_id"], "--ticket-hash", item["ticket_hash"], "--approver", APPROVER,
                "--approval-evidence-ref", "user-confirmation:chat-20261005-e2e",
            )
        )

    def agent_checkpoint(self, checkpoint_id: str) -> subprocess.CompletedProcess[str]:
        self.counter += 1
        return self.child(
            "checkpoint", "create", "--checkpoint-id", checkpoint_id, "--run-id", RUN_ID, "--owner", OWNER, "--lease-token", TOKEN,
            "--summary", "progress", "--evidence", "pytest:0", "--idempotency-key", f"cp-{self.counter}", group="continuity",
        )


@dataclass
class Child:
    process: subprocess.Popen[str]

    def wait_result(self) -> subprocess.CompletedProcess[str]:
        stdout, stderr = self.process.communicate(timeout=180)
        return subprocess.CompletedProcess(self.process.args, self.process.returncode, stdout, stderr)


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    root = tmp_path / "ws"
    root.mkdir()
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    (root / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8", errors="replace")
    _git(root, "add", "README.md", ".gitignore")
    _git(root, "-c", "user.name=Intake E2E", "-c", "user.email=intake@example.invalid", "commit", "-m", "baseline")
    project = root / PROJECT
    project.mkdir()
    (project / ".copier-answers.yml").write_text(f"project_id: {PROJECT}\nproject_name: Intake E2E\nstack: python\n", encoding="utf-8")
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps({"schema_version": "workspace-registry.v1", "projects": [{"project_id": PROJECT, "project_root": PROJECT, "development_root": PROJECT}]}),
        encoding="utf-8",
    )
    _specs(root)
    clock = Clock()
    clock.value = datetime.now(UTC)
    works = WorkRegistryService(root, now=lambda: clock().isoformat())
    works.initialize("test")
    works.create_work(
        work_id="WORK-001", subject_project_id=PROJECT, kind=WorkKind.GOVERNANCE, title="Running card", owner="architect",
        scope_paths=["auto_pm/core/a.py"], source_fingerprint="sha256:abc", idempotency_key="create-work", read_only=True,
    )
    execution = ContinuityExecutionService(root, store=ContinuityStore(root, _clock=clock), now=clock)
    _start(execution, lease_token=TOKEN)
    execution.transition_run(RUN_ID, RunState.RUNNING, OWNER, TOKEN, "to-running")
    _checkpoint(execution, lease_token=TOKEN, checkpoint_id="CP-A1")
    launcher = tmp_path / "launcher" / "main.py"
    launcher.parent.mkdir()
    launcher.write_text(LAUNCHER, encoding="utf-8")
    return Scene(root, launcher, execution)


def test_e01_a_new_bug_goes_into_the_inbox_while_the_card_keeps_running(scene: Scene) -> None:
    before, before_events = scene.snapshot(), scene.run_events()
    assert before["run_items"] and before["execution_leases"] and before["checkpoints"]
    first = scene.resume()
    assert first["intake"]["queue"] == [] and first["work"]["work_id"] == "WORK-001" and first["run"]["run_id"] == RUN_ID
    added = scene.add("REQ-ASIDE-1", "施工中发现：导出按钮点两次会重复写文件")
    item = scene.item(added)
    assert item["item_id"] == f"INBOX-{PROJECT}-0001" and item["status"] == "PROPOSED" and TOKEN not in added.stdout + added.stderr
    assert scene.snapshot() == before and scene.run_events() == before_events
    after = scene.resume()
    assert (after["work"]["work_id"], after["run"]["run_id"], after["lease"]["owner_id"]) == ("WORK-001", RUN_ID, OWNER)
    assert after["next_legal_action"] == first["next_legal_action"] and after["conflicts"] == first["conflicts"]
    assert after["intake"]["awaiting_confirmation"] == 1 and after["intake"]["queue"][0]["item_id"] == item["item_id"]
    text = scene.child("resume", PROJECT)
    assert text.returncode == 0 and f"{item['item_id']} [BUG]" in text.stdout and "work: WORK-001" in text.stdout
    assert scene.agent_checkpoint("CP-A2").returncode == 0, "the running agent must still be able to write"
    assert scene.snapshot()["run_items"] == before["run_items"]


def test_e02_an_urgent_item_is_listed_first_yet_only_waits_for_a_human_decision(scene: Scene) -> None:
    before = scene.snapshot()
    routine = scene.item(scene.add("REQ-ASIDE-1", "普通问题"))
    urgent = scene.item(
        scene.add(
            "REQ-ASIDE-2", "线上写入了错误数据", "--urgent-criterion", "wrong_output", kind="urgent", disposition="interrupt_now",
        )
    )
    queue = scene.resume()["intake"]["queue"]
    assert [entry["item_id"] for entry in queue] == [urgent["item_id"], routine["item_id"]]
    assert queue[0]["disposition"] == "INTERRUPT_NOW" and queue[0]["status"] == "PROPOSED"
    scene.confirm(routine)
    resumed = scene.resume()
    assert [entry["item_id"] for entry in resumed["intake"]["queue"]] == [routine["item_id"], urgent["item_id"]]
    assert (resumed["intake"]["awaiting_confirmation"], resumed["intake"]["confirmed_waiting"]) == (1, 1)
    assert scene.snapshot() == before and resumed["run"]["run_id"] == RUN_ID and resumed["lease"]["owner_id"] == OWNER
    assert scene.agent_checkpoint("CP-A2").returncode == 0


def test_e03_the_whole_loop_from_inbox_to_a_filed_plan_runs_in_real_processes(scene: Scene) -> None:
    before = scene.snapshot()
    item = scene.item(scene.add("REQ-ASIDE-1", "冻结旧导出功能", "--change-action", "freeze", kind="change"))
    refused = scene.child(
        "plan", "--project-id", PROJECT, "--request-id", "REQ-PLAN-1", "--objective", "Freeze the legacy export", "--acceptance", "Export is frozen.",
        "--scope", "auto_pm/export.py", "--declared-dirty", "auto_pm/export.py", "--risk", "users still depend on it", "--non-goal", "no removal", "--adapter", "codex",
        "--approved-model", "gpt-approved", "--inbox-id", item["item_id"],
        *checklist_args(original="刚才发现的问题"),
    )
    assert refused.returncode != 0 and "已确认" in refused.stdout + refused.stderr
    scene.confirm(item)
    planned = scene.child(
        "plan", "--project-id", PROJECT, "--request-id", "REQ-PLAN-1", "--objective", "Freeze the legacy export", "--acceptance", "Export is frozen.",
        "--scope", "auto_pm/export.py", "--declared-dirty", "auto_pm/export.py", "--risk", "users still depend on it", "--non-goal", "no removal", "--adapter", "codex",
        "--approved-model", "gpt-approved", "--inbox-id", item["item_id"],
        *checklist_args(original="刚才发现的问题"),
    )
    assert planned.returncode == 0, planned.stderr + planned.stdout
    change = ChangeService(str(scene.root)).get_change_request(json.loads(planned.stdout)["change_id"], project_id=PROJECT)
    assert change is not None and (change.business_nature, change.domain, change.urgency) == ("REQ", "SCPT", "normal")
    assert "change_action=FREEZE" in change.references and item["item_id"] in change.references
    listed = json.loads(scene.child("inbox", "list", "--project-id", PROJECT, "--status", "planned").stdout)["items"]
    assert [(entry["item_id"], entry["plan_request_id"]) for entry in listed] == [(item["item_id"], "REQ-PLAN-1")]
    assert scene.resume()["intake"]["queue"] == []
    assert scene.snapshot() == before and scene.agent_checkpoint("CP-A2").returncode == 0


def test_e04_simultaneous_additions_get_distinct_numbers_and_keep_the_event_chain_intact(scene: Scene) -> None:
    children = [scene.start(*arguments) for arguments in _additions(4)]
    results = [child.wait_result() for child in children]
    assert [result.returncode for result in results] == [0, 0, 0, 0], [result.stderr for result in results]
    ids = sorted(json.loads(result.stdout)["item"]["item_id"] for result in results)
    assert ids == [f"INBOX-{PROJECT}-{number:04d}" for number in range(1, 5)]
    with closing(sqlite3.connect(scene.root / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*), COUNT(DISTINCT seq) FROM intake_items").fetchone() == (4, 4)
        chain = conn.execute("SELECT previous_hash, event_hash FROM events ORDER BY rowid").fetchall()
    assert chain[0][0] == "" and all(chain[index][0] == chain[index - 1][1] for index in range(1, len(chain)))
    assert scene.resume()["intake"]["awaiting_confirmation"] == 4


def test_e05_the_same_request_from_two_processes_is_recorded_once(scene: Scene) -> None:
    first = scene.add("REQ-TWICE", "只记一次")
    second = scene.add("REQ-TWICE", "只记一次")
    assert json.loads(first.stdout)["created"] is True and json.loads(second.stdout)["created"] is False
    assert json.loads(first.stdout)["item"] == json.loads(second.stdout)["item"]
    with closing(sqlite3.connect(scene.root / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM intake_items").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='INTAKE_ITEM_RECORDED'").fetchone()[0] == 1



def _audit_race_worker(
    root: str,
    request: str,
    item_id: str,
    illegal: bool,
    mode: str,
    entry_barrier: Any,
    boundary_barrier: Any,
    sequence: Any,
    messages: Any,
) -> None:
    """Synchronize live service calls without replacing their business or SQLite operations."""
    import time

    from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
    from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
    from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PlanningScopeCard, PmIntent
    from auto_pm.infrastructure.intake_store import IntakeStore

    os.chdir(root)
    facade = PmFacadeService(root)
    item = IntakeStore(root).get_item(item_id)
    real_submit = IntakeStore.submit_classified_planning_scope_card
    real_card = PlanningScopeCard.from_draft

    def meet_boundary() -> None:
        with sequence.get_lock():
            sequence.value += 1
            ordinal = sequence.value
        messages.put(("arrived", request, illegal, ordinal, time.perf_counter_ns(), os.getpid()))
        boundary_barrier.wait(timeout=30)
        with sequence.get_lock():
            sequence.value += 1
            ordinal = sequence.value
        messages.put(("released", request, illegal, ordinal, time.perf_counter_ns(), os.getpid()))

    def submit(self: IntakeStore, *args: Any, **kwargs: Any) -> int:
        meet_boundary()
        return real_submit(self, *args, **kwargs)

    def build(*args: Any, **kwargs: Any) -> PlanningScopeCard:
        if kwargs["change_id"] == "":
            meet_boundary()
        return real_card(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        if mode == "illegal_legal":
            patch.setattr(PlanningScopeCard, "from_draft", build)
        else:
            patch.setattr(IntakeStore, "submit_classified_planning_scope_card", submit)
        entry_barrier.wait(timeout=30)
        try:
            card = facade.create_planning_scope_card(
                PmIntent(
                    request_id=request,
                    subject_project_id=PROJECT,
                    objective="Race planning",
                    acceptance_criteria=("One consumption identity",),
                ),
                scope_paths=("auto_pm/*",) if illegal else ("auto_pm/race.py",),
                risks=("Race",),
                non_goals=("No deployment",),
                execution_grant=PlanningExecutionGrant(
                    adapter=ExecutionAdapterKind.CODEX,
                    approved_model="gpt-approved",
                    declared_dirty_paths=("auto_pm/race.py",),
                    plan_checklist=full_checklist(original="刚才发现的问题"),
                ),
                classification=item.classification,
                intake_item_id=item_id,
            )
        except PmFacadeError as error:
            messages.put(("result", request, "refused", str(error), os.getpid()))
        else:
            messages.put(("result", request, "success", card.model_dump(mode="json"), os.getpid()))


@pytest.mark.parametrize("mode", ["same_request", "different_requests", "illegal_legal"])
def test_audit_f07_overlapping_processes_commit_one_consumption_identity(
    scene: Scene, mode: str
) -> None:
    import multiprocessing
    import time

    from auto_pm.application.core.pm_facade_service import PmFacadeService
    from auto_pm.contracts.pm_facade import PmIntent
    from auto_pm.infrastructure.intake_store import IntakeStore

    item = scene.confirm(scene.item(scene.add("REQ-RACE-INBOX", "Concurrent planning")))
    filing = IntakeStore(scene.root).get_item(item["item_id"]).classification
    requests = ["REQ-RACE-1", "REQ-RACE-2" if mode == "different_requests" else "REQ-RACE-1"]
    facade = PmFacadeService(scene.root)
    # File reservations precede the race; the confirmed item, card, binding and consumption are fresh.
    for request in sorted(set(requests)):
        facade.create_planning_draft_change(
            PmIntent(
                request_id=request,
                subject_project_id=PROJECT,
                objective="Race planning",
                acceptance_criteria=("One consumption identity",),
            ),
            classification=filing,
            intake_item_id=item["item_id"],
        )
    before = scene.snapshot()
    ctx = multiprocessing.get_context("spawn")
    entry_barrier, boundary_barrier = ctx.Barrier(2), ctx.Barrier(2)
    sequence = ctx.Value("i", 0)
    messages = ctx.Queue()
    children = [
        ctx.Process(
            target=_audit_race_worker,
            args=(
                str(scene.root),
                request,
                item["item_id"],
                mode == "illegal_legal" and index == 0,
                mode,
                entry_barrier,
                boundary_barrier,
                sequence,
                messages,
            ),
        )
        for index, request in enumerate(requests)
    ]
    records: list[tuple[Any, ...]] = []
    joined: list[dict[str, Any]] = []
    try:
        for child in children:
            child.start()
        for child in children:
            child.join(timeout=50)
            joined.append(
                {
                    "pid": child.pid,
                    "exit_code": child.exitcode,
                    "alive": child.is_alive(),
                    "joined_perf_counter_ns": time.perf_counter_ns(),
                }
            )
        assert all(not child.is_alive() for child in children), "race subprocess timeout"
        assert [child.exitcode for child in children] == [0, 0]
        records = [messages.get(timeout=10) for _ in range(6)]
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(timeout=10)
            if child.is_alive():
                child.kill()
                child.join(timeout=10)
        messages.close()
        messages.join_thread()
        assert all(not child.is_alive() for child in children)
    arrivals = [record[3] for record in records if record[0] == "arrived"]
    releases = [record[3] for record in records if record[0] == "released"]
    assert len(arrivals) == len(releases) == 2
    assert max(arrivals) < min(releases), (
        "both real calls must overlap at the synchronized boundary"
    )
    results = [record for record in records if record[0] == "result"]
    successes = [record for record in results if record[2] == "success"]
    assert (
        len(successes) == {"same_request": 2, "different_requests": 1, "illegal_legal": 1}[mode]
    ), results
    if mode == "same_request":
        assert successes[0][3] == successes[1][3]
    else:
        refusals = [record[3] for record in results if record[2] == "refused"]
        assert len(refusals) == 1
        expected_reason = {"illegal_legal": "wildcards", "different_requests": "已确认"}[mode]
        assert expected_reason in refusals[0]
    planned = IntakeStore(scene.root).get_item(item["item_id"])
    assert planned.plan_request_id == successes[0][1] and planned.status.value == "PLANNED"
    card = successes[0][3]
    saved = ContinuityStore(scene.root).get_submitted_planning_scope_card(
        card["request_id"], card["plan_hash"]
    )
    assert saved.card.model_dump(mode="json") == card and saved.revision == 1
    with closing(sqlite3.connect(scene.root / ".auto-pm" / "continuity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM planning_scope_cards").fetchone()[0] == 1
        assert (
            conn.execute("SELECT COUNT(*) FROM planning_draft_intake_bindings").fetchone()[0] == 1
        )
        for event in (
            "INTAKE_ITEM_PLANNED",
            "PLANNING_DRAFT_INTAKE_BOUND",
            "PLANNING_SCOPE_CARD_SUBMITTED",
        ):
            assert (
                conn.execute("SELECT COUNT(*) FROM events WHERE event_type=?", (event,)).fetchone()[
                    0
                ]
                == 1
            )
        reservations = conn.execute("SELECT change_id FROM planning_draft_chg_bindings").fetchall()
        assert len(reservations) == len(set(reservations)) == len(set(requests))
        chain = conn.execute(
            "SELECT previous_hash, event_hash FROM events ORDER BY rowid"
        ).fetchall()
    assert all(chain[index][0] == chain[index - 1][1] for index in range(1, len(chain)))
    assert scene.snapshot() == before
    print(
        json.dumps({"F07": mode, "boundary_records": records, "joined": joined}, ensure_ascii=False)
    )


def test_audit_f01_f04_real_cli_failure_stays_visible_then_cold_retry_succeeds(
    scene: Scene,
) -> None:
    item = scene.confirm(scene.item(scene.add("REQ-RETRY-INBOX", "Cold retry")))
    before = scene.snapshot()
    args = [
        "plan",
        "--project-id",
        PROJECT,
        "--request-id",
        "REQ-COLD-RETRY",
        "--objective",
        "Cold retry",
        "--acceptance",
        "Persisted card",
        "--risk",
        "Drift",
        "--non-goal",
        "No deployment",
        "--adapter",
        "codex",
        "--approved-model",
        "gpt-approved",
        "--inbox-id",
        item["item_id"],
        *checklist_args(original="刚才发现的问题"),
    ]
    failed = _rehearsal_process(scene, *args, "--scope", "auto_pm/*")
    assert failed.returncode != 0 and "wildcards" in failed.stdout + failed.stderr
    visible = json.loads(_rehearsal_process(scene, "inbox", "list", "--project-id", PROJECT).stdout)["items"]
    assert visible[0]["status"] == "CONFIRMED" and visible[0]["plan_request_id"] == ""
    succeeded = _rehearsal_process(
        scene, *args, "--scope", "auto_pm/retry.py", "--declared-dirty", "auto_pm/retry.py"
    )
    assert succeeded.returncode == 0, succeeded.stdout + succeeded.stderr
    card = json.loads(succeeded.stdout)
    assert (
        ContinuityStore(scene.root)
        .get_submitted_planning_scope_card(card["request_id"], card["plan_hash"])
        .card.model_dump(mode="json")
        == card
    )
    assert scene.snapshot() == before



def _additions(count: int) -> list[tuple[str, ...]]:
    return [
        (
            "inbox", "add", "--project-id", PROJECT, "--request-id", f"REQ-PARALLEL-{number}", "--title", f"并发入箱 {number}", "--kind", "bug",
            "--domain", "SCPT", "--original-words", "同时发现", "--affects", "多个模块", "--duplicate-check", "查过",
            "--evidence", "file:README.md", "--disposition", "inbox_wait", "--rationale", "排队", "--alternative", "忽略", "--cost-risk", "低",
        )
        for number in range(1, count + 1)
    ]


def _rehearsal_process(
    scene: Scene, *arguments: str, sdk: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run the real CLI or SDK in a fresh child; subprocess.run reaps on timeout."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-B", "-X", "utf8"]
    if sdk:
        command += ["-c", arguments[0], str(scene.root), *arguments[1:]]
    else:
        command += [str(scene.launcher), "-w", str(scene.root), "pm", *arguments]
    return subprocess.run(
        command, cwd=scene.root, env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )


def _rehearsal_plan_args(request: str) -> list[str]:
    return [
        "--project-id", PROJECT, "--request-id", request,
        "--objective", "Rehearsal approval", "--acceptance", "Exact saved identity",
        "--scope", "auto_pm/example.py", "--risk", "Scope drift",
        "--non-goal", "No execution", "--adapter", "codex",
        "--approved-model", "gpt-approved", "--declared-dirty", "auto_pm/example.py",
        *checklist_args(),
    ]


def _rehearsal_approve_args(card: dict[str, Any]) -> list[str]:
    return [
        "approve", *_rehearsal_plan_args(card["request_id"]),
        "--kind", "bug", "--domain", "SCPT", "--impact-scope", "MODULE",
        "--plan-hash", card["plan_hash"], "--approver", APPROVER,
        "--approval-evidence-ref", "user-confirmation:chat-20261005-rehearsal",
    ]


def _rehearsal_rows(root: Path) -> dict[str, list[tuple[Any, ...]]]:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for table in tables}


def _rehearsal_authority_bytes(root: Path) -> dict[str, bytes]:
    paths = list((root / PROJECT).rglob("CHG-*.md"))
    paths += list((root / ".auto-pm" / "decisions").glob("DEC-*.json"))
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in paths}


def _rehearsal_legacy_sdk_card(scene: Scene, request: str) -> dict[str, Any]:
    source = """import sys
from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.contracts.execution_adapter import ExecutionAdapterKind
from auto_pm.contracts.pm_facade import PlanningExecutionGrant, PmIntent
from tests.plan_checklist_support import full_checklist
# The refusal is lifted only to write the record an older build wrote, before every plan had to be classified.
PmFacadeService._refuse_unclassified_plan = lambda self, *args: None
facade = PmFacadeService(sys.argv[1])
card = facade.create_planning_scope_card(
    PmIntent(subject_project_id=sys.argv[3], request_id=sys.argv[2],
             objective='Rehearsal approval', acceptance_criteria=('Exact saved identity',)),
    scope_paths=('auto_pm/example.py',), risks=('Scope drift',), non_goals=('No execution',),
    execution_grant=PlanningExecutionGrant(adapter=ExecutionAdapterKind.CODEX,
        approved_model='gpt-approved', declared_dirty_paths=('auto_pm/example.py',),
        plan_checklist=full_checklist()),
)
print(card.model_dump_json())
"""
    result = _rehearsal_process(scene, source, request, PROJECT, sdk=True)
    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["request_id"] == request
    assert "planning_draft_intake_bindings" not in _rehearsal_rows(scene.root)
    return payload


def test_rehearsal_c11_real_sdk_legacy_card_full_cli_approval_and_replay(scene: Scene) -> None:
    """C11-S/R: legacy SDK identity converts once, then the exact CLI approval replays."""
    card = _rehearsal_legacy_sdk_card(scene, "REQ-REHEARSAL-C11")
    change = ChangeService(str(scene.root)).get_change_request(card["change_id"], project_id=PROJECT)
    assert change is not None
    before_change = Path(change.file_path).read_bytes()
    before = scene.snapshot()
    args = _rehearsal_approve_args(card)
    first = _rehearsal_process(scene, *args)
    assert first.returncode == 0, first.stdout + first.stderr
    approved = json.loads(first.stdout)
    assert approved["plan_hash"] == card["plan_hash"]
    assert approved["authorization_status"] == "AUTHORIZED"
    assert _rehearsal_rows(scene.root)["planning_draft_intake_bindings"]
    rows, files = _rehearsal_rows(scene.root), _rehearsal_authority_bytes(scene.root)
    replay = _rehearsal_process(scene, *args)
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert json.loads(replay.stdout) == approved
    assert _rehearsal_rows(scene.root) == rows
    assert _rehearsal_authority_bytes(scene.root) == files
    # Approval legitimately changes CHG lifecycle text; classification must not change its identity.
    assert before_change != Path(change.file_path).read_bytes()
    saved = ContinuityStore(scene.root).get_submitted_planning_scope_card(card["request_id"], card["plan_hash"])
    assert saved.card.model_dump(mode="json") == card
    after = scene.snapshot()
    for table in ("run_items", "execution_leases", "checkpoints", "handoffs_v2"):
        assert after[table] == before[table]


@pytest.mark.parametrize("invalid", ["request_ref", "fingerprint_ref", "domain", "approver", "evidence", "plan_hash"])
def test_rehearsal_c11_real_cli_legacy_conversion_rejects_wrong_identity_without_writes(
    scene: Scene, invalid: str
) -> None:
    """C11-N/I: request/fingerprint/classification/human/hash mismatch cannot convert."""
    card = _rehearsal_legacy_sdk_card(scene, "REQ-REHEARSAL-C11-WRONG")
    args = _rehearsal_approve_args(card)
    if invalid in ("request_ref", "fingerprint_ref"):
        change = ChangeService(str(scene.root)).get_change_request(card["change_id"], project_id=PROJECT)
        assert change is not None
        path = Path(change.file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        reference = (f"request_id={card['request_id']}" if invalid == "request_ref" else
                     f"fingerprint={ContinuityStore(scene.root).get_planning_draft(card['request_id']).input_fingerprint}")
        assert reference in content
        path.write_text(content.replace(reference, reference + "-wrong"), encoding="utf-8", errors="replace", newline="\n")
    else:
        option, value = {"domain": ("--domain", "PLC"), "approver": ("--approver", "claude"),
                         "evidence": ("--approval-evidence-ref", "chat said yes"),
                         "plan_hash": ("--plan-hash", "0" * 64)}[invalid]
        args[args.index(option) + 1] = value
    before_rows, before_files = _rehearsal_rows(scene.root), _rehearsal_authority_bytes(scene.root)
    failed = _rehearsal_process(scene, *args)
    assert failed.returncode != 0, failed.stdout + failed.stderr
    assert _rehearsal_rows(scene.root) == before_rows
    assert _rehearsal_authority_bytes(scene.root) == before_files


def test_rehearsal_c12_real_cli_plan_refuses_approved_but_approve_recovers_same_card(scene: Scene) -> None:
    """C12-S/N/R/I: only exact approve replays; plan and changed identity write nothing."""
    request = "REQ-REHEARSAL-C12"
    plan_args = ["plan", *_rehearsal_plan_args(request), "--kind", "bug", "--domain", "SCPT"]
    planned = _rehearsal_process(scene, *plan_args)
    assert planned.returncode == 0, planned.stdout + planned.stderr
    card: dict[str, Any] = json.loads(planned.stdout)
    args = _rehearsal_approve_args(card)
    approved = _rehearsal_process(scene, *args)
    assert approved.returncode == 0, approved.stdout + approved.stderr
    rows, files = _rehearsal_rows(scene.root), _rehearsal_authority_bytes(scene.root)
    refused = _rehearsal_process(scene, *plan_args)
    assert refused.returncode != 0 and "已批准" in refused.stdout + refused.stderr
    assert _rehearsal_rows(scene.root) == rows
    assert _rehearsal_authority_bytes(scene.root) == files
    replay = _rehearsal_process(scene, *args)
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert json.loads(replay.stdout) == json.loads(approved.stdout)
    assert _rehearsal_rows(scene.root) == rows
    assert _rehearsal_authority_bytes(scene.root) == files
    for option, value in (("--kind", "debt"), ("--approver", "claude"), ("--approval-evidence-ref", "chat said yes"), ("--plan-hash", "0" * 64)):
        invalid_args = args.copy()
        invalid_args[invalid_args.index(option) + 1] = value
        wrong = _rehearsal_process(scene, *invalid_args)
        assert wrong.returncode != 0, wrong.stdout + wrong.stderr
        assert _rehearsal_rows(scene.root) == rows
        assert _rehearsal_authority_bytes(scene.root) == files
