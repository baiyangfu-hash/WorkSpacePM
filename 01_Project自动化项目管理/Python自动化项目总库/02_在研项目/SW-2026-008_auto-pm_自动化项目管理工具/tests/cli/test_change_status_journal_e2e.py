"""TD (audit 524, point 3; pre-audit 527): the commit hook trusts the transition journal, so every real way of moving a change
order must write it -- and the real hook must accept exactly those moves.

No hand-inserted rows here: the rows come from the real ``change transition`` command, from the three ``pm approve`` entry
points (command, facade, SDK) and from the pm saga; the verdict comes from the real ``enforce_commit_msg`` on the two-root
fixture.  The contrast case writes the same status into the file by hand and is refused.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm import api as cockpit_api
from auto_pm.application.core import pm_facade_service as facade_module
from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.status_journal import journal_path, last_recorded_status
from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg
from auto_pm.ui.cli import pm as pm_cli
from auto_pm.ui.cli.change import change_group
from tests.cli.test_agent_cannot_approve import GOOD_EVIDENCE, _obj
from tests.infrastructure.test_git_hook_enforcer import _make_dual_root_fixture

pytestmark = pytest.mark.usefixtures("identity_guard_off")

PID = "SW-2026-008"
PACKAGE = Path(__file__).resolve().parents[2] / "auto_pm"


def _order(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """The two-root fixture plus a real draft change order made by the service (all sections filled), bound by the commit message."""

    cand, ctrl, msg = _make_dual_root_fixture(tmp_path, chg_in_control=False)
    created = ChangeService(str(ctrl)).create_change_request(
        project_id=PID, domain="SCPT", business_nature="DEF", impact_scope=["LOCAL"], applicant="user",
        background="e2e background", necessity="e2e necessity",
    )
    number = created.change_number
    # The fixture's ledger is a two-column stub the service cannot index into; the hook only needs the number to be listed.
    ledger = next(ctrl.rglob("01_版本变更台账.md"))
    ledger.write_text(f"# 版本变更台账\n\n| 变更编号 | 状态 |\n| --- | --- |\n| {number} | draft |\n", encoding="utf-8")
    msg.write_text(f"feat: [{number}] e2e\n", encoding="utf-8")
    return cand, ctrl, msg, number


def _change_file(control_root: Path, number: str) -> Path:
    return next(control_root.rglob(f"{number}.md"))


def _status_in(path: Path) -> str:
    match = re.search(r"\|\s*变更状态\s*\|\s*(\S+)\s*\|", path.read_text(encoding="utf-8"))
    assert match, path
    return match.group(1)


def _transition(control_root: Path, number: str, status: str) -> None:
    extra = ["--approval-evidence-ref", GOOD_EVIDENCE] if status == "approved" else []
    result = CliRunner().invoke(
        change_group,
        ["transition", number, "--to", status, "--approver", "user", "--comment", "e2e", *extra],
        obj=_obj(control_root),
    )
    assert result.exit_code == 0, result.output


@pytest.fixture
def agent_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real situation: an agent session, so the approval needs the user's evidence reference (given)."""

    monkeypatch.setenv("CLAUDECODE", "1")


# --- the command line ------------------------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("agent_session")
def test_real_cli_transitions_to_approved_then_the_real_hook_accepts_the_commit(tmp_path: Path) -> None:
    cand, ctrl, msg, number = _order(tmp_path)
    assert not journal_path(ctrl).exists()
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1  # draft: not approved yet

    for status in ("submitted", "under_review", "approved"):
        _transition(ctrl, number, status)

    assert _status_in(_change_file(ctrl, number)) == "approved"
    assert last_recorded_status(ctrl, number, PID) == "approved"
    assert not (ctrl / ".auto-pm" / "index.db").exists()  # the command line never had the database cache
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


def test_the_same_status_written_by_hand_is_refused(tmp_path: Path) -> None:
    cand, ctrl, msg, number = _order(tmp_path)
    chg = _change_file(ctrl, number)
    chg.write_text(chg.read_text(encoding="utf-8").replace("| 变更状态 | draft |", "| 变更状态 | approved |"), encoding="utf-8")
    assert _status_in(chg) == "approved"
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


# --- pm approve: the command, the facade and the SDK all build their own ChangeService -----------------------------------------------


def _approve_with_command(ctrl: Path, number: str) -> None:
    root: Any = SimpleNamespace(obj=SimpleNamespace(control_root=ctrl, workspace_root=str(ctrl)))
    ctx: Any = SimpleNamespace(find_root=lambda: root)
    pm_cli._approve_planning_change(ctx, _card(number), "user")


def _approve_with_facade(ctrl: Path, number: str) -> None:
    service = object.__new__(facade_module.PmFacadeService)
    service._changes = ChangeService(str(ctrl))
    service._approve_planning_change(_card(number), "user")


