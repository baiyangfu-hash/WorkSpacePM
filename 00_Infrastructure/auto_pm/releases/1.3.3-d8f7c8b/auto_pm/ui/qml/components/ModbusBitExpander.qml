// ModbusBitExpander.qml — 16位寄存器位解析器组件（对齐 V13 原型）
//
// 功能：
//   - 以 16 个 LED 圆点（两排 8×2）可视化展示一个 16 位寄存器的每一位
//   - 每个 LED 可点击切换 0/1 状态
//   - 自动计算并显示合成后的 Dec（十进制）和 Hex（十六进制）
//   - loadValue(val) 接口：从外部载入数值同步 LED 状态
//   - currentValue 属性：供父视图读取当前合成值
//
// 用法：
//   ModbusBitExpander {
//       id: bitExpander
//       onValueChanged: console.log("New value:", currentValue)
//   }
//   bitExpander.loadValue(1234)
//
// 参考：GitHub QModMaster 16-bit register bit view

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property int currentValue: 0         // 当前合成的 16 位整数值
    property string displayAddr: "40001" // 显示的物理地址

    signal valueChanged(int newValue)

    color: "transparent"
    implicitHeight: ledColumn.implicitHeight + addrRow.implicitHeight + decHexRow.implicitHeight + 20

    // ── 内部工具函数 ─────────────────────────────────────

    function loadValue(val) {
        currentValue = val & 0xFFFF
        _refreshLeds()
    }

    function _refreshLeds() {
        for (var i = 0; i < 16; i++) {
            var led = _getLed(i)
            if (led) led.bitActive = ((root.currentValue >> i) & 1) === 1
        }
        root.valueChanged(root.currentValue)
    }

    function _getLed(bitIndex) {
        if (bitIndex >= 8) {
            return highRow.itemAt(15 - bitIndex)  // 高字节：bit15..8 → index 0..7
        } else {
            return lowRow.itemAt(7 - bitIndex)    // 低字节：bit7..0 → index 0..7
        }
    }

    function _toggleBit(bitIndex) {
        if ((root.currentValue >> bitIndex) & 1) {
            root.currentValue &= ~(1 << bitIndex)
        } else {
            root.currentValue |= (1 << bitIndex)
        }
        root.currentValue = root.currentValue & 0xFFFF
        _refreshLeds()
    }

    // ── 物理地址行 ────────────────────────────────────────
    RowLayout {
        id: addrRow
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 8

        Text {
            text: "💡 16位寄存器位解析器"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            font.bold: true
            Layout.fillWidth: true
        }

        Text {
            text: root.displayAddr
            color: Theme.secondary
            font.pixelSize: Theme.fontSizeSm
            font.family: "Consolas, Courier New, monospace"
        }
    }

    // ── LED 矩阵（双排 8×2） ──────────────────────────────
    Column {
        id: ledColumn
        anchors.top: addrRow.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: Theme.spacingSm
        spacing: 6

        // 高字节行（Bit 15 → 8）
        Rectangle {
            width: parent.width
            height: 42
            color: Qt.rgba(0, 0, 0, 0.15)
            radius: Theme.radiusSm
            border.color: Theme.border
            border.width: 1

            // 位标签行
            RowLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 0

                Repeater {
                    model: ["15","14","13","12","11","10","9","8"]
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: modelData
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeXs
                    }
                }
            }

            // LED 灯行
            RowLayout {
                id: highRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                spacing: 0

                Repeater {
                    model: 8  // Bit 15..8
                    delegate: LedDot {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 14
                        bitIndex: 15 - index  // Bit 15, 14, 13...8
                        onToggled: root._toggleBit(bitIndex)
                    }
                }
            }
        }

        // 低字节行（Bit 7 → 0）
        Rectangle {
            width: parent.width
            height: 42
            color: Qt.rgba(0, 0, 0, 0.15)
            radius: Theme.radiusSm
            border.color: Theme.border
            border.width: 1

            RowLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 0

                Repeater {
                    model: ["7","6","5","4","3","2","1","0"]
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: modelData
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeXs
                    }
                }
            }

            RowLayout {
                id: lowRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                spacing: 0

                Repeater {
                    model: 8  // Bit 7..0
                    delegate: LedDot {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 14
                        bitIndex: 7 - index  // Bit 7, 6, 5...0
                        onToggled: root._toggleBit(bitIndex)
                    }
                }
            }
        }
    }

    // ── Dec / Hex 显示行 ──────────────────────────────────
    RowLayout {
        id: decHexRow
        anchors.top: ledColumn.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: Theme.spacingSm
        spacing: 0

        Text {
            text: "Dec: "
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
        }
        Text {
            text: root.currentValue.toString()
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            font.bold: true
        }
        Item { Layout.fillWidth: true }
        Text {
            text: "Hex: "
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
        }
        Text {
            text: "0x" + ("0000" + root.currentValue.toString(16).toUpperCase()).slice(-4)
            color: Theme.warning
            font.pixelSize: Theme.fontSizeSm
            font.bold: true
            font.family: "Consolas, Courier New, monospace"
        }
    }

    // ── 内联 LED 点组件 ────────────────────────────────────
    component LedDot: Item {
        property int bitIndex: 0
        property bool bitActive: false
        signal toggled()

        implicitHeight: 14

        Rectangle {
            id: led
            width: 12
            height: 12
            radius: 6
            anchors.centerIn: parent
            color: parent.bitActive ? Theme.success : "#1e293b"
            border.color: parent.bitActive
                          ? Qt.lighter(Theme.success, 1.3)
                          : Qt.rgba(1, 1, 1, 0.1)
            border.width: 1

            // 活跃时发光效果
            layer.enabled: parent.bitActive
            layer.effect: null  // 简化：通过颜色模拟发光，避免 Qt5 MultiEffect 依赖

            Behavior on color { ColorAnimation { duration: 80 } }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.toggled()
        }
    }
}
