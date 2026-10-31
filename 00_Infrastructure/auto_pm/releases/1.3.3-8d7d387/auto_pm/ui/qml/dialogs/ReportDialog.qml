// ReportDialog.qml - 报告生成对话框（V0.6.0 W3-S16）
//
// 选择报告类型 + 项目范围 → 生成报告（PDF/Markdown/HTML）
// 显示生成进度 + 输出路径

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string reportType: "summary"
    property string outputFormat: "markdown"
    property string outputPath: ""
    property bool isGenerating: false
    property real progress: 0.0

    // ── 信号 ────────────────────────────────────────────
    signal reportGenerated(string outputPath)
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.4
        visible: root._isOpen
        MouseArea { anchors.fill: parent; onClicked: {} }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 520
        height: 420
        color: Theme.background
        radius: Theme.radiusLg
        border.color: Theme.border
        border.width: 1
        visible: root._isOpen

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                color: Theme.primary
                Text {
                    anchors.centerIn: parent
                    text: "生成报告"
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Theme.spacingLg
                spacing: Theme.spacingMd

                // 报告类型
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "报告类型"; width: 100; color: Theme.textSecondary }
                    ComboBox {
                        model: ["summary", "detailed", "change_history", "spec_drift"]
                        onActivated: root.reportType = currentText
                    }
                }

                // 输出格式
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "输出格式"; width: 100; color: Theme.textSecondary }
                    ComboBox {
                        model: ["markdown", "html", "pdf"]
                        onActivated: root.outputFormat = currentText
                    }
                }

                // 输出路径
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "输出路径"; width: 100; color: Theme.textSecondary }
                    TextField {
                        Layout.fillWidth: true
                        placeholderText: "选择输出位置"
                        text: root.outputPath
                        onTextChanged: root.outputPath = text
                    }
                }

                // 进度条
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 8
                    color: Theme.border
                    radius: 4
                    visible: root.isGenerating

                    Rectangle {
                        width: parent.width * root.progress
                        height: parent.height
                        color: Theme.primary
                        radius: 4
                    }
                }

                Text {
                    text: Math.round(root.progress * 100) + "%"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    visible: root.isGenerating
                    Layout.alignment: Qt.AlignHCenter
                }

                Item { Layout.fillHeight: true }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: Theme.surface
                Rectangle {
                    anchors.top: parent.top
                    anchors.fill: parent
                    height: 1
                    color: Theme.border
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    Item { Layout.fillWidth: true }
                    PrimaryButton {
                        text: "取消"
                        type: "ghost"
                        Layout.preferredWidth: 80
                        enabled: !root.isGenerating
                        onClicked: { root._isOpen = false; root.cancelled() }
                    }
                    PrimaryButton {
                        text: "生成"
                        type: "primary"
                        Layout.preferredWidth: 80
                        enabled: !root.isGenerating && root.outputPath !== ""
                        onClicked: {
                            root.isGenerating = true
                            root.progress = 0.0
                            // 模拟进度（实际由 Python 端驱动）
                            for (var i = 0; i <= 10; i++) {
                                root.progress = i / 10
                            }
                            root.isGenerating = false
                            root.reportGenerated(root.outputPath)
                            root._isOpen = false
                        }
                    }
                }
            }
        }
    }
}
