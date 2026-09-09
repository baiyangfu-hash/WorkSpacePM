// Badge.qml - 可复用徽标组件（V0.6.0 W2-S4）
//
// 圆角胶囊型徽标，用于技术栈/阶段/状态/紧急程度等可视化标记。
// 支持 5 种语义类型，每种类型映射 Theme.qml 的颜色 token。
//
// 用法：
//   Badge { text: "PLC"; type: "plc" }
//   Badge { text: "在研"; type: "developing" }
//   Badge { text: "draft"; type: "draft" }

import QtQuick
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string text: ""
    property string type: "default"  // plc/python/unknown/developing/commissioning/production/archived/draft/submitted/approved/implementing/completed/closed/archived/urgent/critical/default

    // ── 颜色映射 ────────────────────────────────────────
    readonly property var _colorMap: ({
        "plc": Theme.badgePlc,
        "python": Theme.badgePython,
        "unknown": Theme.badgeUnknown,
        "developing": Theme.phaseDeveloping,
        "commissioning": Theme.phaseCommissioning,
        "production": Theme.phaseProduction,
        "archived": Theme.phaseArchived,
        "draft": "#6b7280",
        "submitted": "#3b82f6",
        "under_review": "#3b82f6",
        "approved": "#10b981",
        "conditionally_approved": "#f59e0b",
        "rejected": "#ef4444",
        "implementing": "#8b5cf6",
        "pending_acceptance": "#f59e0b",
        "accepting": "#f59e0b",
        "completed": "#10b981",
        "closed": "#10b981",
        "urgent": Theme.warning,
        "critical": Theme.error,
        "default": Theme.textSecondary
    })

    readonly property color _bgColor: _colorMap[type] || Theme.textSecondary

    // ── 视觉样式 ────────────────────────────────────────
    color: _bgColor
    radius: height / 2
    implicitWidth: badgeText.implicitWidth + 16
    implicitHeight: 22

    Text {
        id: badgeText
        anchors.centerIn: parent
        text: root.text
        color: "white"
        font.pixelSize: Theme.fontSizeXs
        font.bold: true
    }
}
