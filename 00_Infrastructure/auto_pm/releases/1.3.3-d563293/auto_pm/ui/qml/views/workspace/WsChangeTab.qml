// WsChangeTab.qml — 工程变更控制矩阵 Tab V1.0.0 (CHG-123: 驾驶舱模式)
// 从 WorkspaceView.qml 的 changeTab（原 L733-L951）提取
// 状态属性全部通过 property 从 WorkspaceView 绑定传入

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../../theme"

Item {
    id: root

    // ── 公开属性（由 WorkspaceView 绑定）
    property var    changesList: []
    property var    filteredChangesList: []
    property var    selectedChangeDetail: ({})
    property var    changeSummary: ({})
    property var    currentChangeStateMachine: ({})
    property string currentChangeNumber: ""
    property string currentProjectId: ""
    property string searchKeyword: ""
    property string selectedStatusFilter: "ALL"
    property string selectedDomainFilter: "ALL"
    property int    viewWidth: 800   // WorkspaceView 宽度，用于计算分栏比例

    // ── 信号
    signal changeSelected(string changeNumber)
    signal searchFilterChanged(string keyword)
    signal statusFilterChanged(string filter)
    signal domainFilterChanged(string filter)
    signal initializePmRequested()

    ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        clip: true

        ColumnLayout {
            width: parent.width - 16
            spacing: Theme.spacingLg

            // 状态流转机器（CHG-123 V10 原型）
            DashboardStateMachine {
                Layout.fillWidth: true
                Layout.preferredHeight: 180
                title: root.changesList.length > 0 ? "变更状态流转" : "暂无变更"
                tagText: root.currentChangeNumber
                stateMachine: root.currentChangeStateMachine
            }

            ActivityTimeline {
                Layout.fillWidth: true
                Layout.preferredHeight: 220
                activities: root.changeSummary.activities || []
            }

            // 变更列表 + 详情面板（Split View）
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 520
                spacing: Theme.spacingLg

                // 左侧：变更列表
                Rectangle {
                    Layout.preferredWidth: root.viewWidth * 0.5 - Theme.spacingLg
                    Layout.fillHeight: true
                    color: Theme.surface
                    radius: Theme.radiusMd
                    border.color: Theme.border
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingSm

                        // 列表标题行
                        RowLayout {
                            Layout.fillWidth: true
                            anchors.leftMargin: Theme.spacingMd
                            anchors.rightMargin: Theme.spacingMd
                            anchors.topMargin: Theme.spacingMd
                            Text {
                                text: "变更列表"
                                font.pixelSize: Theme.fontSizeMd; font.bold: true
                                color: Theme.textPrimary
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "共 " + root.filteredChangesList.length + " 条"
                                font.pixelSize: Theme.fontSizeSm; color: Theme.textMuted
                            }
                        }

                        // 过滤工具栏
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: Theme.spacingMd
                            Layout.rightMargin: Theme.spacingMd
                            spacing: Theme.spacingSm

                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 28
                                placeholderText: "搜索变更单号/标题..."
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textPrimary
                                background: Rectangle {
                                    color: Theme.glassBg; radius: Theme.radiusSm
                                    border.color: Theme.glassBorder; border.width: 1
                                }
                                onTextChanged: root.searchFilterChanged(text)
                            }
                            ComboBox {
                                Layout.preferredWidth: 100; Layout.preferredHeight: 28
                                model: ["全部状态","草稿","已提交","审核中","已批准","实施中","已完成","已关闭"]
                                property var keys: ["ALL","draft","submitted","under_review","approved","implementing","completed","closed"]
                                onCurrentIndexChanged: root.statusFilterChanged(keys[currentIndex])
                            }
                            ComboBox {
                                Layout.preferredWidth: 100; Layout.preferredHeight: 28
                                model: ["全部领域","PLC","HMI","ELEC","DOCU"]
                                property var keys: ["ALL","PLC","HMI","ELEC","DOCU"]
                                onCurrentIndexChanged: root.domainFilterChanged(keys[currentIndex])
                            }
                        }

                        // 变更单列表
                        ListView {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; spacing: Theme.spacingSm
                            model: root.filteredChangesList

                            ColumnLayout {
                                anchors.centerIn: parent
                                visible: root.filteredChangesList.length === 0
                                spacing: Theme.spacingMd
                                Text {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: (root.selectedDomainFilter === "ALL" && root.selectedStatusFilter === "ALL" && root.searchKeyword.trim() === "") ? "该项目暂无变更单" : "该筛选条件下暂无变更单"
                                    color: Theme.textMuted; font.pixelSize: Theme.fontSizeMd
                                }
                                PrimaryButton {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "🔧 初始化项目 PM 与变更管理"
                                    type: "primary"; Layout.preferredWidth: 200
                                    visible: root.selectedDomainFilter === "ALL" && root.selectedStatusFilter === "ALL" && root.searchKeyword.trim() === ""
                                    onClicked: root.initializePmRequested()
                                }
                            }

                            delegate: Rectangle {
                                width: parent.width; height: 60
                                color: Theme.background; radius: Theme.radiusSm
                                border.color: Theme.border; border.width: 1
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: Theme.spacingSm
                                    spacing: Theme.spacingSm
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2
                                        Text { text: modelData.change_number || ""; font.pixelSize: Theme.fontSizeMd; font.bold: true; color: Theme.textPrimary }
                                        Text { text: modelData.title || "(无标题)"; font.pixelSize: Theme.fontSizeSm; color: Theme.textSecondary; elide: Text.ElideRight; Layout.fillWidth: true }
                                    }
                                    Badge { text: modelData.domain || ""; type: "default" }
                                    Badge { text: modelData.status || ""; type: modelData.status || "default" }
                                }
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: root.changeSelected(modelData.change_number)
                                }
                            }
                        }
                    }
                }

                // 右侧：详情面板
                ChangeDetailPanel {
                    Layout.preferredWidth: root.viewWidth * 0.5 - Theme.spacingLg
                    Layout.fillHeight: true
                    changeDetail: root.selectedChangeDetail
                    changeNumber: root.selectedChangeDetail.change_number || ""
                    projectId: root.currentProjectId
                }
            }
        }
    }
}
