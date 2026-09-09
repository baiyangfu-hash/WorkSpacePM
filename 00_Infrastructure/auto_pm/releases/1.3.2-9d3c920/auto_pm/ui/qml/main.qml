// main.qml - V1.1.0 — 重构为纯路由壳 (CHG-REFACTOR-2026-001)
//
// V1.1.0 重构内容:
// - Header 抽取为 AppHeader 组件 (components/AppHeader.qml)
// - 侧边栏抽取为 AppSidebar 组件 (layout/AppSidebar.qml，数据驱动，预留扩展空间)
// - 对话框层抽取为 DialogLayer 组件 (layout/DialogLayer.qml)
// - main.qml 只保留: 全局状态 + StackLayout 路由 + 信号连接
//
// V1.0.0 约束（保留不变，对应 138 个 QML 测试）:
// - currentPage 值: projectList/workspace/changeCenter/specCenter/reportCenter/templateManage/settings/platformDashboard/modbusDebugger
// - StackLayout 9 个分支 (0-8) 和 currentIndex 映射逻辑不变
// - view id 不变: projectListView/workspaceView/changeCenterView/specCenterView/reportView/templateView/settingsView
// - modbusDebuggerView / platformDashboardView id 不变
// - onProjectClicked/onBackToProjectList 信号处理不变
// - Connections { workbenchBridge.onProjectSelected } 不变
// - Component.onCompleted 启动逻辑不变
//
// context property: workbenchBridge/changeBridge/specBridge/deliveryBridge/systemBridge/fileWatcherBridge
//                   projectModel/changeModel

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "theme"
import "views"
import "components"
import "dialogs"
import "layout"

