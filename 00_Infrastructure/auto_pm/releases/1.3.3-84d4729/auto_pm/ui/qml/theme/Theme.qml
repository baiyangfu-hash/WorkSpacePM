// Theme.qml - V0.9.3 深色玻璃拟物设计系统（对齐 HTML 原型 V7）
//
// 映射自 02_设计/Html原型预览/012_UI架构原型_V7.html CSS 变量
// V0.6.0 浅色主题 → V0.9.3 深色玻璃拟物（CHG-SCPT-2026-102 T1）
//
// 设计原则：
// - 保留所有 token 名称不变（138 个 qml 测试 + 所有 view 依赖）
// - 颜色值从浅色→深色，文本色同步反转保证 WCAG AA 对比度
// - 新增 glass 系列 token 供 GlassPanel/AmbientOrb 组件使用
//
// QML 端使用方式：import "../theme"  // 自动加载为单例
//                 color: Theme.primary

pragma Singleton

import QtQuick

QtObject {
    // ── 深色玻璃拟物基底色（对齐原型 V7 --bg-*）──────────
    readonly property color background: "#020617"          // --bg-base 深蓝黑
    readonly property color surface: "#0f172a"             // --bg-gradient-2 极深蓝（卡片表面）
    readonly property color sidebarBg: "#0f172a"           // 侧边栏背景（与 surface 一致，玻璃拟物基底）
    readonly property color backgroundTertiary: "#1e293b"  // 三级背景色（容器背景，对齐新面板）
    readonly property color bgCard: "#0f172a"              // 卡片背景色（同 surface，对齐新卡片）

    // ── 功能色（对齐原型 V7）─────────────────────────────
    readonly property color primary: "#6366f1"             // --primary 靛蓝（主交互）
    readonly property color secondary: "#38bdf8"           // --secondary 天蓝（次级，新增）
    readonly property color success: "#10b981"             // --success 绿
    readonly property color warning: "#f59e0b"             // --warning 橙
    readonly property color error: "#ef4444"               // --danger 红

    // ── 玻璃拟物 token（新增，对齐原型 V7 --glass-*）─────
    readonly property color glassBg: Qt.rgba(1.0, 1.0, 1.0, 0.03)       // rgba(255,255,255,0.03) 毛玻璃背景
    readonly property color glassBorder: Qt.rgba(1.0, 1.0, 1.0, 0.08)   // rgba(255,255,255,0.08) 玻璃边框
    readonly property color glassHighlight: Qt.rgba(1.0, 1.0, 1.0, 0.05) // 悬停高亮

    // ── 文本色（深色背景适配，保证 WCAG AA 对比度）──────
    readonly property color textPrimary: "#f1f5f9"         // 主文本（浅色，对比度 >7:1）
    readonly property color textSecondary: "#cbd5e1"       // 次文本（浅灰，对比度 >4.5:1）
    readonly property color textMuted: "#94a3b8"           // 静音文本（中灰，对比度 >3:1）
    readonly property color textTertiary: "#94a3b8"        // 三级文本/辅助色（同 textMuted）

    // ── 边框/分隔（深色适配，复用玻璃边框色）─────────────
    readonly property color border: Qt.rgba(1.0, 1.0, 1.0, 0.08)        // 玻璃边框色
    readonly property color borderSubtle: Qt.rgba(1.0, 1.0, 1.0, 0.04)  // 细微边框色

    // ── 徽标色（保留现有，深色背景可读）──────────────────
    readonly property color badgePlc: "#2563eb"            // PLC 徽标
    readonly property color badgePython: "#16a34a"         // Python 徽标
    readonly property color badgeUnknown: "#6b7280"        // 未分类徽标

    // ── 阶段色（保留现有，深色背景可读）──────────────────
    readonly property color phaseDeveloping: "#3b82f6"     // 开发中
    readonly property color phaseCommissioning: "#f59e0b"  // 调试中
    readonly property color phaseProduction: "#10b981"     // 生产中
    readonly property color phaseArchived: "#6b7280"       // 已归档

    // ── 间距 token（8px 网格系统，保留不变）──────────────
    readonly property int spacingXs: 4
    readonly property int spacingSm: 8
    readonly property int spacingMd: 16
    readonly property int spacingLg: 24
    readonly property int spacingXl: 32

    // ── 排版 token（保留不变，避免布局破坏）──────────────
    readonly property int fontSizeXs: 10
    readonly property int fontSizeSm: 12
    readonly property int fontSizeMd: 14
    readonly property int fontSizeLg: 16
    readonly property int fontSizeXl: 20
    readonly property int fontSizeXxl: 24

    // ── 圆角 token（保留不变）────────────────────────────
    readonly property int radiusSm: 4
    readonly property int radiusMd: 8
    readonly property int radiusLg: 12

    // ── 侧边栏宽度（对齐原型 V7：220 → 280）─────────────
    readonly property int sidebarWidth: 280
}
