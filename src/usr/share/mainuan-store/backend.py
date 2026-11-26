import configparser
import glob
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from PySide6.QtCore import Property, QObject, QSettings, QUrl, Signal, Slot

import appimage_core as AI
import notifier
from strings import EN, STRINGS

APP_VERSION = "0.7.0"
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
DEB_DIR = os.path.join(BASE, "debs")
ICON_DIR = os.path.join(BASE, "assets", "icons")
BANNER_DIR = os.path.join(BASE, "banners")
BANNER_EXT = (".jpg", ".jpeg", ".png", ".webp")
GH_TTL = 3 * 3600                 # as releases GitHub das apps Mainuan são consultadas de 3 em 3 horas
HELPER = os.path.join(BASE, "helper.py")
HOME = os.path.expanduser("~")
APPIMG_DIR = str(AI.APPIMAGES_DIR)
APPIMG_INDEX = os.path.join(HOME, ".local", "share", "mainuan-store", "appimages.json")
DESKTOP_DIR = os.path.join(HOME, ".local", "share", "applications")
CACHE_DIR = os.path.join(HOME, ".cache", "mainuan-store")
GH_CACHE = os.path.join(CACHE_DIR, "releases.json")
FEED_FILE = os.path.join(CACHE_DIR, "appimage-feed.json")
FEED_URL = "https://appimage.github.io/feed.json"
FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
UA = {"User-Agent": "MainuanStore/" + APP_VERSION}
ENV = dict(os.environ, LC_ALL="C")
PROTECTED = {"mainuan-store"}
SKIP_SUFFIX = ("-dev", "-dbg", "-dbgsym", "-doc", "-data", "-common", "-l10n", "-locale")
PKEXEC_APT = ["pkexec", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get"]
APT_OPTS = ["-o", "APT::Status-Fd=1", "-o", "Dpkg::Use-Pty=0"]


def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=ENV)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


SELF_APP = {"name": "Mainuan Store", "package": "mainuan-store", "repo": "mainuan/mainuan-store",
            "iconName": "mainuan-store"}


def clear_cache():
    """Limpa a cache da loja (catálogos, releases, feeds, traduções, transferências parciais).
    Mantém só o estado das notificações; a loja volta a obter tudo de novo ao abrir."""
    keep = {"notified.json", "notify-id", "updates.json", "errors.log", "icon-variant"}
    try:
        names = os.listdir(CACHE_DIR)
    except OSError:
        return
    for name in names:
        if name in keep:
            continue
        path = os.path.join(CACHE_DIR, name)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError:
            pass


def read_json(name):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def norm_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "app"


def fmt_size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" if unit in ("B", "KB") else "%.1f %s") % (n, unit)
        n /= 1024.0
    return ""


def gh_repo(links):
    for link in links or []:
        url = link.get("url", "") if isinstance(link, dict) else str(link)
        m = re.search(r"github\.com/([\w.-]+/[\w.-]+)", url)
        if m:
            return re.sub(r"\.git$", "", m.group(1))
        if isinstance(link, dict) and link.get("type") == "GitHub" and re.fullmatch(r"[\w.-]+/[\w.-]+", url):
            return url
    return ""


def _entries(raw):
    """Entradas de uma lista de locales (ex.: "pt_BR:pt:en", "pt-BR", "pt_br.UTF-8")."""
    out = []
    for e in (raw or "").split(":"):
        e = e.strip().split(".")[0].split("@")[0].replace("-", "_")
        if e and e not in ("C", "POSIX"):
            out.append(e)
    return out


def _code_of(entry):
    """Código de idioma da app para uma entrada; "pt" sem região devolve "pt"."""
    low = entry.lower()
    if low == "pt":
        return "pt"
    if low.startswith("pt_"):
        return "pt_BR" if low[3:5] == "br" else "pt_PT"
    for pre in ("fr", "es"):
        if low == pre or low.startswith(pre + "_"):
            return pre
    return "en" if low else ""


def _lang_code(raw):
    for e in _entries(raw):
        code = _code_of(e)
        if code and code != "pt":
            return code
        if code == "pt":
            return "pt_PT"
    return ""


def _conf_value(path, keys):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.strip() in keys and v.strip():
                    return v.strip().strip('"')
    except OSError:
        pass
    return ""


def _pt_region(sources):
    """"pt" sem região: procura "pt_BR" noutras fontes; senão usa o fuso horário."""
    for raw in sources:
        for e in _entries(raw):
            if e.lower().startswith("pt_"):
                return "pt_BR" if e[3:5].lower() == "br" else "pt_PT"
    try:
        with open("/etc/timezone", encoding="utf-8") as f:
            tz = f.read().strip()
    except OSError:
        tz = os.path.realpath("/etc/localtime")
    if tz.startswith("America/") or "/America/" in tz:
        return "pt_BR"
    return "pt_PT"


