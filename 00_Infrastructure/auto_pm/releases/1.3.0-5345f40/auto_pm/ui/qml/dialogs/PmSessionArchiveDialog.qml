// PmSessionArchiveDialog.qml - PM_SESSION 归档对话框（M5 CHG-117）
//
// 归档 PM_SESSION 指定章节的早期内容到归档文件
// 调用 systemBridge.archivePmSession(section, keepRecent, dryRun)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string section: "8"
    property int keepRecent: 3
    property var archiveResult: null
    property bool isExecuting: false

    // 信号
    signal archived()
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 998

    function open(pid) {
        root._isOpen = true
        root.archiveResult = null
        root.isExecuting = false
    }

    function close() {
        root._isOpen = false
    }

    // 章节选项模型
    ListModel {
        id: sectionModel
        ListElement { sectionId: "6"; sectionName: "§6 实施记录（按行归档）" }
        ListElement { sectionId: "8"; sectionName: "§8 交接记录（按条目归档）" }
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
                    text: "📦 PM_SESSION 归档"
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
                text: "将指定章节的早期内容移动到归档文件，主文件保留最新内容。§8 支持条目级归档（保留最新 N 条 skill_handoff）。"
                font.pixelSize: 12
                color: Theme.textSecondary
                wrapMode: Text.Wrap
            }

            // 章节选择
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "归档章节:"
                    font.pixelSize: 13
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                ComboBox {
                    id: sectionCombo
                    Layout.fillWidth: true
                    model: sectionModel
                    textRole: "sectionName"
                    valueRole: "sectionId"
                    currentIndex: 1  // 默认 §8

                    onActivated: {
                        root.section = currentValue
                        // §8 默认保留 3 条，§6 默认保留 20 行
                        if (currentValue === "8") {
                            keepRecentSpin.value = 3
                        } else {
                            keepRecentSpin.value = 20
                        }
                        root.archiveResult = null
                    }
                }
            }

            // 保留数量
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: root.section === "8" ? "保留条目数:" : "保留行数:"
                    font.pixelSize: 13
                    color: Theme.textPrimary
                    Layout.preferredWidth: 80
                }

                SpinBox {
                    id: keepRecentSpin
                    Layout.fillWidth: true
                    from: 0
                    to: 100
                    value: 3
                    onValueModified: {
                        root.keepRecent = value
                        root.archiveResult = null
                    }
                }
            }

            // 提示信息
            Text {
                Layout.fillWidth: true
                text: root.section === "8"
                    ? "§8 条目级归档：保留最新 N 条 skill_handoff + 所有 current_state，旧条目移到归档文件"
                    : "§6 按行归档：保留最近 N 行内容，早期记录移到归档文件"
                font.pixelSize: 11
                color: Theme.textTertiary
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
                visible: root.archiveResult !== null

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: root.archiveResult && root.archiveResult.is_dry_run
                                ? "📋 预览结果（未实际修改）"
                                : "✅ 归档完成"
                            font.pixelSize: 14
                            font.bold: true
                            color: root.archiveResult && root.archiveResult.is_dry_run
                                ? Theme.warning
                                : Theme.success
                        }

                        Text {
                            text: root.archiveResult
                                ? "章节: §" + root.archiveResult.archived_sections.join(", ") + " " + root.archiveResult.section_title
                                : ""
                            font.pixelSize: 12
                            color: Theme.textPrimary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: root.archiveResult
                                ? "章节总行数: " + root.archiveResult.section_total_lines
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }

                        Text {
                            text: root.archiveResult
                                ? "归档行数: " + root.archiveResult.archived_line_count
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }

                        Text {
                            text: root.archiveResult
                                ? "保留: " + root.archiveResult.keep_recent + (root.section === "8" ? " 条" : " 行")
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }

                        Text {
                            text: root.archiveResult
                                ? "主文件行数: " + root.archiveResult.main_file_lines_before + " → " + root.archiveResult.main_file_lines_after
                                : ""
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }

                        Text {
                            text: root.archiveResult
                                ? "归档文件: " + root.archiveResult.archive_file
                                : ""
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            // 按钮区
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                PrimaryButton {
                    text: "预览"
                    type: "secondary"
                    Layout.preferredWidth: 80
                    loading: root.isExecuting
                    enabled: !root.isExecuting
                    onClicked: {
                        root.isExecuting = true
                        var res = systemBridge.archivePmSession(root.section, root.keepRecent, true)
                        root.archiveResult = res
                        root.isExecuting = false
                    }
                }

                PrimaryButton {
                    text: "执行归档"
                    type: "primary"
                    Layout.preferredWidth: 100
                    loading: root.isExecuting
                    enabled: !root.isExecuting && root.archiveResult !== null && root.archiveResult.is_dry_run
                    onClicked: {
                        root.isExecuting = true
                        var res = systemBridge.archivePmSession(root.section, root.keepRecent, false)
                        root.archiveResult = res
                        root.isExecuting = false
                        if (res && !res.is_dry_run) {
                            root.archived()
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
