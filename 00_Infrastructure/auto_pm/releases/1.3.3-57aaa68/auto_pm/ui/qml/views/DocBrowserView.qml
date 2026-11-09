// DocBrowserView.qml - 文档浏览器及 Markdown 结构化委托渲染与大纲双向联动视图
//
// 提供项目内部文档目录树浏览（支持分类与模糊过滤）、Markdown 原生卡片渲染、大纲随动导航与本地 PDF 零依赖导出。

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../theme"
import "../components"

Rectangle {
    id: root
    color: "transparent"

    property string projectId: ""
    property var docList: []
    property string selectedPath: ""
    property var docBlocks: []
    property string statusMessage: ""
    property string filterText: ""
    property string selectedCategory: "all"

    // 维持向后兼容的 selectedIndex 只读属性绑定
    property int selectedIndex: {
        if (!selectedPath) return -1
        for (var i = 0; i < docList.length; i++) {
            if (docList[i].path === selectedPath) {
                return i
            }
        }
        return -1
    }

    // 大纲数据模型（只提取 h1 和 h2 层级做导航）
    property var outlineModel: {
        var res = []
        for (var i = 0; i < docBlocks.length; i++) {
            var block = docBlocks[i]
            if (block.type === "h1" || block.type === "h2") {
                res.push({
                    text: block.text,
                    type: block.type,
                    blockIndex: i
                })
            }
        }
        return res
    }

    // 根据 contentY 动态匹配最靠近视口顶部的激活大纲项索引
    property int currentHighlightIndex: {
        if (outlineModel.length === 0) return -1
        // 获取当前视口顶部的 block 索引
        var idx = blocksListView.indexAt(10, blocksListView.contentY + 20)
        if (idx < 0) return -1
        
        var nearestHeaderIdx = -1
        for (var i = 0; i < outlineModel.length; i++) {
            if (outlineModel[i].blockIndex <= idx) {
                nearestHeaderIdx = i
            } else {
                break
            }
        }
        return nearestHeaderIdx
    }

    // 目录分类与模糊过滤结果
    property var filteredDocList: {
        var res = []
        var keyword = filterText.toLowerCase()
        for (var i = 0; i < docList.length; i++) {
            var doc = docList[i]
            
            // 1. 分类筛选判断
            if (selectedCategory !== "all") {
                if (doc.category !== selectedCategory) {
                    continue
                }
            }
            
            // 2. 搜索过滤判断
            if (keyword) {
                if (doc.name.toLowerCase().indexOf(keyword) === -1) {
                    continue
                }
            }
            res.push(doc)
        }
        return res
    }

    onProjectIdChanged: {
        loadDocs()
    }

    function loadDocs() {
        if (!projectId) return
        selectedPath = ""
        docBlocks = []
        statusMessage = ""
        filterText = ""
        selectedCategory = "all"
        if (categoryCombo) categoryCombo.currentIndex = 0
        if (searchField) searchField.text = ""
        if (typeof deliveryBridge !== "undefined" && deliveryBridge !== null) {
            root.docList = deliveryBridge.listProjectDocs(root.projectId)
            if (root.filteredDocList.length > 0) {
                selectDoc(0)
            } else {
                statusMessage = "未在此项目中找到 Markdown 文档 (.md)"
            }
        }
    }

    function selectDoc(index) {
        if (index < 0 || index >= filteredDocList.length) return
        
        var actualDoc = filteredDocList[index]
        selectedPath = actualDoc.path
        statusMessage = ""
        
        if (typeof deliveryBridge !== "undefined" && deliveryBridge !== null) {
            docBlocks = deliveryBridge.parseMarkdownToBlocks(actualDoc.path)
        }
    }

    function getSelectedDocName() {
        for (var i = 0; i < docList.length; i++) {
            if (docList[i].path === selectedPath) {
                return docList[i].name
            }
        }
        return ""
    }

    function cleanFilePath(fileUrl) {
        var path = fileUrl.toString()
        if (path.indexOf("file:///") === 0) {
            path = path.substring(8)
        } else if (path.indexOf("file://") === 0) {
            path = path.substring(7)
        }
        path = decodeURIComponent(path)
        path = path.replace(/\//g, "\\")
        return path
    }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.spacingMd

        // ── 左侧文档列表与分类 ──────────────────────────────
        Rectangle {
            Layout.preferredWidth: 280
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusLg
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingSm

                Text {
                    text: "📄 项目文档目录"
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    color: Theme.textPrimary
                    Layout.fillWidth: true
                }

                // 通用分类 ComboBox 筛选器
                ComboBox {
                    id: categoryCombo
                    Layout.fillWidth: true
                    model: ["📂 全部文档", "📋 项目管理文档", "💻 技术文档", "📐 指标规范", "✍️ PM日志", "📄 其他文档"]
                    onCurrentIndexChanged: {
                        var valMap = ["all", "pm", "tech", "spec", "log", "other"]
                        root.selectedCategory = valMap[currentIndex]
                    }
                }

                // 搜索过滤栏
                TextField {
                    id: searchField
                    placeholderText: "🔍 过滤文档..."
                    Layout.fillWidth: true
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSizeSm
                    selectByMouse: true
                    background: Rectangle {
                        color: Theme.backgroundTertiary
                        border.color: searchField.activeFocus ? Theme.primary : Theme.border
                        border.width: 1
                        radius: Theme.radiusSm
                    }
                    onTextChanged: {
                        root.filterText = text
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.border
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ListView {
                        id: docListView
                        model: root.filteredDocList
                        spacing: 2
                        delegate: Item {
                            width: docListView.width
                            height: 48

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 2
                                color: root.selectedPath === modelData.path ? Theme.glassBg : "transparent"
                                border.color: root.selectedPath === modelData.path ? Theme.primary : "transparent"
                                border.width: 1
                                radius: Theme.radiusSm

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: Theme.spacingSm
                                    anchors.rightMargin: Theme.spacingSm
                                    spacing: Theme.spacingSm

                                    Text {
                                        text: {
                                            if (modelData.category === "pm") return "📋";
                                            if (modelData.category === "tech") return "💻";
                                            if (modelData.category === "spec") return "📐";
                                            if (modelData.category === "log") return "✍️";
                                            return "📄";
                                        }
                                        font.pixelSize: 16
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text {
                                            text: modelData.name.split("/").pop() // filename
                                            font.pixelSize: Theme.fontSizeSm
                                            font.bold: root.selectedPath === modelData.path
                                            color: root.selectedPath === modelData.path ? Theme.primary : Theme.textPrimary
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Text {
                                            text: modelData.name.substring(0, modelData.name.lastIndexOf("/")) || "/"
                                            font.pixelSize: Theme.fontSizeXs
                                            color: Theme.textMuted
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.selectDoc(index)
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── 中间 Markdown 结构化渲染区 ─────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusLg
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 0
                spacing: 0

                // 渲染区工具栏
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    color: "transparent"

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: Theme.border
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.spacingLg
                        anchors.rightMargin: Theme.spacingLg
                        spacing: Theme.spacingMd

                        Text {
                            text: root.selectedPath !== "" ? "📖 " + root.getSelectedDocName() : "未选择文档"
                            font.pixelSize: Theme.fontSizeMd
                            font.bold: true
                            color: Theme.textPrimary
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }

                        // 📤 导出 PDF 按钮
                        PrimaryButton {
                            text: "📤 导出 PDF"
                            type: "ghost"
                            Layout.preferredWidth: 100
                            enabled: root.selectedPath !== ""
                            onClicked: savePdfDialog.open()
                        }

                        PrimaryButton {
                            text: "🔄 刷新自动区"
                            type: "accent"
                            Layout.preferredWidth: 120
                            enabled: root.selectedPath !== ""
                            onClicked: {
                                refreshOverlay.visible = true
                                var result = deliveryBridge.refreshProjectDocs(root.projectId, false)
                                if (result && result.success) {
                                    root.statusMessage = "文档自动区刷新完成：" + (result.message || "")
                                    root.loadDocs() // reload content
                                } else {
                                    root.statusMessage = "刷新失败：" + (result ? result.message : "")
                                }
                                refreshOverlay.visible = false
                            }
                        }
                    }
                }

                // 核心从属渲染列表
                Item {
                    id: readerContainer
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingLg
                        clip: true
                        visible: root.statusMessage === "" && root.selectedPath !== ""
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        ListView {
                            id: blocksListView
                            model: root.docBlocks
                            width: readerContainer.width - Theme.spacingLg * 2
                            spacing: Theme.spacingMd
                            interactive: false // ScrollView handles scrolling

                            delegate: Loader {
                                width: blocksListView.width
                                source: {
                                    var type = modelData.type
                                    if (type.substring(0, 1) === "h") {
                                        return "../components/doc/DocHeader.qml";
                                    }
                                    if (type === "code") {
                                        return "../components/doc/DocCodeBlock.qml";
                                    }
                                    if (type === "alert") {
                                        return "../components/doc/DocAlert.qml";
                                    }
                                    if (type === "table") {
                                        return "../components/doc/DocTable.qml";
                                    }
                                    return "../components/doc/DocParagraph.qml";
                                }

                                onLoaded: {
                                    var type = modelData.type
                                    if (type.substring(0, 1) === "h") {
                                        item.textData = modelData.text
                                        item.type = type
                                    } else if (type === "code") {
                                        item.codeData = modelData.code
                                        item.language = modelData.lang
                                    } else if (type === "alert") {
                                        item.htmlData = modelData.html
                                        item.alertType = modelData.alert_type
                                    } else if (type === "table") {
                                        item.htmlData = modelData.html
                                    } else {
                                        item.htmlData = modelData.html
                                    }
                                }
                            }
                        }
                    }

                    // 状态/空信息提示
                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: Theme.spacingSm
                        visible: root.statusMessage !== "" || root.selectedPath === ""

                        Text {
                            text: root.statusMessage || "请从左侧选择一个文档进行实时渲染浏览"
                            font.pixelSize: Theme.fontSizeMd
                            color: Theme.textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            Layout.fillWidth: true
                        }
                    }

                    // 刷新中遮罩
                    Rectangle {
                        id: refreshOverlay
                        anchors.fill: parent
                        color: "#80000000"
                        visible: false

                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: Theme.spacingSm
                            Text {
                                text: "🔄 正在自动刷新文档数据区..."
                                font.pixelSize: Theme.fontSizeMd
                                color: "white"
                                font.bold: true
                            }
                        }
                    }
                }
            }
        }

        // ── 右侧大纲导航面板 (200px) ──────────────────────────────
        Rectangle {
            Layout.preferredWidth: 200
            Layout.fillHeight: true
            color: Theme.surface
            radius: Theme.radiusLg
            border.color: Theme.border
            border.width: 1
            visible: root.selectedPath !== "" && root.outlineModel.length > 0

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingSm

                Text {
                    text: "📋 大纲导航"
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    color: Theme.textPrimary
                    Layout.fillWidth: true
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.border
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    ListView {
                        id: outlineListView
                        model: root.outlineModel
                        spacing: Theme.spacingXs
                        delegate: Item {
                            width: outlineListView.width
                            height: 32

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 1
                                color: root.currentHighlightIndex === index ? Theme.glassHighlight : "transparent"
                                radius: Theme.radiusSm

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: modelData.type === "h2" ? Theme.spacingMd : Theme.spacingSm
                                    anchors.rightMargin: Theme.spacingSm
                                    spacing: 4

                                    Text {
                                        text: modelData.type === "h1" ? "▪" : "▫"
                                        color: root.currentHighlightIndex === index ? Theme.primary : Theme.textMuted
                                        font.bold: root.currentHighlightIndex === index
                                    }

                                    Text {
                                        text: modelData.text
                                        font.pixelSize: Theme.fontSizeSm
                                        color: root.currentHighlightIndex === index ? Theme.primary : Theme.textSecondary
                                        font.bold: root.currentHighlightIndex === index
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        // 绝对跳转至正文中对应的 Block 节点项
                                        blocksListView.positionViewAtIndex(modelData.blockIndex, ListView.Beginning)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ── 导出 PDF 保存选择文件对话框 ──────────────────────────
    FileDialog {
        id: savePdfDialog
        title: "导出为 PDF 文档"
        fileMode: FileDialog.SaveFile
        nameFilters: ["PDF files (*.pdf)"]
        onAccepted: {
            var rawPath = selectedFile.toString()
            var savePath = root.cleanFilePath(rawPath)
            if (savePath.toLowerCase().indexOf(".pdf") === -1) {
                savePath = savePath + ".pdf"
            }
            refreshOverlay.visible = true
            var result = deliveryBridge.exportDocToPdf(root.selectedPath, savePath)
            if (result && result.success) {
                root.statusMessage = "PDF 成功保存至：" + savePath
            } else {
                root.statusMessage = "PDF 导出失败：" + (result ? result.message : "")
            }
            refreshOverlay.visible = false
        }
    }

    Component.onCompleted: loadDocs()
}
