import QtQuick
import QtQuick.Controls

TextField {
    id: f
    implicitHeight: 40
    color: Theme.text
    placeholderTextColor: Theme.dim
    selectionColor: Theme.primaryDark
    font.pixelSize: 14
    leftPadding: 14
    rightPadding: 14
    selectByMouse: true
    background: Rectangle {
        radius: 10
        color: Theme.surface
        border.width: 1
        border.color: f.activeFocus ? Theme.primary : Theme.border
    }
}
