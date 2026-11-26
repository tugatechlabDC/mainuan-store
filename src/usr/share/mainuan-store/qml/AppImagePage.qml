import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Menu «AppImage»: mesmas funções e aspeto do Mainuan AppImage Manager
// (lista, adicionar, integrar no menu iniciar, propriedades, atualizações, executar, eliminar).
Item {
    id: page
    readonly property var str: B.strings
    property var items: []
    property string sig: ""
    property var updates: ({})          // ficheiro -> resultado da última verificação
    property string lastAdded: ""
    property bool busy: false
    property string busyText: ""
    property int busyPct: -1
    signal toast(string text)

    function refresh() { B.loadAppimages() }
    function fmt(t, name) { return String(t).replace("{name}", name) }
    function localPath(url) {
        var u = String(url)
        return u.indexOf("file://") === 0 ? decodeURIComponent(u.substring(7)) : u
    }
    function fileName(path) {
        var p = String(path)
        return p.substring(p.lastIndexOf("/") + 1)
    }
    function pick() {
        if (pickL.item) {
            pickL.item.kind = "appimage"
            pickL.item.open()
        } else toast(str.op_fail)
    }
    function askAdd(url) {
        addPop.url = String(url)
        addPop.name = fileName(localPath(url))
        addPop.open()
    }
    function setUpdate(file, info) {
        var u = Object.assign({}, updates)
        u[file] = info
        updates = u
    }
    function phaseOf(info) {
        if (info.mode === "none") return "nosource"
        if (info.has_update === true) return "available"
        if (info.has_update === false) return "uptodate"
        return "error"
    }
    function integratedFiles() {
        var out = []
        for (var i = 0; i < items.length; i++) if (items[i].integrated) out.push({ file: items[i].file, name: items[i].name })
        return out
    }
    function indexOfFile(file) {
        for (var i = 0; i < items.length; i++) if (items[i].file === file) return i
        return -1
    }

    onVisibleChanged: if (visible) refresh()
    Component.onCompleted: refresh()

    Loader { id: pickL; source: "FilePicker.qml" }
    Connections {
        target: pickL.item
        function onPicked(url) { page.askAdd(url) }
    }

    Timer {
        // acompanha alterações feitas fora da loja (equivalente ao monitor de pasta do gestor)
        interval: 4000
        repeat: true
        running: page.visible
        onTriggered: B.loadAppimages()
    }
    Timer { id: hlTimer; interval: 4500; onTriggered: page.lastAdded = "" }

    Connections {
        target: B
        function onAppimagesReady(list) {
            var s = JSON.stringify(list)
            if (s !== page.sig) {
                page.sig = s
                page.items = list
                if (page.lastAdded !== "") {
                    var i = page.indexOfFile(page.lastAdded)
                    if (i >= 0) lv.positionViewAtIndex(i, ListView.Contain)
                }
            }
        }
        function onAppimageBusy(isBusy, text, percent) {
            page.busyText = text
            page.busyPct = percent
            page.busy = isBusy
            if (isBusy && !busyPop.opened) busyPop.open()
            if (!isBusy) busyPop.close()
        }
        function onAppimageResult(kind, ok, message, file) {
            if (kind === "add" || kind === "integrate") {
                if (ok) {
                    page.lastAdded = file
                    hlTimer.restart()
                    page.toast(page.str.ai_added)
                } else page.toast(page.str.ai_add_error + ": " + message)
            } else if (kind === "run") {
                if (!ok) page.toast(page.str.ai_run_error + ": " + message)
            } else if (kind === "delete" || kind === "save") {
                page.toast(ok ? page.str.op_ok : page.str.op_fail + ": " + message)
            }
        }
        function onAppimageUpdateInfo(file, info) {
            page.setUpdate(file, info)
            if (updPop.opened && updPop.a.file === file) updPop.gotInfo(info)
            if (allPop.opened) allPop.gotInfo(file, info)
        }
        function onAppimageUpdateState(file, phase, percent, message) {
            if (updPop.opened && updPop.a.file === file) updPop.gotState(phase, percent, message)
            if (allPop.opened) allPop.gotState(file, phase, percent, message)
            if (phase === "done") {
                var u = Object.assign({}, page.updates)
                delete u[file]
                page.updates = u
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 32
            Layout.rightMargin: 32
            Layout.topMargin: 14
            Layout.bottomMargin: 10
            spacing: 10
            Text {
                text: page.str.ai_title
                color: Theme.text
                font.pixelSize: 22
                font.weight: Font.Bold
            }
            Text {
                text: "· " + page.items.length
                color: Theme.dim
                font.pixelSize: 16
                Layout.alignment: Qt.AlignBottom
            }
            Item { Layout.fillWidth: true }
            MiniButton {
                glyph: "plus"
                text: page.str.ai_add_tip
                iconOnly: page.width < 700
                tip: page.str.ai_add_tip
                onClicked: page.pick()
            }
            MiniButton {
                glyph: "updates"
                text: page.str.ai_check_all
                iconOnly: page.width < 900
                tip: page.str.ai_check_all
                onClicked: allPop.openAll()
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: lv
                anchors.fill: parent
                clip: true
                model: page.items
                bottomMargin: 20
                leftMargin: 32
                rightMargin: 32
                boundsBehavior: Flickable.StopAtBounds
                delegate: Rectangle {
                    id: row
                    readonly property var a: modelData
                    readonly property var upd: page.updates[modelData.file]
                    readonly property bool hl: page.lastAdded === modelData.file
                    width: ListView.view.width - 64
                    height: 88
                    radius: 12
                    color: hl ? Theme.banner : (rma.containsMouse ? Theme.surface : "transparent")
                    border.width: hl ? 1 : 0
                    border.color: Theme.primary
                    Behavior on color { ColorAnimation { duration: 250 } }
                    MouseArea { id: rma; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                    Rectangle {
                        visible: !row.hl
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 1
                        color: Theme.border
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 14
                        Item {
                            Layout.preferredWidth: 52
                            Layout.preferredHeight: 52
                            Image {
                                anchors.fill: parent
                                visible: realIcon.status !== Image.Ready
                                source: "image://icon/application-x-executable"
                                sourceSize: Qt.size(104, 104)
                                fillMode: Image.PreserveAspectFit
                            }
                            Image {
                                id: realIcon
                                anchors.fill: parent
                                source: row.a.icon
                                sourceSize: Qt.size(104, 104)
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text {
                                Layout.fillWidth: true
                                text: row.a.name
                                color: Theme.text
                                font.pixelSize: 15
                                font.weight: Font.Bold
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: row.a.file
                                color: Theme.dim
                                font.pixelSize: 12
                                elide: Text.ElideMiddle
                            }
                            Text {
                                Layout.fillWidth: true
                                text: page.str.ai_type + " " + row.a.type + "  ·  " + row.a.sizeText
                                      + (row.a.version !== "" ? "  ·  v" + row.a.version : "")
                                      + (!row.a.integrated ? "  ·  " + page.str.ai_not_integrated
                                         : ((row.upd && row.upd.has_update === true) ? "  ·  " + page.str.ai_available_short : ""))
                                color: !row.a.integrated ? Theme.warn
                                       : ((row.upd && row.upd.has_update === true) ? Theme.ok : Theme.dim)
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                        }
                        IconBtn {
                            visible: row.a.integrated
                            glyph: "props"
                            tip: page.str.ai_props
                            onClicked: propsPop.openFor(row.a)
                        }
                        IconBtn {
                            visible: row.a.integrated
                            glyph: "updates"
                            tip: page.str.ai_check_update
                            onClicked: updPop.openFor(row.a)
                        }
                        IconBtn {
                            visible: row.a.integrated
                            glyph: "play"
                            tip: page.str.ai_run
                            onClicked: B.runAppimage(row.a.file)
                        }
                        MButton {
                            visible: !row.a.integrated
                            text: page.str.ai_integrate
                            onClicked: B.integrateAppimage(row.a.file)
                        }
                        IconBtn {
                            glyph: "trash"
                            danger: true
                            tip: page.str.ai_delete
                            onClicked: { delPop.a = row.a; delPop.open() }
                        }
                    }
                }
            }
            MScrollBar { target: lv }

            Text {
                anchors.centerIn: parent
                visible: page.items.length === 0
                width: Math.min(parent.width - 80, 520)
                text: page.str.ai_empty
                color: Theme.dim
                font.pixelSize: 16
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

            DropArea {
                id: dropArea
                anchors.fill: parent
                onEntered: function (drag) { drag.accepted = drag.hasUrls }
                onDropped: function (drop) {
                    if (!drop.hasUrls) return
                    for (var i = 0; i < drop.urls.length; i++) {
                        var u = String(drop.urls[i])
                        if (u.toLowerCase().endsWith(".appimage")) { page.askAdd(u); break }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 12
                    visible: dropArea.containsDrag
                    radius: 18
                    color: "#33" + String(Theme.primary).replace("#", "")
                    border.width: 2
                    border.color: Theme.primary
                    Text {
                        anchors.centerIn: parent
                        text: page.str.ai_drop
                        color: Theme.text
                        font.pixelSize: 20
                        font.weight: Font.Bold
                    }
                }
            }
        }
    }

    // ---------- adicionar: mover ou copiar ----------
    Popup {
        id: addPop
        property string url: ""
        property string name: ""
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(540, parent.width - 60)
        modal: true
        focus: true
        padding: 26
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle { radius: 22; color: Theme.bg2; border.width: 1; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                text: page.fmt(page.str.ai_add_q, addPop.name)
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
                wrapMode: Text.WrapAnywhere
            }
            Text {
                Layout.fillWidth: true
                text: page.str.ai_add_q_text
                color: Theme.dim
                font.pixelSize: 14
                wrapMode: Text.WordWrap
            }
            Flow {
                Layout.fillWidth: true
                spacing: 10
                MButton {
                    text: page.str.ai_copy
                    onClicked: { B.addAppimage(addPop.url, true); addPop.close() }
                }
                MButton {
                    primary: false
                    text: page.str.ai_move
                    onClicked: { B.addAppimage(addPop.url, false); addPop.close() }
                }
                MButton { primary: false; text: page.str.cancel; onClicked: addPop.close() }
            }
        }
    }

    // ---------- a adicionar / integrar (progresso) ----------
    Popup {
        id: busyPop
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 60)
        modal: true
        focus: true
        padding: 26
        closePolicy: Popup.NoAutoClose
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle { radius: 22; color: Theme.bg2; border.width: 1; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                text: page.str.ai_adding
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
            }
            Text {
                Layout.fillWidth: true
                text: page.busyText
                color: Theme.text
                font.pixelSize: 14
                elide: Text.ElideMiddle
            }
            Text {
                Layout.fillWidth: true
                text: page.str.ai_extracting
                color: Theme.dim
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            ProgressBarX { Layout.fillWidth: true; implicitHeight: 10; pct: page.busyPct >= 100 ? -1 : page.busyPct }
        }
    }

    // ---------- eliminar ----------
    Popup {
        id: delPop
        property var a: ({})
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 60)
        modal: true
        focus: true
        padding: 26
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle { radius: 22; color: Theme.bg2; border.width: 1; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                text: page.fmt(page.str.ai_del_q, delPop.a.name ? delPop.a.name : "")
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: page.str.ai_del_text
                color: Theme.dim
                font.pixelSize: 14
                wrapMode: Text.WordWrap
            }
            RowLayout {
                spacing: 10
                MButton {
                    danger: true
                    text: page.str.ai_delete
                    onClicked: { B.deleteAppimage(delPop.a.file); delPop.close() }
                }
                MButton { primary: false; text: page.str.cancel; onClicked: delPop.close() }
            }
        }
    }

    // ---------- propriedades ----------
    Popup {
        id: propsPop
        property var a: ({})
        function openFor(app) {
            a = app
            nameF.text = app.name
            verF.text = app.version
            descF.text = app.comment
            catF.text = app.categories
            rootCk.checked = app.runAsRoot
            urlF.text = app.updateUrl
            open()
        }
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(560, parent.width - 60)
        height: Math.min(660, parent.height - 40)
        modal: true
        focus: true
        padding: 24
        closePolicy: Popup.CloseOnEscape
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle { radius: 22; color: Theme.bg2; border.width: 1; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                text: page.str.ai_props
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
            }
            MFlick {
                id: propsFlick
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentHeight: pcol.implicitHeight
                ColumnLayout {
                    id: pcol
                    width: propsFlick.width - 16
                    spacing: 14
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 16
                        Image {
                            Layout.preferredWidth: 64
                            Layout.preferredHeight: 64
                            source: propsPop.a.icon ? propsPop.a.icon : "image://icon/application-x-executable"
                            sourceSize: Qt.size(128, 128)
                            fillMode: Image.PreserveAspectFit
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.str.ai_file + ": " + (propsPop.a.filename ? propsPop.a.filename : "") + "\n"
                                  + page.str.ai_size + ": " + (propsPop.a.sizeText ? propsPop.a.sizeText : "") + "  ·  "
                                  + page.str.ai_type + ": AppImage " + (propsPop.a.type ? propsPop.a.type : "")
                            color: Theme.dim
                            font.pixelSize: 12
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        rowSpacing: 10
                        columnSpacing: 12
                        Text { text: page.str.ai_name; color: Theme.dim; font.pixelSize: 13; Layout.alignment: Qt.AlignRight | Qt.AlignVCenter }
                        MField { id: nameF; Layout.fillWidth: true }
                        Text { text: page.str.version; color: Theme.dim; font.pixelSize: 13; Layout.alignment: Qt.AlignRight | Qt.AlignVCenter }
                        MField { id: verF; Layout.fillWidth: true; placeholderText: "1.2.3" }
                        Text { text: page.str.ai_desc; color: Theme.dim; font.pixelSize: 13; Layout.alignment: Qt.AlignRight | Qt.AlignVCenter }
                        MField { id: descF; Layout.fillWidth: true; placeholderText: page.str.ai_short_desc }
                        Text { text: page.str.ai_categories; color: Theme.dim; font.pixelSize: 13; Layout.alignment: Qt.AlignRight | Qt.AlignVCenter }
                        MField { id: catF; Layout.fillWidth: true; placeholderText: "Utility;" }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    Check {
                        id: rootCk
                        label: page.str.ai_root
                        onToggled: checked = !checked
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.str.ai_root_hint
                        color: Theme.dim
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    Text {
                        text: page.str.ai_update_url
                        color: Theme.text
                        font.pixelSize: 14
                        font.weight: Font.Bold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.str.ai_update_hint + "\n" + page.str.ai_update_hint1 + "\n" + page.str.ai_update_hint2
                        color: Theme.dim
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    MField {
                        id: urlF
                        Layout.fillWidth: true
                        placeholderText: "https://github.com/user/repo  |  https://example.com/latest/App.AppImage"
                    }
                }
            }
            RowLayout {
                spacing: 10
                MButton {
                    text: page.str.ai_save
                    onClicked: {
                        B.saveAppimage(propsPop.a.file, {
                            name: nameF.text.trim() !== "" ? nameF.text.trim() : propsPop.a.name,
                            version: verF.text.trim(),
                            comment: descF.text.trim(),
                            categories: catF.text.trim() !== "" ? catF.text.trim() : "Utility;",
                            updateUrl: urlF.text.trim(),
                            runAsRoot: rootCk.checked
                        })
                        var u = Object.assign({}, page.updates)
                        delete u[propsPop.a.file]
                        page.updates = u
                        propsPop.close()
                    }
                }
                MButton { primary: false; text: page.str.cancel; onClicked: propsPop.close() }
            }
        }
    }

    // ---------- atualização de um AppImage ----------
    Popup {
        id: updPop
        property var a: ({})
        property var info: ({})
        property string phase: "checking"   // checking available uptodate error nosource downloading done failed
        property int pct: -1
        property string msg: ""
        readonly property string statusText: {
            if (phase === "checking") return page.str.ai_checking
            if (phase === "available") return page.str.ai_upd_available
            if (phase === "uptodate") return page.str.ai_upd_uptodate
            if (phase === "error") return page.str.ai_upd_failed + " " + (info.message ? info.message : "")
            if (phase === "nosource") return page.str.ai_no_source
            if (phase === "downloading") return page.str.ai_upd_download
            if (phase === "done") return page.str.ai_upd_done
            return page.str.ai_upd_fail + (msg !== "" ? " " + msg : "")
        }
        function openFor(app) {
            a = app
            info = ({})
            phase = "checking"
            pct = -1
            msg = ""
            open()
            B.checkAppimageUpdate(app.file)
        }
        function gotInfo(i) {
            if (phase === "downloading" || phase === "done") return
            info = i
            phase = page.phaseOf(i)
        }
        function gotState(p, percent, message) {
            phase = p
            pct = percent
            msg = message
        }
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 60)
        modal: true
        focus: true
        padding: 26
        closePolicy: Popup.CloseOnEscape
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle { radius: 22; color: Theme.bg2; border.width: 1; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                text: page.str.ai_upd_title
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
            }
            Text {
                Layout.fillWidth: true
                text: updPop.a.name ? updPop.a.name : ""
                color: Theme.text
                font.pixelSize: 15
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: updPop.statusText
                color: (updPop.phase === "available" || updPop.phase === "done") ? Theme.ok
                       : ((updPop.phase === "error" || updPop.phase === "failed") ? Theme.err : Theme.text)
                font.pixelSize: 14
                font.weight: updPop.phase === "available" ? Font.Bold : Font.Normal
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                visible: updPop.phase === "available" && !!updPop.info.message
                text: updPop.info.message ? updPop.info.message : ""
                color: Theme.dim
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                visible: updPop.phase === "nosource"
                text: page.str.ai_no_source_text
                color: Theme.dim
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            ProgressBarX {
                Layout.fillWidth: true
                implicitHeight: 10
                visible: updPop.phase === "checking" || updPop.phase === "downloading"
                pct: updPop.phase === "downloading" ? updPop.pct : -1
            }
            RowLayout {
                spacing: 10
                MButton {
                    visible: updPop.phase === "available"
                    text: page.str.ai_upd_btn
                    onClicked: {
                        updPop.phase = "downloading"
                        updPop.pct = -1
                        B.updateAppimage(updPop.a.file, updPop.info)
                    }
                }
                MButton {
                    primary: false
                    text: page.str.close
                    onClicked: updPop.close()
                }
            }
        }
    }

    // ---------- procurar todas as atualizações ----------
    Popup {
        id: allPop
        property var files: []
        property var states: ({})
        property var queue: []
        property bool updating: false
        readonly property int checking: {
            var n = 0
            for (var i = 0; i < files.length; i++) {
                var s = states[files[i].file]
                if (!s || s.phase === "checking") n++
            }
            return n
        }
        readonly property int available: {
            var n = 0
            for (var i = 0; i < files.length; i++) {
                var s = states[files[i].file]
                if (s && s.phase === "available") n++
            }
            return n
        }
        function setStatus(file, st) {
            var o = Object.assign({}, states)
            o[file] = st
            states = o
        }
        function openAll() {
            files = page.integratedFiles()
            states = ({})
            queue = []
            updating = false
            var o = {}
            var list = []
            for (var i = 0; i < files.length; i++) {
                o[files[i].file] = { phase: "checking" }
                list.push(files[i].file)
            }
            states = o
            open()
            if (list.length > 0) B.checkAllAppimageUpdates(list)
        }
        function gotInfo(file, info) {
            if (!states[file]) return
            var ph = page.phaseOf(info)
            setStatus(file, { phase: ph, info: info, msg: info.message ? info.message : "" })
        }
        function nextUpdate() {
            if (queue.length === 0) {
                updating = false
                return
            }
            var f = queue[0]
            queue = queue.slice(1)
            var st = states[f]
            setStatus(f, { phase: "updating", info: st.info, pct: -1 })
            B.updateAppimage(f, st.info)
        }
        function updateAll() {
            var q = []
            for (var i = 0; i < files.length; i++) {
                var s = states[files[i].file]
                if (s && s.phase === "available") q.push(files[i].file)
            }
            queue = q
            updating = true
            nextUpdate()
        }
        function gotState(file, phase, percent, message) {
            var st = states[file]
            if (!st || (st.phase !== "updating")) return
            if (phase === "downloading") setStatus(file, { phase: "updating", info: st.info, pct: percent })
            else if (phase === "done") { setStatus(file, { phase: "updated", info: st.info }); nextUpdate() }
            else if (phase === "failed") { setStatus(file, { phase: "failed", info: st.info, msg: message }); nextUpdate() }
        }
        function labelOf(st) {
            if (!st || st.phase === "checking") return page.str.ai_checking
            if (st.phase === "available") return "● " + page.str.ai_available_short
            if (st.phase === "uptodate") return page.str.ai_uptodate_short
            if (st.phase === "nosource") return page.str.ai_no_source
            if (st.phase === "updating") return page.str.ai_updating + (st.pct >= 0 ? " " + st.pct + "%" : "")
            if (st.phase === "updated") return "✓ " + page.str.ai_updated
            if (st.phase === "failed") return page.str.ai_upd_fail
            return String(st.msg ? st.msg : page.str.ai_error).substring(0, 50)
        }
        function colorOf(st) {
            if (!st) return Theme.dim
            if (st.phase === "available" || st.phase === "updated") return Theme.ok
            if (st.phase === "error" || st.phase === "failed") return Theme.err
            if (st.phase === "updating") return Theme.primary
            return Theme.dim
        }
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(620, parent.width - 60)
        modal: true
        focus: true
        padding: 26
        closePolicy: Popup.CloseOnEscape
        Overlay.modal: Rectangle { color: "#b3010f15" }
        background: Rectangle { radius: 22; color: Theme.bg2; border.width: 1; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                text: page.str.ai_all_title
                color: Theme.text
                font.pixelSize: 20
                font.weight: Font.Bold
            }
            Text {
                Layout.fillWidth: true
                text: allPop.files.length === 0 ? page.str.ai_empty
                      : (allPop.checking > 0 ? page.str.ai_checking
                         : (allPop.available > 0 ? allPop.available + " / " + allPop.files.length + "  " + page.str.ai_n_updates
                            : page.str.ai_all_uptodate))
                color: Theme.dim
                font.pixelSize: 14
                wrapMode: Text.WordWrap
            }
            ListView {
                id: allLv
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 300)
                clip: true
                visible: allPop.files.length > 0
                model: allPop.files
                boundsBehavior: Flickable.StopAtBounds
                delegate: Item {
                    width: ListView.view.width
                    height: 40
                    readonly property var st: allPop.states[modelData.file]
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 1
                        color: Theme.border
                    }
                    RowLayout {
                        anchors.fill: parent
                        spacing: 10
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            color: Theme.text
                            font.pixelSize: 14
                            elide: Text.ElideRight
                        }
                        Text {
                            text: allPop.labelOf(st)
                            color: allPop.colorOf(st)
                            font.pixelSize: 13
                        }
                    }
                }
            }
            RowLayout {
                spacing: 10
                MButton {
                    visible: allPop.available > 0 && !allPop.updating
                    text: page.str.update_all
                    onClicked: allPop.updateAll()
                }
                MButton { primary: false; text: page.str.close; onClicked: allPop.close() }
            }
        }
    }
}
