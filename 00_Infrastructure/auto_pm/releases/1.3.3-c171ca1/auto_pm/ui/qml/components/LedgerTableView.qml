// LedgerTableView.qml - 变更单台账表格视图（CHG-2 T2）
//
// 全宽表格视图，与 Split View 互补。展示所有变更单的紧凑表格。
// 点击行 → 发出 changeSelected 信号 → 父组件切回 Split View 并选中。
//
// 用法：
//   LedgerTableView {
//       model: filteredModel
//       selectedChangeNumber: root.selectedChangeNumber
//       onChangeSelected: (number) => { ... }
//   }

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "."

GlassPanel {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property var model: null
    property string selectedChangeNumber: ""

    // ── 信号 ────────────────────────────────────────────
    signal changeSelected(string changeNumber, string projectId)

    // ── 列宽定义 ────────────────────────────────────────
    readonly property int _colNumber: 160   // 变更编号
    readonly property int _colTitle: 320    // 标题
    readonly property int _colStatus: 100   // 状态
    readonly property int _colDomain: 80    // 领域
    readonly property int _colApplicant: 100 // 申请人
    readonly property int _colDate: 120     // 申请日期

    // ── 表头 ────────────────────────────────────────────
    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 36
        color: Theme.glassBg
        border.color: Theme.glassBorder
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.spacingSm
            anchors.rightMargin: Theme.spacingSm
            spacing: 0

            Text {
                text: "变更编号"
                Layout.preferredWidth: root._colNumber
                font.pixelSize: Theme.fontSizeXs
                font.bold: true
                color: Theme.textSecondary
            }
            Text {
                text: "标题"
                Layout.preferredWidth: root._colTitle
                Layout.fillWidth: true
                font.pixelSize: Theme.fontSizeXs
                font.bold: true
                color: Theme.textSecondary
            }
            Text {
                text: "状态"
                Layout.preferredWidth: root._colStatus
                font.pixelSize: Theme.fontSizeXs
                font.bold: true
                color: Theme.textSecondary
            }
            Text {
                text: "领域"
                Layout.preferredWidth: root._colDomain
                font.pixelSize: Theme.fontSizeXs
                font.bold: true
                color: Theme.textSecondary
            }
            Text {
                text: "申请人"
                Layout.preferredWidth: root._colApplicant
                font.pixelSize: Theme.fontSizeXs
                font.bold: true
                color: Theme.textSecondary
            }
            Text {
                text: "申请日期"
                Layout.preferredWidth: root._colDate
                font.pixelSize: Theme.fontSizeXs
                font.bold: true
                color: Theme.textSecondary
            }
        }
    }

    // ── 表格内容 ────────────────────────────────────────
    ListView {
        id: tableView
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 0
        clip: true
        spacing: 0
        model: root.model

        // 空状态
        Text {
            anchors.centerIn: parent
            visible: (root.model === null) || (root.model.count === 0)
            text: "暂无变更"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeLg
        }

        delegate: Rectangle {
            width: tableView.width
            height: 40
            color: root.selectedChangeNumber === model.change_number ? Theme.glassHighlight : "transparent"

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: Theme.glassBorder
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingSm
                anchors.rightMargin: Theme.spacingSm
                spacing: 0

                Text {
                    text: model.change_number || ""
                    Layout.preferredWidth: root._colNumber
                    font.pixelSize: Theme.fontSizeXs
                    font.bold: true
                    color: Theme.textPrimary
                }
                Text {
                    text: model.title || "(无标题)"
                    Layout.preferredWidth: root._colTitle
                    Layout.fillWidth: true
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textSecondary
                    elide: Text.ElideRight
                }
                Badge {
                    text: model.status || ""
                    type: model.status || "default"
                    Layout.preferredWidth: root._colStatus
                }
                Text {
                    text: model.domain || ""
                    Layout.preferredWidth: root._colDomain
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textSecondary
                }
                Text {
                    text: model.applicant || ""
                    Layout.preferredWidth: root._colApplicant
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textSecondary
                }
                Text {
                    text: model.apply_date || ""
                    Layout.preferredWidth: root._colDate
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textSecondary
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.changeSelected(model.change_number, model.project_id || "")
            }
        }
    }
}
