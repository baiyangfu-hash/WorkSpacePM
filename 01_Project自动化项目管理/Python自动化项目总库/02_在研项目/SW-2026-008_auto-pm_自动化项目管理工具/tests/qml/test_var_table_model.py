"""VarTableModel 单元测试（V0.6.0 W3-S5~S9）

覆盖：
- 8 列结构（COLUMNS 常量 + headerData）
- setEntries（dict/list 两种形式）+ clear
- 单元格编辑（setData + setCell）+ 字段校验
- 批量操作（batchUpdate 多行同列）
- 撤销/重做（UndoStack ≥20 步）+ canUndo/canRedo
- rowCount/columnCount/data/getCell

测试策略：
- 直接调用 Python 方法（不走 QML 引擎）
- 用 qapp fixture 确保 Qt 事件循环可用
- 断言内部 _rows 状态 + 撤销栈大小
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from auto_pm.ui.qml.models.var_table_model import (
    COL_ADDRESS,
    COL_COMMENT,
    COL_INDEX,
    COL_SIGNAL_TYPE,
    COL_STATION,
    COL_TAG,
    COLUMNS,
    UndoAction,
    UndoStack,
    VarTableModel,
    _validate_field,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


# ── COLUMNS / 常量 ────────────────────────────────────────


def test_columns_has_8_fields() -> None:
    """COLUMNS 应有 8 个字段（# + 7 数据列）"""
    assert len(COLUMNS) == 8
    assert COLUMNS[0] == "#"
    assert COLUMNS[1] == "station"
    assert COLUMNS[7] == "comment"


def test_col_constants_match_indexes() -> None:
    """列索引常量与 COLUMNS 顺序一致"""
    assert COL_INDEX == 0
    assert COL_STATION == 1
    assert COL_SIGNAL_TYPE == 2
    assert COL_ADDRESS == 3
    assert COL_TAG == 4
    assert COL_COMMENT == 7


# ── UndoStack ─────────────────────────────────────────────


def test_undo_stack_basic() -> None:
    """UndoStack 基本 push/undo/redo 流程"""
    stack = UndoStack(max_size=100)
    assert not stack.can_undo()
    assert not stack.can_redo()

    stack.push(UndoAction(row=0, col=1, old_value="a", new_value="b"))
    assert stack.can_undo()
    assert not stack.can_redo()

    action = stack.undo()
    assert action is not None
    assert action.row == 0
    assert stack.can_redo()
    assert not stack.can_undo()

    action2 = stack.redo()
    assert action2 is not None
    assert stack.can_undo()
    assert not stack.can_redo()


def test_undo_stack_push_clears_redo() -> None:
    """新动作 push 后 redo 栈应被清空"""
    stack = UndoStack()
    stack.push(UndoAction(0, 1, "a", "b"))
    stack.undo()  # undo 栈空，redo 栈有 1
    assert stack.can_redo()

    stack.push(UndoAction(1, 1, "c", "d"))  # push 后 redo 应清空
    assert not stack.can_redo()
    assert stack.can_undo()


def test_undo_stack_max_size_limit() -> None:
    """UndoStack 应支持 ≥20 步（实际 maxlen=100）"""
    stack = UndoStack(max_size=100)
    for i in range(30):  # 推 30 个动作超过 20
        stack.push(UndoAction(i, 1, f"old{i}", f"new{i}"))
    assert stack.can_undo()
    # 撤销 30 步
    count = 0
    while stack.can_undo():
        stack.undo()
        count += 1
    assert count == 30


def test_undo_stack_clear() -> None:
    """clear() 应同时清空 undo + redo 栈"""
    stack = UndoStack()
    stack.push(UndoAction(0, 1, "a", "b"))
    stack.undo()
    stack.clear()
    assert not stack.can_undo()
    assert not stack.can_redo()


# ── 字段校验 ──────────────────────────────────────────────


def test_validate_field_address_required() -> None:
    """地址字段必填"""
    ok, _ = _validate_field(COL_ADDRESS, "")
    assert not ok
    ok, _ = _validate_field(COL_ADDRESS, "   ")
    assert not ok
    ok, _ = _validate_field(COL_ADDRESS, "Y10")
    assert ok


