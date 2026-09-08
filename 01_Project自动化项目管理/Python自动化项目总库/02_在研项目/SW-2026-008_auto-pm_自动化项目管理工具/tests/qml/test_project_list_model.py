"""ProjectListModel 单元测试

覆盖 QAbstractListModel 核心方法：
- rowCount / data / roleNames（必须实现）
- setProjects / clear / getProjectAt / projectCount（数据更新接口）

测试策略：
- 内存构造 ProjectInfo 列表（不依赖文件系统扫描）
- 用 qapp fixture 确保 Qt 事件循环可用（QAbstractListModel 需要 QApplication）
- 直接断言方法返回值，不走 QML 渲染
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from auto_pm.models import ProjectInfo

from auto_pm.ui.qml.models.project_list_model import ProjectListModel

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


# ── 初始状态 ───────────────────────────────────────────────


def test_initial_state_empty(qapp: QApplication) -> None:
    """新建 ProjectListModel 应为空"""
    model = ProjectListModel()
    assert model.rowCount() == 0
    assert model.projectCount() == 0
    assert model.getProjectAt(0) is None


# ── setProjects ────────────────────────────────────────────


def test_setProjects_populates_model(
    qapp: QApplication, sample_projects: list[ProjectInfo]
) -> None:
    """setProjects 后 rowCount/projectCount/getProjectAt 应正确返回"""
    model = ProjectListModel()
    model.setProjects(sample_projects)

    assert model.rowCount() == 3
    assert model.projectCount() == 3

    # getProjectAt 按索引返回
    p0 = model.getProjectAt(0)
    assert p0 is not None
    assert p0.project_id == "SW-2026-008"
    p2 = model.getProjectAt(2)
    assert p2 is not None
    assert p2.project_id == "DJ-2026-010"


def test_setProjects_empty_list_clears_model(qapp: QApplication) -> None:
    """setProjects([]) 应清空模型（与 clear 等价）"""
    model = ProjectListModel()
    model.setProjects(
        [
            ProjectInfo(
                project_id="SW-2026-008",
                name="auto-pm",
                path="c:/tmp",
                stack="python",
            )
        ]
    )
    assert model.rowCount() == 1

    model.setProjects([])
    assert model.rowCount() == 0
    assert model.projectCount() == 0


# ── roleNames ──────────────────────────────────────────────


def test_roleNames_returns_seven_mappings(qapp: QApplication) -> None:
    """roleNames 应返回 7 个角色映射，key 为 bytes"""
    model = ProjectListModel()
    role_names = model.roleNames()

    assert len(role_names) == 7
    # 验证每个 key 是 bytes（QML 端通过 model.xxx 访问）
    expected_names = {
        b"project_id",
        b"name",
        b"stack",
        b"phase",
        b"version",
        b"path",
        b"business_line",
    }
    assert set(role_names.values()) == expected_names


def test_roleNames_role_to_field_alignment(qapp: QApplication) -> None:
    """每个 role 对应的字段名应与 ProjectInfo 字段一致"""
    model = ProjectListModel()
    role_names = model.roleNames()

    # 反向映射：role_id → bytes_name
    id_to_name = {role_id: name.decode("ascii") for role_id, name in role_names.items()}

    assert id_to_name[ProjectListModel.ProjectIdRole] == "project_id"
    assert id_to_name[ProjectListModel.NameRole] == "name"
    assert id_to_name[ProjectListModel.StackRole] == "stack"
    assert id_to_name[ProjectListModel.PhaseRole] == "phase"
    assert id_to_name[ProjectListModel.VersionRole] == "version"
    assert id_to_name[ProjectListModel.PathRole] == "path"
    assert id_to_name[ProjectListModel.BusinessLineRole] == "business_line"


# ── data() ─────────────────────────────────────────────────


def test_data_returns_correct_field_for_each_role(
    qapp: QApplication, sample_projects: list[ProjectInfo]
) -> None:
    """data(index, role) 应返回对应字段的字符串值"""

    model = ProjectListModel()
    model.setProjects(sample_projects)

    idx = model.index(0)  # SW-2026-008

    # 验证每个 role 的返回值
    assert model.data(idx, ProjectListModel.ProjectIdRole) == "SW-2026-008"
    assert model.data(idx, ProjectListModel.NameRole) == "auto-pm"
    assert model.data(idx, ProjectListModel.StackRole) == "python"
    assert model.data(idx, ProjectListModel.PhaseRole) == "developing"
    assert model.data(idx, ProjectListModel.VersionRole) == "0.6.0"
    assert model.data(idx, ProjectListModel.PathRole) == "c:/tmp/SW-2026-008_auto-pm"
    assert model.data(idx, ProjectListModel.BusinessLineRole) == "SW"


def test_data_for_plc_project_returns_correct_stack(
    qapp: QApplication, sample_projects: list[ProjectInfo]
) -> None:
    """验证 PLC 项目的 stack/phase/business_line 字段"""
    model = ProjectListModel()
    model.setProjects(sample_projects)

    idx = model.index(1)  # DJ-2026-005
    assert model.data(idx, ProjectListModel.StackRole) == "plc"
    assert model.data(idx, ProjectListModel.PhaseRole) == "commissioning"
    assert model.data(idx, ProjectListModel.BusinessLineRole) == "DJ"


def test_data_invalid_index_returns_none(qapp: QApplication) -> None:
    """无效 index 返回 None"""
    from PySide6.QtCore import QModelIndex

    model = ProjectListModel()
    invalid_idx = QModelIndex()  # 无效 index
    assert model.data(invalid_idx, ProjectListModel.ProjectIdRole) is None


def test_data_out_of_bounds_returns_none(
    qapp: QApplication, sample_projects: list[ProjectInfo]
) -> None:
    """超出范围的 row 返回 None"""
    model = ProjectListModel()
    model.setProjects(sample_projects)

    idx = model.index(99)  # 超出范围
    assert model.data(idx, ProjectListModel.ProjectIdRole) is None


# ── clear() ────────────────────────────────────────────────


def test_clear_resets_model(
    qapp: QApplication, sample_projects: list[ProjectInfo]
) -> None:
    """clear() 应清空模型"""
    model = ProjectListModel()
    model.setProjects(sample_projects)
    assert model.rowCount() == 3

    model.clear()
    assert model.rowCount() == 0
    assert model.projectCount() == 0
    assert model.getProjectAt(0) is None


# ── getProjectAt 边界 ─────────────────────────────────────


def test_getProjectAt_out_of_bounds_returns_none(
    qapp: QApplication, sample_projects: list[ProjectInfo]
) -> None:
    """getProjectAt 越界返回 None"""
    model = ProjectListModel()
    model.setProjects(sample_projects)

    assert model.getProjectAt(-1) is None
    assert model.getProjectAt(99) is None
