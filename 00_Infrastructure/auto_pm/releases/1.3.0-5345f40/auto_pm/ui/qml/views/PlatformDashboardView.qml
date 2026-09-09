// PlatformDashboardView.qml - 平台驾驶舱大盘视图（CHG-106 T6）
//
// 对齐 V7 原型 view-platform-dashboard（012_UI架构原型_V7.html L985-1072）
// 三大区块：KPI 网格（4 卡片）+ 状态机 + 活动时间线
//
// 数据流：
//   workbenchBridge.getDashboardSummary() → KPI 卡片 + 时间线
//   workbenchBridge.getActiveChangeStatus(projectId) → 状态机

import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 公开属性 ────────────────────────────────────────
    property string platformProjectId: "SW-2026-008"  // 平台项目编号（auto-pm 自身）

    // ── 内部状态 ────────────────────────────────────────
    property var _snapshot: ({})           // 驾驶舱快照数据
    property var _activeChangeStatus: ({}) // 活跃变更状态机数据
    property bool _dataLoaded: false
    property bool _loading: false          // CHG-107: 加载状态（控制 LoadingOverlay）

    // ── 信号 ────────────────────────────────────────────
    signal backToProjectList()

    // ── 数据加载 ────────────────────────────────────────
    function loadData() {
        if (typeof workbenchBridge === "undefined" || workbenchBridge === null) {
            console.warn("[QML] PlatformDashboardView: workbenchBridge 未初始化")
            return
        }

        console.log("[QML] PlatformDashboardView: 加载数据...")
        _loading = true  // CHG-107: 显示 LoadingOverlay
        try {
            _snapshot = workbenchBridge.getDashboardSummary() || {}
            _activeChangeStatus = workbenchBridge.getActiveChangeStatus(root.platformProjectId) || {}
            _dataLoaded = true
        } catch (e) {
            console.error("[QML] PlatformDashboardView 加载数据发生错误: " + e)
        } finally {
            _loading = false  // CHG-107: 隐藏 LoadingOverlay
        }
        console.log("[QML] PlatformDashboardView: 数据加载完成, projects=" + (_snapshot.total_projects || 0))
    }

    // ── 辅助函数 ────────────────────────────────────────
    function _phaseLabel(): string {
        var phases = _snapshot.phase_counts || {}
        if (phases.initiating > 0) return "Initiating"
        if (phases.planning > 0) return "Planning"
        if (phases.developing > 0) return "Developing"
        if (phases.commissioning > 0) return "Commissioning"
        if (phases.production > 0) return "Production"
        return "—"
    }

    function _projectsSubtitle(): string {
        var phases = _snapshot.phase_counts || {}
        var dev = phases.developing || 0
        var comm = phases.commissioning || 0
        var prod = phases.production || 0
        return "在研 " + dev + " · 调试 " + comm + " · 生产 " + prod
    }

    function _testSubtitle(): string {
        var total = _snapshot.test_total || 0
        if (total > 0) {
            return total + " 个测试用例"
        }
        return "暂无测试数据"
    }

    function _activeChangeValue(): string {
        if (_activeChangeStatus.active) {
            return _activeChangeStatus.change_number || "—"
        }
        return "无活跃变更"
    }

    function _activeChangeSubtitle(): string {
        if (_activeChangeStatus.active) {
            return _activeChangeStatus.title || ""
        }
        return "所有变更已闭环"
    }

    function _formatActivities(activities): var {
        return activities || []
    }

    // ── 主布局 ──────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingLg

        // ── 页面头部 ────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true

                Text {
                    text: "SW-2026-008_auto-pm_自动化项目管理工具"
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeXxl
                    font.bold: true
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Text {
                    text: "📁 Python自动化项目总库 / 02_在研项目 / SW-2026-008"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeMd
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }

            Item { Layout.fillWidth: true }

            // 操作按钮（占位，后续接入）
            Rectangle {
                width: 120
                height: 32
                radius: Theme.radiusSm
                color: "transparent"
                border.color: Theme.glassBorder
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "💻 CLI 终端"
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSizeSm
                }
            }
        }

        // ── KPI 网格（4 卡片）────────────────────────────
        KpiGrid {
            Layout.fillWidth: true
            Layout.preferredHeight: 120

            // 卡片 1：纳管项目总数
            KpiCard {
                title: "纳管项目总数"
                value: String(root._snapshot.total_projects || 0)
                valueSuffix: "个"
                subtitle: root._projectsSubtitle()
                iconText: "📦"
                iconColor: Theme.primary
            }

            // 卡片 2：当前开发阶段
            KpiCard {
                title: "当前开发阶段"
                value: root._phaseLabel()
                subtitle: "平台工具自身迭代"
                iconText: "🏁"
                iconColor: Theme.phaseDeveloping
            }

            // 卡片 3：自动化测试通过率
            KpiCard {
                title: "自动化测试通过率"
                value: (root._snapshot.test_pass_rate || 0).toFixed(1) + "%"
                subtitle: root._testSubtitle()
                iconText: (root._snapshot.test_pass_rate || 0) >= 95 ? "✓" : "⚠"
                iconColor: (root._snapshot.test_pass_rate || 0) >= 95 ? Theme.success :
                           (root._snapshot.test_pass_rate || 0) >= 80 ? Theme.warning : Theme.error
                valueColor: (root._snapshot.test_pass_rate || 0) >= 95 ? Theme.success :
                           (root._snapshot.test_pass_rate || 0) >= 80 ? Theme.warning : Theme.error
            }

            // 卡片 4：活跃变更单
            KpiCard {
                title: "活跃变更单"
                value: root._activeChangeValue()
                subtitle: root._activeChangeSubtitle()
                iconText: "🔄"
                iconColor: root._activeChangeStatus.active ? Theme.primary : Theme.textMuted
                valueColor: root._activeChangeStatus.active ? Theme.primary : Theme.textMuted
            }
        }

        // ── 主体：状态机 + 时间线 ────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spacingLg

            // 左侧：状态机（占 60%）
            DashboardStateMachine {
                Layout.preferredWidth: root.width * 0.6 - Theme.spacingLg
                Layout.fillHeight: true
                title: root._activeChangeStatus.active ?
                    "主线流转 (" + root._activeChangeStatus.change_number + ")" : "主线流转"
                tagText: root._activeChangeStatus.active ? root._activeChangeStatus.state_machine.current_node_name : ""
                stateMachine: root._activeChangeStatus.state_machine || ({
                    "current_node": 0,
                    "current_node_name": "",
                    "progress": 0,
                    "nodes": []
                })
            }

            // 右侧：活动时间线（占 40%）
            ActivityTimeline {
                Layout.preferredWidth: root.width * 0.4 - Theme.spacingLg
                Layout.fillHeight: true
                activities: root._formatActivities(root._snapshot.recent_activities)
            }
        }
    }

    // ── 加载遮罩（CHG-107 T3：异步加载指示）──────────
    LoadingOverlay {
        id: loadingOverlay
        anchors.fill: parent
        active: root._loading
        message: "加载驾驶舱数据..."
    }

    // ── 初始化 ────────────────────────────────────────
    Component.onCompleted: {
        loadData()
    }
}
