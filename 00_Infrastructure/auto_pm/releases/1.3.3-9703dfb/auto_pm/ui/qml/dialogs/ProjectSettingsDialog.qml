// ProjectSettingsDialog.qml - 项目设置对话框（V0.6.0 W3-S12）
//
// 显示和编辑项目设置：版本号/阶段/技术栈/业务线/路径

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false

    // 项目设置字段
    property string projectId: ""
    property string projectName: ""
    property string version: "0.1.0"
    property string phase: "developing"
    property string stack: "python"
    property string businessLine: "SW"
    property string projectPath: ""

    // ── 信号 ────────────────────────────────────────────
    signal saved()
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.4
        visible: root._isOpen
        MouseArea { anchors.fill: parent; onClicked: {} }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 560
        height: 440
        color: Theme.background
        radius: Theme.radiusLg
        border.color: Theme.border
        border.width: 1
        visible: root._isOpen

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                color: Theme.primary
                Text {
                    anchors.centerIn: parent
                    text: "项目设置（" + root.projectId + "）"
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Theme.spacingLg
                spacing: Theme.spacingSm

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "项目名称"; width: 100; color: Theme.textSecondary }
                    TextField {
                        Layout.fillWidth: true
                        text: root.projectName
                        onTextChanged: root.projectName = text
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "版本号"; width: 100; color: Theme.textSecondary }
                    TextField {
                        Layout.fillWidth: true
                        text: root.version
                        onTextChanged: root.version = text
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "阶段"; width: 100; color: Theme.textSecondary }
                    ComboBox {
                        model: ["developing", "commissioning", "production", "archived"]
                        currentIndex: ["developing", "commissioning", "production", "archived"].indexOf(root.phase)
                        onActivated: root.phase = currentText
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "技术栈"; width: 100; color: Theme.textSecondary }
                    ComboBox {
                        model: ["python", "plc", "unknown"]
                        currentIndex: ["python", "plc", "unknown"].indexOf(root.stack)
                        onActivated: root.stack = currentText
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "业务线"; width: 100; color: Theme.textSecondary }
                    ComboBox {
                        model: ["SW", "DJ", "ZD", "XT", "WX"]
                        currentIndex: ["SW", "DJ", "ZD", "XT", "WX"].indexOf(root.businessLine)
                        onActivated: root.businessLine = currentText
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "项目路径"; width: 100; color: Theme.textSecondary }
                    Text {
                        Layout.fillWidth: true
                        text: root.projectPath
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeSm
                        elide: Text.ElideMiddle
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: Theme.surface
                Rectangle {
                    anchors.top: parent.top
                    anchors.fill: parent
                    height: 1
                    color: Theme.border
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    Item { Layout.fillWidth: true }
                    PrimaryButton {
                        text: "取消"
                        type: "ghost"
                        Layout.preferredWidth: 80
                        onClicked: { root._isOpen = false; root.cancelled() }
                    }
                    PrimaryButton {
                        text: "保存"
                        type: "primary"
                        Layout.preferredWidth: 80
                        onClicked: { root._isOpen = false; root.saved() }
                    }
                }
            }
        }
    }
}
