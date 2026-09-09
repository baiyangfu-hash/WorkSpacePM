// PmInitializeConfirmDialog.qml - 初始化 PM 规范与变更管理确认对话框
//
// 确认是否为当前选中的老项目初始化 PM 框架及变更自愈系统（包括 PM_SESSION 和首个创世变更单）

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string projectId: ""
    property string projectName: ""

    // 信号
    signal confirmed(string projectId)
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 999

    function open(pid, pname) {
        if (pid) root.projectId = pid
        if (pname) root.projectName = pname
        root._isOpen = true
    }

    function close() {
        root._isOpen = false
    }

    // 遮罩层
    Rectangle {
        anchors.fill: parent
        color: "#80000000"
        MouseArea {
            anchors.fill: parent
            onClicked: root.cancelled()
        }
    }

    // 对话框主体
    GlassPanel {
        width: 420
        height: columnLayout.implicitHeight + Theme.spacingXl * 2
        anchors.centerIn: parent
        radius: Theme.radiusLg

        ColumnLayout {
            id: columnLayout
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // 图标 + 标题
            RowLayout {
                Text {
                    text: "🔧"
                    font.pixelSize: Theme.fontSizeXxl
                }
                Text {
                    text: "初始化项目 PM 规范"
                    color: Theme.primary
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                }
            }

            Text {
                text: "将为项目 \"" + root.projectName + "\" (" + root.projectId + ") 自动补齐以下基础管理框架："
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeMd
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Text {
                text: "• 建立 PM 专属管理目录\n• 自动生成单一真源 PM_SESSION 规范文档\n• 自动生成立项表草稿模板\n• 自动生成变更台账并补齐首个创世变更单\n\n注意：此操作不会修改、覆盖您的任何核心代码或 PLC 程序块。"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeSm
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            // 按钮栏
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingMd

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "取消"
                    type: "ghost"
                    Layout.preferredWidth: 80
                    onClicked: root.cancelled()
                }

                PrimaryButton {
                    text: "确认初始化"
                    type: "primary"
                    Layout.preferredWidth: 110
                    onClicked: {
                        root.confirmed(root.projectId)
                        root.close()
                    }
                }
            }
        }
    }
}
