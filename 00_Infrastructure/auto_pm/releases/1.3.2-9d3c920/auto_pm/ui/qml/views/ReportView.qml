// ReportView.qml - V0.8.0 Phase 2 报告中心（CHG-091?
//
// 2×2 卡片网格 + 柱状图，对应 QWidget ?report_page.py?
//   ┌─ 项目概览 ─?┌─ 阶段分布 ─?
//   ┌─ 业务线分布 ┌─ 变更统计 ─┘
//
// 数据流：deliveryBridge.getProjectReport() / deliveryBridge.getChangeReport() → 内部 ListModel → 渲染
// 三重守卫：typeof deliveryBridge === "undefined" || deliveryBridge === null || !deliveryBridge.hasService

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 信号 ────────────────────────────────────────────
    signal backToProjectList()

    // ── 内部数据模型 ────────────────────────────────────
    ListModel { id: projectOverviewModel }   // 项目概览：{label, value, max}
    ListModel { id: phaseModel }              // 阶段分布
    ListModel { id: blModel }                 // 业务线分布
    ListModel { id: changeModel }             // 变更统计
    property string projectSummary: ""        // "总项目数: 13"
    property string changeSummary: ""        // "总变更: 20"
    property string errorMessage: ""

    // ── 加载数据 ────────────────────────────────────────
    function loadData() {
        if (typeof deliveryBridge === "undefined" || deliveryBridge === null || !deliveryBridge.hasService) {
            console.warn("[QML] ReportView: ReportService 未启用")
            errorMessage = "ReportService 未启用"
            projectOverviewModel.clear()
            phaseModel.clear()
            blModel.clear()
            changeModel.clear()
            return
        }
        errorMessage = ""
        var projectData = deliveryBridge.getProjectReport()
        var changeData = deliveryBridge.getChangeReport()

        if (projectData && projectData.error) {
            errorMessage = projectData.error
            return
        }
        if (changeData && changeData.error) {
            errorMessage = changeData.error
            return
        }

        // 项目概览：按技术栈
        projectSummary = "总项目数: " + (projectData.total || 0)
        var byStack = projectData.by_stack || {}
        var stackMax = 0
        for (var k in byStack) {
            if (byStack[k] > stackMax) stackMax = byStack[k]
        }
        projectOverviewModel.clear()
        var stackOrder = ["plc", "python", "unknown"]
        var stackLabels = {"plc": "PLC", "python": "Python", "unknown": "未知"}
        for (var i = 0; i < stackOrder.length; i++) {
            var key = stackOrder[i]
            projectOverviewModel.append({
                "label": stackLabels[key] || key,
                "value": byStack[key] || 0,
                "max": stackMax
            })
        }

        // 阶段分布
        var byPhase = projectData.by_phase || {}
        var phaseMax = 0
        for (var k2 in byPhase) {
            if (byPhase[k2] > phaseMax) phaseMax = byPhase[k2]
        }
        phaseModel.clear()
        var phaseOrder = ["initiating", "planning", "developing", "commissioning", "production", "archived"]
        var phaseLabels = {
            "initiating": "启动",
            "planning": "规划",
            "developing": "开发中",
            "commissioning": "调试",
            "production": "生产",
            "archived": "已归档",
        }
        for (var j = 0; j < phaseOrder.length; j++) {
            var pkey = phaseOrder[j]
            phaseModel.append({
                "label": phaseLabels[pkey] || pkey,
                "value": byPhase[pkey] || 0,
                "max": phaseMax
            })
        }

        // 业务线分布
        var byBl = projectData.by_business_line || {}
        var blMax = 0
        for (var k3 in byBl) {
            if (byBl[k3] > blMax) blMax = byBl[k3]
        }
        blModel.clear()
        var blOrder = ["SW", "DJ", "ZD", "XT", "WX"]
        for (var m = 0; m < blOrder.length; m++) {
            var blKey = blOrder[m]
            if (byBl[blKey] !== undefined) {
                blModel.append({
                    "label": blKey,
                    "value": byBl[blKey] || 0,
                    "max": blMax
                })
            }
        }

        // 变更统计：按状态
        changeSummary = "总变更: " + (changeData.total || 0)
        var byStatus = changeData.by_status || {}
        var statusMax = 0
        for (var k4 in byStatus) {
            if (byStatus[k4] > statusMax) statusMax = byStatus[k4]
        }
        changeModel.clear()
        var statusOrder = [
            "draft", "submitted", "under_review", "approved",
            "implementing", "pending_acceptance", "accepting",
            "completed", "closed", "conditionally_approved", "rejected"
        ]
        var statusLabels = {
            "draft": "草稿",
            "submitted": "已提交",
            "under_review": "审核中",
            "approved": "已批准",
            "conditionally_approved": "有条件批准",
            "rejected": "已驳回",
            "implementing": "实施中",
            "pending_acceptance": "待验收",
            "accepting": "验收中",
            "completed": "已完成",
            "closed": "已关闭",
        }
        var rendered = {}
        for (var n = 0; n < statusOrder.length; n++) {
            var skey = statusOrder[n]
            if (byStatus[skey] !== undefined) {
                changeModel.append({
                    "label": statusLabels[skey] || skey,
                    "value": byStatus[skey] || 0,
                    "max": statusMax
                })
                rendered[skey] = true
            }
        }
        // 兜底：未在预定义顺序中的状态
        for (var s2 in byStatus) {
            if (!rendered[s2]) {
                changeModel.append({
                    "label": statusLabels[s2] || s2,
                    "value": byStatus[s2] || 0,
                    "max": statusMax
                })
            }
        }
    }

    // ── 顶部导航 ────────────────────────────────────────
    Rectangle {
        id: navBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 88
        color: Theme.surface

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Text {
                    text: "📊 报告中心"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "刷新"
                    onClicked: loadData()
                }

                PrimaryButton {
                    text: "返回"
                    type: "ghost"
                    onClicked: root.backToProjectList()
                }
            }

            Text {
                text: "项目与变更统计概览"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }
        }
    }

    // ── 错误状态 ────────────────────────────────────────
    Text {
        visible: errorMessage !== ""
        anchors.centerIn: parent
        text: "?" + errorMessage
        color: Theme.error
        font.pixelSize: Theme.fontSizeMd
    }

    // ── 2×2 卡片网格 ────────────────────────────────────
    GridLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: navBar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacingMd
        columns: 2
        rows: 2
        columnSpacing: Theme.spacingMd
        rowSpacing: Theme.spacingMd
        visible: errorMessage === ""

        // 卡片 1：项目概览
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingXs

                Text {
                    text: "项目概览"
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    color: Theme.primary
                }
                Text {
                    text: projectSummary
                    font.pixelSize: Theme.fontSizeSm
                    font.bold: true
                    color: Theme.textPrimary
                }

                Repeater {
                    model: projectOverviewModel
                    delegate: BarRow {}
                }

                Item { Layout.fillHeight: true }
            }
        }

        // 卡片 2：阶段分布
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingXs

                Text {
                    text: "阶段分布"
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    color: Theme.primary
                }

                Repeater {
                    model: phaseModel
                    delegate: BarRow {}
                }

                Item { Layout.fillHeight: true }
            }
        }

        // 卡片 3：业务线分布
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingXs

                Text {
                    text: "业务线分布"
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    color: Theme.primary
                }

                Repeater {
                    model: blModel
                    delegate: BarRow {}
                }

                Item { Layout.fillHeight: true }
            }
        }

        // 卡片 4：变更统计
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingXs

                Text {
                    text: "变更统计"
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    color: Theme.primary
                }
                Text {
                    text: changeSummary
                    font.pixelSize: Theme.fontSizeSm
                    font.bold: true
                    color: Theme.textPrimary
                }

                Repeater {
                    model: changeModel
                    delegate: BarRow {}
                }

                Item { Layout.fillHeight: true }
            }
        }
    }

    Component.onCompleted: loadData()
}