ApplicationWindow {
    id: mainWindow
    visible: true
    width: 1280
    height: 800
    title: "auto-pm V1.1.0 (QML)"
    color: Theme.background

    // ── 全局页面状态
    property string currentPage: "projectList"
    property string currentProjectId: ""
    property string currentProjectName: ""
    property string currentProjectPhase: "developing"
    property string currentProjectStack: "python"

    // ── 文件监听工具栏状态
    property bool watcherToolbarExpanded: true
    property bool watcherEnabled: false
    property bool syncInProgress: false
    property string watcherStatusText: "就绪"

    // ── 全局导航函数（保留 V1.0.0 接口）
    function selectProjectContext(projectId, projectName) {
        mainWindow.currentProjectId = projectId
        mainWindow.currentProjectName = projectName
        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
            var detail = workbenchBridge.getProjectById(projectId)
            if (detail) {
                mainWindow.currentProjectPhase = detail.phase || "developing"
                mainWindow.currentProjectStack = detail.stack || "python"
            } else {
                mainWindow.currentProjectPhase = "developing"
                mainWindow.currentProjectStack = "python"
            }
        }
        mainWindow.currentPage = "workspace"
        workspaceView.setProject(projectId, projectName)
    }

    function switchToProjectTab(projectId, projectName, tabIndex) {
        selectProjectContext(projectId, projectName)
        mainWindow.currentPage = "workspace"
        workspaceView.switchTab(tabIndex)
    }

    function navigateToPage(pageKey) {
        mainWindow.currentPage = pageKey
        if (pageKey === "platformDashboard") platformDashboardView.loadData()
        else if (pageKey === "changeCenter") changeCenterView.loadChanges()
        else if (pageKey === "specCenter") { specCenterView.loadOverview(); specCenterView.loadEntries(); }
        else if (pageKey === "reportCenter") reportView.loadData()
        else if (pageKey === "templateManage") templateView.loadData()
        else if (pageKey === "settings") settingsView.loadData()
    }

    // ── 背景光晕
    Item {
        id: ambientLayer
        anchors.fill: parent
        z: -1
        AmbientOrb {
            width: 480; height: 480; glowColor: Theme.primary
            anchors.top: parent.top; anchors.left: parent.left; anchors.margins: -180
        }
        AmbientOrb {
            width: 520; height: 520; glowColor: Theme.secondary
            anchors.bottom: parent.bottom; anchors.right: parent.right; anchors.margins: -200
        }
    }

    // ── 顶部 Header（组件化）
    AppHeader {
        id: appHeader
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        appVersion: "V1.1.0"
        workspaceRoot: typeof workspace_root !== "undefined" ? workspace_root : ""
        onRefreshRequested: {
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                workbenchBridge.refreshProjects()
                projectModel.setProjects(workbenchBridge.listProjects())
            }
            if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService)
                changeBridge.refreshChanges()
        }
    }

    // ── 主内容区
    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: appHeader.bottom; anchors.bottom: statusbar.top
        spacing: 0

        // ── 侧边栏（组件化，数据驱动）
        AppSidebar {
            id: appSidebar
            Layout.preferredWidth: Theme.sidebarWidth
            Layout.fillHeight: true
            currentPage: mainWindow.currentPage
            currentProjectId: mainWindow.currentProjectId
            currentProjectName: mainWindow.currentProjectName
            currentProjectPhase: mainWindow.currentProjectPhase
            currentProjectStack: mainWindow.currentProjectStack
            changeBadgeCount: changeBridge ? changeBridge.changeCount : 0
            projectCount: projectModel ? projectModel.count : 0
            workspaceCurrentTabIndex: workspaceView.currentTabIndex

            onNavigateTo: (pageKey) => navigateToPage(pageKey)
            onNavigateToTab: (pageKey, tabIndex) => {
                mainWindow.currentPage = "workspace"
                workspaceView.switchTab(tabIndex)
            }
            onPlatformCardClicked: {
                mainWindow.currentPage = "platformDashboard"
                platformDashboardView.loadData()
            }
            onActiveProjectCardClicked: {
                if (mainWindow.currentProjectId !== "") {
                    mainWindow.currentPage = "workspace"
                    workspaceView.switchTab(0)
                } else {
                    mainWindow.currentPage = "projectList"
                }
            }
        }

        // ── 页面内容区（StackLayout，保留 9 个分支不变）
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.bottomMargin: 48
            currentIndex: {
                if (mainWindow.currentPage === "projectList") return 0
                if (mainWindow.currentPage === "workspace") return 1
                if (mainWindow.currentPage === "changeCenter") return 2
                if (mainWindow.currentPage === "specCenter") return 3
                if (mainWindow.currentPage === "reportCenter") return 4
                if (mainWindow.currentPage === "templateManage") return 5
                if (mainWindow.currentPage === "settings") return 6
                if (mainWindow.currentPage === "platformDashboard") return 7
                if (mainWindow.currentPage === "modbusDebugger") return 8
                return 0
            }

            // 0. 项目列表页
            ProjectListView {
                id: projectListView
                onRequestNewProject: dialogLayer.openNewProject()
                onRequestImportProject: dialogLayer.openImportProject()
                onProjectClicked: (projectId, projectName) => mainWindow.selectProjectContext(projectId, projectName)
            }

            // 1. 项目工作区页
            WorkspaceView {
                id: workspaceView
                onBackToProjectList: mainWindow.currentPage = "projectList"
                onRequestEditProject: dialogLayer.openEditProject(workspaceView.currentProjectId, workspaceView.currentProjectName, workspaceView.currentProjectDetail)
                onRequestDeleteProject: dialogLayer.openDeleteProject(workspaceView.currentProjectId, workspaceView.currentProjectName)
                onRequestApplyTemplate: dialogLayer.openApplyTemplate(workspaceView.currentProjectId, workspaceView.currentProjectName)
            }

            // 2. 变更中心页
            ChangeCenterView {
                id: changeCenterView
                onRequestNewChange: dialogLayer.openNewChange(mainWindow.currentProjectId)
                onRequestEditChange: dialogLayer.openEditChange(changeCenterView.selectedChangeDetail)
                onRequestReconcileLedger: dialogLayer.openReconcileLedger(changeCenterView.selectedProjectId)
                onBackToProjectList: mainWindow.currentPage = "projectList"
            }

            // 3. 规范中心页
            SpecCenterView {
                id: specCenterView
                onBackToProjectList: mainWindow.currentPage = "projectList"
                onRequestGenerateSpecIndex: dialogLayer.openSpecIndex()
                onRequestGenerateSpecReport: dialogLayer.openSpecReport()
                onRequestCheckSpecFrontmatter: dialogLayer.openSpecFrontmatter()
            }

            // 4. 报告中心页
            ReportView {
                id: reportView
                onBackToProjectList: mainWindow.currentPage = "projectList"
            }

            // 5. 模板管理页
            TemplateView {
                id: templateView
                currentProjectId: mainWindow.currentProjectId
                onBackToProjectList: mainWindow.currentPage = "projectList"
            }

            // 6. 设置页
            SettingsView {
                id: settingsView
                onBackToProjectList: mainWindow.currentPage = "projectList"
                onRequestArchivePmSession: dialogLayer.openPmSessionArchive()
                onRequestShowAbout: dialogLayer.openAbout()
                onRequestShowGlobalSettings: dialogLayer.openGlobalSettings(settingsView.settingsData.workspace_root || "")
            }

            // 7. 平台驾驶舱大盘页
            PlatformDashboardView {
                id: platformDashboardView
                onBackToProjectList: mainWindow.currentPage = "projectList"
            }

            // 8. Modbus 联调工坊
            ModbusDebuggerView {
                id: modbusDebuggerView
            }
        }
    }

    // ── 对话框层（组件化）
    DialogLayer {
        id: dialogLayer

        onProjectCreated: (projectId) => {
            console.log("[QML main] 项目创建成功: " + projectId)
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                workbenchBridge.refreshProjects()
                projectModel.setProjects(workbenchBridge.listProjects())
            }
        }
        onProjectImported: (projectId) => {
            console.log("[QML main] 项目导入成功: " + projectId)
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                workbenchBridge.refreshProjects()
                projectModel.setProjects(workbenchBridge.listProjects())
            }
        }
        onChangeCreated: (changeNumber) => {
            console.log("[QML main] 变更单创建成功: " + changeNumber)
            if (typeof changeBridge !== "undefined" && changeBridge !== null) {
                changeBridge.refreshChanges(); changeBridge.listAllChanges()
            }
            if (mainWindow.currentPage === "changeCenter") changeCenterView.loadChanges()
        }
        onChangeSaved: (changeNumber) => {
            console.log("[QML main] 变更单更新成功: " + changeNumber)
            if (typeof changeBridge !== "undefined" && changeBridge !== null) {
                changeBridge.refreshChanges(); changeBridge.listAllChanges()
            }
            if (mainWindow.currentPage === "changeCenter") {
                changeCenterView.loadChanges()
                changeCenterView.loadChangeDetail(changeNumber)
            }
        }
        onProjectSaved: (projectId) => {
            console.log("[QML main] 项目编辑成功: " + projectId)
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                workbenchBridge.refreshProjects()
                projectModel.setProjects(workbenchBridge.listProjects())
                workspaceView.currentProjectDetail = workbenchBridge.getProjectById(projectId)
            }
        }
        onProjectDeleted: (projectId) => {
            console.log("[QML main] 删除项目: " + projectId)
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                var result = workbenchBridge.deleteProject(projectId)
                if (result && result.success) {
                    workbenchBridge.refreshProjects()
                    projectModel.setProjects(workbenchBridge.listProjects())
                    mainWindow.currentPage = "projectList"
                } else {
                    console.warn("[QML main] 删除失败: " + (result ? result.message : ""))
                }
            }
        }
        onLedgerReconciled: {
            console.log("[QML main] 台账对账自动修复完成")
            changeCenterView.loadChanges()
        }
        onPmInitialized: (projectId) => {
            console.log("[QML main] 确认初始化 PM: " + projectId)
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                var result = workbenchBridge.initializeProjectPm(projectId)
                if (result && result.success) {
                    workbenchBridge.refreshProjects()
                    projectModel.setProjects(workbenchBridge.listProjects())
                    workspaceView.setProject(workspaceView.currentProjectId, workspaceView.currentProjectName)
                } else {
                    console.warn("[QML main] 初始化项目 PM 失败: " + (result ? result.message : ""))
                }
            }
        }
        onPmSessionArchived:      console.log("[QML main] PM_SESSION 归档完成")
        onSpecIndexGenerated:     { console.log("[QML main] 规范索引生成完成"); specCenterView.loadEntries() }
        onSpecReportGenerated:    console.log("[QML main] 规范报告生成完成")
        onSpecFrontmatterChecked: console.log("[QML main] 规范 Frontmatter 检查完成")
        onGlobalSettingsSaved: (wsRoot) => {
            console.log("[QML main] 全局配置保存成功, workspaceRoot: " + wsRoot)
            var res = workbenchBridge.saveWorkspaceRoot(wsRoot)
            if (res && res.config_saved) {
                settingsView.resultMessage = res.message || "配置已保存"
                settingsView.loadData()
                if (res.runtime_reloaded) {
                    workbenchBridge.refreshProjects()
                    projectModel.setProjects(workbenchBridge.listProjects())
                }
            } else {
                settingsView.resultMessage = "保存失败: " + (res ? res.message : "未知错误")
            }
        }
    }

    // ── 状态栏
    Rectangle {
        id: statusbar
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 24; color: Theme.surface
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 1; color: Theme.glassBorder }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: Theme.spacingMd; anchors.rightMargin: Theme.spacingMd
            spacing: Theme.spacingMd
            Text { text: "● 就绪"; color: Theme.success; font.pixelSize: Theme.fontSizeXs }
            Text { text: "项目: " + (projectModel ? projectModel.count : 0); color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs }
            Text { text: "变更: " + (changeBridge ? changeBridge.changeCount : 0); color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs }
            Item { Layout.fillWidth: true }
            Text { text: "QML V1.1.0"; color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs }
        }
    }

    // ── 文件监听同步工具栏（全局常驻浮动）
    Rectangle {
        id: fileWatcherToolbar
        anchors.right: parent.right; anchors.bottom: statusbar.top
        anchors.rightMargin: Theme.spacingMd; anchors.bottomMargin: Theme.spacingSm
        width: watcherToolbarExpanded ? 460 : 52; height: 40
        radius: Theme.radiusMd; color: Qt.rgba(0.02, 0.02, 0.09, 0.92)
        border.color: Theme.glassBorder; border.width: 1; z: 100
        Behavior on width { NumberAnimation { duration: 150 } }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: Theme.spacingSm; anchors.rightMargin: Theme.spacingSm
            spacing: Theme.spacingSm
            PrimaryButton {
                text: syncInProgress ? "⏳ 同步中" : "🔄 同步"; type: "ghost"
                Layout.preferredHeight: 32; enabled: !syncInProgress; visible: watcherToolbarExpanded
                onClicked: { if (typeof fileWatcherBridge !== "undefined" && fileWatcherBridge !== null) fileWatcherBridge.syncNow() }
            }
            Switch {
                checked: mainWindow.watcherEnabled; Layout.preferredHeight: 32; visible: watcherToolbarExpanded
                onToggled: { if (typeof fileWatcherBridge !== "undefined" && fileWatcherBridge !== null) fileWatcherBridge.toggleWatcher(checked) }
            }
            Text { text: "监听"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeXs; visible: watcherToolbarExpanded }
            Text {
                text: watcherStatusText; color: syncInProgress ? Theme.primary : Theme.textSecondary
                font.pixelSize: Theme.fontSizeXs; Layout.fillWidth: true; elide: Text.ElideRight; visible: watcherToolbarExpanded
            }
            PrimaryButton {
                text: watcherToolbarExpanded ? "›" : "‹"; type: "ghost"
                Layout.preferredWidth: 32; Layout.preferredHeight: 32
                onClicked: mainWindow.watcherToolbarExpanded = !mainWindow.watcherToolbarExpanded
            }
        }
    }

    // ── FileWatcherBridge 信号连接（不变）
    Connections {
        target: typeof fileWatcherBridge !== "undefined" && fileWatcherBridge !== null ? fileWatcherBridge : null
        function onWatcherToggled(enabled) { mainWindow.watcherEnabled = enabled }
        function onSyncStarted() { mainWindow.syncInProgress = true; mainWindow.watcherStatusText = "同步中..." }
        function onSyncFinished(projects, changes, ms) {
            mainWindow.syncInProgress = false
            var t = typeof fileWatcherBridge !== "undefined" && fileWatcherBridge !== null ? fileWatcherBridge.lastSyncTime() : ""
            mainWindow.watcherStatusText = "已同步 " + projects + " 项 · " + t
            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                workbenchBridge.refreshProjects()
                projectModel.setProjects(workbenchBridge.listProjects())
            }
            if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService) changeBridge.refreshChanges()
            console.log("[FileWatcher] 同步完成: " + projects + " 项目, " + changes + " 变更, " + ms + "ms")
        }
        function onSyncError(msg) {
            mainWindow.syncInProgress = false; mainWindow.watcherStatusText = "同步失败: " + msg
            console.warn("[FileWatcher] 同步失败: " + msg)
        }
    }

    // ── workbenchBridge 信号连接（不变）
    Connections {
        target: typeof workbenchBridge !== "undefined" && workbenchBridge !== null ? workbenchBridge : null
        function onProjectSelected(projectId, projectName) { mainWindow.selectProjectContext(projectId, projectName) }
    }

    // ── 启动初始化（不变）
    Component.onCompleted: {
        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
            console.log("[QML main] workbenchBridge 可用，初始化数据...")
            var projects = workbenchBridge.listProjects()
            console.log("[QML main] 加载了 " + projects.length + " 个项目")
            projectModel.setProjects(projects)
        } else {
            console.warn("[QML main] workbenchBridge 未注入")
        }
        if (typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService) changeBridge.listAllChanges()
    }
}
