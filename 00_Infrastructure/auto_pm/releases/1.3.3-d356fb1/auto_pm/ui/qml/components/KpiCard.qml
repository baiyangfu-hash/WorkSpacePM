// KpiCard.qml - KPI 卡片组件（CHG-106 T3 / CHG-111 自适应修复）
//
// 单个 KPI 卡片：标题行（标题+图标）+ 主数值 + 副文本
// 对齐 V7 原型 .kpi-card（02_设计/Html原型预览/012_UI架构原型_V7.html L1001-1026）
//
// CHG-111 修复：字号自适应 + ToolTip 兜底，解决长文本（如变更单号）溢出问题
//
// 用法：
//   KpiCard {
//       title: "遗留技术债"
//       value: "0"
//       valueSuffix: "项"
//       subtitle: "V0.9.2 已偿还全部 34 项"
//       iconText: "⚠"
//       iconColor: Theme.warning
//   }

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

GlassPanel {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string title: ""        // 卡片标题
    property string value: "0"       // 主数值
    property string valueSuffix: ""  // 数值后缀（如"项"，小号灰色）
    property string subtitle: ""     // 副文本
    property color valueColor: Theme.textPrimary  // 数值颜色
    property color iconColor: Theme.primary       // 图标颜色
    property string iconText: ""     // 图标字符（Unicode/emoji）

    implicitHeight: 120

    // ── 字号自适应：根据 value 长度动态缩放 ──────────────
    readonly property int _adaptiveFontSize: {
        var len = root.value.length
        if (len <= 3) return Theme.fontSizeXxl    // 24px
        if (len <= 6) return Theme.fontSizeXl     // 20px
        if (len <= 12) return Theme.fontSizeLg    // 16px
        return Theme.fontSizeMd                    // 14px
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingXs

        // 标题行：标题（左）+ 图标（右）
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            Text {
                text: root.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeMd
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            Text {
                text: root.iconText
                color: root.iconColor
                font.pixelSize: 20
                visible: root.iconText !== ""
            }
        }

        // 主数值 + 后缀
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingXs

            Text {
                id: valueText
                text: root.value
                color: root.valueColor
                font.pixelSize: root._adaptiveFontSize
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            Text {
                text: root.valueSuffix
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Normal
                visible: root.valueSuffix !== ""
                Layout.alignment: Qt.AlignBottom
                bottomPadding: 2
            }
        }

        // 副文本
        Text {
            id: subtitleText
            text: root.subtitle
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            elide: Text.ElideRight
            visible: root.subtitle !== ""
        }

        // 弹性占位，让内容顶部对齐
        Item {
            Layout.fillHeight: true
            Layout.fillWidth: true
        }
    }

    // ── ToolTip：hover 时显示完整 value（仅当文本被截断时）──
    HoverHandler {
        id: valueHover
    }

    ToolTip {
        visible: valueHover.hovered && root.value.length > 12
        text: root.value
        delay: 500
    }

    // ── ToolTip：hover 时显示完整 subtitle（仅当文本被截断时）──
    HoverHandler {
        id: subtitleHover
    }

    ToolTip {
        visible: subtitleHover.hovered && root.subtitle.length > 30
        text: root.subtitle
        delay: 500
    }
}