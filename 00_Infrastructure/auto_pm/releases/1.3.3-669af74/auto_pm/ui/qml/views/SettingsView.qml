// SettingsView.qml - V0.8.0 Phase 2 系统设置（CHG-091?
//
// 工作空间路径 + DB 统计 + 清除/重建 + PM_SESSION 健康，对应 QWidget 的 settings_page.py
//   ┌─ 通用 ─────────────────────────────────────────┐
//   │ 工作路径: [/tmp/workspace]            [📂]   │
//   │ 扫描深度: 4                                     │
//   ├─ 数据库 ────────────────────────────────────────┤
//   │ 缓存路径 / 项目记录 / 变更记录 / 上次同步       │
//   │[清除缓存]  [重建索引]                          │
//   ├─ PM_SESSION 健康 ───────────────────────────────┤
//   │ 文件 / 大小 / 行数 / 状态                      │
//   │[刷新检查]                                      │
//   └─────────────────────────────────────────────────┘
//
// 数据流：workbenchBridge.getSettingsSummary() / clearCache() / rebuildIndex() / runPmSessionCheck()
// 三重守卫：workbenchBridge !== null（getSettingsSummary 始终可用，DB 部分基于 db_available）

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 信号 ────────────────────────────────────────────
    signal backToProjectList()
    signal requestArchivePmSession()
    signal requestShowAbout()
    signal requestShowGlobalSettings()

    // ── 内部状态 ────────────────────────────────────────
    property var settingsData: ({})
    property var pmSessionData: ({})
    property string errorMessage: ""
    property string resultMessage: ""
    property bool isGitHooksInstalled: false

    // ── 加载数据 ────────────────────────────────────────
    function loadData() {
        if (typeof workbenchBridge === "undefined" || workbenchBridge === null) {
            errorMessage = "workbenchBridge 未注入"
            return
        }
        errorMessage = ""
        settingsData = workbenchBridge.getSettingsSummary()
        if (settingsData && settingsData.error) {
            errorMessage = settingsData.error
            return
        }
        // 加载 PM_SESSION 健康
        if (systemBridge.hasService) {
            pmSessionData = systemBridge.runPmSessionCheck()
        } else {
            pmSessionData = {"error": "未启用 PM_SESSION 服务"}
        }
        // 加载门禁安装状态
        if (typeof mainWindow !== "undefined" && mainWindow !== null && mainWindow.currentProjectId !== "") {
            isGitHooksInstalled = workbenchBridge.isHooksInstalled(mainWindow.currentProjectId)
        } else {
            isGitHooksInstalled = false
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
                    text: "⚙️ 系统设置"
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                    color: Theme.textPrimary
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "🩺 环境自检"
                    type: "ghost"
                    onClicked: {
                        if (typeof systemBridge !== "undefined" && systemBridge !== null) {
                            var docRes = systemBridge.runDoctorCheck()
                            if (docRes && docRes.all_passed) {
                                resultMessage = "🩺 环境自检：✅ 正常 (Python " + docRes.python_version + "，依赖就绪)"
                            } else {
                                resultMessage = "🩺 环境自检：⚠️ 部分检查未通过，请查看 CLI doctor 输出 (版本: " + (docRes.project_version || "1.1.0") + ")"
                            }
                        }
                    }
                }

                PrimaryButton {
                    text: "关于"
                    type: "ghost"
                    onClicked: root.requestShowAbout()
                }

                PrimaryButton {
                    text: "全局设置"
                    type: "ghost"
                    onClicked: root.requestShowGlobalSettings()
                }

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
                text: "工作空间路径 + 数据库缓存 + PM_SESSION 健康"
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

    // ── 设置内容（4 个卡片）────────────────────────────
    ScrollView {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: navBar.bottom
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacingMd
        visible: errorMessage === ""
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: Theme.spacingMd

            // ── 卡片 1：通用 ─────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: generalLayout.implicitHeight + 2 * Theme.spacingMd
                color: Theme.surface
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                ColumnLayout {
                    id: generalLayout
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Text {
                        text: "通用"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm

                        Text {
                            text: "工作空间路径:"
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textSecondary
                        }
                        Text {
                            Layout.fillWidth: true
                            text: settingsData.workspace_root || ""
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textPrimary
                            elide: Text.ElideMiddle
                        }
                        PrimaryButton {
                            text: "修改"
                            type: "ghost"
                            onClicked: workspaceDirDialog.open()
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm

                        Text {
                            text: "扫描深度:"
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textSecondary
                        }
                        Text {
                            text: "4"
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            color: Theme.textPrimary
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // ── 卡片 2：数据库 ───────────────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: dbLayout.implicitHeight + 2 * Theme.spacingMd
                color: Theme.surface
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                ColumnLayout {
                    id: dbLayout
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Text {
                        text: "数据库"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "缓存路径: " + (settingsData.db_path || "未连接")
                        font.pixelSize: Theme.fontSizeSm
                        color: settingsData.db_available ? Theme.textPrimary : Theme.textMuted
                        elide: Text.ElideMiddle
                    }

                    Text {
                        text: "项目记录: " + (settingsData.project_count || 0) + " 条"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                    }

                    Text {
                        text: "变更记录: " + (settingsData.change_count || 0) + " 条"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                    }

                    Text {
                        text: "上次同步: " + (settingsData.last_sync || "")
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm

                        PrimaryButton {
                            text: "清除缓存"
                            type: "danger"
                            enabled: settingsData.db_available === true
                            onClicked: clearCacheDialog.open()
                        }

                        PrimaryButton {
                            text: "重建索引"
                            enabled: settingsData.db_available === true
                            onClicked: rebuildDialog.open()
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // ── 卡片 3：PM_SESSION 健康 ─────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: pmLayout.implicitHeight + 2 * Theme.spacingMd
                color: Theme.surface
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                ColumnLayout {
                    id: pmLayout
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Text {
                        text: "PM_SESSION 健康"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "文件: " + (pmSessionData.file_path || pmSessionData.error || "")
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        elide: Text.ElideMiddle
                    }

                    Text {
                        text: "大小: " + (pmSessionData.file_size_kb || 0).toFixed(1)
                            + " KB / " + (pmSessionData.max_file_size_kb || 0) + " KB"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        visible: !pmSessionData.error
                    }

                    Text {
                        text: "行数: " + (pmSessionData.total_lines || 0)
                            + " / " + (pmSessionData.max_file_lines || 0)
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        visible: !pmSessionData.error
                    }

                    Text {
                        text: pmSessionData.is_healthy === true ? "✓健康" : "✗不健康"
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: true
                        color: pmSessionData.is_healthy === true ? Theme.success : Theme.error
                        visible: !pmSessionData.error
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm

                        PrimaryButton {
                            text: "刷新检查"
                            enabled: systemBridge !== null && systemBridge.hasService
                            onClicked: loadData()
                        }

                        PrimaryButton {
                            text: "📦 归档"
                            enabled: systemBridge !== null && systemBridge.hasService
                            onClicked: root.requestArchivePmSession()
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // ── 卡片 4：Git 提交门禁与自愈 ───────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: gitHooksLayout.implicitHeight + 2 * Theme.spacingMd
                color: Theme.surface
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                ColumnLayout {
                    id: gitHooksLayout
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Text {
                        text: "Git 提交门禁与自愈"
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                        color: Theme.primary
                    }

                    Text {
                        text: (typeof mainWindow !== "undefined" && mainWindow !== null && mainWindow.currentProjectId !== "") ? 
                              "当前活跃项目: " + mainWindow.currentProjectId :
                              "⚠️ 未选择活跃项目 (请先返回项目列表，点击一个项目进入工作台)"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm
                        visible: (typeof mainWindow !== "undefined" && mainWindow !== null && mainWindow.currentProjectId !== "")

                        Text {
                            text: "门禁激活状态:"
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textSecondary
                        }

                        Text {
                            text: root.isGitHooksInstalled ? "🟢 已激活 (auto-pm Pre-commit 提交门禁已装配)" : "🟡 未激活 (未装配 Git 提交门禁)"
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                            color: root.isGitHooksInstalled ? Theme.success : Theme.warning
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm
                        visible: (typeof mainWindow !== "undefined" && mainWindow !== null && mainWindow.currentProjectId !== "")

                        PrimaryButton {
                            text: "安装门禁"
                            enabled: !root.isGitHooksInstalled
                            onClicked: {
                                var res = workbenchBridge.installHooks(mainWindow.currentProjectId)
                                resultMessage = res.message
                                loadData()
                            }
                        }

                        PrimaryButton {
                            text: "卸载门禁"
                            type: "danger"
                            enabled: root.isGitHooksInstalled
                            onClicked: {
                                var res = workbenchBridge.uninstallHooks(mainWindow.currentProjectId)
                                resultMessage = res.message
                                loadData()
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            Connections {
                target: (typeof mainWindow !== "undefined") ? mainWindow : null
                function onCurrentProjectIdChanged() {
                    loadData()
                }
            }

            // ── 结果消息 ─────────────────────────────────
            Text {
                Layout.fillWidth: true
                visible: resultMessage !== ""
                text: resultMessage
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }
        }
    }

    // ── 清除缓存确认对话框 ──────────────────────────────
    Dialog {
        id: clearCacheDialog
        title: "清除缓存"
        dialogWidth: 400
        dialogHeight: 200
        showButtons: false
        _isOpen: false

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Text {
                Layout.fillWidth: true
                text: "⚠将删除缓存文件："
                font.pixelSize: Theme.fontSizeMd
                font.bold: true
                color: Theme.error
            }

            Text {
                Layout.fillWidth: true
                text: settingsData.db_path || ""
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textPrimary
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: "删除后需重建索引恢复数据，是否继续？"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "取消"
                    type: "ghost"
                    onClicked: clearCacheDialog.close()
                }

                PrimaryButton {
                    text: "确认清除"
                    type: "danger"
                    onClicked: {
                        var result = workbenchBridge.clearCache()
                        resultMessage = result.message
                        clearCacheDialog.close()
                        loadData()
                    }
                }
            }
        }
    }

    // ── 重建索引确认对话框 ──────────────────────────────
    Dialog {
        id: rebuildDialog
        title: "重建索引"
        dialogWidth: 400
        dialogHeight: 160
        showButtons: false
        _isOpen: false

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Text {
                Layout.fillWidth: true
                text: "⚠将强制全量扫描工作空间并重建索引，可能耗时较长，是否继续？"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textPrimary
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "取消"
                    type: "ghost"
                    onClicked: rebuildDialog.close()
                }

                PrimaryButton {
                    text: "确认重建"
                    onClicked: {
                        var result = workbenchBridge.rebuildIndex()
                        resultMessage = result.message
                            + "（项目数: " + result.projects_found
                            + " / 变更 " + result.changes_found + ""
                        rebuildDialog.close()
                        loadData()
                    }
                }
            }
        }
    }

    // ── 工作空间根目录选择对话框 ──────────────────────────
    FolderDialog {
        id: workspaceDirDialog
        title: "选择全局工作空间根目录"
        currentFolder: settingsData.workspace_root ? "file:///" + settingsData.workspace_root.replace(/\\/g, "/") : ""
        onAccepted: {
            var path = selectedFolder.toString()
            if (path.indexOf("file:///") === 0) {
                path = path.substring(8);
            } else if (path.indexOf("file://") === 0) {
                path = path.substring(7);
            }
            path = path.replace(/\//g, "\\")
            path = decodeURIComponent(path)

            var res = workbenchBridge.saveWorkspaceRoot(path)
            if (res && res.config_saved) {
                resultMessage = res.message
                loadData()
                if (res.runtime_reloaded) {
                    workbenchBridge.refreshProjects()
                }
            } else {
                resultMessage = "保存失败: " + (res ? res.message : "未知错误")
            }
        }
    }

    Component.onCompleted: loadData()
}

