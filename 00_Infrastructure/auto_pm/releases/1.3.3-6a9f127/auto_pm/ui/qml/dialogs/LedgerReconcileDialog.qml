// LedgerReconcileDialog.qml - 台账对账对话框（M5 CHG-118）
//
// 扫描 CHG 文件 vs 版本变更台账，展示差异 + 自动修复
// 调用 changeBridge.reconcileLedger(projectId, autoFix)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string projectId: ""
    property var reconcileResult: null
    property bool isExecuting: false

    // 信号
    signal reconciled()
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 998

    function open(projectId) {
        root._isOpen = true
        root.projectId = projectId || ""
        root.reconcileResult = null
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
        width: Math.min(640, parent.width - 48)
        height: Math.min(560, parent.height - 48)

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // ── 标题栏 ────────────────────────────────
            RowLayout {
                Layout.fillWidth: true

                Text {
                    text: "📊 台账对账"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "✕"
                    type: "ghost"
                    Layout.preferredWidth: 36
                    onClicked: root.close()
                }
            }

            // ── 项目编号输入 ──────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Text {
                    text: "项目编号:"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                }

                TextField {
                    id: projectIdInput
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    text: root.projectId
                    placeholderText: "如 SW-2026-008"
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        color: Theme.glassBg
                        radius: Theme.radiusSm
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                    onTextChanged: root.projectId = text
                }
            }

            // ── 操作按钮 ──────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                PrimaryButton {
                    text: "🔍 仅对账"
                    type: "primary"
                    enabled: root.projectId !== "" && !root.isExecuting
                    Layout.preferredHeight: 36
                    onClicked: {
                        root.isExecuting = true
                        root.reconcileResult = changeBridge.reconcileLedger(root.projectId, false)
                        root.isExecuting = false
                    }
                }

                PrimaryButton {
                    text: "🔧 自动修复"
                    type: "ghost"
                    enabled: root.projectId !== "" && !root.isExecuting
                    Layout.preferredHeight: 36
                    onClicked: {
                        root.isExecuting = true
                        root.reconcileResult = changeBridge.reconcileLedger(root.projectId, true)
                        root.isExecuting = false
                        root.reconciled()
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    visible: root.isExecuting
                    text: "执行中..."
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textMuted
                }
            }

            // ── 结果展示区 ────────────────────────────
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    width: panel.width - Theme.spacingLg * 2
                    spacing: Theme.spacingSm

                    // 无结果占位
                    Text {
                        visible: root.reconcileResult === null
                        text: "点击「仅对账」扫描差异，或「自动修复」一键修复"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textMuted
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        topPadding: Theme.spacingXl
                    }

                    // 错误提示
                    Rectangle {
                        visible: root.reconcileResult !== null && root.reconcileResult.success === false
                        Layout.fillWidth: true
                        Layout.preferredHeight: 48
                        color: Qt.rgba(0.8, 0.2, 0.2, 0.15)
                        radius: Theme.radiusSm
                        border.color: Qt.rgba(0.8, 0.2, 0.2, 0.4)
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: (root.reconcileResult && root.reconcileResult.message) || "对账失败"
                            font.pixelSize: Theme.fontSizeSm
                            color: "#ff6666"
                        }
                    }

                    // 对账无差异
                    Rectangle {
                        visible: root.reconcileResult !== null && root.reconcileResult.is_clean === true && root.reconcileResult.success !== false
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56
                        color: Qt.rgba(0.2, 0.7, 0.3, 0.15)
                        radius: Theme.radiusSm
                        border.color: Qt.rgba(0.2, 0.7, 0.3, 0.4)
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "✅ 对账无差异\n" + (root.reconcileResult ? root.reconcileResult.summary : "")
                            font.pixelSize: Theme.fontSizeSm
                            color: "#66cc66"
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    // 摘要
                    Text {
                        visible: root.reconcileResult !== null && root.reconcileResult.is_clean === false && root.reconcileResult.success !== false
                        text: root.reconcileResult ? "📋 " + root.reconcileResult.summary : ""
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: true
                        color: Theme.textPrimary
                        Layout.fillWidth: true
                    }

                    // 缺失行
                    Text {
                        visible: root.reconcileResult !== null
                            && root.reconcileResult.missing_in_ledger
                            && root.reconcileResult.missing_in_ledger.length > 0
                        text: "🔴 台账缺失（CHG 文件存在但台账无记录）:"
                        font.pixelSize: Theme.fontSizeXs
                        font.bold: true
                        color: "#ff6666"
                        Layout.fillWidth: true
                    }

                    Repeater {
                        model: root.reconcileResult && root.reconcileResult.missing_in_ledger ? root.reconcileResult.missing_in_ledger : []
                        delegate: Text {
                            text: "  • " + modelData
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                            Layout.fillWidth: true
                        }
                    }

                    // 孤儿记录
                    Text {
                        visible: root.reconcileResult !== null
                            && root.reconcileResult.orphan_in_ledger
                            && root.reconcileResult.orphan_in_ledger.length > 0
                        text: "🟡 台账多余（孤儿记录，需人工审核）:"
                        font.pixelSize: Theme.fontSizeXs
                        font.bold: true
                        color: "#ffaa44"
                        Layout.fillWidth: true
                    }

                    Repeater {
                        model: root.reconcileResult && root.reconcileResult.orphan_in_ledger ? root.reconcileResult.orphan_in_ledger : []
                        delegate: Text {
                            text: "  • " + modelData
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                            Layout.fillWidth: true
                        }
                    }

                    // 状态不一致
                    Text {
                        visible: root.reconcileResult !== null
                            && root.reconcileResult.status_mismatches
                            && root.reconcileResult.status_mismatches.length > 0
                        text: "🟡 状态不一致（CHG 状态 vs 台账状态）:"
                        font.pixelSize: Theme.fontSizeXs
                        font.bold: true
                        color: "#ffaa44"
                        Layout.fillWidth: true
                    }

                    Repeater {
                        model: root.reconcileResult && root.reconcileResult.status_mismatches ? root.reconcileResult.status_mismatches : []
                        delegate: Text {
                            text: "  • " + modelData[0] + "  期望: " + modelData[1] + "  实际: " + modelData[2]
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                            Layout.fillWidth: true
                        }
                    }

                    // 修复标记
                    Rectangle {
                        visible: root.reconcileResult !== null
                            && root.reconcileResult.auto_fixed === true
                            && root.reconcileResult.success !== false
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        color: Qt.rgba(0.2, 0.5, 0.8, 0.15)
                        radius: Theme.radiusSm
                        border.color: Qt.rgba(0.2, 0.5, 0.8, 0.4)
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "🔧 已自动修复缺失行和状态不一致（孤儿记录保留人工审核）"
                            font.pixelSize: Theme.fontSizeXs
                            color: "#66aaff"
                        }
                    }
                }
            }

            // ── 底部按钮 ──────────────────────────────
            RowLayout {
                Layout.fillWidth: true

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "关闭"
                    type: "ghost"
                    Layout.preferredWidth: 80
                    onClicked: root.close()
                }
            }
        }
    }
}
