// ProjectEditDialog.qml - 项目编辑对话框（M4 CHG-115）
//
// 编辑项目元数据：phase/description/version/business_line
// 调用 workbenchBridge.editProject() 保存

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

    // 字段属性
    property string phase: ""
    property string description: ""
    property string version: ""
    property string businessLine: ""

    // 信号
    signal projectSaved(string projectId)
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent
    z: 998

    function open(pid, pname, detail) {
        root.projectId = pid || ""
        root.projectName = pname || pid || ""
        if (detail) {
            root.phase = detail.phase || ""
            root.description = detail.description || ""
            root.version = detail.version || ""
            root.businessLine = detail.business_line || ""
        } else if (typeof workbenchBridge !== "undefined" && workbenchBridge !== null && pid) {
            var d = workbenchBridge.getProjectById(pid)
            if (d) {
                root.phase = d.phase || ""
                root.description = d.description || ""
                root.version = d.version || ""
                root.businessLine = d.business_line || ""
            }
        }
        root._isOpen = true
    }

    function close() {
        root._isOpen = false
    }

    function resetForm() {
        root.phase = ""
        root.description = ""
        root.version = ""
        root.businessLine = ""
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
        width: 480
        height: columnLayout.implicitHeight + Theme.spacingXl * 2
        anchors.centerIn: parent
        radius: Theme.radiusLg

        ColumnLayout {
            id: columnLayout
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // 标题
            Text {
                text: "编辑项目: " + root.projectName
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeXl
                font.bold: true
            }

            // 阶段
            Text {
                text: "开发阶段"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
            }
            ComboBox {
                id: phaseCombo
                Layout.fillWidth: true
                model: ["developing", "testing", "deploying", "maintenance", "archived"]
                currentIndex: {
                    var phases = ["developing", "testing", "deploying", "maintenance", "archived"]
                    return Math.max(0, phases.indexOf(root.phase))
                }
                onCurrentTextChanged: root.phase = currentText
            }

            // 描述
            Text {
                text: "项目描述"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
            }
            TextArea {
                id: descField
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                text: root.description
                onTextChanged: root.description = text
                placeholderText: "输入项目描述..."
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeMd
            }

            // 版本号
            Text {
                text: "版本号"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
            }
            TextField {
                id: versionField
                Layout.fillWidth: true
                text: root.version
                onTextChanged: root.version = text
                placeholderText: "如 V1.0.0"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSizeMd
            }

            // 业务线
            Text {
                text: "业务线"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
            }
            ComboBox {
                id: businessLineCombo
                Layout.fillWidth: true
                model: ["SW", "DJ", "JD", "SZ"]
                currentIndex: {
                    var lines = ["SW", "DJ", "JD", "SZ"]
                    return Math.max(0, lines.indexOf(root.businessLine))
                }
                onCurrentTextChanged: root.businessLine = currentText
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
                    text: "保存"
                    type: "primary"
                    Layout.preferredWidth: 90
                    onClicked: {
                        if (typeof workbenchBridge === "undefined" || workbenchBridge === null) return
                        var fields = {}
                        if (root.phase) fields["phase"] = root.phase
                        if (root.description) fields["description"] = root.description
                        if (root.version) fields["version"] = root.version
                        if (root.businessLine) fields["business_line"] = root.businessLine
                        var result = workbenchBridge.editProject(root.projectId, fields)
                        if (result && result.success) {
                            console.log("[QML] ProjectEditDialog: 保存成功")
                            root.projectSaved(root.projectId)
                        } else {
                            console.warn("[QML] ProjectEditDialog: 保存失败 -", result ? result.message : "")
                        }
                    }
                }
            }
        }
    }
}