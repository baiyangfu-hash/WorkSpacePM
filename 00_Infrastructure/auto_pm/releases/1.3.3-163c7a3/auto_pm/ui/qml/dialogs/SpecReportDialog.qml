// SpecReportDialog.qml - 规范报告生成对话框（M5 CHG-120）
//
// 生成规范元数据汇总报告（markdown/json 格式），复用后端 ReportService
// 调用 specBridge.generateSpecReport(fmt)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string fmt: "markdown"
    property var reportResult: null
    property bool isExecuting: false

    // 信号
    signal generated()
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 999

    function open() {
        root._isOpen = true
        root.reportResult = null
        root.isExecuting = false
        root.fmt = "markdown"
        fmtCombo.currentIndex = 0
    }

    function close() {
        root._isOpen = false
    }

    // 格式选项模型
    ListModel {
        id: fmtModel
        ListElement { fmtId: "markdown"; fmtName: "Markdown（.md，含表格+Mermaid 图）" }
        ListElement { fmtId: "json"; fmtName: "JSON（.json，原始注册表数据）" }
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
        width: Math.min(640, parent.width - 48)
        height: Math.min(600, parent.height - 48)

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 16

            // 标题栏
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Text {
                    text: "📊 规范报告生成"
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
                text: "根据 spec_registry.json 生成规范元数据汇总报告，覆盖现有报告文件。Markdown 格式含总览/域分布/替代关系图/YAML 清单，JSON 格式为原始注册表数据。"
                font.pixelSize: 12
                color: Theme.textSecondary
                wrapMode: Text.Wrap
            }

            // 格式选择
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "输出格式:"
                    font.pixelSize: 13
                    color: Theme.textPrimary
                    Layout.preferredWidth: 72
                }

                ComboBox {
                    id: fmtCombo
                    Layout.fillWidth: true
                    model: fmtModel
                    textRole: "fmtName"
                    valueRole: "fmtId"
                    currentIndex: 0

                    onActivated: {
                        root.fmt = currentValue
                        root.reportResult = null
                    }
                }
            }

            // 提示信息
            Text {
                Layout.fillWidth: true
                text: "⚠️ 此操作将覆盖现有报告文件。Markdown 报告含规范总数/生命周期分布/按域分布/类型前缀分布/替代关系图/完整 YAML 元数据清单。"
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
                visible: root.reportResult !== null

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 8

                        // 成功状态
                        Text {
                            text: root.reportResult && root.reportResult.fmt
                                ? "✅ 报告生成成功"
                                : ""
                            font.pixelSize: 14
                            font.bold: true
                            color: Theme.success
                            visible: root.reportResult !== null && root.reportResult.fmt
                        }

                        // 失败状态
                        Text {
                            text: root.reportResult && root.reportResult.message && !root.reportResult.fmt
                                ? "❌ 生成失败: " + root.reportResult.message
                                : ""
                            font.pixelSize: 13
                            color: Theme.error
                            wrapMode: Text.Wrap
                            visible: root.reportResult !== null && root.reportResult.message && !root.reportResult.fmt
                            Layout.fillWidth: true
                        }

                        // 输出格式
                        Text {
                            text: root.reportResult && root.reportResult.fmt
                                ? "输出格式: " + root.reportResult.fmt
                                : ""
                            font.pixelSize: 12
                            color: Theme.textPrimary
                            visible: root.reportResult !== null && root.reportResult.fmt
                        }

                        // 输出路径
                        Text {
                            text: root.reportResult && root.reportResult.output_path
                                ? "📄 输出路径: " + root.reportResult.output_path
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            visible: root.reportResult !== null && root.reportResult.output_path
                            Layout.fillWidth: true
                        }

                        // 文件大小
                        Text {
                            text: root.reportResult && root.reportResult.file_size !== undefined
                                ? "💾 文件大小: " + (root.reportResult.file_size / 1024).toFixed(2) + " KB (" + root.reportResult.file_size + " 字符)"
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            visible: root.reportResult !== null && root.reportResult.file_size !== undefined
                        }

                        // 报告内容预览
                        Text {
                            text: root.reportResult && root.reportResult.content
                                ? "📝 报告内容预览（前 2000 字符）:"
                                : ""
                            font.pixelSize: 12
                            font.bold: true
                            color: Theme.textPrimary
                            visible: root.reportResult !== null && root.reportResult.content
                        }

                        Text {
                            text: root.reportResult && root.reportResult.content
                                ? root.reportResult.content.substring(0, 2000) + (root.reportResult.content.length > 2000 ? "\n\n... (已截断，完整内容见输出文件)" : "")
                                : ""
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            wrapMode: Text.Wrap
                            visible: root.reportResult !== null && root.reportResult.content
                            Layout.fillWidth: true
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
                    text: "生成报告"
                    icon: "📊"
                    type: "primary"
                    Layout.preferredWidth: 110
                    loading: root.isExecuting
                    enabled: !root.isExecuting
                    onClicked: {
                        root.isExecuting = true
                        var res = specBridge.generateSpecReport(root.fmt)
                        root.reportResult = res
                        root.isExecuting = false
                        if (res && res.fmt) {
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
