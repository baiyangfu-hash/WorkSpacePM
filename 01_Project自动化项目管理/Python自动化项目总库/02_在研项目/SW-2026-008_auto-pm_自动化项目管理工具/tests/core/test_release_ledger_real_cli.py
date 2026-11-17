"""CHG-SCPT-2026-709: the deploy bookkeeping (``release_ledger.open_books`` / ``close_books``) against the **real** cockpit commands.

``tests/core/test_release_ledger.py`` drives the bookkeeping with a fake ledger that accepts whatever it is sent, so two wrong commands
went through it unnoticed and only failed on the user's machine at the first real deploy (2026-11-17, ``deploy_real.txt``):

* the Decision id was ``DEC-<date>-DEPLOY<last 8 of the slug>`` (``DEC-20261117-DEPLOY-DAD7036``), which ``decision create`` refuses
  (``contracts.decision_package.DECISION_ID_PATTERN``: ``DEC-`` + 8-digit date + ``-`` + 8 of ``[A-Z0-9]``);
* ``continuity work create`` for a write Work requires ``--card-file`` (the card must pass the pre-start precheck), and the plan never
  carried one.

The card is the one the cockpit generates for the release (``release_card.ensure_card``, the same call ``release_wiring.real_deploy``
makes when no ``--card-file`` is given), so the real ``work create`` and the real post-switch ``implementation-card precheck`` both
judge the generated card, with its tier line checked by the real classifier.

Here every command the bookkeeping sends goes through the real ``auto_pm.ui.cli.__main__.cli`` in this process (``CliRunner``, the way
``tests/e2e/test_exit_drill.py`` drives the exit chains), in a throw-away control root with its own ledger.  The port is the real
``release_wiring.CockpitLedgerPort`` (in-process reads, the station opened with ``git worktree add``); only how a command is *run* differs
from production (``CliRunner`` instead of a ``main.py`` subprocess).  The production control-root rule is on (``control_root_guard_on``):
the Run must start in the deploy station, never in the control root.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from auto_pm.application.core import release_card
from auto_pm.application.core import release_ledger as rl
from auto_pm.application.core import release_wiring as wiring
from auto_pm.contracts.decision_package import is_canonical_decision_id
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli import runtime_identity_guard
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_continuity_resume_service import _workspace
from tests.core.test_implementation_card_tier import _install_classifier

CONFIRM = "user-confirmation:2026-11-17T03:26:28Z"
APPROVER = "baiyang"
OLD = "1.3.3-84d4729"
COMMIT = "dad70364ec87424216f5b7c256bda47cbde25aa6"
RELEASE = "1.3.3-dad7036"
CONTAINER = "00_Infrastructure/auto_pm"
POINTERS = ("deployment_manifest.json", "active_release.json", "previous_release.json")
PAYLOAD = ("auto_pm/__init__.py", "auto_pm/ui/cli/__main__.py", "templates/README.md", "release_meta.json")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def _control_root(root: Path) -> Path:
    """A control root like the user's: the project registered, the three pointer files committed, the tier classifier in place, and the
    intake card the cockpit generates for this release (the pointer files exist, the release folder and its files are new)."""

    project = _workspace(root)
    # The project marker ChangeService locates the project by: _workspace writes it; written again here, same bytes, so the fixture
    # health scan (tests/test_fixture_health.py) sees it in this file.
    (project / ".copier-answers.yml").write_text((project / ".copier-answers.yml").read_text(encoding="utf-8"), encoding="utf-8")
    container = root / CONTAINER
    container.mkdir(parents=True)
    for name in POINTERS:
        body: dict[str, object] = {"releases": {OLD: {}}} if name == "deployment_manifest.json" else {"schema_version": "release_pointer.v1", "slot": name, "release_id": OLD}
        (container / name).write_text(json.dumps(body), encoding="utf-8")
    _git(root, "add", CONTAINER)
    _git(root, "-c", "user.name=Deploy Test", "-c", "user.email=deploy@example.invalid", "commit", "-q", "-m", "pointers")
    _install_classifier(root)  # untracked, like the user's control root has it: the card's tier line is judged for real
    return release_card.ensure_card(root, release_id=RELEASE, old_release=OLD, commit=COMMIT, files=PAYLOAD)


def _runner(root: Path) -> wiring.Runner:
    """``main.py <args>`` in the control root, run in this process by the real command line (production runs it as a subprocess)."""

    def run(args: Sequence[str]) -> tuple[int, str]:
        result = CliRunner().invoke(cli, ["-w", str(root), *args])
        output = result.output
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            output += f"\n{type(result.exception).__name__}: {result.exception}"
        return result.exit_code, output

    return run


@pytest.fixture
def deploy_scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, control_root_guard_on: None) -> SimpleNamespace:
    card = _control_root(tmp_path)
    assert card == tmp_path / ".auto-pm" / "release-candidates" / RELEASE / "release_card.md"

    class _NoConflicts:  # the runtime identity guard stays in the path, reading a clean identity (same as test_exit_drill.py)
        def __init__(self, *_a: object, **_k: object) -> None: ...

        def resolve(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(conflicts=())

    monkeypatch.setattr(runtime_identity_guard, "WorkspaceContextService", _NoConflicts)
    report = SimpleNamespace(release_id=RELEASE, commit=COMMIT)
    plan, _backup = wiring.plan_for(tmp_path, report, approver=APPROVER, confirm_ref=CONFIRM, card_file=card)
    port = wiring.CockpitLedgerPort(tmp_path, run=_runner(tmp_path), changes=ChangeService(str(tmp_path)), store=ContinuityStore(tmp_path))
    return SimpleNamespace(root=tmp_path, plan=plan, port=port, card=card)


def _open(scene: SimpleNamespace) -> rl.Books:
    return rl.open_books(scene.plan, scene.port, background="一键发版：测试", necessity="让修复对所有对话生效")


def _close(scene: SimpleNamespace, change_id: str) -> rl.Books:
    return rl.close_books(
        scene.plan, scene.port, change_id=change_id,
        evidence=[f"release={RELEASE} commit={COMMIT}", "post_checks sha256=0" * 1], conclusion=f"验收通过：有效版本 {RELEASE}",
    )


@pytest.mark.parametrize("caller", ["", "claude"], ids=["user-terminal", "claude-agent"])
def test_open_and_close_books_run_through_the_real_commands_to_closed_succeeded_completed(
    deploy_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, caller: str
) -> None:
    """Both callers the deploy has: the user in a terminal, and an agent session carrying the user's confirmation reference."""

    if caller:
        monkeypatch.setenv("AUTO_PM_AGENT", caller)
    plan, port = deploy_scene.plan, deploy_scene.port

    opened = _open(deploy_scene)  # every command below is the real one; a refused command raises LedgerError with its output

    assert is_canonical_decision_id(plan.decision_id), plan.decision_id

    assert port.change_status(opened.change_id) == "implementing"
    assert port.decision_exists(plan.decision_id)
    assert port.work_state(plan.work_id) == "IN_PROGRESS"
    assert port.run_state(plan.run_id) == "RUNNING"
    run = ContinuityStore(deploy_scene.root).find_run(plan.run_id)
    assert run is not None and Path(run.worktree_path).resolve() == plan.station.resolve() != deploy_scene.root.resolve()
    code, output = _runner(deploy_scene.root)(["implementation-card", "precheck", "--card-file", str(plan.card_file)])
    assert code == 0, output  # the post-switch card precheck self-check runs exactly this against the same card

    closed = _close(deploy_scene, opened.change_id)

    assert port.checkpoint_exists(plan.checkpoint_id)
    assert port.run_state(plan.run_id) == "SUCCEEDED"
    assert port.work_state(plan.work_id) == "CLOSED"
    assert port.change_status(opened.change_id) == "completed"
    assert closed.steps[-1] == "change accepting -> completed"


