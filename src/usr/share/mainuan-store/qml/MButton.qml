import QtQuick
import QtQuick.Controls

Button {
    id: c
    property bool primary: true
    property bool danger: false
    implicitHeight: 38
    leftPadding: 18
    rightPadding: 18
    contentItem: Text {
        text: c.text
        color: c.primary ? (c.danger ? "#ffffff" : Theme.onPrimary) : Theme.text
        font.pixelSize: 14
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        opacity: c.enabled ? 1 : 0.5
    }
    background: Rectangle {
        radius: 10
        opacity: c.enabled ? 1 : 0.5
        color: c.danger ? (c.down ? Qt.darker(Theme.err, 1.3) : (c.hovered ? Qt.lighter(Theme.err, 1.15) : Theme.err))
                         : c.primary ? (c.down ? Theme.primaryDark : (c.hovered ? Theme.primarySoft : Theme.primary))
                         : (c.hovered ? Theme.raised : "transparent")
        border.width: c.primary ? 0 : 1
        border.color: Theme.border
    }
}
