// SpecIndexDialog.qml - 规范索引生成对话框（M5 CHG-119）
//
// 生成规范索引文件（pm/plc/python 域），复用后端 IndexService
// 调用 specBridge.generateSpecIndex(domain)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string domain: "all"
    property var indexResult: null
    property bool isExecuting: false

    // 信号
    signal generated()
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 999

    function open() {
        root._isOpen = true
        root.indexResult = null
        root.isExecuting = false
        root.domain = "all"
        domainCombo.currentIndex = 0
    }

    function close() {
        root._isOpen = false
    }

    // 域选项模型
    ListModel {
        id: domainModel
        ListElement { domainId: "all"; domainName: "全部域 (pm + plc + python)" }
        ListElement { domainId: "pm"; domainName: "PM 域（项目管理规范）" }
        ListElement { domainId: "plc"; domainName: "PLC 域（PLC 技术栈规范）" }
        ListElement { domainId: "python"; domainName: "Python 域（Python 技术栈规范）" }
    }

    // 遮罩层
    Rectangle {
        anchors.fill: parent
        color: "#80000000"
        MouseArea {
            anchors.fill: parent
            onClicked: root.close()
        }
    }

    // 主体面板
    GlassPanel {
        id: panel
        anchors.centerIn: parent
        width: Math.min(560, parent.width - 48)
        height: Math.min(520, parent.height - 48)

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 16

            // 标题栏
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Text {
                    text: "📝 规范索引生成"
                    font.pixelSize: 18
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: "✕"
                    flat: true
                    onClicked: root.close()
                }
            }

            // 说明
            Text {
                Layout.fillWidth: true
                text: "根据 spec_registry.json 生成规范索引 Markdown 文件，覆盖现有索引文件。支持按域生成或全量生成。"
                font.pixelSize: 12
                color: Theme.textSecondary
                wrapMode: Text.Wrap
            }

            // 域选择
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "生成域:"
                    font.pixelSize: 13
                    color: Theme.textPrimary
                    Layout.preferredWidth: 60
                }

                ComboBox {
                    id: domainCombo
                    Layout.fillWidth: true
                    model: domainModel
                    textRole: "domainName"
                    valueRole: "domainId"
                    currentIndex: 0

                    onActivated: {
                        root.domain = currentValue
                        root.indexResult = null
                    }
                }
            }

            // 提示信息
            Text {
                Layout.fillWidth: true
                text: "⚠️ 此操作将覆盖现有索引文件。生成的索引文件包含规范 ID、文件名、版本、说明等信息。"
                font.pixelSize: 11
                color: Theme.warning
                wrapMode: Text.Wrap
            }

            // 结果展示区
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.backgroundTertiary
                radius: 6
                border.color: Theme.border
                border.width: 1
                visible: root.indexResult !== null

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 8

                        // 错误状态
                        Rectangle {
                            Layout.fillWidth: true
                            visible: root.indexResult && root.indexResult.errors && root.indexResult.errors.length > 0
                            color: "#33FF4444"
                            radius: 4
                            implicitHeight: errorLabel.implicitHeight + 12

                            Text {
                                id: errorLabel
                                anchors.fill: parent
                                anchors.margins: 6
                                text: root.indexResult ? "❌ 生成过程中有 " + root.indexResult.errors.length + " 个错误" : ""
                                font.pixelSize: 13
                                color: Theme.error
                                wrapMode: Text.Wrap
                            }
                        }

                        // 成功状态
                        Text {
                            text: root.indexResult && root.indexResult.errors && root.indexResult.errors.length === 0
                                ? "✅ 索引生成成功"
                                : (root.indexResult && root.indexResult.generated_files ? "⚠️ 部分成功" : "")
                            font.pixelSize: 14
                            font.bold: true
                            color: root.indexResult && root.indexResult.errors && root.indexResult.errors.length === 0
                                ? Theme.success
                                : Theme.warning
                            visible: root.indexResult !== null
                        }

                        // 生成域
                        Text {
                            text: root.indexResult ? "生成域: " + root.indexResult.domain : ""
                            font.pixelSize: 12
                            color: Theme.textPrimary
                            visible: root.indexResult !== null
                        }

                        // 生成文件数
                        Text {
                            text: root.indexResult && root.indexResult.generated_files
                                ? "已生成文件数: " + root.indexResult.generated_files.length
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            visible: root.indexResult !== null
                        }

                        // 生成文件列表
                        Text {
                            text: root.indexResult && root.indexResult.generated_files && root.indexResult.generated_files.length > 0
                                ? "📄 生成文件:"
                                : ""
                            font.pixelSize: 12
                            font.bold: true
                            color: Theme.textPrimary
                            visible: root.indexResult !== null && root.indexResult.generated_files && root.indexResult.generated_files.length > 0
                        }

                        Repeater {
                            model: root.indexResult && root.indexResult.generated_files ? root.indexResult.generated_files : []

                            Text {
                                Layout.leftMargin: 12
                                text: "  • " + modelData
                                font.pixelSize: 11
                                color: Theme.textTertiary
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }

                        // 错误列表
                        Text {
                            text: root.indexResult && root.indexResult.errors && root.indexResult.errors.length > 0
                                ? "❌ 错误列表:"
                                : ""
                            font.pixelSize: 12
                            font.bold: true
                            color: Theme.error
                            visible: root.indexResult !== null && root.indexResult.errors && root.indexResult.errors.length > 0
                        }

                        Repeater {
                            model: root.indexResult && root.indexResult.errors ? root.indexResult.errors : []

                            Text {
                                Layout.leftMargin: 12
                                text: "  • " + modelData
                                font.pixelSize: 11
                                color: Theme.error
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            // 按钮区
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "生成索引"
                    icon: "📝"
                    type: "primary"
                    Layout.preferredWidth: 110
                    loading: root.isExecuting
                    enabled: !root.isExecuting
                    onClicked: {
                        root.isExecuting = true
                        var res = specBridge.generateSpecIndex(root.domain)
                        root.indexResult = res
                        root.isExecuting = false
                        if (res && res.generated_files && res.generated_files.length > 0 && (!res.errors || res.errors.length === 0)) {
                            root.generated()
                        }
                    }
                }

                PrimaryButton {
                    text: "关闭"
                    type: "ghost"
                    Layout.preferredWidth: 80
                    enabled: !root.isExecuting
                    onClicked: root.close()
                }
            }
        }
    }
}
