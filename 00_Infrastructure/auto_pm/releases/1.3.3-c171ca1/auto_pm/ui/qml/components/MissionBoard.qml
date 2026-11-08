// Read-only four-column board of one project's cards (TD-071 card 4): 在干 / 等你 / 搁着 / 已关.
// There are no buttons on purpose: putting a card down, picking one back up and switching are done on the
// command line (pm park / pm unpark / pm switch), and only on the user's word. Internal ids are not rendered.
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    property var board: ({})

    readonly property var columns: [
        { key: "active", label: "在干", hint: "同一时刻只有一张" },
        { key: "waiting", label: "等你", hint: "待批、待开工、待验收或卡住了" },
        { key: "parked", label: "搁着", hint: "断点已记，等你说拿回哪张" },
        { key: "closed", label: "已关", hint: "最近的几张" }
    ]

    function cardsOf(key) {
        return board && board[key] ? board[key] : []
    }

    implicitHeight: content.implicitHeight + Theme.spacingMd * 2
    color: Theme.surface
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        Text {
            objectName: "boardTitle"
            text: (board && board.project_name ? board.project_name : "项目")
                  + " · 开着 " + (board && board.open_count !== undefined ? board.open_count : 0)
                  + " / " + (board && board.open_limit ? board.open_limit : 8) + " 张"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSizeLg
            font.bold: true
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        Text {
            objectName: "boardOverLimit"
            visible: !!board && board.open_count >= board.open_limit
            text: "已到 " + (board ? board.open_limit : 8) + " 张上限：再开新卡要你一句话放行。"
            color: Theme.warning
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            Repeater {
                model: root.columns
                delegate: ColumnLayout {
                    id: column
                    objectName: "boardColumn_" + modelData.key
                    readonly property var cards: root.cardsOf(modelData.key)
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.alignment: Qt.AlignTop
                    spacing: Theme.spacingXs

                    Text {
                        objectName: "boardColumnHeader"
                        text: modelData.label + "（" + column.cards.length + "）"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSizeMd
                        font.bold: true
                    }
                    Text {
                        text: modelData.hint
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeXs
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: column.cards.length === 0
                        text: "—"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeSm
                    }
                    Repeater {
                        model: column.cards
                        delegate: Rectangle {
                            objectName: modelData.stale ? "boardCardStale" : "boardCard"
                            Layout.fillWidth: true
                            implicitHeight: cardText.implicitHeight + Theme.spacingSm * 2
                            radius: Theme.radiusSm
                            color: Theme.backgroundTertiary
                            border.width: 1
                            border.color: modelData.stale ? Theme.warning : Theme.borderSubtle

                            ColumnLayout {
                                id: cardText
                                anchors.fill: parent
                                anchors.margins: Theme.spacingSm
                                spacing: 2
                                Text {
                                    text: modelData.title
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontSizeSm
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: modelData.state_label
                                    color: Theme.textSecondary
                                    font.pixelSize: Theme.fontSizeXs
                                    Layout.fillWidth: true
                                }
                                Text {
                                    visible: !!modelData.note
                                    text: modelData.note || ""
                                    color: modelData.stale ? Theme.warning : Theme.textSecondary
                                    font.pixelSize: Theme.fontSizeXs
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }
                    Text {
                        visible: modelData.key === "closed" && !!root.board && root.board.closed_hidden > 0
                        text: root.board ? "另有 " + root.board.closed_hidden + " 张更早的已关卡" : ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeXs
                    }
                }
            }
        }
    }
}
