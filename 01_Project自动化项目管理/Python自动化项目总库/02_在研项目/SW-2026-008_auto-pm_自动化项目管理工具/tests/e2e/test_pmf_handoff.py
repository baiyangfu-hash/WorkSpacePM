"""Real-process proofs for checkpoint-bound handoff.v2: the receiver continues the same Work, the old owner is fenced out, nothing leaks (V03).

Every actor is a real child process that talks to the real continuity database through the real ``continuity`` command group; the test process plays
the project manager that holds the lease tokens in memory, so no token and no JSON file is moved by a person. The mechanism is exercised at the command
and store level: the project manager layer has no agent-swap command yet (see the technical-debt ledger).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import auto_pm
from auto_pm.contracts.continuity import HandoffV2, LeaseItem, RunState
from tests.core.test_continuity_execution_service import Clock, _checkpoint, _services, _start
from tests.workspace_support import register_project

if TYPE_CHECKING:
    from auto_pm.application.core.continuity_execution_service import (
        ContinuityExecutionError,
        ContinuityExecutionService,
    )
else:
    from auto_pm.application.core.continuity_execution_service import (
        ContinuityExecutionError,
        ContinuityExecutionService,
    )

LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""
RUN_ID = "RUN-001"
OWNER_A, OWNER_B, OWNER_C = "agent-a", "agent-b", "agent-c"
TOKEN_A, TOKEN_B, TOKEN_C = "token-of-agent-a-7f3a", "token-of-agent-b-91c2", "token-of-agent-c-d04e"
TOKEN_ENVIRONMENT = "V03_AGENT_LEASE_TOKEN"


@dataclass
class Scene:
    root: Path
    service: ContinuityExecutionService
    launcher: Path
    counter: int = 0

    def events(self) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def token_locations(self, secret: str) -> set[tuple[str, str]]:
        """Every (table, column) of the continuity database whose stored value contains this secret."""

        found: set[tuple[str, str]] = set()
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
                for row in conn.execute(f'SELECT * FROM "{table}"'):
                    for column, value in zip(columns, row, strict=True):
                        if secret in str(value):
                            found.add((table, column))
        return found

    def agent(self, *arguments: str, token: str | None = None) -> subprocess.CompletedProcess[str]:
        """One real child process that runs one ``continuity`` command against this workspace."""

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        if token is not None:
            environment[TOKEN_ENVIRONMENT] = token
        return subprocess.run(
            [sys.executable, str(self.launcher), "-w", str(self.root), "continuity", *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, timeout=120, check=False,
        )

    def key(self, label: str) -> str:
        self.counter += 1
        return f"{label}-{self.counter}"

    def checkpoint(self, owner: str, token: str, checkpoint_id: str) -> subprocess.CompletedProcess[str]:
        return self.agent(
            "checkpoint", "create", "--checkpoint-id", checkpoint_id, "--run-id", RUN_ID, "--owner", owner, "--lease-token", token,
            "--summary", "progress", "--evidence", "pytest:0", "--idempotency-key", self.key("cp"),
        )

    def transition(self, owner: str, token: str, to: str) -> subprocess.CompletedProcess[str]:
        return self.agent(
            "run", "transition", "--run-id", RUN_ID, "--to", to, "--owner", owner, "--lease-token", token, "--idempotency-key", self.key("tr"),
        )

    def renew(self, owner: str, token: str) -> subprocess.CompletedProcess[str]:
        version = self.service._store.get_lease(RUN_ID).version
        return self.agent(
            "lease", "renew", "--run-id", RUN_ID, "--owner", owner, "--lease-token-env", TOKEN_ENVIRONMENT, "--expected-version", str(version),
            "--idempotency-key", self.key("renew"), token=token,
        )

    def hand_off(self, checkpoint_id: str, from_owner: str, from_token: str, to_owner: str, to_token: str, key: str = "") -> tuple[HandoffV2, LeaseItem]:
        return self.service.create_checkpoint_bound_handoff(
            checkpoint_id=checkpoint_id, from_owner=from_owner, to_owner=to_owner, lease_token=from_token, new_lease_token=to_token,
            lease_seconds=900, idempotency_key=key or self.key("handoff"),
        )

    def old_owner_writes(self, owner: str, token: str, label: str) -> list[subprocess.CompletedProcess[str]]:
        return [self.checkpoint(owner, token, f"CP-{label}-LATE"), self.transition(owner, token, "VERIFYING"), self.renew(owner, token)]


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    clock = Clock()
    clock.value = datetime.now(UTC)
    root = tmp_path / "ws"
    root.mkdir()
    _, service = _services(root, clock)
    register_project(root, "SW-2026-008")
    _start(service, lease_token=TOKEN_A)
    service.transition_run(RUN_ID, RunState.RUNNING, OWNER_A, TOKEN_A, "to-running")
    (root / "main.py").write_text(LAUNCHER, encoding="utf-8")
    _checkpoint(service, lease_token=TOKEN_A, checkpoint_id="CP-A1")
    return Scene(root, service, root / "main.py")


def refused(process: subprocess.CompletedProcess[str]) -> bool:
    return process.returncode != 0 and "ownership" in process.stdout + process.stderr


def test_q01_before_the_handoff_the_first_agent_writes_through_the_real_command(scene: Scene) -> None:
    events = scene.events()

    process = scene.checkpoint(OWNER_A, TOKEN_A, "CP-A2")

    assert process.returncode == 0, process.stdout + process.stderr
    assert scene.events() == events + 1
    assert scene.renew(OWNER_A, TOKEN_A).returncode == 0


def test_q02_after_the_handoff_every_write_of_the_old_owner_is_refused_and_leaves_no_event(scene: Scene) -> None:
    scene.hand_off("CP-A1", OWNER_A, TOKEN_A, OWNER_B, TOKEN_B)
    events = scene.events()

    attempts = scene.old_owner_writes(OWNER_A, TOKEN_A, "A")

    assert all(refused(process) for process in attempts), [(p.returncode, p.stdout + p.stderr) for p in attempts]
    assert scene.events() == events
    assert scene.service._store.get_run(RUN_ID).state is RunState.RUNNING
    assert scene.service._store.get_lease(RUN_ID).owner_id == OWNER_B


def test_q03_the_receiver_continues_the_same_work_through_the_real_command(scene: Scene) -> None:
    handoff, lease = scene.hand_off("CP-A1", OWNER_A, TOKEN_A, OWNER_B, TOKEN_B)

    checkpoint = scene.checkpoint(OWNER_B, TOKEN_B, "CP-B1")
    renewal = scene.renew(OWNER_B, TOKEN_B)
    verifying = scene.transition(OWNER_B, TOKEN_B, "VERIFYING")

    assert (checkpoint.returncode, renewal.returncode, verifying.returncode) == (0, 0, 0), checkpoint.stderr + renewal.stderr + verifying.stderr
    assert handoff.work_id == "WORK-001" and lease.run_id == RUN_ID and lease.owner_id == OWNER_B
    assert scene.service._store.get_run(RUN_ID).work_id == handoff.work_id
    assert scene.service._store.get_run(RUN_ID).state is RunState.VERIFYING


def test_q04_the_handoff_binds_checkpoint_work_and_baseline_and_the_live_token_exists_only_in_the_lease_column(scene: Scene) -> None:
    handoff, _ = scene.hand_off("CP-A1", OWNER_A, TOKEN_A, OWNER_B, TOKEN_B)
    checkpoint = scene.service._store.get_checkpoint("CP-A1")

    assert handoff.schema_version == "handoff.v2"
    assert handoff.checkpoint_id == "CP-A1" and handoff.git_head == checkpoint.git_head
    payload = handoff.model_dump_json()
    assert TOKEN_A not in payload and TOKEN_B not in payload
    assert scene.token_locations(TOKEN_A) == set()  # the consumed token is gone from the database
    assert scene.token_locations(TOKEN_B) == {("execution_leases", "lease_token")}  # the live capability lives only in the lease column


def test_q05_replaying_the_same_handoff_changes_nothing(scene: Scene) -> None:
    first = scene.hand_off("CP-A1", OWNER_A, TOKEN_A, OWNER_B, TOKEN_B, key="replay-key")
    events = scene.events()
    lease_before = scene.service._store.get_lease(RUN_ID)  # the full LeaseItem: owner, token, expiry, version, updated_at

    second = scene.hand_off("CP-A1", OWNER_A, TOKEN_A, OWNER_B, TOKEN_B, key="replay-key")

    assert second == first and second[1].owner_id == OWNER_B  # the same handoff and the very same lease, not only the same owner
    assert scene.service._store.get_lease(RUN_ID) == lease_before
    assert scene.events() == events


def test_q06_in_a_chain_each_new_owner_fences_out_the_previous_one(scene: Scene) -> None:
    scene.hand_off("CP-A1", OWNER_A, TOKEN_A, OWNER_B, TOKEN_B)
    assert scene.checkpoint(OWNER_B, TOKEN_B, "CP-B1").returncode == 0
    scene.hand_off("CP-B1", OWNER_B, TOKEN_B, OWNER_C, TOKEN_C)
    events = scene.events()

    old_attempts = scene.old_owner_writes(OWNER_B, TOKEN_B, "B") + scene.old_owner_writes(OWNER_A, TOKEN_A, "A")
    receiver = scene.checkpoint(OWNER_C, TOKEN_C, "CP-C1")

    assert all(refused(process) for process in old_attempts)
    assert receiver.returncode == 0, receiver.stdout + receiver.stderr
    assert scene.events() == events + 1
    assert scene.service._store.get_lease(RUN_ID).owner_id == OWNER_C


def test_q07_a_handoff_addressed_to_one_agent_cannot_be_taken_by_another(scene: Scene) -> None:
    handoff = scene.service.create_handoff(
        handoff_id="HO-Q07", checkpoint_id="CP-A1", from_owner=OWNER_A, to_owner=OWNER_B, lease_token=TOKEN_A, idempotency_key=scene.key("create"),
    )

    with pytest.raises(ContinuityExecutionError):
        scene.service.accept_handoff(handoff_id=handoff.handoff_id, receiver_id=OWNER_C, new_lease_token=TOKEN_C, lease_seconds=900, idempotency_key=scene.key("steal"))
    assert scene.service._store.get_lease(RUN_ID).owner_id == OWNER_A
    assert scene.checkpoint(OWNER_A, TOKEN_A, "CP-A2").returncode == 0

    lease = scene.service.accept_handoff(handoff_id=handoff.handoff_id, receiver_id=OWNER_B, new_lease_token=TOKEN_B, lease_seconds=900, idempotency_key=scene.key("accept"))
    assert lease.owner_id == OWNER_B
    assert scene.checkpoint(OWNER_B, TOKEN_B, "CP-B1").returncode == 0


def test_q08_a_handoff_with_the_wrong_token_is_refused_and_the_owner_keeps_the_run(scene: Scene) -> None:
    with pytest.raises(ContinuityExecutionError):
        scene.hand_off("CP-A1", OWNER_A, "not-the-lease-token", OWNER_B, TOKEN_B)
    with pytest.raises(ContinuityExecutionError):
        scene.hand_off("CP-A1", OWNER_B, TOKEN_A, OWNER_B, TOKEN_B)

    assert scene.service._store.get_lease(RUN_ID).owner_id == OWNER_A
    assert scene.checkpoint(OWNER_A, TOKEN_A, "CP-A2").returncode == 0
