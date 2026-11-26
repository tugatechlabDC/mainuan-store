"""Notificações do sistema (org.freedesktop.Notifications) via gdbus.

A notificação de atualizações fica visível até as atualizações terminarem: guarda-se o
identificador devolvido pelo serviço de notificações para a poder fechar de imediato
(CloseNotification) quando já não há atualizações pendentes. Funciona a partir de qualquer
processo da loja (janela ou serviço do tabuleiro).
"""
import os
import re
import shutil
import subprocess

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "mainuan-store")
ID_FILE = os.path.join(CACHE_DIR, "notify-id")
DEST = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"


def available():
    return bool(shutil.which("gdbus"))


def _call(method, *args):
    cmd = ["gdbus", "call", "--session", "--dest", DEST, "--object-path", PATH,
           "--method", DEST + "." + method, *map(str, args)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def load_id():
    try:
        with open(ID_FILE, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _save_id(n):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(int(n)))
    except OSError:
        pass


def _q(text):
    """Texto entre aspas para o formato GVariant do gdbus."""
    return "'" + str(text).replace("\\", "\\\\").replace("'", "\\'") + "'"


def show(summary, body, action_label="Open", icon="mainuan-store"):
    """Mostra (ou substitui) a notificação; fica até ser fechada. Devolve o id ou 0."""
    if not available():
        return 0
    out = _call("Notify", "Mainuan Store", load_id(), icon, summary, body,
                "['default', %s]" % _q(action_label),
                "{'desktop-entry': <'mainuan-store'>}", 0)
    m = re.search(r"uint32\s+(\d+)", out)
    if not m:
        return 0
    _save_id(m.group(1))
    return int(m.group(1))


def close_saved():
    """Fecha a notificação de atualizações, se existir."""
    n = load_id()
    if n and available():
        _call("CloseNotification", n)
    try:
        os.remove(ID_FILE)
    except OSError:
        pass


def parse_action(line, wanted):
    """True se a linha do `gdbus monitor` for a ação `default` da notificação `wanted`."""
    m = re.search(r"ActionInvoked \(uint32 (\d+), '([^']*)'\)", line)
    return bool(m) and int(m.group(1)) == wanted and m.group(2) == "default"
