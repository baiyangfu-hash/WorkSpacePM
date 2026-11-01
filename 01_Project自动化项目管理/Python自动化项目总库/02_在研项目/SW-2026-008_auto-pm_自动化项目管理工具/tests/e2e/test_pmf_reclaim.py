"""Real-process proof of the reclaim interface (M3-HANDOFF card, V04-R1 case 3): the executor is killed, another agent takes the card over.

Every agent is a real child process talking to the real continuity database through the real ``continuity`` commands, and the lease holder's
long-lived process is a real process that the test kills.  Only the passing of time is simulated (the lease end is moved into the past),
because the shortest lease plus the 120 s grace would make the test wait more than three minutes.  No token is ever passed in argv.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import auto_pm
from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.contracts.continuity import RunState
from auto_pm.infrastructure import lease_wallet, process_probe
from tests.core.test_continuity_execution_service import Clock, _services
from tests.git_support import run_worktree
from tests.workspace_support import register_project

LAUNCHER = """from auto_pm.cli.__main__ import cli

if __name__ == "__main__":
    cli()
"""
RUN = "RUN-DRILL-001"
pytestmark = pytest.mark.skipif(
    not (sys.platform == "win32" or sys.platform.startswith("linux")), reason="the probe observes Windows and Linux only"
)


class Scene:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.launcher = root / "main.py"

    def agent(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {key: value for key, value in os.environ.items() if key not in AGENT_MARKERS}
        environment["PYTHONPATH"] = str(Path(auto_pm.__file__).resolve().parent.parent)
        environment["PYTHONIOENCODING"] = "utf-8"
        command = [sys.executable, str(self.launcher), "-w", str(self.root), "continuity", *arguments]
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, timeout=120, check=False)
        for token in self.tokens():
            assert token not in " ".join(command), "a lease token reached argv"
            assert token not in done.stdout + done.stderr, "a lease token reached the output"
        return done

    def tokens(self) -> list[str]:
        folder = self.root / lease_wallet.WALLET_DIR
        if not folder.is_dir():
            return []
        return [json.loads(path.read_text(encoding="utf-8"))["lease_token"] for path in folder.glob("*.json")]

    def lease(self) -> sqlite3.Row:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            conn.row_factory = sqlite3.Row
            row: sqlite3.Row | None = conn.execute("SELECT owner_id, version, expires_at FROM execution_leases WHERE run_id=?", (RUN,)).fetchone()
            assert row is not None
            return row

    def events(self) -> int:
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def time_passes(self) -> None:
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        with closing(sqlite3.connect(self.root / ".auto-pm" / "continuity.db")) as conn, conn:
            conn.execute("UPDATE execution_leases SET expires_at=? WHERE run_id=?", (past, RUN))


@pytest.fixture
def executor() -> Iterator[subprocess.Popen[bytes]]:
    """The first agent's long-lived process (what a power loss or a crash kills)."""

    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    yield process
    if process.poll() is None:
        process.kill()
    process.wait(30)


@pytest.fixture
def scene(tmp_path: Path) -> Scene:
    root = tmp_path / "ws"
    root.mkdir()
    _services(root, Clock())  # git repository, schema and WORK-001 (scope auto_pm/core/a.py, tests/test_a.py)
    register_project(root, "SW-2026-008")
    (root / "main.py").write_text(LAUNCHER, encoding="utf-8")
    return Scene(root)


def _start(scene: Scene, owner: str, holder_pid: int, run_id: str = RUN) -> subprocess.CompletedProcess[str]:
    return scene.agent(
        "run", "start", "--run-id", run_id, "--work-id", "WORK-001", "--executor", owner, "--adapter", "codex", "--owned", "auto_pm/core/a.py",
        "--declared-dirty", "auto_pm/core/a.py", "--worktree", str(run_worktree(scene.root)),
        "--lease-wallet", "--holder-pid", str(holder_pid), "--lease-seconds", "60", "--idempotency-key", f"start-{owner}",
    )


