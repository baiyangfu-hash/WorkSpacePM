// KpiGrid.qml - KPI 网格容器（CHG-106 T3）
//
// 4 列等宽 KPI 卡片网格，对齐 V7 原型 .kpi-grid（L1000）
//
// 用法：
//   KpiGrid {
//       KpiCard { title: "技术债"; value: "0" }
//       KpiCard { title: "通过率"; value: "100%" }
//       KpiCard { ... }
//       KpiCard { ... }
//   }

import QtQuick
import QtQuick.Layouts
import "../theme"

RowLayout {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property int columnCount: 4       // 列数（默认 4）
    property int columnSpacing: Theme.spacingMd  // 列间距

    spacing: root.columnSpacing
    layoutDirection: Qt.LeftToRight

    // 子项自动等宽
    onChildrenChanged: {
        for (let i = 0; i < children.length; i++) {
            if (children[i] instanceof Item) {
                children[i].Layout.fillWidth = true
                children[i].Layout.fillHeight = true
                children[i].Layout.preferredWidth = 0
            }
        }
    }
}
