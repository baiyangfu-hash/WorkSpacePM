"""Interlock matrix, defence line 2 (CHG-SCPT-2026-476): exit drills with the production guards switched on.

A drill puts the ledger into an abnormal state and then walks the way out with the real command line.  Two rules make it more
than the unit tests that already exist:

* **The state may be made by writing the ledger directly (an expired lease cannot be made any other way), the way out may not:**
  every exit step runs through ``cli`` with the guards the cockpit ships with.  ``identity_guard_off`` is refused for a test marked
  ``production_guards`` (see ``tests/conftest.py``); ``control_root_guard_switch`` only puts the production control-root rule back
  after the scene is built.
* **A refusal must say which guard refused** (``GuardRefusal.guard_id``) and that guard must be one the matrix declares for the
  step's command.  A guard that fires but is not in the matrix is a hole in the matrix.

The row that cannot pass today (the recovery chain under a runtime-identity conflict) is a strict ``xfail`` with a TD number: it
turns green when the recovery order lands, and the strict flag then forces someone to turn it into an ordinary test.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner, Result

from auto_pm.contracts.guard_refusal import GuardRefusal
from auto_pm.contracts.interlock_matrix import COMMANDS, GUARDS, STATES
from auto_pm.ui.cli import runtime_identity_guard
from auto_pm.ui.cli.__main__ import cli
from tests.cli.test_continuity import _repository, _settlement_ready, _write_card
from tests.core.test_continuity_resume_service import _run, _work, _workspace

pytestmark = pytest.mark.production_guards

PROJECT = "SW-2026-008"
DECISION = "DEC-20260911-5C37A985"


def _ledger_digest(root: Path) -> str:
    """Hash of every row of every table: a read-only command must leave it unchanged."""

    db = root / ".auto-pm" / "continuity.db"
    digest = hashlib.sha256()
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            digest.update(name.encode())
            for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall():  # noqa: S608 - table names come from sqlite_master
                digest.update(repr(row).encode())
    return digest.hexdigest()


def _cli(root: Path, *args: str) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), *args], catch_exceptions=False)


def _json(result: Result) -> dict[str, object]:
    assert result.exit_code == 0, result.output
    start = result.output.index("{")
    return dict(json.JSONDecoder().raw_decode(result.output[start:])[0])


def _finished_work_with_live_run(root: Path) -> None:
    """The sample from the ledger: the Work was accepted, the Run was left RUNNING with a lease that has expired."""

    from auto_pm.application.core.work_registry_service import WorkRegistryService
    from auto_pm.contracts.continuity import WorkState

    _work(root, "WORK-ACCEPTED")
    _run(root, work_id="WORK-ACCEPTED", run_id="RUN-ACCEPTED")
    registry = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    registry.transition("WORK-ACCEPTED", WorkState.IN_PROGRESS, "start-accepted")
    registry.transition("WORK-ACCEPTED", WorkState.VERIFYING, "verify-accepted")
    registry.transition("WORK-ACCEPTED", WorkState.ACCEPTED, "accept-accepted")


# ---------------------------------------------------------------------------------------------------------------------
# Row LIVE_RUN_UNDER_FINISHED_WORK: orient must see it, the plan must name the way out, neither may write
# ---------------------------------------------------------------------------------------------------------------------


def test_orient_sees_a_live_run_under_a_finished_work_and_prints_the_way_out(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _finished_work_with_live_run(tmp_path)
    before = _ledger_digest(tmp_path)

    result = _cli(tmp_path, "pm", "orient", PROJECT, "--json")
    payload = _json(result)

    assert payload["conflicts"] == ["LIVE_RUN_UNDER_FINISHED_WORK"]
    hints = payload["exit_hints"]
    assert isinstance(hints, list) and len(hints) == 1 and "RUN-ACCEPTED" in hints[0]
    assert "continuity recovery plan" in hints[0]
    text = _cli(tmp_path, "pm", "orient", PROJECT).output
    assert "冲突: LIVE_RUN_UNDER_FINISHED_WORK" in text and "出口:" in text
    assert _ledger_digest(tmp_path) == before


def test_recovery_plan_prints_the_full_chain_with_the_run_filled_in_and_writes_nothing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _finished_work_with_live_run(tmp_path)
    before = _ledger_digest(tmp_path)

    result = _cli(tmp_path, "continuity", "recovery", "plan", "--pid", PROJECT, "--run-id", "RUN-ACCEPTED")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "LIVE_RUN_UNDER_FINISHED_WORK" in out
    assert "--target-run-id RUN-ACCEPTED" in out and f"--pid {PROJECT}" in out
    state = STATES["LIVE_RUN_UNDER_FINISHED_WORK"]
    for index in range(1, len(state.exit_steps) + 1):
        assert f"  {index}. " in out
    assert "<RECOVERY_DECISION>" in out  # what the ledger does not know stays a placeholder
    assert _ledger_digest(tmp_path) == before


def test_recovery_plan_from_orient_plans_every_conflict(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _finished_work_with_live_run(tmp_path)
    result = _cli(tmp_path, "continuity", "recovery", "plan", "--pid", PROJECT, "--from-orient")
    assert result.exit_code == 0 and "LIVE_RUN_UNDER_FINISHED_WORK" in result.output


def test_a_healthy_ledger_has_no_conflict_and_no_hint(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-HEALTHY")
    _run(tmp_path, work_id="WORK-HEALTHY", run_id="RUN-HEALTHY")
    payload = _json(_cli(tmp_path, "pm", "orient", PROJECT, "--json"))
    conflicts = payload["conflicts"]
    assert isinstance(conflicts, list) and "LIVE_RUN_UNDER_FINISHED_WORK" not in conflicts


def test_recovery_plan_refuses_a_run_that_is_not_abnormal(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-FINE")
    _run(tmp_path, work_id="WORK-FINE", run_id="RUN-FINE")
    result = _cli(tmp_path, "continuity", "recovery", "plan", "--pid", PROJECT, "--run-id", "RUN-FINE")
    # The lease of this Run is long gone in the fixture's clock (2026-09-09), so it is the expired-lease state, not "fine".
    assert result.exit_code == 0 and "LEASE_EXPIRED" in result.output
    unknown = _cli(tmp_path, "continuity", "recovery", "plan", "--pid", PROJECT, "--state", "NOT_A_STATE")
    assert unknown.exit_code != 0 and "矩阵里没有状态" in unknown.output


# ---------------------------------------------------------------------------------------------------------------------
# Row LEASE_EXPIRED, settlement chain: runs through the real command line with the control-root rule on
# ---------------------------------------------------------------------------------------------------------------------


def _chain_tail(card: Path) -> list[tuple[str, list[str]]]:
    return [
        (
            "continuity work create",
            ["continuity", "work", "create", "--work-id", "WORK-DRILL", "--pid", "SW-TEST-001", "--kind", "GOVERNANCE", "--title", "drill",
             "--owner", "recovery-agent", "--scope", "README.md", "--scope", ".auto-pm/continuity.db", "--idempotency-key", "drill-work",
             "--card-file", str(card)],
        ),
        (
            "continuity work authorize",
            ["continuity", "work", "authorize", "--work-id", "WORK-DRILL", "--decision-id", DECISION, "--idempotency-key", "drill-auth"],
        ),
        (
            "continuity work transition",
            ["continuity", "work", "transition", "--work-id", "WORK-DRILL", "--to", "IN_PROGRESS", "--idempotency-key", "drill-wip"],
        ),
        (
            "continuity run start",
            ["continuity", "run", "start", "--run-id", "RUN-DRILL", "--work-id", "WORK-DRILL", "--executor", "recovery-agent", "--adapter",
             "codex", "--owned", ".auto-pm/continuity.db", "--declared-dirty", ".auto-pm/continuity.db", "--lease-token", "drill-secret",
             "--lease-seconds", "900", "--idempotency-key", "drill-run", "--recovery-change", "CHG-SCPT-2026-214"],
        ),
        (
            "continuity run transition",
            ["continuity", "run", "transition", "--run-id", "RUN-DRILL", "--to", "RUNNING", "--owner", "recovery-agent", "--lease-token",
             "drill-secret", "--idempotency-key", "drill-running"],
        ),
        (
            "continuity run settle-expired",
            ["continuity", "run", "settle-expired", "--target-run-id", "RUN-CLI-TARGET", "--recovery-run-id", "RUN-DRILL", "--recovery-owner",
             "recovery-agent", "--recovery-lease-token", "drill-secret", "--decision-id", DECISION, "--outcome", "CANCELLED", "--reason",
             "drill", "--idempotency-key", "drill-settle"],
        ),
    ]


def _walk_the_chain(
    tmp_path: Path,
    control_root_guard_switch: Callable[[], None],
    monkeypatch: pytest.MonkeyPatch,
    conflicts: tuple[str, ...],
) -> list[tuple[str, int, str]]:
    """Run the recovery chain tail; returns (matrix command, exit code, guard id that refused or '')."""

    _repository(tmp_path)
    _settlement_ready(tmp_path, start_recovery_run=False)
    card = _write_card(tmp_path, [("README.md", "存在"), (".auto-pm/continuity.db", "计划新增")])
    monkeypatch.setattr("auto_pm.application.core.implementation_card_tier.card_is_new", lambda _card: False)
    # The historical scene above starts its Runs in the throw-away repository root, which production forbids; the rule goes on
    # now, so every exit step below meets the control-root guard the cockpit ships with.
    control_root_guard_switch()

    class _Context:
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def resolve(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(conflicts=conflicts)

    monkeypatch.setattr(runtime_identity_guard, "WorkspaceContextService", _Context)
    report: list[tuple[str, int, str]] = []
    for command, args in _chain_tail(card):
        result = CliRunner().invoke(cli, ["-w", str(tmp_path), *args], standalone_mode=False)
        refusal = result.exception
        guard_id = refusal.guard_id if isinstance(refusal, GuardRefusal) else ""
        report.append((command, result.exit_code, guard_id))
        if guard_id:
            # reconciliation: the guard that fired must be one the matrix declares for this very command
            assert guard_id in GUARDS, f"{command}: 拦截来自未登记的护栏 {guard_id}"
            assert guard_id in COMMANDS[command].guards, f"{command}: 护栏 {guard_id} 拦了它，但命令表没有声明"
    return report


def test_settlement_chain_runs_end_to_end_with_the_production_guards_on(
    tmp_path: Path, control_root_guard_switch: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _walk_the_chain(tmp_path, control_root_guard_switch, monkeypatch, conflicts=())
    assert [(name, code) for name, code, _ in report] == [(name, 0) for name, _, _ in report], report
    assert len(report) == 6


@pytest.mark.xfail(
    strict=True,
    reason="TD-PENDING-476: under RUNTIME_IDENTITY_DIVERGENCE the chain is refused at its first step by G-IDENTITY-WRITE; the recovery order (P2) clears it",
)
def test_settlement_chain_runs_end_to_end_under_a_runtime_identity_conflict(
    tmp_path: Path, control_root_guard_switch: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _walk_the_chain(tmp_path, control_root_guard_switch, monkeypatch, conflicts=("RUNTIME_IDENTITY_DIVERGENCE",))
    assert all(code == 0 for _, code, _ in report), report


def test_under_a_runtime_identity_conflict_the_chain_stops_at_its_first_step_and_the_refusal_names_its_guard(
    tmp_path: Path, control_root_guard_switch: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins today's behaviour so the day the recovery order changes it, this file shows exactly which step changed.

    The first step is refused by ``G-IDENTITY-WRITE``.  The later steps cannot be observed in one run: they look up the Work or Run
    the first step should have created and stop on "does not exist" before their own guard speaks.  The per-step verdicts of the
    guard are pinned by ``tests/cli/test_continuity_runtime_identity.py`` (every ``GUARDED`` command), and the matrix's
    ``find_deadlocks`` reads them from the tables.
    """

    report = _walk_the_chain(tmp_path, control_root_guard_switch, monkeypatch, conflicts=("RUNTIME_IDENTITY_DIVERGENCE",))
    assert report[0] == ("continuity work create", 1, "G-IDENTITY-WRITE")
    assert all(code != 0 for _, code, _ in report)


def test_a_test_marked_production_guards_cannot_switch_the_identity_guard_off() -> None:
    from tests.conftest import identity_guard_use_is_refused

    class _Item:
        fixturenames = ("identity_guard_off",)

        def __init__(self, marked: bool) -> None:
            self._marked = marked

        def get_closest_marker(self, name: str) -> object | None:
            return object() if self._marked and name == "production_guards" else None

    assert identity_guard_use_is_refused(_Item(True)) is True
    assert identity_guard_use_is_refused(_Item(False)) is False
