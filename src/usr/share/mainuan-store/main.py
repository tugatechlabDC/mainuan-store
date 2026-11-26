import os
import re
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import (Property, QBuffer, QByteArray, QIODevice, QObject, QSize, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import (QGuiApplication, QIcon, QImage, QImageReader, QPalette, QPixmap)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider

import iconcolor
from backend import Backend, clear_cache, start_tray

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
NAV_DIR = os.path.join(ASSETS, "nav")

DARK = {
    "bg": "#011a27", "bg2": "#02232b", "sidebar": "#010f15",
    "surface": "#032a35", "banner": "#05505f", "raised": "#053744", "border": "#0b4857",
    "primary": "#08e2ea", "primarySoft": "#3aeef3", "primaryDark": "#0399b2",
    "onPrimary": "#012028", "text": "#e8fbfd", "dim": "#8fb8c0",
    "ok": "#3ddc97", "warn": "#ffb454", "err": "#ff7a7a",
}
LIGHT = {
    "bg": "#f2f8fa", "bg2": "#ffffff", "sidebar": "#e2eef1",
    "surface": "#ffffff", "banner": "#c4e8ee", "raised": "#d9ecf0", "border": "#bcd5db",
    "primary": "#02829a", "primarySoft": "#0399b2", "primaryDark": "#3aa5b8",
    "onPrimary": "#ffffff", "text": "#0c2a33", "dim": "#4b6770",
    "ok": "#1c8f5f", "warn": "#b86e00", "err": "#c93a3a",
}


class ThemeObject(QObject):
    """Tema da app: segue automaticamente o modo claro/escuro do sistema."""

    changed = Signal()

    def __init__(self, dark=True):
        super().__init__()
        self._dark = dark
        self._p = DARK if dark else LIGHT

    def set_dark(self, dark):
        if bool(dark) != self._dark:
            self._dark = bool(dark)
            self._p = DARK if self._dark else LIGHT
            self.changed.emit()

    @Property(str, constant=True)
    def assets(self):
        return ASSETS

    @Property(bool, notify=changed)
    def dark(self):
        return self._dark

    @Property(str, notify=changed)
    def bg(self):
        return self._p["bg"]

    @Property(str, notify=changed)
    def bg2(self):
        return self._p["bg2"]

    @Property(str, notify=changed)
    def sidebar(self):
        return self._p["sidebar"]

    @Property(str, notify=changed)
    def surface(self):
        return self._p["surface"]

    @Property(str, notify=changed)
    def banner(self):
        return self._p["banner"]

    @Property(str, notify=changed)
    def raised(self):
        return self._p["raised"]

    @Property(str, notify=changed)
    def border(self):
        return self._p["border"]

    @Property(str, notify=changed)
    def primary(self):
        return self._p["primary"]

    @Property(str, notify=changed)
    def primarySoft(self):
        return self._p["primarySoft"]

    @Property(str, notify=changed)
    def primaryDark(self):
        return self._p["primaryDark"]

    @Property(str, notify=changed)
    def onPrimary(self):
        return self._p["onPrimary"]

    @Property(str, notify=changed)
    def text(self):
        return self._p["text"]

    @Property(str, notify=changed)
    def dim(self):
        return self._p["dim"]

    @Property(str, notify=changed)
    def ok(self):
        return self._p["ok"]

    @Property(str, notify=changed)
    def warn(self):
        return self._p["warn"]

    @Property(str, notify=changed)
    def err(self):
        return self._p["err"]


def system_is_dark(app):
    """Modo escuro do sistema (Qt >= 6.5 diz-o; senão deduz-se da paleta)."""
    scheme_cls = getattr(Qt, "ColorScheme", None)
    getter = getattr(app.styleHints(), "colorScheme", None)
    if scheme_cls is not None and getter is not None:
        try:
            cs = getter()
            if cs == scheme_cls.Dark:
                return True
            if cs == scheme_cls.Light:
                return False
        except Exception:  # noqa: BLE001
            pass
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


class IconProvider(QQuickImageProvider):
    """Serve ícones do tema do sistema e os ícones de navegação da app (SVG com a cor pedida)."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def _nav(self, name, w, h):
        # name = "nav/<icone>/<rrggbb>"
        m = re.fullmatch(r"nav/([a-z]+)/([0-9a-fA-F]{6})", name)
        if not m:
            return QPixmap()
        path = os.path.join(NAV_DIR, m.group(1) + ".svg")
        try:
            with open(path, encoding="utf-8") as f:
                svg = f.read().replace("#COLOR", "#" + m.group(2))
        except OSError:
            return QPixmap()
        data = QByteArray(svg.encode("utf-8"))
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buf, QByteArray(b"svg"))
        reader.setScaledSize(QSize(w, h))
        img = reader.read()
        buf.close()
        if img.isNull():
            return QPixmap()
        return QPixmap.fromImage(img)

    def requestPixmap(self, name, size, requested):
        w = requested.width() if requested.width() > 0 else 64
        h = requested.height() if requested.height() > 0 else 64
        if name.startswith("nav/"):
            return self._nav(name, w, h)
        icon = QIcon(name) if os.path.isabs(name) else QIcon.fromTheme(name)
        if icon.isNull():
            return QPixmap()
        return icon.pixmap(QSize(w, h))


PAGES = {"home": 0, "inicio": 0, "explore": 1, "installed": 3, "updates": 4, "atualizacoes": 4,
         "settings": 5, "about": 6, "appimage": 7}


def parse_args(argv):
    """Devolve (ficheiro, página). Ex.: mainuan-store --page updates | mainuan-store app.deb"""
    page, start, i = -1, "", 0
    while i < len(argv):
        a = argv[i]
        if a in ("--page", "-p") and i + 1 < len(argv):
            page = PAGES.get(argv[i + 1].lower(), page)
            i += 1
        elif a == "--updates":
            page = 4
        elif not start and not a.startswith("-") and os.path.isfile(a):
            start = os.path.abspath(a)
        i += 1
    return start, page


def ipc_name():
    return "mainuan-store-%d" % os.getuid()


def send_to_running(start, page):
    """Se já existe uma Mainuan Store aberta, entrega-lhe o pedido (ficheiro/página) e termina."""
    sock = QLocalSocket()
    sock.connectToServer(ipc_name())
    if not sock.waitForConnected(300):
        return False
    msg = "file\t" + start if start else ("page\t%d" % page if page >= 0 else "show\t")
    sock.write(msg.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(800)
    sock.disconnectFromServer()
    return True


def main():
    start, page = parse_args(sys.argv[1:])
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Mainuan Store")
    app.setDesktopFileName("mainuan-store")
    variant = [iconcolor.detect()]
    app.setWindowIcon(QIcon(iconcolor.svg_path(variant[0])))
    iconcolor.apply_user_icons(variant[0])

    def sync_icon():
        v = iconcolor.detect()
        if v != variant[0]:
            variant[0] = v
            app.setWindowIcon(QIcon(iconcolor.svg_path(v)))
            iconcolor.apply_user_icons(v)
    icon_timer = QTimer()
    icon_timer.setInterval(15000)
    icon_timer.timeout.connect(sync_icon)
    icon_timer.start()

    theme = ThemeObject(system_is_dark(app))

    def refresh_theme(*_args):
        theme.set_dark(system_is_dark(app))

    try:
        app.styleHints().colorSchemeChanged.connect(refresh_theme)
    except AttributeError:
        pass
    try:
        app.paletteChanged.connect(refresh_theme)
    except AttributeError:
        pass
    # rede de segurança: plataformas onde nenhum sinal chega
    poll = QTimer()
    poll.setInterval(3000)
    poll.timeout.connect(refresh_theme)
    poll.start()

    if send_to_running(start, page):
        return
    clear_cache()                  # cada vez que a loja abre, a cache é limpa e volta a ser obtida
    backend = Backend(start)
    backend.set_start_page(page)
    server = QLocalServer()
    QLocalServer.removeServer(ipc_name())
    server.listen(ipc_name())

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            raw = bytes(conn.readAll()).decode("utf-8", "replace")
            cmd, _, arg = raw.partition("\t")
            backend.remoteCommand.emit(cmd, arg)
            conn.disconnectFromServer()
        if conn.bytesAvailable():
            read()
        else:
            conn.readyRead.connect(read)
    server.newConnection.connect(on_connection)
    engine = QQmlApplicationEngine()
    provider = IconProvider()
    engine.addImageProvider("icon", provider)
    ctx = engine.rootContext()
    ctx.setContextProperty("B", backend)
    ctx.setContextProperty("Theme", theme)
    engine.load(QUrl.fromLocalFile(os.path.join(BASE, "qml", "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    QTimer.singleShot(1500, backend.loadUpdates)   # verifica logo as atualizações ao abrir
    if backend.notifyUpdates:
        QTimer.singleShot(4000, start_tray)   # garante o serviço de avisos de atualizações
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
