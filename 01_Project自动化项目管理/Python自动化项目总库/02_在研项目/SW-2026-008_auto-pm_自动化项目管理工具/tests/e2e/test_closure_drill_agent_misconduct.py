"""The AI plays Trae: it follows the D08 prompt, then deliberately breaks its rules to see whether the cockpit holds.

Rules the D08 prompt gives the IDE agent (``/mnt/project-files/D08_第2第3道提示词_20261021.md``): every ``change`` command
carries ``--pid``; after acceptance only ``close_accepted`` closes the Mission; never move a Run or Work by hand; never edit the
database or governance JSON.  Each misconduct below is one the field has produced or could produce.  The release-directory
``__pycache__`` misconduct lives in ``test_release_pycache_drill.py``.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from tests.e2e.test_closure_drill import (
    APPROVER,
    MAIN_DOMAIN,
    PROJECT_ID,
    SECOND,
    SECOND_ID,
    assert_closed_and_clean,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    close_mission,
    comment_files,
    drive_mission,
    make_drill,
)


def _store(root: Path):  # type: ignore[no-untyped-def]
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    return ContinuityStore(root)


def _card(drill, request_id: str) -> dict:  # type: ignore[no-untyped-def,type-arg]
    return json.loads((drill.tools / f"card-{request_id}.json").read_text(encoding="utf-8"))


def test_r01_by_the_book_orient_shows_no_conflict_and_the_mission_closes(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    oriented = drill.cli("pm", "orient", PROJECT_ID, "--json")
    assert oriented.returncode == 0, drill.transcript()
    assert json.loads(oriented.stdout)["conflicts"] == []

    files = comment_files(drill.root, "按规矩做")
    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-ROLE-R01", files=files, declared=tuple(files))

    assert_closed_and_clean(drill, result, PROJECT_ID)


def test_r02_defect_2_hand_made_terminals_after_a_prepared_closure_are_refused(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """D08 track 1: closure prepared, then the agent pushed Run and Work to terminal by hand; card 178 refuses that."""

    drill = make_drill(tmp_path, benchmark_tar)
    token = secrets.token_urlsafe(32)
    files = comment_files(drill.root, "收口准备后手推终态")
    accepted = drive_mission(
        drill, project_id=PROJECT_ID, request_id="REQ-ROLE-R02", files=files, declared=tuple(files), stop_after="accept", lease_token=token
    )
    assert accepted.stage == "accepted", f"{accepted.stage}: {accepted.refusal}\n{drill.transcript()}"
    card = _card(drill, "REQ-ROLE-R02")
    half = drill.sdk("prepare", card)
    assert half.returncode == 0, drill.transcript()

    store = _store(drill.root)
    mission = store.get_mission(accepted.mission_id)
    assert mission.root_work_id
    run = store.list_runs(mission.root_work_id, include_terminal=True)[0]
    owner = store.get_lease(run.run_id).owner_id

    run_push = drill.cli(
        "continuity", "run", "transition", "--run-id", run.run_id, "--to", "SUCCEEDED", "--owner", owner,
        "--lease-token", token, "--idempotency-key", "agent-hand-run",
    )
    work_push = drill.cli(
        "continuity", "work", "transition", "--work-id", mission.root_work_id, "--to", "VERIFYING", "--idempotency-key", "agent-hand-work"
    )

    assert run_push.returncode != 0 and "close_accepted" in run_push.stderr, drill.transcript()
    assert work_push.returncode != 0 and "close_accepted" in work_push.stderr, drill.transcript()
    assert_closed_and_clean(drill, close_mission(drill, card, accepted.mission_id), PROJECT_ID)


def _same_number_in_both_projects(drill) -> str:  # type: ignore[no-untyped-def]
    """Project B already holds a hand-made sheet with the number project A's planning will draw (numbers are per project)."""

    created = drill.cli(
        "change", "create", "--pid", SECOND_ID, "--domain", MAIN_DOMAIN, "--nature", "DEF", "--scope", "MODULE",
        "--applicant", "现场", "--background", "另一个项目自己的变更单", "--necessity", "演练同号",
    )
    assert created.returncode == 0, drill.transcript()
    sheets = sorted((drill.root / SECOND).glob(f"**/CHG-{MAIN_DOMAIN}-*.md"))
    assert len(sheets) == 1, sheets
    return sheets[0].stem


def test_r03_change_without_pid_on_a_number_two_projects_share_is_refused(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar, second_project=True)
    shared = _same_number_in_both_projects(drill)
    files = comment_files(drill.root, "不带 --pid")
    accepted = drive_mission(
        drill, project_id=PROJECT_ID, request_id="REQ-ROLE-R03", files=files, declared=tuple(files), stop_after="accept"
    )
    assert accepted.stage == "accepted", f"{accepted.stage}: {accepted.refusal}\n{drill.transcript()}"
    assert accepted.change_id == shared
    before = {path: path.read_bytes() for path in drill.root.glob(f"**/{shared}.md") if ".auto-pm" not in path.parts}
    assert len(before) == 2

    blind = drill.cli("change", "transition", shared, "--to", "implementing", "--approver", APPROVER, "--comment", "忘了带 --pid")

    after = {path: path.read_bytes() for path in before}
    changed = sorted(str(path.relative_to(drill.root)) for path in before if after[path] != before[path])
    # Which project's sheet is hit first depends on directory order, so demand the refusal names the ambiguity.
    assert blind.returncode != 0, f"不带 --pid 的 change transition 被执行了，改动了: {changed}\n{blind.stdout}{blind.stderr}"
    assert changed == []
    assert "--pid" in blind.stdout + blind.stderr, f"拒绝的原因不是“单号在多个项目里”: {blind.stdout}{blind.stderr}"


def test_r04_defect_1_closure_writes_only_its_own_project_sheet_when_numbers_coincide(tmp_path: Path, benchmark_tar: bytes) -> None:  # noqa: F811
    """D08 track 1: closure looked the sheet up across the whole workspace and refused a duplicate; card 177 scopes it to the project."""

    drill = make_drill(tmp_path, benchmark_tar, second_project=True)
    shared = _same_number_in_both_projects(drill)
    other = next(path for path in (drill.root / SECOND).glob(f"**/{shared}.md"))
    other_bytes = other.read_bytes()
    files = comment_files(drill.root, "同号收口")

    result = drive_mission(drill, project_id=PROJECT_ID, request_id="REQ-ROLE-R04", files=files, declared=tuple(files))

    assert result.change_id == shared
    assert_closed_and_clean(drill, result, PROJECT_ID)
    assert other.read_bytes() == other_bytes
