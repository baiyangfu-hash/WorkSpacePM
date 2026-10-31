// AboutDialog.qml - 关于/帮助对话框（V0.6.0 W3-S15）
//
// 显示应用版本、技术栈、依赖项、版权信息。

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false

    // 应用信息
    property string appVersion: "1.0.0"
    property string appName: "auto-pm"
    property string description: "自动化项目管理工具"
    property string techStack: "Python 3.11+ / PySide6 / QML"
    property string license: "MIT"
    property string copyright: "© 2026 Auto-PM Team"

    // ── 信号 ────────────────────────────────────────────
    signal closed()

    function open() {
        root._isOpen = true
    }

    function close() {
        root._isOpen = false
        root.closed()
    }

    visible: _isOpen
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.4
        visible: root._isOpen
        MouseArea { anchors.fill: parent; onClicked: { root._isOpen = false; root.closed() } }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 480
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

            // 标题栏
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                color: Theme.primary
                Text {
                    anchors.centerIn: parent
                    text: "关于"
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            // 内容区
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Theme.spacingLg
                spacing: Theme.spacingMd

                // 应用图标 + 名称
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMd

                    Rectangle {
                        width: 64
                        height: 64
                        radius: 12
                        color: Theme.primary
                        Text {
                            anchors.centerIn: parent
                            text: "📋"
                            font.pixelSize: 36
                        }
                    }

                    ColumnLayout {
                        spacing: 2
                        Text {
                            text: root.appName
                            font.pixelSize: Theme.fontSizeXxl
                            font.bold: true
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "V" + root.appVersion
                            font.pixelSize: Theme.fontSizeMd
                            color: Theme.textSecondary
                        }
                        Text {
                            text: root.description
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textSecondary
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.border
                }

                // 技术信息
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingXs

                    Text {
                        text: "技术栈"
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: true
                        color: Theme.textPrimary
                    }
                    Text {
                        text: root.techStack
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }
                }

                // 版权信息
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingXs

                    Text {
                        text: root.copyright
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }
                    Text {
                        text: "License: " + root.license
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }
                }

                Item { Layout.fillHeight: true }

                // 帮助链接
                Text {
                    text: "📘 文档 · 🐛 报告问题 · 💬 反馈"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.primary
                    Layout.alignment: Qt.AlignHCenter
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
                        type: "primary"
                        Layout.preferredWidth: 80
                        onClicked: { root._isOpen = false; root.closed() }
                    }
                }
            }
        }
    }
}
