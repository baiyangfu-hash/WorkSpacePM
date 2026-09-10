// Safe default entry. The legacy professional workbench is available only through --advanced.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "views" as Views
import "components" as Components
import "theme"

ApplicationWindow {
    id: root

    width: 1280
    height: 820
    minimumWidth: 900
    minimumHeight: 600
    visible: true
    title: "我的驾驶舱"
    color: Theme.background

    property var snapshot: ({ projects: [], notices: [] })
    property string statusMessage: ""

    function refreshSnapshot() {
        if (typeof pmCockpitBridge === "undefined") {
            statusMessage = "驾驶舱桥接尚未连接。"
            return
        }
        var response = pmCockpitBridge.loadSnapshot()
        if (response.success) {
            snapshot = response.snapshot
        } else {
            statusMessage = response.message || "无法读取驾驶舱状态。"
        }
    }

    function showEvidence(projectId) {
        var response = pmCockpitBridge.loadEvidence(projectId)
        if (response.success) {
            evidenceDrawer.openEvidence(response.evidence)
        } else {
            statusMessage = response.message || "无法读取证据。"
        }
    }

    Views.BossCockpitView {
        anchors.fill: parent
        cards: root.snapshot.projects || []
        notices: root.snapshot.notices || []
        statusMessage: root.statusMessage
        onEvidenceRequested: root.showEvidence(projectId)
        onStartConfirmed: function(missionId) {
            var response = pmCockpitBridge.confirmStart(missionId)
            root.statusMessage = response.message || "已记录开工确认。"
            root.refreshSnapshot()
        }
        onAcceptanceConfirmed: function(missionId) {
            var response = pmCockpitBridge.confirmAcceptance(missionId)
            root.statusMessage = response.message || "已记录最终验收。"
            root.refreshSnapshot()
        }
    }

    Components.EvidenceDrawer {
        id: evidenceDrawer
        z: 10
        width: Math.min(parent.width - Theme.spacingXl * 2, 820)
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: Theme.spacingXl
        onCloseRequested: opened = false
    }

    Component.onCompleted: refreshSnapshot()
}
