// SidebarBadge.qml - 侧边栏待办数徽标（对齐原型 V7 .sidebar-badge）
//
// CHG-SCPT-2026-102 T3：三轨道导航入口右上角待办数指示
//
// 小圆形 + 数字，count > 0 时 visible，count > 99 显示 "99+"
// 颜色用 Theme.error（红色，醒目提示）
//
// 用法：
//   SidebarBadge {
//       count: changeBridge.changeCount
//       anchors.top: parent.top
//       anchors.right: parent.right
//   }
import QtQuick
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property int count: 0

    // ── 视觉样式 ────────────────────────────────────────
    // count > 0 时显示，否则隐藏
    visible: count > 0
    width: _displayText.implicitWidth >= 24 ? _displayText.implicitWidth + 8 : 18
    height: 18
    radius: height / 2
    color: Theme.error
    border.color: Theme.sidebarBg  // 描边与侧边栏背景一致，形成"挖空"效果
    border.width: 2

    // ── 数字文本（>99 显示 99+）─────────────────────────
    Text {
        id: _displayText
        anchors.centerIn: parent
        text: root.count > 99 ? "99+" : String(root.count)
        color: "white"
        font.pixelSize: Theme.fontSizeXs
        font.bold: true
        minimumPixelSize: Theme.fontSizeXs
    }
}
