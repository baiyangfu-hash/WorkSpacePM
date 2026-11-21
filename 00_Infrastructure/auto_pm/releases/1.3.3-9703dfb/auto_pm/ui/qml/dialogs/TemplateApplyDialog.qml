// TemplateApplyDialog.qml - 模板应用对话框（M4 CHG-115）
//
// 列出可用模板，选择后应用到指定项目
// 调用 systemBridge.applyTemplate() 执行

import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string projectId: ""
    property string projectName: ""
    property var templates: []
    property string selectedTemplate: ""
    property bool applying: false

    // 信号
    signal templateApplied(string projectId, string templateName)
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 998

    function open(pid, pname) {
        root.projectId = pid
        root.projectName = pname
        root.selectedTemplate = ""
        root.applying = false
        // 加载模板列表
        if (typeof systemBridge !== "undefined" && systemBridge !== null) {
            if (typeof systemBridge.listTemplates === "function") {
                root.templates = systemBridge.listTemplates()
                if (root.templates.length > 0) {
                    root.selectedTemplate = root.templates[0]
                }
            } else {
                root.templates = []
            }
        }
        root._isOpen = true
    }

    function close() {
        root._isOpen = false
    }

    // 遮罩层（阻断底部点击）
    Rectangle {
        anchors.fill: parent
        color: "#b3000000"
        MouseArea {
            anchors.fill: parent
            onClicked: {
                if (!root.applying) {
                    root.cancelled()
                }
            }
        }
    }

    // 对话框主体（深色实底磨砂拟物）
    GlassPanel {
        width: 500
        height: Math.min(540, columnLayout.implicitHeight + Theme.spacingXl * 2)
        anchors.centerIn: parent
        radius: Theme.radiusLg

        ColumnLayout {
            id: columnLayout
            anchors.fill: parent
            anchors.margins: Theme.spacingXl
            spacing: Theme.spacingMd

            // 标题
            RowLayout {
                spacing: Theme.spacingSm
                Text {
                    text: "📑"
                    font.pixelSize: Theme.fontSizeXl
                }
                Text {
                    text: "应用模板到: " + (root.projectName || root.projectId)
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    Layout.fillWidth: true
                }
            }

            Text {
                text: "选择标准工程模板，将规范化自动区文档与初始结构。现有自定义业务文件将安全保留。"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            // 模板列表
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: 220
                color: "#0b1120"
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1
                clip: true

                ListView {
                    id: templateList
                    anchors.fill: parent
                    anchors.margins: 4
                    spacing: 4
                    model: root.templates
                    clip: true

                    delegate: Rectangle {
                        width: templateList.width
                        height: 44
                        color: root.selectedTemplate === modelData ? Qt.rgba(99/255, 102/255, 241/255, 0.2) : (itemMouseArea.containsMouse ? Qt.rgba(1, 1, 1, 0.05) : "transparent")
                        border.color: root.selectedTemplate === modelData ? Theme.primary : "transparent"
                        border.width: 1
                        radius: Theme.radiusSm

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.spacingMd
                            anchors.rightMargin: Theme.spacingMd
                            spacing: Theme.spacingSm

                            Text {
                                text: "📦"
                                font.pixelSize: Theme.fontSizeMd
                            }

                            Text {
                                text: modelData
                                color: root.selectedTemplate === modelData ? "#ffffff" : Theme.textPrimary
                                font.pixelSize: Theme.fontSizeMd
                                font.bold: root.selectedTemplate === modelData
                                Layout.fillWidth: true
                            }

                            Text {
                                visible: root.selectedTemplate === modelData
                                text: "✓ 已选"
                                color: Theme.primary
                                font.pixelSize: Theme.fontSizeSm
                                font.bold: true
                            }
                        }

                        MouseArea {
                            id: itemMouseArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectedTemplate = modelData
                        }
                    }
                }

                // 空状态
                ColumnLayout {
                    anchors.centerIn: parent
                    visible: root.templates.length === 0
                    spacing: Theme.spacingSm

                    Text {
                        text: "🔍"
                        font.pixelSize: 28
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Text {
                        text: "未找到可用的项目模板"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeMd
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }

            // 底部按钮栏
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingMd
                spacing: Theme.spacingMd

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "取消"
                    type: "ghost"
                    Layout.preferredWidth: 90
                    enabled: !root.applying
                    onClicked: root.cancelled()
                }

                PrimaryButton {
                    text: "应用模板"
                    type: "primary"
                    loading: root.applying
                    Layout.preferredWidth: 110
                    enabled: root.selectedTemplate !== "" && !root.applying
                    onClicked: {
                        if (typeof systemBridge === "undefined" || systemBridge === null) return
                        root.applying = true
                        applyTimer.restart()
                    }
                }
            }
        }
    }

    Timer {
        id: applyTimer
        interval: 100
        repeat: false
        onTriggered: {
            try {
                var result = systemBridge.applyTemplate(root.projectId, root.selectedTemplate)
                if (result && result.success) {
                    console.log("[QML] TemplateApplyDialog: 模板应用成功")
                    root.templateApplied(root.projectId, root.selectedTemplate)
                } else {
                    console.warn("[QML] TemplateApplyDialog: 模板应用失败 -", result ? result.message : "")
                }
            } finally {
                root.applying = false
                root.close()
            }
        }
    }
}