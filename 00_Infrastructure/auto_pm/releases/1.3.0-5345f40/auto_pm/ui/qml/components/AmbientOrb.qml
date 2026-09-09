// AmbientOrb.qml - 光晕背景球（对齐原型 V7 .ambient-orb）
//
// CHG-SCPT-2026-102 T2：深色玻璃拟物背景装饰
//
// 用法：放在背景层，作为装饰光晕（2 个 orb 错落分布）
//   AmbientOrb {
//       width: 400; height: 400
//       glowColor: "#6366f1"
//       anchors.top: parent.top; anchors.left: parent.left
//       anchors.margins: -100  // 部分溢出视口
//   }
import QtQuick

Rectangle {
    id: root

    // 可配置光晕颜色（默认靛蓝，对齐原型 V7 orb-1）
    property color glowColor: "#6366f1"

    radius: width / 2  // 圆形
    color: glowColor
    opacity: 0.08      // 低透明度模拟光晕扩散
}
