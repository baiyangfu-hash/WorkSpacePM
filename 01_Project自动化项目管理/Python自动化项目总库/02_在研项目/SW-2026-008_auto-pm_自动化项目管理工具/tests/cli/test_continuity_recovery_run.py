"""The recovery Run of an administrative settlement may use the control root as its worktree; no other Run may.

The store binds the recovery Run of ``settle-expired``, the terminal-lease fence and reconcile, the legacy fence and the Work
adjudication to the control-root main worktree, while ``run start`` refuses the control root for every Run (WS-001).  The two
rules locked each other: an expired Run could never be settled from the command line.  ``run start --recovery-change`` is the
narrow way out, and the service checks every condition itself.

Each scene is built with the suite's usual switch-off of the control-root rule (its historical Runs start in the throw-away
repository root), then ``control_root_guard_switch`` puts the production rule back before the command under test runs.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.continuity_execution_service import RECOVERY_RUN_ACTIONS
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.contracts.continuity import RunState, WorkKind, WorkState
from auto_pm.contracts.decision_package import RuntimeDecisionAction
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.cli.test_continuity import (
    _invoke,
    _repository,
    _run_count,
    _settlement_args,
    _settlement_ready,
)

# Like tests/cli/test_continuity.py: these scenes have no registered project anchor.
pytestmark = pytest.mark.usefixtures("identity_guard_off")


def _start_recovery_run_args(
    *extra: str,
    work_id: str = "WORK-CLI-RECOVERY",
    owned: tuple[str, ...] = (".auto-pm/continuity.db",),
    run_id: str = "RUN-CLI-RECOVERY",
    key: str = "cli-recovery-run",
) -> list[str]:
    """``run start`` for the recovery Run, with no ``--worktree``: the control root itself, where the store binds a recovery Run."""

    owned_options = [argument for path in owned for argument in ("--owned", path)]
    declared = ".auto-pm/continuity.db" if ".auto-pm/continuity.db" in owned else owned[0]
    return [
        "run", "start", "--run-id", run_id, "--work-id", work_id, "--executor", "recovery-agent",
        "--adapter", "codex", *owned_options, "--declared-dirty", declared,
        "--lease-token", "recovery-cli-secret", "--lease-seconds", "900", "--idempotency-key", key, *extra,
    ]


def test_an_expired_run_is_settled_from_the_command_line_by_a_recovery_run_started_on_the_control_root(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None]
) -> None:
    """The deadlock: the store wants the recovery Run on the control root, and ``run start`` refused the control root for every Run."""
    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False)
    control_root_guard_switch()

    started = _invoke(cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-214"))
    assert started.exit_code == 0, started.output
    assert json.loads(started.output)["worktree_path"] == str(tmp_path.resolve())
    running = _invoke(
        cli_runner, tmp_path,
        ["run", "transition", "--run-id", "RUN-CLI-RECOVERY", "--to", "RUNNING", "--owner", "recovery-agent",
         "--lease-token", "recovery-cli-secret", "--idempotency-key", "cli-recovery-running"],
    )
    assert running.exit_code == 0, running.output
    settled = _invoke(cli_runner, tmp_path, _settlement_args())

    assert settled.exit_code == 0, settled.output
    assert json.loads(settled.output)["state"] == RunState.CANCELLED.value
    store = ContinuityStore(tmp_path)  # the ledger now says the target is done: the "still open" test reads exactly this
    assert store.aggregate_has_event("run", "RUN-CLI-TARGET", "RUN_EXPIRED_SETTLED")
    assert not store.aggregate_has_event("run", "RUN-CLI-TARGET", "RUN_TERMINAL_LEASE_FENCED")


def test_an_ordinary_run_is_still_refused_the_control_root_with_or_without_a_recovery_change(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None]
) -> None:
    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False)
    works = WorkRegistryService(tmp_path)
    works.create_work(
        work_id="WORK-CLI-ORDINARY", subject_project_id="SW-TEST-001", kind=WorkKind.GOVERNANCE, title="Ordinary", owner="agent-a",
        scope_paths=["README.md"], source_fingerprint="sha256:ordinary", idempotency_key="cli-ordinary-work",
    )
    works.authorize("WORK-CLI-ORDINARY", "DEC-20260910-A2TARGT1", "cli-authorize-ordinary")
    works.transition("WORK-CLI-ORDINARY", WorkState.IN_PROGRESS, "cli-start-ordinary")
    before = _run_count(tmp_path)
    control_root_guard_switch()

    plain = _invoke(cli_runner, tmp_path, _start_recovery_run_args(work_id="WORK-CLI-ORDINARY"))
    claimed = _invoke(
        cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-213", work_id="WORK-CLI-ORDINARY")
    )

    assert plain.exit_code == 1 and "控制根" in plain.output and "--recovery-change" in plain.output
    assert claimed.exit_code == 1 and "未声明任何恢复类 runtime_capability" in claimed.output
    assert _run_count(tmp_path) == before


@pytest.mark.parametrize(
    ("change", "owned", "expected"),
    [
        ("CHG-SCPT-2026-999", (".auto-pm/continuity.db",), "与 --recovery-change CHG-SCPT-2026-999 不一致"),
        ("not-a-change", (".auto-pm/continuity.db",), "不是规范的 CHG 编号"),
        ("CHG-SCPT-2026-214", ("README.md",), "owned_paths 只能是 .auto-pm/continuity.db"),
        # a business file next to the database is still a business file: the control root runs cockpit commands only
        ("CHG-SCPT-2026-214", ("README.md", ".auto-pm/continuity.db"), "owned_paths 只能是 .auto-pm/continuity.db"),
    ],
)
def test_a_recovery_run_that_does_not_meet_every_condition_is_refused_and_nothing_is_written(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None], change: str, owned: tuple[str, ...], expected: str
) -> None:
    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False)
    before = _run_count(tmp_path)
    control_root_guard_switch()

    refused = _invoke(cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", change, owned=owned))

    assert refused.exit_code == 1 and expected in refused.output
    assert _run_count(tmp_path) == before


@pytest.mark.parametrize(
    ("action", "allowed"),
    [(action, action is not RuntimeDecisionAction.REVOKE_UNSTARTED_RUN) for action in RuntimeDecisionAction],
)
def test_every_recovery_action_may_start_its_recovery_run_on_the_control_root_and_nothing_else_may(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None], action: RuntimeDecisionAction, allowed: bool
) -> None:
    """The store binds the recovery Run of the settlement, the lease fence and reconcile, the legacy fence and the adjudication to the root."""
    _repository(tmp_path)
    target = {
        RuntimeDecisionAction.SETTLE_EXPIRED_RUN: "expired",
        RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK: "blocked",
    }.get(action, "terminal")  # the lease fence/reconcile act on a Run that already ended
    _settlement_ready(tmp_path, start_recovery_run=False, action=action, target=target)
    control_root_guard_switch()

    result = _invoke(cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-214"))

    assert (result.exit_code == 0) is allowed, result.output
    if not allowed:
        assert "未声明任何恢复类 runtime_capability" in result.output


def test_the_recovery_exception_is_for_exactly_the_actions_whose_recovery_run_the_store_binds_to_the_control_root() -> None:
    assert RECOVERY_RUN_ACTIONS == set(RuntimeDecisionAction) - {RuntimeDecisionAction.REVOKE_UNSTARTED_RUN}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


RECOVERY_DECISION = ".auto-pm/decisions/DEC-20260911-5C37A985.json"
ORIGINAL_DECISION = ".auto-pm/decisions/DEC-20260910-A2TARGT1.json"


@pytest.mark.parametrize("which", [RECOVERY_DECISION, ORIGINAL_DECISION])
@pytest.mark.parametrize("how", ["edited", "untracked"])
def test_a_decision_that_is_not_committed_and_clean_at_head_refuses_the_recovery_run_and_writes_nothing(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None], which: str, how: str
) -> None:
    """The recovery Decision and the Decision it settles are bound to the control-root HEAD when the recovery Run starts, not only at settlement."""
    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False)
    if how == "edited":
        with (tmp_path / which).open("a", encoding="utf-8") as handle:
            handle.write("\n")
    else:
        _git(tmp_path, "rm", "--cached", "-q", "--", which)
    before = _run_count(tmp_path)
    control_root_guard_switch()

    refused = _invoke(cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-214"))

    assert refused.exit_code == 1 and "未被控制根 Git 跟踪或相对 HEAD 有改动" in refused.output
    assert _run_count(tmp_path) == before


def test_one_approval_is_not_a_standing_permission_the_target_must_still_be_open(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None]
) -> None:
    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False, target="terminal")  # the Decision settles an expired Run; this one already ended
    before = _run_count(tmp_path)
    control_root_guard_switch()

    refused = _invoke(cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-214"))

    assert refused.exit_code == 1 and "已处理完毕或不处于可恢复状态" in refused.output
    assert _run_count(tmp_path) == before


def test_one_recovery_work_has_one_live_run_in_the_control_root_at_a_time(
    cli_runner: CliRunner, tmp_path: Path, control_root_guard_switch: Callable[[], None]
) -> None:
    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False)
    control_root_guard_switch()
    first = _invoke(cli_runner, tmp_path, _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-214"))
    assert first.exit_code == 0, first.output
    before = _run_count(tmp_path)

    second = _invoke(
        cli_runner, tmp_path,
        _start_recovery_run_args("--recovery-change", "CHG-SCPT-2026-214", run_id="RUN-CLI-RECOVERY-2", key="cli-recovery-run-2"),
    )

    assert second.exit_code == 1 and "已有未终态 Run RUN-CLI-RECOVERY" in second.output
    assert _run_count(tmp_path) == before
