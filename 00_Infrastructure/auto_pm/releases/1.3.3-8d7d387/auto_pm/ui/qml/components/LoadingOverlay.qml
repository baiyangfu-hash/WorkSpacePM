// LoadingOverlay.qml - 异步操作加载指示组件（对齐原型 V7 .loading-overlay L744-772）
//
// CHG-SCPT-2026-107 T1：收尾阶段交互组件
//
// 用法：覆盖在父容器上方，active=true 时显示 spinner + 文本
//   LoadingOverlay {
//       id: loadingOverlay
//       anchors.fill: parent
//       active: false
//       message: "加载中..."
//   }
//   loadingOverlay.active = true  // 显示
//   loadingOverlay.active = false // 隐藏
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property bool active: false          // 是否激活（显示）
    property string message: "加载中..."  // 加载提示文本
    property int spinnerSize: 40         // spinner 尺寸（对齐 V7 .spinner 40x40）

    // ── 视觉基底（对齐 V7 .loading-overlay）────────────
    color: Qt.rgba(0.02, 0.06, 0.09, 0.7)  // rgba(2,6,23,0.7) 深色半透明
    radius: Theme.radiusLg
    visible: active
    opacity: active ? 1.0 : 0.0

    // 平滑过渡（对齐 V7 transition: opacity 0.2s ease）
    Behavior on opacity {
        NumberAnimation { duration: 200; easing.type: Easing.OutQuad }
    }

    // ── 居中内容：spinner + 文本 ───────────────────────
    ColumnLayout {
        anchors.centerIn: parent
        spacing: Theme.spacingMd

        // ── Spinner（对齐 V7 .spinner 40x40 圆形 primary 色边框旋转动画）──
        Item {
            id: spinner
            width: root.spinnerSize
            height: root.spinnerSize
            Layout.alignment: Qt.AlignHCenter

            // 旋转动画（对齐 V7 @keyframes spin 1s linear infinite）
            RotationAnimation on rotation {
                loops: Animation.Infinite
                duration: 1000
                from: 0
                to: 360
                running: root.active
            }

            // 用 ConicalGradient 模拟 border-top-color 效果
            // V7: border: 3px solid rgba(99,102,241,0.2); border-top-color: var(--primary)
            // QML 用 Canvas 绘制环形 spinner
            Canvas {
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var cx = width / 2
                    var cy = height / 2
                    var radius = Math.max(1, Math.min(width, height) / 2 - 3)
                    // 背景环（淡色，对齐 rgba(99,102,241,0.2)）
                    ctx.beginPath()
                    ctx.arc(cx, cy, radius, 0, Math.PI * 2)
                    ctx.lineWidth = 3
                    ctx.strokeStyle = Qt.rgba(0.39, 0.40, 0.94, 0.2)
                    ctx.stroke()
                    // 前景弧（primary 色，对齐 border-top-color: var(--primary)）
                    ctx.beginPath()
                    ctx.arc(cx, cy, radius, -Math.PI / 2, Math.PI / 2)
                    ctx.lineWidth = 3
                    ctx.strokeStyle = Theme.primary.toString()
                    ctx.stroke()
                }
            }
        }

        // ── 加载提示文本 ────────────────────────────────
        Text {
            text: root.message
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeSm
            Layout.alignment: Qt.AlignHCenter
        }
    }
}
