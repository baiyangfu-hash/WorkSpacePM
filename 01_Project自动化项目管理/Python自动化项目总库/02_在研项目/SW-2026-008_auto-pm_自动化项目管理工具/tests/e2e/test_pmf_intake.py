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

LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""
PROJECT = "SW-2026-905"
RUN_ID, OWNER, TOKEN = "RUN-001", "agent-a", "token-of-agent-a-5c1e"
APPROVER = "fubai"
GUARDED = ("work_items", "run_items", "execution_leases", "checkpoints", "mission_items", "handoffs_v2")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


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
        "--scope", "auto_pm/export.py", "--risk", "users still depend on it", "--non-goal", "no removal", "--adapter", "codex",
        "--approved-model", "gpt-approved", "--inbox-id", item["item_id"],
    )
    assert refused.returncode != 0 and "已确认" in refused.stdout + refused.stderr
    scene.confirm(item)
    planned = scene.child(
        "plan", "--project-id", PROJECT, "--request-id", "REQ-PLAN-1", "--objective", "Freeze the legacy export", "--acceptance", "Export is frozen.",
        "--scope", "auto_pm/export.py", "--risk", "users still depend on it", "--non-goal", "no removal", "--adapter", "codex",
        "--approved-model", "gpt-approved", "--inbox-id", item["item_id"],
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


def _additions(count: int) -> list[tuple[str, ...]]:
    return [
        (
            "inbox", "add", "--project-id", PROJECT, "--request-id", f"REQ-PARALLEL-{number}", "--title", f"并发入箱 {number}", "--kind", "bug",
            "--domain", "SCPT", "--original-words", "同时发现", "--affects", "多个模块", "--duplicate-check", "查过",
            "--evidence", "file:README.md", "--disposition", "inbox_wait", "--rationale", "排队", "--alternative", "忽略", "--cost-risk", "低",
        )
        for number in range(1, count + 1)
    ]
