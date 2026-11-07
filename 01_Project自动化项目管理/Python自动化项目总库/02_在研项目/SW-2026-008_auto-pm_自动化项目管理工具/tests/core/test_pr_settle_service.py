"""D-32: a merge on GitHub triggers nothing in the ledger.  The scan finds Runs whose work is already in main and names the legal next commands.

Real Git (the Run's worktree and a fake ``origin/main`` ref), a real ledger with a real Run; nothing is mocked except where a case needs a
worktree that no longer exists.  The scan is read-only: the ledger is compared before and after.
"""

from __future__ import annotations

import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.pr_settle_service import PrSettleError, PrSettleService, render
from auto_pm.ui.cli.pr import pr_group
from tests.core.test_continuity_execution_service import Clock, _services, _start

PROJECT = "SW-2026-008"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _scene(tmp_path: Path) -> tuple[Any, str]:
    _, service = _services(tmp_path, Clock())
    start = _git(tmp_path, "rev-parse", "HEAD")
    _start(service)
    return service, start


def _commit(tmp_path: Path) -> str:
    (tmp_path / "work.txt").write_text("work\n", encoding="utf-8")
    _git(tmp_path, "add", "work.txt")
    _git(tmp_path, "commit", "-m", "the work")
    return _git(tmp_path, "rev-parse", "HEAD")


def _publish(tmp_path: Path, sha: str) -> None:
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", sha)


def _event_count(root: Path) -> int:
    with closing(sqlite3.connect(root / ".auto-pm" / "continuity.db")) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])


def test_a_run_whose_commit_is_in_main_is_found_with_its_next_steps(tmp_path: Path) -> None:
    service, _ = _scene(tmp_path)
    _publish(tmp_path, _commit(tmp_path))

    (item,) = PrSettleService(tmp_path, service._store).scan(PROJECT)

    assert item.merged and item.run_id == "RUN-001" and item.work_id == "WORK-001"
    assert item.next_steps
    assert not any(
        f"continuity {kind} transition" in step
        for step in item.next_steps
        for kind in ("run", "work", "mission")
    )
    assert any("change transition" in step for step in item.next_steps)


def test_a_commit_not_yet_in_main_is_not_reported_as_merged(tmp_path: Path) -> None:
    service, start = _scene(tmp_path)
    _publish(tmp_path, start)
    _commit(tmp_path)

    (item,) = PrSettleService(tmp_path, service._store).scan(PROJECT)

    assert not item.merged and "not in origin/main yet" in item.why and item.next_steps == ()


def test_a_run_with_no_commit_since_it_started_is_never_merged_even_though_its_start_is_in_main(
    tmp_path: Path,
) -> None:
    service, start = _scene(tmp_path)
    _publish(tmp_path, start)

    (item,) = PrSettleService(tmp_path, service._store).scan(PROJECT)

    assert not item.merged and item.why == "no commit since the Run started"


def test_when_the_worktree_is_gone_the_latest_checkpoint_head_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = _scene(tmp_path)
    merged_head = _commit(tmp_path)
    _publish(tmp_path, merged_head)
    store = service._store
    run = store.get_run("RUN-001").model_copy(
        update={"worktree_path": str(tmp_path / "removed-worktree")}
    )
    monkeypatch.setattr(
        store, "latest_checkpoint", lambda _run_id: SimpleNamespace(git_head=merged_head)
    )

    item = PrSettleService(tmp_path, store)._judge(run, None)

    assert item.merged and item.head == merged_head


def test_the_scan_writes_nothing_to_the_ledger(tmp_path: Path) -> None:
    service, _ = _scene(tmp_path)
    _publish(tmp_path, _commit(tmp_path))
    before = _event_count(tmp_path)
    states = (service._store.get_run("RUN-001").state, service._store.get_work("WORK-001").state)

    PrSettleService(tmp_path, service._store).scan(PROJECT)

    assert _event_count(tmp_path) == before
    assert (
        service._store.get_run("RUN-001").state,
        service._store.get_work("WORK-001").state,
    ) == states


def test_without_a_base_branch_the_scan_says_to_fetch_instead_of_guessing(tmp_path: Path) -> None:
    service, _ = _scene(tmp_path)
    with pytest.raises(PrSettleError, match="git fetch"):
        PrSettleService(tmp_path, service._store).scan(PROJECT)


@pytest.mark.parametrize(
    ("mission_state", "must_contain"),
    [
        ("ACCEPTED", "pm close --mission-id M-1"),
        ("ACCEPTANCE_PENDING", "等用户验收"),
        ("CLOSED", "recovery plan"),
        (None, "没有绑定 Mission"),
    ],
)
def test_next_steps_follow_the_mission_state_and_never_move_a_state(
    mission_state: str | None, must_contain: str
) -> None:
    steps = PrSettleService._next_steps(
        "RUN-001", "WORK-001", "M-1" if mission_state else None, mission_state, expired=False
    )
    assert any(must_contain in step for step in steps)
    assert not any(
        "run transition" in step or "work transition" in step or "mission transition" in step
        for step in steps
    )


def test_an_expired_lease_adds_the_read_only_recovery_plan() -> None:
    steps = PrSettleService._next_steps("RUN-001", "WORK-001", "M-1", "ACCEPTED", expired=True)
    assert any("租约已过期" in step and "recovery plan" in step for step in steps)


