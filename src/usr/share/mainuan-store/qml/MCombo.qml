import QtQuick
import QtQuick.Controls

// Campo de escolha com lista rolante (e barra de rolamento visível).
// Lista própria (sem DelegateModel/ItemDelegate): as opções ficam sempre visíveis, com ou sem rato por cima.
ComboBox {
    id: c
    property var textOf: function (m) { return String(m) }
    property int popupMax: 320
    readonly property int rowH: 38
    readonly property var cur: (currentIndex >= 0 && model && currentIndex < model.length) ? model[currentIndex] : null

    implicitHeight: 42
    hoverEnabled: true

    contentItem: Text {
        leftPadding: 14
        rightPadding: 36
        text: c.cur === null ? "" : c.textOf(c.cur)
        color: Theme.text
        font.pixelSize: 14
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: c.width - width - 14
        y: (c.height - height) / 2
        text: "▾"
        color: Theme.dim
        font.pixelSize: 16
    }
    background: Rectangle {
        radius: 10
        color: c.hovered ? Theme.raised : Theme.surface
        border.width: 1
        border.color: (c.activeFocus || c.popup.visible) ? Theme.primary : Theme.border
    }
    popup: Popup {
        y: c.height + 4
        width: c.width
        height: Math.min(c.popupMax, (c.model ? c.model.length : 0) * c.rowH + 12)
        padding: 6
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onOpened: lv.positionViewAtIndex(Math.max(0, c.currentIndex), ListView.Contain)
        contentItem: Item {
            ListView {
                id: lv
                anchors.fill: parent
                anchors.rightMargin: (contentHeight > height) ? 16 : 0
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: c.popup.visible ? c.model : null
                delegate: Rectangle {
                    id: d
                    width: ListView.view ? ListView.view.width : c.width
                    height: c.rowH
                    radius: 8
                    readonly property bool isCur: index === c.currentIndex
                    color: dm.containsMouse ? Theme.raised : (isCur ? Theme.surface : "transparent")
                    border.width: isCur ? 1 : 0
                    border.color: Theme.primary
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        text: c.textOf(modelData)
                        color: d.isCur ? Theme.primary : Theme.text
                        font.pixelSize: 14
                        font.weight: d.isCur ? Font.DemiBold : Font.Normal
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        id: dm
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            c.currentIndex = index
                            c.activated(index)
                            c.popup.close()
                        }
                    }
                }
            }
            MScrollBar { target: lv; visible: lv.contentHeight > lv.height }
        }
        background: Rectangle {
            radius: 12
            color: Theme.bg2
            border.width: 1
            border.color: Theme.border
        }
    }
}
