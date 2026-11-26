import QtQuick

// Barra de rolamento própria (sempre visível). Usa-se como irmã do Flickable/ListView:
//   ListView { id: lv ... }
//   MScrollBar { target: lv }
Item {
    id: sb
    property Flickable target: null

    anchors.top: parent.top
    anchors.bottom: parent.bottom
    anchors.right: parent.right
    width: 14
    z: 5

    readonly property real range: target ? (target.contentHeight + target.topMargin + target.bottomMargin - target.height) : 0
    readonly property bool scrollable: range > 1
    readonly property real trackH: Math.max(1, height - 4)
    readonly property real thumbH: scrollable
                                   ? Math.max(36, Math.min(trackH, trackH * target.height / (target.height + range)))
                                   : trackH
    readonly property real frac: scrollable
                                 ? Math.max(0, Math.min(1, (target.contentY - target.originY + target.topMargin) / range))
                                 : 0

    function scrollToMouse(my) {
        if (!scrollable) return
        var f = (my - 2 - thumbH / 2) / Math.max(1, trackH - thumbH)
        f = Math.max(0, Math.min(1, f))
        target.contentY = target.originY - target.topMargin + f * range
    }

    Rectangle {
        x: 2
        y: 2
        width: parent.width - 4
        height: sb.trackH
        radius: width / 2
        color: Theme.surface
        border.width: 1
        border.color: Theme.border
    }
    Rectangle {
        id: thumb
        x: 3
        y: 2 + sb.frac * (sb.trackH - sb.thumbH)
        width: parent.width - 6
        height: sb.thumbH
        radius: width / 2
        opacity: sb.scrollable ? 1 : 0.35
        color: ma.pressed ? Theme.primary : (ma.containsMouse ? Theme.primarySoft : Theme.primaryDark)
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onPressed: function (mouse) { sb.scrollToMouse(mouse.y) }
        onPositionChanged: function (mouse) { if (pressed) sb.scrollToMouse(mouse.y) }
    }
}
