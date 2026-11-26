import QtQuick

// Área com rolamento vertical e barra de rolamento visível.
// Uso: MFlick { id: x; contentHeight: col.implicitHeight; ColumnLayout { id: col; width: x.width - 14 } }
Item {
    id: root
    default property alias content: flick.flickableData
    property alias contentHeight: flick.contentHeight
    property alias flickable: flick
    clip: true

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        clip: true
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds
    }
    MScrollBar { target: flick }
}
