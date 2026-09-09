// ChangeCenterView.qml - V0.9.3 变更中心（Split View + Ledger View + 详情面板）
//
// CHG-SCPT-2026-103 T1+T3：视觉升级 + 视图切换 + 集成 ChangeDetailPanel/LedgerTableView
//
// 三种视图模式：
//   1. Split View（默认）：左侧变更单列表 + 右侧 ChangeDetailPanel 详情面板
//   2. Ledger View：全宽 LedgerTableView 表格视图
//
// 数据流：changeBridge.listAllChanges() → filteredModel → ListView/LedgerTableView
//         → 点击 → loadChangeDetail() → ChangeDetailPanel.changeDetail

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 公开状态 ────────────────────────────────────────
    property string selectedChangeNumber: ""
    property string selectedProjectId: ""
    property var selectedChangeDetail: ({})
    property string statusFilter: "all"
    property string domainFilter: "all"
    property string searchText: ""
    property string viewMode: "split"  // "split" | "ledger"
    property var pendingHandoffs: []

    // ── 信号 ────────────────────────────────────────────
    signal backToProjectList()
    signal requestNewChange()
    signal requestEditChange()
    signal requestReconcileLedger()  // M5 CHG-118: 台账对账

    // ── 过滤后的展示模型 ────────────────────────────────
    ListModel { id: filteredModel }

    // ── 加载数据 ────────────────────────────────────────
    function loadChanges() {
        if (typeof changeBridge === "undefined" || changeBridge === null || !changeBridge.hasService) {
            console.warn("[QML] ChangeCenterView: ChangeService 未启用")
            filteredModel.clear()
            return
        }
        console.log("[QML] ChangeCenterView: 加载变更列表...")
        var changes = changeBridge.listAllChanges()
        console.log("[QML] ChangeCenterView: 收到 " + changes.length + " 条变更")
        applyFilters(changes)
    }

    function refreshPendingHandoffs() {
        if (typeof aiContextBridge === "undefined" || aiContextBridge === null) {
            pendingHandoffs = []
            return
        }
        pendingHandoffs = aiContextBridge.listPendingHandoffs(root.selectedProjectId) || []
    }

    function preparePmClosure() {
        if (pendingHandoffs.length === 0 || typeof aiContextBridge === "undefined") return
        var handoff = pendingHandoffs[0]
        var detail = root.selectedChangeDetail || {}
        var result = aiContextBridge.writePmClosureContext(
            handoff.request_id,
            root.selectedProjectId || handoff.project_id,
            mainWindow.currentProjectName,
            mainWindow.currentProjectStack,
            mainWindow.currentProjectPhase,
            root.selectedChangeNumber,
            detail.title || "",
            mainWindow.currentPage
        )
        if (result && result.success) {
            console.log("[QML] PM 收口上下文已写入: " + result.file)
        } else {
            console.warn("[QML] PM 收口上下文写入失败: " + (result ? result.message : "未知错误"))
        }
    }

    function applyFilters(changes) {
        var source = changes || (typeof changeBridge !== "undefined" && changeBridge !== null ? changeBridge.listAllChanges() : [])
        var filtered = []

        for (var i = 0; i < source.length; i++) {
            var c = source[i]
            if (root.statusFilter !== "all" && c.status !== root.statusFilter) continue
            if (root.domainFilter !== "all" && c.domain !== root.domainFilter) continue
            if (root.searchText !== "") {
                var q = root.searchText.toLowerCase()
                if (!String(c.change_number).toLowerCase().includes(q) &&
                    !String(c.title).toLowerCase().includes(q) &&
                    !String(c.project_id).toLowerCase().includes(q)) {
                    continue
                }
            }
            filtered.push(c)
        }

        // 按申请日期及变更单号降序排列（最新排在最上面）
        filtered.sort(function(a, b) {
            var dateA = a.apply_date || ""
            var dateB = b.apply_date || ""
            if (dateA !== dateB) {
                return dateB.localeCompare(dateA)
            }
            var numA = a.change_number || ""
            var numB = b.change_number || ""
            return numB.localeCompare(numA)
        })

        filteredModel.clear()
        for (var j = 0; j < filtered.length; j++) {
            filteredModel.append(filtered[j])
        }
    }

    function loadChangeDetail(changeNumber, projectId) {
        if (typeof changeBridge === "undefined" || changeBridge === null) return
        root.selectedChangeNumber = changeNumber
        root.selectedProjectId = projectId || ""
        root.selectedChangeDetail = changeBridge.getChangeRequest(changeNumber, root.selectedProjectId)
        root.refreshPendingHandoffs()
        console.log("[QML] ChangeCenterView: 加载变更详情 " + changeNumber + " (项目: " + root.selectedProjectId + ") →" + (Object.keys(root.selectedChangeDetail).length) + " 字段")
    }

    // ── Ledger View 行点击 → 切回 Split View 并选中 ────
    function onLedgerChangeSelected(changeNumber, projectId) {
        root.viewMode = "split"
        root.loadChangeDetail(changeNumber, projectId)
    }

    // ── ChangeDetailPanel 状态流转后刷新 ────────────────
    function onDetailStatusChanged() {
        if (typeof changeBridge !== "undefined" && changeBridge !== null) {
            changeBridge.refreshChanges()
        }
        root.loadChanges()
        if (root.selectedChangeNumber !== "") {
            root.loadChangeDetail(root.selectedChangeNumber, root.selectedProjectId)
        }
    }

    // ── 顶部导航 ────────────────────────────────────────
    GlassPanel {
        id: navBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 88

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                PrimaryButton {
                    text: "‹返回"
                    type: "ghost"
                    Layout.preferredWidth: 80
                    onClicked: root.backToProjectList()
                }

                Text {
                    text: "变更中心"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                // ── 视图切换 toggle ────────────────────────
                RowLayout {
                    spacing: 0

                    PrimaryButton {
                        text: "Split View"
                        type: root.viewMode === "split" ? "primary" : "ghost"
                        Layout.preferredWidth: 90
                        Layout.preferredHeight: 28
                        onClicked: root.viewMode = "split"
                    }

                    PrimaryButton {
                        text: "Ledger View"
                        type: root.viewMode === "ledger" ? "primary" : "ghost"
                        Layout.preferredWidth: 90
                        Layout.preferredHeight: 28
                        onClicked: root.viewMode = "ledger"
                    }
                }

                PrimaryButton {
                    text: "刷新"
                    type: "ghost"
                    Layout.preferredWidth: 60
                    enabled: typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService
                    onClicked: {
                        if (typeof changeBridge !== "undefined" && changeBridge !== null) {
                            changeBridge.refreshChanges()
                        }
                        root.loadChanges()
                        root.refreshPendingHandoffs()
                    }
                }

                PrimaryButton {
                    text: "待 PM 收口 (" + root.pendingHandoffs.length + ")"
                    type: root.pendingHandoffs.length > 0 ? "primary" : "ghost"
                    Layout.preferredWidth: 120
                    enabled: root.pendingHandoffs.length > 0
                    onClicked: root.preparePmClosure()
                }

                PrimaryButton {
                    text: "📊 台账对账"
                    type: "ghost"
                    Layout.preferredWidth: 100
                    enabled: typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService
                    onClicked: root.requestReconcileLedger()
                }

                PrimaryButton {
                    text: "🤖 AI 辅助"
                    type: "primary"
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 28
                    enabled: typeof aiContextBridge !== "undefined"
                             && aiContextBridge !== null
                             && root.selectedChangeNumber !== ""
                    onClicked: {
                        var detail = root.selectedChangeDetail || {}
                        var result = aiContextBridge.writeAiContext(
                            root.selectedProjectId,
                            mainWindow.currentProjectName,
                            mainWindow.currentProjectStack,
                            mainWindow.currentProjectPhase,
                            root.selectedChangeNumber,
                            detail.title || "",
                            detail.domain || "",
                            detail.business_nature || detail.nature || "",
                            detail.status || "",
                            mainWindow.currentPage
                        )
                        if (result && result.success) {
                            console.log("[QML] AI 上下文已写入: " + result.file)
                        } else {
                            console.warn("[QML] AI 上下文写入失败: "
                                + (result ? result.message : "未知错误"))
                        }
                    }
                }

                PrimaryButton {
                    text: "+ 新建变更"
                    type: "primary"
                    Layout.preferredWidth: 100
                    enabled: typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService
                    onClicked: root.requestNewChange()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                TextField {
                    id: searchField
                    Layout.preferredWidth: 240
                    Layout.preferredHeight: 28
                    placeholderText: "搜索变更编号/标题/项目..."
                    text: root.searchText
                    onTextChanged: {
                        root.searchText = text
                        root.applyFilters()
                    }
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        color: Theme.glassBg
                        radius: Theme.radiusSm
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }

                ComboBox {
                    Layout.preferredWidth: 120
                    Layout.preferredHeight: 28
                    model: ["全部状态", "draft", "submitted", "approved", "implementing", "completed", "closed"]
                    onCurrentIndexChanged: {
                        var map = ["all", "draft", "submitted", "approved", "implementing", "completed", "closed"]
                        root.statusFilter = map[currentIndex]
                        root.applyFilters()
                    }
                }

                ComboBox {
                    Layout.preferredWidth: 120
                    Layout.preferredHeight: 28
                    model: ["全部领域", "ELEC", "MECH", "PLC", "HMI", "SCPT", "DOCU", "SAFE"]
                    onCurrentIndexChanged: {
                        var map = ["all", "ELEC", "MECH", "PLC", "HMI", "SCPT", "DOCU", "SAFE"]
                        root.domainFilter = map[currentIndex]
                        root.applyFilters()
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: "共 " + filteredModel.count + " 条"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                }
            }
        }
    }

    // ── 主内容：StackLayout 切换 Split/Ledger ──────────
    StackLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: navBar.bottom
        anchors.bottom: parent.bottom
        currentIndex: root.viewMode === "split" ? 0 : 1

        // ─── Page 0: Split View（左列表 + 右详情）──────
        RowLayout {
            spacing: 0

            // ── 左侧变更单列表 ──────────────────────────
            GlassPanel {
                Layout.preferredWidth: 480
                Layout.fillHeight: true

                ListView {
                    id: changeListView
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    clip: true
                    spacing: Theme.spacingXs
                    model: filteredModel

                    // 空状态
                    Text {
                        anchors.centerIn: parent
                        visible: filteredModel.count === 0
                        text: "暂无变更"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeLg
                    }

                    delegate: Item {
                        width: changeListView.width
                        height: 88

                        Rectangle {
                            anchors.fill: parent
                            anchors.leftMargin: 4
                            anchors.rightMargin: 12
                            anchors.topMargin: 4
                            anchors.bottomMargin: 4
                            color: root.selectedChangeNumber === model.change_number ? Theme.glassHighlight : Theme.glassBg
                            radius: Theme.radiusSm
                            border.color: root.selectedChangeNumber === model.change_number ? Theme.primary : Theme.glassBorder
                            border.width: root.selectedChangeNumber === model.change_number ? 2 : 1

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.spacingSm
                                spacing: 2

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.spacingXs

                                    Text {
                                        text: model.change_number || ""
                                        font.pixelSize: Theme.fontSizeSm
                                        font.bold: true
                                        color: Theme.textPrimary
                                    }

                                    Item { Layout.fillWidth: true }

                                    Badge {
                                        text: model.status || ""
                                        type: model.status || "default"
                                    }
                                }

                                Text {
                                    text: model.title || "(无标题)"
                                    font.pixelSize: Theme.fontSizeXs
                                    color: Theme.textSecondary
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.spacingXs

                                    Text {
                                        text: model.project_id || ""
                                        font.pixelSize: Theme.fontSizeXs
                                        color: Theme.textMuted
                                    }

                                    Item { Layout.fillWidth: true }

                                    Text {
                                        text: (model.applicant || "") + " " + (model.apply_date || "")
                                        font.pixelSize: Theme.fontSizeXs
                                        color: Theme.textMuted
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.loadChangeDetail(model.change_number, model.project_id)
                            }
                        }
                    }
                }
            }

            // ── 右侧详情面板（ChangeDetailPanel）──────
            ChangeDetailPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                changeNumber: root.selectedChangeNumber
                projectId: root.selectedProjectId
                changeDetail: root.selectedChangeDetail
                onStatusChanged: root.onDetailStatusChanged()
                onRequestEditChange: root.requestEditChange()
            }
        }

        // ─── Page 1: Ledger View（全宽表格）────────────
        LedgerTableView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: filteredModel
            selectedChangeNumber: root.selectedChangeNumber
            onChangeSelected: (number, projId) => root.onLedgerChangeSelected(number, projId)
        }
    }

    // ── 初始加载 ────────────────────────────────────────
    Component.onCompleted: {
        loadChanges()
        refreshPendingHandoffs()
    }
}
