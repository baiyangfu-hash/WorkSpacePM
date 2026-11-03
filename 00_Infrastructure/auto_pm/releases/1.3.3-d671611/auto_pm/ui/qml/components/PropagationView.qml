// PropagationView.qml - 变更传播链视图（V0.6.0 W3-S2）
//
// 横向 Flexbox 箭头链，展示一个变更影响的项目/模块传播路径。
// 每个节点显示项目 ID + 模块名，节点间用 → 箭头连接。
//
// 用法：
//   PropagationView {
//       nodes: [
//           { label: "CHG-SCPT-2026-086", type: "change" },
//           { label: "SW-2026-008", type: "project" },
//           { label: "auto_pm/ui", type: "module" }
//       ]
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property var nodes: []  // 传播节点数组：[{ label, type }, ...]
    property string emptyText: "无传播链数据"

    // ── 视觉样式 ────────────────────────────────────────
    color: Theme.surface
    border.color: Theme.border
    border.width: 1
    radius: Theme.radiusMd
    implicitWidth: 700
    implicitHeight: 80

    // ── 节点类型颜色映射 ────────────────────────────────
    function _typeColor(nodeType: string): color {
        if (nodeType === "change") return Theme.primary
        if (nodeType === "project") return Theme.badgePython
        if (nodeType === "module") return Theme.phaseCommissioning
        if (nodeType === "external") return Theme.textSecondary
        return Theme.primary
    }

    function _typeLabel(nodeType: string): string {
        const map = {
            "change": "变更",
            "project": "项目",
            "module": "模块",
            "external": "外部"
        }
        return map[nodeType] || nodeType
    }

    // ── 内容区 ──────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingXs

        // 标题
        Text {
            text: "传播链（" + root.nodes.length + " 个节点）"
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
            color: Theme.textPrimary
            Layout.fillWidth: true
        }

        // 空状态
        Text {
            visible: root.nodes.length === 0
            text: root.emptyText
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        // 节点链
        Flickable {
            visible: root.nodes.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: nodesRow.width
            contentHeight: nodesRow.height
            clip: true
            flickableDirection: Flickable.HorizontalFlick

            RowLayout {
                id: nodesRow
                spacing: Theme.spacingXs

                Repeater {
                    model: root.nodes

                    RowLayout {
                        spacing: Theme.spacingXs

                        // 节点徽标
                        Rectangle {
                            width: 120
                            height: 36
                            radius: Theme.radiusSm
                            color: root._typeColor(modelData.type || "")
                            border.color: Theme.border
                            border.width: 1

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 4
                                spacing: 0

                                Text {
                                    text: root._typeLabel(modelData.type || "")
                                    color: "white"
                                    font.pixelSize: Theme.fontSizeXs
                                    Layout.alignment: Qt.AlignHCenter
                                }
                                Text {
                                    text: modelData.label || ""
                                    color: "white"
                                    font.pixelSize: Theme.fontSizeSm
                                    font.bold: true
                                    Layout.alignment: Qt.AlignHCenter
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }

                        // 箭头（除最后一个节点外都显示）
                        Text {
                            visible: index < root.nodes.length - 1
                            text: "→"
                            font.pixelSize: Theme.fontSizeLg
                            font.bold: true
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                    }
                }
            }
        }
    }
}
