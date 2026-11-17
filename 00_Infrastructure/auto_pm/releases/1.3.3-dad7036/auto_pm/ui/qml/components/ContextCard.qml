// ContextCard.qml - 当前项目上下文卡片（对齐原型 V7 .context-card）
//
// CHG-SCPT-2026-102 T3：三轨道导航 Active Project 区域顶部上下文卡片
//
// 显示当前选中项目的 ID / 名称 / 阶段 / 技术栈徽标
// 未选项目时整体置灰（opacity:0.4），点击 emit clicked() 信号
//
// 数据来源：由 main.qml 传入 projectId/projectName/phase/stack 属性
// （T4 简化决策：不调 workbench_bridge.getActiveProjectContext()，避免新增 Slot）
//
// 用法：
//   ContextCard {
//       projectId: "SW-2026-008"
//       projectName: "auto-pm 自动化项目管理工具"
//       phase: "developing"
//       stack: "python"
//       onClicked: currentPage = "workspace"
//   }
import QtQuick
import QtQuick.Layouts
import "../theme"

GlassPanel {
    id: root

    // ── 公开属性（由 main.qml 绑定）─────────────────────
    property string projectId: ""
    property string projectName: ""
    property string phase: ""           // developing/commissioning/production/archived
    property string stack: ""           // plc/python/unknown
    property bool hasProject: false     // 由 main.qml 显式赋值（避免绑定循环）

    // ── 信号 ────────────────────────────────────────────
    signal clicked()

    // ── 视觉状态 ────────────────────────────────────────
    // 未选项目时整体置灰（对齐原型 V7 .context-card.disabled）
    opacity: hasProject ? 1.0 : 0.4
    implicitHeight: 88
    implicitWidth: 240

    // 鼠标点击区域
    MouseArea {
        anchors.fill: parent
        cursorShape: root.hasProject ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }

    // ── 内容布局 ────────────────────────────────────────
    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingMd

        // 项目图标（圆形 + 首字母）
        Rectangle {
            Layout.preferredWidth: 48
            Layout.preferredHeight: 48
            radius: width / 2
            color: Theme.primary
            opacity: root.hasProject ? 1.0 : 0.5

            Text {
                anchors.centerIn: parent
                text: root.projectName.charAt(0).toUpperCase() || "?"
                color: "white"
                font.pixelSize: Theme.fontSizeXl
                font.bold: true
            }
        }

        // 项目信息列
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 2

            // 项目名称
            Text {
                text: root.hasProject ? root.projectName : "未选择项目"
                font.pixelSize: Theme.fontSizeMd
                font.bold: true
                color: Theme.textPrimary
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            // 项目 ID
            Text {
                text: root.hasProject ? root.projectId : "点击项目列表选择"
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textMuted
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            // 徽标行：阶段 + 技术栈
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingXs
                visible: root.hasProject

                // 阶段徽标
                Rectangle {
                    visible: root.phase !== ""
                    Layout.preferredHeight: 18
                    implicitWidth: phaseText.implicitWidth + 12
                    radius: height / 2
                    color: Qt.rgba(1, 1, 1, 0.08)

                    Text {
                        id: phaseText
                        anchors.centerIn: parent
                        text: root.phase
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSizeXs
                    }
                }

                // 技术栈徽标
                Rectangle {
                    visible: root.stack !== ""
                    Layout.preferredHeight: 18
                    implicitWidth: stackText.implicitWidth + 12
                    radius: height / 2
                    color: root.stack === "python" ? Theme.badgePython :
                           (root.stack === "plc" ? Theme.badgePlc : Theme.badgeUnknown)

                    Text {
                        id: stackText
                        anchors.centerIn: parent
                        text: root.stack.toUpperCase()
                        color: "white"
                        font.pixelSize: Theme.fontSizeXs
                        font.bold: true
                    }
                }

                Item { Layout.fillWidth: true }
            }
        }
    }
}
