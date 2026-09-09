// PhaseProgress.qml - 阶段进度条（V0.6.0 W3-S4）
//
// 项目阶段进度条，展示 developing/commissioning/production/archived 4 阶段。
// 当前阶段高亮，已完成阶段绿色，未来阶段灰色。
//
// 用法：
//   PhaseProgress {
//       currentPhase: "commissioning"
//       phases: ["developing", "commissioning", "production", "archived"]
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string currentPhase: "developing"
    property var phases: ["developing", "commissioning", "production", "archived"]
    property var phaseLabels: ({
        "developing": "开发中",
        "commissioning": "调试中",
        "production": "生产中",
        "archived": "已归档"
    })

    // ── 视觉样式 ────────────────────────────────────────
    color: Theme.surface
    border.color: Theme.border
    border.width: 1
    radius: Theme.radiusMd
    implicitWidth: 600
    implicitHeight: 70

    // ── 阶段颜色映射 ────────────────────────────────────
    function _phaseColor(phase: string): color {
        if (phase === "developing") return Theme.phaseDeveloping
        if (phase === "commissioning") return Theme.phaseCommissioning
        if (phase === "production") return Theme.phaseProduction
        if (phase === "archived") return Theme.phaseArchived
        return Theme.textMuted
    }

    function _phaseIndex(phase: string): int {
        for (let i = 0; i < root.phases.length; i++) {
            if (root.phases[i] === phase) return i
        }
        return -1
    }

    function _isCompleted(phase: string): bool {
        const currentIdx = _phaseIndex(root.currentPhase)
        const phaseIdx = _phaseIndex(phase)
        return phaseIdx >= 0 && currentIdx >= 0 && phaseIdx < currentIdx
    }

    function _progressPercent(): real {
        const currentIdx = _phaseIndex(root.currentPhase)
        if (currentIdx < 0 || root.phases.length === 0) return 0.0
        // 当前阶段位于 (currentIdx + 0.5) / total，居中显示
        return (currentIdx + 0.5) / root.phases.length
    }

    // ── 内容区 ──────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        // 标题 + 进度百分比
        RowLayout {
            Layout.fillWidth: true

            Text {
                text: "阶段进度"
                font.pixelSize: Theme.fontSizeMd
                font.bold: true
                color: Theme.textPrimary
            }

            Item { Layout.fillWidth: true }

            Text {
                text: Math.round(root._progressPercent() * 100) + "%"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }
        }

        // 进度条主体
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 28

            // 背景轨道
            Rectangle {
                id: trackBg
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                height: 8
                radius: 4
                color: Theme.border
            }

            // 已完成进度填充
            Rectangle {
                id: progressFill
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: trackBg.width * root._progressPercent()
                height: 8
                radius: 4
                color: _phaseColor(root.currentPhase)
                Behavior on width {
                    NumberAnimation { duration: 200 }
                }
            }

            // 阶段节点
            RowLayout {
                anchors.fill: parent
                spacing: 0

                Repeater {
                    model: root.phases

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        // 阶段节点圆点
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.verticalCenter: parent.verticalCenter
                            width: 16
                            height: 16
                            radius: 8
                            color: _isCompleted(modelData)
                                ? Theme.success
                                : (modelData === root.currentPhase
                                    ? _phaseColor(modelData)
                                    : Theme.background)
                            border.color: _phaseColor(modelData)
                            border.width: 2
                        }

                        // 阶段标签
                        Text {
                            anchors.top: parent.verticalCenter
                            anchors.topMargin: 12
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: root.phaseLabels[modelData] || modelData
                            font.pixelSize: Theme.fontSizeXs
                            color: (modelData === root.currentPhase || _isCompleted(modelData))
                                ? Theme.textPrimary
                                : Theme.textMuted
                            font.bold: modelData === root.currentPhase
                        }
                    }
                }
            }
        }
    }
}
