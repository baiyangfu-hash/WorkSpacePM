// User-facing card for one persisted scope that waits for the user's single approval.
// It never renders internal identifiers; the request id and plan hash only travel with the signal.
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    property var card: ({})
    property bool busy: false
    signal approveRequested()

    readonly property bool approvable: !!card && card.can_approve === true

    implicitHeight: content.implicitHeight + Theme.spacingLg * 2
    color: Theme.surface
    radius: Theme.radiusMd
    border.color: Theme.primary
    border.width: 1

    function lines(values) {
        return values && values.length > 0 ? values.join("；") : "无"
    }

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "待您批准的范围 · " + (card && card.project_name ? card.project_name : "项目")
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Text {
                objectName: "pendingRevision"
                text: card && card.revision ? "第 " + card.revision + " 版" : ""
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeSm
            }
        }

        Repeater {
            model: [
                { label: "目标", value: card && card.objective ? card.objective : "-" },
                { label: "验收", value: lines(card ? card.acceptance_criteria : []) },
                { label: "改动范围", value: lines(card ? card.scope_paths : []) },
                { label: "风险", value: lines(card ? card.risks : []) },
                { label: "不做什么", value: lines(card ? card.non_goals : []) },
                { label: "执行者", value: card && card.executor ? card.executor + "（独立工作树）" : "-" },
                { label: "起草人", value: card && card.submitted_by ? card.submitted_by : "-" }
            ]
            delegate: RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: modelData.label + "："
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSizeSm
                    Layout.alignment: Qt.AlignTop
                }
                Text {
                    text: modelData.value
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeSm
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        Text {
            objectName: "approverLabel"
            text: card && card.approver ? "批准人：" + card.approver : "批准人：未配置"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
        }

        Text {
            objectName: "approveBlockedReason"
            visible: !root.approvable
            text: card && card.approve_blocked_reason ? card.approve_blocked_reason : ""
            color: Theme.warning
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        PrimaryButton {
            objectName: "approveScopeButton"
            text: root.busy ? "正在批准并启动…" : "批准范围并开始"
            enabled: root.approvable && !root.busy
            loading: root.busy
            Layout.alignment: Qt.AlignRight
            onClicked: root.approveRequested()
        }
    }
}
