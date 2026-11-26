"""Ícone da Mainuan Store conforme a cor do sistema.

Há 7 variantes (azul, brow, claro, gray, green, red, rosa). A variante é escolhida pela cor
de destaque do sistema (KDE Plasma: AccentColor / cor de seleção; GNOME: accent-color) e pelo
esquema claro/escuro. Por defeito usa o azul. Pode forçar-se uma variante com o ficheiro
~/.config/mainuan-store/icon-color (conteúdo: o nome da variante, ou "auto").
"""
import colorsys
import configparser
import os
import shutil
import subprocess

HOME = os.path.expanduser("~")
BASE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(BASE, "assets", "app-icons")
VARIANTS = ("azul", "brow", "claro", "gray", "green", "red", "rosa")
DEFAULT = "azul"
SIZES = (16, 22, 24, 32, 48)
STATE = os.path.join(HOME, ".cache", "mainuan-store", "icon-variant")
OVERRIDE = os.path.join(HOME, ".config", "mainuan-store", "icon-color")
USER_HICOLOR = os.path.join(HOME, ".local", "share", "icons", "hicolor")
KDEGLOBALS = os.path.join(HOME, ".config", "kdeglobals")

GNOME = {"blue": "azul", "teal": "azul", "green": "green", "yellow": "brow", "orange": "brow",
         "red": "red", "pink": "rosa", "purple": "rosa", "slate": "gray"}


def svg_path(variant):
    return os.path.join(ICONS, "%s.svg" % (variant if variant in VARIANTS else DEFAULT))


def _rgb(text):
    try:
        r, g, b = [int(float(x)) for x in str(text).split(",")[:3]]
        return r, g, b
    except (ValueError, TypeError):
        return None


def variant_for_rgb(rgb):
    """Variante mais próxima de uma cor (matiz/saturação)."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
    h *= 360
    if s < 0.22 or v < 0.12:
        return "gray"
    if h >= 335 or h < 14:
        return "red"
    if h < 75:
        return "brow"
    if h < 170:
        return "green"
    if h < 262:
        return "azul"
    return "rosa"


def _kde():
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str
    try:
        cfg.read(KDEGLOBALS, encoding="utf-8")
    except (OSError, configparser.Error):
        return None, False
    accent = _rgb(cfg.get("General", "AccentColor", fallback=""))
    if not accent:
        accent = _rgb(cfg.get("Colors:Selection", "BackgroundNormal", fallback=""))
    bg = _rgb(cfg.get("Colors:Window", "BackgroundNormal", fallback=""))
    light = bool(bg) and colorsys.rgb_to_hls(*(c / 255.0 for c in bg))[1] > 0.62
    return accent, light


def _gsettings(key):
    if not shutil.which("gsettings"):
        return ""
    try:
        r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", key],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip().strip("'") if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def detect():
    """Nome da variante do ícone para a cor atual do sistema."""
    try:
        with open(OVERRIDE, encoding="utf-8") as f:
            forced = f.read().strip().lower()
        if forced in VARIANTS:
            return forced
    except OSError:
        pass
    accent, light = _kde()
    variant = variant_for_rgb(accent) if accent else None
    if variant is None:
        name = _gsettings("accent-color")
        if name in GNOME:
            variant = GNOME[name]
            light = _gsettings("color-scheme") == "default" and light
        else:
            variant = DEFAULT
    if light and variant in ("azul", "gray"):
        return "claro"          # tema claro com destaque azul/neutro
    return variant


def _emit_icon_changed():
    if shutil.which("gdbus"):
        try:
            subprocess.run(["gdbus", "emit", "--session", "--object-path", "/KIconLoader",
                            "--signal", "org.kde.KIconLoader.iconChanged", "0"],
                           capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass


def apply_user_icons(variant):
    """Põe o ícone da variante em ~/.local/share/icons (tem prioridade sobre o do sistema), para
    o menu, o lançador e a barra de tarefas mostrarem a cor certa. O azul remove o override."""
    try:
        with open(STATE, encoding="utf-8") as f:
            if f.read().strip() == variant:
                return False
    except OSError:
        pass
    targets = [("scalable", "mainuan-store.svg", svg_path(variant))]
    for s in SIZES:
        targets.append(("%dx%d" % (s, s), "mainuan-store.png", os.path.join(ICONS, "%s-%d.png" % (variant, s))))
    for sub, name, src in targets:
        dest_dir = os.path.join(USER_HICOLOR, sub, "apps")
        dest = os.path.join(dest_dir, name)
        try:
            if variant == DEFAULT:
                if os.path.exists(dest):
                    os.remove(dest)
            else:
                os.makedirs(dest_dir, exist_ok=True)
                tmp = dest + ".tmp"
                shutil.copyfile(src, tmp)
                os.replace(tmp, dest)
        except OSError:
            pass
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as f:
            f.write(variant)
    except OSError:
        pass
    _emit_icon_changed()
    return True
