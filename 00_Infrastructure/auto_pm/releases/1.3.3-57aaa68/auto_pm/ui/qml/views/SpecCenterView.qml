// SpecCenterView.qml - V0.8.0 Phase 2 规范中心（CHG-091）
//
// 简化 3 Tab 结构（原 QWidget 6 Tab 简化），对应 spec_center.py
//   Tab 1: 概览（规范统计 + 健康摘要）
//   Tab 2: 规范索引（搜索 + 域过滤 + 列表）
//   Tab 3: 健康检查（运行检查 + 结果列表）
//
// 数据流：
//   specBridge.getSpecOverview() → 概览 Tab
//   specBridge.listSpecEntries(domain) → 索引 Tab
//   specBridge.runSpecCheck() → 检查 Tab
// 三重守卫：typeof specBridge === "undefined" || specBridge === null || !specBridge.hasService
//
// 注：Frontmatter/报告/对比 Tab 留待 V0.9 实现

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
    signal requestGenerateSpecIndex()  // M5 CHG-119: 规范索引生成
    signal requestGenerateSpecReport()  // M5 CHG-120: 规范报告生成
    signal requestCheckSpecFrontmatter()  // M5 CHG-121: 规范 Frontmatter 检查

    // ── 内部数据 ────────────────────────────────────────
    property var overviewData: ({})
    property string errorMessage: ""
    property int currentTab: 0  // 0=概览 1=索引 2=检查

    ListModel { id: entriesModel }
    ListModel { id: checkResultsModel }

    property string searchKeyword: ""
    property string domainFilter: "all"

    // ── 加载概览数据 ────────────────────────────────────
    function loadOverview() {
        if (typeof specBridge === "undefined" || specBridge === null || !specBridge.hasService) {
            errorMessage = "SpecCenterAdapter 未启用（参考 spec_registry.json）"
            return
        }
        errorMessage = ""
        overviewData = specBridge.getSpecOverview()
        if (overviewData && overviewData.error) {
            errorMessage = overviewData.error
        }
    }

    // ── 加载规范索引 ────────────────────────────────────
    function loadEntries() {
        if (typeof specBridge === "undefined" || specBridge === null || !specBridge.hasService) {
            entriesModel.clear()
            return
        }
        var entries = specBridge.listSpecEntries(domainFilter)
        entriesModel.clear()
        for (var i = 0; i < entries.length; i++) {
            // 应用搜索过滤（QML 端过滤，避免后端往返）
            if (searchKeyword !== "") {
                var q = searchKeyword.toLowerCase()
                var e = entries[i]
                if (!String(e.spec_id || "").toLowerCase().includes(q) &&
                    !String(e.title || "").toLowerCase().includes(q) &&
                    !String(e.number || "").toLowerCase().includes(q)) {
                    continue
                }
            }
            entriesModel.append(entries[i])
        }
    }

    // ── 运行健康检查 ────────────────────────────────────
    function runChecks() {
        if (typeof specBridge === "undefined" || specBridge === null || !specBridge.hasService) {
            checkResultsModel.clear()
            checkResultsModel.append({
                "check_id": "",
                "severity": "ERROR",
                "message": "SpecCheckService 未启用",
                "details": "",
                "fix_suggestion": ""
            })
            return
        }
        var result = specBridge.runSpecCheck()
        checkResultsModel.clear()
        if (result && result.error) {
            checkResultsModel.append({
                "check_id": "",
                "severity": "ERROR",
                "message": result.error || result.message || "检查失败",
                "details": "",
                "fix_suggestion": ""
            })
            return
        }
        var results = result.results || []
        for (var i = 0; i < results.length; i++) {
            checkResultsModel.append(results[i])
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
                    text: "📐 规范中心"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "刷新"
                    onClicked: {
                        loadOverview()
                        loadEntries()
                    }
                }

                PrimaryButton {
                    text: "🔄 同步 Obsidian"
                    type: "primary"
                    enabled: typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService
                    onClicked: {
                        if (typeof specBridge !== "undefined" && specBridge !== null) {
                            var res = specBridge.syncObsidian()
                            loadOverview()
                            loadEntries()
                        }
                    }
                }

                PrimaryButton {
                    text: "📝 生成索引"
                    type: "ghost"
                    enabled: typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService
                    onClicked: root.requestGenerateSpecIndex()
                }

                PrimaryButton {
                    text: "📊 生成报告"
                    type: "ghost"
                    enabled: typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService
                    onClicked: root.requestGenerateSpecReport()
                }

                PrimaryButton {
                    text: "🔍 检查 Frontmatter"
                    type: "ghost"
                    enabled: typeof specBridge !== "undefined" && specBridge !== null && specBridge.hasService
                    onClicked: root.requestCheckSpecFrontmatter()
                }

                PrimaryButton {
                    text: "返回"
                    type: "ghost"
                    onClicked: root.backToProjectList()
                }
            }

            Text {
                text: "基于 spec_registry.json 的规范管理与健康检查中心（3 Tab 简化版）"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }
        }
    }

    // ── Tab 栏 ──────────────────────────────────────────
    Rectangle {
        id: tabBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: navBar.bottom
        height: 40
        color: Theme.surface

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.border
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.spacingMd
            anchors.rightMargin: Theme.spacingMd
            spacing: Theme.spacingXs

            Repeater {
                model: [
                    {"label": "概览", "index": 0},
                    {"label": "规范索引", "index": 1},
                    {"label": "健康检查", "index": 2}
                ]
                delegate: Rectangle {
                    Layout.preferredHeight: 32
                    Layout.preferredWidth: tabText.implicitWidth + 24
                    color: root.currentTab === modelData.index ? Theme.primary : "transparent"
                    radius: Theme.radiusSm

                    Text {
                        id: tabText
                        anchors.centerIn: parent
                        text: modelData.label || ""
                        color: root.currentTab === modelData.index ? "white" : Theme.textSecondary
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: root.currentTab === modelData.index
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.currentTab = modelData.index
                            if (modelData.index === 1 && entriesModel.count === 0) {
                                loadEntries()
                            } else if (modelData.index === 2 && checkResultsModel.count === 0) {
                                // 不自动运行检查，等用户点击"运行检查"按钮
                            }
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }
    }

    // ── 错误状态 ────────────────────────────────────────
    Text {
        visible: errorMessage !== ""
        anchors.top: tabBar.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: Theme.spacingXl
        text: "❌" + errorMessage
        color: Theme.error
        font.pixelSize: Theme.fontSizeMd
    }

    // ── Tab 内容区（StackLayout）────────────────────────
    StackLayout {
        id: tabContent
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: tabBar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacingMd
        currentIndex: root.currentTab
        visible: errorMessage === ""

        // ── Tab 1：概览 ───────────────────────────────
        Rectangle {
            color: "transparent"

            ScrollView {
                anchors.fill: parent
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: Theme.spacingMd

                    // 规范总数卡片
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 100
                        color: Theme.surface
                        radius: Theme.radiusMd
                        border.color: Theme.border
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingXs

                            Text {
                                text: "规范总数"
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textSecondary
                            }
                            Text {
                                text: (overviewData.spec_count || 0).toString()
                                font.pixelSize: Theme.fontSizeXxl
                                font.bold: true
                                color: Theme.primary
                            }
                        }
                    }

                    // 健康摘要卡片
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: healthLayout.implicitHeight + 2 * Theme.spacingMd
                        color: Theme.surface
                        radius: Theme.radiusMd
                        border.color: Theme.border
                        border.width: 1

                        ColumnLayout {
                            id: healthLayout
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingXs

                            Text {
                                text: "健康摘要"
                                font.pixelSize: Theme.fontSizeMd
                                font.bold: true
                                color: Theme.primary
                            }

                            Text {
                                text: "⚠错误: " + (overviewData.health_summary ? overviewData.health_summary.error_count : 0)
                                font.pixelSize: Theme.fontSizeSm
                                color: overviewData.health_summary && overviewData.health_summary.error_count > 0 ? Theme.error : Theme.textPrimary
                            }
                            Text {
                                text: "⚠️ 警告: " + (overviewData.health_summary ? overviewData.health_summary.warning_count : 0)
                                font.pixelSize: Theme.fontSizeSm
                                color: overviewData.health_summary && overviewData.health_summary.warning_count > 0 ? Theme.warning : Theme.textPrimary
                            }
                            Text {
                                text: "ℹ信息: " + (overviewData.health_summary ? overviewData.health_summary.info_count : 0)
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textPrimary
                            }
                        }
                    }

                    // 按域统计卡片
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: domainLayout.implicitHeight + 2 * Theme.spacingMd
                        color: Theme.surface
                        radius: Theme.radiusMd
                        border.color: Theme.border
                        border.width: 1

                        ColumnLayout {
                            id: domainLayout
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingXs

                            Text {
                                text: "按域统计"
                                font.pixelSize: Theme.fontSizeMd
                                font.bold: true
                                color: Theme.primary
                            }

                            Text {
                                Layout.fillWidth: true
                                text: {
                                    var counts = overviewData.domain_counts || {}
                                    var parts = []
                                    for (var k in counts) {
                                        parts.push(k + ": " + counts[k])
                                    }
                                    return parts.length > 0 ? parts.join(" / ") : ""
                                }
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textPrimary
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    // 生命周期统计卡片
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: lifecycleLayout.implicitHeight + 2 * Theme.spacingMd
                        color: Theme.surface
                        radius: Theme.radiusMd
                        border.color: Theme.border
                        border.width: 1

                        ColumnLayout {
                            id: lifecycleLayout
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingXs

                            Text {
                                text: "生命周期分布"
                                font.pixelSize: Theme.fontSizeMd
                                font.bold: true
                                color: Theme.primary
                            }

                            Text {
                                Layout.fillWidth: true
                                text: {
                                    var counts = overviewData.lifecycle_counts || {}
                                    var parts = []
                                    for (var k in counts) {
                                        parts.push(k + ": " + counts[k])
                                    }
                                    return parts.length > 0 ? parts.join(" / ") : ""
                                }
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textPrimary
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }

        // ── Tab 2：规范索引 ───────────────────────────
        Rectangle {
            color: "transparent"

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.spacingSm

                // 工具栏：搜索 + 域过滤
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm

                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        placeholderText: "搜索 spec_id / title / number..."
                        text: root.searchKeyword
                        onTextChanged: {
                            root.searchKeyword = text
                            loadEntries()
                        }
                    }

                    ComboBox {
                        id: domainCombo
                        Layout.preferredWidth: 140
                        model: ["all", "pm", "plc", "python"]
                        currentIndex: 0
                        onActivated: {
                            root.domainFilter = currentText
                            loadEntries()
                        }
                    }
                }

                    // 规范列表
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: entriesModel
                        spacing: Theme.spacingXs

                        delegate: Rectangle {
                            width: ListView.view ? ListView.view.width : 600
                            height: 56
                            color: Theme.surface
                            radius: Theme.radiusSm
                            border.color: Theme.border
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.spacingMd
                                spacing: Theme.spacingSm

                                Text {
                                    text: model.spec_id || ""
                                    font.pixelSize: Theme.fontSizeSm
                                    font.bold: true
                                    color: Theme.primary
                                    Layout.preferredWidth: 120
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: model.title || ""
                                    font.pixelSize: Theme.fontSizeSm
                                    color: Theme.textPrimary
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: model.domain || ""
                                    font.pixelSize: Theme.fontSizeXs
                                    color: Theme.textSecondary
                                    Layout.preferredWidth: 60
                                }
                                Text {
                                    text: model.lifecycle || ""
                                    font.pixelSize: Theme.fontSizeXs
                                    color: model.lifecycle === "active" ? Theme.success : Theme.textMuted
                                    Layout.preferredWidth: 80
                                }
                            }
                        }
                    }

                    // 空状态
                    Text {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: entriesModel.count === 0
                        text: "暂无规范条目"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeLg
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
            }
        }

        // ── Tab 3：健康检查 ───────────────────────────
        Rectangle {
            color: "transparent"

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.spacingSm

                // 工具栏：运行检查按钮
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm

                    PrimaryButton {
                        text: "▶运行检查"
                        enabled: specBridge !== null && specBridge.hasService
                        onClicked: runChecks()
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: "共 " + checkResultsModel.count + " 条结果"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }
                }

                // 检查结果列表
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: checkResultsModel
                    spacing: Theme.spacingXs

                    delegate: Rectangle {
                        width: ListView.view ? ListView.view.width : 600
                        height: resultLayout.implicitHeight + 2 * Theme.spacingSm
                        color: Theme.surface
                        radius: Theme.radiusSm
                        border.color: Theme.border
                        border.width: 1

                        ColumnLayout {
                            id: resultLayout
                            anchors.fill: parent
                            anchors.margins: Theme.spacingSm
                            spacing: Theme.spacingXs

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.spacingXs

                                Rectangle {
                                    width: 60
                                    height: 18
                                    radius: 2
                                    color: {
                                        var s = (model.severity || "").toUpperCase()
                                        if (s === "ERROR") return Theme.error
                                        if (s === "WARNING" || s === "WARN") return Theme.warning
                                        return Theme.textMuted
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        text: (model.severity || "INFO").toUpperCase()
                                        font.pixelSize: Theme.fontSizeXs
                                        font.bold: true
                                        color: "white"
                                    }
                                }

                                Text {
                                    text: model.check_id || ""
                                    font.pixelSize: Theme.fontSizeXs
                                    font.bold: true
                                    color: Theme.textSecondary
                                    Layout.preferredWidth: 100
                                    elide: Text.ElideRight
                                }

                                Text {
                                    text: model.message || ""
                                    font.pixelSize: Theme.fontSizeSm
                                    color: Theme.textPrimary
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                visible: (model.details || "") !== ""
                                text: "详情: " + (model.details || "")
                                font.pixelSize: Theme.fontSizeXs
                                color: Theme.textSecondary
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                Layout.fillWidth: true
                                visible: (model.fix_suggestion || "") !== ""
                                text: "建议: " + (model.fix_suggestion || "")
                                font.pixelSize: Theme.fontSizeXs
                                color: Theme.primary
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }

                // 空状态
                Text {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: checkResultsModel.count === 0
                    text: "点击 \"运行检查\" 按钮开始"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeLg
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    Component.onCompleted: loadOverview()
}

