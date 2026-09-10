// Default screen for a non-technical decision maker.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components" as Components
import "../theme"

Item {
    id: root

    property var cards: []
    property var notices: []
    property string statusMessage: ""
    signal evidenceRequested(string projectId)
    signal startConfirmed(string missionId)
    signal acceptanceConfirmed(string missionId)

    Flickable {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true

        ColumnLayout {
            id: content
            width: parent.width
            spacing: Theme.spacingMd

            Text {
                text: "我的驾驶舱"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeXl
                font.bold: true
                Layout.fillWidth: true
            }
            Text {
                text: "你只需要确认开始与最终验收；其余执行、分流和证据整理由 PM 驾驶舱处理。"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeSm
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Rectangle {
                visible: root.statusMessage !== ""
                color: Theme.backgroundTertiary
                radius: Theme.radiusSm
                Layout.fillWidth: true
                implicitHeight: message.implicitHeight + Theme.spacingSm * 2
                Text {
                    id: message
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    text: root.statusMessage
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeSm
                    wrapMode: Text.WordWrap
                }
            }

            Repeater {
                model: root.cards
                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingXs
                    Components.PmConfirmationCard {
                        Layout.fillWidth: true
                        card: modelData
                        onStartConfirmed: root.startConfirmed(modelData.mission_id)
                        onAcceptanceConfirmed: root.acceptanceConfirmed(modelData.mission_id)
                    }
                    Components.PrimaryButton {
                        text: "查看证据"
                        type: "ghost"
                        Layout.alignment: Qt.AlignRight
                        onClicked: root.evidenceRequested(modelData.project_id)
                    }
                }
            }

            Repeater {
                model: root.notices
                delegate: Text {
                    text: "提示：" + modelData
                    color: Theme.warning
                    font.pixelSize: Theme.fontSizeSm
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }
}
