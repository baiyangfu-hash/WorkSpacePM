// BackendStatus.qml - 数据库连接状态指示灯（对齐原型 V7 .backend-status）
//
// CHG-SCPT-2026-102 T3：侧边栏底部 DB 连接状态指示
//
// 状态灯 + 文本，绿灯=已连接 / 红灯=未连接
//
// 解耦设计：connected 属性由 main.qml 绑定 systemBridge.hasService
// （T4 简化决策：不调 system_bridge.getDbStatus()，复用现有 hasService Property）
//
// 用法：
//   BackendStatus {
//       connected: systemBridge.hasService
//       anchors.bottom: parent.bottom
//       anchors.horizontalCenter: parent.horizontalCenter
//   }
import QtQuick
import QtQuick.Layouts
import "../theme"

RowLayout {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property bool connected: false

    // ── 布局 ────────────────────────────────────────────
    spacing: Theme.spacingSm
    Layout.preferredHeight: 24

    // ── 状态灯 ──────────────────────────────────────────
    Rectangle {
        Layout.preferredWidth: 8
        Layout.preferredHeight: 8
        radius: width / 2
        color: root.connected ? Theme.success : Theme.error

        // 光晕效果（已连接时绿灯发光）
        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 2
            height: parent.height * 2
            radius: width / 2
            color: parent.color
            opacity: root.connected ? 0.3 : 0.0
            z: -1
        }
    }

    // ── 状态文本 ────────────────────────────────────────
    Text {
        text: root.connected ? "数据库已连接" : "数据库未连接"
        font.pixelSize: Theme.fontSizeXs
        color: root.connected ? Theme.textSecondary : Theme.error
    }
}
