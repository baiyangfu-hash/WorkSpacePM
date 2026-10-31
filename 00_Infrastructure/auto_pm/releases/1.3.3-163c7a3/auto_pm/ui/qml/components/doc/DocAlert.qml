import QtQuick
import QtQuick.Layouts
import "../../theme"

Rectangle {
    id: root
    width: parent.width
    height: Math.max(56, contentLayout.implicitHeight + Theme.spacingMd)
    color: Qt.rgba(1.0, 1.0, 1.0, 0.01)
    radius: Theme.radiusSm
    border.color: Theme.border
    border.width: 1

    property string htmlData: ""
    property string alertType: "note"

    // 左边粗条
    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 5
        color: {
            if (root.alertType === "note") return Theme.primary;
            if (root.alertType === "tip") return Theme.success;
            if (root.alertType === "warning") return Theme.warning;
            if (root.alertType === "caution" || root.alertType === "important") return Theme.error;
            return Theme.primary;
        }
        radius: 2
    }

    RowLayout {
        id: contentLayout
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingMd + 5
        anchors.rightMargin: Theme.spacingMd
        anchors.topMargin: Theme.spacingSm
        anchors.bottomMargin: Theme.spacingSm
        spacing: Theme.spacingSm

        // 图标 Emoji
        Text {
            text: {
                if (root.alertType === "note") return "ℹ️";
                if (root.alertType === "tip") return "💡";
                if (root.alertType === "warning") return "⚠️";
                if (root.alertType === "caution" || root.alertType === "important") return "🚨";
                return "ℹ️";
            }
            font.pixelSize: 18
            Layout.alignment: Qt.AlignTop
        }

        // 内容富文本
        Text {
            text: root.htmlData
            textFormat: Text.RichText
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeMd
            Layout.fillWidth: true
            Layout.fillHeight: true

            onLinkActivated: (link) => {
                Qt.openUrlExternally(link)
            }
        }
    }
}
