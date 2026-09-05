"""PLC-HMI 概念映射：HMI 数据模型（变量表模型（QML 变量表编辑器的数据源））

像 HMI 触摸屏的配方数据表/报警列表，为 QML 的 ListView/TableView 提供数据源。

--- 原始注释 ---

变量表 QAbstractTableModel（V0.6.0 W3-S5~S9）

VarTableModel 包装 VarEntry 列表为 QAbstractTableModel，供 QML TableView 使用。
支持：
- 8 列（#/station/signal_type/address/tag/signal_name/device/comment）
- 单元格编辑（setData + 校验）
- 批量操作（多选 + 批量改类型/地址）
- 万行虚拟化（QML TableView 原生虚拟化，模型端只负责 data/index）
- 撤销/重做（UndoStack 集成，≥20 步可回退）

设计参考：02_设计/GUI原型设计.md §5.5 变量表编辑器
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Slot,
)

# ── 8 列定义 ──────────────────────────────────────────────
COLUMNS: tuple[str, ...] = (
    "#",  # 0: 行号（只读）
    "station",  # 1: 站点
    "signal_type",  # 2: 信号类型
    "address",  # 3: 地址
    "tag",  # 4: 标签
    "signal_name",  # 5: 信号名
    "device",  # 6: 设备
    "comment",  # 7: 注释
)

# 列索引常量
COL_INDEX = 0
COL_STATION = 1
COL_SIGNAL_TYPE = 2
COL_ADDRESS = 3
COL_TAG = 4
COL_SIGNAL_NAME = 5
COL_DEVICE = 6
COL_COMMENT = 7


# ── 撤销/重做栈 ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UndoAction:
    """单次撤销动作（记录一个或多个单元格的变更）"""

    row: int
    col: int
    old_value: str
    new_value: str


class UndoStack:
    """撤销/重做栈（≥20 步可回退）

    用 deque(maxlen=100) 限制内存，undo_stack 正向弹栈，redo_stack 反向弹栈。
    """

    def __init__(self, max_size: int = 100) -> None:
        self._undo: deque[UndoAction] = deque(maxlen=max_size)
        self._redo: deque[UndoAction] = deque(maxlen=max_size)

    def push(self, action: UndoAction) -> None:
        """记录一个新动作（清空 redo 栈）"""
        self._undo.append(action)
        self._redo.clear()

    def undo(self) -> UndoAction | None:
        """撤销最新动作，返回该动作（用于反向应用）"""
        if not self._undo:
            return None
        action = self._undo.pop()
        self._redo.append(action)
        return action

    def redo(self) -> UndoAction | None:
        """重做最新撤销动作"""
        if not self._redo:
            return None
        action = self._redo.pop()
        self._undo.append(action)
        return action

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()


# ── 字段校验规则 ──────────────────────────────────────────


def _validate_field(col: int, value: str) -> tuple[bool, str]:
    """字段校验：返回 (是否通过, 错误消息)"""
    if col == COL_ADDRESS:
        # 地址必填
        if not value.strip():
            return False, "地址不能为空"
    if col == COL_TAG:
        # 标签不能含空格
        if " " in value:
            return False, "标签不能含空格"
    if col == COL_STATION:
        # 站点必填
        if not value.strip():
            return False, "站点不能为空"
    return True, ""


# ── 主模型 ────────────────────────────────────────────────


class VarTableModel(QAbstractTableModel):
    """变量表 QAbstractTableModel

    QML 端通过 TableView + model 子类访问。
    支持 setEntries / setData / 批量操作 / 撤销重做。
    """

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[list[str]] = []  # 每行为 8 字段字符串列表
        self._undo_stack = UndoStack(max_size=100)

    # ── QAbstractTableModel 必须实现 ───────────────────────

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        if not (0 <= index.column() < len(COLUMNS)):
            return None

        row_data = self._rows[index.row()]

        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if index.column() == COL_INDEX:
                # 行号列返回 1-based 索引
                return str(index.row() + 1)
            return row_data[index.column()]
        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        if not (0 <= index.row() < len(self._rows)):
            return False
        if index.column() == COL_INDEX:
            return False  # 行号列只读

        col = index.column()
        new_value = str(value) if not isinstance(value, str) else value
        old_value = self._rows[index.row()][col]

        # 校验
        ok, _msg = _validate_field(col, new_value)
        if not ok:
            return False

        if old_value == new_value:
            return False  # 无变化

        # 应用变更 + 推入 undo 栈
        self._rows[index.row()][col] = new_value
        self._undo_stack.push(
            UndoAction(row=index.row(), col=col, old_value=old_value, new_value=new_value)
        )
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.column() == COL_INDEX:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(COLUMNS):
            return COLUMNS[section]
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None

    # ── 数据更新接口（QML 端 @Slot） ──────────────────────

    @Slot(list)
    def setEntries(self, entries: list[Any]) -> None:
        """批量替换变量表数据（重置模型）

        QML 端传入 [[station, signal_type, address, tag, signal_name, device, comment], ...]
        模型内部补齐 # 列。
        """
        self.beginResetModel()
        self._rows = []
        for entry in entries:
            # 兼容 dict 和 list 两种形式
            if isinstance(entry, dict):
                row = [
                    "",
                    str(entry.get("station", "")),
                    str(entry.get("signal_type", "")),
                    str(entry.get("address", "")),
                    str(entry.get("tag", "")),
                    str(entry.get("signal_name", "")),
                    str(entry.get("device", "")),
                    str(entry.get("comment", "")),
                ]
            elif isinstance(entry, (list, tuple)):
                # 列表形式：前 7 字段，第 8 字段补空（# 列由模型算）
                row = [""] + [str(x) for x in entry[:7]]
                while len(row) < 8:
                    row.append("")
            else:
                continue
            self._rows.append(row)
        self._undo_stack.clear()
        self.endResetModel()

    @Slot()
    def clear(self) -> None:
        """清空变量表"""
        self.beginResetModel()
        self._rows = []
        self._undo_stack.clear()
        self.endResetModel()

    @Slot(int, int, str, result=bool)
    def setCell(self, row: int, col: int, value: str) -> bool:
        """QML 端调用：设置 (row, col) 单元格的值

        返回是否设置成功（校验失败返回 False）。
        """
        if not (0 <= row < len(self._rows)):
            return False
        if col == COL_INDEX:
            return False
        idx = self.index(row, col)
        return self.setData(idx, value, Qt.ItemDataRole.EditRole)

    @Slot(int, int, result=str)
    def getCell(self, row: int, col: int) -> str:
        """QML 端调用：读取 (row, col) 单元格的值"""
        if not (0 <= row < len(self._rows)):
            return ""
        if not (0 <= col < len(COLUMNS)):
            return ""
        if col == COL_INDEX:
            return str(row + 1)
        return self._rows[row][col]

    @Slot(list, int, str, result=int)
    def batchUpdate(self, rows: list[int], col: int, value: str) -> int:
        """批量更新多行的同一列

        QML 端选中多个行后调用 batchUpdate([0, 2, 5], COL_SIGNAL_TYPE, "DI") 批量改类型。
        每个单元格的变更独立推入 undo 栈（撤销时逐行回退）。
        返回实际成功更新的行数。
        """
        if col == COL_INDEX:
            return 0
        ok, _msg = _validate_field(col, value)
        if not ok:
            return 0

        count = 0
        for row in rows:
            if not (0 <= row < len(self._rows)):
                continue
            old_value = self._rows[row][col]
            if old_value == value:
                continue
            self._rows[row][col] = value
            self._undo_stack.push(
                UndoAction(row=row, col=col, old_value=old_value, new_value=value)
            )
            idx = self.index(row, col)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.EditRole])
            count += 1
        return count

    @Slot(result=int)
    def rowCountQml(self) -> int:
        """QML 端调用：返回行数"""
        return len(self._rows)

    @Slot(result=int)
    def columnCountQml(self) -> int:
        """QML 端调用：返回列数"""
        return len(COLUMNS)

    @Slot(int, result=str)
    def headerText(self, col: int) -> str:
        """QML 端调用：返回列标题"""
        if 0 <= col < len(COLUMNS):
            return COLUMNS[col]
        return ""

    # ── 撤销/重做接口 ─────────────────────────────────────

    @Slot(result=bool)
    def canUndo(self) -> bool:
        return self._undo_stack.can_undo()

    @Slot(result=bool)
    def canRedo(self) -> bool:
        return self._undo_stack.can_redo()

    @Slot(result=bool)
    def undo(self) -> bool:
        """撤销最新动作"""
        action = self._undo_stack.undo()
        if action is None:
            return False
        # 反向应用：将 new_value 还原为 old_value
        if 0 <= action.row < len(self._rows) and 0 <= action.col < len(COLUMNS):
            self._rows[action.row][action.col] = action.old_value
            idx = self.index(action.row, action.col)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.EditRole])
            return True
        return False

    @Slot(result=bool)
    def redo(self) -> bool:
        """重做最新撤销动作"""
        action = self._undo_stack.redo()
        if action is None:
            return False
        if 0 <= action.row < len(self._rows) and 0 <= action.col < len(COLUMNS):
            self._rows[action.row][action.col] = action.new_value
            idx = self.index(action.row, action.col)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.EditRole])
            return True
        return False

    @Slot(result=int)
    def undoStackSize(self) -> int:
        """返回 undo 栈大小（用于验证 ≥20 步）"""
        return len(self._undo_stack._undo)

    @Slot(result=int)
    def redoStackSize(self) -> int:
        return len(self._undo_stack._redo)

    @Slot(result=list)
    def getEntries(self) -> list[dict[str, Any]]:
        """返回当前变量表中的全部条目"""
        result = []
        for row in self._rows:
            result.append(
                {
                    "station": row[COL_STATION],
                    "signal_type": row[COL_SIGNAL_TYPE],
                    "address": row[COL_ADDRESS],
                    "tag": row[COL_TAG],
                    "signal_name": row[COL_SIGNAL_NAME],
                    "device": row[COL_DEVICE],
                    "comment": row[COL_COMMENT],
                }
            )
        return result

    # ── Python 端测试辅助 ─────────────────────────────────

    def to_rows(self) -> list[list[str]]:
        """返回内部行数据（Python 端测试用）"""
        return [list(row) for row in self._rows]
