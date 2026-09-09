// AppSidebar.qml — 三轨道分组侧边栏 V1.0.0
// 数据驱动：新增导航入口只需增加 SidebarNavItem，不改布局逻辑
// 预留扩展：轨道分组标题、信号统一从 navigateTo / navigateToTab 发出
// 来自 main.qml L238-L818（侧边栏整体）

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Rectangle {
    id: sidebar

    // ── 公开属性（由 main.qml 绑定）
    property string currentPage: ""
    property string currentProjectId: ""
    property string currentProjectName: ""
    property string currentProjectPhase: "developing"
    property string currentProjectStack: "python"
    property int    changeBadgeCount: 0
    property int    projectCount: 0
    property int    workspaceCurrentTabIndex: 0

    // ── 信号
    signal navigateTo(string pageKey)
    signal navigateToTab(string pageKey, int tabIndex)
    signal platformCardClicked()
    signal activeProjectCardClicked()

    // ── 外观
    color: Theme.sidebarBg

    Rectangle {
        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        width: 1; color: Theme.glassBorder
    }

    ScrollView {
        anchors.fill: parent
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: parent.width - 24
            x: 12; y: 12
            spacing: Theme.spacingSm

            // ═══ 轨道 1: Platform Cockpit ═════════════════════
            Text {
                text: "PLATFORM COCKPIT 🚀"
                color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs
                font.bold: true; font.letterSpacing: 1.5
                Layout.topMargin: Theme.spacingSm
            }

            ContextCard {
                Layout.fillWidth: true
                projectId: "SW-2026-008"; projectName: "auto-pm 研发管理平台"
                phase: "developing"; stack: "python"; hasProject: true
                onClicked: sidebar.platformCardClicked()
            }

            SidebarNavItem {
                pageKey: "platformDashboard"; icon: "📊"; label: "平台驾驶舱大盘"
                isActive: sidebar.currentPage === "platformDashboard"
                onNavClicked: (k) => sidebar.navigateTo(k)
            }
            SidebarNavItem {
                pageKey: "changeCenter"; icon: "🔄"; label: "平台变更管控"
                isActive: sidebar.currentPage === "changeCenter"
                badgeCount: sidebar.changeBadgeCount
                onNavClicked: (k) => sidebar.navigateTo(k)
            }
            SidebarNavItem {
                pageKey: "specCenter"; icon: "📐"; label: "平台架构规范检查"
                isActive: sidebar.currentPage === "specCenter"
                onNavClicked: (k) => sidebar.navigateTo(k)
            }
            SidebarNavItem {
                pageKey: "reportCenter"; icon: "📄"; label: "平台迭代与发布"
                isActive: sidebar.currentPage === "reportCenter"
                onNavClicked: (k) => sidebar.navigateTo(k)
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder; Layout.topMargin: Theme.spacingSm; Layout.bottomMargin: Theme.spacingSm }

            // ═══ 轨道 2: Workspace ════════════════════════════
            Text {
                text: "WORKSPACE 🌐"
                color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs
                font.bold: true; font.letterSpacing: 1.5
            }

            SidebarNavItem {
                pageKey: "projectList"; icon: "🏠"; label: "业务项目大厅"
                isActive: sidebar.currentPage === "projectList"
                onNavClicked: (k) => sidebar.navigateTo(k)
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder; Layout.topMargin: Theme.spacingSm; Layout.bottomMargin: Theme.spacingSm }

            // ═══ 轨道 3: Active Business Project ═════════════
            Text {
                text: "ACTIVE BUSINESS PROJECT 💻"
                color: Theme.textMuted; font.pixelSize: Theme.fontSizeXs
                font.bold: true; font.letterSpacing: 1.5
            }

            ContextCard {
                Layout.fillWidth: true
                projectId: sidebar.currentProjectId
                projectName: sidebar.currentProjectName
                phase: sidebar.currentProjectPhase
                stack: sidebar.currentProjectStack
                hasProject: sidebar.currentProjectId !== ""
                onClicked: sidebar.activeProjectCardClicked()
            }

            SidebarNavItem {
                pageKey: "workspace"; icon: "📊"; label: "工程健康度概览"
                isActive: sidebar.currentPage === "workspace" && sidebar.workspaceCurrentTabIndex === 0
                navEnabled: sidebar.currentProjectId !== ""
                onNavClicked: (k) => sidebar.navigateToTab(k, 0)
            }
            SidebarNavItem {
                pageKey: "workspace"; icon: "📋"; label: "变量表与 IO 资产"
                isActive: sidebar.currentPage === "workspace" && sidebar.workspaceCurrentTabIndex === 4
                navEnabled: sidebar.currentProjectId !== ""
                onNavClicked: (k) => sidebar.navigateToTab(k, 4)
            }
            SidebarNavItem {
                pageKey: "workspace"; icon: "🔀"; label: "工程变更控制矩阵"
                isActive: sidebar.currentPage === "workspace" && sidebar.workspaceCurrentTabIndex === 1
                navEnabled: sidebar.currentProjectId !== ""
                onNavClicked: (k) => sidebar.navigateToTab(k, 1)
            }
            SidebarNavItem {
                pageKey: "workspace"; icon: "🛡️"; label: "工程规范与死区检查"
                isActive: sidebar.currentPage === "workspace" && sidebar.workspaceCurrentTabIndex === 2
                navEnabled: sidebar.currentProjectId !== ""
                onNavClicked: (k) => sidebar.navigateToTab(k, 2)
            }
            SidebarNavItem {
                pageKey: "workspace"; icon: "🚀"; label: "工程交付与试运行报告"
                isActive: sidebar.currentPage === "workspace" && sidebar.workspaceCurrentTabIndex === 3
                navEnabled: sidebar.currentProjectId !== ""
                onNavClicked: (k) => sidebar.navigateToTab(k, 3)
            }

            Item { Layout.fillHeight: true }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder; Layout.bottomMargin: Theme.spacingSm }

            // ═══ 轨道 4: Settings ═════════════════════════════
            SidebarNavItem {
                pageKey: "settings"; icon: "⚙️"; label: "设置"
                isActive: sidebar.currentPage === "settings"
                onNavClicked: (k) => sidebar.navigateTo(k)
            }

            // ═══ 轨道 5: 公共工具 (Modbus，绿色主题) ═══════════
            SidebarNavItem {
                pageKey: "modbusDebugger"; icon: "⚡"; label: "Modbus 联调工坊"
                isActive: sidebar.currentPage === "modbusDebugger"
                accentColor: Qt.rgba(0.38, 0.71, 0.51, 0.85)
                onNavClicked: (k) => sidebar.navigateTo(k)
            }

            BackendStatus {
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingSm
                connected: typeof systemBridge !== "undefined" && systemBridge !== null && systemBridge.hasService
            }
        }
    }
}
