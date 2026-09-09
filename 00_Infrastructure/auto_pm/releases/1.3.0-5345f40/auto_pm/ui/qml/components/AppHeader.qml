// AppHeader.qml — 顶部标题栏组件 V1.0.0
// 从 main.qml L122-L228 抽取
// 预留扩展: 未来新增操作按钮直接加到 RowLayout 中，不改 main.qml

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."
import "../theme"

Rectangle {
    id: appHeader

    // ── 公开属性
    property string appVersion: "V1.0.0"
    property string workspaceRoot: ""

    // ── 信号
    signal refreshRequested()

    // ── 外观
    height: 72
    color: Qt.rgba(0.02, 0.02, 0.09, 0.85)

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.glassBorder
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingLg
        anchors.rightMargin: Theme.spacingLg
        spacing: Theme.spacingMd

        // Logo
        Rectangle {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            radius: width / 2
            color: Theme.primary
            opacity: 0.9
            Text {
                anchors.centerIn: parent
                text: "A"
                color: "white"
                font.pixelSize: Theme.fontSizeXl
                font.bold: true
            }
        }

        ColumnLayout {
            spacing: 0
            Text { text: "auto-pm"; color: Theme.textPrimary; font.pixelSize: Theme.fontSizeLg; font.bold: true }
            Text { text: appHeader.appVersion; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
        }

        // 全局搜索
        TextField {
            Layout.fillWidth: true
            Layout.maximumWidth: 480
            Layout.preferredHeight: 36
            placeholderText: "搜索项目 / 变更 / 规范..."
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            background: Rectangle {
                color: Theme.glassBg
                radius: Theme.radiusMd
                border.color: Theme.glassBorder
                border.width: 1
            }
        }

        // 刷新按钮
        PrimaryButton {
            text: "🔄 刷新"
            type: "ghost"
            Layout.preferredHeight: 36
            onClicked: appHeader.refreshRequested()
        }

        // 工作空间路径
        Text {
            text: appHeader.workspaceRoot !== "" ? "📁 " + appHeader.workspaceRoot : ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeXs
            elide: Text.ElideRight
            Layout.maximumWidth: 240
        }
    }
}
