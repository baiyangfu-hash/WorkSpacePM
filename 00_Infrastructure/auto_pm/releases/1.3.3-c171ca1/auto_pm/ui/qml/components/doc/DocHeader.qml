import QtQuick
import QtQuick.Layouts
import "../../theme"

Item {
    id: root
    width: parent.width
    height: contentLayout.implicitHeight + Theme.spacingMd

    property string textData: ""
    property string type: "h1"

    ColumnLayout {
        id: contentLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.spacingXs

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            // 左边饰条 (只对 h1, h2 渲染)
            Rectangle {
                Layout.preferredWidth: 4
                Layout.preferredHeight: headerText.implicitHeight
                color: root.type === "h1" ? Theme.primary : Theme.secondary
                visible: root.type === "h1" || root.type === "h2"
                radius: 2
            }

            Text {
                id: headerText
                text: root.textData
                font.pixelSize: {
                    if (root.type === "h1") return Theme.fontSizeXxl;
                    if (root.type === "h2") return Theme.fontSizeXl;
                    if (root.type === "h3") return Theme.fontSizeLg;
                    return Theme.fontSizeMd;
                }
                font.bold: true
                color: Theme.textPrimary
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        // 下划细线分隔线 (对 h1, h2)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
            visible: root.type === "h1" || root.type === "h2"
            opacity: 0.5
        }
    }
}
