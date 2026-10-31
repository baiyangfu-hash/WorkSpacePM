import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../theme"

Rectangle {
    id: root
    width: parent.width
    height: Math.max(120, contentColumn.implicitHeight + Theme.spacingLg)
    color: "#070a13"
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1

    property string codeData: ""
    property string language: "text"

    function copyToClipboard(text) {
        try {
            var escapedText = text
                .replace(/\\/g, "\\\\")
                .replace(/\n/g, "\\n")
                .replace(/\r/g, "\\r")
                .replace(/'/g, "\\'");
            var textInput = Qt.createQmlObject("import QtQuick 2.15; TextInput { text: '" + escapedText + "'; visible: false }", root);
            textInput.selectAll();
            textInput.copy();
            textInput.destroy();
            return true;
        } catch (e) {
            console.log("Copy failed: ", e);
            return false;
        }
    }

    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        // 顶栏：语言标签与 Copy 按钮
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 24

            Text {
                text: root.language.toUpperCase()
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                color: Theme.textMuted
            }

            Item { Layout.fillWidth: true }

            // Copy 按钮
            Rectangle {
                id: copyButton
                width: 76
                height: 24
                color: copyMouseArea.containsMouse ? Theme.glassHighlight : Theme.glassBg
                border.color: Theme.glassBorder
                border.width: 1
                radius: Theme.radiusSm

                RowLayout {
                    anchors.centerIn: parent
                    spacing: 4
                    Text {
                        id: copyBtnText
                        text: "Copy"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }
                }

                Timer {
                    id: restoreTimer
                    interval: 1500
                    onTriggered: {
                        copyBtnText.text = "Copy"
                        copyBtnText.color = Theme.textSecondary
                    }
                }

                MouseArea {
                    id: copyMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (root.copyToClipboard(root.codeData)) {
                            copyBtnText.text = "✓ Copied"
                            copyBtnText.color = Theme.success
                            restoreTimer.restart()
                        }
                    }
                }
            }
        }

        // 代码正文
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AsNeeded
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            TextEdit {
                id: codeEdit
                text: root.codeData
                font.family: "Courier New"
                font.pixelSize: 13
                color: "#e2e8f0"
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.NoWrap
                width: Math.max(parent.width, implicitWidth)
            }
        }
    }
}
