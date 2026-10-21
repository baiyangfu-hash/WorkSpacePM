"""IDE-agent lane (gap 8): from an approved scope card to a closed Mission with commands only, no temporary script.

This is the route the entry skill (step 6 to 8) gives Trae: ``pm confirm-start``, a ``git worktree add``, ``continuity run
start --worktree --lease-wallet``, RUNNING, the agent writes in the worktree, VERIFYING, ``pm verify --lease-wallet``, the
user's acceptance, ``pm close``.  Every step is a real child process; the agent's writing is plain file I/O in the worktree.
The closure brings the accepted bytes back into the control root, or refuses without writing anything.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.test_closure_drill import Drill, assert_closed_and_clean, comment_files, make_drill
from tests.e2e.test_pmf_plc import (
    PROJECT_ID,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    git,
)
from tests.e2e.test_raw_requirement_drill import _approve_from_one_sentence

EXECUTOR = "trae:cn"


class Lane:
    """One IDE-agent Mission walked by command line; ``files`` are what the agent writes in its worktree."""

    def __init__(self, drill: Drill, request_id: str, files: dict[str, str]) -> None:
        self.drill = drill
        self.files = files
        self.card, approved = _approve_from_one_sentence(drill, request_id, files=files)
        assert approved.returncode == 0, drill.transcript()
        from auto_pm.infrastructure.continuity_store import ContinuityStore

        missions = [
            mission
            for mission in ContinuityStore(drill.root).list_missions(PROJECT_ID, include_terminal=True)
            if mission.authority.change_id == self.card["change_id"]
        ]
        assert len(missions) == 1, missions
        self.mission_id = missions[0].mission_id
        self.worktree = drill.root / ".auto-pm" / "worktrees" / f"ide-{request_id.lower()}"
        self.run_id = f"RUN-IDE-{request_id}"
        self.work_id = ""

    def start(self) -> None:
        drill = self.drill
        started = drill.cli("pm", "confirm-start", "--mission-id", self.mission_id)
        assert started.returncode == 0, drill.transcript()
        from auto_pm.infrastructure.continuity_store import ContinuityStore

        self.work_id = ContinuityStore(drill.root).get_mission(self.mission_id).root_work_id or ""
        git(drill.root, "worktree", "add", "-q", "--detach", str(self.worktree))
        run = ["continuity", "run", "start", "--run-id", self.run_id, "--work-id", self.work_id, "--executor", EXECUTOR,
               "--adapter", "trae", "--worktree", str(self.worktree), "--lease-wallet", "--holder-pid", "none",
               "--idempotency-key", f"{self.run_id}:start"]
        for path in self.files:
            run += ["--owned", path, "--declared-dirty", path]
        opened = drill.cli(*run)
        assert opened.returncode == 0, drill.transcript()
        self.transition("RUNNING")

    def write(self) -> None:
        for relative, text in self.files.items():
            target = self.worktree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def transition(self, state: str) -> None:
        moved = self.drill.cli(
            "continuity", "run", "transition", "--run-id", self.run_id, "--to", state, "--owner", EXECUTOR,
            "--lease-wallet", "--idempotency-key", f"{self.run_id}:{state}",
        )
        assert moved.returncode == 0, self.drill.transcript()

    def verify(self):  # type: ignore[no-untyped-def]
        return self.drill.cli("pm", "verify", "--mission-id", self.mission_id, "--lease-wallet")

    def accept(self) -> None:
        # The user's own act (in the field: the cockpit button); the drill has no human, so it uses the command.
        accepted = self.drill.cli("pm", "accept", "--mission-id", self.mission_id)
        assert accepted.returncode == 0, self.drill.transcript()

    def close(self):  # type: ignore[no-untyped-def]
        return self.drill.cli("pm", "close", "--mission-id", self.mission_id)

    def walk_to_acceptance(self) -> None:
        self.start()
        self.write()
        self.transition("VERIFYING")
        verified = self.verify()
        assert verified.returncode == 0, self.drill.transcript()
        assert verified.json()["verified"] is True
        assert verified.json()["mission_state"] == "ACCEPTANCE_PENDING"
        self.accept()


def _result(lane: Lane):  # type: ignore[no-untyped-def]
    from tests.e2e.test_closure_drill import MissionResult

    return MissionResult("closed", lane.mission_id, lane.card["change_id"])


def _no_cache_in_release(drill: Drill) -> None:
    releases = drill.root / "00_Infrastructure" / "auto_pm" / "releases"
    assert not list(releases.rglob("__pycache__")), "收口路线不应往发布目录写缓存"


def test_i01_ide_lane_closes_by_command_line_and_the_accepted_bytes_land_in_the_control_root(
    tmp_path: Path, benchmark_tar: bytes  # noqa: F811
) -> None:
    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-IDE-I01", comment_files(drill.root, "IDE 路线：一条命令收口"))
    lane.walk_to_acceptance()
    before = {relative: (drill.root / relative).read_bytes() for relative in lane.files}
    assert all(before[relative] != text.encode("utf-8") for relative, text in lane.files.items())

    closed = lane.close()

    assert closed.returncode == 0, drill.transcript()
    assert closed.json()["state"] == "COMPLETED"
    for relative, text in lane.files.items():
        assert (drill.root / relative).read_bytes() == (lane.worktree / relative).read_bytes() == text.encode("utf-8")
    assert_closed_and_clean(drill, _result(lane), PROJECT_ID)
    _no_cache_in_release(drill)
    # A second close is a harmless replay.
    again = lane.close()
    assert again.returncode == 0 and again.json()["state"] == "COMPLETED", drill.transcript()


def test_i02_verify_refuses_a_run_that_is_not_verifying_and_never_prints_the_token(
    tmp_path: Path, benchmark_tar: bytes  # noqa: F811
) -> None:
    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-IDE-I02", comment_files(drill.root, "IDE 路线：未到验证"))
    lane.start()
    lane.write()

    early = lane.verify()

    assert early.returncode != 0
    assert "VERIFYING" in early.stderr + early.stdout
    wallet = json.loads((drill.root / ".auto-pm" / "cache" / "lease-wallet" / f"{lane.run_id}.json").read_text(encoding="utf-8"))
    for step in drill.log:
        assert wallet["lease_token"] not in step.stdout + step.stderr


def test_i03_close_refuses_before_the_users_acceptance(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-IDE-I03", comment_files(drill.root, "IDE 路线：未验收不收口"))
    lane.start()
    lane.write()
    lane.transition("VERIFYING")
    assert lane.verify().returncode == 0, drill.transcript()

    refused = lane.close()

    assert refused.returncode != 0
    assert "尚未验收" in refused.stderr + refused.stdout
    for relative in lane.files:
        assert (drill.root / relative).read_text(encoding="utf-8") != lane.files[relative]


def test_i04_a_worktree_changed_after_verification_is_not_merged_back(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-IDE-I04", comment_files(drill.root, "IDE 路线：验收后又改"))
    lane.walk_to_acceptance()
    original = {relative: (drill.root / relative).read_bytes() for relative in lane.files}
    relative = next(iter(lane.files))
    (lane.worktree / relative).write_text(lane.files[relative] + "// 验收后偷偷加的一行\n", encoding="utf-8", newline="\n")

    refused = lane.close()

    assert refused.returncode != 0
    payload = refused.json()
    assert payload["state"] == "PENDING_SYNC"
    assert "质量验证之后又被改动" in payload["reason"]
    assert {path: (drill.root / path).read_bytes() for path in lane.files} == original
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    assert ContinuityStore(drill.root).get_mission(lane.mission_id).state.value == "ACCEPTED"


def test_i05_a_control_root_file_changed_by_someone_else_is_a_conflict_and_nothing_is_written(
    tmp_path: Path, benchmark_tar: bytes  # noqa: F811
) -> None:
    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-IDE-I05", comment_files(drill.root, "IDE 路线：控制根冲突"))
    lane.walk_to_acceptance()
    relative = next(iter(lane.files))
    foreign = (drill.root / relative).read_text(encoding="utf-8") + "// 别人在控制根里改的\n"
    (drill.root / relative).write_text(foreign, encoding="utf-8", newline="\n")

    refused = lane.close()

    assert refused.returncode != 0
    assert "可能被别人改过" in refused.json()["reason"]
    assert (drill.root / relative).read_text(encoding="utf-8") == foreign

    # The user resolves it (here: puts the baseline back) and retries; the same command then closes.
    git(drill.root, "checkout", "--", relative)
    retried = lane.close()
    assert retried.returncode == 0, drill.transcript()
    assert (drill.root / relative).read_text(encoding="utf-8") == lane.files[relative]


def test_i06_bytes_already_copied_by_hand_are_accepted_as_they_are(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """The D08 track 2 situation: the agent had already copied the files back; closure must not trip over it."""

    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, "REQ-IDE-I06", comment_files(drill.root, "IDE 路线：已手工拷回"))
    lane.walk_to_acceptance()
    for relative in lane.files:
        (drill.root / relative).write_bytes((lane.worktree / relative).read_bytes())

    closed = lane.close()

    assert closed.returncode == 0, drill.transcript()
    assert closed.json()["state"] == "COMPLETED"


@pytest.mark.parametrize("command", ["verify", "close"])
def test_i07_both_commands_refuse_inside_a_worktree(tmp_path: Path, benchmark_tar: bytes, command: str) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    lane = Lane(drill, f"REQ-IDE-I07{command.upper()}", comment_files(drill.root, "IDE 路线：工作树里不许跑"))
    lane.start()
    arguments = ["pm", command, "--mission-id", lane.mission_id] + (["--lease-wallet"] if command == "verify" else [])
    inside = subprocess.run(  # noqa: S603 - the drill's own launcher
        [sys.executable, str(drill.tools / "launcher.py"), "-w", str(lane.worktree), *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=drill._env(), timeout=600,
    )

    assert inside.returncode != 0, inside.stdout

