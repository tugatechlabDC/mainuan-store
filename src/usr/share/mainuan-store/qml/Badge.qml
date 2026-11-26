import QtQuick

Rectangle {
    id: b
    property string source: ""
    readonly property var names: ({ apt: "APT", flatpak: "Flatpak", appimage: "AppImage", deb: "DEB", snap: "Snap", firmware: "Firmware" })
    implicitWidth: lbl.implicitWidth + 16
    implicitHeight: 22
    radius: 11
    color: Theme.raised
    border.width: 1
    border.color: Theme.border
    Text {
        id: lbl
        anchors.centerIn: parent
        text: b.names[b.source] !== undefined ? b.names[b.source] : b.source
        color: Theme.primary
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
}
