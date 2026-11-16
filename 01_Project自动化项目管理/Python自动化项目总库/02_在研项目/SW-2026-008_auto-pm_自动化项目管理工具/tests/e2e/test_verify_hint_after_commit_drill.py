"""A commit made in the worktree while the Run is open: the hint ``pm verify`` prints must lead back to a passing verify.

DJ-2026-005 trial, round 2 T4b/T4c: the old hint said "turn the Run FAILED and start a new Run on the current HEAD".  Doing so
blocks the Work (D-109), and a BLOCKED Work cannot get a new Run, so the only exit left was cancelling the whole card.  The
hint now says to take the commit back into the index (``git reset --soft <the Run's git_head>``) and hand in again.  This
drill follows the printed command literally, in the same throw-away repository and ledger the closure drill uses.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.e2e.test_closure_drill import Drill, comment_files, make_drill
from tests.e2e.test_ide_lane_drill import EXECUTOR
from tests.e2e.test_pmf_plc import PROJECT_ID, benchmark_tar, git  # noqa: F401
from tests.e2e.test_raw_requirement_drill import _approve_from_one_sentence

_HINT = re.compile(r'git -C "(?P<worktree>[^"]+)" reset --soft (?P<head>[0-9a-f]{40})')


def _store(drill: Drill):  # type: ignore[no-untyped-def]
    from auto_pm.infrastructure.continuity_store import ContinuityStore  # noqa: PLC0415

    return ContinuityStore(drill.root)


def _transition(drill: Drill, run_id: str, state: str):  # type: ignore[no-untyped-def]
    return drill.cli(
        "continuity", "run", "transition", "--run-id", run_id, "--to", state, "--owner", EXECUTOR,
        "--lease-wallet", "--idempotency-key", f"{run_id}:{state}",
    )


def test_the_head_moved_hint_is_one_command_that_brings_verify_back(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    files = comment_files(drill.root, "试车 REQ-HINT-T4B")
    card, approved = _approve_from_one_sentence(drill, "REQ-HINT-T4B")
    assert approved.returncode == 0, approved.stdout + approved.stderr
    mission = next(
        item for item in _store(drill).list_missions(PROJECT_ID, include_terminal=True)
        if item.authority.change_id == card["change_id"]
    )
    started = drill.cli("pm", "confirm-start", "--mission-id", mission.mission_id)
    assert started.returncode == 0, started.stdout + started.stderr
    work_id = _store(drill).get_mission(mission.mission_id).root_work_id or ""
    worktree = drill.root / ".auto-pm" / "worktrees" / "hint-drill"
    git(drill.root, "worktree", "add", "-q", "--detach", str(worktree))
    start = [
        "continuity", "run", "start", "--run-id", "RUN-HINT-T4B", "--work-id", work_id, "--executor", EXECUTOR,
        "--adapter", "trae", "--worktree", str(worktree), "--lease-wallet", "--holder-pid", "none",
        "--idempotency-key", "RUN-HINT-T4B:start",
    ]
    for path in files:
        start += ["--owned", path, "--declared-dirty", path]
    assert drill.cli(*start).returncode == 0
    assert _transition(drill, "RUN-HINT-T4B", "RUNNING").returncode == 0
    for relative, text in files.items():
        (worktree / relative).write_text(text, encoding="utf-8", newline="\n")
    run_head = git(worktree, "rev-parse", "HEAD")
    git(worktree, "add", "-A")
    git(worktree, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "commit while the Run is open")
    assert _transition(drill, "RUN-HINT-T4B", "VERIFYING").returncode == 0

    refused = drill.cli("pm", "verify", "--mission-id", mission.mission_id, "--lease-wallet")

    output = refused.stdout + refused.stderr
    assert refused.returncode == 1, output
    assert "转 FAILED，在当前 HEAD" not in output
    hint = _HINT.search(output)
    assert hint is not None, output
    assert hint["head"] == run_head and Path(hint["worktree"]).resolve() == worktree.resolve()

    subprocess.run(["git", "-C", hint["worktree"], "reset", "--soft", hint["head"]], check=True, capture_output=True)
    again = drill.cli("pm", "verify", "--mission-id", mission.mission_id, "--lease-wallet")

    assert again.returncode == 0, again.stdout + again.stderr
    store = _store(drill)
    assert store.get_mission(mission.mission_id).state.value == "ACCEPTANCE_PENDING"
    assert store.get_work(work_id).state.value == "IN_PROGRESS"  # never BLOCKED: the hint does not send anyone through FAILED
