import QtQuick

Item {
    id: c
    property bool checked: false
    property string label: ""
    property string note: ""
    signal toggled()
    implicitHeight: 32
    implicitWidth: row.implicitWidth
    Row {
        id: row
        spacing: 10
        anchors.verticalCenter: parent.verticalCenter
        Rectangle {
            width: 20
            height: 20
            radius: 5
            color: c.checked ? Theme.primary : "transparent"
            border.width: 1.5
            border.color: c.checked ? Theme.primary : Theme.dim
            Text {
                anchors.centerIn: parent
                visible: c.checked
                text: "✓"
                color: Theme.onPrimary
                font.pixelSize: 14
                font.bold: true
            }
        }
        Text {
            visible: c.label !== ""
            text: c.label
            width: Math.min(implicitWidth, 560)
            elide: Text.ElideRight
            color: Theme.text
            font.pixelSize: 14
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            visible: c.note !== ""
            text: c.note
            color: Theme.dim
            font.italic: true
            font.pixelSize: 13
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: c.toggled()
    }
}
