import QtQuick

Item {
    id: r
    property var app
    property int size: 56
    width: size
    height: size

    Rectangle {
        anchors.fill: parent
        radius: r.size * 0.24
        visible: img.status !== Image.Ready
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.primary }
            GradientStop { position: 1; color: Theme.primaryDark }
        }
        Text {
            anchors.centerIn: parent
            text: (r.app && r.app.name) ? r.app.name.charAt(0).toUpperCase() : "?"
            color: Theme.onPrimary
            font.pixelSize: r.size * 0.45
            font.bold: true
        }
    }
    Image {
        id: img
        anchors.fill: parent
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        sourceSize: Qt.size(r.size * 2, r.size * 2)
        source: !r.app ? "" : (r.app.iconFile ? "file://" + r.app.iconFile
                               : (r.app.iconName ? "image://icon/" + r.app.iconName : ""))
    }
}
