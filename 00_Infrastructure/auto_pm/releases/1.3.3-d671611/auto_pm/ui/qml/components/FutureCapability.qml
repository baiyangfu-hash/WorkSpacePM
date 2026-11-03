// FutureCapability.qml - 未实现功能灰化占位组件（对齐原型 V7 .future-capability L774-793 + L1145-1152）
//
// CHG-SCPT-2026-107 T2：收尾阶段交互组件
//
// 用法：用于未实现功能的灰化占位提示
//   FutureCapability {
//       title: "详细变量表映射编辑 (Variables Editor)"
//       description: "基线服务目前仅支持资产统计。跨平台细粒度变量级增删改查将在 M4 迭代中提供。"
//       buttonText: "进入变量矩阵视图"
//       badgeText: "🚀 M4 迭代解锁"
//   }
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string title: "未实现功能"
    property string description: "此功能将在后续迭代中提供支持。"
    property string buttonText: "查看详情"
    property string badgeText: "🚀 M4 迭代解锁"
    property string iconText: "🔒"

    // ── 视觉基底（对齐 V7 .future-capability）────────────
    // V7: border: 1px dashed rgba(255,255,255,0.1); background: rgba(255,255,255,0.02); border-radius: 8px
    color: Qt.rgba(1.0, 1.0, 1.0, 0.02)  // 极淡背景
    radius: Theme.radiusMd  // 8px
    implicitHeight: contentLayout.implicitHeight + Theme.spacingXl * 2
    clip: true  // 对齐 overflow: hidden（角标溢出裁剪）

    // ── Dashed 边框（Canvas 绘制，对齐 V7 border: 1px dashed）──
    Canvas {
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = Qt.rgba(1.0, 1.0, 1.0, 0.1)  // rgba(255,255,255,0.1)
            ctx.lineWidth = 1
            ctx.setLineDash([4, 4])  // dashed 虚线
            ctx.beginPath()
            var r = root.radius
            // 圆角矩形路径
            ctx.moveTo(r, 0)
            ctx.lineTo(width - r, 0)
            ctx.arcTo(width, 0, width, r, r)
            ctx.lineTo(width, height - r)
            ctx.arcTo(width, height, width - r, height, r)
            ctx.lineTo(r, height)
            ctx.arcTo(0, height, 0, height - r, r)
            ctx.lineTo(0, r)
            ctx.arcTo(0, 0, r, 0, r)
            ctx.stroke()
        }
    }

    // ── 角标（对齐 V7 .future-capability::before）─────────
    // V7: content '🚀 M4 迭代解锁'; position: absolute; top:12px right:-30px;
    //     background: var(--warning); color: #000; font-size:10px bold; padding:4px 30px; transform: rotate(45deg)
    Rectangle {
        id: badge
        width: 140
        height: 24
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 12
        anchors.rightMargin: -40  // 溢出（对齐 right:-30px + clip 裁剪）
        rotation: 45
        color: Theme.warning
        x: parent.width - 30  // 定位到右上角

        Text {
            anchors.centerIn: parent
            text: root.badgeText
            color: "#000000"
            font.pixelSize: Theme.fontSizeXs  // 10px
            font.bold: true
        }
    }

    // ── 内容居中布局 ────────────────────────────────────
    ColumnLayout {
        id: contentLayout
        anchors.fill: parent
        anchors.margins: Theme.spacingXl  // padding: 24px
        spacing: Theme.spacingSm

        // 顶部留白（避开角标）
        Item { Layout.preferredHeight: Theme.spacingSm }

        // ── 锁图标（对齐 V7 ph-lock-key 32px rgba(255,255,255,0.2)）──
        Text {
            text: root.iconText
            color: Qt.rgba(1.0, 1.0, 1.0, 0.2)  // rgba(255,255,255,0.2)
            font.pixelSize: 32
            Layout.alignment: Qt.AlignHCenter
        }

        // ── 标题（对齐 V7 h3）──────────────────────────────
        Text {
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeLg  // 16px
            font.bold: true
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }

        // ── 描述（对齐 V7 p color:text-muted font-size:13px max-width:500px）──
        Text {
            text: root.description
            color: Theme.textMuted
            font.pixelSize: 13
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            Layout.maximumWidth: 500
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }

        // ── 禁用按钮（对齐 V7 button.btn-outline disabled opacity:0.5）──
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.spacingSm
            Layout.preferredWidth: buttonTextRow.implicitWidth + 24
            Layout.preferredHeight: 36
            radius: Theme.radiusSm
            color: "transparent"
            border.color: Theme.glassBorder
            border.width: 1
            opacity: 0.5  // 对齐 disabled opacity:0.5

            RowLayout {
                id: buttonTextRow
                anchors.centerIn: parent
                spacing: Theme.spacingXs

                Text {
                    text: root.buttonText
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeSm
                }
            }
        }
    }
}