def test_validate_field_station_required() -> None:
    """站点字段必填"""
    ok, _ = _validate_field(COL_STATION, "")
    assert not ok
    ok, _ = _validate_field(COL_STATION, "cpu0")
    assert ok


def test_validate_field_tag_no_space() -> None:
    """标签不能含空格"""
    ok, _ = _validate_field(COL_TAG, "tag with space")
    assert not ok
    ok, _ = _validate_field(COL_TAG, "tag_no_space")
    assert ok


def test_validate_field_comment_allows_anything() -> None:
    """注释字段允许任意值（含空格）"""
    ok, _ = _validate_field(COL_COMMENT, "")
    assert ok
    ok, _ = _validate_field(COL_COMMENT, "any text with spaces")
    assert ok


# ── VarTableModel 基本 ────────────────────────────────────


def test_var_table_model_empty_state(qapp: QApplication) -> None:
    """空模型 rowCount/columnCount 应正确"""
    model = VarTableModel()
    assert model.rowCount() == 0
    assert model.columnCount() == 8


def test_var_table_model_header_data(qapp: QApplication) -> None:
    """headerData 应返回 COLUMNS 字段名"""
    model = VarTableModel()
    assert model.headerData(0, Qt.Orientation.Horizontal) == "#"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "station"
    assert model.headerData(7, Qt.Orientation.Horizontal) == "comment"
    assert model.headerData(0, Qt.Orientation.Vertical) == "1"


# ── setEntries ────────────────────────────────────────────


def test_var_table_model_set_entries_dict(qapp: QApplication) -> None:
    """setEntries 接受 dict 形式，行数应正确"""
    model = VarTableModel()
    entries = [
        {
            "station": "cpu0",
            "signal_type": "DI",
            "address": "Y0",
            "tag": "tag0",
            "signal_name": "信号0",
            "device": "dev0",
            "comment": "注释0",
        },
        {
            "station": "cpu1",
            "signal_type": "DO",
            "address": "Y1",
            "tag": "tag1",
            "signal_name": "信号1",
            "device": "dev1",
            "comment": "注释1",
        },
    ]
    model.setEntries(entries)
    qapp.processEvents()

    assert model.rowCount() == 2
    assert model.columnCount() == 8


def test_var_table_model_set_entries_list(qapp: QApplication) -> None:
    """setEntries 接受 list 形式（前 7 字段）"""
    model = VarTableModel()
    entries = [
        ["cpu0", "DI", "Y0", "tag0", "信号0", "dev0", "注释0"],
        ["cpu1", "DO", "Y1", "tag1", "信号1", "dev1", "注释1"],
    ]
    model.setEntries(entries)
    qapp.processEvents()

    assert model.rowCount() == 2
    # 验证 station 列（col=1）
    assert model.getCell(0, COL_STATION) == "cpu0"
    assert model.getCell(1, COL_STATION) == "cpu1"


def test_var_table_model_clear(qapp: QApplication) -> None:
    """clear 应清空所有行"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "address": "Y0"}])
    assert model.rowCount() == 1

    model.clear()
    assert model.rowCount() == 0


def test_var_table_model_data_index_column(qapp: QApplication) -> None:
    """data() 在 # 列应返回 1-based 索引"""
    model = VarTableModel()
    model.setEntries(
        [
            {"station": "cpu0", "address": "Y0"},
            {"station": "cpu1", "address": "Y1"},
        ]
    )
    qapp.processEvents()

    idx0 = model.index(0, COL_INDEX)
    idx1 = model.index(1, COL_INDEX)
    assert model.data(idx0, Qt.ItemDataRole.DisplayRole) == "1"
    assert model.data(idx1, Qt.ItemDataRole.DisplayRole) == "2"


# ── 单元格编辑 ────────────────────────────────────────────


