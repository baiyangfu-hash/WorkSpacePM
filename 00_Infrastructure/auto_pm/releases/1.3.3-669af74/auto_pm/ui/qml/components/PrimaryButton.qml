// PrimaryButton.qml - 可复用工业级按钮组件
//
// 支持 primary/secondary/danger/accent/ghost 5 种主题样式。
// 支持按压弹性下沉反馈、悬浮高亮、以及 Loading 加载旋转动效与防抖。

import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    // ── 公开属性 ────────────────────────────────────────
    property string text: ""
    property string type: "primary"  // primary/secondary/danger/accent/ghost
    property bool loading: false
    property string icon: ""

    // ── 信号 ────────────────────────────────────────────
    signal clicked()

    // ── 颜色映射 ────────────────────────────────────────
    readonly property var _typeColorMap: ({
        "primary": Theme.primary,
        "secondary": Theme.textSecondary,
        "danger": Theme.error,
        "accent": Theme.accent || "#00d2d3",
        "ghost": "transparent"
    })
    readonly property color _baseColor: _typeColorMap[type] || Theme.primary
    readonly property bool _isGhost: type === "ghost"
    readonly property bool _isInteractive: enabled && !loading

    // ── 动态按压与悬停视觉计算 ──────────────────────────
    readonly property color _currentColor: {
        if (!enabled || loading) return _isGhost ? "transparent" : Qt.rgba(_baseColor.r, _baseColor.g, _baseColor.b, 0.5)
        if (mouseArea.pressed) return _isGhost ? Qt.rgba(1, 1, 1, 0.15) : Qt.darker(_baseColor, 1.25)
        if (mouseArea.containsMouse) return _isGhost ? Qt.rgba(1, 1, 1, 0.08) : Qt.lighter(_baseColor, 1.15)
        return _isGhost ? "transparent" : _baseColor
    }

    // ── 几何与外观 ──────────────────────────────────────
    implicitWidth: Math.max(80, contentRow.implicitWidth + 24)
    implicitHeight: 32
    color: _currentColor
    radius: Theme.radiusSm
    border.color: _isGhost ? (mouseArea.containsMouse ? Theme.primary : Theme.glassBorder) : "transparent"
    border.width: _isGhost ? 1 : 0
    opacity: enabled ? 1.0 : 0.5
    scale: mouseArea.pressed && _isInteractive ? 0.95 : (mouseArea.containsMouse && _isInteractive ? 1.02 : 1.0)

    Behavior on scale {
        NumberAnimation { duration: 90; easing.type: Easing.OutQuad }
    }
    Behavior on color {
        ColorAnimation { duration: 120 }
    }

    // ── 内容布局（图标 + 旋转加载器 + 文字）─────────────
    RowLayout {
        id: contentRow
        anchors.centerIn: parent
        spacing: 6

        // 旋转加载指示器（Loading Spinner）
        Item {
            id: spinnerItem
            visible: root.loading
            Layout.preferredWidth: 14
            Layout.preferredHeight: 14

            Rectangle {
                anchors.centerIn: parent
                width: 12
                height: 12
                radius: 6
                color: "transparent"
                border.color: _isGhost ? Theme.primary : "#ffffff"
                border.width: 2

                // 缺口扇区实现经典旋转环
                Rectangle {
                    width: 5
                    height: 5
                    color: root._currentColor
                    anchors.top: parent.top
                    anchors.right: parent.right
                }
            }

            RotationAnimator on rotation {
                from: 0
                to: 360
                duration: 800
                loops: Animation.Infinite
                running: root.loading
            }
        }

        // 图标
        Text {
            visible: !root.loading && root.icon !== ""
            text: root.icon
            font.pixelSize: Theme.fontSizeSm
        }

        // 按钮文本
        Text {
            id: buttonText
            text: root.loading ? "处理中..." : root.text
            color: _isGhost ? (_isInteractive && mouseArea.containsMouse ? Theme.primary : Theme.textPrimary) : "#ffffff"
            font.pixelSize: Theme.fontSizeSm
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    // ── 交互事件处理 ────────────────────────────────────
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        cursorShape: root.loading ? Qt.BusyCursor : (_isInteractive ? Qt.PointingHandCursor : Qt.ArrowCursor)
        hoverEnabled: true
        enabled: _isInteractive
        onClicked: {
            if (_isInteractive) {
                root.clicked()
            }
        }
    }
}
