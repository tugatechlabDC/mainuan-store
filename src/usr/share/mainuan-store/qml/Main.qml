import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: win
    width: 1240
    height: 800
    minimumWidth: 560
    minimumHeight: 520
    visible: true
    title: "Mainuan Store"
    color: Theme.bg

    readonly property var str: B.strings
    readonly property bool compact: !B.sideExpanded || width < 640
    readonly property int sideW: compact ? 72 : 196
    readonly property var catKeys: ["all", "accessibility", "dev", "education", "office", "graphics", "internet",
                                    "games", "media", "system", "utils", "addons", "plasma", "fonts"]
    readonly property var catSorted: {
        var loc = B.lang.replace("_", "-")
        var rest = catKeys.slice(1).sort(function (a, b) { return String(str["cat_" + a]).localeCompare(String(str["cat_" + b]), loc) })
        return ["all"].concat(rest)
    }
    readonly property var catIcons: ({
        all: "view-list-icons", accessibility: "preferences-desktop-accessibility",
        dev: "applications-development", education: "applications-education", office: "applications-office",
        graphics: "applications-graphics", internet: "applications-internet", games: "applications-games",
        media: "applications-multimedia", system: "applications-system", utils: "applications-utilities",
        addons: "preferences-plugin", plasma: "plasma", fonts: "preferences-desktop-font" })

    property int page: 0   // 0 início, 1 explorar, 2 pesquisa, 3 instaladas, 4 atualizações, 5 definições, 6 sobre, 7 AppImage
    property var featuredList: []
    property var catalogList: []
    property var searchList: []
    property var installedList: []
    property var updatesList: []
    property var sourcesData: ({})
    property var ops: ({})
    property var selected: ({})
    property var itemOps: ({})
    property var categoryList: []
    property bool indexBuilding: false
    property int shown: 60
    property bool searching: false
    property bool loadingInstalled: false
    property string category: "all"
    property string instFilter: "all"
    property string toastText: ""

    readonly property var opKeys: Object.keys(ops)
    readonly property var homeSections: buildHome(catalogList)
    readonly property var exploreAll: featuredList.filter(function (a) {
        return category === "all" || a.category === category
    }).concat(categoryList)
    readonly property var exploreList: exploreAll.slice(0, shown)
    readonly property var instShown: installedList.filter(function (a) {
        return instFilter === "all" || a.origin === instFilter
    })
    readonly property int selCount: {
        var n = 0
        for (var k in selected) if (selected[k]) n++
        return n
    }

    function buildHome(list) {
        var out = []
        for (var i = 1; i < catKeys.length; i++) {
            var k = catKeys[i]
            var items = list.filter(function (a) { return a.category === k })
            if (items.length > 0) out.push({ key: k, count: items.length, items: items.slice(0, 3) })
        }
        return out
    }
    function countOrigin(f) {
        if (f === "all") return installedList.length
        var n = 0
        for (var i = 0; i < installedList.length; i++) if (installedList[i].origin === f) n++
        return n
    }
    function setOp(key, name, pct) {
        var o = Object.assign({}, ops)
        o[key] = { name: name, pct: pct }
        ops = o
    }
    function clearOp(key) {
        var o = Object.assign({}, ops)
        delete o[key]
        ops = o
    }
    function opLabel(key) {
        if (key === "index") return str.check_updates
        if (key === "all") return str.update_all
        if (key === "sel") return str.update_selected
        if (key === "src") return str.settings
        return ops[key] ? ops[key].name : key
    }
    function toggleSel(id) {
        var s = Object.assign({}, selected)
        s[id] = !s[id]
        selected = s
    }
    function selectAll(v) {
        var s = {}
        if (v) for (var i = 0; i < updatesList.length; i++) s[updatesList[i].id] = true
        selected = s
    }
    function toast(t) {
        toastText = t
        toastTimer.restart()
    }
    function goSearch() {
        if (searchField.text.trim().length >= 2) {
            page = 2
            searching = true
            B.search(searchField.text)
        }
    }
    function openApp(a) {
        pop.app = a
        pop.longText = a.description || ""
        pop.vinfo = ({})
        pop.shots = []
        pop.shotIdx = 0
        pop.shotsLoading = true
        var s = 0
        for (var i = 0; i < a.variants.length; i++)
            if (a.variants[i].source === B.defaultSource) { s = i; break }
        pop.sel = s
        verBox.currentIndex = s
        B.details(a)
        pop.open()
        Qt.callLater(function () { verBox.currentIndex = pop.sel })
    }
    function hex(c) {
        return String(c).replace("#", "")
    }
    function fitToScreen() {
        var m = 16
        var aw = Screen.desktopAvailableWidth, ah = Screen.desktopAvailableHeight
        if (aw > 0 && ah > 0) {
            width = Math.max(minimumWidth, aw - 2 * m)
            height = Math.max(minimumHeight, ah - 2 * m)
            x = Screen.virtualX + Math.round((aw - width) / 2)
            y = Screen.virtualY + Math.round((ah - height) / 2)
        }
    }
    function setItem(id, phase, pct) {
        var o = Object.assign({}, itemOps)
        o[id] = { phase: phase, pct: pct }
        itemOps = o
        if (phase === "done") doneTimer.restart()
    }
    function dropDone() {
        var keep = updatesList.filter(function (a) { return !(itemOps[a.id] && itemOps[a.id].phase === "done") })
        var o = {}
        for (var k in itemOps) if (itemOps[k].phase !== "done") o[k] = itemOps[k]
        updatesList = keep
        itemOps = o
    }
    function openFile(kind) {
        if (picker.item) {
            picker.item.kind = kind
            picker.item.open()
        } else toast(str.op_fail)
    }

    onCategoryChanged: { shown = 60; B.loadCategory(category) }
    onPageChanged: {
        if (page === 1) B.loadCategory(category)
        if (page === 3) { loadingInstalled = true; B.loadInstalled() }
        if (page === 4) B.loadUpdates()
        if (page === 5) B.loadSources()
        if (page === 7) aiPage.refresh()
        if (page === 0) B.reloadBanners()
    }
    Component.onCompleted: {
        fitToScreen()
        B.loadHome()
        B.loadUpdates()
        B.migrateAppimages()
        if (B.startPage >= 0) win.page = B.startPage
        if (B.startFile !== "") B.inspectFile(B.startFile)
    }
    // deteção automática de atualizações enquanto a loja está aberta (de 30 em 30 minutos)
    Timer { interval: 1800000; running: true; repeat: true; onTriggered: B.loadUpdates() }
    function bringToFront() {
        win.show()
        win.raise()
        win.requestActivate()
    }
    // o idioma da app acompanha o idioma do sistema
    Timer { interval: 5000; running: true; repeat: true; onTriggered: B.syncLang() }

    Loader { id: picker; source: "FilePicker.qml" }
    Connections {
        target: picker.item
        function onPicked(url) { B.inspectFile(url) }
    }

    Connections {
        target: B
        function onListReady(kind, items) {
            if (kind === "featured") win.featuredList = items
            else if (kind === "catalog") win.catalogList = items
            else if (kind === "category") win.categoryList = items
            else if (kind === "search") { win.searchList = items; win.searching = false }
            else if (kind === "installed") { win.installedList = items; win.loadingInstalled = false }
            else if (kind === "updates") { win.updatesList = items; win.selected = ({}) }
        }
        function onSourcesReady(data) { win.sourcesData = data }
        function onIndexBuilding(building) { win.indexBuilding = building }
        function onItemState(id, phase, percent) { win.setItem(id, phase, percent) }
        function onOpStarted(key, name) { win.setOp(key, name, -1) }
        function onOpProgress(key, percent) { if (win.ops[key]) win.setOp(key, win.ops[key].name, percent) }
        function onOpFinished(key, ok, message) {
            if (key.indexOf("file:") === 0 && filePop.info.path && key === "file:" + filePop.info.path) {
                if (message === "cancelled") {
                    filePop.result = ""
                    filePop.close()
                } else {
                    filePop.resultMsg = message
                    filePop.result = ok ? "ok" : "fail"
                    if (!filePop.opened) filePop.open()
                }
            }
            win.clearOp(key)
            win.dropDone()
            win.itemOps = ({})
            if (key.indexOf("file:") === 0) { /* o popup mostra o resultado */ }
            else if (message === "cancelled") win.toast(win.str.op_cancelled)
            else win.toast(ok ? win.str.op_ok : (win.str.op_fail + (message ? ": " + message : "")))
            B.loadUpdates()
            if (win.page === 3) B.loadInstalled()
            if (key === "src" || key === "index") { B.loadSources(); B.loadHome() }
        }
        function onDetailsReady(info) {
            if (pop.app && info.id === pop.app.id) {
                if (info.text) pop.longText = info.text
                pop.vinfo = info.variants
            }
        }
        function onShotsReady(id, urls) {
            if (pop.app && id === pop.app.id) {
                pop.shots = urls
                pop.shotsLoading = false
            }
        }
        function onRemoteCommand(cmd, arg) {
            // pedido de outra instância (ícone de atualizações, duplo clique num ficheiro...)
            win.bringToFront()
            if (cmd === "page") win.page = parseInt(arg)
            else if (cmd === "file" && arg !== "") B.inspectFile(arg)
        }
        function onFileInfo(info) {
            win.bringToFront()
            if (info.ok === true && info.installed === true) {
                // app já instalada: pergunta se quer eliminar
                filePop.result = ""
                filePop.resultMsg = ""
                filePop.info = info
                filePop.open()
                return
            }
            if (info.ok === true && info.kind === "appimage") {
                // AppImage: abre o menu AppImage e adiciona lá a app
                win.page = 7
                B.addAppimage(info.path, true)
                return
            }
            filePop.result = ""
            filePop.resultMsg = ""
            filePop.info = info
            filePop.open()
        }
        function onPrefsChanged() { B.loadSources(); B.loadHome() }
        function onLangChanged() { B.loadHome() }
    }

    Timer {
        id: searchTimer
        interval: 450
        onTriggered: {
            if (searchField.text.trim().length >= 2) win.goSearch()
            else if (win.page === 2) win.page = 0
        }
    }
    Timer { id: doneTimer; interval: 1600; onTriggered: win.dropDone() }
    Timer { id: toastTimer; interval: 4500; onTriggered: win.toastText = "" }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---------- barra lateral ----------
        Rectangle {
            Layout.preferredWidth: win.sideW
            Layout.fillHeight: true
            color: Theme.sidebar
            clip: true

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: win.compact ? 10 : 14
                spacing: 6

                Rectangle {
                    id: sideToggle
                    Layout.alignment: win.compact ? Qt.AlignHCenter : Qt.AlignLeft
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 34
                    Layout.bottomMargin: 8
                    radius: 10
                    color: stm.containsMouse ? Theme.raised : "transparent"
                    ToolTip.visible: stm.containsMouse
                    ToolTip.delay: 300
                    ToolTip.text: win.compact ? win.str.menu_expand : win.str.menu_collapse
                    Column {
                        anchors.centerIn: parent
                        spacing: 4
                        Repeater {
                            model: 3
                            Rectangle { width: 18; height: 2; radius: 1; color: Theme.text }
                        }
                    }
                    MouseArea {
                        id: stm
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: B.setSideExpanded(win.compact ? true : false)
                    }
                }

                RowLayout {
                    Layout.bottomMargin: 18
                    Layout.alignment: win.compact ? Qt.AlignHCenter : Qt.AlignLeft
                    spacing: 10
                    Image {
                        source: "file://" + Theme.assets + "/logo.png"
                        sourceSize: Qt.size(88, 88)
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                    }
                    Text {
                        visible: !win.compact
                        text: "Mainuan\nStore"
                        color: Theme.text
                        font.pixelSize: 16
                        font.weight: Font.Bold
                        lineHeight: 0.95
                    }
                }

                Repeater {
                    model: [
                        { k: "home", i: 0, ic: "home" }, { k: "explore", i: 1, ic: "explore" },
                        { k: "installed", i: 3, ic: "installed" }, { k: "updates", i: 4, ic: "updates" },
                        { k: "appimage", i: 7, ic: "appimage" },
                        { k: "settings", i: 5, ic: "settings" }, { k: "about", i: 6, ic: "about" }
                    ]
                    delegate: Rectangle {
                        id: nav
                        readonly property bool sel: win.page === modelData.i || (modelData.i === 1 && win.page === 2)
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        radius: 10
                        color: sel ? Theme.raised : (nm.containsMouse ? Theme.surface : "transparent")
                        ToolTip.visible: nm.containsMouse && win.compact
                        ToolTip.delay: 300
                        ToolTip.text: win.str[modelData.k]
                        Rectangle {
                            visible: nav.sel
                            width: 4; height: 20; radius: 2
                            color: Theme.primary
                            anchors.left: parent.left
                            anchors.leftMargin: 3
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Image {
                            x: win.compact ? (parent.width - width) / 2 : 16
                            anchors.verticalCenter: parent.verticalCenter
                            width: 22
                            height: 22
                            sourceSize: Qt.size(44, 44)
                            source: "image://icon/nav/" + modelData.ic + "/" + win.hex(nav.sel ? Theme.primary : Theme.text)
                        }
                        Text {
                            visible: !win.compact
                            x: 50
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 50 - (updBadge.visible ? 42 : 10)
                            elide: Text.ElideRight
                            text: win.str[modelData.k]
                            color: nav.sel ? Theme.primary : Theme.text
                            font.pixelSize: 14
                            font.weight: nav.sel ? Font.DemiBold : Font.Normal
                        }
                        Rectangle {
                            id: updBadge
                            visible: modelData.k === "updates" && win.updatesList.length > 0
                            width: win.compact ? 18 : 24
                            height: win.compact ? 16 : 20
                            radius: height / 2
                            color: Theme.primary
                            x: parent.width - width - (win.compact ? 4 : 12)
                            y: win.compact ? 3 : (parent.height - height) / 2
                            Text {
                                anchors.centerIn: parent
                                text: win.updatesList.length
                                color: Theme.onPrimary
                                font.pixelSize: win.compact ? 10 : 11
                                font.bold: true
                            }
                        }
                        MouseArea {
                            id: nm
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.page = modelData.i
                        }
                    }
                }
                Item { Layout.fillHeight: true }

                // instalações em curso (versão compacta)
                Rectangle {
                    visible: win.opKeys.length > 0 && win.compact
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    radius: 12
                    color: Theme.surface
                    border.width: 1
                    border.color: Theme.border
                    ToolTip.visible: tm.containsMouse
                    ToolTip.text: win.str.tasks_title + " (" + win.opKeys.length + ")"
                    Image {
                        anchors.centerIn: parent
                        source: "image://icon/folder-download"
                        sourceSize: Qt.size(40, 40)
                        width: 20
                        height: 20
                    }
                    Rectangle {
                        x: parent.width - width - 2
                        y: 2
                        width: 16; height: 16; radius: 8
                        color: Theme.primary
                        Text {
                            anchors.centerIn: parent
                            text: win.opKeys.length
                            color: Theme.onPrimary
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }
                    MouseArea { id: tm; anchors.fill: parent; hoverEnabled: true }
                }

                // instalações em curso
                Rectangle {
                    visible: win.opKeys.length > 0 && !win.compact
                    Layout.fillWidth: true
                    Layout.preferredHeight: tcol.implicitHeight + 24
                    radius: 12
                    color: Theme.surface
                    border.width: 1
                    border.color: Theme.border
                    ColumnLayout {
                        id: tcol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 12
                        spacing: 8
                        RowLayout {
                            spacing: 8
                            Image {
                                source: "image://icon/folder-download"
                                sourceSize: Qt.size(32, 32)
                                Layout.preferredWidth: 16
                                Layout.preferredHeight: 16
                            }
                            Text {
                                text: win.str.tasks_title + " (" + win.opKeys.length + ")"
                                color: Theme.text
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                        }
                        Repeater {
                            model: win.opKeys
                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        Layout.fillWidth: true
                                        text: win.opLabel(modelData)
                                        color: Theme.text
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        text: (win.ops[modelData] && win.ops[modelData].pct >= 0) ? win.ops[modelData].pct + "%" : "…"
                                        color: Theme.dim
                                        font.pixelSize: 12
                                    }
                                    Text {
                                        text: "✕"
                                        color: Theme.err
                                        font.pixelSize: 14
                                        font.bold: true
                                        leftPadding: 6
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: B.cancel(modelData)
                                        }
                                    }
                                }
                                ProgressBarX {
                                    Layout.fillWidth: true
                                    implicitHeight: 5
                                    pct: win.ops[modelData] ? win.ops[modelData].pct : -1
                                }
                            }
                        }
                    }
                }
            }
        }

        // ---------- conteúdo ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 68
                visible: win.page <= 3
                color: Theme.bg
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 32
                    anchors.rightMargin: 32
                    spacing: 12
                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        Layout.maximumWidth: 640
                        Layout.preferredHeight: 42
                        placeholderText: win.str.search_ph
                        placeholderTextColor: Theme.dim
                        color: Theme.text
                        selectionColor: Theme.primaryDark
                        font.pixelSize: 15
                        leftPadding: 16
                        background: Rectangle {
                            radius: 21
                            color: Theme.surface
                            border.width: 1
                            border.color: searchField.activeFocus ? Theme.primary : Theme.border
                        }
                        onTextChanged: searchTimer.restart()
                        onAccepted: win.goSearch()
                    }
                    MiniButton {
                        visible: win.page <= 2
                        glyph: "appimage"
                        text: "AppImage"
                        iconOnly: win.width < 720
                        tip: win.str.open_appimage
                        onClicked: win.openFile("appimage")
                    }
                    MiniButton {
                        visible: win.page <= 2
                        glyph: "deb"
                        text: "DEB"
                        iconOnly: win.width < 720
                        tip: win.str.open_deb
                        onClicked: win.openFile("deb")
                    }
                    Item { Layout.fillWidth: true }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: win.page

                // 0 — Início: hero + categorias com banner + ranking
                MFlick {
                    id: homeScroll
                    contentHeight: homeCol.implicitHeight
                    ColumnLayout {
                        id: homeCol
                        width: homeScroll.width
                        spacing: 0
                        BannerCarousel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 220
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 24
                            Layout.topMargin: 22
                            Layout.bottomMargin: 32
                            spacing: 20
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignTop
                                spacing: 24
                                Repeater {
                                    model: win.homeSections
                                    delegate: ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 12
                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 56
                                            radius: 12
                                            color: bm.containsMouse ? Theme.primaryDark : Theme.banner
                                            MouseArea {
                                                id: bm
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: { win.category = modelData.key; win.page = 1 }
                                            }
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 16
                                                anchors.rightMargin: 16
                                                spacing: 12
                                                Image {
                                                    source: "image://icon/" + win.catIcons[modelData.key]
                                                    sourceSize: Qt.size(56, 56)
                                                    Layout.preferredWidth: 28
                                                    Layout.preferredHeight: 28
                                                }
                                                Text {
                                                    text: win.str["cat_" + modelData.key]
                                                    color: Theme.text
                                                    font.pixelSize: 17
                                                    font.weight: Font.Bold
                                                }
                                                Text {
                                                    text: modelData.count
                                                    color: Theme.dim
                                                    font.pixelSize: 13
                                                }
                                                Item { Layout.fillWidth: true }
                                                Text {
                                                    text: win.str.see_all + "  ›"
                                                    color: Theme.primary
                                                    font.pixelSize: 14
                                                    font.weight: Font.DemiBold
                                                }
                                            }
                                        }
                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: Math.max(1, Math.min(3, Math.floor(width / 200)))
                                            columnSpacing: 14
                                            rowSpacing: 14
                                            Repeater {
                                                model: modelData.items
                                                delegate: AppCard {
                                                    Layout.fillWidth: true
                                                    Layout.preferredHeight: 156
                                                    app: modelData
                                                    onActivated: win.openApp(modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Rectangle {
                                visible: homeScroll.width > 820
                                Layout.preferredWidth: 250
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredHeight: rankCol.implicitHeight + 32
                                radius: 16
                                color: Theme.surface
                                border.width: 1
                                border.color: Theme.primaryDark
                                ColumnLayout {
                                    id: rankCol
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 16
                                    spacing: 6
                                    Text {
                                        text: "★ " + win.str.rank_title
                                        color: Theme.primary
                                        font.pixelSize: 15
                                        font.weight: Font.Bold
                                        font.letterSpacing: 0.5
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                        Layout.bottomMargin: 6
                                    }
                                    Repeater {
                                        model: win.featuredList
                                        delegate: Rectangle {
                                            id: rk
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 54
                                            radius: 10
                                            color: rm.containsMouse ? Theme.raised : "transparent"
                                            readonly property bool inst: { B.rev; return B.isInstalled(modelData.variants[0].source, modelData.variants[0].pkg) }
                                            MouseArea {
                                                id: rm
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: win.openApp(modelData)
                                            }
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 6
                                                anchors.rightMargin: 6
                                                spacing: 10
                                                Text {
                                                    text: index + 1
                                                    color: Theme.dim
                                                    font.pixelSize: 14
                                                    font.bold: true
                                                    Layout.preferredWidth: 16
                                                }
                                                AppIcon { app: modelData; size: 34 }
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 0
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: modelData.name
                                                        color: Theme.text
                                                        font.pixelSize: 14
                                                        font.weight: Font.DemiBold
                                                        elide: Text.ElideRight
                                                    }
                                                    Text {
                                                        text: rk.inst ? win.str.installed_badge : (modelData.variants[0].available === false ? win.str.unavailable : win.str.install)
                                                        color: rk.inst ? Theme.ok : Theme.dim
                                                        font.pixelSize: 11
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // 1 — Explorar
                MFlick {
                    id: exploreScroll
                    contentHeight: exploreCol.implicitHeight
                    ColumnLayout {
                        id: exploreCol
                        width: exploreScroll.width
                        spacing: 0
                        Flow {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 8
                            spacing: 10
                            Repeater {
                                model: win.catSorted
                                delegate: Chip {
                                    fontSize: 12
                                    text: win.str["cat_" + modelData]
                                    icon: win.catIcons[modelData]
                                    selected: win.category === modelData
                                    onClicked: win.category = modelData
                                }
                            }
                        }
                        ColumnLayout {
                            visible: win.indexBuilding
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 18
                            spacing: 8
                            Text {
                                Layout.fillWidth: true
                                text: win.str.catalog_loading
                                color: Theme.dim
                                font.pixelSize: 13
                                wrapMode: Text.WordWrap
                            }
                            ProgressBarX { Layout.fillWidth: true; pct: -1 }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 18
                            columns: width > 800 ? 2 : 1
                            columnSpacing: 16
                            rowSpacing: 12
                            Repeater {
                                model: win.exploreList
                                delegate: AppRow {
                                    Layout.fillWidth: true
                                    app: modelData
                                    onActivated: win.openApp(modelData)
                                }
                            }
                        }
                        MButton {
                            visible: win.exploreAll.length > win.shown
                            Layout.alignment: Qt.AlignHCenter
                            Layout.topMargin: 18
                            text: win.str.show_more + " (" + (win.exploreAll.length - win.shown) + ")"
                            onClicked: win.shown += 60
                        }
                        Item { Layout.preferredHeight: 32 }
                    }
                }

                // 2 — Pesquisa
                Item {
                    ListView {
                        anchors.fill: parent
                        clip: true
                        spacing: 10
                        topMargin: 8
                        bottomMargin: 24
                        leftMargin: 32
                        rightMargin: 32
                        id: searchLv
                        model: win.searchList
                        delegate: AppRow {
                            width: ListView.view.width - 64
                            app: modelData
                            onActivated: win.openApp(modelData)
                        }
                    }
                    MScrollBar { target: searchLv }
                    Text {
                        anchors.centerIn: parent
                        visible: win.searching || win.searchList.length === 0
                        text: win.searching ? win.str.searching : win.str.no_results
                        color: Theme.dim
                        font.pixelSize: 16
                    }
                }

                // 3 — Instaladas
                ColumnLayout {
                    spacing: 0
                    Flow {
                        Layout.fillWidth: true
                        Layout.leftMargin: 32
                        Layout.rightMargin: 32
                        Layout.topMargin: 8
                        Layout.bottomMargin: 14
                        spacing: 10
                        Repeater {
                            model: ["all", "apt", "flatpak", "appimage", "deb"]
                            delegate: Chip {
                                text: (modelData === "all" ? win.str.filter_all
                                       : (modelData === "apt" ? "APT" : (modelData === "flatpak" ? "Flatpak"
                                       : (modelData === "appimage" ? "AppImage" : "DEB"))))
                                      + " · " + win.countOrigin(modelData)
                                selected: win.instFilter === modelData
                                onClicked: win.instFilter = modelData
                            }
                        }
                    }
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            anchors.fill: parent
                            clip: true
                            spacing: 10
                            bottomMargin: 24
                            leftMargin: 32
                            rightMargin: 32
                            id: instLv
                            model: win.instShown
                            delegate: AppRow {
                                width: ListView.view.width - 64
                                app: modelData
                                onActivated: win.openApp(modelData)
                            }
                        }
                        MScrollBar { target: instLv }
                        Text {
                            anchors.centerIn: parent
                            visible: win.loadingInstalled || win.instShown.length === 0
                            text: win.loadingInstalled ? win.str.loading : win.str.empty_installed
                            color: Theme.dim
                            font.pixelSize: 16
                        }
                    }
                }

                // 4 — Atualizações
                ColumnLayout {
                    spacing: 0
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 32
                        Layout.rightMargin: 32
                        Layout.topMargin: 8
                        Layout.bottomMargin: 10
                        spacing: 10
                        Text {
                            Layout.fillWidth: true
                            text: win.updatesList.length > 0 ? (win.updatesList.length + " " + win.str.updates_count) : ""
                            color: Theme.text
                            font.pixelSize: 18
                            font.weight: Font.DemiBold
                        }
                        MButton {
                            primary: false
                            enabled: !win.ops["index"]
                            text: win.str.check_updates
                            onClicked: B.refreshIndex()
                        }
                        MButton {
                            visible: !!(win.ops["all"] || win.ops["sel"])
                            primary: false
                            text: win.str.cancel
                            onClicked: B.cancel(win.ops["all"] ? "all" : "sel")
                        }
                        MButton {
                            visible: win.updatesList.length > 0
                            primary: false
                            enabled: win.selCount > 0 && !win.ops["sel"] && !win.ops["all"]
                            text: win.str.update_selected + " (" + win.selCount + ")"
                            onClicked: B.updateSelected(win.updatesList.filter(function (a) { return !!win.selected[a.id] }))
                        }
                        MButton {
                            visible: win.updatesList.length > 0
                            enabled: !win.ops["all"] && !win.ops["sel"]
                            text: win.str.update_all
                            onClicked: B.updateAll()
                        }
                    }
                    Check {
                        visible: win.updatesList.length > 0
                        Layout.leftMargin: 32
                        Layout.bottomMargin: 10
                        label: win.str.select_all
                        checked: win.updatesList.length > 0 && win.selCount === win.updatesList.length
                        onToggled: win.selectAll(win.selCount !== win.updatesList.length)
                    }
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            anchors.fill: parent
                            clip: true
                            spacing: 10
                            bottomMargin: 24
                            leftMargin: 32
                            rightMargin: 32
                            id: updLv
                            model: win.updatesList
                            delegate: UpdateRow {
                                width: ListView.view.width - 64
                                app: modelData
                                checked: !!win.selected[modelData.id]
                                opState: win.itemOps[modelData.id]
                                onToggled: win.toggleSel(modelData.id)
                            }
                        }
                        MScrollBar { target: updLv }
                        ColumnLayout {
                            anchors.centerIn: parent
                            visible: win.updatesList.length === 0
                            spacing: 16
                            Rectangle {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 96
                                Layout.preferredHeight: 96
                                radius: 48
                                color: Theme.raised
                                border.width: 2
                                border.color: Theme.primaryDark
                                Text {
                                    anchors.centerIn: parent
                                    text: "✓"
                                    color: Theme.primary
                                    font.pixelSize: 52
                                    font.bold: true
                                }
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: win.str.no_updates
                                color: Theme.text
                                font.pixelSize: 34
                                font.weight: Font.Bold
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }
                    }
                }

                // 5 — Definições
                MFlick {
                    id: setScroll
                    contentHeight: setCol.implicitHeight
                    ColumnLayout {
                        id: setCol
                        width: setScroll.width
                        spacing: 4

                        SectionHead {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 8
                            title: win.str.updates
                        }
                        Check {
                            Layout.leftMargin: 32
                            checked: B.notifyUpdates
                            label: win.str.notify_updates
                            note: win.str.notify_updates_hint
                            onToggled: B.setNotifyUpdates(!B.notifyUpdates)
                        }

                        SectionHead {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 22
                            title: win.str.repos_title
                        }
                        RowLayout {
                            Layout.leftMargin: 32
                            spacing: 14
                            MButton {
                                enabled: !win.ops["index"]
                                text: win.ops["index"] ? win.str.st_update : win.str.refresh_repos
                                onClicked: B.refreshIndex()
                            }
                            Text {
                                text: win.str.refresh_repos_hint
                                color: Theme.dim
                                font.pixelSize: 13
                            }
                        }

                        SectionHead {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 22
                            title: "Flatpak"
                            showDefault: true
                            showAdd: true
                            isDefault: B.defaultSource === "flatpak"
                            onMakeDefault: B.setDefaultSource("flatpak")
                            onAddSource: addPop.open()
                        }
                        Text {
                            visible: !win.sourcesData.flatpakPresent
                            Layout.leftMargin: 32
                            text: "Flatpak — " + win.str.not_installed
                            color: Theme.dim
                            font.pixelSize: 13
                        }
                        Repeater {
                            model: win.sourcesData.flatpak ? win.sourcesData.flatpak : []
                            delegate: Check {
                                Layout.leftMargin: 32
                                checked: modelData.enabled
                                label: modelData.id + (modelData.user ? " " + win.str.user_suffix : "")
                                note: "- " + modelData.host
                                onToggled: B.setFlatpakRemote(modelData.id, modelData.user, !modelData.enabled)
                            }
                        }



                        SectionHead {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 22
                            title: "AppImage"
                            showDefault: true
                            isDefault: B.defaultSource === "appimage"
                            onMakeDefault: B.setDefaultSource("appimage")
                        }
                        Check {
                            Layout.leftMargin: 32
                            checked: !!win.sourcesData.appimageOn
                            label: "AppImage"
                            note: "appimage.github.io"
                            onToggled: B.setAppimage(!win.sourcesData.appimageOn)
                        }

                        SectionHead {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 22
                            title: win.str.set_firmware
                        }
                        Text {
                            visible: !win.sourcesData.fwupdPresent
                            Layout.leftMargin: 32
                            text: "fwupd — " + win.str.not_installed
                            color: Theme.dim
                            font.pixelSize: 13
                        }
                        Repeater {
                            model: win.sourcesData.firmware ? win.sourcesData.firmware : []
                            delegate: Check {
                                Layout.leftMargin: 32
                                checked: modelData.enabled
                                label: modelData.id
                                note: "- " + modelData.title
                                onToggled: B.setFirmwareRemote(modelData.id, !modelData.enabled)
                            }
                        }

                        SectionHead {
                            Layout.fillWidth: true
                            Layout.leftMargin: 32
                            Layout.rightMargin: 32
                            Layout.topMargin: 22
                            title: win.sourcesData.osname ? win.sourcesData.osname : "Ubuntu"
                            showDefault: true
                            isDefault: B.defaultSource === "apt"
                            onMakeDefault: B.setDefaultSource("apt")
                        }
                        Repeater {
                            model: win.sourcesData.apt ? win.sourcesData.apt : []
                            delegate: Check {
                                Layout.leftMargin: 32
                                checked: modelData.enabled
                                label: modelData.label
                                onToggled: B.setAptSource(modelData.file, modelData.index, !modelData.enabled)
                            }
                        }
                        Item { Layout.preferredHeight: 32 }
                    }
                }

                // 6 — Sobre
                MFlick {
                    id: aboutScroll
                    contentHeight: aboutCol.height
                    ColumnLayout {
                        id: aboutCol
                        width: aboutScroll.width
                        height: Math.max(aboutScroll.height, implicitHeight)
                        spacing: 6
                    Item { Layout.fillHeight: true }
                    Image {
                        Layout.alignment: Qt.AlignHCenter
                        source: "file://" + Theme.assets + "/logo.png"
                        sourceSize: Qt.size(192, 192)
                        Layout.preferredWidth: 96
                        Layout.preferredHeight: 96
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "Mainuan Store"
                        color: Theme.text
                        font.pixelSize: 28
                        font.weight: Font.Bold
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: win.str.about_sub
                        color: Theme.dim
                        font.pixelSize: 14
                    }
                    Item { Layout.preferredHeight: 18 }
                    Repeater {
                        model: [
                            { k: win.str.about_version, v: B.appVersion, link: "" },
                            { k: win.str.about_copyright, v: "© 2026 David Caixinha", link: "" },
                            { k: win.str.about_license, v: win.str.license_name, link: "https://www.gnu.org/licenses/gpl-3.0.html" },
                            { k: win.str.about_author, v: "David Caixinha", link: "" },
                            { k: win.str.about_translator, v: "David Caixinha", link: "" }
                        ]
                        delegate: ColumnLayout {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.bottomMargin: 12
                            spacing: 2
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: modelData.k
                                color: Theme.dim
                                font.pixelSize: 12
                                font.capitalization: Font.AllUppercase
                                font.letterSpacing: 1
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: Math.min(520, implicitWidth)
                                horizontalAlignment: Text.AlignHCenter
                                text: modelData.v
                                color: Theme.text
                                font.pixelSize: 15
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                visible: modelData.link !== ""
                                Layout.alignment: Qt.AlignHCenter
                                text: modelData.link
                                color: Theme.primary
                                font.pixelSize: 13
                                font.underline: true
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: Qt.openUrlExternally(modelData.link)
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    }
                }

                // 7 — AppImage (gestor integrado, aspeto do Mainuan AppImage Manager)
                AppImagePage {
                    id: aiPage
                    onToast: function (t) { win.toast(t) }
                }
            }
        }
    }

    // ---------- aviso temporário ----------
    Rectangle {
        visible: win.toastText !== ""
        z: 20
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        width: Math.min(700, toastLabel.implicitWidth + 40)
        height: 44
        radius: 22
        color: Theme.raised
        border.width: 1
        border.color: Theme.primaryDark
        Text {
            id: toastLabel
            anchors.centerIn: parent
            width: parent.width - 32
            text: win.toastText
            color: Theme.text
            font.pixelSize: 14
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }
    }

    // ---------- detalhe da aplicação (capturas, versão, descrição) ----------
    Popup {
        id: pop
        property var app: ({})
        property int sel: 0
        property string longText: ""
        property var vinfo: ({})
        property var shots: []
        property int shotIdx: 0
        property bool shotsLoading: false
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(1000, win.width - 40)
        height: Math.min(780, win.height - 40)
        modal: true
        focus: true
        padding: 24
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        readonly property bool wide: width >= 760
        readonly property var variants: app.variants ? app.variants : []
        readonly property var variant: variants.length > sel ? variants[sel] : ({})
        readonly property var curInfo: (variant.source && vinfo[variant.source]) ? vinfo[variant.source] : ({})
        readonly property string curVer: curInfo.version ? curInfo.version : (variant.version ? variant.version : "")
        readonly property string curSize: curInfo.size ? curInfo.size : ""
        readonly property string infoLine: {
            var parts = []
            if (curVer !== "") parts.push(win.str.version + " " + curVer)
            if (curSize !== "") parts.push(curSize)
            if (parts.length === 0 && variant.source) return srcName(variant.source)
            return parts.join(" · ")
        }
        readonly property bool inst: { B.rev; return variant.source ? B.isInstalled(variant.source, variant.pkg) : false }
        readonly property var op: win.ops[app.id]
        readonly property bool working: op !== undefined
        readonly property int pct: working ? op.pct : -1

        function srcName(s) {
            return s === "apt" ? "APT" : (s === "flatpak" ? "Flatpak" : (s === "appimage" ? "AppImage" : "DEB"))
        }
        function variantText(v) {
            B.rev
            var i = vinfo[v.source]
            var ver = (i && i.version) ? i.version : (v.version ? v.version : "")
            var t = srcName(v.source) + (ver !== "" ? " · " + ver : "")
            return B.isInstalled(v.source, v.pkg) ? t + "   ✓" : t
        }
        function goShot(d) {
            if (shots.length === 0) return
            shotIdx = (shotIdx + d + shots.length) % shots.length
            thumbs.positionViewAtIndex(shotIdx, ListView.Contain)
        }

        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle {
            radius: 22
            color: Theme.bg2
            border.width: 1
            border.color: Theme.border
        }
        contentItem: ColumnLayout {
            spacing: 16

            // cabeçalho: ícone, nome, versão + tamanho escolhidos
            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                AppIcon { app: pop.app; size: 80 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        Layout.fillWidth: true
                        text: pop.app.name || ""
                        color: Theme.text
                        font.pixelSize: 26
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: pop.infoLine
                        color: Theme.primary
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: pop.app.summary || ""
                        color: Theme.dim
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }
                MButton {
                    Layout.alignment: Qt.AlignTop
                    primary: false
                    text: win.str.close
                    onClicked: pop.close()
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                columns: pop.wide ? 2 : 1
                columnSpacing: 22
                rowSpacing: 14

                // caixa à direita: escolha da versão + ações
                Rectangle {
                    Layout.row: 0
                    Layout.column: pop.wide ? 1 : 0
                    Layout.alignment: Qt.AlignTop
                    Layout.fillWidth: !pop.wide
                    Layout.preferredWidth: pop.wide ? 270 : -1
                    Layout.preferredHeight: boxCol.implicitHeight + 32
                    radius: 16
                    color: Theme.surface
                    border.width: 1
                    border.color: Theme.border
                    ColumnLayout {
                        id: boxCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 16
                        spacing: 10
                        Text {
                            text: win.str.choose_version
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        MCombo {
                            id: verBox
                            Layout.fillWidth: true
                            popupMax: 220
                            model: pop.variants
                            textOf: function (v) { return pop.variantText(v) }
                            onActivated: function (i) { pop.sel = i }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: pop.variant.source !== undefined && win.str["src_" + pop.variant.source + "_d"] !== undefined
                            text: pop.variant.source ? (win.str["src_" + pop.variant.source + "_d"] || "") : ""
                            color: Theme.dim
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            MButton {
                                visible: !pop.inst
                                Layout.fillWidth: true
                                enabled: !pop.working && pop.variant.available !== false
                                text: pop.working ? win.str.installing : (pop.variant.available === false ? win.str.unavailable : win.str.install)
                                onClicked: B.install(pop.app, pop.variant.source)
                            }
                            MButton {
                                visible: pop.inst
                                Layout.fillWidth: true
                                enabled: !pop.working
                                text: win.str.open
                                onClicked: B.launch(pop.app, pop.variant.source)
                            }
                            MButton {
                                visible: pop.inst
                                primary: false
                                enabled: !pop.working
                                text: pop.working ? win.str.removing : win.str.remove
                                onClicked: B.remove(pop.app, pop.variant.source)
                            }
                        }
                        ColumnLayout {
                            visible: pop.working
                            Layout.fillWidth: true
                            spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: pop.inst ? win.str.removing : win.str.installing
                                    color: Theme.text
                                    font.pixelSize: 13
                                }
                                Text {
                                    text: pop.pct >= 0 ? pop.pct + "%" : "…"
                                    color: Theme.primary
                                    font.pixelSize: 14
                                    font.weight: Font.Bold
                                }
                            }
                            ProgressBarX { Layout.fillWidth: true; implicitHeight: 10; pct: pop.pct }
                            MButton {
                                primary: false
                                text: win.str.cancel
                                onClicked: B.cancel(pop.app.id)
                            }
                        }
                    }
                }

                // à esquerda: capturas de ecrã + descrição (com rolamento)
                MFlick {
                    id: popFlick
                    Layout.row: pop.wide ? 0 : 1
                    Layout.column: 0
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 140
                    contentHeight: popBody.implicitHeight + 8
                    ColumnLayout {
                        id: popBody
                        width: popFlick.width - 18
                        spacing: 14

                        Text {
                            visible: pop.shots.length === 0 && pop.shotsLoading
                            text: win.str.loading_shots
                            color: Theme.dim
                            font.pixelSize: 13
                        }
                        ColumnLayout {
                            visible: pop.shots.length > 0
                            Layout.fillWidth: true
                            spacing: 10
                            Text {
                                text: win.str.screenshots
                                color: Theme.text
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(200, Math.min(360, width * 0.56))
                                radius: 14
                                color: Theme.surface
                                border.width: 1
                                border.color: Theme.border
                                clip: true
                                Image {
                                    id: shotImg
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    source: pop.shots.length > 0 ? pop.shots[pop.shotIdx] : ""
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                    smooth: true
                                    mipmap: true
                                }
                                Text {
                                    anchors.centerIn: parent
                                    visible: shotImg.status === Image.Loading
                                    text: "…"
                                    color: Theme.dim
                                    font.pixelSize: 28
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: bigShot.open()
                                }
                                Rectangle {
                                    visible: pop.shots.length > 1
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 36; height: 36; radius: 18
                                    color: lm.containsMouse ? Theme.primary : Theme.bg2
                                    border.width: 1
                                    border.color: Theme.border
                                    opacity: 0.92
                                    Text {
                                        anchors.centerIn: parent
                                        text: "‹"
                                        color: lm.containsMouse ? Theme.onPrimary : Theme.text
                                        font.pixelSize: 24
                                        font.bold: true
                                    }
                                    MouseArea {
                                        id: lm
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: pop.goShot(-1)
                                    }
                                }
                                Rectangle {
                                    visible: pop.shots.length > 1
                                    anchors.right: parent.right
                                    anchors.rightMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 36; height: 36; radius: 18
                                    color: rm2.containsMouse ? Theme.primary : Theme.bg2
                                    border.width: 1
                                    border.color: Theme.border
                                    opacity: 0.92
                                    Text {
                                        anchors.centerIn: parent
                                        text: "›"
                                        color: rm2.containsMouse ? Theme.onPrimary : Theme.text
                                        font.pixelSize: 24
                                        font.bold: true
                                    }
                                    MouseArea {
                                        id: rm2
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: pop.goShot(1)
                                    }
                                }
                            }
                            ListView {
                                id: thumbs
                                visible: pop.shots.length > 1
                                Layout.fillWidth: true
                                Layout.preferredHeight: 66
                                orientation: ListView.Horizontal
                                spacing: 8
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: pop.shots
                                delegate: Rectangle {
                                    width: 104
                                    height: 62
                                    radius: 10
                                    color: Theme.surface
                                    clip: true
                                    border.width: 2
                                    border.color: index === pop.shotIdx ? Theme.primary : Theme.border
                                    Image {
                                        anchors.fill: parent
                                        anchors.margins: 3
                                        source: modelData
                                        sourceSize: Qt.size(240, 140)
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: pop.shotIdx = index
                                    }
                                }
                            }
                        }

                        Text {
                            text: win.str.description
                            color: Theme.text
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: pop.longText !== "" ? pop.longText : win.str.loading
                            color: Theme.dim
                            font.pixelSize: 14
                            wrapMode: Text.WordWrap
                            lineHeight: 1.25
                        }
                    }
                }
            }
        }
    }

    // ---------- captura de ecrã em ponto grande ----------
    Popup {
        id: bigShot
        z: 10
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: win.width - 40
        height: win.height - 40
        modal: true
        focus: true
        padding: 12
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: "#d9000a10" }
        background: Rectangle {
            radius: 18
            color: Theme.bg2
            border.width: 1
            border.color: Theme.border
        }
        contentItem: Item {
            Image {
                anchors.fill: parent
                source: pop.shots.length > 0 ? pop.shots[pop.shotIdx] : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                smooth: true
                mipmap: true
            }
            MouseArea {
                anchors.fill: parent
                onClicked: bigShot.close()
            }
            MButton {
                anchors.top: parent.top
                anchors.right: parent.right
                primary: false
                text: win.str.close
                onClicked: bigShot.close()
            }
            Rectangle {
                visible: pop.shots.length > 1
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: 44; height: 44; radius: 22
                color: bl.containsMouse ? Theme.primary : Theme.surface
                border.width: 1
                border.color: Theme.border
                Text {
                    anchors.centerIn: parent
                    text: "‹"
                    color: bl.containsMouse ? Theme.onPrimary : Theme.text
                    font.pixelSize: 30
                    font.bold: true
                }
                MouseArea {
                    id: bl
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: pop.goShot(-1)
                }
            }
            Rectangle {
                visible: pop.shots.length > 1
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 44; height: 44; radius: 22
                color: br.containsMouse ? Theme.primary : Theme.surface
                border.width: 1
                border.color: Theme.border
                Text {
                    anchors.centerIn: parent
                    text: "›"
                    color: br.containsMouse ? Theme.onPrimary : Theme.text
                    font.pixelSize: 30
                    font.bold: true
                }
                MouseArea {
                    id: br
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: pop.goShot(1)
                }
            }
        }
    }

    // ---------- instalar a partir de ficheiro (DEB) ----------
    Popup {
        id: filePop
        property var info: ({})
        property string result: ""      // "" (a perguntar / a instalar), "ok" (concluída), "fail" (falhou)
        property string resultMsg: ""
        readonly property bool finished: result !== ""
        readonly property bool removing: info.installed === true
        readonly property bool working: !finished && (info.path ? win.ops["file:" + info.path] !== undefined : false)
        readonly property int pct: working ? win.ops["file:" + info.path].pct : -1
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(520, win.width - 80)
        modal: true
        focus: true
        padding: 26
        closePolicy: working ? Popup.NoAutoClose : (Popup.CloseOnEscape | Popup.CloseOnPressOutside)
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle {
            radius: 22
            color: Theme.bg2
            border.width: 1
            border.color: Theme.border
        }
        contentItem: ColumnLayout {
            spacing: 12

            // --- fim da instalação: só o resultado e o botão Fechar ---
            ColumnLayout {
                visible: filePop.finished
                Layout.fillWidth: true
                spacing: 12
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 64
                    radius: 32
                    color: filePop.result === "ok" ? Theme.ok : Theme.err
                    Text {
                        anchors.centerIn: parent
                        text: filePop.result === "ok" ? "✓" : "✕"
                        color: "#ffffff"
                        font.pixelSize: 34
                        font.bold: true
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: filePop.result === "ok" ? (filePop.removing ? win.str.remove_done : win.str.install_done)
                                                  : (filePop.removing ? win.str.remove_failed : win.str.install_failed)
                    color: filePop.result === "ok" ? Theme.ok : Theme.err
                    font.pixelSize: 22
                    font.weight: Font.Bold
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    text: filePop.info.name ? filePop.info.name + (filePop.info.version ? " · " + filePop.info.version : "") : ""
                    color: Theme.text
                    font.pixelSize: 15
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    visible: filePop.result === "fail" && filePop.resultMsg !== ""
                    text: filePop.resultMsg
                    color: Theme.dim
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
                MButton {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 6
                    text: win.str.close
                    onClicked: filePop.close()
                }
            }

            // --- antes/durante a instalação ---
            ColumnLayout {
                visible: !filePop.finished
                Layout.fillWidth: true
                spacing: 12
                Text {
                    text: filePop.removing ? win.str.file_installed_title : win.str.install_file_title
                    color: Theme.text
                    font.pixelSize: 20
                    font.weight: Font.Bold
                }
                RowLayout {
                    spacing: 8
                    Text {
                        text: filePop.info.name ? filePop.info.name : ""
                        color: Theme.text
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Badge { visible: filePop.info.ok === true; source: filePop.info.kind === "deb" ? "deb" : "appimage" }
                    Text {
                        visible: !!filePop.info.version
                        text: filePop.info.version ? "· " + filePop.info.version : ""
                        color: Theme.dim
                        font.pixelSize: 13
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: filePop.removing ? String(win.str.file_installed_text).replace("{name}", filePop.info.name ? filePop.info.name : "")
                                           : (filePop.info.ok === true ? (filePop.info.description || "") : win.str.file_unsupported)
                    color: (filePop.removing || filePop.info.ok === true) ? (filePop.removing ? Theme.text : Theme.dim) : Theme.err
                    font.pixelSize: filePop.removing ? 14 : 13
                    wrapMode: Text.WordWrap
                }
                Text {
                    Layout.fillWidth: true
                    visible: filePop.removing && !!filePop.info.installedVersion
                    text: win.str.file_installed_ver + ": " + (filePop.info.installedVersion ? filePop.info.installedVersion : "")
                    color: Theme.dim
                    font.pixelSize: 13
                }
                Text {
                    Layout.fillWidth: true
                    visible: filePop.removing && filePop.info.canRemove === false
                    text: win.str.file_protected
                    color: Theme.warn
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
                ColumnLayout {
                    visible: filePop.working
                    Layout.fillWidth: true
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: filePop.removing ? win.str.removing : win.str.installing; color: Theme.text; font.pixelSize: 13 }
                        Text {
                            text: filePop.pct >= 0 ? filePop.pct + "%" : "…"
                            color: Theme.primary
                            font.pixelSize: 14
                            font.weight: Font.Bold
                        }
                    }
                    ProgressBarX { Layout.fillWidth: true; implicitHeight: 10; pct: filePop.pct }
                }
                RowLayout {
                    spacing: 10
                    MButton {
                        visible: filePop.info.ok === true && !filePop.removing
                        enabled: !filePop.working
                        text: filePop.working ? win.str.installing : win.str.install
                        onClicked: B.installFile(filePop.info.path)
                    }
                    MButton {
                        visible: filePop.removing && filePop.info.canRemove !== false
                        danger: true
                        enabled: !filePop.working
                        text: filePop.working ? "…" : win.str.ai_delete
                        onClicked: B.uninstallFile(filePop.info.path)
                    }
                    MButton {
                        primary: false
                        text: win.str.cancel
                        onClicked: filePop.working ? B.cancel("file:" + filePop.info.path) : filePop.close()
                    }
                }
            }
        }
    }

    // ---------- adicionar fonte Flatpak ----------
    Popup {
        id: addPop
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(520, win.width - 80)
        modal: true
        focus: true
        padding: 26
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle {
            radius: 22
            color: Theme.bg2
            border.width: 1
            border.color: Theme.border
        }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                text: win.str.add_source
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
            }
            TextField {
                id: urlField
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                placeholderText: win.str.add_source_ph
                placeholderTextColor: Theme.dim
                color: Theme.text
                selectionColor: Theme.primaryDark
                font.pixelSize: 14
                leftPadding: 14
                background: Rectangle {
                    radius: 10
                    color: Theme.surface
                    border.width: 1
                    border.color: urlField.activeFocus ? Theme.primary : Theme.border
                }
            }
            RowLayout {
                spacing: 10
                MButton {
                    enabled: urlField.text.trim().length > 8
                    text: win.str.add
                    onClicked: { B.addFlatpakRemote(urlField.text.trim()); urlField.text = ""; addPop.close() }
                }
                MButton { primary: false; text: win.str.cancel; onClicked: addPop.close() }
            }
        }
    }
}
