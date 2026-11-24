// ImportProjectDialog.qml - 导入项目对话框（V0.6.0 W3-S14）
//
// 从外部路径导入现有项目到工作空间。
// 输入路径 → 检测项目标志 → 预览 → 确认导入。

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string projectPath: ""
    property string detectedId: ""
    property string detectedName: ""
    property string detectedStack: "unknown"
    property bool isDetecting: false

    // ── 信号 ────────────────────────────────────────────
    signal imported(string projectId, string projectPath)
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
        height: 380
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
                    text: "导入项目"
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

                // 项目路径输入
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "项目路径"; width: 80; color: Theme.textSecondary }
                    TextField {
                        Layout.fillWidth: true
                        placeholderText: "如 D:\\Projects\\MyProject"
                        text: root.projectPath
                        onTextChanged: root.projectPath = text
                    }
                    PrimaryButton {
                        text: "浏览..."
                        type: "ghost"
                        onClicked: {
                            // 实际浏览由 Python 端文件对话框处理
                        }
                    }
                }

                // 检测按钮
                PrimaryButton {
                    text: "检测项目"
                    type: "primary"
                    Layout.alignment: Qt.AlignHCenter
                    enabled: root.projectPath !== "" && !root.isDetecting
                    onClicked: {
                        root.isDetecting = true
                        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                            var res = workbenchBridge.detectProject(root.projectPath)
                            if (res && res.success) {
                                root.detectedId = res.project_id
                                root.detectedName = res.name
                                root.detectedStack = res.stack
                            } else {
                                root.detectedId = "无法识别"
                                root.detectedName = res ? res.message : "检测失败"
                                root.detectedStack = "unknown"
                            }
                        } else {
                            root.detectedId = "未初始化"
                            root.detectedName = "Bridge 服务未启用"
                            root.detectedStack = "unknown"
                        }
                        root.isDetecting = false
                    }
                }

                // 检测结果
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    color: Theme.surface
                    radius: Theme.radiusMd
                    border.color: Theme.border
                    visible: root.detectedId !== ""

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingMd
                        spacing: Theme.spacingXs

                        Text {
                            text: "检测结果："
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            color: Theme.textPrimary
                        }
                        Text { text: "项目 ID: " + root.detectedId; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
                        Text { text: "项目名称: " + root.detectedName; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
                        Text { text: "技术栈: " + root.detectedStack; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
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
                        text: "导入"
                        type: "primary"
                        Layout.preferredWidth: 80
                        enabled: root.detectedId !== "" && root.detectedId !== "待检测" && root.detectedId !== "无法识别" && root.detectedId !== "未初始化"
                        onClicked: {
                            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                                var res = workbenchBridge.importProject(root.projectPath)
                                if (res && res.success) {
                                    root.imported(res.project_id, root.projectPath)
                                } else {
                                    console.error("导入项目失败: " + JSON.stringify(res))
                                }
                            }
                            root._isOpen = false
                        }
                    }
                }
            }
        }
    }
}
