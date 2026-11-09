// GlassPanel.qml - 毛玻璃容器组件（对齐原型 V7 .glass-panel）
//
// CHG-SCPT-2026-102 T2：深色玻璃拟物基底组件
//
// 用法：作为卡片/面板的容器，内部放内容
//   GlassPanel {
//       width: 200; height: 100
//       Text { text: "内容"; anchors.centerIn: parent; color: Theme.textPrimary }
//   }
import QtQuick
import "../theme"

Rectangle {
    id: root

    // 玻璃拟物基底（深色实底 + 边框 + 圆角，确保浮动对话框具备完好的遮蔽力与对比度）
    color: "#0f172a"
    border.color: Theme.glassBorder
    border.width: 1
    radius: Theme.radiusLg

    // 顶部高光渐变（模拟微弱玻璃光泽）
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: Math.min(40, parent.height * 0.3)
        radius: parent.radius
        clip: true
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.05) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
}
