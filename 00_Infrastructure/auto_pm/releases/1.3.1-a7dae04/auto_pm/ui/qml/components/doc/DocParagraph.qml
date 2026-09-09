import QtQuick
import "../../theme"

Item {
    id: root
    width: parent.width
    height: bodyText.implicitHeight + Theme.spacingSm

    property string htmlData: ""

    Text {
        id: bodyText
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: root.htmlData
        textFormat: Text.RichText
        wrapMode: Text.WordWrap
        color: Theme.textPrimary
        font.pixelSize: Theme.fontSizeMd
        lineHeight: 1.4

        onLinkActivated: (link) => {
            Qt.openUrlExternally(link)
        }
    }
}
