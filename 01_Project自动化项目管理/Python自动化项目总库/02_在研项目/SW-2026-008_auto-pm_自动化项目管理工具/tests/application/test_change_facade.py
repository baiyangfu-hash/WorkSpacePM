from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.change.ledger_reconciler import ReconcileDiff

from auto_pm.application.change_facade import ChangeFacade
from auto_pm.ui.contracts.commands.change_commands import (
    CreateChangeCommand,
    TransitionChangeCommand,
)
from auto_pm.ui.contracts.dto.change_dto import LedgerReconcileResultDTO


@pytest.fixture
def mock_change_service() -> None:
    return MagicMock(spec=ChangeService)  # type: ignore[return-value]

@pytest.fixture
def change_facade(mock_change_service) -> None:  # type: ignore[no-untyped-def]
    return ChangeFacade(mock_change_service)  # type: ignore[return-value]

def _make_summary(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    """构造 ChangeSummary mock"""
    mock = MagicMock()
    mock.change_number = overrides.get("change_number", "CHG-123")
    mock.project_id = overrides.get("project_id", "PRJ-123")
    mock.project_name = overrides.get("project_name", "Project 123")
    mock.domain = overrides.get("domain", "ELEC")
    mock.business_nature = overrides.get("business_nature", "DEF")
    mock.impact_scope = overrides.get("impact_scope", [])
    mock.status = overrides.get("status", "draft")
    mock.applicant = overrides.get("applicant", "user")
    mock.apply_date = overrides.get("apply_date", "2026-07-06")
    mock.title = overrides.get("title", "Title")
    mock.urgency = overrides.get("urgency", "normal")
    return mock

def _make_request(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    """构造 ChangeRequest mock（含详情字段）"""
    mock = MagicMock()
    mock.change_number = overrides.get("change_number", "CHG-123")
    mock.project_id = overrides.get("project_id", "PRJ-123")
    mock.project_name = overrides.get("project_name", "Project 123")
    mock.domain = overrides.get("domain", "ELEC")
    mock.business_nature = overrides.get("business_nature", "DEF")
    mock.impact_scope = overrides.get("impact_scope", [])
    mock.status = overrides.get("status", "draft")
    mock.applicant = overrides.get("applicant", "user")
    mock.apply_date = overrides.get("apply_date", "2026-07-06")
    mock.planned_date = overrides.get("planned_date", "2026-07-07")
    mock.urgency = overrides.get("urgency", "normal")
    mock.background = overrides.get("background", "")
    mock.necessity = overrides.get("necessity", "")
    mock.references = overrides.get("references", "")
    mock.risk_level = overrides.get("risk_level", "")
    mock.mitigation = overrides.get("mitigation", "")
    mock.propagation_chain = overrides.get("propagation_chain", "")
    mock.file_path = overrides.get("file_path", "")
    mock.sections = overrides.get("sections", {})
    return mock

def _make_approval(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    """构造 ApprovalRecord mock"""
    mock = MagicMock()
    mock.from_status = overrides.get("from_status", "draft")
    mock.to_status = overrides.get("to_status", "submitted")
    mock.approver = overrides.get("approver", "user1")
    mock.comment = overrides.get("comment", "approve")
    mock.transition_date = overrides.get("transition_date", "2026-07-07T10:00:00")
    return mock

def _make_impact(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    """构造 ImpactAnalysis mock"""
    mock = MagicMock()
    mock.change_number = overrides.get("change_number", "CHG-123")
    mock.risk_level = overrides.get("risk_level", "medium")
    mock.mitigation = overrides.get("mitigation", "mitigation plan")
    mock.propagation_chain = overrides.get("propagation_chain", "chain")
    mock.domain_impacts = overrides.get("domain_impacts", {"ELEC": {"impact": "low"}})
    mock.related_changes = overrides.get("related_changes", ["CHG-122"])
    mock.updated_at = overrides.get("updated_at", "2026-07-07")
    return mock


# ── 已有 3 个测试（保留并补充 impact_scope 断言） ────────────────

def test_list_change_requests(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    mock_change_service.list_all_changes.return_value = [_make_summary()]
    result = change_facade.list_change_requests()
    assert result.success is True
    assert len(result.payload) == 1
    assert result.payload[0].change_number == "CHG-123"

def test_get_change_detail(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    mock_change_service.get_change_request.return_value = _make_request()
    result = change_facade.get_change_detail("CHG-123")
    assert result.success is True
    assert result.payload.change_number == "CHG-123"

def test_create_change_request(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    cmd = CreateChangeCommand(
        project_id="PRJ-123",
        title="Test Title",
        domain="ELEC",
        nature="DEF",
        background="bg",
        necessity="nec",
        applicant="user",
    )
    mock_change_service.create_change_request.return_value = _make_request()
    result = change_facade.create_change_request(cmd)
    assert result.success is True
    assert result.payload.change_number == "CHG-123"
    mock_change_service.create_change_request.assert_called_once()
    # 验证 impact_scope 透传（M3 新增）
    _, kwargs = mock_change_service.create_change_request.call_args
    assert kwargs["impact_scope"] == []


# ── M3 新增测试 ──────────────────────────────────────────

def test_create_change_request_with_impact_scope(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """M3: impact_scope 从 command 透传到 Service"""
    cmd = CreateChangeCommand(
        project_id="PRJ-123",
        title="Test",
        domain="ELEC",
        nature="DEF",
        background="bg",
        necessity="nec",
        applicant="user",
        impact_scope=["约束A", "约束B"],
    )
    mock_change_service.create_change_request.return_value = _make_request(impact_scope=["约束A", "约束B"])
    result = change_facade.create_change_request(cmd)
    assert result.success is True
    _, kwargs = mock_change_service.create_change_request.call_args
    assert kwargs["impact_scope"] == ["约束A", "约束B"]


def test_transition_change(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """transition_change 正常流转"""
    cmd = TransitionChangeCommand(
        change_id="CHG-123",
        target_status="submitted",
        operator="user1",
        note="approved",
        allow_partial_verification=False,
    )
    mock_change_service.get_change_request.return_value = _make_request(status="submitted")
    result = change_facade.transition_change(cmd)
    assert result.success is True
    assert result.payload.status == "submitted"
    mock_change_service.transition_status.assert_called_once()
    _, kwargs = mock_change_service.transition_status.call_args
    assert kwargs["new_status"] == "submitted"
    assert kwargs["approver"] == "user1"


def test_transition_change_service_exception(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """Service 抛异常时返回 success=False"""
    cmd = TransitionChangeCommand(
        change_id="CHG-123",
        target_status="approved",
        operator="user1",
        note=None,
        allow_partial_verification=True,
    )
    mock_change_service.transition_status.side_effect = Exception("Status transition not allowed")
    result = change_facade.transition_change(cmd)
    assert result.success is False
    assert "Status transition not allowed" in result.message


def test_get_change_timeline_empty(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """无审批历史时返回空列表"""
    mock_change_service.list_approval_history.return_value = []
    result = change_facade.get_change_timeline("CHG-123")
    assert result.success is True
    assert result.payload == []


def test_get_change_timeline_normal(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """多条审批记录按时间顺序返回"""
    mock_change_service.list_approval_history.return_value = [
        _make_approval(from_status="draft", to_status="submitted", transition_date="2026-07-07T10:00:00"),
        _make_approval(from_status="submitted", to_status="approved", transition_date="2026-07-08T11:00:00"),
    ]
    result = change_facade.get_change_timeline("CHG-123")
    assert result.success is True
    assert len(result.payload) == 2
    assert result.payload[0].from_status == "draft"
    assert result.payload[1].to_status == "approved"
    assert result.payload[1].transition_date == "2026-07-08T11:00:00"


def test_get_change_timeline_service_exception(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """Service 抛异常时返回 success=False"""
    mock_change_service.list_approval_history.side_effect = Exception("DB Error")
    result = change_facade.get_change_timeline("CHG-123")
    assert result.success is False
    assert result.payload == []


def test_get_change_validation_summary_no_impact(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """无影响分析时，risk_level/mitigation 等字段为空"""
    mock_change_service.get_change_request.return_value = _make_request(status="draft")
    mock_change_service.get_impact_analysis.return_value = None
    mock_change_service.list_approval_history.return_value = []
    result = change_facade.get_change_validation_summary("CHG-123")
    assert result.success is True
    assert result.payload.current_status == "draft"
    assert result.payload.risk_level == ""
    assert result.payload.approval_count == 0
    assert result.payload.last_approval_date is None
    assert result.payload.domain_impacts == {}
    assert result.payload.related_changes == []


def test_get_change_validation_summary_normal(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """含影响分析 + 审批历史时，聚合字段正确"""
    mock_change_service.get_change_request.return_value = _make_request(status="approved")
    mock_change_service.get_impact_analysis.return_value = _make_impact(
        risk_level="high",
        mitigation="plan B",
        propagation_chain="A→B→C",
        domain_impacts={"ELEC": {"impact": "high"}},
        related_changes=["CHG-122", "CHG-121"],
    )
    mock_change_service.list_approval_history.return_value = [
        _make_approval(transition_date="2026-07-07T10:00:00"),
        _make_approval(transition_date="2026-07-08T11:00:00"),
    ]
    result = change_facade.get_change_validation_summary("CHG-123")
    assert result.success is True
    assert result.payload.current_status == "approved"
    assert result.payload.risk_level == "high"
    assert result.payload.mitigation == "plan B"
    assert result.payload.propagation_chain == "A→B→C"
    assert result.payload.approval_count == 2
    assert result.payload.last_approval_date == "2026-07-08T11:00:00"
    assert result.payload.domain_impacts == {"ELEC": {"impact": "high"}}
    assert result.payload.related_changes == ["CHG-122", "CHG-121"]


def test_get_change_validation_summary_not_found(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """change_id 不存在时返回 success=False"""
    mock_change_service.get_change_request.return_value = None
    result = change_facade.get_change_validation_summary("NOT-EXIST")
    assert result.success is False
    assert "not found" in result.message


def test_get_change_validation_summary_service_exception(change_facade, mock_change_service) -> None:  # type: ignore[no-untyped-def]
    """Service 抛异常时返回 success=False"""
    mock_change_service.get_change_request.side_effect = Exception("DB Error")
    result = change_facade.get_change_validation_summary("CHG-123")
    assert result.success is False
    assert "DB Error" in result.message


# ── service=None 降级测试 ──────────────────────────────

def test_list_change_requests_no_service() -> None:
    """facade=None 时 list 返回 success=False + 空列表"""
    facade = ChangeFacade(change_service=None)
    result = facade.list_change_requests()
    assert result.success is False
    assert result.payload == []


def test_create_change_request_no_service() -> None:
    """facade=None 时 create 返回 success=False + None"""
    facade = ChangeFacade(change_service=None)
    cmd = CreateChangeCommand(
        project_id="PRJ-123",
        title="Test",
        domain="ELEC",
        nature="DEF",
        background="bg",
        necessity="nec",
        applicant="user",
    )
    result = facade.create_change_request(cmd)
    assert result.success is False
    assert result.payload is None


def test_get_change_timeline_no_service() -> None:
    """facade=None 时 timeline 返回 success=False + 空列表"""
    facade = ChangeFacade(change_service=None)
    result = facade.get_change_timeline("CHG-123")
    assert result.success is False
    assert result.payload == []


def test_get_change_validation_summary_no_service() -> None:
    """facade=None 时 validation_summary 返回 success=False + None"""
    facade = ChangeFacade(change_service=None)
    result = facade.get_change_validation_summary("CHG-123")
    assert result.success is False
    assert result.payload is None


# ── reconcile_ledger 测试（M5 CHG-118 新增）──────────────


def _make_diff(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    """构造 ReconcileDiff mock"""
    return ReconcileDiff(
        missing_in_ledger=overrides.get("missing_in_ledger", []),
        orphan_in_ledger=overrides.get("orphan_in_ledger", []),
        status_mismatches=overrides.get("status_mismatches", []),
    )


def test_reconcile_ledger_success() -> None:
    """正常调用返回 LedgerReconcileResultDTO 且字段正确（auto_fix=False）"""
    diff = _make_diff(
        missing_in_ledger=["CHG-SCPT-2026-001"],
        orphan_in_ledger=["CHG-SCPT-2026-099"],
        status_mismatches=[("CHG-SCPT-2026-002", "✅已关闭", "🔄待处理")],
    )
    mock_project_svc = MagicMock()
    mock_project_svc.find_project_path.return_value = "/tmp/project"
    mock_reconciler = MagicMock()
    mock_reconciler.reconcile.return_value = diff

    facade = ChangeFacade(
        change_service=None,
        project_service=mock_project_svc,
        ledger_reconciler=mock_reconciler,
    )

    result = facade.reconcile_ledger("SW-2026-008", auto_fix=False)

    assert result.success is True
    assert isinstance(result.payload, LedgerReconcileResultDTO)
    assert result.payload.project_id == "SW-2026-008"
    assert result.payload.is_clean is False
    assert result.payload.missing_in_ledger == ["CHG-SCPT-2026-001"]
    assert result.payload.orphan_in_ledger == ["CHG-SCPT-2026-099"]
    assert result.payload.status_mismatches == [["CHG-SCPT-2026-002", "✅已关闭", "🔄待处理"]]
    assert "台账缺失" in result.payload.summary
    assert result.payload.auto_fixed is False
    # 验证调用的是 reconcile（不是 auto_fix）
    mock_reconciler.reconcile.assert_called_once_with("/tmp/project")
    mock_reconciler.auto_fix.assert_not_called()


def test_reconcile_ledger_auto_fix() -> None:
    """auto_fix=True 时调用 auto_fix 且 auto_fixed=True"""
    diff = _make_diff()  # clean diff
    mock_project_svc = MagicMock()
    mock_project_svc.find_project_path.return_value = "/tmp/project"
    mock_reconciler = MagicMock()
    mock_reconciler.auto_fix.return_value = diff

    facade = ChangeFacade(
        change_service=None,
        project_service=mock_project_svc,
        ledger_reconciler=mock_reconciler,
    )

    result = facade.reconcile_ledger("SW-2026-008", auto_fix=True)

    assert result.success is True
    assert result.payload.is_clean is True  # type: ignore[union-attr]
    assert result.payload.auto_fixed is True  # type: ignore[union-attr]
    mock_reconciler.auto_fix.assert_called_once_with("/tmp/project")
    mock_reconciler.reconcile.assert_not_called()


def test_reconcile_ledger_no_project_service() -> None:
    """project_service=None 时返回 success=False"""
    facade = ChangeFacade(change_service=None, project_service=None, ledger_reconciler=MagicMock())
    result = facade.reconcile_ledger("SW-2026-008")
    assert result.success is False
    assert "No project_service" in result.message
    assert result.payload is None


def test_reconcile_ledger_no_reconciler() -> None:
    """ledger_reconciler=None 时返回 success=False"""
    facade = ChangeFacade(change_service=None, project_service=MagicMock(), ledger_reconciler=None)
    result = facade.reconcile_ledger("SW-2026-008")
    assert result.success is False
    assert "No ledger_reconciler" in result.message
    assert result.payload is None


def test_reconcile_ledger_project_not_found() -> None:
    """project_service.find_project_path 返回 None 时返回 success=False"""
    mock_project_svc = MagicMock()
    mock_project_svc.find_project_path.return_value = None
    facade = ChangeFacade(
        change_service=None,
        project_service=mock_project_svc,
        ledger_reconciler=MagicMock(),
    )
    result = facade.reconcile_ledger("NOT-EXIST")
    assert result.success is False
    assert "项目不存在" in result.message
    assert result.payload is None


def test_reconcile_ledger_exception() -> None:
    """reconciler.reconcile() 抛异常时返回 success=False"""
    mock_project_svc = MagicMock()
    mock_project_svc.find_project_path.return_value = "/tmp/project"
    mock_reconciler = MagicMock()
    mock_reconciler.reconcile.side_effect = Exception("reconcile boom")

    facade = ChangeFacade(
        change_service=None,
        project_service=mock_project_svc,
        ledger_reconciler=mock_reconciler,
    )

    result = facade.reconcile_ledger("SW-2026-008")

    assert result.success is False
    assert "reconcile boom" in result.message
    assert result.payload is None
