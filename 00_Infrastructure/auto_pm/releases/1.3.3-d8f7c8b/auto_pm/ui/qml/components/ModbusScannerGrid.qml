// ModbusScannerGrid.qml — 寄存器扫描探测器网格（对齐 V13 原型）
//
// 功能：
//   - 10×10 共 100 个地址格子，展示寄存器扫描结果
//   - 三种状态：灰色（未扫描）/ 绿色（活跃，有应答）/ 红色（超时，无应答）
//   - updateCell(offset, isActive)：更新单格状态（由 ModbusBridge.scanCellUpdated 驱动）
//   - resetAll()：重置全部格子到灰色未扫描状态
//   - 点击格子可跳转到对应地址（通过 cellClicked(offset) 信号通知父视图）
//
// 用法：
//   ModbusScannerGrid {
//       id: scannerGrid
//       startOffset: 0
//       onCellClicked: { mbStartField.text = offset.toString() }
//   }
//   // 更新单格：
//   Connections {
//       target: modbusBridge
//       function onScanCellUpdated(offset, isActive) {
//           scannerGrid.updateCell(offset, isActive)
//       }
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property int startOffset: 0     // 起始偏移（用于显示物理地址标签）
    property int totalCells: 100    // 格子总数（10×10）

    signal cellClicked(int offset)

    // ── 格子状态模型（0=未扫描, 1=活跃, 2=超时）────────
    property var _cellStates: []

    Component.onCompleted: resetAll()

    // ── 接口函数 ─────────────────────────────────────────
    function resetAll() {
        var arr = []
        for (var i = 0; i < root.totalCells; i++) arr.push(0)
        root._cellStates = arr
        cellRepeater.model = root._cellStates
    }

    function updateCell(offset, isActive) {
        if (offset < 0 || offset >= root.totalCells) return
        var arr = root._cellStates.slice()
        arr[offset] = isActive ? 1 : 2
        root._cellStates = arr
        // 强制 Repeater 刷新单项
        var item = cellRepeater.itemAt(offset)
        if (item) item._state = arr[offset]
    }

    implicitHeight: gridContainer.implicitHeight

    // ── 说明文字 ──────────────────────────────────────────
    Column {
        anchors.fill: parent
        spacing: Theme.spacingSm

        Text {
            text: "对目标 PLC 保持寄存器区间 [" + (40001 + root.startOffset) +
                  " - " + (40001 + root.startOffset + root.totalCells - 1) +
                  "] 进行并发 FC03 扫描探测。🟢 活跃  🔴 超时  ⬜ 未扫描"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeXs
            wrapMode: Text.WordWrap
            width: parent.width
        }

        // 10×10 网格
        Grid {
            id: gridContainer
            columns: 10
            spacing: 5
            width: parent.width

            Repeater {
                id: cellRepeater
                model: root.totalCells

                Rectangle {
                    id: cellRect
                    property int _state: 0  // 0=灰, 1=活跃, 2=超时

                    width: (gridContainer.width - 9 * 5) / 10
                    height: 32
                    radius: Theme.radiusSm

                    // 状态驱动颜色
                    color: {
                        if (_state === 1) return Qt.rgba(0.06, 0.73, 0.51, 0.15)
                        if (_state === 2) return Qt.rgba(0.94, 0.27, 0.27, 0.05)
                        return Qt.rgba(1, 1, 1, 0.03)
                    }
                    border.color: {
                        if (_state === 1) return Theme.success
                        if (_state === 2) return Qt.rgba(0.94, 0.27, 0.27, 0.3)
                        return Theme.border
                    }
                    border.width: 1

                    Behavior on color { ColorAnimation { duration: 150 } }

                    Text {
                        anchors.centerIn: parent
                        text: (root.startOffset + index).toString().padStart(2, "0")
                        font.pixelSize: Theme.fontSizeXs
                        font.family: "Consolas, Courier New, monospace"
                        color: {
                            if (cellRect._state === 1) return Theme.success
                            if (cellRect._state === 2) return Theme.error
                            return Theme.textMuted
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onEntered: cellRect.opacity = 0.7
                        onExited: cellRect.opacity = 1.0
                        onClicked: root.cellClicked(root.startOffset + index)
                    }
                }
            }
        }
    }
}