def test_render_lists_waiting_runs_first_with_their_steps(tmp_path: Path) -> None:
    service, _ = _scene(tmp_path)
    _publish(tmp_path, _commit(tmp_path))
    lines = render(PrSettleService(tmp_path, service._store).scan(PROJECT))
    assert lines[0].startswith("开着的 Run 1 个，其中 1 个的工作已并入主线")
    assert "RUN-001" in lines[1]


def _invoke(tmp_path: Path, *argv: str) -> Any:
    return CliRunner().invoke(
        pr_group,
        ["settle-scan", *argv],
        obj=SimpleNamespace(control_root=str(tmp_path), workspace_root=str(tmp_path)),
    )


def test_cli_exit_codes_say_waiting_nothing_waiting_and_cannot_judge(tmp_path: Path) -> None:
    service, start = _scene(tmp_path)
    assert _invoke(tmp_path, PROJECT).exit_code == 2  # no origin/main yet
    _publish(tmp_path, start)
    assert _invoke(tmp_path, PROJECT).exit_code == 0  # nothing committed since start
    _publish(tmp_path, _commit(tmp_path))
    result = _invoke(tmp_path, PROJECT)
    assert result.exit_code == 1 and "RUN-001" in result.output
    service._store.close_read_snapshot()


def test_settle_scan_has_no_apply_option_so_it_can_never_write() -> None:
    """User decision 2026-11-07: no ``--apply`` that runs ``pm close`` by itself.  The command stays read-only; adding a write option must fail here."""

    command = pr_group.commands["settle-scan"]
    options = {
        name
        for param in command.params
        for name in getattr(param, "opts", [])
        if name.startswith("-")
    }
    assert options == {"--base"}


# ── gaps found by the independent audit of #594 (four mutants survived) ──


def test_when_git_cannot_judge_the_run_is_never_reported_as_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit git does not know (exit 128, neither 0 nor 1) must not turn into "merged, ready to close"."""
    service, _ = _scene(tmp_path)
    _publish(tmp_path, _commit(tmp_path))
    store = service._store
    run = store.get_run("RUN-001").model_copy(
        update={"worktree_path": str(tmp_path / "removed-worktree")}
    )
    unknown_head = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setattr(
        store, "latest_checkpoint", lambda _run_id: SimpleNamespace(git_head=unknown_head)
    )

    item = PrSettleService(tmp_path, store)._judge(run, None)

    assert item.merged is False
    assert item.why.startswith("unknown: git could not judge")
    assert item.next_steps == ()


@pytest.mark.parametrize("state", ["ACCEPTED", "ACCEPTANCE_PENDING", "CLOSED", "CANCELLED", None])
def test_each_mission_state_gets_its_own_first_step(state: str | None) -> None:
    steps = PrSettleService._next_steps(
        "RUN-001", "WORK-001", "M-1" if state else None, state, expired=False
    )
    first = steps[0]
    if state == "ACCEPTED":
        assert first.startswith("main.py pm close --mission-id M-1") and "一步收口" in first
        assert "等用户验收" not in first
    elif state == "ACCEPTANCE_PENDING":
        assert "等用户验收" in first and not first.startswith("main.py pm close")
        assert "pm accept --mission-id M-1" in first
    elif state in {"CLOSED", "CANCELLED"}:
        assert f"已是 {state}" in first and "continuity recovery plan" in first
        assert "pm close" not in first
    else:
        assert "没有绑定 Mission" in first
    assert "change transition" in steps[-1]


@pytest.mark.parametrize(
    ("expires_at", "expired"),
    [
        ("2020-01-01T00:00:00Z", True),
        ("2020-01-01T00:00:00+00:00", True),
        ("2020-01-01T00:00:00", True),  # no zone: read as UTC
        ("2999-01-01T00:00:00Z", False),
        ("2999-01-01T00:00:00+00:00", False),
        ("2999-01-01T00:00:00", False),
    ],
)
def test_lease_expiry_is_computed_for_z_offset_and_naive_timestamps(
    expires_at: str, expired: bool
) -> None:
    store = SimpleNamespace(get_lease=lambda _run_id: SimpleNamespace(expires_at=expires_at))
    assert PrSettleService(Path("."), store)._lease_expired("RUN-001") is expired  # type: ignore[arg-type]


def test_a_missing_lease_does_not_count_as_expired() -> None:
    from auto_pm.infrastructure.continuity_store import ContinuityStoreError

    def _no_lease(_run_id: str) -> Any:
        raise ContinuityStoreError("no lease")

    store = SimpleNamespace(get_lease=_no_lease)
    assert PrSettleService(Path("."), store)._lease_expired("RUN-001") is False  # type: ignore[arg-type]


def test_a_merged_run_with_an_expired_lease_gets_the_recovery_step_through_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = _scene(tmp_path)
    _publish(tmp_path, _commit(tmp_path))
    store = service._store
    monkeypatch.setattr(
        store, "get_lease", lambda _run_id: SimpleNamespace(expires_at="2020-01-01T00:00:00Z")
    )

    (item,) = PrSettleService(tmp_path, store).scan(PROJECT)

    assert item.merged and item.lease_expired
    assert any("租约已过期" in step for step in item.next_steps)