def _reclaim(scene: Scene, claimant: str) -> subprocess.CompletedProcess[str]:
    return scene.agent(
        "run", "reclaim", "--run-id", RUN, "--claimant", claimant, "--reason", "executor killed", "--holder-pid", "none"
    )


def test_k01_the_killed_executors_card_is_taken_over_and_the_executor_coming_back_is_refused(
    scene: Scene, executor: subprocess.Popen[bytes]
) -> None:
    if process_probe.fingerprint(executor.pid) is None or not process_probe.local_host_id():
        pytest.skip("the process table of this host cannot be read")
    started = _start(scene, "agent-a", executor.pid)
    assert started.returncode == 0, started.stdout + started.stderr
    running = scene.agent("run", "transition", "--run-id", RUN, "--to", RunState.RUNNING.value, "--owner", "agent-a", "--lease-wallet", "--idempotency-key", "a-run")
    assert running.returncode == 0, running.stdout + running.stderr
    old_token = lease_wallet.load(scene.root, run_id=RUN, owner_id="agent-a")

    # case 1: a second agent cannot start the same card; it is told who holds it and until when
    second = _start(scene, "agent-b", os.getpid(), run_id="RUN-DRILL-002")
    assert second.returncode != 0 and "agent-a" in second.stderr + second.stdout and "租约到" in second.stderr + second.stdout

    # the lease is still live: no reclaim, whatever happened to the process
    events = scene.events()
    live = _reclaim(scene, "agent-b")
    assert live.returncode == 1 and json.loads(live.stdout)["decision"] == "REFUSE_LIVE_LEASE"
    # the lease ran out but the executor still runs: never pre-empted
    scene.time_passes()
    alive = _reclaim(scene, "agent-b")
    assert alive.returncode in (1, 3), alive.stdout + alive.stderr  # ALIVE, or UNKNOWN where the command line cannot be read
    assert json.loads(alive.stdout)["decision"] in ("REFUSE_PROCESS_ALIVE", "PENDING")
    assert scene.events() == events and scene.lease()["owner_id"] == "agent-a"

    # the executor is killed: now the card can be taken over and the epoch rises
    executor.kill()
    executor.wait(30)
    version = scene.lease()["version"]
    taken = _reclaim(scene, "agent-b")
    assert taken.returncode == 0, taken.stdout + taken.stderr
    outcome = json.loads(taken.stdout)
    assert outcome["decision"] == "ALLOW" and outcome["process_verdict"] == "PROVEN_DEAD" and outcome["owner_id"] == "agent-b"
    assert outcome["epoch"] == version + 1 and scene.lease()["owner_id"] == "agent-b"

    # the old executor comes back with its old token: every write is refused and leaves nothing
    lease_wallet.save(scene.root, run_id="RUN-STALE-COPY", owner_id="agent-a", lease_token=old_token, epoch=1)  # what the old agent still holds
    events = scene.events()
    environment = {**os.environ, "OLD_TOKEN": old_token}
    late = subprocess.run(
        [sys.executable, str(scene.launcher), "-w", str(scene.root), "continuity", "lease", "renew", "--run-id", RUN, "--owner", "agent-a",
         "--lease-token-env", "OLD_TOKEN", "--expected-version", str(version), "--idempotency-key", "late-renew"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env={**environment, "PYTHONPATH": str(Path(auto_pm.__file__).resolve().parent.parent)},
        timeout=120, check=False,
    )
    assert late.returncode != 0
    assert scene.events() == events

    # the receiver works on through its wallet
    renewed = scene.agent(
        "lease", "renew", "--run-id", RUN, "--owner", "agent-b", "--lease-wallet", "--expected-version", str(scene.lease()["version"]),
        "--idempotency-key", "b-renew",
    )
    assert renewed.returncode == 0, renewed.stdout + renewed.stderr
