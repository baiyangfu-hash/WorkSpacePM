// SpecFrontmatterDialog.qml - 规范 Frontmatter 检查/修复对话框（M5 CHG-121）
//
// 检查规范文件的 frontmatter 完整性，可选自动修复（添加缺失的 frontmatter）
// 复用后端 FrontmatterService.preview()/apply()
// 调用 specBridge.checkSpecFrontmatter(autoFix)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property var checkResult: null
    property bool isExecuting: false

    // 信号
    signal checked()
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 999

    function open() {
        root._isOpen = true
        root.checkResult = null
        root.isExecuting = false
    }

    function close() {
        root._isOpen = false
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
        width: Math.min(700, parent.width - 48)
        height: Math.min(640, parent.height - 48)

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 16

            // 标题栏
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Text {
                    text: "🔍 规范 Frontmatter 检查"
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

            // 说明文字
            Text {
                Layout.fillWidth: true
                text: "检查规范文件的 frontmatter 完整性。缺失 frontmatter 的规范文件会被标记为 pending，可选择自动修复。"
                color: Theme.textSecondary
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }

            // 警告提示
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                color: "#33F59E0B"
                radius: 6
                visible: true

                Text {
                    anchors.centerIn: parent
                    text: "⚠️ 自动修复将修改规范文件（添加缺失的 YAML frontmatter），请谨慎操作"
                    color: "#F59E0B"
                    font.pixelSize: 11
                }
            }

            // 操作按钮
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                PrimaryButton {
                    text: "🔍 仅检查"
                    type: "primary"
                    enabled: !root.isExecuting
                    onClicked: {
                        root.isExecuting = true
                        root.checkResult = specBridge.checkSpecFrontmatter(false)
                        root.isExecuting = false
                        if (root.checkResult && root.checkResult.success !== false) {
                            root.checked()
                        }
                    }
                }

                PrimaryButton {
                    text: "🔧 检查并修复"
                    type: "ghost"
                    enabled: !root.isExecuting
                    onClicked: {
                        root.isExecuting = true
                        root.checkResult = specBridge.checkSpecFrontmatter(true)
                        root.isExecuting = false
                        if (root.checkResult && root.checkResult.success !== false) {
                            root.checked()
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "关闭"
                    type: "ghost"
                    Layout.preferredWidth: 80
                    onClicked: root.close()
                }
            }

            // 结果展示区
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.checkResult !== null

                ColumnLayout {
                    width: parent.width
                    spacing: 12

                    // 失败消息
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        color: "#33EF4444"
                        radius: 6
                        visible: root.checkResult && root.checkResult.success === false

                        Text {
                            anchors.centerIn: parent
                            text: root.checkResult ? ("❌ " + (root.checkResult.message || "检查失败")) : ""
                            color: "#EF4444"
                            font.pixelSize: 12
                        }
                    }

                    // 统计信息
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80
                        color: Theme.bgCard
                        radius: 8
                        visible: root.checkResult && root.checkResult.success !== false

                        GridLayout {
                            anchors.centerIn: parent
                            columns: 4
                            columnSpacing: 24
                            rowSpacing: 8

                            // 总数
                            ColumnLayout {
                                spacing: 2
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: root.checkResult ? root.checkResult.total_count : 0
                                    font.pixelSize: 20
                                    font.bold: true
                                    color: Theme.textPrimary
                                }
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "总数"
                                    font.pixelSize: 10
                                    color: Theme.textSecondary
                                }
                            }

                            // 待处理
                            ColumnLayout {
                                spacing: 2
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: root.checkResult ? root.checkResult.pending_count : 0
                                    font.pixelSize: 20
                                    font.bold: true
                                    color: "#F59E0B"
                                }
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "待处理"
                                    font.pixelSize: 10
                                    color: Theme.textSecondary
                                }
                            }

                            // 已跳过
                            ColumnLayout {
                                spacing: 2
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: root.checkResult ? root.checkResult.skipped_count : 0
                                    font.pixelSize: 20
                                    font.bold: true
                                    color: "#10B981"
                                }
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "已跳过"
                                    font.pixelSize: 10
                                    color: Theme.textSecondary
                                }
                            }

                            // 错误
                            ColumnLayout {
                                spacing: 2
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: root.checkResult ? root.checkResult.error_count : 0
                                    font.pixelSize: 20
                                    font.bold: true
                                    color: "#EF4444"
                                }
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "错误"
                                    font.pixelSize: 10
                                    color: Theme.textSecondary
                                }
                            }
                        }
                    }

                    // 修复统计（仅 auto_fix=True 时显示）
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        color: "#3310B981"
                        radius: 6
                        visible: root.checkResult && root.checkResult.auto_fixed === true

                        Text {
                            anchors.centerIn: parent
                            text: root.checkResult ? ("✅ 已修复 " + root.checkResult.modified_count + " 个规范文件的 frontmatter") : ""
                            color: "#10B981"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }

                    // 明细标题
                    Text {
                        text: "📋 检查明细"
                        font.pixelSize: 14
                        font.bold: true
                        color: Theme.textPrimary
                        visible: root.checkResult && root.checkResult.success !== false
                    }

                    // 明细列表
                    Repeater {
                        model: root.checkResult && root.checkResult.items ? root.checkResult.items : []

                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 60
                            color: Theme.bgCard
                            radius: 6
                            border.width: 1
                            border.color: {
                                var s = modelData.status
                                if (s === "pending") return "#F59E0B"
                                if (s === "error") return "#EF4444"
                                if (s === "applied") return "#10B981"
                                return Theme.borderSubtle
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8

                                // 状态图标
                                Text {
                                    text: {
                                        var s = modelData.status
                                        if (s === "pending") return "⏳"
                                        if (s === "error") return "❌"
                                        if (s === "applied") return "✅"
                                        if (s === "skipped") return "⏭️"
                                        return "❓"
                                    }
                                    font.pixelSize: 16
                                }

                                // spec_id + 状态
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Text {
                                        text: modelData.spec_id
                                        font.pixelSize: 13
                                        font.bold: true
                                        color: Theme.textPrimary
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: {
                                            var s = modelData.status
                                            var parts = []
                                            if (modelData.is_deprecated) parts.push("已弃用")
                                            if (modelData.has_frontmatter) parts.push("已有 frontmatter")
                                            if (!modelData.file_exists) parts.push("文件不存在")
                                            if (s === "pending") parts.push("待添加 frontmatter")
                                            if (s === "applied") parts.push("已添加 frontmatter")
                                            if (s === "error") parts.push("处理失败")
                                            return parts.join(" · ")
                                        }
                                        font.pixelSize: 10
                                        color: Theme.textSecondary
                                        elide: Text.ElideRight
                                    }
                                }

                                // 文件路径
                                Text {
                                    text: modelData.file_path
                                    font.pixelSize: 9
                                    color: Theme.textTertiary
                                    elide: Text.ElideMiddle
                                    Layout.maximumWidth: 200
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
