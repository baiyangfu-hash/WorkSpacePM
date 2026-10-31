// VarTableEditorView.qml - 变量表编辑器视图（V0.6.0 W3-S5~S9）
//
// 完整变量表编辑器，支持：
// - 8 列 TableView（#/station/signal_type/address/tag/signal_name/device/comment）
// - 双击单元格进入编辑态 + 字段校验
// - 多选 + 批量改类型/地址
// - 万行数据原生虚拟化（TableView 自带）
// - 撤销/重做（Ctrl+Z / Ctrl+Y）
//
// 通过 context property 访问：varTableModel（VarTableModel）

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root
    color: Theme.background

    // ── 公开属性 ────────────────────────────────────────
    property string projectId: ""
    property var selectedRows: []  // 当前选中的行索引列表
    property string lastValidationError: ""

    // ── 顶部工具栏 ──────────────────────────────────────
    Rectangle {
        id: toolbar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 56
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
            spacing: Theme.spacingSm

            Text {
                text: "变量表编辑器"
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
                color: Theme.textPrimary
            }

            Text {
                text: "（" + (typeof varTableModel !== "undefined" && varTableModel ? varTableModel.rowCountQml() : 0) + " 行）"
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }

            Item { Layout.fillWidth: true }

            // 撤销按钮
            PrimaryButton {
                text: "撤销"
                type: "ghost"
                enabled: typeof varTableModel !== "undefined" && varTableModel ? varTableModel.canUndo() : false
                onClicked: {
                    if (typeof varTableModel !== "undefined" && varTableModel) varTableModel.undo()
                }
            }

            // 重做按钮
            PrimaryButton {
                text: "重做"
                type: "ghost"
                enabled: typeof varTableModel !== "undefined" && varTableModel ? varTableModel.canRedo() : false
                onClicked: {
                    if (typeof varTableModel !== "undefined" && varTableModel) varTableModel.redo()
                }
            }

            // 保存按钮
            PrimaryButton {
                text: "保存"
                type: "primary"
                enabled: root.projectId !== ""
                onClicked: {
                    if (typeof deliveryBridge !== "undefined" && deliveryBridge !== null && deliveryBridge.hasService) {
                        var ok = deliveryBridge.saveVarTable(root.projectId, varTableModel)
                        if (ok) {
                            root.lastValidationError = "变量表保存成功"
                        } else {
                            root.lastValidationError = "变量表保存失败"
                        }
                    }
                }
            }

            Rectangle { width: 1; height: 24; color: Theme.border }

            // 批量改类型
            PrimaryButton {
                text: "批量改类型"
                type: "ghost"
                enabled: root.selectedRows.length > 0
                onClicked: batchTypeDialog._isOpen = true
            }

            // 批量改地址
            PrimaryButton {
                text: "批量改地址"
                type: "ghost"
                enabled: root.selectedRows.length > 0
                onClicked: batchAddressDialog._isOpen = true
            }

            Rectangle { width: 1; height: 24; color: Theme.border }

            // 加载示例数据按钮（演示用）
            PrimaryButton {
                text: "加载示例"
                type: "primary"
                onClicked: {
                    if (typeof varTableModel !== "undefined" && varTableModel) {
                        var sample = []
                        for (var i = 0; i < 100; i++) {
                            sample.push({
                                station: "cpu" + (i % 3),
                                signal_type: i % 2 === 0 ? "DI" : "DO",
                                address: "Y" + i,
                                tag: "tag_" + i,
                                signal_name: "信号_" + i,
                                device: "device_" + (i % 5),
                                comment: "注释 " + i
                            })
                        }
                        varTableModel.setEntries(sample)
                    }
                }
            }

            // 万行压测按钮
            PrimaryButton {
                text: "万行压测"
                type: "ghost"
                onClicked: {
                    if (typeof varTableModel !== "undefined" && varTableModel) {
                        var sample = []
                        for (var i = 0; i < 10000; i++) {
                            sample.push({
                                station: "cpu" + (i % 10),
                                signal_type: ["DI", "DO", "AI", "AO"][i % 4],
                                address: "Y" + i,
                                tag: "tag_" + i,
                                signal_name: "信号_" + i,
                                device: "dev_" + (i % 20),
                                comment: "注释 " + i
                            })
                        }
                        varTableModel.setEntries(sample)
                    }
                }
            }
        }
    }

    // 表头
    HorizontalHeaderView {
        id: horizontalHeader
        syncView: tableView
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: toolbar.bottom
        height: 32
        z: 2
    }

    // ── 变量表主体 ──────────────────────────────────────
    TableView {
        id: tableView
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: horizontalHeader.bottom
        anchors.bottom: validationBar.top
        anchors.margins: 0
        clip: true

        // 行选择模式：可多选
        selectionBehavior: TableView.SelectRows
        selectionMode: TableView.ExtendedSelection

        // 行高
        rowHeightProvider: function(row) { return 32 }
        columnWidthProvider: function(col) {
            // 各列宽度分配
            var widths = [40, 100, 100, 120, 150, 200, 100, 200]
            return widths[col] || 100
        }

        model: typeof varTableModel !== "undefined" ? varTableModel : null

        // 委托：单元格
        delegate: Rectangle {
            implicitWidth: 100
            implicitHeight: 32
            color: tableView.currentRow === row ? Theme.surface : Theme.background
            border.color: Theme.border
            border.width: 0.5

            // 选中行高亮
            Rectangle {
                anchors.fill: parent
                color: Theme.primary
                opacity: 0.1
                visible: {
                    var selected = false
                    for (var i = 0; i < root.selectedRows.length; i++) {
                        if (root.selectedRows[i] === row) {
                            selected = true
                            break
                        }
                    }
                    return selected
                }
            }

            // 单元格文本
            Text {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                verticalAlignment: Text.AlignVCenter
                text: display || ""
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeSm
                elide: Text.ElideRight
            }

            // 双击进入编辑态（仅非 # 列）
            MouseArea {
                anchors.fill: parent
                onDoubleClicked: {
                    if (column !== 0) {
                        editLoader.active = true
                        editLoader.item.forceActiveFocus()
                    }
                }
                onClicked: {
                    // 切换选中状态
                    var newSelected = root.selectedRows.slice()
                    var idx = newSelected.indexOf(row)
                    if (idx >= 0) {
                        newSelected.splice(idx, 1)
                    } else {
                        newSelected.push(row)
                    }
                    root.selectedRows = newSelected
                }
            }

            // 编辑态 Loader
            Loader {
                id: editLoader
                active: false
                sourceComponent: column !== 0 ? editComponent : null
                anchors.fill: parent
            }

            Component {
                id: editComponent
                TextField {
                    text: display || ""
                    anchors.fill: parent
                    font.pixelSize: Theme.fontSizeSm
                    selectByMouse: true
                    onEditingFinished: {
                        if (typeof varTableModel !== "undefined" && varTableModel) {
                            var ok = varTableModel.setCell(row, column, text)
                            if (!ok) {
                                root.lastValidationError = "校验失败：值不合法"
                            }
                        }
                        editLoader.active = false
                    }
                    Keys.onEnterPressed: focus = false
                    Keys.onReturnPressed: focus = false
                    Keys.onEscapePressed: {
                        editLoader.active = false
                    }
                }
            }
        }

        // 滚动条
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
    }

    // ── 校验信息栏 ──────────────────────────────────────
    Rectangle {
        id: validationBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 24
        color: Theme.surface

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: Theme.border
        }

        Text {
            anchors.fill: parent
            anchors.leftMargin: Theme.spacingMd
            verticalAlignment: Text.AlignVCenter
            text: root.lastValidationError
            color: root.lastValidationError ? Theme.error : Theme.textMuted
            font.pixelSize: Theme.fontSizeXs
        }
    }

    // ── 批量改类型对话框 ────────────────────────────────
    Dialog {
        id: batchTypeDialog
        title: "批量改信号类型"
        dialogWidth: 360
        dialogHeight: 200
        anchors.fill: parent
        _isOpen: false

        property string selectedType: "DI"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Text {
                text: "选择新的信号类型（影响 " + root.selectedRows.length + " 行）："
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textPrimary
                Layout.fillWidth: true
            }

            ComboBox {
                model: ["DI", "DO", "AI", "AO"]
                currentIndex: 0
                onActivated: batchTypeDialog.selectedType = currentText
                Layout.fillWidth: true
            }
        }

        onOkClicked: {
            var count = 0
            if (typeof varTableModel !== "undefined" && varTableModel) {
                count = varTableModel.batchUpdate(root.selectedRows, 2, batchTypeDialog.selectedType)
            }
            root.lastValidationError = "已批量更新 " + count + " 行的信号类型"
            batchTypeDialog._isOpen = false
        }
        onCancelClicked: batchTypeDialog._isOpen = false
    }

    // ── 批量改地址对话框 ────────────────────────────────
    Dialog {
        id: batchAddressDialog
        title: "批量改地址"
        dialogWidth: 360
        dialogHeight: 200
        anchors.fill: parent
        _isOpen: false

        property string newAddress: ""

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Text {
                text: "输入新地址（影响 " + root.selectedRows.length + " 行）："
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textPrimary
                Layout.fillWidth: true
            }

            TextField {
                id: addressInput
                Layout.fillWidth: true
                placeholderText: "如 Y10"
                onTextChanged: batchAddressDialog.newAddress = text
            }
        }

        onOkClicked: {
            var count = 0
            if (typeof varTableModel !== "undefined" && varTableModel) {
                count = varTableModel.batchUpdate(root.selectedRows, 3, batchAddressDialog.newAddress)
            }
            root.lastValidationError = "已批量更新 " + count + " 行的地址"
            batchAddressDialog._isOpen = false
        }
        onCancelClicked: batchAddressDialog._isOpen = false
    }

    // ── 键盘快捷键：Ctrl+Z / Ctrl+Y ────────────────────
    Shortcut {
        sequence: "Ctrl+Z"
        enabled: typeof varTableModel !== "undefined" && varTableModel ? varTableModel.canUndo() : false
        onActivated: { if (typeof varTableModel !== "undefined" && varTableModel) varTableModel.undo() }
    }

    Shortcut {
        sequence: "Ctrl+Y"
        enabled: typeof varTableModel !== "undefined" && varTableModel ? varTableModel.canRedo() : false
        onActivated: { if (typeof varTableModel !== "undefined" && varTableModel) varTableModel.redo() }
    }
}
