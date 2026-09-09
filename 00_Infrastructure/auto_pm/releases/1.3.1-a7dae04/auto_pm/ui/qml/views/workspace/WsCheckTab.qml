// WsCheckTab.qml — 工程规范与死区检查 Tab V1.0.0
// 从 WorkspaceView.qml 的 checkTab（原 L953-L1082）提取
// parent 绑定: WorkspaceView 通过 property 传入所需状态
// 预留扩展: 新增检查命令只在此文件添加按钮，不改 WorkspaceView

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../../theme"

Item {
    id: root

    // ── 公开属性（由 WorkspaceView 绑定）
    property var   specCheckResult: ({})
    property bool  checkingSpec: false
    property bool  repairingSpec: false
    property bool  isPlcProject: false
    property bool  specServiceAvailable: false

    // ── 信号
    signal runCheckRequested()
    signal repairRequested()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        // 检查摘要卡片
        Card {
            Layout.fillWidth: true
            title: "规范检查报告"
            bodyText: {
                var r = root.specCheckResult
                if (!r || r.error_count === -1) return "未启用规范检查服务或检查失败"
                return "错误: " + (r.error_count || 0) + "\n" +
                       "警告: " + (r.warning_count || 0) + "\n" +
                       "信息: " + (r.info_count || 0) + "\n" +
                       "退出码: " + (r.exit_code || 0)
            }
        }

        // 操作按钮行
        RowLayout {
            spacing: Theme.spacingMd
            PrimaryButton {
                text: "重新运行检查"
                type: "primary"
                loading: root.checkingSpec
                Layout.preferredWidth: 120
                enabled: root.specServiceAvailable
                onClicked: root.runCheckRequested()
            }
            PrimaryButton {
                text: "一键修复"
                type: "accent"
                loading: root.repairingSpec
                Layout.preferredWidth: 120
                visible: root.isPlcProject
                enabled: root.specServiceAvailable
                onClicked: root.repairRequested()
            }
        }

        // 检查结果列表
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: Theme.spacingXs
            model: root.specCheckResult.results || []

            delegate: Rectangle {
                width: parent ? parent.width : 0
                implicitHeight: detailText.visible ? 54 : 36
                height: implicitHeight
                color: Theme.surface
                radius: Theme.radiusSm
                border.color: Theme.border
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    spacing: 2

                    RowLayout {
                        spacing: Theme.spacingSm
                        Layout.fillWidth: true
                        Badge {
                            text: modelData.severity || ""
                            type: modelData.severity === "ERROR" ? "critical" :
                                  (modelData.severity === "WARNING" ? "urgent" : "default")
                        }
                        Text {
                            text: modelData.check_id || ""
                            font.pixelSize: Theme.fontSizeXs
                            font.bold: true
                            color: Theme.textSecondary
                        }
                        Text {
                            text: {
                                var cid = (modelData.check_id || "").trim()
                                var msg = (modelData.message || "").trim()
                                if (cid && msg.startsWith(cid)) {
                                    msg = msg.substring(cid.length).trim()
                                    if (msg.startsWith(":") || msg.startsWith("-") || msg.startsWith("："))
                                        msg = msg.substring(1).trim()
                                }
                                return msg
                            }
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textPrimary
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        id: detailText
                        text: {
                            var det = (modelData.details || "").trim()
                            var msg = (modelData.message || "").trim()
                            if (det === "" || det === msg || msg.indexOf(det) !== -1) return ""
                            return det
                        }
                        font.pixelSize: Theme.fontSizeXs
                        color: Theme.textMuted
                        elide: Text.ElideRight
                        visible: text !== ""
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
