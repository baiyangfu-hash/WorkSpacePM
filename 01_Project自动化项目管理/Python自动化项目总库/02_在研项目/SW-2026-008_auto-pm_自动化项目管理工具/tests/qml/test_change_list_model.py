"""ChangeListModel 单元测试（V0.6.0 W2-S5）

覆盖 QAbstractListModel 核心方法：
- rowCount / data / roleNames（必须实现）
- setChanges / clear / getChangeAt / changeCount（数据更新接口）

测试策略：
- 内存构造 ChangeSummary dict 列表（QML 端通过 bridge.listAllChanges() 拿到）
- 用 qapp fixture 确保 Qt 事件循环可用
- 直接断言方法返回值，不走 QML 渲染
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from PySide6.QtCore import QModelIndex

from auto_pm.ui.qml.models.change_list_model import ChangeListModel

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


# ── 测试 fixture ─────────────────────────────────────────


def _make_change(
    change_number: str = "CHG-SCPT-2026-086",
    project_id: str = "SW-2026-008",
    project_name: str = "auto-pm",
    domain: str = "SCPT",
    business_nature: str = "OPT",
    status: str = "draft",
    applicant: str = "glm",
    apply_date: str = "2026-07-04",
    title: str = "QML 重构",
    urgency: str = "normal",
) -> dict[str, Any]:
    """构造 ChangeSummary dict（模拟 QmlBridge._summary_to_dict 输出）"""
    return {
        "change_number": change_number,
        "project_id": project_id,
        "project_name": project_name,
        "domain": domain,
        "business_nature": business_nature,
        "status": status,
        "applicant": applicant,
        "apply_date": apply_date,
        "title": title,
        "urgency": urgency,
    }


@pytest.fixture
def sample_changes() -> list[dict[str, Any]]:
    """3 条变更单摘要（覆盖 draft/implementing/closed 三种状态）"""
    return [
        _make_change(
            change_number="CHG-SCPT-2026-086",
            status="draft",
            title="QML 重构",
        ),
        _make_change(
            change_number="CHG-PLC-2026-001",
            project_id="DJ-2026-005",
            project_name="输送线",
            domain="PLC",
            status="implementing",
            title="输送线逻辑优化",
            urgency="urgent",
        ),
        _make_change(
            change_number="CHG-DOCU-2026-010",
            project_id="DJ-2026-010",
            project_name="包装机",
            domain="DOCU",
            business_nature="REQ",
            status="closed",
            title="操作手册更新",
        ),
    ]


# ── 初始状态 ───────────────────────────────────────────────


def test_initial_state_empty(qapp: QApplication) -> None:
    """新建 ChangeListModel 应为空"""
    model = ChangeListModel()
    assert model.rowCount() == 0
    assert model.changeCount() == 0
    assert model.getChangeAt(0) is None


# ── setChanges ────────────────────────────────────────────


def test_setChanges_populates_model(
    qapp: QApplication, sample_changes: list[dict[str, Any]]
) -> None:
    """setChanges 后 rowCount/changeCount/getChangeAt 应正确返回"""
    model = ChangeListModel()
    model.setChanges(sample_changes)

    assert model.rowCount() == 3
    assert model.changeCount() == 3

    c0 = model.getChangeAt(0)
    assert c0 is not None
    assert c0["change_number"] == "CHG-SCPT-2026-086"

    c2 = model.getChangeAt(2)
    assert c2 is not None
    assert c2["change_number"] == "CHG-DOCU-2026-010"


def test_setChanges_empty_list_clears_model(qapp: QApplication) -> None:
    """setChanges([]) 应清空模型（与 clear 等价）"""
    model = ChangeListModel()
    model.setChanges([_make_change()])
    assert model.rowCount() == 1

    model.setChanges([])
    assert model.rowCount() == 0
    assert model.changeCount() == 0


# ── roleNames ─────────────────────────────────────────────


def test_roleNames_returns_ten_mappings(qapp: QApplication) -> None:
    """roleNames 应返回 10 个角色映射（change_number..urgency）"""
    model = ChangeListModel()
    role_names = model.roleNames()

    assert len(role_names) == 10
    expected_names = {
        b"change_number",
        b"project_id",
        b"project_name",
        b"domain",
        b"business_nature",
        b"status",
        b"applicant",
        b"apply_date",
        b"title",
        b"urgency",
    }
    assert set(role_names.values()) == expected_names


def test_roleNames_role_to_field_alignment(qapp: QApplication) -> None:
    """每个 role 对应的字段名应与 dict key 一致"""
    model = ChangeListModel()
    role_names = model.roleNames()
    id_to_name = {role_id: name.decode("ascii") for role_id, name in role_names.items()}

    assert id_to_name[ChangeListModel.ChangeNumberRole] == "change_number"
    assert id_to_name[ChangeListModel.ProjectIdRole] == "project_id"
    assert id_to_name[ChangeListModel.ProjectNameRole] == "project_name"
    assert id_to_name[ChangeListModel.DomainRole] == "domain"
    assert id_to_name[ChangeListModel.BusinessNatureRole] == "business_nature"
    assert id_to_name[ChangeListModel.StatusRole] == "status"
    assert id_to_name[ChangeListModel.ApplicantRole] == "applicant"
    assert id_to_name[ChangeListModel.ApplyDateRole] == "apply_date"
    assert id_to_name[ChangeListModel.TitleRole] == "title"
    assert id_to_name[ChangeListModel.UrgencyRole] == "urgency"


# ── data() ─────────────────────────────────────────────────


def test_data_returns_correct_field_for_each_role(
    qapp: QApplication, sample_changes: list[dict[str, Any]]
) -> None:
    """data(index, role) 应返回对应字段的字符串值"""
    model = ChangeListModel()
    model.setChanges(sample_changes)

    idx = model.index(0)  # CHG-SCPT-2026-086

    assert model.data(idx, ChangeListModel.ChangeNumberRole) == "CHG-SCPT-2026-086"
    assert model.data(idx, ChangeListModel.ProjectIdRole) == "SW-2026-008"
    assert model.data(idx, ChangeListModel.ProjectNameRole) == "auto-pm"
    assert model.data(idx, ChangeListModel.DomainRole) == "SCPT"
    assert model.data(idx, ChangeListModel.BusinessNatureRole) == "OPT"
    assert model.data(idx, ChangeListModel.StatusRole) == "draft"
    assert model.data(idx, ChangeListModel.ApplicantRole) == "glm"
    assert model.data(idx, ChangeListModel.ApplyDateRole) == "2026-07-04"
    assert model.data(idx, ChangeListModel.TitleRole) == "QML 重构"
    assert model.data(idx, ChangeListModel.UrgencyRole) == "normal"


def test_data_for_plc_change_returns_correct_domain(
    qapp: QApplication, sample_changes: list[dict[str, Any]]
) -> None:
    """验证 PLC 变更单的 domain/urgency 字段"""
    model = ChangeListModel()
    model.setChanges(sample_changes)

    idx = model.index(1)  # CHG-PLC-2026-001
    assert model.data(idx, ChangeListModel.DomainRole) == "PLC"
    assert model.data(idx, ChangeListModel.UrgencyRole) == "urgent"
    assert model.data(idx, ChangeListModel.StatusRole) == "implementing"


def test_data_invalid_index_returns_none(qapp: QApplication) -> None:
    """无效 index 返回 None"""
    model = ChangeListModel()
    invalid_idx = QModelIndex()
    assert model.data(invalid_idx, ChangeListModel.ChangeNumberRole) is None


def test_data_out_of_bounds_returns_none(
    qapp: QApplication, sample_changes: list[dict[str, Any]]
) -> None:
    """超出范围的 row 返回 None"""
    model = ChangeListModel()
    model.setChanges(sample_changes)

    idx = model.index(99)
    assert model.data(idx, ChangeListModel.ChangeNumberRole) is None


# ── clear() ────────────────────────────────────────────────


def test_clear_resets_model(qapp: QApplication, sample_changes: list[dict[str, Any]]) -> None:
    """clear() 应清空模型"""
    model = ChangeListModel()
    model.setChanges(sample_changes)
    assert model.rowCount() == 3

    model.clear()
    assert model.rowCount() == 0
    assert model.changeCount() == 0
    assert model.getChangeAt(0) is None


# ── getChangeAt 边界 ─────────────────────────────────────


def test_getChangeAt_out_of_bounds_returns_none(
    qapp: QApplication, sample_changes: list[dict[str, Any]]
) -> None:
    """getChangeAt 越界返回 None"""
    model = ChangeListModel()
    model.setChanges(sample_changes)

    assert model.getChangeAt(-1) is None
    assert model.getChangeAt(99) is None
