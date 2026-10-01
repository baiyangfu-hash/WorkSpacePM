// Evidence drawer: provenance is visible on demand, while normal cards stay non-technical.
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    property var evidence: ({})
    property bool opened: false
    readonly property var focusInfo: evidence && evidence.focus ? evidence.focus : ({})
    readonly property var resumeInfo: evidence && evidence.resume ? evidence.resume : ({})
    readonly property string currency: evidence && evidence.evidence_currency
        ? evidence.evidence_currency : ""
    signal closeRequested()

    function actionLabel(action) {
        if (action === "CONFIRM_START")
            return "确认开工"
        if (action === "CONFIRM_ACCEPTANCE")
            return "确认最终验收"
        if (action === "REVIEW_ESCALATION")
            return "需要您查看并决策"
        return "无需操作"
    }

    function focusText() {
        if (!focusInfo.mission_id)
            return "暂无进行中的需求。"
        return "需求：" + focusInfo.mission_id
            + "    根工作：" + (focusInfo.work_id || "暂无")
            + "    运行：" + (focusInfo.run_id || "暂无")
            + (focusInfo.run_state ? "（" + focusInfo.run_state + "）" : "")
    }

    function currencyText() {
        var reason = evidence && evidence.evidence_currency_reason
            ? evidence.evidence_currency_reason : ""
        if (currency === "CURRENT")
            return "与当前内容一致"
        if (currency === "NOT_CURRENT")
            return "与当前内容不一致或无法核验：" + reason
        if (currency === "NOT_APPLICABLE")
            return "无需核验：" + reason
        return "暂无核验信息。"
    }

    function currencyColor() {
        if (currency === "CURRENT")
            return Theme.success
        if (currency === "NOT_CURRENT")
            return Theme.warning
        return Theme.textSecondary
    }

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
            visible: !!(evidence && evidence.change_id)
            text: "变更：" + (evidence.change_id || "") + "    决策：" + (evidence.decision_id || "")
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Text {
            text: "当前任务"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
        }
        Text {
            text: root.focusText()
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Text {
            text: "验证证据与当前内容"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
        }
        Text {
            text: root.currencyText()
            color: root.currencyColor()
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Text {
            text: "下一步"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
        }
        Text {
            text: (root.resumeInfo.reason || "暂无下一步信息。")
                + "  （" + root.actionLabel(root.resumeInfo.user_action) + "）"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
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
