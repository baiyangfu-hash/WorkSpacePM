// DashboardStateMachine.qml - 平台驾驶舱 4 节点状态机（CHG-106 T4 / CHG-111 修复）
//
// 对齐 V7 原型 .state-machine（012_UI架构原型_V7.html L1038-1059）
// 4 节点：Draft → Review → Implementing → Closed
// 含进度条 + 当前节点脉冲动画
//
// CHG-111 修复：
//   - tagLabel 锚点修复 + ToolTip 兜底
//   - 节点间箭头连接线
//   - 底部摘要栏（进度百分比 + 完成状态）
//   - 节点 hover ToolTip
//
// 用法：
//   DashboardStateMachine {
//       title: "主线流转 (CHG-106)"
//       tagText: "V1.0 迭代"
//       stateMachine: bridge.getActiveChangeStatus("SW-2026-008").state_machine
//   }

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

GlassPanel {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string title: "主线流转"  // 标题
    property string tagText: ""        // 右上角标签
    property var stateMachine: ({      // 状态机数据（来自 getActiveChangeStatus）
        "current_node": 0,
        "current_node_name": "",
        "progress": 0,
        "nodes": []
    })

    implicitHeight: 200

    // ── 计算属性 ────────────────────────────────────────
    readonly property int _doneCount: {
        var count = 0
        var nodes = root.stateMachine.nodes || []
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].status === "done") count++
        }
        return count
    }

    readonly property int _totalNodes: (root.stateMachine.nodes || []).length

    readonly property string _summaryText: {
        if (root._totalNodes === 0) return "暂无状态数据"
        if (root._doneCount === root._totalNodes) return "全部 " + root._totalNodes + " 个节点已完成"
        return "已完成 " + root._doneCount + " / " + root._totalNodes + " 个节点"
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── 头部：标题 + 标签 ────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: "transparent"

            // 底部分隔线
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: Theme.glassBorder
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingLg
                anchors.rightMargin: Theme.spacingLg
                spacing: Theme.spacingSm

                Text {
                    text: "🔀 " + root.title
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                // 标签胶囊
                Rectangle {
                    visible: root.tagText !== ""
                    Layout.maximumWidth: 250
                    Layout.preferredWidth: Math.min(250, tagLabel.implicitWidth + 16)
                    height: 24
                    radius: 12
                    color: Theme.primary

                    Text {
                        id: tagLabel
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        text: root.tagText
                        color: "white"
                        font.pixelSize: Theme.fontSizeSm
                        elide: Text.ElideRight
                    }

                    HoverHandler {
                        id: tagHover
                    }

                    ToolTip {
                        visible: tagHover.hovered && root.tagText.length > 20
                        text: root.tagText
                        delay: 500
                    }
                }
            }
        }

        // ── 状态机主体 ────────────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.spacingLg

            // 背景线（从第一节点中心到末节点中心）
            Rectangle {
                id: bgLine
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: root._totalNodes > 0 ? parent.width / (2 * root._totalNodes) : parent.width / 8
                anchors.rightMargin: root._totalNodes > 0 ? parent.width / (2 * root._totalNodes) : parent.width / 8
                height: 2
                color: Theme.glassBorder
                radius: 1
            }

            // 进度线（从第一节点到当前进度位置）
            Rectangle {
                id: progressLine
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: bgLine.left
                height: 2
                width: bgLine.width * (root.stateMachine.progress / 100)
                color: Theme.primary
                radius: 1

                Behavior on width {
                    NumberAnimation { duration: 400; easing.type: Easing.OutCubic }
                }
            }

            // 4 节点行
            Row {
                anchors.fill: parent

                Repeater {
                    model: root.stateMachine.nodes

                    Item {
                        width: root._totalNodes > 0 ? parent.width / root._totalNodes : parent.width / 4
                        height: parent.height

                        // 节点间箭头（非末节点且总节点数较少时显示）
                        Text {
                            visible: (index < root._totalNodes - 1) && (root._totalNodes <= 5)
                            anchors.verticalCenter: circle.verticalCenter
                            anchors.horizontalCenter: parent.right
                            text: "→"
                            color: Theme.glassBorder
                            font.pixelSize: Theme.fontSizeLg
                        }

                        // 节点圆圈
                        Rectangle {
                            id: circle
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.verticalCenter: parent.verticalCenter
                            readonly property int circleSize: root._totalNodes > 5 ? 30 : 40
                            width: circleSize
                            height: circleSize
                            radius: circleSize / 2
                            color: modelData.status === "pending" ? Theme.surface :
                                   modelData.status === "done" ? Theme.success : Theme.primary
                            border.color: modelData.status === "pending" ? Theme.glassBorder :
                                          modelData.status === "done" ? Theme.success : Theme.primary
                            border.width: modelData.status === "active" ? 2 : 1

                            // 脉冲动画（仅 active 节点）
                            SequentialAnimation on scale {
                                running: modelData.status === "active"
                                loops: Animation.Infinite
                                NumberAnimation { to: 1.1; duration: 800; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1.0; duration: 800; easing.type: Easing.InOutSine }
                            }

                            // 节点图标
                            Text {
                                anchors.centerIn: parent
                                text: modelData.status === "done" ? "✓" : _nodeIcon(modelData.name || "")
                                color: modelData.status === "pending" ? Theme.textMuted : "white"
                                font.pixelSize: root._totalNodes > 5 ? 12 : 18
                                font.bold: true
                            }
                        }

                        // 节点标签
                        Text {
                            anchors.top: circle.bottom
                            anchors.topMargin: Theme.spacingSm
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.name || ""
                            color: modelData.status === "active" ? Theme.primary :
                                   modelData.status === "done" ? Theme.textSecondary : Theme.textMuted
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: modelData.status === "active"
                            elide: Text.ElideRight
                            width: parent.width - Theme.spacingXs
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }
            }
        }

        // ── 底部摘要栏 ────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: "transparent"

            // 顶部分隔线
            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: Theme.glassBorder
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingLg
                anchors.rightMargin: Theme.spacingLg
                spacing: Theme.spacingSm

                Text {
                    text: root._summaryText
                    color: root._doneCount === root._totalNodes && root._totalNodes > 0 ?
                           Theme.success : Theme.textSecondary
                    font.pixelSize: Theme.fontSizeSm
                    Layout.fillWidth: true
                }

                Text {
                    text: root.stateMachine.progress + "%"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeSm
                    visible: root._totalNodes > 0
                }
            }
        }
    }

    // ── 辅助函数 ────────────────────────────────────────
    function _nodeIcon(name: string): string {
        if (!name) return "•"
        if (name.indexOf("Draft") >= 0 || name.indexOf("草稿") >= 0) return "草"
        if (name.indexOf("Review") >= 0 || name.indexOf("审核") >= 0) return "审"
        if (name.indexOf("Implementing") >= 0 || name.indexOf("实施") >= 0) return "实"
        if (name.indexOf("Closed") >= 0 || name.indexOf("关闭") >= 0) return "关"
        if (name.indexOf("提交") >= 0) return "提"
        if (name.indexOf("批准") >= 0) return "批"
        if (name.indexOf("待验") >= 0) return "验"
        if (name.indexOf("验收") >= 0) return "收"
        if (name.indexOf("完成") >= 0) return "完"
        return "•"
    }
}