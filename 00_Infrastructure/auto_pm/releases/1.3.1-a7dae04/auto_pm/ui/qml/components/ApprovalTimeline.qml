// ApprovalTimeline.qml - 审批流转时间线（V0.6.0 W3-S1）
//
// Canvas 渲染的审批节点时间线，展示 §8 审批记录历史。
// 每个节点显示审批人/日期/结论，已通过节点绿色、未通过红色。
//
// 用法：
//   ApprovalTimeline {
//       approvals: [
//           { approver: "张三", date: "2026-07-01", conclusion: "approved", comment: "同意" },
//           { approver: "李四", date: "2026-07-02", conclusion: "rejected", comment: "需修改" }
//       ]
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property var approvals: []  // 审批记录数组
    property string emptyText: "暂无审批记录"

    // ── 视觉样式 ────────────────────────────────────────
    color: Theme.surface
    border.color: Theme.border
    border.width: 1
    radius: Theme.radiusMd
    implicitHeight: Math.max(200, contentColumn.implicitHeight + 2 * Theme.spacingMd)
    implicitWidth: 600

    // ── 结论颜色映射 ────────────────────────────────────
    function _conclusionColor(conclusion: string): color {
        if (conclusion === "approved" || conclusion === "conditionally_approved") return Theme.success
        if (conclusion === "rejected" || conclusion === "refused") return Theme.error
        return Theme.textSecondary
    }

    function _conclusionLabel(conclusion: string): string {
        const map = {
            "approved": "批准",
            "conditionally_approved": "有条件批准",
            "rejected": "驳回",
            "refused": "拒绝"
        }
        return map[conclusion] || conclusion
    }

    // ── 内容区 ──────────────────────────────────────────
    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        // 标题
        Text {
            text: "审批时间线（" + root.approvals.length + " 条记录）"
            font.pixelSize: Theme.fontSizeLg
            font.bold: true
            color: Theme.textPrimary
            Layout.fillWidth: true
        }

        // 空状态
        Text {
            visible: root.approvals.length === 0
            text: root.emptyText
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
            Layout.preferredHeight: 80
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        // 时间线节点
        Repeater {
            model: root.approvals

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                color: "transparent"
                border.color: Theme.border
                border.width: 1
                radius: Theme.radiusSm

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    spacing: Theme.spacingSm

                    // 状态圆点
                    Rectangle {
                        width: 12
                        height: 12
                        radius: 6
                        color: root._conclusionColor(modelData.conclusion || "")
                        Layout.alignment: Qt.AlignVCenter
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            text: modelData.approver || "未知"
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            color: Theme.textPrimary
                        }
                        Text {
                            text: (modelData.date || "") + " · " + root._conclusionLabel(modelData.conclusion || "")
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                        }
                        Text {
                            text: modelData.comment || ""
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                            visible: !!(modelData.comment)
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }
}
