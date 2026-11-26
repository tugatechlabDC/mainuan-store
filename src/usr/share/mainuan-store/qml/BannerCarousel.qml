import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Banner do menu Início: slide 0 = «Bem-vindo» (wallpaper + logo Mainuan) e, a seguir,
// os banners de publicidade que o administrador coloca na pasta banners/ do projeto.
Rectangle {
    id: bc
    readonly property var str: B.strings
    readonly property var custom: B.banners
    readonly property int count: 1 + custom.length
    property int cur: 0
    color: Theme.sidebar
    clip: true

    onCountChanged: if (cur >= count) cur = 0
    Timer {
        interval: 7000
        repeat: true
        running: bc.count > 1 && !hov.hovered && bc.visible
        onTriggered: bc.cur = (bc.cur + 1) % bc.count
    }
    HoverHandler { id: hov }

    // ---------- slide 0: Bem-vindo ----------
    Item {
        anchors.fill: parent
        opacity: bc.cur === 0 ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 450 } }
        Image {
            anchors.fill: parent
            source: "file://" + Theme.assets + "/hero.jpg"
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#99011a27" }
                GradientStop { position: 0.55; color: "#33011a27" }
                GradientStop { position: 1.0; color: "#00011a27" }
            }
        }
        // logo Mainuan à direita, com brilho por trás
        Item {
            id: logoBox
            visible: bc.width > 620
            anchors.right: parent.right
            anchors.rightMargin: Math.max(24, Math.min(110, bc.width * 0.08))
            anchors.verticalCenter: parent.verticalCenter
            width: 170
            height: 188
            Image {
                anchors.centerIn: parent
                width: 380
                height: 380
                source: "file://" + Theme.assets + "/logo-glow.png"
                smooth: true
            }
            Image {
                anchors.fill: parent
                source: "file://" + Theme.assets + "/mainuan-logo.png"
                fillMode: Image.PreserveAspectFit
                sourceSize: Qt.size(340, 376)
                smooth: true
                mipmap: true
            }
        }
        ColumnLayout {
            anchors.left: parent.left
            anchors.leftMargin: 40
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(220, Math.min(600, bc.width - (logoBox.visible ? logoBox.width + 170 : 80)))
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: bc.str.hero_welcome
                color: "#ffffff"
                font.pixelSize: 34
                font.weight: Font.Bold
                wrapMode: Text.WordWrap
                style: Text.Raised
                styleColor: "#66000000"
            }
            Text {
                Layout.fillWidth: true
                text: bc.str.hero_slogan
                color: Theme.dark ? Theme.primary : "#7ff6fb"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
        }
    }

    // ---------- banners de publicidade (pasta banners/) ----------
    Repeater {
        model: bc.custom
        delegate: Item {
            required property int index
            required property var modelData
            anchors.fill: parent
            opacity: bc.cur === index + 1 ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: 450 } }
            Image {
                anchors.fill: parent
                source: modelData.src
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                smooth: true
            }
            MouseArea {
                anchors.fill: parent
                enabled: modelData.url !== ""
                cursorShape: modelData.url !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
                hoverEnabled: true
                onClicked: B.openBanner(modelData.url)
                ToolTip.visible: containsMouse && modelData.title !== ""
                ToolTip.text: modelData.title
                ToolTip.delay: 500
            }
        }
    }

    // ---------- indicadores ----------
    Row {
        visible: bc.count > 1
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8
        Repeater {
            model: bc.count
            delegate: Rectangle {
                required property int index
                width: bc.cur === index ? 24 : 9
                height: 9
                radius: 4.5
                color: bc.cur === index ? Theme.primary : "#99ffffff"
                border.width: 1
                border.color: "#55000000"
                Behavior on width { NumberAnimation { duration: 200 } }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -5
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bc.cur = index
                }
            }
        }
    }
}
