// WorkspaceView.qml — V1.0.0 项目工作区协调壳
//
// 职责：状态持有 + Tab 路由 + Bridge 调用编排
// 不含任何 Tab 内容渲染，全部委托给 workspace/ 子组件：
//   workspace/WsOverviewTab.qml  — 概览
//   workspace/WsChangeTab.qml   — 变更驾驶舱
//   workspace/WsCheckTab.qml    — 规范检查
//   workspace/WsDocTab.qml      — 文档浏览
//   workspace/WsVarTableTab.qml — 变量表
//
// 对外接口（main.qml 依赖，不可变）：
//   id: workspaceView
//   function setProject(projectId, projectName)
//   function switchTab(index)
//   property int currentTabIndex (只读)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"
import "workspace"

Rectangle {
    id: root
    color: Theme.background

    // ── 对外接口属性 ─────────────────────────────────────
    readonly property int currentTabIndex: tabBar.currentTabIndex

    // ── 内部状态属性 ─────────────────────────────────────
    property string currentProjectId: ""
    property string currentProjectName: ""
    property var currentProjectDetail: ({})
    property var changesList: []
    property var selectedChangeDetail: ({})
    property var specCheckResult: ({})
    property var assetSummary: ({})

    property bool checkingSpec: false
    property bool repairingSpec: false
    property bool refreshingAssets: false

    // 变更 Tab 辅助属性
    property var    _changeSummary: ({})
    property string searchKeyword: ""
    property string selectedStatusFilter: "ALL"
    property string selectedDomainFilter: "ALL"

    // 过滤后的变更列表（computed）
    readonly property var filteredChangesList: {
        var list = root.changesList || []
        return list.filter(function(item) {
            var kw = root.searchKeyword.trim().toLowerCase()
            if (kw !== "") {
                var n = (item.change_number || "").toLowerCase()
                var t = (item.title || "").toLowerCase()
                if (n.indexOf(kw) === -1 && t.indexOf(kw) === -1) return false
            }
            if (root.selectedDomainFilter !== "ALL") {
                if ((item.domain || "").toUpperCase() !== root.selectedDomainFilter) return false
            }
            if (root.selectedStatusFilter !== "ALL") {
                if ((item.status || "").toLowerCase() !== root.selectedStatusFilter.toLowerCase()) return false
            }
            return true
        })
    }

    onSearchKeywordChanged: _autoSelectFirstChange()
    onSelectedStatusFilterChanged: _autoSelectFirstChange()
    onSelectedDomainFilterChanged: _autoSelectFirstChange()

    function _autoSelectFirstChange() {
        if (root.filteredChangesList && root.filteredChangesList.length > 0) {
            if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService) {
                root.selectedChangeDetail = changeBridge.getChangeRequest(root.filteredChangesList[0].change_number, root.currentProjectId) || {}
            }
        } else {
            root.selectedChangeDetail = {}
        }
    }

    // 变更状态机（computed from selectedChangeDetail）
    readonly property var _currentChangeStateMachine: {
        var status = "draft"
        if (root.selectedChangeDetail && root.selectedChangeDetail.status) {
            status = root.selectedChangeDetail.status
        } else if (root.filteredChangesList && root.filteredChangesList.length > 0) {
            status = root.filteredChangesList[0].status
        }
        return _computeStateMachineForStatus(status)
    }

    readonly property string _currentChangeNumber: {
        if (root.selectedChangeDetail && root.selectedChangeDetail.change_number)
            return root.selectedChangeDetail.change_number
        if (root.filteredChangesList && root.filteredChangesList.length > 0)
            return root.filteredChangesList[0].change_number
        return ""
    }

    function _computeStateMachineForStatus(status) {
        var statusOrder = ["draft","submitted","under_review","approved","implementing","pending_acceptance","accepting","completed","closed"]
        var statusNames = { "draft":"草稿","submitted":"已提交","under_review":"审核中","approved":"已批准","implementing":"实施中","pending_acceptance":"待验收","accepting":"验收中","completed":"已完成","closed":"已关闭" }
        var latestStatus = status || "draft"
        var latestIdx = statusOrder.indexOf(latestStatus)
        if (latestIdx === -1) latestIdx = 0
        var nodes = []
        for (var i = 0; i < statusOrder.length; i++) {
            var ns = statusOrder[i]
            nodes.push({ "name": statusNames[ns], "status": i < latestIdx ? "done" : (i === latestIdx ? "active" : "pending"), "active": ns === latestStatus, "completed": i <= latestIdx })
        }
        var progress = statusOrder.length > 1 ? (latestIdx / (statusOrder.length - 1)) * 100 : 0
        return { "current_node": latestIdx + 1, "current_node_name": statusNames[latestStatus] || latestStatus, "progress": progress, "nodes": nodes }
    }

    // ── 信号 ─────────────────────────────────────────────
    signal backToProjectList()
    signal requestEditProject()
    signal requestDeleteProject()
    signal requestApplyTemplate()
    signal requestInitializePm()

    // ── 公开方法 ─────────────────────────────────────────
    function setProject(projectId, projectName) {
        root.currentProjectId = projectId
        root.currentProjectName = projectName
        console.log("[QML] WorkspaceView: 加载项目 " + projectId + " - " + projectName)
        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
            root.currentProjectDetail = workbenchBridge.getProjectById(projectId)
            if (changeBridge.hasService) {
                root.changesList = changeBridge.listChanges(projectId)
            } else {
                root.changesList = []
            }
        }
        // 默认加载第一条变更详情
        if (root.changesList.length > 0) {
            if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService) {
                root.selectedChangeDetail = changeBridge.getChangeRequest(root.changesList[0].change_number, root.currentProjectId) || {}
            }
        } else {
            root.selectedChangeDetail = {}
        }
        tabBar.currentTabIndex = 0
        _loadCurrentTab()
        _loadAssetSummary()
    }

    function switchTab(index) {
        tabBar.currentTabIndex = index
        _loadCurrentTab()
    }

    function _loadAssetSummary() {
        if (typeof deliveryBridge === "undefined" || deliveryBridge === null || !deliveryBridge.hasService) { root.assetSummary = {}; return }
        if (root.currentProjectDetail.stack !== "plc") { root.assetSummary = {}; return }
        var res = deliveryBridge.getAssetSummary(root.currentProjectId)
        root.assetSummary = (res && res.data) ? res.data : {}
    }

    function _loadCurrentTab() {
        switch (tabBar.currentTabIndex) {
            case 1: _loadChangeTab(); break
            case 2: _loadCheckTab(); break
            case 3: _loadDocTab(); break
            case 4: _loadVarTableTab(); break
            default: break
        }
    }

    function _loadChangeTab() {
        if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService) {
            root.changesList = changeBridge.listChanges(root.currentProjectId)
        }
        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null && workbenchBridge.hasService) {
            root._changeSummary = workbenchBridge.getProjectChangeSummary(root.currentProjectId) || {}
        } else {
            root._changeSummary = {}
        }
    }

    function _loadCheckTab() {
        root.checkingSpec = true
        checkTimer.restart()
    }

    function _loadDocTab() {
        if (docTabItem && docTabItem.projectId !== undefined) {
            // DocBrowserView 监听 projectId 变化自动刷新
        }
    }

    function _loadVarTableTab() {
        if (typeof deliveryBridge !== "undefined" && deliveryBridge !== null && deliveryBridge.hasService) {
            // VarTableEditorView 监听 projectId 变化自动刷新
        }
    }

    // ── 定时器 ────────────────────────────────────────────
    Timer {
        id: checkTimer
        interval: 30; repeat: false
        onTriggered: {
            try {
                if (typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService) {
                    root.specCheckResult = specBridge.runSpecCheck(root.currentProjectId)
                } else {
                    root.specCheckResult = { "error_count": -1, "message": "未启用规范检查服务" }
                }
            } finally {
                root.checkingSpec = false
            }
        }
    }

    Timer {
        id: repairTimer
        interval: 30; repeat: false
        onTriggered: {
            try {
                if (typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService) {
                    specBridge.repairSpec(root.currentProjectId)
                    root.specCheckResult = specBridge.runSpecCheck(root.currentProjectId)
                }
            } finally {
                root.repairingSpec = false
            }
        }
    }

    Timer {
        id: assetRefreshTimer
        interval: 30; repeat: false
        onTriggered: {
            try {
                if (typeof deliveryBridge !== "undefined" && deliveryBridge !== null && deliveryBridge.hasService) {
                    var res = deliveryBridge.refreshAssetSummary(root.currentProjectId)
                    if (res && res.result) root.assetSummary = res.result
                }
            } finally {
                root.refreshingAssets = false
            }
        }
    }

    // ── 顶部导航栏 ────────────────────────────────────────
    Rectangle {
        id: navBar
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 56
        color: Theme.surface
        Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 1; color: Theme.border }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.spacingLg
            anchors.rightMargin: Theme.spacingLg
            spacing: Theme.spacingSm

            PrimaryButton { text: "‹返回"; type: "ghost"; Layout.preferredWidth: 80; onClicked: root.backToProjectList() }
            Text { text: root.currentProjectName || "(未选择项目)"; font.pixelSize: Theme.fontSizeXl; font.bold: true; color: Theme.textPrimary }
            Text { text: root.currentProjectId; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; Layout.leftMargin: Theme.spacingSm }
            Item { Layout.fillWidth: true }
            Badge { text: root.currentProjectDetail.stack || ""; type: root.currentProjectDetail.stack || "unknown" }
            Badge {
                text: { var m = {"initiating":"启动","planning":"规划","developing":"在研","commissioning":"调试","production":"生产","archived":"归档"}; return m[root.currentProjectDetail.phase] || "未分类" }
                type: root.currentProjectDetail.phase || "default"
            }
            Text {
                text: { var v = root.currentProjectDetail.version || ""; if (!v || v === "-") return "-"; return (v.startsWith("v") || v.startsWith("V")) ? v : ("v" + v) }
                font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary
            }
            PrimaryButton { text: "编辑"; type: "ghost"; Layout.preferredWidth: 60; onClicked: root.requestEditProject() }
            PrimaryButton {
                text: "初始化 PM"; type: "accent"; Layout.preferredWidth: 90
                visible: root.changesList.length === 0
                onClicked: root.requestInitializePm()
            }
            PrimaryButton { text: "模板"; type: "ghost"; Layout.preferredWidth: 60; onClicked: root.requestApplyTemplate() }
            PrimaryButton {
                text: "🌐 预览 HMI 原型"; type: "secondary"; Layout.preferredWidth: 120
                visible: (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) ? workbenchBridge.hasHmiPrototype(root.currentProjectId) : false
                onClicked: { if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) workbenchBridge.openHmiPrototype(root.currentProjectId) }
            }
            PrimaryButton { text: "删除"; type: "danger"; Layout.preferredWidth: 60; onClicked: root.requestDeleteProject() }
        }
    }

    // ── Tab 栏 ────────────────────────────────────────────
    TabBar {
        id: tabBar
        anchors { left: parent.left; right: parent.right; top: navBar.bottom }
        tabs: ["概览", "变更", "检查", "文档", "变量表"]
        onCurrentTabChanged: root._loadCurrentTab()
    }

    // ── Tab 内容区（统一父容器，修复原结构 bug）─────────────
    Item {
        id: tabContent
        anchors { left: parent.left; right: parent.right; top: tabBar.bottom; bottom: parent.bottom }

        // Tab 0 — 概览
        WsOverviewTab {
            anchors.fill: parent
            visible: tabBar.currentTabIndex === 0
            projectDetail: root.currentProjectDetail
            assetSummary: root.assetSummary
            refreshingAssets: root.refreshingAssets
            currentProjectId: root.currentProjectId
            assetServiceAvailable: typeof deliveryBridge !== "undefined" && deliveryBridge !== null && deliveryBridge.hasService
            hmiPrototypeExists: (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) ? workbenchBridge.hasHmiPrototype(root.currentProjectId) : false
            onRefreshAssetsRequested: { root.refreshingAssets = true; assetRefreshTimer.restart() }
            onOpenHmiPrototypeRequested: { if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) workbenchBridge.openHmiPrototype(root.currentProjectId) }
        }

        // Tab 1 — 变更
        WsChangeTab {
            anchors.fill: parent
            visible: tabBar.currentTabIndex === 1
            changesList: root.changesList
            filteredChangesList: root.filteredChangesList
            selectedChangeDetail: root.selectedChangeDetail
            changeSummary: root._changeSummary
            currentChangeStateMachine: root._currentChangeStateMachine
            currentChangeNumber: root._currentChangeNumber
            currentProjectId: root.currentProjectId
            searchKeyword: root.searchKeyword
            selectedStatusFilter: root.selectedStatusFilter
            selectedDomainFilter: root.selectedDomainFilter
            viewWidth: root.width
            onChangeSelected: function(changeNumber) {
                if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService) {
                    root.selectedChangeDetail = changeBridge.getChangeRequest(changeNumber, root.currentProjectId) || {}
                }
            }
            onSearchFilterChanged: function(kw) { root.searchKeyword = kw }
            onStatusFilterChanged: function(f) { root.selectedStatusFilter = f }
            onDomainFilterChanged: function(f) { root.selectedDomainFilter = f }
            onInitializePmRequested: root.requestInitializePm()
        }

        // Tab 2 — 检查
        WsCheckTab {
            anchors.fill: parent
            visible: tabBar.currentTabIndex === 2
            specCheckResult: root.specCheckResult
            checkingSpec: root.checkingSpec
            repairingSpec: root.repairingSpec
            isPlcProject: root.currentProjectDetail.stack === "plc"
            specServiceAvailable: typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService
            onRunCheckRequested: root._loadCheckTab()
            onRepairRequested: { root.repairingSpec = true; repairTimer.restart() }
        }

        // Tab 3 — 文档
        WsDocTab {
            id: docTabItem
            anchors.fill: parent
            visible: tabBar.currentTabIndex === 3
            projectId: root.currentProjectId
        }

        // Tab 4 — 变量表
        WsVarTableTab {
            anchors.fill: parent
            visible: tabBar.currentTabIndex === 4
            projectId: root.currentProjectId
        }
    }
}
