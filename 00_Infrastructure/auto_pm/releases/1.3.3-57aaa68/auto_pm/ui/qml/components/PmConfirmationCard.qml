// User-facing confirmation card. It intentionally never renders internal Work/Run identifiers.
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    property var card: ({})
    property bool busy: false
    signal startConfirmed()
    signal acceptanceConfirmed()

    implicitHeight: content.implicitHeight + Theme.spacingLg * 2
    color: Theme.surface
    radius: Theme.radiusMd
    border.color: card && card.blocked ? Theme.error : Theme.border
    border.width: 1

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: card && card.project_name ? card.project_name : "项目"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Text {
                text: card && card.blocked ? "需要决策" : "已整理"
                color: card && card.blocked ? Theme.error : Theme.success
                font.pixelSize: Theme.fontSizeSm
            }
        }

        Text {
            text: card && card.mission ? card.mission : "暂无进行中的需求"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        GridLayout {
            columns: 2
            columnSpacing: Theme.spacingLg
            rowSpacing: Theme.spacingXs
            Layout.fillWidth: true

            Repeater {
                model: [
                    { label: "里程碑", value: card && card.milestone ? card.milestone : "-" },
                    { label: "进展", value: card && card.progress ? card.progress : "-" },
                    { label: "验证", value: card && card.verification ? card.verification : "-" },
                    { label: "风险", value: card && card.risk ? card.risk : "-" },
                    { label: "当前负责人", value: card && card.current_owner ? card.current_owner : "-" },
                    { label: "下一步", value: card && card.next_user_action ? card.next_user_action : "-" }
                ]
                delegate: RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: modelData.label + "："
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSizeSm
                    }
                    Text {
                        text: modelData.value
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeSm
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
            }
        }

        PrimaryButton {
            visible: card && card.user_action === "CONFIRM_START"
            text: "确认开始"
            loading: root.busy
            Layout.alignment: Qt.AlignRight
            onClicked: root.startConfirmed()
        }

        PrimaryButton {
            visible: card && card.user_action === "CONFIRM_ACCEPTANCE"
            text: "确认验收"
            type: "accent"
            loading: root.busy
            Layout.alignment: Qt.AlignRight
            onClicked: root.acceptanceConfirmed()
        }
    }
}
