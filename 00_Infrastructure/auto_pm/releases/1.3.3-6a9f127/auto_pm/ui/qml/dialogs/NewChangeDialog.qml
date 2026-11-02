// NewChangeDialog.qml - 变更单新建对话框（V1.0.0 CHG-SCPT-2026-114 M4 重构）
//
// V0.6.0 W3-S11 原始版本：表单填写变更单信息，生成 CHG-*.md 文件。
// V1.0.0 CHG-114 重构：
//   - 下拉框中文化（domain/nature 显示中文标签）
//   - 新增 impact_scope 多选（CheckBox 列表）
//   - projectId 改为外部属性（从 ChangeCenterView 上下文传入）
//   - 移除未使用的 changeType 属性
//   - 对齐 constants.py DOMAINS/BUSINESS_NATURES/IMPACT_SCOPES 常量

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

Item {
    id: root

    property bool _isOpen: false

    // ── 外部属性 ────────────────────────────────────────
    property string projectId: ""  // 从 ChangeCenterView 上下文传入

    // ── 表单字段 ────────────────────────────────────────
    property string changeTitle: ""
    property string domain: "PLC"
    property string nature: "REQ"
    property string applicant: "fubai"
    property string background: ""
    property string necessity: ""
    // impact_scope 多选：用 JS object 存储选中状态
    property var _selectedScopes: ({})

    // ── 常量映射 ────────────────────────────────────────
    readonly property var _domainLabels: ({
        "PLC": "PLC程序", "HMI": "HMI程序", "ELEC": "电气设计",
        "MECH": "机械结构", "SCPT": "Python脚本", "DOCU": "工程文档", "SAFE": "安全功能"
    })
    readonly property var _natureLabels: ({
        "REQ": "需求变更", "DEF": "缺陷修复", "OPT": "优化改进",
        "CFG": "配置调整", "EMRG": "紧急变更"
    })
    readonly property var _scopeLabels: ({
        "LOCAL": "局部变更", "MODULE": "模块级变更", "SYSTEM": "系统级变更",
        "CROSS": "跨系统变更", "SAFE": "安全相关变更"
    })
    readonly property var _scopeDescriptions: ({
        "LOCAL": "仅单个POU/画面/IO点 → 项目经理审批",
        "MODULE": "单个设备/单条线 → 项目负责人审批",
        "SYSTEM": "多模块联动/联锁逻辑 → 技术总监审批",
        "CROSS": "PLC+HMI+电气多领域联动 → 高层管理层审批",
        "SAFE": "急停/SIL/安全功能 → 安全负责人+高层联合审批"
    })

    // ── 信号 ────────────────────────────────────────────
    signal changeCreated(string changeNumber, string title)
    signal cancelled()

    // ── 初始化 ──────────────────────────────────────────
    function resetForm() {
        root.changeTitle = ""
        root.domain = "PLC"
        root.nature = "REQ"
        root.applicant = "fubai"
        root.background = ""
        root.necessity = ""
        root._selectedScopes = {}
    }

    function open() {
        resetForm()
        root._isOpen = true
    }

    function close() {
        root._isOpen = false
    }

    visible: _isOpen
    anchors.fill: parent

    // 半透明焦点遮罩
    Rectangle {
        anchors.fill: parent
        color: "#b3000000"
        visible: root._isOpen
        MouseArea { anchors.fill: parent; onClicked: {} }
    }

    // 对话框主体
    Rectangle {
        anchors.centerIn: parent
        width: 600
        height: 600
        color: Theme.background
        radius: Theme.radiusLg
        border.color: Theme.border
        border.width: 1
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
                Text {
                    anchors.centerIn: parent
                    text: "新建变更单"
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

                    // ── 项目编号（只读） ────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "影响项目"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            text: root.projectId
                            readOnly: true
                            color: Theme.textMuted
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    // ── 变更标题 ────────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "变更标题"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            placeholderText: "简明描述变更内容"
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

                    // ── 技术领域 ────────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "技术领域"; width: 80; color: Theme.textSecondary }
                        ComboBox {
                            id: domainCombo
                            Layout.preferredWidth: 240
                            textRole: "label"
                            valueRole: "value"
                            model: [
                                { value: "PLC", label: "PLC (PLC程序)" },
                                { value: "HMI", label: "HMI (HMI程序)" },
                                { value: "ELEC", label: "ELEC (电气设计)" },
                                { value: "MECH", label: "MECH (机械结构)" },
                                { value: "SCPT", label: "SCPT (Python脚本)" },
                                { value: "DOCU", label: "DOCU (工程文档)" },
                                { value: "SAFE", label: "SAFE (安全功能)" }
                            ]
                            onActivated: root.domain = model[currentIndex].value
                            Component.onCompleted: {
                                var vals = ["PLC","HMI","ELEC","MECH","SCPT","DOCU","SAFE"]
                                currentIndex = Math.max(0, vals.indexOf(root.domain))
                            }
                        }
                    }

                    // ── 变更性质 ────────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "变更性质"; width: 80; color: Theme.textSecondary }
                        ComboBox {
                            id: natureCombo
                            Layout.preferredWidth: 240
                            textRole: "label"
                            valueRole: "value"
                            model: [
                                { value: "REQ", label: "REQ (需求变更)" },
                                { value: "DEF", label: "DEF (缺陷修复)" },
                                { value: "OPT", label: "OPT (优化改进)" },
                                { value: "CFG", label: "CFG (配置调整)" },
                                { value: "EMRG", label: "EMRG (紧急变更)" }
                            ]
                            onActivated: root.nature = model[currentIndex].value
                            Component.onCompleted: {
                                var vals = ["REQ","DEF","OPT","CFG","EMRG"]
                                currentIndex = Math.max(0, vals.indexOf(root.nature))
                            }
                        }
                    }

                    // ── 申请人 ──────────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "申请人"; width: 80; color: Theme.textSecondary }
                        TextField {
                            Layout.fillWidth: true
                            placeholderText: "如 fubai"
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

                    // ── 影响范围（多选） ────────────────────
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingXs
                        Text {
                            text: "影响范围（可多选）"
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSizeSm
                        }
                        Repeater {
                            model: ["LOCAL", "MODULE", "SYSTEM", "CROSS", "SAFE"]
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.spacingXs
                                CheckBox {
                                    checked: root._selectedScopes[modelData] === true
                                    onCheckedChanged: {
                                        var scopes = root._selectedScopes
                                        scopes[modelData] = checked
                                        root._selectedScopes = scopes  // 触发绑定更新
                                    }
                                }
                                Text {
                                    text: root._scopeLabels[modelData] || modelData
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontSizeSm
                                }
                                Text {
                                    text: "— " + (root._scopeDescriptions[modelData] || "")
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontSizeXs
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }

                    // ── 背景说明 ────────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "背景说明"; width: 80; color: Theme.textSecondary }
                        TextArea {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 60
                            placeholderText: "变更背景与现状描述"
                            text: root.background
                            onTextChanged: root.background = text
                            color: Theme.textPrimary
                            wrapMode: TextEdit.Wrap
                            background: Rectangle {
                                color: Theme.glassBg
                                radius: Theme.radiusSm
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    // ── 必要性说明 ──────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "必要性说明"; width: 80; color: Theme.textSecondary }
                        TextArea {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 60
                            placeholderText: "为什么必须进行此变更"
                            text: root.necessity
                            onTextChanged: root.necessity = text
                            color: Theme.textPrimary
                            wrapMode: TextEdit.Wrap
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
                        onClicked: { root.close(); root.cancelled() }
                    }
                    PrimaryButton {
                        text: "创建"
                        type: "primary"
                        Layout.preferredWidth: 80
                        enabled: root.projectId !== "" && root.changeTitle !== "" && root.applicant !== ""
                        onClicked: {
                            if (typeof changeBridge !== "undefined" && changeBridge !== null) {
                                // 收集选中的 impact_scope
                                var scopes = []
                                var scopeKeys = ["LOCAL", "MODULE", "SYSTEM", "CROSS", "SAFE"]
                                for (var i = 0; i < scopeKeys.length; i++) {
                                    if (root._selectedScopes[scopeKeys[i]] === true) {
                                        scopes.push(scopeKeys[i])
                                    }
                                }
                                if (scopes.length === 0) {
                                    scopes = ["LOCAL"]  // 默认
                                }

                                var cmd = {
                                    "project_id": root.projectId,
                                    "title": root.changeTitle,
                                    "domain": root.domain,
                                    "nature": root.nature,
                                    "applicant": root.applicant,
                                    "background": root.background,
                                    "necessity": root.necessity,
                                    "impact_scope": scopes
                                }
                                var res = changeBridge.createChange(cmd)
                                if (res && res.change_number) {
                                    root.changeCreated(res.change_number, root.changeTitle)
                                    root.close()
                                } else {
                                    console.error("[QML] 创建变更失败: " + JSON.stringify(res))
                                }
                            } else {
                                root.close()
                            }
                        }
                    }
                }
            }
        }
    }
}