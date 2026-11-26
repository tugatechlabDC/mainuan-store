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
    implicitHeight: 76
    radius: 14
    color: m.containsMouse ? Theme.raised : Theme.surface
    border.width: 1
    border.color: Theme.border

    MouseArea {
        id: m
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: r.activated()
    }
    RowLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 14
        AppIcon { app: r.app; size: 48 }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    text: r.app ? r.app.name : ""
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    Layout.maximumWidth: 280
                }
                Repeater {
                    model: (r.app && r.app.variants) ? r.app.variants : []
                    delegate: Badge { source: modelData.source }
                }
                Item { Layout.fillWidth: true }
            }
            Text {
                Layout.fillWidth: true
                text: r.app ? (r.app.summary || "") : ""
                color: Theme.dim
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }
        Text {
            visible: r.inst
            text: r.str.installed_badge
            color: Theme.ok
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }
    }
}
