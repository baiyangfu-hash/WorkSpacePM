// ProjectListView.qml - V0.6.0 W2-S1 完整功能版（搜索/过滤/排序/分页）
//
// 在 W1 PoC 基础上扩展：
// - 搜索框（实时模糊匹配 name/project_id）
// - 业务线 + 阶段筛选下拉
// - 排序下拉（按名称/编号/版本号）
// - 分页（每页 10/20/50 可选）
// - 卡片视图 + 表格视图切换
// - 点击卡片触发 workbenchBridge.selectProject 跳工作区跳转
//
// 数据流：workbenchBridge.listProjects() → projectModel → JS 过滤/排序 → displayModel（ListModel）→ ListView

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 公开状态 ────────────────────────────────────────
    property string searchText: ""
    property string stackFilter: "all"  // all/plc/python/unknown
    property string phaseFilter: "all"  // all/initiating/planning/developing/commissioning/production/archived
    property string sortField: "name"   // name/project_id/version
    property string sortDir: "asc"      // asc/desc
    property int pageSize: 20
    property int currentPage: 0
    property string viewMode: "card"    // card/table
    property int totalCount: 0          // 当前过滤后总数
    property var filteredItems: []      // 过滤排序后的项目数组

    // ── 信号 ────────────────────────────────────────────
    signal projectClicked(string projectId, string projectName)
    signal requestNewProject()
    signal requestImportProject()

    // ── 过滤排序后的展示模型 ────────────────────────────
    ListModel { id: displayModel }

    // ── 顶部工具栏 ──────────────────────────────────────
    Rectangle {
        id: toolbar
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

            // 第一行：标题 + 视图切换 + 新增/导入按钮 + 项目数
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "项目列表"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "+ 新建项目"
                    type: "primary"
                    Layout.preferredWidth: 100
                    onClicked: root.requestNewProject()
                }

                PrimaryButton {
                    text: "+ 导入项目"
                    type: "ghost"
                    Layout.preferredWidth: 100
                    onClicked: root.requestImportProject()
                }

                // 视图切换按钮组
                RowLayout {
                    spacing: 0
                    PrimaryButton {
                        text: "卡片"
                        type: root.viewMode === "card" ? "primary" : "ghost"
                        Layout.preferredWidth: 60
                        onClicked: root.viewMode = "card"
                    }
                    PrimaryButton {
                        text: "表格"
                        type: root.viewMode === "table" ? "primary" : "ghost"
                        Layout.preferredWidth: 60
                        onClicked: root.viewMode = "table"
                    }
                }

                Text {
                    text: "共 " + root.totalCount + " 个项目"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                }
            }

            // 第二行：搜索框 + 筛选 + 排序
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                // 搜索框
                TextField {
                    id: searchInput
                    Layout.preferredWidth: 280
                    Layout.preferredHeight: 32
                    placeholderText: "搜索项目名称或编号.."
                    text: root.searchText
                    onTextChanged: {
                        root.searchText = text
                        root.currentPage = 0
                        root.applyFilters()
                    }
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        color: Theme.background
                        radius: Theme.radiusSm
                        border.color: Theme.border
                        border.width: 1
                    }
                }

                // 业务线筛选
                ComboBox {
                    id: stackCombo
                    Layout.preferredWidth: 120
                    Layout.preferredHeight: 32
                    model: ["全部技术栈", "PLC", "Python", "未分类"]
                    onCurrentIndexChanged: {
                        var map = ["all", "plc", "python", "unknown"]
                        root.stackFilter = map[currentIndex]
                        root.currentPage = 0
                        root.applyFilters()
                    }
                }

                // 阶段筛选
                ComboBox {
                    id: phaseCombo
                    Layout.preferredWidth: 120
                    Layout.preferredHeight: 32
                    model: ["全部阶段", "在研", "调试", "生产", "归档"]
                    onCurrentIndexChanged: {
                        var map = ["all", "developing", "commissioning", "production", "archived"]
                        root.phaseFilter = map[currentIndex]
                        root.currentPage = 0
                        root.applyFilters()
                    }
                }

                Item { Layout.fillWidth: true }

                // 排序字段
                ComboBox {
                    id: sortCombo
                    Layout.preferredWidth: 140
                    Layout.preferredHeight: 32
                    model: ["按名称", "按编号", "按版本"]
                    onCurrentIndexChanged: {
                        var map = ["name", "project_id", "version"]
                        root.sortField = map[currentIndex]
                        root.applyFilters()
                    }
                }

                // 升降序切换
                PrimaryButton {
                    text: root.sortDir === "asc" ? "↑" : "↓"
                    type: "ghost"
                    Layout.preferredWidth: 32
                    onClicked: {
                        root.sortDir = root.sortDir === "asc" ? "desc" : "asc"
                        root.applyFilters()
                    }
                }

                // 刷新按钮
                PrimaryButton {
                    text: "刷新"
                    type: "ghost"
                    Layout.preferredWidth: 60
                    onClicked: {
                        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                            workbenchBridge.refreshProjects()
                            var projects = workbenchBridge.listProjects()
                            projectModel.setProjects(projects)
                            root.applyFilters()
                        }
                    }
                }
            }
        }
    }

    // ── 项目列表区 ─────────────────────────────────────
    Rectangle {
        id: listArea
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: toolbar.bottom
        anchors.bottom: paginationBar.top
        color: "transparent"

        // 卡片视图
        ListView {
            id: cardListView
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            visible: root.viewMode === "card"
            clip: true
            spacing: Theme.spacingSm
            model: displayModel

            // 空状态
            Text {
                anchors.centerIn: parent
                visible: displayModel.count === 0
                text: "暂无项目匹配筛选条件\n\n请调整搜索词或筛选条件"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeLg
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            delegate: Rectangle {
                width: cardListView.width
                height: 80
                color: Theme.surface
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingMd

                    // 技术栈徽标
                    Badge {
                        Layout.preferredWidth: 48
                        Layout.preferredHeight: 48
                        text: model.stack ? model.stack.toUpperCase().substring(0, 3) : "?"
                        type: model.stack || "unknown"
                        radius: Theme.radiusSm
                    }

                    // 项目信息
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            text: model.name || "(未命名项目)"
                            font.pixelSize: Theme.fontSizeLg
                            font.bold: true
                            color: Theme.textPrimary
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        Text {
                            text: model.project_id || ""
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textSecondary
                        }
                    }

                    // 版本号
                    Text {
                        text: {
                            var v = model.version || ""
                            if (!v || v === "-") return "-"
                            return (v.startsWith("v") || v.startsWith("V")) ? v : ("v" + v)
                        }
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }

                    // 阶段徽标
                    Badge {
                        Layout.preferredWidth: 64
                        Layout.preferredHeight: 24
                        text: {
                            var phaseMap = {
                                "initiating": "启动",
                                "planning": "规划",
                                "developing": "在研",
                                "commissioning": "调试",
                                "production": "生产",
                                "archived": "归档"
                            }
                            return phaseMap[model.phase] || "未分类"
                        }
                        type: model.phase || "default"
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        console.log("[QML] 点击项目: " + model.project_id + " - " + model.name)
                        root.projectClicked(model.project_id, model.name)
                        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                            workbenchBridge.selectProject(model.project_id, model.name)
                        }
                    }
                }
            }
        }

        // 表格视图
        Rectangle {
            id: tableView
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            visible: root.viewMode === "table"
            color: Theme.surface
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            // 表头
            Rectangle {
                id: tableHeader
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 36
                color: Theme.background

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.spacingMd
                    anchors.rightMargin: Theme.spacingMd
                    spacing: 0

                    Text { text: "项目编号"; font.pixelSize: Theme.fontSizeXs; font.bold: true; color: Theme.textSecondary; Layout.preferredWidth: 140 }
                    Text { text: "项目名称"; font.pixelSize: Theme.fontSizeXs; font.bold: true; color: Theme.textSecondary; Layout.fillWidth: true }
                    Text { text: "技术栈"; font.pixelSize: Theme.fontSizeXs; font.bold: true; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                    Text { text: "阶段"; font.pixelSize: Theme.fontSizeXs; font.bold: true; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                    Text { text: "版本"; font.pixelSize: Theme.fontSizeXs; font.bold: true; color: Theme.textSecondary; Layout.preferredWidth: 80 }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: Theme.border
                }
            }

            // 表格数据 ListView
            ListView {
                id: tableListView
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: tableHeader.bottom
                anchors.bottom: parent.bottom
                clip: true
                model: displayModel

                delegate: Rectangle {
                    width: tableListView.width
                    height: 36
                    color: index % 2 === 0 ? Theme.surface : Theme.background

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.spacingMd
                        anchors.rightMargin: Theme.spacingMd
                        spacing: 0

                        Text { text: model.project_id || ""; font.pixelSize: Theme.fontSizeXs; color: Theme.textPrimary; Layout.preferredWidth: 140; elide: Text.ElideRight }
                        Text { text: model.name || ""; font.pixelSize: Theme.fontSizeXs; color: Theme.textPrimary; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { text: model.stack || ""; font.pixelSize: Theme.fontSizeXs; color: Theme.textPrimary; Layout.preferredWidth: 80 }
                        Text { text: model.phase || ""; font.pixelSize: Theme.fontSizeXs; color: Theme.textPrimary; Layout.preferredWidth: 80 }
                        Text { text: model.version || ""; font.pixelSize: Theme.fontSizeXs; color: Theme.textPrimary; Layout.preferredWidth: 80 }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.projectClicked(model.project_id, model.name)
                            if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
                                workbenchBridge.selectProject(model.project_id, model.name)
                            }
                        }
                    }
                }
            }

            // 表格空状态
            Text {
                anchors.centerIn: parent
                visible: displayModel.count === 0
                text: "暂无项目匹配筛选条件"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeMd
            }
        }
    }

    // ── 分页区 ──────────────────────────────────────────
    Rectangle {
        id: paginationBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 44
        color: Theme.surface

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: Theme.border
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            // 每页大小
            Text {
                text: "每页:"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }

            ComboBox {
                Layout.preferredWidth: 80
                Layout.preferredHeight: 28
                model: ["10", "20", "50"]
                currentIndex: 1  // 默认 20
                onCurrentIndexChanged: {
                    var sizes = [10, 20, 50]
                    root.pageSize = sizes[currentIndex]
                    root.currentPage = 0
                    root.applyFilters()
                }
            }

            Item { Layout.fillWidth: true }

            // 上一页
            PrimaryButton {
                text: "上一页"
                type: "ghost"
                Layout.preferredWidth: 60
                enabled: root.currentPage > 0
                onClicked: {
                    if (root.currentPage > 0) {
                        root.currentPage--
                        root.applyFilters()
                    }
                }
            }

            // 页码显示
            Text {
                text: {
                    var totalPages = Math.max(1, Math.ceil(root.totalCount / root.pageSize))
                    return (root.currentPage + 1) + " / " + totalPages
                }
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textPrimary
            }

            // 下一页
            PrimaryButton {
                text: "下一页"
                type: "ghost"
                Layout.preferredWidth: 60
                enabled: root.currentPage < Math.ceil(root.totalCount / root.pageSize) - 1
                onClicked: {
                    var totalPages = Math.ceil(root.totalCount / root.pageSize)
                    if (root.currentPage < totalPages - 1) {
                        root.currentPage++
                        root.applyFilters()
                    }
                }
            }
        }
    }

    // ── 过滤/排序/分页逻辑（JS） ─────────────────────────
    function applyFilters() {
        var projects = []
        var count = projectModel ? projectModel.rowCount() : 0

        // 1. 收集 + 过滤
        for (var i = 0; i < count; i++) {
            var idx = projectModel.index(i, 0)
            var pid = projectModel.data(idx, 0x0100 + 1)  // ProjectIdRole
            var name = projectModel.data(idx, 0x0100 + 2)  // NameRole
            var stack = projectModel.data(idx, 0x0100 + 3) // StackRole
            var phase = projectModel.data(idx, 0x0100 + 4) // PhaseRole
            var version = projectModel.data(idx, 0x0100 + 5) // VersionRole

            // 搜索匹配（name 或 project_id 含搜索词，忽略大小写）
            if (root.searchText !== "") {
                var q = root.searchText.toLowerCase()
                if (!String(name).toLowerCase().includes(q) &&
                    !String(pid).toLowerCase().includes(q)) {
                    continue
                }
            }

            // 业务线筛选
            if (root.stackFilter !== "all" && stack !== root.stackFilter) {
                continue
            }

            // 阶段筛选
            if (root.phaseFilter !== "all" && phase !== root.phaseFilter) {
                continue
            }

            projects.push({
                project_id: pid,
                name: name,
                stack: stack,
                phase: phase,
                version: version
            })
        }

        // 2. 排序
        projects.sort(function(a, b) {
            var field = root.sortField
            var va = a[field] || ""
            var vb = b[field] || ""
            if (va < vb) return root.sortDir === "asc" ? -1 : 1
            if (va > vb) return root.sortDir === "asc" ? 1 : -1
            return 0
        })

        // 3. 总数
        root.totalCount = projects.length
        root.filteredItems = projects

        // 4. 分页切片
        var start = root.currentPage * root.pageSize
        var end = Math.min(start + root.pageSize, projects.length)
        var pageItems = projects.slice(start, end)

        // 5. 重置 displayModel
        displayModel.clear()
        for (var j = 0; j < pageItems.length; j++) {
            displayModel.append(pageItems[j])
        }
    }

    // ── 监听 projectModel 变化 ──────────────────────────
    Connections {
        target: projectModel
        function onRowsInserted() { root.applyFilters() }
        function onRowsRemoved() { root.applyFilters() }
        function onLayoutChanged() { root.applyFilters() }
        function onModelReset() { root.applyFilters() }
    }

    // ── 初始加载 ────────────────────────────────────────
    Component.onCompleted: {
        if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) {
            console.log("[QML] ProjectListView: workbenchBridge 可用，加载项目数...")
            var projects = workbenchBridge.listProjects()
            console.log("[QML] ProjectListView: 收到 " + projects.length + " 个项目")
            projectModel.setProjects(projects)
            root.applyFilters()
        } else {
            console.warn("[QML] ProjectListView: workbenchBridge 未注入")
            root.applyFilters()
        }
    }
}

