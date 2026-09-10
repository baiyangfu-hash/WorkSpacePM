// Compact, read-only Work Graph for the evidence drawer.
import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root

    property var nodes: []
    implicitHeight: graph.implicitHeight

    ColumnLayout {
        id: graph
        width: parent.width
        spacing: Theme.spacingSm

        Repeater {
            model: root.nodes
            delegate: RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Rectangle {
                    width: 10
                    height: 10
                    radius: 5
                    color: modelData.state === "已阻塞" ? Theme.error : Theme.primary
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: modelData.title + " · " + modelData.state
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeSm
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text {
                        text: "负责人：" + modelData.owner
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSizeXs
                    }
                    Text {
                        visible: modelData.runs && modelData.runs.length > 0
                        text: modelData.runs ? modelData.runs.join("；") : ""
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSizeXs
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Text {
            visible: root.nodes.length === 0
            text: "尚无已登记的执行节点。"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSizeSm
        }
    }
}
