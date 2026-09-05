"""ChangeBridge 单元测试（M3 新增）

约束（与 tests/qml/conftest.py 一致）：
- qapp fixture 引用 tests/conftest.py 的 session 级 QApplication
- 不重新定义 qapp
- 全部用 Mock Facade，无文件系统/DB 依赖
"""

from __future__ import annotations

from unittest.mock import MagicMock

from auto_pm.ui.contracts.commands.change_commands import (
    CreateChangeCommand,
    TransitionChangeCommand,
)
from auto_pm.ui.contracts.dto.change_dto import (
    ChangeRequestDTO,
    ChangeSummaryDTO,
    ChangeTimelineItemDTO,
    ChangeValidationSummaryDTO,
    LedgerReconcileResultDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult


def _make_summary_dto(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    return ChangeSummaryDTO(
        change_number=overrides.get("change_number", "CHG-2026-001"),
        project_id=overrides.get("project_id", "PRJ-001"),
        project_name=overrides.get("project_name", "Test Project"),
        domain=overrides.get("domain", "ELEC"),
        business_nature=overrides.get("business_nature", "DEF"),
        impact_scope=overrides.get("impact_scope", []),
        status=overrides.get("status", "draft"),
        applicant=overrides.get("applicant", "user"),
        apply_date=overrides.get("apply_date", "2026-07-07"),
        title=overrides.get("title", "Test Change"),
        urgency=overrides.get("urgency", "normal"),
    )


def _make_request_dto(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    return ChangeRequestDTO(
        change_number=overrides.get("change_number", "CHG-2026-001"),
        project_id=overrides.get("project_id", "PRJ-001"),
        project_name=overrides.get("project_name", "Test Project"),
        domain=overrides.get("domain", "ELEC"),
        business_nature=overrides.get("business_nature", "DEF"),
        impact_scope=overrides.get("impact_scope", []),
        status=overrides.get("status", "draft"),
        applicant=overrides.get("applicant", "user"),
        apply_date=overrides.get("apply_date", "2026-07-07"),
        planned_date=overrides.get("planned_date", "2026-07-10"),
        urgency=overrides.get("urgency", "normal"),
        background=overrides.get("background", "bg"),
        necessity=overrides.get("necessity", "nec"),
        references=overrides.get("references", ""),
        risk_level=overrides.get("risk_level", "low"),
        mitigation=overrides.get("mitigation", ""),
        propagation_chain=overrides.get("propagation_chain", ""),
        file_path=overrides.get("file_path", "/tmp/CHG-2026-001.md"),
        sections=overrides.get("sections", {}),
    )


def _make_timeline_dto(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    return ChangeTimelineItemDTO(
        from_status=overrides.get("from_status", "draft"),
        to_status=overrides.get("to_status", "submitted"),
        approver=overrides.get("approver", "user1"),
        comment=overrides.get("comment", "approve"),
        transition_date=overrides.get("transition_date", "2026-07-07T10:00:00"),
    )


def _make_validation_dto(**overrides) -> Any:  # type: ignore[name-defined, no-untyped-def]
    return ChangeValidationSummaryDTO(
        change_number=overrides.get("change_number", "CHG-2026-001"),
        current_status=overrides.get("current_status", "approved"),
        risk_level=overrides.get("risk_level", "high"),
        mitigation=overrides.get("mitigation", "plan B"),
        propagation_chain=overrides.get("propagation_chain", "A→B"),
        approval_count=overrides.get("approval_count", 2),
        last_approval_date=overrides.get("last_approval_date", "2026-07-08T11:00:00"),
        domain_impacts=overrides.get("domain_impacts", {"ELEC": {"impact": "high"}}),
        related_changes=overrides.get("related_changes", ["CHG-2026-000"]),
    )


def test_change_bridge_list_all_changes(qapp) -> None:  # type: ignore[no-untyped-def]
    """listAllChanges() 返回 list[dict]"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.list_change_requests.return_value = QueryResult(
        success=True, message="Success", payload=[_make_summary_dto()]
    )
    bridge = ChangeBridge(facade=mock_facade)
    result = bridge.listAllChanges()
    assert len(result) == 1
    assert result[0]["change_number"] == "CHG-2026-001"
    assert result[0]["domain"] == "ELEC"


def test_change_bridge_get_change_request(qapp) -> None:  # type: ignore[no-untyped-def]
    """getChangeRequest() 返回 dict（含详情字段）"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.get_change_detail.return_value = QueryResult(
        success=True, message="Success", payload=_make_request_dto(status="submitted")
    )
    bridge = ChangeBridge(facade=mock_facade)
    result = bridge.getChangeRequest("CHG-2026-001")
    assert result["change_number"] == "CHG-2026-001"
    assert result["status"] == "submitted"
    assert result["background"] == "bg"


def test_change_bridge_create_change(qapp) -> None:  # type: ignore[no-untyped-def]
    """createChange(dict) 委托 Facade 并返回 dict"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.create_change_request.return_value = CommandResult(
        success=True, message="Created", payload=_make_request_dto(status="draft")
    )
    bridge = ChangeBridge(facade=mock_facade)
    cmd_dict = {
        "project_id": "PRJ-001",
        "title": "Test Change",
        "domain": "ELEC",
        "nature": "DEF",
        "background": "bg",
        "necessity": "nec",
        "applicant": "user",
        "impact_scope": ["约束A"],
    }
    result = bridge.createChange(cmd_dict)
    assert result["change_number"] == "CHG-2026-001"
    # 验证 Facade 收到 CreateChangeCommand 且 impact_scope 透传
    mock_facade.create_change_request.assert_called_once()
    cmd_arg = mock_facade.create_change_request.call_args[0][0]
    assert isinstance(cmd_arg, CreateChangeCommand)
    assert cmd_arg.impact_scope == ["约束A"]


def test_change_bridge_transition_change(qapp) -> None:  # type: ignore[no-untyped-def]
    """transitionChange(dict) 委托 Facade 并返回 dict"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.transition_change.return_value = CommandResult(
        success=True, message="Transitioned", payload=_make_request_dto(status="approved")
    )
    bridge = ChangeBridge(facade=mock_facade)
    cmd_dict = {
        "change_id": "CHG-2026-001",
        "target_status": "approved",
        "operator": "user1",
        "note": "approved",
        "allow_partial_verification": False,
    }
    result = bridge.transitionChange(cmd_dict)
    assert result["status"] == "approved"
    mock_facade.transition_change.assert_called_once()
    cmd_arg = mock_facade.transition_change.call_args[0][0]
    assert isinstance(cmd_arg, TransitionChangeCommand)
    assert cmd_arg.target_status == "approved"


def test_change_bridge_get_timeline(qapp) -> None:  # type: ignore[no-untyped-def]
    """getChangeTimeline() 返回 list[dict]"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.get_change_timeline.return_value = QueryResult(
        success=True,
        message="Success",
        payload=[
            _make_timeline_dto(from_status="draft", to_status="submitted"),
            _make_timeline_dto(
                from_status="submitted", to_status="approved", transition_date="2026-07-08T11:00:00"
            ),
        ],
    )
    bridge = ChangeBridge(facade=mock_facade)
    result = bridge.getChangeTimeline("CHG-2026-001")
    assert len(result) == 2
    assert result[0]["from_status"] == "draft"
    assert result[1]["to_status"] == "approved"
    assert result[1]["transition_date"] == "2026-07-08T11:00:00"


def test_change_bridge_get_validation_summary(qapp) -> None:  # type: ignore[no-untyped-def]
    """getChangeValidationSummary() 返回 dict"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.get_change_validation_summary.return_value = QueryResult(
        success=True, message="Success", payload=_make_validation_dto()
    )
    bridge = ChangeBridge(facade=mock_facade)
    result = bridge.getChangeValidationSummary("CHG-2026-001")
    assert result["current_status"] == "approved"
    assert result["risk_level"] == "high"
    assert result["approval_count"] == 2
    assert result["last_approval_date"] == "2026-07-08T11:00:00"
    assert result["domain_impacts"] == {"ELEC": {"impact": "high"}}
    assert result["related_changes"] == ["CHG-2026-000"]


def test_change_bridge_no_facade(qapp) -> None:  # type: ignore[no-untyped-def]
    """facade=None 时所有 Slot 降级返回空值，不抛异常"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    bridge = ChangeBridge(facade=None)
    assert bridge.listAllChanges() == []
    assert bridge.listChanges("PRJ-001") == []
    assert bridge.getChangeRequest("CHG-001") == {}
    # M3 新增 Slot 的降级
    assert bridge.createChange({}) == {"success": False, "message": "未初始化"}
    assert bridge.transitionChange({}) == {"success": False, "message": "未初始化"}
    assert bridge.getChangeTimeline("CHG-001") == []
    assert bridge.getChangeValidationSummary("CHG-001") == {}
    # M5 CHG-118 新增 Slot 的降级
    assert bridge.reconcileLedger("SW-2026-008", False) == {"success": False, "message": "未初始化"}


def test_change_bridge_create_change_failure(qapp) -> None:  # type: ignore[no-untyped-def]
    """Facade 返回失败时，createChange 返回 {"success": False, "message": ...}"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.create_change_request.return_value = CommandResult(
        success=False, message="Validation failed", payload=None
    )
    bridge = ChangeBridge(facade=mock_facade)
    result = bridge.createChange({"project_id": "PRJ-001"})
    assert result == {"success": False, "message": "Validation failed"}