def test_var_table_model_set_cell_basic(qapp: QApplication) -> None:
    """setCell 应正确更新单元格值"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "address": "Y0", "tag": "old"}])
    qapp.processEvents()

    ok = model.setCell(0, COL_TAG, "new_tag")
    assert ok
    assert model.getCell(0, COL_TAG) == "new_tag"


def test_var_table_model_set_cell_index_readonly(qapp: QApplication) -> None:
    """setCell 在 # 列应失败（只读）"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0"}])

    ok = model.setCell(0, COL_INDEX, "999")
    assert not ok


def test_var_table_model_set_cell_validation_rejects_empty_address(
    qapp: QApplication,
) -> None:
    """setCell 校验：地址不能为空"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "address": "Y0"}])

    ok = model.setCell(0, COL_ADDRESS, "")
    assert not ok
    assert model.getCell(0, COL_ADDRESS) == "Y0"  # 未变


def test_var_table_model_set_cell_no_change_returns_false(
    qapp: QApplication,
) -> None:
    """setCell 设置相同值应返回 False（无变化）"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "tag": "same"}])

    ok = model.setCell(0, COL_TAG, "same")
    assert not ok


def test_var_table_model_set_cell_pushes_undo(qapp: QApplication) -> None:
    """setCell 成功后 undo 栈大小应增加"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "tag": "old"}])
    assert model.undoStackSize() == 0

    model.setCell(0, COL_TAG, "new")
    assert model.undoStackSize() == 1


# ── 批量操作 ──────────────────────────────────────────────


def test_var_table_model_batch_update(qapp: QApplication) -> None:
    """batchUpdate 应批量更新多行同列"""
    model = VarTableModel()
    model.setEntries(
        [
            {"station": "cpu0", "signal_type": "DI"},
            {"station": "cpu1", "signal_type": "DO"},
            {"station": "cpu2", "signal_type": "AI"},
        ]
    )

    count = model.batchUpdate([0, 2], COL_SIGNAL_TYPE, "AO")
    assert count == 2
    assert model.getCell(0, COL_SIGNAL_TYPE) == "AO"
    assert model.getCell(1, COL_SIGNAL_TYPE) == "DO"  # 未改
    assert model.getCell(2, COL_SIGNAL_TYPE) == "AO"


def test_var_table_model_batch_update_skips_same_value(
    qapp: QApplication,
) -> None:
    """batchUpdate 对相同值不计数"""
    model = VarTableModel()
    model.setEntries(
        [
            {"station": "cpu0", "signal_type": "DI"},
            {"station": "cpu1", "signal_type": "DI"},
        ]
    )

    count = model.batchUpdate([0, 1], COL_SIGNAL_TYPE, "DI")
    assert count == 0


def test_var_table_model_batch_update_validates(qapp: QApplication) -> None:
    """batchUpdate 应校验字段（地址不能为空）"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "address": "Y0"}])

    count = model.batchUpdate([0], COL_ADDRESS, "")
    assert count == 0


def test_var_table_model_batch_update_index_col_rejected(
    qapp: QApplication,
) -> None:
    """batchUpdate 在 # 列应返回 0（只读）"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0"}])

    count = model.batchUpdate([0], COL_INDEX, "999")
    assert count == 0


def test_var_table_model_batch_update_pushes_undo_per_row(
    qapp: QApplication,
) -> None:
    """batchUpdate 每行变更应独立推入 undo 栈"""
    model = VarTableModel()
    model.setEntries(
        [
            {"station": "cpu0", "signal_type": "DI"},
            {"station": "cpu1", "signal_type": "DO"},
            {"station": "cpu2", "signal_type": "AI"},
        ]
    )

    model.batchUpdate([0, 1, 2], COL_SIGNAL_TYPE, "AO")
    assert model.undoStackSize() == 3


# ── 撤销/重做 ─────────────────────────────────────────────


def test_var_table_model_undo_redo_basic(qapp: QApplication) -> None:
    """undo/redo 基本流程：单元格改值后撤销应还原"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "tag": "old"}])

    model.setCell(0, COL_TAG, "new")
    assert model.getCell(0, COL_TAG) == "new"

    ok = model.undo()
    assert ok
    assert model.getCell(0, COL_TAG) == "old"

    ok = model.redo()
    assert ok
    assert model.getCell(0, COL_TAG) == "new"


