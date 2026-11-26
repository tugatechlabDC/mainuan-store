import QtQuick
import QtQuick.Layouts

Rectangle {
    id: r
    property var app
    property bool checked: false
    property var opState
    signal toggled()
    readonly property var str: B.strings
    readonly property bool busy: opState !== undefined
    implicitHeight: busy ? 98 : 70
    radius: 14
    color: m.containsMouse ? Theme.raised : Theme.surface
    border.width: 1
    border.color: busy ? Theme.primaryDark : (checked ? Theme.primaryDark : Theme.border)

    MouseArea {
        id: m
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: r.toggled()
    }
    RowLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 14
        Check { checked: r.checked; onToggled: r.toggled() }
        AppIcon { app: r.app; size: 42 }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            RowLayout {
                spacing: 8
                Text {
                    text: r.app ? r.app.name : ""
                    color: Theme.text
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    Layout.maximumWidth: 320
                }
                Badge { source: r.app ? r.app.origin : "" }
            }
            Text {
                text: r.app ? ((r.app.fromVer ? r.app.fromVer + " → " : "") + (r.app.toVer || "")) : ""
                color: Theme.dim
                font.pixelSize: 12
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            ColumnLayout {
                visible: r.busy
                Layout.fillWidth: true
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: r.busy ? r.str["st_" + r.opState.phase] : ""
                        color: (r.busy && r.opState.phase === "done") ? Theme.ok : Theme.text
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                    Text {
                        visible: r.busy && r.opState.phase !== "waiting"
                        text: r.busy ? r.opState.pct + "%" : ""
                        color: Theme.primary
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                }
                ProgressBarX {
                    Layout.fillWidth: true
                    implicitHeight: 6
                    pct: r.busy ? (r.opState.phase === "waiting" ? 0 : r.opState.pct) : 0
                }
            }
        }
    }
}