def _approve_with_sdk(ctrl: Path, number: str) -> None:
    client = object.__new__(cockpit_api.CockpitClient)
    client._root = ctrl
    client._approve_change(_card(number), "user")


def _card(number: str) -> Any:
    return SimpleNamespace(change_id=number, subject_project_id=PID, plan_hash="H")


@pytest.mark.parametrize("approve", [_approve_with_command, _approve_with_facade, _approve_with_sdk], ids=["command", "facade", "sdk"])
def test_pm_approve_writes_the_journal_and_the_real_hook_accepts(approve: Any, tmp_path: Path) -> None:
    cand, ctrl, msg, number = _order(tmp_path)
    approve(ctrl, number)
    assert _status_in(_change_file(ctrl, number)) == "approved"
    assert last_recorded_status(ctrl, number, PID) == "approved"
    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 0


# --- the journal is written first, and a failure stops the operation ------------------------------------------------------------------


def test_a_journal_that_cannot_be_written_stops_the_transition_and_leaves_the_file_alone(tmp_path: Path) -> None:
    _cand, ctrl, _msg, number = _order(tmp_path)
    (ctrl / ".auto-pm").write_text("a file where the folder should be", encoding="utf-8")
    chg = _change_file(ctrl, number)
    before = chg.read_bytes()
    result = CliRunner().invoke(
        change_group, ["transition", number, "--to", "submitted", "--approver", "user", "--comment", "e2e"], obj=_obj(ctrl)
    )
    assert result.exit_code != 0
    assert "流转记录写不进" in result.output
    assert chg.read_bytes() == before


def test_a_file_write_that_loses_a_race_puts_the_old_status_back_into_the_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.infrastructure.utils.file_utils import StaleFileError

    _cand, ctrl, _msg, number = _order(tmp_path)
    from auto_pm.infrastructure.utils.file_utils import write_file as real_write

    def _stale(path: str, content: str, expected_mtime: float | None = None) -> None:
        if expected_mtime is None:
            real_write(path, content)
            return
        raise StaleFileError("changed by someone else")

    monkeypatch.setattr("auto_pm.domain.change.change_service.write_file", _stale)
    assert ChangeService(str(ctrl)).transition_status(number, "submitted", approver="user", project_id=PID) is None
    assert last_recorded_status(ctrl, number, PID) == "draft"  # the journal ends where the file still is


def test_a_retrofit_order_is_recorded_as_closed(tmp_path: Path) -> None:
    _cand, ctrl, _msg = _make_dual_root_fixture(tmp_path, chg_in_control=False)
    created = ChangeService(str(ctrl)).create_change_request(
        project_id=PID, domain="SCPT", business_nature="DEF", impact_scope=["LOCAL"], applicant="user",
        background="b", necessity="n", retrofit=True,
    )
    assert last_recorded_status(ctrl, created.change_number, PID) == "closed"


def test_the_pm_saga_writes_the_journal_before_it_changes_the_status_line(tmp_path: Path) -> None:
    """The saga edits §3.4 itself (completed / closed), not through ``transition_status``: it must journal that too."""

    from auto_pm.application.core.pm_saga_service import PmClosureSagaCoordinator

    _cand, ctrl, _msg, number = _order(tmp_path)
    saga = PmClosureSagaCoordinator(ctrl)
    saga._step_chg_transitioned({"request_id": "e2e"}, {"project_id": PID, "chg_updates": [number]})
    assert _status_in(_change_file(ctrl, number)) == "completed"
    assert last_recorded_status(ctrl, number, PID) == "completed"


# --- structure: nobody may write the §3.4 status except through the journalled doors --------------------------------------------------


def _calls(attribute: str) -> set[str]:
    found: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attribute:
                found.add(path.relative_to(PACKAGE).as_posix())
    return found


def test_only_the_known_modules_write_the_status_line() -> None:
    """A new module that edits §3.4 (``update_status_field``) must go through ``ChangeService.transition_status`` or journal the
    change itself -- this list is the review point.  Both entries below do."""

    assert _calls("update_status_field") == {
        "application/core/pm_saga_service.py",  # journals the transition itself, before the write
        "domain/change/change_service.py",  # transition_status: journal first, then the file
    }


def test_every_transition_status_caller_builds_its_service_on_a_root_the_hook_reads() -> None:
    """The journal goes to ``ChangeService(workspace_root)``; each caller below constructs it on the control root (the
    cockpit commands only run there).  A new caller shows up here and must be looked at."""

    assert _calls("transition_status") == {
        "api.py",  # SDK: ChangeService(str(self._root)), the control root
        "application/change_facade.py",  # GUI: the service built by the main window on the opened workspace
        "application/core/pm_facade_service.py",  # facade: the workspace root of the PM facade
        "ui/cli/change.py",  # change transition
        "ui/cli/pm.py",  # pm approve: ChangeService(control_root)
    }
