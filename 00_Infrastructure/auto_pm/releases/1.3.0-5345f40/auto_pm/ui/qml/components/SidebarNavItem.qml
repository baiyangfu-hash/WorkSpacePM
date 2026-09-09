// SidebarNavItem.qml — 通用侧边栏导航项 V1.0.0
// 消灭 main.qml 中重复的 Rectangle + RowLayout + MouseArea 三件套
// 新增导航项只需 <SidebarNavItem pageKey="xxx" label="xxx" icon="..." />
//
// 预留扩展点:
//   - badgeCount: 待办徽标
//   - navEnabled: 是否可点击
//   - isActive: 激活态（由父组件绑定）
//   - accentColor: 特殊颜色（如 Modbus 绿色轨道）

import QtQuick
import QtQuick.Layouts
import "."
import "../theme"

Rectangle {
    id: root

    // ── 公开属性
    property string pageKey: ""
    property string icon: ""
    property string label: ""
    property bool   navEnabled: true
    property int    badgeCount: 0
    property bool   isActive: false
    property color  accentColor: Theme.primary

    // ── 信号
    signal navClicked(string pageKey)

    // ── 尺寸与外观
    Layout.fillWidth: true
    Layout.preferredHeight: 36
    radius: Theme.radiusSm
    color: isActive ? accentColor : "transparent"
    opacity: navEnabled ? 1.0 : 0.4

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingSm
        anchors.rightMargin: Theme.spacingSm
        spacing: Theme.spacingSm

        Text {
            text: root.icon
            color: root.isActive ? "white" : Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
        }

        Text {
            text: root.label
            color: root.isActive ? "white" : Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
        }

        SidebarBadge {
            count: root.badgeCount
            visible: root.badgeCount > 0
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.navEnabled
        cursorShape: root.navEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.navClicked(root.pageKey)
    }
}