def test_var_table_model_can_undo_redo_state(qapp: QApplication) -> None:
    """canUndo/canRedo 在不同状态下应正确"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "tag": "old"}])

    # 初始：都不能
    assert not model.canUndo()
    assert not model.canRedo()

    # 改一次：能 undo
    model.setCell(0, COL_TAG, "new")
    assert model.canUndo()
    assert not model.canRedo()

    # 撤销：能 redo
    model.undo()
    assert not model.canUndo()
    assert model.canRedo()

    # 重做：能 undo
    model.redo()
    assert model.canUndo()
    assert not model.canRedo()


def test_var_table_model_undo_20_steps(qapp: QApplication) -> None:
    """≥20 步撤销链应可完整回退（W3-S9 验收）"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "tag": "init"}])

    # 改 25 次（每次改 tag 列）
    for i in range(25):
        model.setCell(0, COL_TAG, f"v{i}")
    assert model.undoStackSize() == 25
    assert model.getCell(0, COL_TAG) == "v24"

    # 撤销 25 次
    for _ in range(25):
        assert model.undo()
    assert model.getCell(0, COL_TAG) == "init"

    # 重做 25 次
    for _ in range(25):
        assert model.redo()
    assert model.getCell(0, COL_TAG) == "v24"


def test_var_table_model_undo_when_empty_returns_false(
    qapp: QApplication,
) -> None:
    """空栈 undo/redo 应返回 False"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0"}])

    assert not model.undo()
    assert not model.redo()


def test_var_table_model_set_entries_clears_undo_stack(
    qapp: QApplication,
) -> None:
    """setEntries 应清空 undo 栈（新数据集不复用旧栈）"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0", "tag": "old"}])
    model.setCell(0, COL_TAG, "new")
    assert model.undoStackSize() == 1

    # 重新 setEntries
    model.setEntries([{"station": "cpu1", "tag": "fresh"}])
    assert model.undoStackSize() == 0
    assert not model.canUndo()


# ── getCell 边界 ──────────────────────────────────────────


def test_var_table_model_get_cell_out_of_bounds(qapp: QApplication) -> None:
    """getCell 越界应返回空字符串"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0"}])

    assert model.getCell(99, COL_STATION) == ""
    assert model.getCell(0, 999) == ""
    assert model.getCell(-1, COL_STATION) == ""


def test_var_table_model_get_cell_index_returns_row_plus_1(
    qapp: QApplication,
) -> None:
    """getCell 在 # 列应返回 1-based 行号"""
    model = VarTableModel()
    model.setEntries(
        [
            {"station": "cpu0"},
            {"station": "cpu1"},
            {"station": "cpu2"},
        ]
    )

    assert model.getCell(0, COL_INDEX) == "1"
    assert model.getCell(1, COL_INDEX) == "2"
    assert model.getCell(2, COL_INDEX) == "3"


# ── QML Slot 接口 ─────────────────────────────────────────


def test_var_table_model_qml_slot_row_count(qapp: QApplication) -> None:
    """rowCountQml() 应返回与 rowCount() 相同值"""
    model = VarTableModel()
    model.setEntries([{"station": "cpu0"}, {"station": "cpu1"}])

    assert model.rowCountQml() == 2
    assert model.rowCountQml() == model.rowCount()


def test_var_table_model_qml_slot_column_count(qapp: QApplication) -> None:
    """columnCountQml() 应返回 8"""
    model = VarTableModel()
    assert model.columnCountQml() == 8


def test_var_table_model_qml_slot_header_text(qapp: QApplication) -> None:
    """headerText(col) 应返回 COLUMNS[col]"""
    model = VarTableModel()
    assert model.headerText(0) == "#"
    assert model.headerText(1) == "station"
    assert model.headerText(7) == "comment"
    assert model.headerText(99) == ""  # 越界返回空
