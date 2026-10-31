// ChangeDetailPanel.qml - 变更单详情面板（CHG-2 T4+T5）
//
// 从 ChangeCenterView.qml 提取的独立详情面板组件
// 包含：基本信息 + 背景 + 必要性 + 风险 + 参考依据 + 文件路径
// 新增：§9 实施记录 + §10 验证项 + 审批时间线 + 状态流转按钮
//
// 数据流：父组件传入 changeDetail(dict) + changeNumber(str)
//         → 面板展示详情 + 状态流转按钮
//         → 用户点击流转按钮 → changeBridge.transitionChange() → statusChanged 信号

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "."

GlassPanel {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property var changeDetail: ({})
    property string changeNumber: ""
    property string projectId: ""

    // ── 信号 ────────────────────────────────────────────
    signal statusChanged()
    signal requestEditChange()

    // ── 状态流转映射 ────────────────────────────────────
    function _getNextStatuses(currentStatus) {
        var map = {
            "draft": ["submitted"],
            "submitted": ["under_review", "draft"],
            "under_review": ["approved", "submitted"],
            "approved": ["implementing"],
            "implementing": ["pending_acceptance"],
            "pending_acceptance": ["accepting"],
            "accepting": ["completed"],
            "completed": ["closed"]
        }
        return map[currentStatus] || []
    }

    function _statusLabel(status) {
        var labels = {
            "draft": "草稿",
            "submitted": "已提交",
            "under_review": "审核中",
            "approved": "已批准",
            "implementing": "实施中",
            "pending_acceptance": "待验收",
            "accepting": "验收中",
            "completed": "已完成",
            "closed": "已关闭"
        }
        return labels[status] || status
    }

    function _doTransition(targetStatus) {
        if (typeof changeBridge === "undefined" || changeBridge === null) return
        var cmd = {
            "change_id": root.changeNumber,
            "target_status": targetStatus,
            "operator": "fubai",
            "note": "GUI 流转: " + targetStatus,
            "project_id": root.projectId
        }
        var result = changeBridge.transitionChange(cmd)
        if (result && result.success === false) {
            console.warn("[QML] ChangeDetailPanel: 流转失败 -", result.message || "")
        } else {
            console.log("[QML] ChangeDetailPanel: 流转成功 →", targetStatus)
            root.statusChanged()
        }
    }

    // ── 时间线数据 ──────────────────────────────────────
    property var timeline: []

    function _loadTimeline() {
        if (typeof changeBridge === "undefined" || changeBridge === null) return
        if (root.changeNumber === "") return
        root.timeline = changeBridge.getChangeTimeline(root.changeNumber, root.projectId)
    }

    onProjectIdChanged: _loadTimeline()
    onChangeNumberChanged: _loadTimeline()
    Component.onCompleted: _loadTimeline()

    // ── 空状态 ──────────────────────────────────────────
    Text {
        anchors.centerIn: parent
        visible: root.changeNumber === ""
        text: "▶ 点击左侧变更单查看详情"
        color: Theme.textMuted
        font.pixelSize: Theme.fontSizeLg
    }

    // ── 详情内容 ────────────────────────────────────────
    ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        visible: root.changeNumber !== ""
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: Theme.spacingMd

            // ── 标题 + 状态流转按钮 ─────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Text {
                    text: root.changeDetail.change_number || ""
                    font.pixelSize: Theme.fontSizeXxl
                    font.bold: true
                    color: Theme.textPrimary
                }

                PrimaryButton {
                    text: "编辑"
                    type: "ghost"
                    Layout.preferredHeight: 28
                    Layout.preferredWidth: 60
                    enabled: typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService
                    onClicked: root.requestEditChange()
                }

                Item { Layout.fillWidth: true }

                // 状态流转按钮（根据当前状态动态显示）
                Repeater {
                    model: root.changeDetail.status ? root._getNextStatuses(root.changeDetail.status) : []

                    PrimaryButton {
                        text: "→" + root._statusLabel(modelData)
                        type: "primary"
                        Layout.preferredHeight: 32
                        enabled: typeof changeBridge !== "undefined" && changeBridge !== null && changeBridge.hasService
                        onClicked: root._doTransition(modelData)
                    }
                }
            }

            // ── 状态 + 领域 + 紧急程度 badges ────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Badge {
                    text: root.changeDetail.status || ""
                    type: root.changeDetail.status || "default"
                }

                Badge {
                    text: root.changeDetail.domain || ""
                    type: "default"
                }

                Badge {
                    text: root.changeDetail.urgency || ""
                    type: root.changeDetail.urgency === "critical" ? "critical" :
                          (root.changeDetail.urgency === "urgent" ? "urgent" : "default")
                }

                Item { Layout.fillWidth: true }
            }

            // ── 基本信息 ──────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "基本信息"
                bodyText: "变更编号: " + (root.changeDetail.change_number || "") + "\n" +
                          "项目编号: " + (root.changeDetail.project_id || "") + "\n" +
                          "项目名称: " + (root.changeDetail.project_name || "") + "\n" +
                          "技术领域: " + (root.changeDetail.domain || "") + "\n" +
                          "业务性质: " + (root.changeDetail.business_nature || "") + "\n" +
                          "影响范围: " + ((root.changeDetail.impact_scope || []).join(", ")) + "\n" +
                          "申请人: " + (root.changeDetail.applicant || "") + "\n" +
                          "申请日期: " + (root.changeDetail.apply_date || "") + "\n" +
                          "计划日期: " + (root.changeDetail.planned_date || "")
            }

            // ── 变更背景 ──────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "§4 变更背景"
                bodyText: root.changeDetail.background || "（未填写）"
            }

            // ── 变更必要性 ────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "§4 变更必要性"
                bodyText: root.changeDetail.necessity || "（未填写）"
            }

            // ── 风险评估 ──────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "§6 风险评估"
                bodyText: "风险等级: " + (root.changeDetail.risk_level || "未评估") + "\n" +
                          "缓解措施: " + (root.changeDetail.mitigation || "未填写") + "\n" +
                          "传播链: " + (root.changeDetail.propagation_chain || "无")
            }

            // ── 参考依据 ──────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "§4 参考依据"
                bodyText: root.changeDetail.references || "（无）"
            }

            // ── §9 实施记录（从 sections dict 取文本）────
            Card {
                Layout.fillWidth: true
                title: "§9 实施记录"
                bodyText: ((root.changeDetail.sections || {})["9"]) || "（未填写）"
            }

            // ── §10 验证项（从 sections dict 取文本）─────
            Card {
                Layout.fillWidth: true
                title: "§10 变更验证"
                bodyText: ((root.changeDetail.sections || {})["10"]) || "（未填写）"
            }

            // ── 审批时间线 ────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "审批时间线"

                ColumnLayout {
                    Layout.fillWidth: true
                    height: implicitHeight
                    spacing: Theme.spacingXs

                    // 空时间线
                    Text {
                        visible: root.timeline.length === 0
                        text: "（暂无审批记录）"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textMuted
                    }

                    // 时间线条目
                    Repeater {
                        model: root.timeline

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingXs

                            Rectangle {
                                Layout.preferredWidth: 4
                                Layout.preferredHeight: 24
                                color: Theme.primary
                                radius: 2
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                Text {
                                    text: (modelData.from_status || "?") + " → " + (modelData.to_status || "?")
                                    font.pixelSize: Theme.fontSizeSm
                                    font.bold: true
                                    color: Theme.textPrimary
                                }

                                Text {
                                    text: (modelData.approver || "") + " · " + (modelData.transition_date || "") + (modelData.comment ? " · " + modelData.comment : "")
                                    font.pixelSize: Theme.fontSizeXs
                                    color: Theme.textSecondary
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }
                }
            }

            // ── 文件路径 ──────────────────────────────────
            Card {
                Layout.fillWidth: true
                title: "变更单文件"
                bodyText: root.changeDetail.file_path || "（未关联文件）"
            }
        }
    }
}
