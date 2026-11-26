import QtQuick
import QtQuick.Layouts

Rectangle {
    id: r
    property var app
    signal activated()
    readonly property var str: B.strings
    readonly property bool inst: {
        B.rev
        if (!app || !app.variants) return false
        for (var i = 0; i < app.variants.length; i++)
            if (B.isInstalled(app.variants[i].source, app.variants[i].pkg)) return true
        return false
    }
    readonly property bool unavailable: app && app.variants && app.variants.length > 0 && app.variants[0].available === false
    radius: 16
    color: m.containsMouse ? Theme.raised : Theme.surface
    border.width: 1
    border.color: m.containsMouse ? Theme.primaryDark : Theme.border

    MouseArea {
        id: m
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: r.activated()
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 8
        RowLayout {
            spacing: 12
            AppIcon { app: r.app; size: 44 }
            Text {
                Layout.fillWidth: true
                text: r.app ? r.app.name : ""
                color: Theme.text
                font.pixelSize: 15
                font.weight: Font.Bold
                elide: Text.ElideRight
            }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 5
            Repeater {
                model: (r.app && r.app.variants) ? r.app.variants : []
                delegate: Badge { source: modelData.source }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: r.app ? (r.app.summary || "") : ""
            color: Theme.dim
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
        Text {
            text: r.inst ? r.str.installed_badge : (r.unavailable ? r.str.unavailable : r.str.install)
            color: r.inst ? Theme.ok : (r.unavailable ? Theme.dim : Theme.primary)
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
    }
}
