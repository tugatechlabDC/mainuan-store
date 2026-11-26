"""Mainuan Store - serviço de avisos de atualizações (ícone na área de notificações).

Corre em segundo plano (arranca com a sessão, ver /etc/xdg/autostart/mainuan-store-updates.desktop),
procura atualizações de APT/sistema, Flatpak e AppImage e mostra um ícone com o número de
atualizações disponíveis. Ao clicar no ícone (ou na notificação) abre a Mainuan Store no menu
Atualizações.
"""
import json
import os
import socket
import sys
import threading

from PySide6.QtCore import QDir, QFileSystemWatcher, QLockFile, QObject, QProcess, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import backend as be
import iconcolor
import notifier
from strings import EN, STRINGS

ASSETS = os.path.join(be.BASE, "assets")
FIRST_CHECK_MS = 3 * 1000               # 1.º controlo, logo que a sessão arranca
RETRY_MS = 15 * 1000                    # sem rede ainda: tenta de novo a cada 15 s
MAX_RETRIES = 40                        # (até ~10 minutos)
ICON_POLL_MS = 20 * 1000                # cor do sistema (ícone da loja)
INTERVAL_MS = 3 * 60 * 60 * 1000        # depois, de 3 em 3 horas
NOTIFIED = os.path.join(be.CACHE_DIR, "notified.json")
UPDATES = os.path.join(be.CACHE_DIR, "updates.json")


def tr(key, **kw):
    text = STRINGS.get(be.detect_lang(), {}).get(key) or EN.get(key, key)
    return text.format(**kw) if kw else text


def make_icon(n):
    """Logo da loja com um círculo vermelho e o número de atualizações."""
    icon = QIcon()
    base_icon = QIcon(iconcolor.svg_path(iconcolor.detect()))
    text = "99+" if n > 99 else str(n)
    for size in (22, 32, 48, 64, 128):
        pm = base_icon.pixmap(size, size)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = size * 0.58
        w = d if len(text) == 1 else d * (0.62 + 0.38 * len(text))
        rect = QRectF(size - w - 0.5, size - d - 0.5, w, d)
        p.setPen(QPen(QColor("#ffffff"), max(1.0, size / 28.0)))
        p.setBrush(QColor("#e53935"))
        p.drawRoundedRect(rect, d / 2, d / 2)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(7, int(d * (0.64 if len(text) == 1 else 0.5))))
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        icon.addPixmap(pm)
    return icon


def online():
    for host in ("api.github.com", "deb.debian.org", "1.1.1.1"):
        try:
            socket.create_connection((host, 443), 3).close()
            return True
        except OSError:
            continue
    return False