def test_a_second_open_and_a_second_close_send_no_command(deploy_scene: SimpleNamespace) -> None:
    """Resumable against the real ledger too: whatever is already there is read, not written again."""

    sent: list[Sequence[str]] = []
    run = _runner(deploy_scene.root)

    def counting(args: Sequence[str]) -> tuple[int, str]:
        sent.append(args)
        return run(args)

    root = deploy_scene.root
    port = wiring.CockpitLedgerPort(root, run=counting, changes=ChangeService(str(root)), store=ContinuityStore(root))
    scene = SimpleNamespace(root=root, plan=deploy_scene.plan, port=port)
    opened = _open(scene)
    first = len(sent)
    assert first > 0 and _open(scene).steps == [] and len(sent) == first
    _close(scene, opened.change_id)
    closed = len(sent)
    assert _close(scene, opened.change_id).steps == [] and len(sent) == closed
    with pytest.raises(rl.LedgerError, match="已完成或已拒绝"):  # the finished order of this release is never walked again
        _open(scene)


def test_without_a_card_the_books_are_not_opened_and_nothing_is_written(deploy_scene: SimpleNamespace) -> None:
    plan = rl.DeployPlan(**{**deploy_scene.plan.__dict__, "card_file": None})
    with pytest.raises(rl.LedgerError, match="实施卡"):
        rl.open_books(plan, deploy_scene.port, background="b", necessity="n")
    assert deploy_scene.port.find_change(RELEASE) == ""
    assert not (deploy_scene.root / ".auto-pm" / "decisions").exists() or not any((deploy_scene.root / ".auto-pm" / "decisions").iterdir())
