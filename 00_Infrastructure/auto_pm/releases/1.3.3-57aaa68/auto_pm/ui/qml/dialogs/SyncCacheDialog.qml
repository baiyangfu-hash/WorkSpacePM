// SyncCacheDialog.qml - 同步缓存对话框（V0.6.0 W3-S13）
//
// 显示同步缓存进度，支持后台执行同步任务。
// 进度条 + 状态文本 + 实时日志。

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property real progress: 0.0  // 0.0 ~ 1.0
    property string statusText: "准备同步..."
    property var logLines: []
    property bool isRunning: false

    // ── 信号 ────────────────────────────────────────────
    signal syncStarted()
    signal syncCompleted(bool success)
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
        height: 400
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
                    text: "同步缓存"
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Theme.spacingLg
                spacing: Theme.spacingMd

                // 状态文本
                Text {
                    text: root.statusText
                    font.pixelSize: Theme.fontSizeMd
                    color: Theme.textPrimary
                    Layout.fillWidth: true
                }

                // 进度条
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 12
                    color: Theme.border
                    radius: 6

                    Rectangle {
                        width: parent.width * root.progress
                        height: parent.height
                        color: Theme.primary
                        radius: 6

                        Behavior on width {
                            NumberAnimation { duration: 200 }
                        }
                    }
                }

                // 百分比
                Text {
                    text: Math.round(root.progress * 100) + "%"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.alignment: Qt.AlignRight
                }

                // 日志区
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: Theme.surface
                    radius: Theme.radiusMd
                    border.color: Theme.border

                    ScrollView {
                        anchors.fill: parent
                        TextArea {
                            readOnly: true
                            text: root.logLines.join("\n")
                            font.family: "Consolas"
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                        }
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
                        text: "关闭"
                        type: "ghost"
                        Layout.preferredWidth: 80
                        enabled: !root.isRunning
                        onClicked: { root._isOpen = false; root.cancelled() }
                    }
                    PrimaryButton {
                        text: "开始同步"
                        type: "primary"
                        Layout.preferredWidth: 100
                        enabled: !root.isRunning
                        onClicked: {
                            root.isRunning = true
                            root.syncStarted()
                        }
                    }
                }
            }
        }
    }

    // ── 公开方法：从外部更新进度 ────────────────────────
    function updateProgress(prog: real, status: string) {
        root.progress = prog
        root.statusText = status
        if (prog >= 1.0) {
            root.isRunning = false
            root.syncCompleted(true)
        }
    }

    function appendLog(line: string) {
        var newLines = root.logLines.slice()
        newLines.push(line)
        root.logLines = newLines
    }
}
