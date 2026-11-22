// TemplateView.qml - V0.8.0 Phase 2 模板管理（CHG-091）
//
// 模板卡片列表 + 更新项目按钮，对应 QWidget 的 template_page.py
//   ┌──────────────────────────────────────────────┐
//   │🏭 plc-standard             [更新项目]       │
//   │v1.0 | 技术栈: PLC | 使用项目: 3             │
//   │PLC 标准项目模板                              │
//   └──────────────────────────────────────────────┘
//
// 数据流：systemBridge.listTemplates() → 循环 systemBridge.getTemplateDetail(name) → 卡片渲染
// 三重守卫：typeof systemBridge === "undefined" || systemBridge === null || !systemBridge.hasService
//
// 更新项目按钮：Phase 2 显示 "Copier 增量更新功能将在 V0.9 实现" 提示

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 公开属性 ────────────────────────────────────────
    property string currentProjectId: ""  // M5: 由 main.qml 绑定，用于 applyTemplate

    // ── 信号 ────────────────────────────────────────────
    signal backToProjectList()

    // ── 内部数据模型 ────────────────────────────────────
    ListModel { id: templatesModel }
    property string errorMessage: ""
    property string selectedTemplate: ""
    property string applyResultMessage: ""  // M5: applyTemplate 结果消息

    // ── 加载数据 ────────────────────────────────────────
    function loadData() {
        if (typeof systemBridge === "undefined" || systemBridge === null || !systemBridge.hasService) {
            console.warn("[QML] TemplateView: TemplateService 未启用")
            errorMessage = "TemplateService 未启用"
            templatesModel.clear()
            return
        }
        errorMessage = ""
        var names = systemBridge.listTemplates()
        templatesModel.clear()
        for (var i = 0; i < names.length; i++) {
            var detail = systemBridge.getTemplateDetail(names[i])
            if (detail && !detail.error) {
                templatesModel.append(detail)
            }
        }
    }

    // ── 顶部导航 ────────────────────────────────────────
    Rectangle {
        id: navBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 88
        color: Theme.surface

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Text {
                    text: "📑 模板管理"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "刷新"
                    onClicked: loadData()
                }

                PrimaryButton {
                    text: "返回"
                    type: "ghost"
                    onClicked: root.backToProjectList()
                }
            }

            Text {
                text: "📋" + templatesModel.count + " 个可用 Copier 模板"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }
        }
    }

    // ── 错误状态 ────────────────────────────────────────
    Text {
        visible: errorMessage !== ""
        anchors.centerIn: parent
        text: "❌" + errorMessage
        color: Theme.error
        font.pixelSize: Theme.fontSizeMd
    }

    // ── 空状态 ─────────────────────────────────────────
    Text {
        visible: errorMessage === "" && templatesModel.count === 0
        anchors.centerIn: parent
        text: "暂无可用模板"
        color: Theme.textMuted
        font.pixelSize: Theme.fontSizeLg
    }

    // ── 模板列表（ScrollView + ColumnLayout）────────────
    ScrollView {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: navBar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacingMd
        visible: errorMessage === "" && templatesModel.count > 0
        clip: true

        ListView {
            model: templatesModel
            spacing: Theme.spacingMd
            delegate: templateCard
        }
    }

    // ── 模板卡片组件 ────────────────────────────────────
    Component {
        id: templateCard

        Rectangle {
            width: ListView.view ? ListView.view.width : 600
            height: cardLayout.implicitHeight + 2 * Theme.spacingMd
            color: Theme.surface
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            // hover 效果
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.ArrowCursor
                onEntered: parent.border.color = Theme.primary
                onExited: parent.border.color = Theme.border
            }

            ColumnLayout {
                id: cardLayout
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingXs

                // 第一行：图标 + 模板名称
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm

                    Text {
                        text: {
                            var s = model.stack || "unknown"
                            if (s === "plc") return "🏭"
                            if (s === "python") return "🐍"
                            return "📦"
                        }
                        font.pixelSize: Theme.fontSizeLg
                    }

                    Text {
                        text: model.name || ""
                        font.pixelSize: Theme.fontSizeLg
                        font.bold: true
                        color: Theme.textPrimary
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    PrimaryButton {
                        text: "应用模板到项目"
                        onClicked: {
                            root.selectedTemplate = model.name
                            root.applyResultMessage = ""
                            updateDialog.open()
                        }
                    }
                }

                // 第二行：版本 | 技术栈 | 使用项目数
                Text {
                    Layout.fillWidth: true
                    text: {
                        var stackLabel = "未分类"
                        if (model.stack === "plc") stackLabel = "PLC"
                        else if (model.stack === "python") stackLabel = "Python"
                        return (model.version || "v1.0")
                            + " | 技术栈: " + stackLabel
                            + " | 使用项目: " + (model.usage_count || 0)
                    }
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                }

                // 第三行：描述
                Text {
                    Layout.fillWidth: true
                    text: model.description || "—"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textPrimary
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    // ── 更新项目确认对话框 ──────────────────────────────
    Dialog {
        id: updateDialog
        title: "应用模板到项目"
        dialogWidth: 420
        dialogHeight: 220
        showButtons: false
        _isOpen: false

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Text {
                Layout.fillWidth: true
                text: "模板: " + root.selectedTemplate
                font.pixelSize: Theme.fontSizeMd
                font.bold: true
                color: Theme.textPrimary
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: root.currentProjectId ?
                          "目标项目: " + root.currentProjectId :
                          "⚠️ 未选择项目（请先在项目列表中点击一个项目）"
                font.pixelSize: Theme.fontSizeSm
                color: root.currentProjectId ? Theme.textSecondary : Theme.error
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                visible: root.applyResultMessage !== ""
                text: root.applyResultMessage
                font.pixelSize: Theme.fontSizeSm
                color: root.applyResultMessage.startsWith("✅") ? Theme.success :
                       (root.applyResultMessage.startsWith("❌") ? Theme.error : Theme.textSecondary)
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "取消"
                    type: "ghost"
                    onClicked: updateDialog.close()
                }

                PrimaryButton {
                    text: "确认应用"
                    type: "primary"
                    enabled: root.currentProjectId !== "" &&
                             typeof systemBridge !== "undefined" && systemBridge !== null && systemBridge.hasService
                    onClicked: {
                        var res = systemBridge.applyTemplate(root.currentProjectId, root.selectedTemplate)
                        if (res && res.success) {
                            root.applyResultMessage = "✅ 模板应用成功（项目: " + (res.project_id || "") + "）"
                        } else if (res && res.message) {
                            root.applyResultMessage = "❌ 失败: " + res.message
                        } else {
                            root.applyResultMessage = "❌ 未知失败"
                        }
                    }
                }
            }
        }
    }

    Component.onCompleted: loadData()
}

