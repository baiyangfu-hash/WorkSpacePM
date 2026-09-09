// DeleteConfirmDialog.qml - 删除确认对话框（M4 CHG-115）
//
// 破坏性操作确认对话框，要求用户输入项目名称确认删除

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
    property string confirmText: ""

    // 信号
    signal confirmed(string projectId)
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 999

    function open(pid, pname) {
        if (pid) root.projectId = pid
        if (pname) root.projectName = pname
        root.confirmText = ""
        root._isOpen = true
    }

    function close() {
        root._isOpen = false
    }

    // 遮罩层
    Rectangle {
        anchors.fill: parent
        color: "#b3000000"
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

            // 警告图标 + 标题
            RowLayout {
                Text {
                    text: "⚠"
                    font.pixelSize: Theme.fontSizeXxl
                }
                Text {
                    text: "确认删除项目"
                    color: Theme.error
                    font.pixelSize: Theme.fontSizeXl
                    font.bold: true
                }
            }

            Text {
                text: "此操作不可撤销！将永久删除项目目录及其所有内容。"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSizeMd
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Text {
                text: "请输入项目名称 \"" + root.projectName + "\" 以确认删除："
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeMd
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            TextField {
                id: confirmField
                Layout.fillWidth: true
                placeholderText: "输入项目名称确认"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeMd
                onTextChanged: root.confirmText = text
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
                    text: "确认删除"
                    type: "danger"
                    Layout.preferredWidth: 100
                    enabled: root.confirmText === root.projectName
                    onClicked: {
                        root.confirmed(root.projectId)
                        root.close()
                    }
                }
            }
        }
    }
}