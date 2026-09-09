import QtQuick
import QtQuick.Controls
import "../../theme"

Rectangle {
    id: root
    width: parent.width
    height: tableText.implicitHeight + Theme.spacingMd * 2
    color: Qt.rgba(1.0, 1.0, 1.0, 0.01)
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1

    property string htmlData: ""

    // 引入 CSS 样式，使表格背景、线条和间距与系统毛玻璃风格融合
    property string styledHtml: {
        return "<html><head><style>" +
            "table { border-collapse: collapse; width: 100%; color: #cbd5e1; font-family: sans-serif; font-size: 13px; }" +
            "th, td { border: 1px solid rgba(255,255,255,0.08); padding: 8px 12px; text-align: left; }" +
            "th { background-color: rgba(255,255,255,0.04); color: #f1f5f9; font-weight: bold; }" +
            "tr:nth-child(even) { background-color: rgba(255,255,255,0.01); }" +
            "</style></head><body>" + htmlData + "</body></html>"
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Text {
            id: tableText
            width: Math.max(parent.width, implicitWidth)
            text: root.styledHtml
            textFormat: Text.RichText
            wrapMode: Text.NoWrap
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeMd

            onLinkActivated: (link) => {
                Qt.openUrlExternally(link)
            }
        }
    }
}
