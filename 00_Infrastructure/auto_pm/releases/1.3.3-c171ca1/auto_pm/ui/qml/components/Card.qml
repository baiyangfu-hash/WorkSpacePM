// Card.qml - 可复用卡片组件（V0.6.0 W2-S4 增强版）
//
// 通用卡片容器：圆角 + 边框 + 阴影 + 标题/副标题/内容区。
// 用于项目卡片、变更卡片、信息卡片等场景。
//
// 用法：
//   Card {
//       title: "项目名称"
//       subtitle: "SW-2026-008"
//       bodyText: "项目描述..."
//   }
//
// 也可通过默认插槽嵌入自定义内容：
//   Card { title: "标题"; Text { text: "自定义内容" } }

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string title: ""
    property string subtitle: ""
    property string bodyText: ""
    property color cardColor: Theme.surface
    property color borderColor: Theme.border
    property int elevation: 1

    // ── 尺寸与外观 ──────────────────────────────────────
    implicitWidth: 320
    implicitHeight: contentLayout.implicitHeight + 2 * Theme.spacingMd
    color: cardColor
    radius: Theme.radiusMd
    border.color: borderColor
    border.width: 1

    // 默认插槽：所有放入 Card 内部的组件均作为 slotLayout 的直接子元素
    default property alias contentData: slotLayout.data

    // ── 内容布局 ────────────────────────────────────────
    ColumnLayout {
        id: contentLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        // 标题
        Text {
            visible: root.title !== ""
            text: root.title
            font.pixelSize: Theme.fontSizeLg
            font.bold: true
            color: Theme.textPrimary
            elide: Text.ElideRight
            Layout.fillWidth: true
        }

        // 副标题
        Text {
            visible: root.subtitle !== ""
            text: root.subtitle
            font.pixelSize: Theme.fontSizeSm
            color: Theme.textSecondary
            elide: Text.ElideRight
            Layout.fillWidth: true
        }

        // 正文
        Text {
            visible: root.bodyText !== ""
            text: root.bodyText
            font.pixelSize: Theme.fontSizeSm
            color: Theme.textPrimary
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        // 自定义插槽布局
        ColumnLayout {
            id: slotLayout
            Layout.fillWidth: true
            spacing: Theme.spacingSm
            visible: children.length > 0
        }
    }
}
