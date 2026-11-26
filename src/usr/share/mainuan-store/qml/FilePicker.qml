import QtQuick
import QtQuick.Dialogs

FileDialog {
    signal picked(string url)
    property string kind: "deb"
    title: kind === "deb" ? B.strings.choose_deb : B.strings.choose_appimage
    nameFilters: kind === "deb" ? ["DEB (*.deb)"] : ["AppImage (*.AppImage *.appimage)"]
    onAccepted: picked(selectedFile.toString())
}
