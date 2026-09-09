// TabBar.qml - 可复用水平 Tab 栏（V0.6.0 W2-S4）
//
// 自定义 TabBar，不依赖 QtQuick.Controls TabBar（更轻量、可控样式）。
// 当前激活 Tab 底部蓝色高亮，点击切换 currentTabIndex。
//
// 用法：
//   TabBar {
//       id: tabBar
//       tabs: ["概览", "变更", "检查", "文档", "变量表"]
//       onCurrentTabChanged: console.log("切换到 Tab", currentIndex)
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property var tabs: []  // 字符串数组
    property int currentTabIndex: 0

    // ── 信号 ────────────────────────────────────────────
    signal currentTabChanged(int index)

    color: Theme.surface
    implicitHeight: 40
    implicitWidth: 600

    // 底部分隔线
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }

    // 当前 Tab 下方高亮条
    Rectangle {
        height: 3
        color: Theme.primary
        y: parent.height - 3

        x: tabRepeater.count > 0 ? tabRepeater.itemAt(root.currentTabIndex).x : 0
        width: tabRepeater.count > 0 ? tabRepeater.itemAt(root.currentTabIndex).width : 0

        Behavior on x { NumberAnimation { duration: 120 } }
        Behavior on width { NumberAnimation { duration: 120 } }
    }

    // ── Tab 按钮组 ──────────────────────────────────────
    RowLayout {
        id: tabRow
        anchors.fill: parent
        spacing: 0

        Repeater {
            id: tabRepeater
            model: root.tabs

            Rectangle {
                id: tabItem
                Layout.preferredWidth: tabText.implicitWidth + 32
                Layout.fillHeight: true
                color: "transparent"

                property bool isActive: index === root.currentTabIndex

                Text {
                    id: tabText
                    anchors.centerIn: parent
                    text: modelData
                    color: tabItem.isActive ? Theme.primary : Theme.textSecondary
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: tabItem.isActive
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (index !== root.currentTabIndex) {
                            root.currentTabIndex = index
                            root.currentTabChanged(index)
                        }
                    }
                }
            }
        }
    }
}
