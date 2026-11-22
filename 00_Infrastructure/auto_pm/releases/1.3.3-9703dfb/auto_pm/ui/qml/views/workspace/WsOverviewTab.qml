// WsOverviewTab.qml — 工程健康度概览 Tab V1.0.0
// 从 WorkspaceView.qml 的 overviewTab（原 L465-L731）提取
// 包含: 基本信息/PLC信息/路径/资产汇总/HMI交付物看板

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../../theme"

Item {
    id: root

    // ── 公开属性（由 WorkspaceView 绑定）
    property var    projectDetail: ({})
    property var    assetSummary: ({})
    property bool   refreshingAssets: false
    property string currentProjectId: ""
    property bool   assetServiceAvailable: false
    property bool   hmiPrototypeExists: false

    // ── 信号
    signal refreshAssetsRequested()
    signal openHmiPrototypeRequested()

    ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        clip: true

        GridLayout {
            width: parent.width
            columns: 3
            rowSpacing: Theme.spacingMd
            columnSpacing: Theme.spacingMd

            // 基本信息
            Card {
                Layout.columnSpan: 3; Layout.fillWidth: true
                title: "基本信息"
                bodyText: "项目编号: " + (root.projectDetail.project_id || "") + "\n" +
                          "项目名称: " + (root.projectDetail.name || "") + "\n" +
                          "技术栈: " + (root.projectDetail.stack || "") + "\n" +
                          "阶段: " + (root.projectDetail.phase || "") + "\n" +
                          "版本: " + (root.projectDetail.version || "") + "\n" +
                          "业务线: " + (root.projectDetail.business_line || "")
            }

            // PLC 信息
            Card {
                Layout.fillWidth: true
                title: "PLC 信息"
                bodyText: "PLC 品牌: " + (root.projectDetail.plc_vendor || "未配置") + "\n" +
                          "PLC 型号: " + (root.projectDetail.plc_model || "未配置") + "\n" +
                          "设备类型: " + (root.projectDetail.equipment_type || "未配置")
            }

            // 项目分类
            Card {
                Layout.fillWidth: true
                title: "项目分类"
                bodyText: "项目类型: " + (root.projectDetail.project_type || "未配置") + "\n" +
                          "业务线: " + (root.projectDetail.business_line || "")
            }

            // 项目描述
            Card {
                Layout.fillWidth: true
                title: "项目描述"
                bodyText: root.projectDetail.description || "暂无描述"
            }

            // 项目路径（可选择复制）
            Card {
                Layout.columnSpan: 3; Layout.fillWidth: true
                title: "项目路径"
                ColumnLayout {
                    Layout.fillWidth: true
                    height: implicitHeight
                    spacing: Theme.spacingSm
                    TextEdit {
                        Layout.fillWidth: true
                        text: root.projectDetail.path || ""
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeSm
                        wrapMode: TextEdit.WrapAnywhere
                        readOnly: true; selectByMouse: true
                        activeFocusOnPress: true; persistentSelection: true
                    }
                }
            }

            // 资产汇总（仅 PLC 项目）
            Card {
                Layout.columnSpan: 3; Layout.fillWidth: true
                visible: root.projectDetail.stack === "plc"
                title: "资产汇总"
                ColumnLayout {
                    Layout.fillWidth: true
                    height: implicitHeight
                    spacing: Theme.spacingMd

                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.spacingSm
                        Text {
                            text: {
                                var s = root.assetSummary.status || "未加载"
                                var m = { "healthy":"健康","warning":"告警","missing":"缺失","not_applicable":"不适用" }
                                return "状态: " + (m[s] || s)
                            }
                            font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary; Layout.fillWidth: true
                        }
                        Badge {
                            text: root.assetSummary.total_issues || 0
                            type: { var s = root.assetSummary.status || ""; if (s==="healthy") return "approved"; if (s==="warning") return "urgent"; if (s==="missing") return "critical"; return "default" }
                        }
                    }

                    PrimaryButton {
                        text: "刷新资产数据"; type: "primary"
                        loading: root.refreshingAssets; Layout.preferredWidth: 120
                        enabled: root.assetServiceAvailable
                        onClicked: root.refreshAssetsRequested()
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder; visible: root.assetSummary && Object.keys(root.assetSummary).length > 0 }

                    Text {
                        Layout.fillWidth: true
                        visible: root.assetSummary && Object.keys(root.assetSummary).length > 0
                        text: {
                            var a = root.assetSummary
                            if (!a || Object.keys(a).length === 0) return "点击刷新加载资产数据"
                            var io = a.io_points || {}; var blk = a.program_blocks || {}; var comm = a.communications || {}
                            return "IO 点数: " + (io.count||0) + "（" + (io.exists?"已配置":"缺失") + "）\n" +
                                   "程序块: " + (blk.count||0) + "（" + (blk.exists?"已配置":"缺失") + "）\n" +
                                   "通讯通道: " + (comm.count||0) + "（" + (comm.exists?"已配置":"缺失") + "）\n" +
                                   "问题总数: " + (a.total_issues||0)
                        }
                        font.pixelSize: Theme.fontSizeSm; color: Theme.textPrimary; wrapMode: Text.WordWrap
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: !root.assetSummary || Object.keys(root.assetSummary).length === 0
                        text: "点击刷新加载资产数据"
                        font.pixelSize: Theme.fontSizeSm; color: Theme.textMuted
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: (root.assetSummary.issue_messages || []).length > 0
                        text: { var m = root.assetSummary.issue_messages || []; return "问题明细:\n" + m.join("\n") }
                        font.pixelSize: Theme.fontSizeXs; color: Theme.error; wrapMode: Text.WordWrap
                    }
                }
            }

            // 工程交付物与 HMI 原型看板（STD-910）
            Card {
                Layout.columnSpan: 3; Layout.fillWidth: true
                title: "工程交付物与 HMI 原型看板"
                ColumnLayout {
                    Layout.fillWidth: true; spacing: Theme.spacingMd
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.spacingLg
                        RowLayout {
                            spacing: Theme.spacingXs
                            Text { text: "HMI 交互原型:"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
                            Badge { text: root.hmiPrototypeExists ? "已就绪" : "未生成"; type: root.hmiPrototypeExists ? "approved" : "default" }
                        }
                        RowLayout {
                            spacing: Theme.spacingXs
                            Text { text: "点表映射(STD-910):"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
                            Badge {
                                property var d: (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) ? workbenchBridge.getDeliverySummary(root.currentProjectId) : ({})
                                text: (d && d.tag_table) ? "已对齐" : "未定义"; type: (d && d.tag_table) ? "approved" : "urgent"
                            }
                        }
                        RowLayout {
                            spacing: Theme.spacingXs
                            Text { text: "FAT/SAT 规程:"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
                            Badge {
                                property var d: (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) ? workbenchBridge.getDeliverySummary(root.currentProjectId) : ({})
                                text: (d && d.fat_sat) ? "已归档" : "待生成"; type: (d && d.fat_sat) ? "approved" : "default"
                            }
                        }
                        RowLayout {
                            spacing: Theme.spacingXs
                            Text { text: "操作维保手册:"; color: Theme.textSecondary; font.pixelSize: Theme.fontSizeSm }
                            Badge {
                                property var d: (typeof workbenchBridge !== "undefined" && workbenchBridge !== null) ? workbenchBridge.getDeliverySummary(root.currentProjectId) : ({})
                                text: (d && d.manual) ? "已就绪" : "待生成"; type: (d && d.manual) ? "approved" : "default"
                            }
                        }
                    }
                    PrimaryButton {
                        text: "🌐 在浏览器中打开并走查 HMI 原型"
                        type: "secondary"; Layout.preferredWidth: 240
                        visible: root.hmiPrototypeExists
                        onClicked: root.openHmiPrototypeRequested()
                    }
                }
            }
        }
    }
}
