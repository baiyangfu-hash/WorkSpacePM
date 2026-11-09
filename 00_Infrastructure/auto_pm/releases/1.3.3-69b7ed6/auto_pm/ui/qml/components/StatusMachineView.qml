// StatusMachineView.qml - 9 步状态机视图（V0.6.0 W3-S3）
//
// 横向展示变更单的 9 步状态流转，当前状态高亮。
// 状态：draft → submitted → reviewing → approved → implementing →
//       verifying → closed / rejected / refused
//
// 用法：
//   StatusMachineView {
//       currentStatus: "implementing"
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string currentStatus: "draft"  // 当前状态
    property var statusOrder: [
        "draft", "submitted", "reviewing", "approved",
        "implementing", "verifying", "closed"
    ]
    property var statusLabels: ({
        "draft": "草稿",
        "submitted": "已提交",
        "reviewing": "审核中",
        "approved": "已批准",
        "implementing": "实施中",
        "verifying": "验证中",
        "closed": "已关闭",
        "rejected": "已驳回",
        "refused": "已拒绝"
    })

    // ── 视觉样式 ────────────────────────────────────────
    color: Theme.surface
    border.color: Theme.border
    border.width: 1
    radius: Theme.radiusMd
    implicitWidth: 800
    implicitHeight: 80

    // ── 状态颜色映射 ────────────────────────────────────
    function _statusColor(status: string, isCurrent: bool): color {
        if (isCurrent) return Theme.primary
        if (status === "closed") return Theme.success
        if (status === "rejected" || status === "refused") return Theme.error
        return Theme.textMuted
    }

    function _statusIndex(status: string): int {
        for (let i = 0; i < root.statusOrder.length; i++) {
            if (root.statusOrder[i] === status) return i
        }
        return -1
    }

    function _isCompleted(status: string): bool {
        const currentIdx = _statusIndex(root.currentStatus)
        const statusIdx = _statusIndex(status)
        return statusIdx >= 0 && currentIdx >= 0 && statusIdx < currentIdx
    }

    // ── 内容区 ──────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingXs

        Text {
            text: "状态流转（当前: " + (root.statusLabels[root.currentStatus] || root.currentStatus) + "）"
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
            color: Theme.textPrimary
            Layout.fillWidth: true
        }

        // 状态节点链
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Repeater {
                model: root.statusOrder

                RowLayout {
                    spacing: 0

                    // 状态徽标
                    Rectangle {
                        width: 90
                        height: 32
                        radius: Theme.radiusSm
                        color: _isCompleted(modelData)
                            ? Theme.success
                            : (modelData === root.currentStatus
                                ? Theme.primary
                                : Theme.surface)
                        border.color: _statusColor(modelData, modelData === root.currentStatus)
                        border.width: modelData === root.currentStatus ? 2 : 1

                        Text {
                            anchors.centerIn: parent
                            text: root.statusLabels[modelData] || modelData
                            color: (_isCompleted(modelData) || modelData === root.currentStatus)
                                ? "white"
                                : Theme.textSecondary
                            font.pixelSize: Theme.fontSizeXs
                            font.bold: modelData === root.currentStatus
                        }
                    }

                    // 流转箭头（除最后一个节点外）
                    Text {
                        visible: index < root.statusOrder.length - 1
                        text: _isCompleted(root.statusOrder[index + 1]) ? "→" : "·"
                        font.pixelSize: Theme.fontSizeMd
                        color: _isCompleted(root.statusOrder[index + 1])
                            ? Theme.success
                            : Theme.textMuted
                        Layout.alignment: Qt.AlignVCenter
                        Layout.leftMargin: 2
                        Layout.rightMargin: 2
                    }
                }
            }
        }
    }
}
