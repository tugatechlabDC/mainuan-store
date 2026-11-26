import QtQuick

Rectangle {
    id: b
    property int pct: -1
    implicitHeight: 8
    radius: 4
    color: Theme.border
    clip: true
    Rectangle {
        visible: b.pct >= 0
        width: parent.width * Math.min(100, b.pct) / 100
        height: parent.height
        radius: 4
        color: Theme.primary
    }
    Rectangle {
        id: ind
        visible: b.pct < 0
        width: parent.width * 0.3
        height: parent.height
        radius: 4
        color: Theme.primary
        SequentialAnimation on x {
            running: b.pct < 0 && b.visible
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: b.width * 0.7; duration: 900 }
            NumberAnimation { from: b.width * 0.7; to: 0; duration: 900 }
        }
    }
}
