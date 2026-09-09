// BarRow.qml - V0.8.0 Phase 2 可复用柱状图行组件（CHG-091）
//
// 单行柱状图：[标签] [进度条] [数值]
// 用于 ReportView 的 4 个统计卡片内每行数据展示。
//
// 用法（Repeater delegate）：
//   Repeater {
//       model: myModel  // myModel 包含 {label, value, max}
//       delegate: BarRow {}
//   }
//
// 模型字段自动绑定：model.label → labelText, model.value → value, model.max → maxValue

import QtQuick
import QtQuick.Layouts
import "../theme"

RowLayout {
    Layout.fillWidth: true
    spacing: Theme.spacingSm

    // 接受 Repeater delegate 默认绑定的 model.* 字段
    property string labelText: typeof model !== "undefined" ? (model.label || "") : ""
    property int value: typeof model !== "undefined" ? (model.value || 0) : 0
    property int maxValue: typeof model !== "undefined" ? (model.max || 0) : 0

    Text {
        text: labelText
        font.pixelSize: Theme.fontSizeSm
        color: Theme.textSecondary
        Layout.preferredWidth: 70
        elide: Text.ElideRight
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 10
        color: Theme.border
        radius: 2

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: maxValue > 0 ? parent.width * (value / maxValue) : 0
            color: Theme.primary
            radius: 2
        }
    }

    Text {
        text: value
        font.pixelSize: Theme.fontSizeSm
        font.bold: true
        color: Theme.textPrimary
        Layout.preferredWidth: 30
        horizontalAlignment: Text.AlignRight
    }
}
