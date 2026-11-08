// EditChangeDialog.qml - 编辑变更单属性对话框（V0.6.0 W3-S11）
//
// 提供变更单的字段编辑能力，直接调用 changeBridge.updateChange() 保存

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false
    property string changeNumber: ""

    // 字段属性
    property string changeTitle: ""
    property string domain: "PLC"
    property string nature: "REQ"
    property string applicant: ""
    property string background: ""
    property string necessity: ""
    property string references: ""
    property string plannedDate: ""
    property string urgency: "normal"
    property string riskLevel: "low"
    property string mitigation: ""
    property string propagationChain: ""
    property string projectId: ""

    // ── 信号 ────────────────────────────────────────────
    signal changeSaved(string changeNumber)
    signal cancelled()

    visible: _isOpen
    anchors.fill: parent

    // 填充数据函数
    function prefill(detail) {
        if (!detail) return
        root.changeNumber = detail.change_number || ""
        root.projectId = detail.project_id || ""
        root.changeTitle = detail.title || ""
        root.domain = detail.domain || "PLC"
        root.nature = detail.business_nature || "REQ"
        root.applicant = detail.applicant || ""
        root.background = detail.background || ""
        root.necessity = detail.necessity || ""
        root.references = detail.references || ""
        root.plannedDate = detail.planned_date || ""
        root.urgency = detail.urgency || "normal"
        root.riskLevel = detail.risk_level || "low"
        root.mitigation = detail.mitigation || ""
        root.propagationChain = detail.propagation_chain || ""

        // 同步下拉框的 index
        var domains = ["PLC", "HMI", "ELEC", "MECH", "SCPT", "DOCU", "SAFE"]
        domainCombo.currentIndex = Math.max(0, domains.indexOf(root.domain))

        var natures = ["REQ", "DSN", "IMP", "TEST", "OPT", "DEF"]
        natureCombo.currentIndex = Math.max(0, natures.indexOf(root.nature))

        var urgencies = ["normal", "urgent", "critical"]
        urgencyCombo.currentIndex = Math.max(0, urgencies.indexOf(root.urgency))

        var risks = ["low", "medium", "high"]
        riskCombo.currentIndex = Math.max(0, risks.indexOf(root.riskLevel))
    }

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.5
        visible: root._isOpen
        MouseArea { anchors.fill: parent; onClicked: {} }
    }

    GlassPanel {
        anchors.centerIn: parent
        width: 600
        height: 560
        radius: Theme.radiusLg
        visible: root._isOpen

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            // 标题栏
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                color: Theme.primary
                radius: Theme.radiusMd

                Text {
                    anchors.centerIn: parent
                    text: "编辑变更单 - " + root.changeNumber
                    color: "white"
                    font.pixelSize: Theme.fontSizeLg
                    font.bold: true
                }
            }

            // 表单内容
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    width: parent.width - 24
                    Layout.margins: Theme.spacingLg
                    spacing: Theme.spacingSm

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "变更标题"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.changeTitle
                            onTextChanged: root.changeTitle = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "技术领域"; width: 80; color: Theme.textSecondary }
                        ComboBox {
                            id: domainCombo
                            model: ["PLC", "HMI", "ELEC", "MECH", "SCPT", "DOCU", "SAFE"]
                            onActivated: root.domain = currentText
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "变更性质"; width: 80; color: Theme.textSecondary }
                        ComboBox {
                            id: natureCombo
                            model: ["REQ (需求)", "DSN (设计)", "IMP (实施)", "TEST (测试)", "OPT (优化)", "DEF (缺陷)"]
                            onActivated: {
                                var map = ["REQ", "DSN", "IMP", "TEST", "OPT", "DEF"]
                                root.nature = map[currentIndex]
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "申请人"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.applicant
                            onTextChanged: root.applicant = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "计划日期"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            placeholderText: "如 2026-07-09"
                            text: root.plannedDate
                            onTextChanged: root.plannedDate = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "紧急程度"; width: 80; color: Theme.textSecondary }
                        ComboBox {
                            id: urgencyCombo
                            model: ["normal", "urgent", "critical"]
                            onActivated: root.urgency = currentText
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "风险等级"; width: 80; color: Theme.textSecondary }
                        ComboBox {
                            id: riskCombo
                            model: ["low", "medium", "high"]
                            onActivated: root.riskLevel = currentText
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "背景说明"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.background
                            onTextChanged: root.background = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "必要性说明"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.necessity
                            onTextChanged: root.necessity = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "参考依据"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.references
                            onTextChanged: root.references = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "缓解措施"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.mitigation
                            onTextChanged: root.mitigation = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "传播链评估"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.propagationChain
                            onTextChanged: root.propagationChain = text
                            color: Theme.textPrimary
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }
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
                    Item { Layout.fillWidth: true }
                    PrimaryButton {
                        text: "取消"
                        type: "ghost"
                        Layout.preferredWidth: 80
                        onClicked: { root._isOpen = false; root.cancelled() }
                    }
                    PrimaryButton {
                        text: "保存"
                        type: "primary"
                        Layout.preferredWidth: 80
                        enabled: root.changeTitle !== "" && root.applicant !== ""
                        onClicked: {
                            if (typeof changeBridge !== "undefined" && changeBridge !== null) {
                                var updates = {
                                    "title": root.changeTitle,
                                    "domain": root.domain,
                                    "business_nature": root.nature,
                                    "applicant": root.applicant,
                                    "background": root.background,
                                    "necessity": root.necessity,
                                    "references": root.references,
                                    "planned_date": root.plannedDate,
                                    "urgency": root.urgency,
                                    "risk_level": root.riskLevel,
                                    "mitigation": root.mitigation,
                                    "propagation_chain": root.propagationChain
                                }
                                var res = changeBridge.updateChange(root.changeNumber, updates, root.projectId)
                                if (res && !res.success) {
                                    console.error("[QML] 更新变更单失败: " + JSON.stringify(res))
                                } else {
                                    root.changeSaved(root.changeNumber)
                                }
                            }
                            root._isOpen = false
                        }
                    }
                }
            }
        }
    }
}
