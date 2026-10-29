"""B10 (user ruling): a change order that was never carried out can be abandoned.

``abandoned`` is a terminal state reachable only from the states before implementation, always with a reason. An
abandoned change order approves no Decision and lets no code be committed.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import get_args

import pytest

from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.constants import (
    ALL_STATUSES,
    LEDGER_STATUS_MAP,
    STATUS_FLOW,
    STATUS_LABELS,
    SpecViolationError,
    TransitionGuardError,
    validate_status_transition,
)
from auto_pm.domain.change.ledger_updater import INDEX_TABLE_SECTION
from auto_pm.domain.models.enums import ChangeStatus
from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg
from tests.infrastructure.test_git_hook_enforcer import _make_dual_root_fixture

from .test_archive_flow import _build_completed_chg

CHG = "CHG-DOCU-2026-001"
BEFORE_IMPLEMENTATION = ("draft", "submitted", "under_review", "approved", "conditionally_approved", "rejected")
STARTED_OR_DONE = ("implementing", "pending_acceptance", "accepting", "completed", "closed", "archived")


def _workspace(tmp_path: Path, status: str) -> str:
    project = tmp_path / "TEST-2026-001"
    project.mkdir(parents=True, exist_ok=True)
    (project / "PM_SESSION_TEST-2026-001.md").write_text("# PM_SESSION\n", encoding="utf-8")
    chg_dir = project / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU"
    chg_dir.mkdir(parents=True, exist_ok=True)
    (chg_dir / f"{CHG}.md").write_text(
        _build_completed_chg().replace("| 变更状态 | completed |", f"| 变更状态 | {status} |"), encoding="utf-8"
    )
    ledger = project / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger.mkdir(parents=True, exist_ok=True)
    (ledger / "01_版本变更台账.md").write_text(INDEX_TABLE_SECTION, encoding="utf-8")
    return str(tmp_path)


def _file(workspace: str) -> Path:
    return next(Path(workspace).rglob(f"{CHG}.md"))


# ── the state machine ───────────────────────────────────────


@pytest.mark.parametrize("source", BEFORE_IMPLEMENTATION)
def test_a_change_order_not_yet_implemented_can_be_abandoned(source: str) -> None:
    validate_status_transition(source, "abandoned")


@pytest.mark.parametrize("source", STARTED_OR_DONE)
def test_a_change_order_already_implemented_or_finished_cannot_be_abandoned(source: str) -> None:
    with pytest.raises(SpecViolationError, match="状态流转"):
        validate_status_transition(source, "abandoned")


def test_abandoned_is_terminal() -> None:
    assert STATUS_FLOW["abandoned"] == set()
    for target in ALL_STATUSES:
        with pytest.raises(SpecViolationError, match="状态流转"):
            validate_status_transition("abandoned", target)


def test_every_table_that_lists_the_states_knows_abandoned() -> None:
    assert "abandoned" in ALL_STATUSES
    assert STATUS_LABELS["abandoned"] == "已废弃"
    assert LEDGER_STATUS_MAP["abandoned"] == "🚫已废弃"
    # The typed list of states and the state machine must never drift apart.
    assert set(get_args(ChangeStatus)) == ALL_STATUSES


# ── the transition on a real change order ───────────────────


def test_abandoning_records_the_reason_and_the_ledger_line(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "draft")
    service = ChangeService(workspace)

    result = service.transition_status(CHG, "abandoned", approver="管理员", comment="需求取消，不再做")

    assert result is not None and result.status == "abandoned"
    text = _file(workspace).read_text(encoding="utf-8")
    assert "已废弃" in text and "需求取消，不再做" in text
    ledger = next(Path(workspace).rglob("01_版本变更台账.md")).read_text(encoding="utf-8")
    assert "🚫已废弃" in ledger and datetime.date.today().isoformat() in ledger


@pytest.mark.parametrize(("approver", "comment"), [("管理员", ""), ("", "需求取消"), ("", "")])
def test_abandoning_without_an_approver_and_a_reason_is_refused_and_changes_nothing(
    tmp_path: Path, approver: str, comment: str
) -> None:
    workspace = _workspace(tmp_path, "draft")
    before = _file(workspace).read_bytes()

    with pytest.raises(TransitionGuardError):
        ChangeService(workspace).transition_status(CHG, "abandoned", approver=approver, comment=comment)

    assert _file(workspace).read_bytes() == before


def test_a_change_order_in_implementation_stays_as_it_is(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "implementing")
    before = _file(workspace).read_bytes()

    with pytest.raises(SpecViolationError, match="状态流转"):
        ChangeService(workspace).transition_status(CHG, "abandoned", approver="管理员", comment="想放弃")

    assert _file(workspace).read_bytes() == before


def test_an_abandoned_change_order_cannot_be_moved_again(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "approved")
    service = ChangeService(workspace)
    service.transition_status(CHG, "abandoned", approver="管理员", comment="不做了")

    for target in ("draft", "submitted", "approved", "implementing"):
        with pytest.raises(SpecViolationError, match="状态流转"):
            service.transition_status(CHG, target, approver="管理员", comment="反悔")


# ── an abandoned change order authorizes nothing ────────────


def test_code_cannot_be_committed_against_an_abandoned_change_order(tmp_path: Path) -> None:
    approved, ctrl_ok, msg_ok = _make_dual_root_fixture(tmp_path / "ok", chg_status="approved")
    assert enforce_commit_msg(approved, msg_ok, control_root=ctrl_ok) == 0

    cand, ctrl, msg = _make_dual_root_fixture(tmp_path / "abandoned", chg_status="abandoned")

    assert enforce_commit_msg(cand, msg, control_root=ctrl) == 1


# ── the other readers of a change order's status treat it as finished ──


def test_an_abandoned_change_order_is_not_an_open_change_of_the_project(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from auto_pm.application.core.dashboard_service import DashboardService
    from auto_pm.application.core.project_fact_service import ProjectFactService

    workspace = _workspace(tmp_path, "abandoned")
    open_changes = ProjectFactService(workspace)._collect_open_changes(Path(workspace) / "TEST-2026-001")
    assert [item.change_number for item in open_changes] == []

    # 废弃的这条日期最晚：若仪表盘不排除，就会被选成“最近活跃变更”
    abandoned = SimpleNamespace(status="abandoned", apply_date="2026-01-03")
    approved = SimpleNamespace(status="approved", apply_date="2026-01-02")
    changes = SimpleNamespace(list_all_changes=lambda project_id=None: [abandoned, approved])
    service = DashboardService(SimpleNamespace(), changes)
    assert service.get_active_change_for_project("TEST-2026-001") is approved



# ── 审计 227 补的缺口 ───────────────────────────────────────


def _ledger_text(workspace: str) -> str:
    return next(Path(workspace).rglob("01_版本变更台账.md")).read_text(encoding="utf-8")


def _ledger_row(workspace: str) -> str:
    return next(line for line in _ledger_text(workspace).splitlines() if CHG in line)


def test_create_refuses_to_overwrite_an_abandoned_change_order_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """编号生成器回退到已用编号时，已废弃的变更单文件和 closed/archived 一样不能被覆盖。"""
    workspace = _workspace(tmp_path, "abandoned")
    service = ChangeService(workspace)
    before = _file(workspace).read_text(encoding="utf-8")
    monkeypatch.setattr(service._locator, "generate_change_number", lambda *args: CHG)

    with pytest.raises(ValueError, match="终态"):
        service.create_change_request(
            project_id="TEST-2026-001",
            domain="DOCU",
            business_nature="DEF",
            impact_scope=["LOCAL"],
            applicant="测试",
            background="背景",
            necessity="必要性",
        )
    assert _file(workspace).read_text(encoding="utf-8") == before


def test_abandoning_writes_the_date_when_the_ledger_already_has_the_row(tmp_path: Path) -> None:
    """台账里已经有这条的行（现有测试只走“新建行”那条路）：改状态时也要回写完成日期。"""
    from auto_pm.domain.change.ledger_updater import LedgerUpdater

    workspace = _workspace(tmp_path, "draft")
    ledger = str(next(Path(workspace).rglob("01_版本变更台账.md")))
    LedgerUpdater().update(ledger, CHG, "已有行", applicant="管理员", apply_date="2026-01-01")
    assert "已废弃" not in _ledger_row(workspace)

    ChangeService(workspace).transition_status(CHG, "abandoned", approver="管理员", comment="需求取消")

    row = _ledger_row(workspace)
    assert "🚫已废弃" in row and datetime.date.today().isoformat() in row


def test_reconcile_backfills_the_date_for_an_abandoned_change_order(tmp_path: Path) -> None:
    """对账补建台账缺失行，和修正状态不一致两条路径，都要给已废弃的写完成日期。"""
    from auto_pm.domain.change.ledger_reconciler import LedgerReconciler
    from auto_pm.domain.change.ledger_updater import LedgerUpdater

    today = datetime.date.today().isoformat()
    project = "TEST-2026-001"

    # 路径一：台账里没有这条 → 补建
    workspace = _workspace(tmp_path / "missing", "abandoned")
    project_path = str(Path(workspace) / project)
    reconciler = LedgerReconciler()
    diff = reconciler.reconcile(project_path)
    assert diff.missing_in_ledger == [CHG]
    reconciler.auto_fix(project_path, diff)
    row = _ledger_row(workspace)
    assert "🚫已废弃" in row and today in row

    # 路径二：台账里是“待处理”→ 状态不一致 → 修正
    workspace = _workspace(tmp_path / "mismatch", "abandoned")
    project_path = str(Path(workspace) / project)
    ledger = str(next(Path(workspace).rglob("01_版本变更台账.md")))
    LedgerUpdater().update(ledger, CHG, "已有行", applicant="管理员", apply_date="2026-01-01")
    diff = reconciler.reconcile(project_path)
    assert [item[0] for item in diff.status_mismatches] == [CHG]
    reconciler.auto_fix(project_path, diff)
    row = _ledger_row(workspace)
    assert "🚫已废弃" in row and today in row
