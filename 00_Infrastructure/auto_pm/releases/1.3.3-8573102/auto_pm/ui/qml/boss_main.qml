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
    // Failures stay up until dismissed or until the same action later succeeds; the 5 s snapshot refresh clears
    // statusMessage, so a failure shown only there disappears before the user has read it.
    property string actionAlert: ""
    property string actionAlertKey: ""
    // The standalone window owns its bridge: closing or destroying it seals the bridge for good. An embedding host sets this to false so that
    // unloading the view only pauses the refresh; the host then seals the bridge itself when it really closes.
    property bool closesBridgeOnDestruction: true

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

    function raiseActionAlert(key, text) {
        actionAlertKey = key
        actionAlert = text
    }

    function clearActionAlert(key) {
        if (actionAlertKey !== key)
            return
        actionAlertKey = ""
        actionAlert = ""
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
        boards: root.snapshot.boards || []
        planningDraft: root.planningDraft
        statusMessage: root.statusMessage
        actionAlert: root.actionAlert
        onActionAlertDismissed: root.clearActionAlert(root.actionAlertKey)
        onDraftInputChanged: root.planningDraft = null
        onPlanningDraftRequested: function(projectId, objective, acceptanceText, kind) {
            var response = pmCockpitBridge.createPlanningDraft(
                projectId, objective, acceptanceText, kind
            )
            root.statusMessage = response.message || "草稿未保存。"
            root.planningDraft = response.success ? response.draft : null
        }
        onEvidenceRequested: root.showEvidence(projectId)
        onScopeApprovalConfirmed: function(requestId, planHash) {
            var response = pmCockpitBridge.approveScopeAndStart(requestId, planHash)
            root.statusMessage = response.message || "范围未能提交批准。"
            if (!response.accepted) {
                cockpitView.setApproveBusy(requestId, false)
                if (!response.busy)
                    root.raiseActionAlert("approve:" + requestId, "批准失败：" + root.statusMessage)
            }
        }
        onStartConfirmed: function(missionId) {
            var response = pmCockpitBridge.startExecution(missionId)
            root.statusMessage = response.message || "任务未能启动。"
            if (!response.accepted) {
                cockpitView.setStartBusy(missionId, false)
                if (!response.busy)
                    root.raiseActionAlert("start:" + missionId, "需求 " + missionId + " 启动失败：" + root.statusMessage)
            }
        }
        onAcceptanceConfirmed: function(missionId) {
            var response = pmCockpitBridge.confirmAcceptance(missionId)
            root.statusMessage = response.message || "已记录最终验收。"
            if (response.success && response.closing)
                cockpitView.setCloseBusy(missionId, true)
            else if (response.success)
                root.raiseActionAlert("close:" + missionId, "需求 " + missionId
                    + "：验收已记录，但收尾没能开始。请关闭驾驶舱窗口，再由主执行重试收口。")
            else
                root.raiseActionAlert("accept:" + missionId, "需求 " + missionId + " 验收没有记录："
                    + (response.message || "原因不明。") + " 请不要重复点击，关闭窗口后交主执行处理。")
            root.refreshSnapshot()
        }
        onSyncRetryRequested: function(missionId) {
            var response = pmCockpitBridge.retryClosure(missionId)
            root.statusMessage = response.message || "未能提交同步请求。"
            if (!response.accepted) {
                cockpitView.setCloseBusy(missionId, false)
                if (!response.busy)
                    root.raiseActionAlert("close:" + missionId, "需求 " + missionId + " 重试同步没能开始：" + root.statusMessage)
            }
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
            if (completed) {
                root.clearActionAlert("close:" + missionId)
                root.clearActionAlert("accept:" + missionId)
            } else {
                root.raiseActionAlert("close:" + missionId, "需求 " + missionId + " " + root.statusMessage)
            }
            root.refreshSnapshot()
        }
        function onScopeApprovalFinished(requestId, success, message) {
            if (!success)
                cockpitView.setApproveBusy(requestId, false)
            root.statusMessage = message || (success ? "范围已批准并启动。" : "范围未能批准并启动。")
            if (success)
                root.clearActionAlert("approve:" + requestId)
            else
                root.raiseActionAlert("approve:" + requestId, root.statusMessage)
            root.refreshSnapshot()
        }
        function onStartFinished(missionId, success, message) {
            cockpitView.setStartBusy(missionId, false)
            root.statusMessage = message || (success ? "任务已启动。" : "任务启动失败。")
            if (success)
                root.clearActionAlert("start:" + missionId)
            else
                root.raiseActionAlert("start:" + missionId, "需求 " + missionId + "：" + root.statusMessage)
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
    onClosing: function(close) {
        if (root.closesBridgeOnDestruction)
            pmCockpitBridge.beginShutdown()
    }
    Component.onDestruction: {
        if (root.closesBridgeOnDestruction)
            pmCockpitBridge.beginShutdown()
        else
            pmCockpitBridge.stopSnapshotRefresh()
    }
}
