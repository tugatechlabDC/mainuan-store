import QtQuick
import QtQuick.Layouts

RowLayout {
    id: h
    property string title: ""
    property bool showDefault: false
    property bool isDefault: false
    property bool showAdd: false
    signal makeDefault()
    signal addSource()
    spacing: 18
    Text {
        Layout.fillWidth: true
        text: h.title
        color: Theme.text
        font.pixelSize: 17
        font.weight: Font.DemiBold
    }
    Text {
        visible: h.showDefault
        text: h.isDefault ? "★ " + B.strings.default_source : "☆ " + B.strings.make_default
        color: h.isDefault ? Theme.primary : Theme.dim
        font.pixelSize: 13
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: h.makeDefault()
        }
    }
    Text {
        visible: h.showAdd
        text: "+ " + B.strings.add_source
        color: Theme.dim
        font.pixelSize: 13
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: h.addSource()
        }
    }
}
