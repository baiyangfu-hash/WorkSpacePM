// ActivityTimeline.qml - 活动时间线组件（CHG-106 T5）
//
// 对齐 V7 原型 .timeline-container（012_UI架构原型_V7.html L1069 + JS renderTimeline L1822）
// 渲染 recent_activities 列表：彩色圆点 + 连接线 + 标题 + 描述 + 时间
//
// 数据格式（来自 DashboardSnapshotDTO.recent_activities）：
//   [{"type": "default"|"success"|"warning", "title": "...", "desc": "...", "time": "..."}]
//
// 用法：
//   ActivityTimeline {
//       activities: snapshot.recent_activities
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

GlassPanel {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string title: "近期活动 (PM_SESSION)"  // 标题
    property string titleIcon: "🔄"                  // 标题图标
    property var activities: []                      // 活动列表

    implicitHeight: 280

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── 头部 ────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: "transparent"

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: Theme.glassBorder
            }

            Text {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingLg
                anchors.rightMargin: Theme.spacingLg
                verticalAlignment: Text.AlignVCenter
                text: root.titleIcon + " " + root.title
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
            }
        }

        // ── 时间线列表（可滚动）──────────────────────────
        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: timelineColumn.implicitHeight + Theme.spacingLg * 2
            clip: true
            boundsMovement: Flickable.StopAtBounds

            Column {
                id: timelineColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: Theme.spacingLg
                spacing: Theme.spacingLg

                // 空状态
                Text {
                    visible: root.activities.length === 0
                    text: "暂无近期活动"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeMd
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    topPadding: Theme.spacingXl
                }

                // 时间线条目
                Repeater {
                    model: root.activities

                    Item {
                        width: timelineColumn.width
                        height: itemColumn.implicitHeight

                        // 连接线（除最后一条外）
                        Rectangle {
                            visible: index < root.activities.length - 1
                            anchors.left: dot.left
                            anchors.horizontalCenter: dot.horizontalCenter
                            anchors.top: dot.bottom
                            anchors.topMargin: 2
                            height: parent.height - dot.height - 2
                            width: 1
                            color: Theme.glassBorder
                        }

                        // 彩色圆点
                        Rectangle {
                            id: dot
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.topMargin: 4
                            width: 11
                            height: 11
                            radius: 5.5
                            color: _typeColor(modelData.type || "default")

                            // 辉光效果
                            Rectangle {
                                anchors.centerIn: parent
                                width: parent.width + 6
                                height: parent.height + 6
                                radius: parent.radius + 3
                                color: parent.color
                                opacity: 0.25
                                z: -1
                            }
                        }

                        // 文本区
                        Column {
                            id: itemColumn
                            anchors.left: dot.right
                            anchors.leftMargin: Theme.spacingMd
                            anchors.right: parent.right
                            anchors.top: parent.top
                            spacing: 2

                            Text {
                                text: modelData.title || ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontSizeMd
                                font.weight: Font.Medium
                                width: parent.width
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                text: modelData.desc || ""
                                color: Theme.textMuted
                                font.pixelSize: 13
                                width: parent.width
                                wrapMode: Text.WordWrap
                                visible: text !== ""
                            }

                            Text {
                                text: modelData.time || ""
                                color: Theme.textMuted
                                font.pixelSize: 11
                                opacity: 0.6
                                topPadding: 2
                                visible: text !== ""
                            }
                        }
                    }
                }
            }
        }
    }

    // ── 辅助函数 ────────────────────────────────────────
    function _typeColor(type: string): color {
        if (type === "success") return Theme.success
        if (type === "warning") return Theme.warning
        if (type === "error") return Theme.error
        return Theme.primary
    }
}
