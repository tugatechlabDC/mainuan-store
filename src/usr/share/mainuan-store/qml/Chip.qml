import QtQuick

Rectangle {
    id: c
    property string text: ""
    property string icon: ""
    property bool selected: false
    property int fontSize: 14
    signal clicked()
    implicitWidth: row.implicitWidth + (fontSize < 14 ? 22 : 28)
    implicitHeight: fontSize < 14 ? 30 : 36
    radius: height / 2
    color: selected ? Theme.primary : (m.containsMouse ? Theme.raised : Theme.surface)
    border.width: selected ? 0 : 1
    border.color: Theme.border
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7
        Image {
            visible: c.icon !== ""
            source: c.icon !== "" ? "image://icon/" + c.icon : ""
            width: c.fontSize < 14 ? 15 : 18
            height: width
            sourceSize: Qt.size(36, 36)
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: c.text
            color: c.selected ? Theme.onPrimary : Theme.text
            font.pixelSize: c.fontSize
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: m
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: c.clicked()
    }
}
