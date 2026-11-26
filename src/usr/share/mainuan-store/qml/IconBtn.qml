import QtQuick
import QtQuick.Controls

// Botão quadrado só com ícone (ícones em assets/nav).
Rectangle {
    id: b
    property string glyph: ""
    property string tip: ""
    property bool danger: false
    property bool busy: false
    signal clicked()
    width: 38
    height: 38
    radius: 10
    color: ma.pressed ? Theme.border : (ma.containsMouse ? Theme.raised : Theme.surface)
    border.width: 1
    border.color: ma.containsMouse ? (danger ? Theme.err : Theme.primaryDark) : Theme.border
    opacity: enabled ? 1 : 0.5
    ToolTip.visible: ma.containsMouse && b.tip !== ""
    ToolTip.delay: 400
    ToolTip.text: b.tip
    Image {
        anchors.centerIn: parent
        width: 18
        height: 18
        sourceSize: Qt.size(36, 36)
        source: b.glyph !== "" ? "image://icon/nav/" + b.glyph + "/" + String(b.danger ? Theme.err : Theme.text).replace("#", "") : ""
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: b.clicked()
    }
}
