// Dialog.qml - 可复用对话框组件（V0.6.0 W2-S4）
//
// 模态对话框容器，含遮罩 + 标题栏 + 内容区 + 按钮区。
// 通过 visible 属性控制显隐，通过 default slot 嵌入自定义内容。
//
// 用法：
//   Dialog {
//       id: myDialog
//       title: "新建项目"
//       dialogWidth: 480
//       dialogHeight: 320
//       onCancelClicked: myDialog.close()
//       onOkClicked: { save(); myDialog.close() }
//       ColumnLayout { Text { text: "表单内容" } }
//   }
//   Button { onClicked: myDialog.open() }

import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string title: ""
    property string okText: "确定"
    property string cancelText: "取消"
    property int dialogWidth: 480
    property int dialogHeight: 320
    property bool showButtons: true
    property bool okEnabled: true
    property alias okButtonEnabled: okBtn.enabled

    // ── 内部状态 ────────────────────────────────────────
    // visible 绑定到 _isOpen（避免直接绑定 false 导致外部 setProperty 失效）
    property bool _isOpen: false

    // ── 信号 ────────────────────────────────────────────
    signal okClicked()
    signal cancelClicked()
    signal opened()
    signal closed()

    // ── 状态控制 ────────────────────────────────────────
    visible: _isOpen
    anchors.fill: parent

    function open() {
        root._isOpen = true
        root.opened()
    }

    function close() {
        root._isOpen = false
        root.closed()
    }

    // ── 遮罩层 ──────────────────────────────────────────
    Rectangle {
        id: overlay
        anchors.fill: parent
        color: "#000000"
        opacity: 0.4
        visible: root.visible

        MouseArea {
            anchors.fill: parent
            onClicked: root.cancelClicked()  // 点击遮罩关闭
        }
    }

    // ── 对话框主体 ──────────────────────────────────────
    Rectangle {
        id: dialogContent
        anchors.centerIn: parent
        width: root.dialogWidth
        height: root.dialogHeight
        color: Theme.background
        radius: Theme.radiusLg
        border.color: Theme.border
        border.width: 1
        visible: root.visible

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            // 标题栏
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                color: Theme.primary

                Text {
                    anchors.centerIn: parent
                    text: root.title
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            // 内容区（默认插槽）
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                default property alias children: contentSlot.children
                Item {
                    id: contentSlot
                    anchors.fill: parent
                }
            }

            // 按钮区
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: Theme.surface

                Rectangle {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    color: Theme.border
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Item { Layout.fillWidth: true }

                    PrimaryButton {
                        id: cancelBtn
                        text: root.cancelText
                        type: "ghost"
                        Layout.preferredWidth: 80
                        onClicked: root.cancelClicked()
                    }

                    PrimaryButton {
                        id: okBtn
                        text: root.okText
                        type: "primary"
                        Layout.preferredWidth: 80
                        enabled: root.okEnabled
                        onClicked: root.okClicked()
                    }
                }
            }
        }
    }
}
