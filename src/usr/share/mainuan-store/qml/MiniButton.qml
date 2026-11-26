import QtQuick
import QtQuick.Controls

Button {
    id: c
    property string glyph: ""
    property bool iconOnly: false
    property string tip: ""
    implicitHeight: 32
    leftPadding: 10
    rightPadding: iconOnly ? 10 : 13
    hoverEnabled: true
    ToolTip.visible: hovered && tip !== ""
    ToolTip.delay: 500
    ToolTip.text: tip
    contentItem: Row {
        spacing: 7
        Image {
            visible: c.glyph !== ""
            source: c.glyph !== "" ? "image://icon/nav/" + c.glyph + "/" + String(Theme.text).replace("#", "") : ""
            width: 18
            height: 18
            sourceSize: Qt.size(36, 36)
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            visible: !c.iconOnly
            text: c.text
            color: Theme.text
            font.pixelSize: 13
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        radius: 9
        color: c.down ? Theme.border : (c.hovered ? Theme.raised : Theme.surface)
        border.width: 1
        border.color: c.hovered ? Theme.primaryDark : Theme.border
    }
}