def test_change_bridge_reconcile_ledger(qapp) -> None:  # type: ignore[no-untyped-def]
    """reconcileLedger() 返回 dict（asdict 转换）+ project_id/autoFix 透传验证（M5 CHG-118）"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    dto = LedgerReconcileResultDTO(
        project_id="SW-2026-008",
        is_clean=False,
        missing_in_ledger=["CHG-SCPT-2026-001"],
        orphan_in_ledger=["CHG-SCPT-2026-099"],
        status_mismatches=[["CHG-SCPT-2026-002", "✅已关闭", "🔄待处理"]],
        summary="台账缺失: 1 条, 台账多余(孤儿): 1 条, 状态不一致: 1 条",
        auto_fixed=False,
    )
    mock_facade = MagicMock()
    mock_facade.reconcile_ledger.return_value = CommandResult(
        success=True, message="OK", payload=dto
    )
    bridge = ChangeBridge(facade=mock_facade)

    result = bridge.reconcileLedger("SW-2026-008", False)

    assert isinstance(result, dict)
    assert result["project_id"] == "SW-2026-008"
    assert result["is_clean"] is False
    assert result["missing_in_ledger"] == ["CHG-SCPT-2026-001"]
    assert result["orphan_in_ledger"] == ["CHG-SCPT-2026-099"]
    assert result["status_mismatches"] == [["CHG-SCPT-2026-002", "✅已关闭", "🔄待处理"]]
    assert "台账缺失" in result["summary"]
    assert result["auto_fixed"] is False
    # 透传验证
    mock_facade.reconcile_ledger.assert_called_once_with("SW-2026-008", False)


def test_change_bridge_reconcile_ledger_error(qapp) -> None:  # type: ignore[no-untyped-def]
    """reconcileLedger() service 返回失败时透传 success=False + message（M5 CHG-118）"""
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge

    mock_facade = MagicMock()
    mock_facade.reconcile_ledger.return_value = CommandResult(
        success=False, message="No project_service", payload=None
    )
    bridge = ChangeBridge(facade=mock_facade)

    result = bridge.reconcileLedger("SW-2026-008", True)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["message"] == "No project_service"
    mock_facade.reconcile_ledger.assert_called_once_with("SW-2026-008", True)
