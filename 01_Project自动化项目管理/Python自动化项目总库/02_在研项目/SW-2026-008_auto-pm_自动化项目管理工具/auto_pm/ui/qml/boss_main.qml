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

    property var snapshot: ({ projects: [], activities: [], notices: [] })
    property var planningDraft: null
    property string statusMessage: ""

    function refreshSnapshot() {
        if (typeof pmCockpitBridge === "undefined") {
            statusMessage = "驾驶舱桥接尚未连接。"
            return
        }
        var response = pmCockpitBridge.requestSnapshot()
        if (!response.accepted && !response.busy) {
            statusMessage = response.message || "无法读取驾驶舱状态。"
        }
    }

    readonly property string evidenceLoadingMessage: "正在读取证据…"

    function showEvidence(projectId) {
        if (typeof pmCockpitBridge === "undefined") {
            statusMessage = "驾驶舱桥接尚未连接。"
            return
        }
        var response = pmCockpitBridge.requestEvidence(projectId)
        statusMessage = response.accepted
            ? evidenceLoadingMessage
            : (response.message || "无法读取证据。")
    }

    Views.BossCockpitView {
        id: cockpitView
        anchors.fill: parent
        cards: root.snapshot.projects || []
        activities: root.snapshot.activities || []
        notices: root.snapshot.notices || []
        pendingCards: root.snapshot.pending_cards || []
        planningDraft: root.planningDraft
        statusMessage: root.statusMessage
        onDraftInputChanged: root.planningDraft = null
        onPlanningDraftRequested: function(projectId, objective, acceptanceText) {
            var response = pmCockpitBridge.createPlanningDraft(
                projectId, objective, acceptanceText
            )
            root.statusMessage = response.message || "草稿未保存。"
            root.planningDraft = response.success ? response.draft : null
        }
        onEvidenceRequested: root.showEvidence(projectId)
        onScopeApprovalConfirmed: function(requestId, planHash) {
            var response = pmCockpitBridge.approveScopeAndStart(requestId, planHash)
            root.statusMessage = response.message || "范围未能提交批准。"
            if (!response.accepted)
                cockpitView.setApproveBusy(requestId, false)
        }
        onStartConfirmed: function(missionId) {
            var response = pmCockpitBridge.startExecution(missionId)
            root.statusMessage = response.message || "任务未能启动。"
            if (!response.accepted)
                cockpitView.setStartBusy(missionId, false)
        }
        onAcceptanceConfirmed: function(missionId) {
            var response = pmCockpitBridge.confirmAcceptance(missionId)
            root.statusMessage = response.message || "已记录最终验收。"
            if (response.success && response.closing)
                cockpitView.setCloseBusy(missionId, true)
            root.refreshSnapshot()
        }
        onSyncRetryRequested: function(missionId) {
            var response = pmCockpitBridge.retryClosure(missionId)
            root.statusMessage = response.message || "未能提交同步请求。"
            if (!response.accepted)
                cockpitView.setCloseBusy(missionId, false)
        }
    }

    Connections {
        target: pmCockpitBridge
        function onSnapshotFinished(response) {
            if (response.success) {
                root.snapshot = response.snapshot
                root.statusMessage = ""
            } else {
                root.statusMessage = response.message || "状态刷新失败；已保留上次可信结果。"
            }
        }
        function onEvidenceFinished(response) {
            if (response.success) {
                evidenceDrawer.openEvidence(response.evidence)
                if (root.statusMessage === root.evidenceLoadingMessage)
                    root.statusMessage = ""
            } else {
                root.statusMessage = response.message || "无法读取证据。"
            }
        }
        function onClosureFinished(missionId, completed, message) {
            cockpitView.setCloseBusy(missionId, false)
            root.statusMessage = message || (completed ? "已完成。" : "同步未完成。")
            root.refreshSnapshot()
        }
        function onScopeApprovalFinished(requestId, success, message) {
            if (!success)
                cockpitView.setApproveBusy(requestId, false)
            root.statusMessage = message || (success ? "范围已批准并启动。" : "范围未能批准并启动。")
            root.refreshSnapshot()
        }
        function onStartFinished(missionId, success, message) {
            cockpitView.setStartBusy(missionId, false)
            root.statusMessage = message || (success ? "任务已启动。" : "任务启动失败。")
            if (success)
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

    Component.onCompleted: pmCockpitBridge.startSnapshotRefresh()
    Component.onDestruction: pmCockpitBridge.stopSnapshotRefresh()
}
