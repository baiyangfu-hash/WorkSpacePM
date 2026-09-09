// GlobalSettingsDialog.qml - 全局设置对话框（V0.6.0 W3-S17）
//
// 全局应用设置：工作空间路径/主题/语言/默认值等
// 设置可保存（持久化由 Python 端处理）

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false

    // 设置字段
    property string workspaceRoot: ""
    property string theme: "light"
    property string language: "zh-CN"
    property bool autoRefresh: true
    property int refreshInterval: 30
    property bool confirmBeforeDelete: true
    property bool enableDebugLog: false

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
        height: 480
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
                    text: "全局设置"
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            // 设置区（可滚动）
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    width: parent ? parent.width : 560
                    spacing: Theme.spacingMd

                    // ── 通用 ────────────────────────────────
                    Text {
                        text: "通用"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                        Layout.leftMargin: Theme.spacingLg
                        Layout.topMargin: Theme.spacingMd
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "工作空间"; width: 120; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.workspaceRoot
                            onTextChanged: root.workspaceRoot = text
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "主题"; width: 120; color: Theme.textSecondary }
                        ComboBox {
                            model: ["light", "dark", "auto"]
                            currentIndex: ["light", "dark", "auto"].indexOf(root.theme)
                            onActivated: root.theme = currentText
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "语言"; width: 120; color: Theme.textSecondary }
                        ComboBox {
                            model: ["zh-CN", "en-US"]
                            currentIndex: ["zh-CN", "en-US"].indexOf(root.language)
                            onActivated: root.language = currentText
                        }
                    }

                    // ── 自动刷新 ────────────────────────────
                    Text {
                        text: "数据刷新"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                        Layout.leftMargin: Theme.spacingLg
                        Layout.topMargin: Theme.spacingMd
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "自动刷新"; width: 120; color: Theme.textSecondary }
                        Switch {
                            checked: root.autoRefresh
                            onToggled: root.autoRefresh = checked
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "刷新间隔(秒)"; width: 120; color: Theme.textSecondary }
                        SpinBox {
                            value: root.refreshInterval
                            from: 5
                            to: 600
                            onValueModified: root.refreshInterval = value
                        }
                    }

                    // ── 安全 ────────────────────────────────
                    Text {
                        text: "安全"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                        Layout.leftMargin: Theme.spacingLg
                        Layout.topMargin: Theme.spacingMd
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "删除前确认"; width: 120; color: Theme.textSecondary }
                        Switch {
                            checked: root.confirmBeforeDelete
                            onToggled: root.confirmBeforeDelete = checked
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spacingLg
                        Layout.rightMargin: Theme.spacingLg
                        Text { text: "启用调试日志"; width: 120; color: Theme.textSecondary }
                        Switch {
                            checked: root.enableDebugLog
                            onToggled: root.enableDebugLog = checked
                        }
                    }

                    Item { Layout.preferredHeight: Theme.spacingLg }
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