def detect_lang():
    """Idioma do sistema (variáveis de ambiente da sessão; depois ficheiros de configuração
    do KDE/Ubuntu e, por fim, o locale do Qt). Percorre TODAS as entradas de LANGUAGE
    (ex.: "pt_BR:pt:en") e distingue pt_BR de pt_PT. Devolve um código existente em STRINGS."""
    sources = [os.environ.get(v, "") for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")]
    sources += [_conf_value(os.path.join(HOME, ".config", "plasma-localerc"), ("LANGUAGE",)),
                _conf_value(os.path.join(HOME, ".config", "plasma-localerc"), ("LANG",)),
                _conf_value("/etc/default/locale", ("LANG", "LC_MESSAGES")),
                _conf_value("/etc/locale.conf", ("LANG", "LC_MESSAGES"))]
    try:
        from PySide6.QtCore import QLocale
        sources.append(QLocale.system().name())
        sources += list(QLocale.system().uiLanguages())
    except Exception:  # noqa: BLE001
        pass
    for raw in sources:
        for e in _entries(raw):
            code = _code_of(e)
            if code == "pt":
                return _pt_region(sources)
            if code:
                return code
    return "en"


def parse_desktop(path, lang):
    pre = lang.split("_")[0]
    d = {"name": "", "loc": "", "icon": "", "comment": "", "hidden": False}
    in_entry = False
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    in_entry = line == "[Desktop Entry]"
                    continue
                if not in_entry or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k == "Name":
                    d["name"] = v
                elif k in ("Name[%s]" % lang, "Name[%s]" % pre) and not d["loc"]:
                    d["loc"] = v
                elif k == "Icon":
                    d["icon"] = v
                elif k == "Comment":
                    d["comment"] = v
                elif k in ("NoDisplay", "Hidden") and v.lower() == "true":
                    d["hidden"] = True
    except Exception:  # noqa: BLE001
        pass
    return d


def parse_apt_sources():
    out = []
    for path in sorted(glob.glob("/etc/apt/sources.list.d/*.sources")):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except Exception:  # noqa: BLE001
            continue
        for idx, st in enumerate(re.split(r"\n\s*\n", text.strip("\n"))):
            fields, last = {}, None
            for line in st.split("\n"):
                if not line.strip() or line.startswith("#"):
                    continue
                if line[0] in " \t" and last:
                    fields[last] += " " + line.strip()
                elif ":" in line:
                    k, _, v = line.partition(":")
                    last = k.strip().lower()
                    fields[last] = v.strip()
            uris = fields.get("uris")
            if not uris:
                continue
            host = re.sub(r"^[a-z+]+://", "", uris.split()[0]).rstrip("/")
            label = "%s - %s (%s)" % (host, fields.get("suites", ""), fields.get("components", ""))
            out.append({"file": path, "index": idx, "label": label.replace(" ()", ""),
                        "enabled": fields.get("enabled", "yes").lower() != "no"})
    files = sorted(glob.glob("/etc/apt/sources.list.d/*.list"))
    if os.path.isfile("/etc/apt/sources.list"):
        files.append("/etc/apt/sources.list")
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().split("\n")
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(lines):
            m = re.match(r"^\s*(#\s*)?(deb\s+.*)$", line)
            if not m:
                continue
            toks = m.group(2).split()[1:]
            if toks and toks[0].startswith("["):
                while toks and not toks[0].endswith("]"):
                    toks.pop(0)
                toks = toks[1:]
            if len(toks) < 2:
                continue
            host = re.sub(r"^[a-z+]+://", "", toks[0]).rstrip("/")
            out.append({"file": path, "index": i,
                        "label": "%s - %s (%s)" % (host, toks[1], " ".join(toks[2:])),
                        "enabled": not m.group(1)})
    return out


INDEX_FILE = os.path.join(CACHE_DIR, "catalog-index.json")
CAT_PRIORITY = [("Accessibility", "accessibility"), ("Game", "games"), ("Development", "dev"),
                ("Graphics", "graphics"), ("AudioVideo", "media"), ("Audio", "media"), ("Video", "media"),
                ("Office", "office"), ("Education", "education"), ("Science", "education"),
                ("Network", "internet"), ("System", "system"), ("Settings", "system"), ("Utility", "utils")]
KEEP_LANGS = ("pt", "pt_BR", "pt_PT", "fr", "es")
ICON_ROOTS = ["/var/lib/swcatalog/icons", "/usr/share/swcatalog/icons",
              "/var/lib/app-info/icons", "/usr/share/app-info/icons"]
XMLLANG = "{http://www.w3.org/XML/1998/namespace}lang"


def map_category(cats, ctype, extends):
    if ctype == "font":
        return "fonts"
    if ctype == "addon":
        return "plasma" if any("plasma" in str(x).lower() for x in extends or []) else "addons"
    have = set(cats or [])
    for key, val in CAT_PRIORITY:
        if key in have:
            return val
    return ""


def loc_dict(v):
    if isinstance(v, str):
        return {"C": v}
    if isinstance(v, dict):
        return {str(k): str(x) for k, x in v.items() if k == "C" or k in KEEP_LANGS}
    return {}


def find_dep11_icon(origin, name):
    for root in ICON_ROOTS:
        for size in ("64x64", "128x128"):
            path = os.path.join(root, origin, size, name)
            if os.path.isfile(path):
                return path
    return ""


def read_dep11(path):
    """Catálogo AppStream do APT (formato DEP-11, YAML)."""
    import yaml
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    origin = ""
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
        for doc in yaml.load_all(f, Loader=loader):
            if not isinstance(doc, dict):
                continue
            if "File" in doc:
                origin = str(doc.get("Origin", ""))
                continue
            ctype = doc.get("Type")
            names = loc_dict(doc.get("Name"))
            if ctype not in ("desktop-application", "addon", "font") or not doc.get("Package") or not names:
                continue
            icon = doc.get("Icon") or {}
            ifile = ""
            for c in icon.get("cached") or []:
                if isinstance(c, dict) and c.get("name"):
                    ifile = find_dep11_icon(origin, str(c["name"]))
                    if ifile:
                        break
            yield {"names": names, "sums": loc_dict(doc.get("Summary")),
                   "category": map_category(doc.get("Categories"), ctype, doc.get("Extends")),
                   "source": "apt", "pkg": str(doc["Package"]),
                   "iconName": str(icon.get("stock") or ""), "iconFile": ifile}


def read_flatpak_xml(path):
    """Catálogo AppStream de um remoto Flatpak (XML)."""
    base = os.path.dirname(path)

    def locs(el, tag):
        out = {}
        for n in el.findall(tag):
            lang = (n.get(XMLLANG) or "C").replace("-", "_")
            if (lang == "C" or lang in KEEP_LANGS) and (n.text or "").strip():
                out[lang] = n.text.strip()
        return out
    with gzip.open(path, "rb") as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag != "component":
                continue
            try:
                if el.get("type") in ("desktop-application", "desktop"):
                    cid = (el.findtext("id") or "").strip()
                    if cid.endswith(".desktop"):
                        cid = cid[:-8]
                    names = locs(el, "name")
                    if cid and names:
                        cats = [c.text for c in el.findall("categories/category") if c.text]
                        ifile = ""
                        for ic in el.findall("icon"):
                            if ic.get("type") == "cached" and ic.text:
                                for size in ("64x64", "128x128"):
                                    cand = os.path.join(base, "icons", size, ic.text.strip())
                                    if os.path.isfile(cand):
                                        ifile = cand
                                        break
                                if ifile:
                                    break
                        yield {"names": names, "sums": locs(el, "summary"), "category": map_category(cats, "", []),
                               "source": "flatpak", "pkg": cid, "iconName": "", "iconFile": ifile}
            finally:
                el.clear()


def start_tray():
    """Arranca (se ainda não estiver a correr) o serviço que avisa de atualizações."""
    try:
        subprocess.Popen(["mainuan-store-tray"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


class Backend(QObject):
    langChanged = Signal()
    sideChanged = Signal()
    revChanged = Signal()
    prefsChanged = Signal()
    listReady = Signal(str, list, arguments=["kind", "items"])
    detailsReady = Signal(dict, arguments=["info"])
    shotsReady = Signal(str, list, arguments=["id", "urls"])
    sourcesReady = Signal(dict, arguments=["data"])
    fileInfo = Signal(dict, arguments=["info"])
    opStarted = Signal(str, str, arguments=["key", "name"])
    opProgress = Signal(str, int, arguments=["key", "percent"])
    opFinished = Signal(str, bool, str, arguments=["key", "ok", "message"])
    itemState = Signal(str, str, int, arguments=["id", "phase", "percent"])
    indexBuilding = Signal(bool, arguments=["building"])
    bannersChanged = Signal()
    remoteCommand = Signal(str, str, arguments=["cmd", "arg"])
    appimagesReady = Signal(list, arguments=["items"])
    appimageBusy = Signal(bool, str, int, arguments=["busy", "text", "percent"])
    appimageResult = Signal(str, bool, str, str, arguments=["kind", "ok", "message", "file"])
    appimageUpdateInfo = Signal(str, dict, arguments=["file", "info"])
    appimageUpdateState = Signal(str, str, int, str, arguments=["file", "phase", "percent", "message"])

    def __init__(self, start_file=""):
        super().__init__()
        self._start = start_file
        self._settings = QSettings("Mainuan", "MainuanStore")
        self._lang = detect_lang()   # idioma da app = idioma do sistema (automático)
        self._default = str(self._settings.value("defaultSource", "apt"))
        if self._default not in ("apt", "flatpak", "appimage"):
            self._default = "apt"
        self._ai_on = self._get_bool("appimageOn", True)
        self._side = self._get_bool("sideExpanded", False)
        self._tr_lock = threading.Lock()
        self._tr_cache = None
        self._rev = 0
        self._inst = {"apt": set(), "flatpak": set(), "appimage": set()}
        self._flat_inst = {}
        self._flat_list = []
        self._flat_ok = True
        self._fw_ok = False
        self._feed_cache = None
        self._shots_cache = {}
        self._last_updates = []
        self._ai_upd = {}
        self._banners = []
        self._start_page = -1
        self._reload_banners(False)
        self._featured = read_json("apps.json")
        self._resolve_aliases()
        self._gh_apps = list(self._featured) + [SELF_APP]      # a loja também se atualiza pelo GitHub
        self._catalog = read_json("catalog.json")
        self._tl = threading.local()
        self._procs = {}
        self._cancel = set()
        self._index = None
        self._index_lock = threading.Lock()
        self._index_started = False
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
        except OSError:
            pass

    def _get_bool(self, key, default):
        v = self._settings.value(key, None)
        return default if v is None else str(v).lower() in ("true", "1")

    # ----- propriedades -----
    @Property("QVariantMap", notify=langChanged)
    def strings(self):
        merged = dict(EN)
        merged.update(STRINGS.get(self._lang, {}))
        return merged

    @Property(str, notify=langChanged)
    def lang(self):
        return self._lang

    @Property("QVariantList", notify=bannersChanged)
    def banners(self):
        return self._banners

    def _reload_banners(self, emit=True):
        """Banners de publicidade: imagens na pasta banners/ (ver banners/LEIA-ME.txt)."""
        out = []
        cfg = {}
        try:
            with open(os.path.join(BANNER_DIR, "banners.json"), encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                cfg = {}
        except (OSError, ValueError):
            cfg = {}
        today = time.strftime("%Y-%m-%d")
        try:
            names = sorted(os.listdir(BANNER_DIR), key=lambda n: n.lower())
        except OSError:
            names = []
        for fn in names:
            full = os.path.join(BANNER_DIR, fn)
            if fn.startswith(("_", ".")) or not fn.lower().endswith(BANNER_EXT) or not os.path.isfile(full):
                continue
            c = cfg.get(fn) if isinstance(cfg.get(fn), dict) else {}
            if c.get("enabled") is False:
                continue
            if str(c.get("from", "")) > today or (c.get("until") and str(c.get("until")) < today):
                continue
            url = str(c.get("url", "")).strip()
            out.append({"src": QUrl.fromLocalFile(full).toString(), "url": url if url.startswith(("http://", "https://")) else "",
                        "title": str(c.get("title", "")), "file": fn})
        if out != self._banners:
            self._banners = out
            if emit:
                self.bannersChanged.emit()

    @Slot()
    def reloadBanners(self):
        self._reload_banners()

    @Slot(str)
    def openBanner(self, url):
        if str(url).startswith(("http://", "https://")):
            try:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            except OSError:
                pass

    @Property(int, constant=True)
    def startPage(self):
        return self._start_page

    def set_start_page(self, page):
        self._start_page = int(page)

    @Property(bool, notify=prefsChanged)
    def notifyUpdates(self):
        return self._get_bool("notifyUpdates", True)

    @Slot(bool)
    def setNotifyUpdates(self, on):
        self._settings.setValue("notifyUpdates", bool(on))
        self._settings.sync()
        self.prefsChanged.emit()
        if on:
            start_tray()

    @Property(int, notify=revChanged)
    def rev(self):
        return self._rev

    @Property(str, constant=True)
    def appVersion(self):
        return APP_VERSION

    @Property(str, constant=True)
    def startFile(self):
        return self._start

    @Property(str, notify=prefsChanged)
    def defaultSource(self):
        return self._default

    @Slot()
    def syncLang(self):
        """O idioma da app acompanha sempre o idioma do sistema."""
        code = detect_lang()
        if code != self._lang:
            self._lang = code
            self.langChanged.emit()

    @Property(bool, notify=sideChanged)
    def sideExpanded(self):
        return self._side

    @Slot(bool)
    def setSideExpanded(self, on):
        self._side = bool(on)
        self._settings.setValue("sideExpanded", bool(on))
        self.sideChanged.emit()

    @Slot(str)
    def setDefaultSource(self, src):
        self._default = src
        self._settings.setValue("defaultSource", src)
        self.prefsChanged.emit()

    @Slot(bool)
    def setAppimage(self, on):
        self._ai_on = bool(on)
        self._settings.setValue("appimageOn", bool(on))
        self.prefsChanged.emit()

    @Slot(str, str, result=bool)
    def isInstalled(self, source, pkg):
        key = "apt" if source in ("apt", "deb") else source
        return pkg in self._inst.get(key, set())

    # ----- utilitários -----
    def _bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _loc(self, value):
        if isinstance(value, str):
            return value
        if not isinstance(value, dict):
            return ""
        return (value.get(self._lang) or value.get(self._lang.split("_")[0]) or value.get("en") or value.get("C") or "")

    @staticmethod
    def _variant(source, pkg, **kw):
        d = {"source": source, "pkg": pkg, "version": "", "size": "", "available": True, "file": "", "repo": ""}
        d.update(kw)
        return d

    @staticmethod
    def _item(name, summary="", variants=None, category="", icon="", description="", origin=""):
        variants = variants or []
        key = norm_key(name) or norm_key(variants[0]["pkg"] if variants else "app")
        return {"id": "app:" + key, "name": name, "summary": summary, "description": description,
                "iconName": icon or re.sub(r"\s+", "-", name.lower()), "iconFile": "",
                "category": category, "variants": variants, "origin": origin}

    @staticmethod
    def _merge(items):
        out, order = {}, []
        for it in items:
            k = it["id"]
            if k in out:
                cur = out[k]
                have = {(v["source"], v["pkg"]) for v in cur["variants"]}
                for v in it["variants"]:
                    if (v["source"], v["pkg"]) not in have:
                        cur["variants"].append(v)
                for f in ("summary", "description", "category"):
                    if not cur.get(f) and it.get(f):
                        cur[f] = it[f]
            else:
                out[k] = it
                order.append(k)
        return [out[k] for k in order]

    def _src_ok(self, src):
        if src in ("apt", "deb"):
            return True
        if src == "flatpak":
            return bool(shutil.which("flatpak")) and self._flat_ok
        if src == "appimage":
            return self._ai_on
        return True

    @staticmethod
    def _tail(rc, lines):
        if rc in (126, 127):
            return "cancelled"
        if rc == 0:
            return ""
        keep = [l for l in lines if "%" not in l][-2:]
        return " ".join(keep)[:240]

    @staticmethod
    def _log_error(cmd, lines, rc):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(os.path.join(CACHE_DIR, "errors.log"), "a", encoding="utf-8") as f:
                f.write("%s rc=%s\n$ %s\n%s\n\n" % (time.strftime("%F %T"), rc, " ".join(cmd), "\n".join(lines[-30:])))
        except Exception:  # noqa: BLE001
            pass

    def _stream(self, cmd, cb, mode, hook=None):
        """Corre um comando e converte a saída em percentagens (0-100) para cb.
        hook(kind, pkg, pct, msg) recebe os detalhes (kind 'dl'/'pm' em apt)."""
        tail = []
        key = getattr(self._tl, "key", None)
        if key and key in self._cancel:
            return 130, "cancelled"
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV)
        except Exception as exc:  # noqa: BLE001
            return 1, str(exc)
        if key:
            self._procs[key] = p

        def handle(raw):
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                return
            if mode == "apt" and (line.startswith("dlstatus:") or line.startswith("pmstatus:")):
                parts = line.split(":", 3)
                try:
                    pct = float(parts[2])
                except (IndexError, ValueError):
                    return
                dl = line[0] == "d"
                cb(pct * 0.4 if dl else 40 + pct * 0.6)
                if hook:
                    hook("dl" if dl else "pm", parts[1], pct, parts[3] if len(parts) > 3 else "")
                return
            if mode != "apt":
                found = re.findall(r"(\d{1,3})%", line)
                if found:
                    pct = min(100, int(found[-1]))
                    cb(pct)
                    if hook:
                        hook(None, "", pct, "")
            tail.append(line)

        buf = b""
        while True:
            chunk = p.stdout.read1(512)
            if not chunk:
                break
            buf += chunk
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for part in parts:
                handle(part)
        if buf:
            handle(buf)
        p.wait()
        if key and key in self._cancel:
            return p.returncode, "cancelled"
        if p.returncode not in (0, 126, 127):
            self._log_error(cmd, tail, p.returncode)
        return p.returncode, self._tail(p.returncode, tail)

    # ----- estado instalado / fontes -----
    def _ai_load(self):
        try:
            with open(APPIMG_INDEX, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _ai_save(self, data):
        os.makedirs(os.path.dirname(APPIMG_INDEX), exist_ok=True)
        with open(APPIMG_INDEX, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    def _refresh_installed(self):
        apt, flat, scope = set(), set(), {}
        rc, out, _ = run(["dpkg-query", "-W", "-f=${Package}\t${db:Status-Abbrev}\n"])
        for line in out.splitlines():
            pkg, _, st = line.partition("\t")
            if st.startswith("ii"):
                apt.add(pkg)
        if shutil.which("flatpak"):
            rc, out, _ = run(["flatpak", "list", "--app", "--columns=application,installation"])
            for line in out.splitlines():
                parts = line.split("\t")
                if parts and parts[0].strip():
                    flat.add(parts[0].strip())
                    scope[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else "user"
        ai = {n for n, d in self._ai_load().items() if os.path.isfile(d.get("file", ""))}
        try:
            ai |= {a.name for a in AI.list_installed()}
        except OSError:
            pass
        self._inst = {"apt": apt, "flatpak": flat, "appimage": ai}
        self._flat_inst = scope
        self._rev += 1
        self.revChanged.emit()

    def _flat_refresh(self):
        lst = []
        if shutil.which("flatpak"):
            rc, out, _ = run(["flatpak", "remotes", "--show-disabled", "--columns=name,url,options"])
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0].strip() and parts[0].strip().lower() not in ("name", "nome"):
                    opts = parts[2] if len(parts) > 2 else ""
                    lst.append({"id": parts[0].strip(), "host": urlparse(parts[1]).netloc or parts[1],
                                "user": "user" in opts, "enabled": "disabled" not in opts})
        self._flat_list = lst
        self._flat_ok = (not lst) or any(r["enabled"] for r in lst)
        return lst

    def _fw_remotes(self):
        out = []
        if not shutil.which("fwupdmgr"):
            return out
        for path in sorted(glob.glob("/etc/fwupd/remotes.d/*.conf")):
            cfg = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cfg.read(path, encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            sec = "fwupd Remote"
            if not cfg.has_section(sec):
                continue
            out.append({"id": os.path.splitext(os.path.basename(path))[0],
                        "title": cfg.get(sec, "Title", fallback=""),
                        "enabled": cfg.get(sec, "Enabled", fallback="true").strip().lower() == "true"})
        self._fw_ok = any(r["enabled"] for r in out)
        return out

    def _ensure_flathub(self):
        if shutil.which("flatpak") and not self._flat_list:
            rc, _, _ = run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_URL], 60)
            if rc == 0:
                self._flat_refresh()

    def _flat_flags(self):
        """Instalações Flatpak a tentar: system (pede palavra-passe) e depois user."""
        enabled = [r for r in self._flat_list if r["enabled"]]

        def pick(lst):
            return next((r["id"] for r in lst if r["id"] == "flathub"), lst[0]["id"])
        users = [r for r in enabled if r["user"]]
        systems = [r for r in enabled if not r["user"]]
        out = []
        if systems:
            out.append(("--system", pick(systems)))
        if users:
            out.append(("--user", pick(users)))
        return out or [("--user", "flathub")]

    def _flat_install(self, pkg, cb):
        rc, msg = 1, ""
        for flag, remote in self._flat_flags():
            if flag == "--system":
                cmd = self._flat_priv(["install", "--system", "-y", "--noninteractive", remote, pkg])
            else:
                cmd = ["flatpak", "install", "--user", "-y", "--noninteractive", remote, pkg]
            rc, msg = self._stream(cmd, cb, "pct")
            if rc == 0 or msg == "cancelled":
                break
        return rc, msg

    def _flat_info(self, pkg):
        for flag, remote in self._flat_flags():
            rc, out, _ = run(["flatpak", "remote-info", flag, remote, pkg], 40)
            if rc == 0:
                return rc, out
        return 1, ""

    @staticmethod
    def _os_name():
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                kv = dict(l.strip().split("=", 1) for l in f if "=" in l)
            name = kv.get("NAME", "Ubuntu").strip('"')
            ver = kv.get("VERSION", "").strip('"').split(" (")[0]
            return (name + " " + ver).strip()
        except Exception:  # noqa: BLE001
            return "Ubuntu"

    # ----- AppImage: feed -----
    def _feed_stale(self):
        return (not os.path.isfile(FEED_FILE)) or time.time() - os.path.getmtime(FEED_FILE) > 3 * 86400

    def _feed_download(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            data = urllib.request.urlopen(urllib.request.Request(FEED_URL, headers=UA), timeout=20).read()
            with open(FEED_FILE, "wb") as f:
                f.write(data)
            self._feed_cache = None
            return True
        except Exception:  # noqa: BLE001
            return False

    def _feed_list(self):
        if self._feed_cache is None:
            lst = []
            try:
                with open(FEED_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
                for it in raw.get("items", []):
                    repo = gh_repo(it.get("links"))
                    if it.get("name") and repo:
                        lst.append({"name": it["name"], "description": it.get("description") or "",
                                    "repo": repo, "key": norm_key(it["name"]),
                                    "shots": [x for x in (it.get("screenshots") or []) if isinstance(x, str)]})
            except Exception:  # noqa: BLE001
                pass
            self._feed_cache = lst
        return self._feed_cache

    # ----- listas -----
    def _resolve_aliases(self):
        """Apps cujo pacote pode ter outro nome: usa o que estiver instalado."""
        for e in self._featured:
            names = [e.get("package", "")] + list(e.get("aliases") or [])
            if len(names) < 2:
                continue
            rc, txt, _ = run(["dpkg-query", "-W", "-f=${Package}\t${db:Status-Abbrev}\n"] + names)
            for line in txt.splitlines():
                p, _, st = line.partition("\t")
                if st.startswith("ii") and p in names:
                    e["package"] = p
                    break

    # ----- releases GitHub das apps exclusivas Mainuan -----
    @staticmethod
    def _gh_cache_load():
        try:
            with open(GH_CACHE, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _gh_cache_save(d):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = GH_CACHE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, GH_CACHE)
        except OSError:
            pass

    @staticmethod
    def _gh_pick_deb(assets):
        debs = [a for a in assets if a.get("name", "").lower().endswith(".deb")]
        if not debs:
            return None
        rc, arch, _ = run(["dpkg", "--print-architecture"])
        arch = arch.strip() or "amd64"
        for want in (arch, "all"):
            for a in debs:
                if re.search(r"[_.-]%s\.deb$" % re.escape(want), a["name"].lower()):
                    return a
        return debs[0]

    def _gh_release(self, repo, max_age=GH_TTL):
        """Última release (não rascunho, não pré-lançamento) do repositório; usa cache."""
        cache = self._gh_cache_load()
        e = cache.get(repo)
        if e and time.time() - e.get("time", 0) < max_age:
            return e
        try:
            req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % repo,
                                         headers=dict(UA, Accept="application/vnd.github+json"))
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            assets = [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""), "size": a.get("size", 0)}
                      for a in data.get("assets", [])]
            deb = self._gh_pick_deb(assets)
            tag = str(data.get("tag_name", ""))
            version = re.sub(r"^[vV]", "", tag)
            if deb and not re.match(r"^\d+(\.\d+)+", version):   # tag sem versão: nome do ficheiro
                parts = deb["name"][:-4].split("_")
                if len(parts) >= 2 and re.match(r"^\d", parts[1]):
                    version = parts[1]
            e = {"time": time.time(), "tag": tag, "version": version,
                 "url": deb["url"] if deb else "", "asset": deb["name"] if deb else "",
                 "size": deb.get("size", 0) if deb else 0}
            cache[repo] = e
            self._gh_cache_save(cache)
        except Exception:  # noqa: BLE001
            pass       # sem rede / limite da API: mantém a cache antiga (se existir)
        return e

    def _refresh_releases(self, force=False):
        """Atualiza a cache das releases; devolve True se alguma coisa mudou."""
        changed = False
        for e in self._gh_apps:
            repo = e.get("repo")
            if not repo:
                continue
            old = self._gh_cache_load().get(repo, {}).get("version")
            new = self._gh_release(repo, 0 if force else GH_TTL)
            if new and new.get("version") != old:
                changed = True
        return changed

    def _featured_items(self):
        items = []
        cache = self._gh_cache_load()
        for e in self._featured:
            pkg, version = e.get("package", ""), e.get("version", "")
            repo = e.get("repo", "")
            rel = cache.get(repo, {}) if repo else {}
            url = rel.get("url", "")
            if rel.get("version"):
                version = rel["version"]
            path = os.path.join(DEB_DIR, e["file"]) if e.get("file") else ""
            has = bool(path) and os.path.isfile(path)
            if has and not url:
                rc, out, _ = run(["dpkg-deb", "-f", path, "Package", "Version"])
                for line in out.splitlines():
                    if line.startswith("Package:"):
                        pkg = line.split(":", 1)[1].strip()
                    elif line.startswith("Version:"):
                        version = line.split(":", 1)[1].strip()
            avail = has or bool(url) or bool(repo) or self._apt_candidates([pkg]).get(pkg, False)
            it = self._item(e.get("name", pkg), self._loc(e.get("summary")),
                            [self._variant("deb", pkg, version=version, file=path if has else "",
                                           available=avail, repo=repo, url=url,
                                           shotsDir=(e.get("screenshots_dir") or "assets/screenshots") if repo else "")],
                            e.get("category", "utils"), e.get("iconName", pkg), self._loc(e.get("description")))
            it["id"] = "deb:" + pkg
            it["screenshots"] = [u for u in (self._shot_url(x) for x in (e.get("screenshots") or [])) if u]
            icon = os.path.join(ICON_DIR, e.get("icon", "")) if e.get("icon") else ""
            it["iconFile"] = icon if icon and os.path.isfile(icon) else ""
            items.append(it)
        return items

    def _gh_install(self, v, cb):
        """Descarrega o DEB da última release GitHub e instala-o com o apt."""
        repo = v.get("repo", "")
        if repo not in {e.get("repo") for e in self._gh_apps}:
            return False, "unknown repository"
        rel = self._gh_release(repo, 600) or {}
        url = rel.get("url") or v.get("url", "")
        if not url:
            return False, "no .deb file in the latest GitHub release"
        dl_dir = os.path.join(CACHE_DIR, "downloads")
        os.makedirs(dl_dir, exist_ok=True)
        path = os.path.join(dl_dir, re.sub(r"[^A-Za-z0-9._+-]", "_", rel.get("asset") or "app.deb"))
        try:
            self._download(url, path, lambda p: cb(p * 0.5),
                           lambda: getattr(self._tl, "key", None) in self._cancel)
            rc, out, _ = run(["dpkg-deb", "-f", path, "Package"])
            got = out.replace("Package:", "").strip()
            allowed = {v.get("pkg", "")}
            for e in self._gh_apps:
                if e.get("repo") == repo:
                    allowed.update(e.get("aliases") or [])
            if rc != 0 or (v.get("pkg") and got not in allowed):
                return False, "unexpected package in release (%s)" % (got or "invalid .deb")
            rc, msg = self._stream(self._apt(["install", "-y", path]), lambda p: cb(50 + p * 0.5), "apt")
            return rc == 0, msg
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            for f in (path, path + ".part"):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _github_updates(self, skip):
        """Apps Mainuan instaladas cuja release GitHub é mais recente que a versão instalada."""
        out = []
        pkgs = [e["package"] for e in self._gh_apps if e.get("repo") and e.get("package")]
        if not pkgs:
            return out
        rc, txt, _ = run(["dpkg-query", "-W", "-f=${Package}\t${db:Status-Abbrev}\t${Version}\n"] + pkgs)
        inst = {}
        for line in txt.splitlines():
            p, _, rest = line.partition("\t")
            st, _, ver = rest.partition("\t")
            if st.startswith("ii"):
                inst[p] = ver.strip()
        for e in self._gh_apps:
            pkg, repo = e.get("package", ""), e.get("repo", "")
            if not repo or pkg not in inst or pkg in skip:
                continue
            rel = self._gh_release(repo)
            new = (rel or {}).get("version", "")
            if not new or not rel.get("url"):
                continue
            rc, _, _ = run(["dpkg", "--compare-versions", inst[pkg], "lt", new])
            if rc == 0:
                it = self._upd("deb", pkg, e.get("name", pkg), inst[pkg], new)
                it["origin"] = "github"
                it["iconName"] = e.get("iconName", pkg)
                icon = os.path.join(ICON_DIR, e.get("icon", "")) if e.get("icon") else ""
                it["iconFile"] = icon if icon and os.path.isfile(icon) else ""
                it["variants"][0].update(repo=repo, url=rel["url"], version=new)
                out.append(it)
        return out

    def _apt_candidates(self, pkgs):
        res, cur = {}, None
        if not pkgs:
            return res
        rc, out, _ = run(["apt-cache", "policy"] + list(pkgs))
        for line in out.splitlines():
            if line and not line.startswith(" ") and line.endswith(":"):
                cur = line[:-1]
                res[cur] = False
            elif cur and line.strip().startswith("Candidate:"):
                res[cur] = "(none)" not in line
        return res

    def _catalog_items(self):
        pkgs = [v["pkg"] for e in self._catalog for v in e.get("variants", []) if v["source"] == "apt"]
        cand = self._apt_candidates(pkgs)
        feed = {f["key"]: f for f in self._feed_list()} if self._ai_on else {}
        items = []
        for e in self._catalog:
            vs = []
            for v in e.get("variants", []):
                s = v["source"]
                if s == "apt" and not cand.get(v["pkg"]):
                    continue
                if self._src_ok(s):
                    vs.append(self._variant(s, v["pkg"]))
            f = feed.get(norm_key(e["name"]))
            if f and not any(x["source"] == "appimage" for x in vs):
                vs.append(self._variant("appimage", f["name"], repo=f["repo"]))
            if vs:
                items.append(self._item(e["name"], self._loc(e.get("summary")), vs,
                                        e.get("category", "utils"), e.get("icon", "")))
        return items

    def _index_sources(self):
        srcs = []
        for path in sorted(glob.glob("/var/lib/apt/lists/*dep11_Components-*.yml.gz")):
            if "amd64" in path or "-all" in path:
                srcs.append(("apt", path))
        if self._src_ok("flatpak"):
            on = {r["id"] for r in self._flat_list if r["enabled"]}
            pats = ["/var/lib/flatpak/appstream/*/*/active/appstream.xml.gz",
                    os.path.join(HOME, ".local/share/flatpak/appstream/*/*/active/appstream.xml.gz")]
            for pat in pats:
                for path in sorted(glob.glob(pat)):
                    remote = path.split("/appstream/")[1].split("/")[0]
                    if not on or remote in on:
                        srcs.append(("flatpak", path))
        return srcs

    @staticmethod
    def _index_sig(srcs):
        sig = []
        for kind, path in srcs:
            try:
                sig.append([kind, path, int(os.path.getmtime(path)), os.path.getsize(path)])
            except OSError:
                pass
        return sig

    def _build_index(self, srcs, sig):
        raw = {}
        for kind, path in srcs:
            try:
                gen = read_dep11(path) if kind == "apt" else read_flatpak_xml(path)
                for e in gen:
                    nm = e["names"].get("C") or next(iter(e["names"].values()), "")
                    k = norm_key(nm)
                    if not k:
                        continue
                    v = {"source": e["source"], "pkg": e["pkg"]}
                    cur = raw.get(k)
                    if cur is None:
                        raw[k] = {"names": e["names"], "sums": e["sums"], "category": e["category"],
                                  "iconName": e["iconName"], "iconFile": e["iconFile"], "variants": [v]}
                        continue
                    if not any(x["source"] == v["source"] and x["pkg"] == v["pkg"] for x in cur["variants"]):
                        cur["variants"].append(v)
                    for f in ("category", "iconName", "iconFile"):
                        if not cur[f] and e[f]:
                            cur[f] = e[f]
                    if not cur["sums"]:
                        cur["sums"] = e["sums"]
            except Exception:  # noqa: BLE001
                continue
        items = list(raw.values())
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump({"sig": sig, "items": items}, f, ensure_ascii=False)
        except OSError:
            pass
        return items

    def _ensure_index(self):
        with self._index_lock:
            if self._index is not None:
                return self._index
            srcs = self._index_sources()
            sig = self._index_sig(srcs)
            try:
                with open(INDEX_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("sig") == sig and data.get("items"):
                    self._index = data["items"]
                    return self._index
            except Exception:  # noqa: BLE001
                pass
            if not srcs:
                self._index = []
                return self._index
            self.indexBuilding.emit(True)
            try:
                self._index = self._build_index(srcs, sig)
            finally:
                self.indexBuilding.emit(False)
            return self._index

    def _category_items(self, cat):
        idx = self._ensure_index() or []
        feed = {f["key"]: f for f in self._feed_list()} if self._src_ok("appimage") else {}
        cur = [i for i in self._catalog_items() if cat == "all" or i["category"] == cat]
        extra = []
        for e in idx:
            if not e["category"] or (cat != "all" and e["category"] != cat):
                continue
            vs = [self._variant(v["source"], v["pkg"]) for v in e["variants"] if self._src_ok(v["source"])]
            if not vs:
                continue
            name = self._loc(e["names"])
            f = feed.get(norm_key(name))
            if f and not any(x["source"] == "appimage" for x in vs):
                vs.append(self._variant("appimage", f["name"], repo=f["repo"]))
            it = self._item(name, self._loc(e["sums"]), vs, e["category"], e.get("iconName") or "")
            it["iconFile"] = e.get("iconFile", "")
            extra.append(it)
        merged = self._merge(cur + extra)
        keep = {i["id"] for i in cur}
        head = [m for m in merged if m["id"] in keep]
        rest = sorted([m for m in merged if m["id"] not in keep], key=lambda m: m["name"].lower())
        return (head + rest)[:1500]

    @Slot(str)
    def loadCategory(self, cat):
        self._bg(self._load_category, cat)

    def _load_category(self, cat):
        self.listReady.emit("category", self._category_items(cat))

    @Slot()
    def loadHome(self):
        self._bg(self._home)

    def _home(self):
        self._refresh_installed()
        self._flat_refresh()
        self._fw_remotes()
        self.listReady.emit("featured", self._featured_items())
        self.listReady.emit("catalog", self._catalog_items())
        if self._refresh_releases():
            self.listReady.emit("featured", self._featured_items())
        if self._ai_on and self._feed_stale() and self._feed_download():
            self.listReady.emit("catalog", self._catalog_items())
        if not self._index_started:
            self._index_started = True
            self._ensure_index()

    @Slot(str)
    def search(self, query):
        self._bg(self._search, query)

    def _search(self, query):
        q = query.strip()
        items = []
        if len(q) >= 2:
            rc, out, _ = run(["apt-cache", "search", "--names-only", q])
            n = 0
            for line in out.splitlines():
                pkg, _, desc = line.partition(" - ")
                if not pkg or pkg.startswith("lib") or pkg.endswith(SKIP_SUFFIX):
                    continue
                items.append(self._item(pkg, desc, [self._variant("apt", pkg)], icon=pkg))
                n += 1
                if n >= 30:
                    break
            if self._src_ok("flatpak"):
                self._ensure_flathub()
                rc, out, _ = run(["flatpak", "search", "--columns=application,name,description", q], 40)
                n = 0
                for line in out.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2 and "." in parts[0] and " " not in parts[0]:
                        items.append(self._item(parts[1], parts[2] if len(parts) > 2 else "",
                                                [self._variant("flatpak", parts[0])], icon=parts[0]))
                        n += 1
                        if n >= 30:
                            break
            if self._src_ok("appimage"):
                if not self._feed_list() and self._feed_stale():
                    self._feed_download()
                ql = q.lower()
                n = 0
                for f in self._feed_list():
                    if ql in f["name"].lower():
                        items.append(self._item(f["name"], f["description"],
                                                [self._variant("appimage", f["name"], repo=f["repo"])]))
                        n += 1
                        if n >= 20:
                            break
            items = self._merge(items)
            try:
                self._refresh_installed()
                self._mark_installed(items)
            except Exception:  # noqa: BLE001
                pass
            ql = q.lower()
            items.sort(key=lambda i: (not i["name"].lower().startswith(ql), ql not in i["name"].lower()))
        self.listReady.emit("search", items)

    def _mark_installed(self, items):
        """Se a app já está instalada por outra via (APT/Flatpak/AppImage), junta essa variante ao
        resultado para aparecer como «Instalada» e permitir Abrir/Remover."""
        by_apt = {norm_key(p): p for p in self._inst["apt"]}
        by_flat = {}
        for fid in self._inst["flatpak"]:
            by_flat[norm_key(fid.split(".")[-1])] = fid
            by_flat[norm_key(fid)] = fid
        by_ai = {norm_key(n): n for n in self._inst["appimage"]}
        for it in items:
            have = {(v["source"], v["pkg"]) for v in it["variants"]}
            if any(self.isInstalled(src, pkg) for src, pkg in have):
                continue
            keys = {norm_key(it["name"])} | {norm_key(v["pkg"].split(".")[-1]) for v in it["variants"]}
            keys.discard("")
            for k in keys:
                for src, table in (("apt", by_apt), ("flatpak", by_flat), ("appimage", by_ai)):
                    pkg = table.get(k)
                    if pkg and (src, pkg) not in have:
                        it["variants"].append(self._variant(src, pkg))
                        have.add((src, pkg))
                        break

    @Slot()
    def loadInstalled(self):
        self._bg(self._installed)

    def _installed(self):
        self._refresh_installed()
        local = set()
        rc, out, _ = run(["apt", "list", "--installed"])
        for line in out.splitlines():
            if "installed" in line and ",local" in line:
                local.add(line.split("/")[0])
        items = []
        files = glob.glob("/usr/share/applications/*.desktop")
        if files:
            rc, out, _ = run(["dpkg-query", "-S"] + files)
            seen = {}
            for line in out.splitlines():
                if ": /" in line:
                    pkgs, _, path = line.partition(": ")
                    for p in pkgs.split(", "):
                        seen.setdefault(p.split(":")[0], path)
            for pkg, path in seen.items():
                info = parse_desktop(path, self._lang)
                if info["hidden"] or not (info["loc"] or info["name"]):
                    continue
                origin = "deb" if pkg in local else "apt"
                items.append(self._item(info["loc"] or info["name"], info["comment"],
                                        [self._variant(origin, pkg)], icon=info["icon"] or pkg, origin=origin))
        if shutil.which("flatpak"):
            rc, out, _ = run(["flatpak", "list", "--app", "--columns=application,name"])
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0].strip():
                    items.append(self._item(parts[1], "", [self._variant("flatpak", parts[0])],
                                            icon=parts[0], origin="flatpak"))
        known = set()
        for name, d in self._ai_load().items():
            if os.path.isfile(d.get("file", "")):
                known.add(d["file"])
                items.append(self._item(name, "AppImage", [self._variant("appimage", name)], origin="appimage"))
        try:
            for a in AI.list_installed():
                if str(a.file_path) not in known:
                    items.append(self._item(a.name, "AppImage", [self._variant("appimage", a.name)],
                                            icon=("" if not a.icon_path else str(a.icon_path)), origin="appimage"))
        except OSError:
            pass
        items.sort(key=lambda i: i["name"].lower())
        self.listReady.emit("installed", items)

    @Slot()
    def loadUpdates(self):
        self._bg(self._updates)

    def _upd(self, source, pkg, name, old, new):
        it = self._item(name, "", [self._variant(source, pkg)], icon=pkg, origin=source)
        it["id"] = "upd:%s:%s" % (source, pkg)
        it["fromVer"], it["toVer"] = old, new
        return it

    def _updates(self):
        items = self.collect_updates()
        self._last_updates = items
        self.listReady.emit("updates", items)

    def collect_updates(self):
        """Atualizações disponíveis: APT (inclui sistema e DEBs de repositórios), Flatpak,
        AppImage e firmware. Também usado pelo serviço de notificações (tray.py)."""
        items = []
        rc, out, _ = run(["apt", "list", "--upgradable"])
        for line in out.splitlines():
            if "/" in line and "upgradable" in line:
                parts = line.split()
                m = re.search(r"from: ([^\]]+)", line)
                items.append(self._upd("apt", line.split("/")[0], line.split("/")[0],
                                       m.group(1) if m else "", parts[1] if len(parts) > 1 else ""))
        if self._src_ok("flatpak"):
            rc, out, _ = run(["flatpak", "remote-ls", "--updates", "--app",
                              "--columns=application,name,version"], 40)
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and "." in parts[0]:
                    items.append(self._upd("flatpak", parts[0], parts[1], "", parts[2] if len(parts) > 2 else ""))
        if shutil.which("fwupdmgr") and self._fw_ok:
            rc, out, _ = run(["fwupdmgr", "get-updates", "--json"], 60)
            try:
                data = json.loads(out[out.index("{"):])
                for d in data.get("Devices", []):
                    rel = (d.get("Releases") or [{}])[0]
                    items.append(self._upd("firmware", d.get("DeviceId", ""), d.get("Name", "Firmware"),
                                           d.get("Version", ""), rel.get("Version", "")))
            except Exception:  # noqa: BLE001
                pass
        try:
            apt_pkgs = {i["variants"][0]["pkg"] for i in items if i.get("origin") == "apt"}
            items.extend(self._github_updates(apt_pkgs))
        except Exception:  # noqa: BLE001
            pass
        if self._ai_on:
            try:
                items.extend(self._appimage_updates())
            except Exception:  # noqa: BLE001
                pass
        self._write_updates_cache(items)
        return items

    def _appimage_updates(self):
        out = []
        self._ai_upd = {}
        for a in AI.list_installed():
            if not a.desktop_file_path:
                continue
            mode = AI.update_mode(a)
            if mode == "none":
                continue
            info = AI.check_update(str(a.file_path))
            if info.get("has_update") is True:
                self._ai_upd[str(a.file_path)] = info
                it = self._upd("appimage", str(a.file_path), a.name, a.version, info.get("latest_version", ""))
                if a.icon_path:
                    it["iconName"] = str(a.icon_path)
                out.append(it)
        return out

    @staticmethod
    def _write_updates_cache(items):
        """Resumo para o serviço de notificações saber o estado atual."""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            data = {"time": int(time.time()), "count": len(items),
                    "items": [{"id": i["id"], "name": i["name"]} for i in items]}
            tmp = os.path.join(CACHE_DIR, "updates.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, os.path.join(CACHE_DIR, "updates.json"))
        except OSError:
            pass
        if not items:
            notifier.close_saved()          # sem atualizações pendentes: a notificação desaparece

    # ----- detalhes -----
    @Slot("QVariantMap")
    def details(self, item):
        self._bg(self._details, dict(item))
        self._bg(self._shots_job, dict(item))

    # ----- capturas de ecrã -----
    @staticmethod
    def _shot_url(u):
        u = str(u or "").strip()
        if not u:
            return ""
        if u.startswith(("http://", "https://", "file://")):
            return u
        path = u if os.path.isabs(u) else os.path.join(BASE, "assets", "screenshots", u)
        return "file://" + path if os.path.isfile(path) else ""

    def _shots_job(self, it):
        try:
            urls = self._find_shots(it)
        except Exception:  # noqa: BLE001
            urls = []
        self.shotsReady.emit(it.get("id", ""), urls[:10])

    def _find_shots(self, it):
        local = [u for u in (self._shot_url(x) for x in (it.get("screenshots") or [])) if u]
        if local:
            return local
        order = {"flatpak": 0, "apt": 1, "deb": 1, "appimage": 2}
        for v in sorted(it.get("variants", []), key=lambda x: order.get(x.get("source"), 9)):
            key = (v.get("source"), v.get("pkg"))
            if key not in self._shots_cache:
                urls = []
                try:
                    if key[0] == "flatpak":
                        urls = self._shots_flathub(v["pkg"])
                    elif key[0] in ("apt", "deb"):
                        urls = self._shots_github(v.get("repo", ""), v.get("shotsDir", "")) or self._shots_dep11(v["pkg"])
                    elif key[0] == "appimage":
                        urls = self._shots_appimage(v.get("repo", ""))
                except Exception:  # noqa: BLE001
                    urls = []
                self._shots_cache[key] = urls
            if self._shots_cache[key]:
                return self._shots_cache[key]
        return []

    def _shots_github(self, repo, folder):
        """Capturas de ecrã na pasta do repositório GitHub (ex.: assets/screenshots); cache de 6 h."""
        if not repo or not folder or repo not in {e.get("repo") for e in self._gh_apps}:
            return []
        key = "%s#shots" % repo
        cache = self._gh_cache_load()
        e = cache.get(key)
        if e and time.time() - e.get("time", 0) < 6 * 3600:
            return e.get("urls", [])
        urls = None
        try:
            req = urllib.request.Request("https://api.github.com/repos/%s/contents/%s" % (repo, folder.strip("/")),
                                         headers=dict(UA, Accept="application/vnd.github+json"))
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            files = sorted((f for f in data if f.get("type") == "file"
                            and f.get("name", "").lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
                            and f.get("download_url")), key=lambda f: f["name"].lower())
            urls = [f["download_url"] for f in files][:10]
            cache[key] = {"time": time.time(), "urls": urls}
            self._gh_cache_save(cache)
        except Exception:  # noqa: BLE001
            pass
        return urls if urls is not None else (e.get("urls", []) if e else [])

    @staticmethod
    def _shots_flathub(appid):
        if "." not in appid:
            return []
        req = urllib.request.Request("https://flathub.org/api/v2/appstream/" + appid, headers=UA)
        data = json.load(urllib.request.urlopen(req, timeout=12))
        out = []
        for sc in data.get("screenshots") or []:
            url = ""
            sizes = [z for z in (sc.get("sizes") or []) if isinstance(z, dict) and z.get("src")]
            if sizes:
                def width(z):
                    try:
                        return int(z.get("width") or 0)
                    except (TypeError, ValueError):
                        return 0
                good = [z for z in sizes if width(z) <= 1400] or sizes
                url = max(good, key=width).get("src", "")
            url = url or sc.get("imgDesktopUrl") or sc.get("src") or ""
            if str(url).startswith("http"):
                out.append(str(url))
        return out

    @staticmethod
    def _shots_dep11(pkg):
        try:
            import yaml
        except ImportError:
            return []
        target = "Package: %s\n" % pkg
        doc = ""
        for path in sorted(glob.glob("/var/lib/apt/lists/*dep11_Components-*.yml.gz")):
            if not ("amd64" in path or "-all" in path):
                continue
            buf, hit = [], False
            try:
                with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("---"):
                            if hit:
                                doc = "".join(buf)
                                break
                            buf, hit = [], False
                        else:
                            buf.append(line)
                            if line == target:
                                hit = True
                    else:
                        if hit:
                            doc = "".join(buf)
            except OSError:
                continue
            if doc:
                break
        if not doc:
            return []
        data = yaml.safe_load(doc)
        out = []
        for sc in (data or {}).get("Screenshots") or []:
            if not isinstance(sc, dict):
                continue
            thumbs = [t for t in (sc.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]

            def tw(t):
                try:
                    return int(t.get("width") or 0)
                except (TypeError, ValueError):
                    return 0
            big = [t for t in thumbs if 600 <= tw(t) <= 1200]
            url = (max(big, key=tw)["url"] if big
                   else ((sc.get("source-image") or {}).get("url") or (max(thumbs, key=tw)["url"] if thumbs else "")))
            if str(url).startswith("http"):
                out.append(str(url))
        return out

    def _shots_appimage(self, repo):
        for f in self._feed_list():
            if f["repo"] == repo:
                return [x if x.startswith("http") else "https://appimage.github.io/database/" + x.lstrip("/")
                        for x in f.get("shots", [])]
        return []

    def _details(self, it):
        info = {"id": it.get("id", ""), "text": "", "variants": {}}
        texts = []
        for v in it.get("variants", []):
            s, d = v["source"], {"version": v.get("version", ""), "size": ""}
            try:
                if s in ("apt", "deb"):
                    if v.get("file") and os.path.isfile(v["file"]):
                        d["size"] = fmt_size(os.path.getsize(v["file"]))
                    rc, out, _ = run(["apt-cache", "show", v["pkg"]])
                    if rc == 0:
                        desc, in_desc = [], False
                        for line in out.split("\n\n")[0].splitlines():
                            if line.startswith("Version:") and not d["version"]:
                                d["version"] = line.split(":", 1)[1].strip()
                            elif line.startswith("Size:") and not d["size"]:
                                d["size"] = fmt_size(line.split(":", 1)[1].strip())
                            elif line.startswith("Description"):
                                in_desc = True
                                desc.append(line.split(":", 1)[1].strip())
                            elif in_desc and line.startswith(" "):
                                t = line.strip()
                                desc.append("" if t == "." else t)
                            else:
                                in_desc = False
                        if len(desc) > 1:
                            texts.append("\n".join(desc[1:]).strip())
                elif s == "flatpak":
                    rc, out = self._flat_info(v["pkg"])
                    lines = out.splitlines()
                    if lines and " - " in lines[0]:
                        texts.append(lines[0].split(" - ", 1)[1].strip())
                    for line in lines:
                        st = line.strip()
                        if st.startswith("Version:"):
                            d["version"] = st.split(":", 1)[1].strip()
                        elif st.startswith("Download:"):
                            d["size"] = st.split(":", 1)[1].strip()
                elif s == "appimage" and v.get("repo"):
                    asset = self._gh_asset(v["repo"])
                    if asset:
                        d["version"], d["size"] = asset[0], fmt_size(asset[3])
            except Exception:  # noqa: BLE001
                pass
            info["variants"][s] = d
        info["text"] = next((t for t in texts if t), "")
        lang = self._lang
        self.detailsReady.emit(info)
        if info["text"] and lang != "en":
            tr = self._translate(info["text"], lang)
            if tr and tr != info["text"] and lang == self._lang:
                info["text"] = tr
                self.detailsReady.emit(info)

    # ----- tradução da descrição para o idioma da app -----
    _TR_CODES = {"pt_PT": ("pt-PT", "pt"), "pt_BR": ("pt",), "fr": ("fr",), "es": ("es",)}

    def _tr_file(self):
        return os.path.join(CACHE_DIR, "translations.json")

    def _tr_load(self):
        if self._tr_cache is None:
            try:
                with open(self._tr_file(), encoding="utf-8") as f:
                    self._tr_cache = json.load(f)
            except (OSError, ValueError):
                self._tr_cache = {}
        return self._tr_cache

    def _translate(self, text, lang):
        """Traduz `text` para `lang` (cache em disco). Se falhar, devolve o texto original."""
        codes = self._TR_CODES.get(lang)
        if not text or not text.strip() or not codes:
            return text
        key = hashlib.md5((lang + "\n" + text).encode("utf-8")).hexdigest()
        with self._tr_lock:
            hit = self._tr_load().get(key)
        if hit:
            return hit
        out = []
        for para in text.split("\n"):
            if not para.strip():
                out.append(para)
                continue
            done = None
            for code in codes:
                try:
                    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="
                           + code + "&dt=t&q=" + urllib.parse.quote(para[:4000]))
                    data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10))
                    done = "".join(seg[0] for seg in data[0] if seg and seg[0])
                    if done.strip():
                        break
                    done = None
                except Exception:  # noqa: BLE001
                    done = None
            if done is None:
                return text          # sem rede / falhou: mantém o original (não guarda em cache)
            out.append(done)
        res = "\n".join(out)
        with self._tr_lock:
            cache = self._tr_load()
            cache[key] = res
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(self._tr_file(), "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
            except OSError:
                pass
        return res

    # ----- operações -----
    @staticmethod
    def _cancel_file(key):
        return os.path.join(CACHE_DIR, "cancel-" + hashlib.md5(key.encode()).hexdigest()[:16])

    def _rm_cancel(self, key):
        try:
            os.remove(self._cancel_file(key))
        except OSError:
            pass

    def _apt(self, args):
        """apt-get como root, com cancelamento, via helper (pede palavra-passe)."""
        key = getattr(self._tl, "key", "none")
        return ["pkexec", HELPER, "apt", self._cancel_file(key)] + APT_OPTS + args

    def _flat_priv(self, args):
        """flatpak como root (instalação system-wide), via helper (pede palavra-passe)."""
        key = getattr(self._tl, "key", "none")
        return ["pkexec", HELPER, "flatpak", self._cancel_file(key)] + args

    @Slot(str)
    def cancel(self, key):
        self._cancel.add(key)
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            open(self._cancel_file(key), "w").close()
        except OSError:
            pass
        p = self._procs.get(key)
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass

    def _op(self, key, name, fn):
        self._tl.key = key
        self._cancel.discard(key)
        self._rm_cancel(key)
        self.opStarted.emit(key, name)
        cb = lambda pct: self.opProgress.emit(key, max(0, min(100, int(pct))))  # noqa: E731
        try:
            ok, msg = fn(cb)
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        if key in self._cancel:
            ok, msg = False, "cancelled"
        self._cancel.discard(key)
        self._rm_cancel(key)
        self._procs.pop(key, None)
        if key in ("index", "src"):
            self._index = None
        self._refresh_installed()
        self.opFinished.emit(key, ok, msg)

    @staticmethod
    def _variant_of(it, source):
        return next((dict(v) for v in it.get("variants", []) if v["source"] == source), None)

    @Slot("QVariantMap", str)
    def install(self, item, source):
        it = dict(item)
        v = self._variant_of(it, source)
        if v:
            self._bg(self._op, it["id"], it["name"], lambda cb: self._do_install(v, cb))

    def _do_install(self, v, cb):
        s = v["source"]
        if s == "deb" and v.get("repo") and not (v.get("file") and not v.get("url")):
            return self._gh_install(v, cb)
        if s in ("apt", "deb"):
            rc, msg = self._stream(self._apt(["install", "-y", v.get("file") or v["pkg"]]), cb, "apt")
        elif s == "flatpak":
            self._ensure_flathub()
            rc, msg = self._flat_install(v["pkg"], cb)
        elif s == "appimage":
            return self._ai_install(v, cb)
        else:
            return False, "unsupported"
        return rc == 0, msg

    @Slot("QVariantMap", str)
    def remove(self, item, source):
        it = dict(item)
        v = self._variant_of(it, source)
        if v:
            self._bg(self._op, it["id"], it["name"], lambda cb: self._do_remove(v, cb))

    def _do_remove(self, v, cb):
        s, pkg = v["source"], v["pkg"]
        if s == "flatpak":
            if self._flat_inst.get(pkg) == "system":
                cmd = self._flat_priv(["uninstall", "--system", "-y", "--noninteractive", pkg])
            else:
                cmd = ["flatpak", "uninstall", "--user", "-y", "--noninteractive", pkg]
            rc, msg = self._stream(cmd, cb, "pct")
            return rc == 0, msg
        if s == "appimage":
            f = self._ai_file_for(pkg)
            try:
                if f:
                    AI.delete(f)
            except (OSError, ValueError) as exc:
                return False, str(exc)
            data = self._ai_load()
            if data.pop(pkg, None) is not None:
                self._ai_save(data)
            cb(100)
            return True, ""
        if pkg in PROTECTED:
            return False, "protected package"
        rc, out, _ = run(["apt-get", "-s", "remove", pkg])
        gone = [l.split()[1] for l in out.splitlines() if l.startswith("Remv") and len(l.split()) > 1]
        others = [g for g in gone if g != pkg]
        if others:
            return False, "would also remove: " + ", ".join(others[:6])
        rc, msg = self._stream(self._apt(["remove", "-y", pkg]), cb, "apt")
        return rc == 0, msg

    # ----- AppImage -----
    def _gh_asset(self, repo):
        req = urllib.request.Request("https://api.github.com/repos/%s/releases?per_page=5" % repo,
                                     headers=dict(UA, Accept="application/vnd.github+json"))
        data = json.load(urllib.request.urlopen(req, timeout=30))
        for rel in data:
            if rel.get("draft"):
                continue
            cands = [a for a in rel.get("assets", [])
                     if a["name"].lower().endswith(".appimage")
                     and not re.search(r"aarch64|arm64|armv|armhf|i386|i686|zsync", a["name"].lower())]
            if cands:
                pref = [a for a in cands if re.search(r"x86[_-]64|amd64|x64", a["name"].lower())] or cands
                a = pref[0]
                return rel.get("tag_name", ""), a["name"], a["browser_download_url"], a.get("size", 0)
        return None

    @staticmethod
    def _download(url, dest, cb, cancelled=None):
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r, open(dest + ".part", "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                block = r.read(65536)
                if not block:
                    break
                if cancelled and cancelled():
                    raise RuntimeError("cancelled")
                f.write(block)
                done += len(block)
                if total:
                    cb(done * 100.0 / total)
        os.replace(dest + ".part", dest)

    def _ai_file_for(self, pkg):
        """Ficheiro AppImage de uma app instalada (pelo índice da loja ou pelo nome)."""
        d = self._ai_load().get(pkg)
        if d and os.path.isfile(d.get("file", "")):
            return d["file"]
        key = norm_key(pkg)
        try:
            for a in AI.list_installed():
                if norm_key(a.name) == key:
                    return str(a.file_path)
        except OSError:
            pass
        return ""

    def _ai_index(self, name, app):
        data = self._ai_load()
        data[name] = {"file": str(app.file_path),
                      "desktop": str(app.desktop_file_path) if app.desktop_file_path else ""}
        self._ai_save(data)

    def _ai_install(self, v, cb):
        if not v.get("repo"):
            return False, "no download source"
        asset = self._gh_asset(v["repo"])
        if not asset:
            return False, "no AppImage found in releases"
        os.makedirs(str(AI.TMP_DIR), exist_ok=True)
        dest = os.path.join(str(AI.TMP_DIR), slugify(v["pkg"]) + ".AppImage")
        self._download(asset[2], dest, lambda p: cb(p * 0.9),
                       lambda: getattr(self._tl, "key", None) in self._cancel)
        if not AI.is_appimage_file(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
            return False, "the downloaded file is not a valid AppImage"
        app = AI.add_appimage(dest, copy=False, display_name=v["pkg"], progress=lambda p: cb(90 + p / 10.0))
        self._ai_index(v["pkg"], app)
        cb(100)
        return True, ""

    # ----- ficheiros locais -----
    @Slot(str)
    def inspectFile(self, p):
        self._bg(self._inspect, p)

    @staticmethod
    def _ai_key(text):
        t = str(text).lower()
        t = re.sub(r"(x86[_-]?64|amd64|x64|aarch64|arm64|i386|i686|linux|appimage)", " ", t)
        t = re.sub(r"v?\d+(\.\d+)+\w*", " ", t)
        return re.sub(r"[^a-z0-9]", "", t)

    def _ai_match(self, path):
        """AppImage já instalado que corresponde ao ficheiro aberto (ou None)."""
        try:
            apps = AI.list_installed()
        except OSError:
            return None
        real = os.path.realpath(path)
        base = os.path.basename(path).lower()
        for a in apps:
            if os.path.realpath(str(a.file_path)) == real or a.file_path.name.lower() == base:
                return a
        key = self._ai_key(os.path.splitext(os.path.basename(path))[0])
        if len(key) >= 2:
            for a in apps:
                if key in (self._ai_key(a.file_path.stem), self._ai_key(a.name)):
                    return a
        return None

    def _file_info(self, p):
        path = QUrl(p).toLocalFile() if p.startswith("file:") else p
        info = {"path": path, "ok": False, "kind": "", "name": os.path.basename(path),
                "version": "", "description": "", "installed": False, "installedVersion": "",
                "installedFile": "", "pkg": "", "canRemove": True}
        low = path.lower()
        if os.path.isfile(path) and low.endswith(".deb"):
            rc, out, _ = run(["dpkg-deb", "-f", path, "Package", "Version", "Description"])
            for line in out.splitlines():
                if line.startswith("Package:"):
                    info["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    info["version"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    info["description"] = line.split(":", 1)[1].strip()
            info["ok"], info["kind"] = rc == 0, "deb"
            if info["ok"]:
                info["pkg"] = info["name"]
                rc2, out2, _ = run(["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${Version}", info["pkg"]])
                if rc2 == 0 and out2.strip().startswith("ii"):
                    info["installed"] = True
                    info["installedVersion"] = out2.split("|", 1)[1].strip() if "|" in out2 else ""
                    info["canRemove"] = info["pkg"] not in PROTECTED
        elif os.path.isfile(path) and low.endswith(".appimage"):
            info["ok"], info["kind"] = AI.is_appimage_file(path), "appimage"
            info["name"] = os.path.splitext(os.path.basename(path))[0]
            info["description"] = "AppImage"
            if info["ok"]:
                a = self._ai_match(path)
                if a:
                    info["installed"] = True
                    info["installedFile"] = str(a.file_path)
                    info["installedVersion"] = a.version
                    info["name"] = a.name
        return info

    def _inspect(self, p):
        self.fileInfo.emit(self._file_info(p))

    @Slot(str)
    def uninstallFile(self, path):
        """Elimina a app correspondente a um ficheiro DEB/AppImage já instalado."""
        self._bg(self._op, "file:" + path, os.path.basename(path), lambda cb: self._do_uninstall_file(path, cb))

    def _do_uninstall_file(self, path, cb):
        info = self._file_info(path)
        if not info["installed"]:
            return False, "not installed"
        if info["kind"] == "deb":
            return self._do_remove({"source": "apt", "pkg": info["pkg"]}, cb)
        f = info["installedFile"]
        try:
            AI.delete(f)
        except (OSError, ValueError) as exc:
            return False, str(exc)
        data = self._ai_load()
        for k in [k for k, d in data.items() if d.get("file") == f]:
            data.pop(k)
        self._ai_save(data)
        cb(100)
        return True, ""

    @Slot(str)
    def installFile(self, path):
        self._bg(self._op, "file:" + path, os.path.basename(path), lambda cb: self._do_file(path, cb))

    def _do_file(self, path, cb):
        if path.lower().endswith(".deb"):
            rc, msg = self._stream(self._apt(["install", "-y", path]), cb, "apt")
            return rc == 0, msg
        try:
            AI.add_appimage(path, copy=True, progress=cb)
        except (OSError, ValueError) as exc:
            return False, str(exc)
        cb(100)
        return True, ""

    # ----- página AppImage (equivalente ao Mainuan AppImage Manager) -----
    @staticmethod
    def _local(p):
        return QUrl(p).toLocalFile() if str(p).startswith("file:") else str(p)

    @Slot()
    def loadAppimages(self):
        self._bg(self._appimages)

    def _appimages(self):
        try:
            items = [a.to_dict() for a in AI.list_installed()]
        except OSError:
            items = []
        self.appimagesReady.emit(items)

    @Slot()
    def migrateAppimages(self):
        def job():
            try:
                if AI.migrate_legacy():
                    self._refresh_installed()
            except Exception:  # noqa: BLE001
                pass
            self._appimages()
        self._bg(job)

    @Slot(str, bool)
    def addAppimage(self, url, copy):
        self._bg(self._ai_add, self._local(url), bool(copy))

    def _ai_add(self, path, copy):
        name = os.path.basename(path)
        self.appimageBusy.emit(True, name, 5)
        try:
            app = AI.add_appimage(path, copy=copy,
                                  progress=lambda p: self.appimageBusy.emit(True, name, int(p)))
            self._ai_index(app.name, app)
            self._refresh_installed()
            self.appimageBusy.emit(False, "", 100)
            self.appimageResult.emit("add", True, app.name, str(app.file_path))
        except Exception as exc:  # noqa: BLE001
            self.appimageBusy.emit(False, "", 0)
            self.appimageResult.emit("add", False, str(exc), path)
        self._appimages()

    @Slot(str)
    def integrateAppimage(self, file):
        def job():
            self.appimageBusy.emit(True, os.path.basename(file), 30)
            try:
                app = AI.integrate_existing(file)
                self._refresh_installed()
                self.appimageBusy.emit(False, "", 100)
                self.appimageResult.emit("integrate", True, app.name if app else "", file)
            except Exception as exc:  # noqa: BLE001
                self.appimageBusy.emit(False, "", 0)
                self.appimageResult.emit("integrate", False, str(exc), file)
            self._appimages()
        self._bg(job)

    @Slot(str)
    def runAppimage(self, file):
        try:
            AI.run(file)
        except Exception as exc:  # noqa: BLE001
            self.appimageResult.emit("run", False, str(exc), file)

    @Slot(str)
    def deleteAppimage(self, file):
        def job():
            try:
                AI.delete(file)
                data = self._ai_load()
                for k in [k for k, d in data.items() if d.get("file") == file]:
                    data.pop(k)
                self._ai_save(data)
                self._refresh_installed()
                self.appimageResult.emit("delete", True, "", file)
            except Exception as exc:  # noqa: BLE001
                self.appimageResult.emit("delete", False, str(exc), file)
            self._appimages()
        self._bg(job)

    @Slot(str, "QVariantMap")
    def saveAppimage(self, file, vals):
        v = dict(vals)
        def job():
            try:
                AI.update_info(file, str(v.get("name", "")).strip(), str(v.get("version", "")).strip(),
                               str(v.get("comment", "")).strip(), str(v.get("categories", "")).strip() or "Utility;",
                               str(v.get("updateUrl", "")).strip(), bool(v.get("runAsRoot", False)))
                self.appimageResult.emit("save", True, "", file)
            except Exception as exc:  # noqa: BLE001
                self.appimageResult.emit("save", False, str(exc), file)
            self._appimages()
        self._bg(job)

    @Slot(str)
    def checkAppimageUpdate(self, file):
        def job():
            self.appimageUpdateInfo.emit(file, AI.check_update(file))
        self._bg(job)

    @Slot("QVariantList")
    def checkAllAppimageUpdates(self, files):
        def job():
            for f in list(files):
                self.appimageUpdateInfo.emit(str(f), AI.check_update(str(f)))
        self._bg(job)

    @Slot(str, "QVariantMap")
    def updateAppimage(self, file, info):
        inf = dict(info)
        def job():
            def prog(p):
                self.appimageUpdateState.emit(file, "downloading", int(p), "")
            try:
                if inf.get("mode") == "tool":
                    tool = shutil.which("appimageupdatetool") or shutil.which("AppImageUpdate")
                    self.appimageUpdateState.emit(file, "downloading", -1, "")
                    rc, out, err = run([tool, "--overwrite", file], timeout=1800)
                    if rc != 0:
                        raise RuntimeError((out + err).strip()[-200:] or "update failed")
                    AI.integrate_existing(file)
                else:
                    AI.download_update(file, inf.get("download_url", ""), inf.get("asset_name", ""), prog)
                self._refresh_installed()
                self.appimageUpdateState.emit(file, "done", 100, "")
            except Exception as exc:  # noqa: BLE001
                self.appimageUpdateState.emit(file, "failed", 0, str(exc))
            self._appimages()
        self._bg(job)

    # ----- atualizações -----
    @Slot()
    def refreshIndex(self):
        """Atualiza os repositórios APT, Flatpak (metadados) e AppImage (índice)."""
        def fn(cb):
            problems = []
            rc, msg = self._stream(self._apt(["update"]), lambda p: cb(p / 3.0), "apt")
            if msg == "cancelled":
                return False, "cancelled"
            if rc != 0:
                problems.append("APT: " + msg)
            cb(33)
            if self._src_ok("flatpak"):
                rc, msg = self._stream(["flatpak", "update", "--appstream", "-y", "--noninteractive"],
                                       lambda p: cb(33 + p / 3.0), "pct")
                if rc != 0:
                    problems.append("Flatpak: " + msg)
            cb(66)
            if self._ai_on and not self._feed_download():
                problems.append("AppImage")
            cb(100)
            return not problems, " ".join(problems)
        self._bg(self._op, "index", "repositories", fn)

    @Slot()
    def updateAll(self):
        items = list(self._last_updates)
        self._bg(self._op, "all", "updates", lambda cb: self._do_updates(items, cb))

    @Slot("QVariantList")
    def updateSelected(self, items):
        items = [dict(i) for i in items]
        self._bg(self._op, "sel", "updates", lambda cb: self._do_updates(items, cb))

    def _emit_item(self, iid, phase, pct=0):
        self.itemState.emit(iid, phase, int(pct))

    def _do_updates(self, items, cb):
        by = {}
        for i in items:
            by.setdefault(i.get("origin"), []).append(i)
            self._emit_item(i["id"], "waiting")
        order = [k for k in ("apt", "github", "flatpak", "appimage", "firmware") if by.get(k)]
        if not order:
            return True, ""
        n, ok, msg = len(order), True, ""
        for gi, kind in enumerate(order):
            def scaled(p, base=gi * 100.0 / n):
                cb(base + p / n)
            group = by[kind]
            if kind == "apt":
                pk = {i["variants"][0]["pkg"]: i["id"] for i in group}
                state, started = {}, [False]

                def emit(pkg, phase, pct=0, pk=pk, state=state):
                    if pkg in pk and state.get(pkg) != (phase, int(pct)):
                        state[pkg] = (phase, int(pct))
                        self._emit_item(pk[pkg], phase, pct)

                def hook(k, pkg, pct, m, pk=pk, state=state, started=started, emit=emit):
                    pkg = pkg.split(":")[0]
                    if k == "dl":
                        for p in pk:
                            if state.get(p, ("", 0))[0] in ("", "waiting", "download"):
                                emit(p, "download", pct)
                    else:
                        if not started[0]:
                            started[0] = True
                            for p in pk:
                                if p != pkg and state.get(p, ("", 0))[0] != "done":
                                    emit(p, "waiting", 0)
                        if pkg in pk:
                            emit(pkg, "done" if m.startswith("Installed") else "install",
                                 100 if m.startswith("Installed") else pct)
                rc, m = self._stream(self._apt(["install", "-y", "--only-upgrade"] + list(pk)),
                                     scaled, "apt", hook)
                if rc == 0:
                    for p in pk:
                        emit(p, "done", 100)
            elif kind == "github":
                rc, m = 0, ""
                for i in group:
                    iid, v = i["id"], i["variants"][0]
                    self._emit_item(iid, "update", 0)
                    ok_i, msg_i = self._gh_install(v, lambda p, iid=iid: self._emit_item(iid, "update", int(p)))
                    if ok_i:
                        self._emit_item(iid, "done", 100)
                    else:
                        rc, m = 1, msg_i
            elif kind == "appimage":
                rc, m = 0, ""
                for i in group:
                    iid, f = i["id"], i["variants"][0]["pkg"]
                    self._emit_item(iid, "update", 0)
                    info = self._ai_upd.get(f) or AI.check_update(f)
                    try:
                        if info.get("mode") == "tool":
                            tool = shutil.which("appimageupdatetool") or shutil.which("AppImageUpdate")
                            r, o, e = run([tool, "--overwrite", f], timeout=1800)
                            if r != 0:
                                raise RuntimeError((o + e).strip()[-200:] or "update failed")
                            AI.integrate_existing(f)
                        elif info.get("download_url"):
                            AI.download_update(f, info["download_url"], info.get("asset_name", ""),
                                               lambda p, iid=iid: self._emit_item(iid, "update", int(p)))
                        else:
                            raise RuntimeError("no update source")
                        self._emit_item(iid, "done", 100)
                    except Exception as exc:  # noqa: BLE001
                        rc, m = 1, str(exc)
            else:
                rc, m = 0, ""
                for i in group:
                    iid, pkg = i["id"], i["variants"][0]["pkg"]
                    self._emit_item(iid, "update", 0)
                    cmd = (["flatpak", "update", "-y", "--noninteractive", pkg] if kind == "flatpak"
                           else ["fwupdmgr", "update", "-y", "--no-reboot-check", pkg])
                    rc, m = self._stream(cmd, scaled, "pct", lambda k, p, pct, mm, iid=iid: self._emit_item(iid, "update", pct))
                    if rc == 0:
                        self._emit_item(iid, "done", 100)
            if rc != 0:
                ok, msg = False, m
        if ok:
            notifier.close_saved()          # terminou: fecha já a notificação do sistema
        try:
            self.collect_updates()          # atualiza o resumo (updates.json) usado pelo serviço do tabuleiro
        except Exception:  # noqa: BLE001
            pass
        return ok, msg

    # ----- fontes (Definições) -----
    @Slot()
    def loadSources(self):
        self._bg(self._sources)

    def _sources(self):
        flat = self._flat_refresh()
        fw = self._fw_remotes()
        self.sourcesReady.emit({
            "osname": self._os_name(), "flatpakPresent": bool(shutil.which("flatpak")),
            "fwupdPresent": bool(shutil.which("fwupdmgr")),
            "appimageOn": self._ai_on,
            "flatpak": flat, "firmware": fw, "apt": parse_apt_sources(),
        })

    def _simple(self, fn):
        self._bg(self._op, "src", "sources", lambda cb: fn())

    @Slot(str, bool, bool)
    def setFlatpakRemote(self, name, user, enabled):
        def fn():
            cmd = ["flatpak", "remote-modify"] + (["--user"] if user else []) + \
                  ["--enable" if enabled else "--disable", name]
            rc, _, err = run(cmd, 60)
            return rc == 0, err.strip()[-200:] if rc else ""
        self._simple(fn)

    @Slot(str)
    def addFlatpakRemote(self, url):
        def fn():
            name = os.path.splitext(os.path.basename(urlparse(url).path))[0] or "custom"
            rc, _, err = run(["flatpak", "remote-add", "--user", "--if-not-exists", name, url], 60)
            return rc == 0, err.strip()[-200:] if rc else ""
        self._simple(fn)

    @Slot(str, bool)
    def setFirmwareRemote(self, rid, enabled):
        def fn():
            rc, _, err = run(["pkexec", "fwupdmgr", "enable-remote" if enabled else "disable-remote", "-y", rid], 120)
            return rc == 0, "cancelled" if rc in (126, 127) else (err.strip()[-200:] if rc else "")
        self._simple(fn)

    @Slot(str, int, bool)
    def setAptSource(self, path, index, enabled):
        def fn():
            rc, _, err = run(["pkexec", HELPER, path, str(index), "yes" if enabled else "no"], 60)
            return rc == 0, "cancelled" if rc in (126, 127) else (err.strip()[-200:] if rc else "")
        self._simple(fn)

    # ----- abrir aplicação -----
    @Slot("QVariantMap", str)
    def launch(self, item, source):
        v = self._variant_of(dict(item), source) or {}
        pkg, cmd = v.get("pkg", ""), None
        if source == "flatpak":
            cmd = ["flatpak", "run", pkg]
        elif source == "appimage":
            f = self._ai_file_for(pkg)
            if f:
                AI.run(f)
            cmd = None
        else:
            rc, out, _ = run(["dpkg-query", "-L", pkg])
            desk = [l for l in out.splitlines()
                    if l.startswith("/usr/share/applications/") and l.endswith(".desktop")]
            if desk:
                cmd = ["gio", "launch", desk[0]]
        if cmd:
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