class Tray(QObject):
    resultReady = Signal(list)
    retryRequested = Signal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.backend = be.Backend("")
        self.settings = QSettings("Mainuan", "MainuanStore")
        self.items = []
        self.checking = False
        self.tray = QSystemTrayIcon()
        self.tray.activated.connect(self.on_activated)
        self.tray.messageClicked.connect(self.open_store)
        self.menu = QMenu()
        self.act_open = self.menu.addAction("")
        self.act_check = self.menu.addAction("")
        self.menu.addSeparator()
        self.act_quit = self.menu.addAction("")
        self.act_open.triggered.connect(self.open_store)
        self.act_check.triggered.connect(self.check)
        self.act_quit.triggered.connect(self.app.quit)
        self.tray.setContextMenu(self.menu)
        self.resultReady.connect(lambda items: self.apply(items, True))
        self.retryRequested.connect(self.retry_later)
        self.timer = QTimer(self)
        self.timer.setInterval(INTERVAL_MS)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        self.retries = 0
        QTimer.singleShot(FIRST_CHECK_MS, self.check)
        # ícone da loja conforme a cor do sistema (menu/lançador e tabuleiro)
        self.variant = ""
        self.icon_timer = QTimer(self)
        self.icon_timer.setInterval(ICON_POLL_MS)
        self.icon_timer.timeout.connect(self.sync_icon)
        self.icon_timer.start()
        self.icon_watch = QFileSystemWatcher([p for p in (iconcolor.KDEGLOBALS, os.path.dirname(iconcolor.KDEGLOBALS)) if os.path.exists(p)])
        self.icon_watch.fileChanged.connect(self.sync_icon)
        self.icon_watch.directoryChanged.connect(self.sync_icon)
        QTimer.singleShot(500, self.sync_icon)
        # clique na notificação do sistema -> abrir a loja nas atualizações
        self.nid = 0
        self.mon = None
        self.start_monitor()
        # a loja (janela) atualiza este ficheiro quando procura/aplica atualizações
        os.makedirs(be.CACHE_DIR, exist_ok=True)
        self.watch = QFileSystemWatcher([be.CACHE_DIR])
        self.watch.directoryChanged.connect(self.load_cache)
        self._cache_mtime = 0
        self.load_cache()

    # ----- definições -----
    def enabled(self):
        self.settings.sync()
        v = self.settings.value("notifyUpdates", None)
        return True if v is None else str(v).lower() in ("true", "1")

    # ----- verificação -----
    def check(self):
        if not self.enabled():
            self.tray.hide()
            return
        if self.checking:
            return
        self.checking = True

        def job():
            try:
                if not online():                 # no arranque a rede pode ainda não estar pronta
                    self.checking = False
                    if self.retries < MAX_RETRIES:
                        self.retries += 1
                        self.retryRequested.emit()
                    return
                self.retries = 0
                items = self.backend.collect_updates()
            except Exception:  # noqa: BLE001
                items = None
            self.checking = False
            if items is not None:
                self.resultReady.emit(items)
        threading.Thread(target=job, daemon=True).start()

    def retry_later(self):
        QTimer.singleShot(RETRY_MS, self.check)

    def load_cache(self, *_):
        try:
            mt = os.path.getmtime(UPDATES)
            if mt == self._cache_mtime:
                return
            self._cache_mtime = mt
            with open(UPDATES, encoding="utf-8") as f:
                data = json.load(f)
            self.apply(list(data.get("items", [])), False)
        except (OSError, ValueError):
            pass

    # ----- apresentação -----
    def apply(self, items, notify):
        self.items = items
        n = len(items)
        self.act_open.setText(tr("tray_open"))
        self.act_check.setText(tr("tray_check"))
        self.act_quit.setText(tr("tray_quit"))
        if n == 0 or not self.enabled():
            self.tray.hide()
            self.save_notified([])
            notifier.close_saved()               # as atualizações terminaram: a notificação desaparece já
            self.nid = 0
            return
        title = tr("tray_one") if n == 1 else tr("tray_many", n=n)
        self.tray.setIcon(make_icon(n))
        self.tray.setToolTip("Mainuan Store\n" + title)
        self.tray.show()
        ids = [i.get("id", "") for i in items]
        old = self.load_notified()
        new = [i for i in items if i.get("id", "") not in old]
        if notify and new:
            names = [i.get("name", "") for i in items][:4]
            body = ", ".join(names) + ("…" if n > 4 else "")
            nid = notifier.show(title, body, tr("tray_open"))
            if nid:
                self.nid = nid
            else:
                self.tray.showMessage(title, body, make_icon(n), 15000)
        if notify or not old:
            self.save_notified(ids)

    @staticmethod
    def load_notified():
        try:
            with open(NOTIFIED, encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, ValueError):
            return set()

    @staticmethod
    def save_notified(ids):
        try:
            with open(NOTIFIED, "w", encoding="utf-8") as f:
                json.dump(list(ids), f)
        except OSError:
            pass

    # ----- ícone da loja (cor do sistema) -----
    def sync_icon(self, *_):
        v = iconcolor.detect()
        if v != self.variant:
            self.variant = v
            iconcolor.apply_user_icons(v)
            if self.items:
                self.tray.setIcon(make_icon(len(self.items)))
        for p in (iconcolor.KDEGLOBALS,):          # o ficheiro é recriado ao gravar: voltar a observá-lo
            if os.path.exists(p) and p not in self.icon_watch.files():
                self.icon_watch.addPath(p)

    # ----- clique na notificação -----
    def start_monitor(self):
        if not notifier.available():
            return
        self.mon = QProcess(self)
        self.mon.readyReadStandardOutput.connect(self.on_monitor)
        self.mon.start("gdbus", ["monitor", "--session", "--dest", notifier.DEST, "--object-path", notifier.PATH])

    def on_monitor(self):
        data = bytes(self.mon.readAllStandardOutput()).decode("utf-8", "ignore")
        wanted = notifier.load_id()
        for line in data.splitlines():
            if wanted and notifier.parse_action(line, wanted):
                self.open_store()

    # ----- ações -----
    def on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.MiddleClick):
            self.open_store()

    @staticmethod
    def open_store():
        QProcess.startDetached("mainuan-store", ["--page", "updates"])


def main():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Mainuan Store Updates")
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(os.path.join(QDir.tempPath(), "mainuan-store-tray-%d.lock" % os.getuid()))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return 0            # já está a correr
    tray = Tray(app)        # noqa: F841 (mantém referência)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
