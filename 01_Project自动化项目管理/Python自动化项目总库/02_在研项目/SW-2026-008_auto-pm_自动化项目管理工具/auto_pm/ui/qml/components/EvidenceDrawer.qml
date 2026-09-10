// Evidence drawer: provenance is visible on demand, while normal cards stay non-technical.
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    property var evidence: ({})
    property bool opened: false
    signal closeRequested()

    visible: opened
    color: Theme.surface
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1
    implicitHeight: drawerContent.implicitHeight + Theme.spacingLg * 2

    function openEvidence(value) {
        evidence = value || ({})
        opened = true
    }

    ColumnLayout {
        id: drawerContent
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "证据与接力信息"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
                Layout.fillWidth: true
            }
            PrimaryButton {
                text: "收起"
                type: "ghost"
                onClicked: root.closeRequested()
            }
        }

        Text {
            text: evidence && evidence.status_note ? evidence.status_note : "暂无可用证据。"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Text {
            visible: evidence && evidence.change_id
            text: "变更：" + (evidence.change_id || "") + "    决策：" + (evidence.decision_id || "")
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Text {
            text: "工作图"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
        }
        WorkGraphView {
            Layout.fillWidth: true
            nodes: evidence && evidence.work_graph ? evidence.work_graph : []
        }

        Text {
            text: "验证证据"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
        }
        Repeater {
            model: evidence && evidence.verification_evidence ? evidence.verification_evidence : []
            delegate: Text {
                text: "• " + modelData
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeSm
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }

        Text {
            visible: !evidence || !evidence.verification_evidence || evidence.verification_evidence.length === 0
            text: "尚无已完成的验证记录。"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
        }

        Text {
            text: "读取来源"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
        }
        Repeater {
            model: evidence && evidence.read_set ? evidence.read_set : []
            delegate: Text {
                text: "• " + modelData
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeXs
                Layout.fillWidth: true
                elide: Text.ElideMiddle
            }
        }
    }
}
