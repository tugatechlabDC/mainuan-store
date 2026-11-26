"""Gestão de AppImages da Mainuan Store (sem dependências Qt).

Baseado no Mainuan AppImage Manager, com correções para Ubuntu/Kubuntu:
  * lançador (appimage-run) que contorna a falta de FUSE 2 (libfuse2) e o bloqueio de
    "user namespaces" do Ubuntu 23.10+/24.04 que impede as apps Electron de arrancar;
  * entradas .desktop válidas (Exec com aspas/escapes) para aparecerem no menu iniciar;
  * ícone extraído do AppImage e cache de menus atualizada (GNOME/KDE).
Pasta dos AppImages: /appimage (raiz do disco), protegida: pertence ao root e o utilizador
não pode apagar nem alterar o conteúdo enquanto houver AppImages configuradas na loja. Todas as
alterações (adicionar, atualizar, remover) passam pelo helper.py via pkexec.
"""
import dataclasses
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

HOME = Path.home()
APPIMAGES_DIR = Path("/appimage")
HOME_APPIMAGES = HOME / "AppImages"          # pasta usada até à versão 0.6.2
LEGACY_DIR = HOME / "Applications"          # pasta usada pelas versões antigas da loja
DESKTOP_DIR = HOME / ".local" / "share" / "applications"
STORE_DATA = HOME / ".local" / "share" / "mainuan-store"
ICONS_DIR = STORE_DATA / "icons"
HELPER = Path(__file__).resolve().parent / "helper.py"
TMP_DIR = HOME / ".cache" / "mainuan-store" / "appimage"
RUN_SCRIPT = STORE_DATA / "appimage-run"
PKG_RUN_SCRIPT = Path(__file__).resolve().parent / "appimage-run"
UA = {"User-Agent": "MainuanStore/appimage"}
DESKTOP_PREFIX = "mainuan-appimage-"


@dataclasses.dataclass
class AppImage:
    name: str
    file_path: Path
    icon_path: Optional[Path]
    desktop_file_path: Optional[Path]
    appimage_type: str
    size: int
    version: str = ""
    comment: str = ""
    categories: str = "Utility;"
    update_url: str = ""
    run_as_root: bool = False
    electron: bool = False

    def to_dict(self):
        return {
            "name": self.name,
            "file": str(self.file_path),
            "filename": self.file_path.name,
            "icon": ("file://" + str(self.icon_path)) if self.icon_path else "",
            "integrated": self.desktop_file_path is not None,
            "type": self.appimage_type,
            "size": self.size,
            "sizeText": "%.1f MB" % (self.size / (1024 * 1024)),
            "version": self.version,
            "comment": self.comment,
            "categories": self.categories,
            "updateUrl": self.update_url,
            "runAsRoot": self.run_as_root,
        }


# ------------------------------------------------------------------ utilidades
def safe_name(name):
    return re.sub(r"[^a-z0-9_-]", "_", (name or "").lower()) or "app"


def is_appimage_file(path):
    """True se o ficheiro é um ELF com a marca AppImage (tipo 1 ou 2)."""
    try:
        with open(path, "rb") as f:
            head = f.read(11)
        return head[:4] == b"\x7fELF" and head[8:10] == b"AI" and head[10:11] in (b"\x01", b"\x02")
    except OSError:
        return False


def appimage_type(path):
    try:
        with open(path, "rb") as f:
            magic = f.read(11)[-3:]
        if magic == b"\x41\x49\x01":
            return "1"
        if magic == b"\x41\x49\x02":
            return "2"
    except OSError:
        pass
    return "?"


def exec_quote(path):
    """Argumento do campo Exec= de um .desktop (aspas, escapes e %% conforme a especificação)."""
    s = str(path)
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    s = s.replace("%", "%%")
    s = s.replace("\\", "\\\\")  # escape ao nível do ficheiro .desktop
    return '"' + s + '"'


def value_clean(text):
    """Remove quebras de linha de um valor de .desktop."""
    return re.sub(r"[\r\n]+", " ", str(text or "")).strip()


def parse_desktop_file(path):
    entry = {}
    try:
        inside = False
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line == "[Desktop Entry]":
                    inside = True
                    continue
                if line.startswith("[") and inside:
                    break
                if inside and "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    entry[k.strip()] = v.strip()
    except OSError:
        pass
    return entry


def ensure_launcher():
    """Copia o lançador para ~/.local/share/mainuan-store (as entradas do menu continuam a
    funcionar mesmo que a loja seja removida). Devolve o caminho a usar no Exec."""
    try:
        STORE_DATA.mkdir(parents=True, exist_ok=True)
        want = PKG_RUN_SCRIPT.read_bytes()
        try:
            have = RUN_SCRIPT.read_bytes()
        except OSError:
            have = b""
        if have != want:
            tmp = RUN_SCRIPT.with_suffix(".tmp")
            tmp.write_bytes(want)
            tmp.chmod(0o755)
            tmp.replace(RUN_SCRIPT)
        RUN_SCRIPT.chmod(0o755)
        return RUN_SCRIPT
    except OSError:
        return PKG_RUN_SCRIPT


def exec_line(appimage_path, run_as_root=False, electron=False):
    parts = [exec_quote(ensure_launcher())]
    if electron:
        parts.append("--electron")
    if run_as_root:
        parts.append("--root")
    parts.append(exec_quote(appimage_path))
    parts.append("%U")
    return " ".join(parts)


def refresh_menus():
    """Atualiza as caches de aplicações para a entrada aparecer logo no menu iniciar."""
    for cmd in (["update-desktop-database", "-q", str(DESKTOP_DIR)],):
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    # KDE (Kubuntu): reconstrói a cache de serviços sem bloquear
    for tool in ("kbuildsycoca6", "kbuildsycoca5"):
        if shutil.which(tool):
            try:
                subprocess.Popen([tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            except OSError:
                pass
            break
    # GNOME/Ubuntu: avisa o menu de que a pasta mudou
    try:
        os.utime(str(DESKTOP_DIR), None)
    except OSError:
        pass


def write_desktop_file(desktop_path, name, appimage_path, icon, comment, categories, version,
                       update_url="", run_as_root=False, electron=False):
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=" + value_clean(name),
        "Exec=" + exec_line(appimage_path, run_as_root, electron),
        "TryExec=" + value_clean(appimage_path),
        "Icon=" + value_clean(icon),
        "Terminal=false",
        "StartupNotify=true",
        "Categories=" + (value_clean(categories) or "Utility;"),
    ]
    if comment:
        lines.append("Comment=" + value_clean(comment))
    if version:
        lines.append("X-AppImage-Version=" + value_clean(version))
    if update_url:
        lines.append("X-AppImage-UpdateUrl=" + value_clean(update_url))
    if run_as_root:
        lines.append("X-AppImage-RunAsRoot=true")
    if electron:
        lines.append("X-Mainuan-Electron=true")
    lines.append("X-AppImage-Integrate=true")
    lines.append("X-Mainuan-AppImage=true")
    lines.append("")
    tmp = Path(str(desktop_path) + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.chmod(0o755)
    tmp.replace(desktop_path)


# ------------------------------------------------------------------ extração de metadados
def _run_extract(appimage_path, cwd, pattern=None, timeout=180):
    cmd = [str(appimage_path), "--appimage-extract"]
    if pattern:
        cmd.append(pattern)
    env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
    try:
        subprocess.run(cmd, cwd=str(cwd), timeout=timeout, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def _extract_appimage(appimage_path, tmp_dir):
    """Extrai só o necessário (desktop, ícones, chrome-sandbox). Devolve squashfs-root ou None."""
    root = Path(tmp_dir) / "squashfs-root"
    seven = shutil.which("7zz") or shutil.which("7z")
    if seven:
        try:
            subprocess.run([seven, "x", str(appimage_path), "-o" + str(root), "-y", "-bso0", "-bsp0",
                            "-ir!*.png", "-ir!*.svg", "-ir!*.desktop", "-ir0!.DirIcon", "-ir!chrome-sandbox"],
                           cwd=str(tmp_dir), timeout=90, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
        if root.exists() and list(root.rglob("*.desktop")):
            return root
    for pattern in ("*.desktop", ".DirIcon", "chrome-sandbox"):
        _run_extract(appimage_path, tmp_dir, pattern, timeout=90)
    desktops = list(root.glob("*.desktop")) or list(root.rglob("*.desktop")) if root.exists() else []
    if desktops:
        entry = parse_desktop_file(desktops[0])
        icon = re.sub(r"\.(png|svg|xpm)$", "", entry.get("Icon", "").strip())
        pats = ["usr/share/icons/hicolor/*/apps/*", "usr/share/pixmaps/*"]
        if icon:
            pats = [icon + ".png", icon + ".svg"] + pats
        for pattern in pats:
            _run_extract(appimage_path, tmp_dir, pattern, timeout=90)
        return root
    # último recurso: extração completa (só se houver espaço livre)
    try:
        need = os.path.getsize(appimage_path) * 3
        if shutil.disk_usage(str(tmp_dir)).free > need:
            _run_extract(appimage_path, tmp_dir, None, timeout=600)
    except OSError:
        pass
    return root if root.exists() else None


def _find_icon(root, icon_name):
    name_lower = icon_name.lower()
    diricon = root / ".DirIcon"
    if diricon.is_symlink():
        try:
            target = os.readlink(str(diricon))
            real = Path(target) if os.path.isabs(target) else (diricon.parent / target).resolve()
            if real.is_file() and str(real).startswith(str(root.resolve())):
                return real
        except OSError:
            pass
    elif diricon.is_file():
        return diricon
    if icon_name:
        for ext in (".svg", ".png"):
            cand = root / (icon_name + ext)
            if cand.exists():
                return cand
        for f in root.iterdir():
            if f.suffix.lower() in (".svg", ".png") and f.stem.lower() == name_lower:
                return f
        hicolor = root / "usr" / "share" / "icons" / "hicolor"
        for size in ("scalable/apps", "512x512/apps", "256x256/apps", "128x128/apps", "64x64/apps", "48x48/apps"):
            for ext in (".png", ".svg"):
                d = hicolor / size
                if (d / (icon_name + ext)).exists():
                    return d / (icon_name + ext)
                if d.exists():
                    for f in d.iterdir():
                        if f.suffix.lower() == ext and f.stem.lower() == name_lower:
                            return f
        pix = root / "usr" / "share" / "pixmaps"
        if pix.exists():
            for f in pix.iterdir():
                if f.suffix.lower() in (".png", ".svg") and f.stem.lower() == name_lower:
                    return f
    for ext in ("*.png", "*.svg"):
        cands = [c for c in root.rglob(ext) if c.is_file()]
        if cands:
            for c in cands:
                if c.stem.lower() == name_lower:
                    return c
            return cands[0]
    return None


def extract_metadata(appimage_path, app_id):
    """Nome, ícone (copiado para ~/AppImages/.icons), versão, comentário, categorias, Electron."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="mainuan-appimage-"))
    try:
        root = _extract_appimage(appimage_path, tmp_dir)
        if not root:
            return {}
        electron = (root / "chrome-sandbox").exists()
        desktops = list(root.glob("*.desktop")) or list(root.rglob("*.desktop"))
        entry = parse_desktop_file(desktops[0]) if desktops else {}
        icon_name = re.sub(r"\.(png|svg)$", "", entry.get("Icon", "").strip())
        icon_dest = None
        icon_src = _find_icon(root, icon_name)
        if icon_src and icon_src.is_file():
            ICONS_DIR.mkdir(parents=True, exist_ok=True)
            suffix = icon_src.suffix.lower() if icon_src.suffix.lower() in (".png", ".svg") else ".png"
            icon_dest = ICONS_DIR / (app_id + suffix)
            shutil.copy2(str(icon_src), str(icon_dest))
        return {
            "name": entry.get("Name") or "",
            "icon_path": str(icon_dest) if icon_dest else None,
            "version": entry.get("X-AppImage-Version", ""),
            "comment": entry.get("Comment", ""),
            "categories": entry.get("Categories", "Utility;") or "Utility;",
            "electron": electron,
        }
    except Exception:  # noqa: BLE001
        return {}
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


# ------------------------------------------------------------------ pasta protegida
def _helper(*args):
    """Corre o helper como root (pkexec). Levanta OSError se falhar ou for cancelado."""
    r = subprocess.run(["pkexec", str(HELPER), "appimage", *map(str, args)],
                       capture_output=True, text=True)
    if r.returncode == 126 or r.returncode == 127:
        raise OSError("authorization cancelled")
    if r.returncode == 17:
        raise FileExistsError(args[2] if len(args) > 2 else "")
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout or "helper failed").strip())


def put_file(source, name, replace=False):
    """Copia `source` para /appimage/<name> (root, 0755, protegido)."""
    _helper("put", source, name, *(["replace"] if replace else []))


def remove_file(name):
    _helper("rm", name)


def _ensure_dirs():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)


def _unique(path):
    if not path.exists():
        return path
    i = 1
    while True:
        cand = path.with_name("%s_%d%s" % (path.stem, i, path.suffix))
        if not cand.exists():
            return cand
        i += 1


def _desktop_for(app_id, file_path):
    """Ficheiro .desktop já existente para este AppImage (ou um novo nome único)."""
    for dp in DESKTOP_DIR.glob("*.desktop"):
        entry = parse_desktop_file(dp)
        ex = entry.get("TryExec", "")
        if ex == str(file_path):
            return dp
    return _unique(DESKTOP_DIR / ("%s%s.desktop" % (DESKTOP_PREFIX, app_id)))


def _from_entry(path, dp, entry):
    icon_path = None
    raw = entry.get("Icon", "")
    if raw and os.path.isabs(raw) and os.path.exists(raw):
        icon_path = Path(raw)
    return AppImage(
        name=entry.get("Name") or path.stem,
        file_path=path,
        icon_path=icon_path,
        desktop_file_path=dp,
        appimage_type=appimage_type(path),
        size=path.stat().st_size,
        version=entry.get("X-AppImage-Version", ""),
        comment=entry.get("Comment", ""),
        categories=entry.get("Categories", "Utility;") or "Utility;",
        update_url=entry.get("X-AppImage-UpdateUrl", ""),
        run_as_root=entry.get("X-AppImage-RunAsRoot", "").lower() == "true",
        electron=entry.get("X-Mainuan-Electron", "").lower() == "true",
    )


def list_installed():
    _ensure_dirs()
    desktop_map = {}
    for dp in DESKTOP_DIR.glob("*.desktop"):
        entry = parse_desktop_file(dp)
        target = entry.get("TryExec") or ""
        if target.startswith(str(APPIMAGES_DIR)):
            desktop_map[target] = (dp, entry)
    result = []
    try:
        listing = sorted(APPIMAGES_DIR.iterdir(), key=lambda x: x.name.lower())
    except OSError:
        listing = []
    for p in listing:
        if p.suffix.lower() != ".appimage" or not p.is_file():
            continue
        try:
            if str(p) in desktop_map:
                dp, entry = desktop_map[str(p)]
                result.append(_from_entry(p, dp, entry))
            else:
                result.append(AppImage(name=p.stem, file_path=p, icon_path=None, desktop_file_path=None,
                                       appimage_type=appimage_type(p), size=p.stat().st_size))
        except OSError:
            pass
    return result


def find(file_path):
    fp = str(file_path)
    for a in list_installed():
        if str(a.file_path) == fp:
            return a
    return None


def _integrate(dest, display_name=None):
    """Extrai metadados e cria a entrada no menu para um AppImage já em /appimage."""
    meta = extract_metadata(dest, safe_name(dest.stem))
    name = meta.get("name") or display_name or dest.stem
    app_id = safe_name(name)
    icon = Path(meta["icon_path"]) if meta.get("icon_path") else None
    # o ícone fica com o nome final da app
    if icon and icon.stem != app_id:
        new_icon = ICONS_DIR / (app_id + icon.suffix)
        try:
            shutil.move(str(icon), str(new_icon))
            icon = new_icon
        except OSError:
            pass
    desktop = _desktop_for(app_id, dest)
    write_desktop_file(desktop, name, dest, str(icon) if icon else "application-x-executable",
                       meta.get("comment", ""), meta.get("categories", "Utility;"),
                       meta.get("version", ""), electron=bool(meta.get("electron")))
    refresh_menus()
    return find(dest)


def add_appimage(source, copy=True, display_name=None, progress=None):
    """Copia/move um AppImage para /appimage (via helper) e integra-o no menu."""
    _ensure_dirs()
    source = Path(source)
    if not source.is_file():
        raise ValueError("file not found")
    if not is_appimage_file(source):
        raise ValueError("not an AppImage")
    if source.parent.resolve() == APPIMAGES_DIR.resolve():
        dest = source
    else:
        dest = _unique(APPIMAGES_DIR / (source.stem + ".AppImage"))
        if progress:
            progress(5)
        put_file(str(source), dest.name)
        if not copy:
            try:
                source.unlink()
            except OSError:
                pass
    if progress:
        progress(60)
    app = _integrate(dest, display_name)
    if progress:
        progress(100)
    return app


def integrate_existing(file_path):
    dest = Path(file_path)
    if not is_appimage_file(dest):
        raise ValueError("not an AppImage")
    return _integrate(dest)


def migrate_legacy():
    """Move os AppImages das versões anteriores (~/Applications e ~/AppImages) para /appimage
    (pasta protegida) e volta a integrá-los. Devolve o número de AppImages migrados."""
    moved = 0
    for old_dir in (LEGACY_DIR, HOME_APPIMAGES):
        if not old_dir.is_dir():
            continue
        for p in list(old_dir.iterdir()):
            if p.suffix.lower() != ".appimage" or not p.is_file() or not is_appimage_file(p):
                continue
            try:
                _ensure_dirs()
                dest = _unique(APPIMAGES_DIR / p.name)
                put_file(str(p), dest.name)
                for dp in list(DESKTOP_DIR.glob("*.desktop")):
                    ex = parse_desktop_file(dp)
                    if ex.get("TryExec") == str(p) and dp.name.startswith(DESKTOP_PREFIX):
                        dp.unlink()
                p.unlink()
                _integrate(dest, p.stem)
                moved += 1
            except (OSError, ValueError):
                pass
        # entradas antigas do menu que ainda apontam para a pasta antiga e já não existem
        for dp in DESKTOP_DIR.glob(DESKTOP_PREFIX + "*.desktop"):
            entry = parse_desktop_file(dp)
            if str(old_dir) in entry.get("Exec", "") and not Path(entry.get("TryExec", "/nonexistent")).exists():
                try:
                    dp.unlink()
                    moved += 1
                except OSError:
                    pass
        # ícones antigos de ~/AppImages/.icons deixam de ser necessários
        if old_dir == HOME_APPIMAGES:
            shutil.rmtree(str(old_dir / ".icons"), ignore_errors=True)
        try:
            old_dir.rmdir()
        except OSError:
            pass
    if moved:
        refresh_menus()
    return moved


def run(file_path):
    a = find(file_path)
    if a and a.desktop_file_path and a.desktop_file_path.exists():
        cmd = ["gio", "launch", str(a.desktop_file_path)] if shutil.which("gio") else None
        if cmd is None and shutil.which("gtk-launch"):
            cmd = ["gtk-launch", a.desktop_file_path.name]
        if cmd:
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    ensure_launcher()
    args = [str(ensure_launcher())] + (["--electron"] if (a and a.electron) else []) + [str(file_path)]
    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def delete(file_path):
    a = find(file_path)
    if not a:
        raise ValueError("not found")
    if a.desktop_file_path and a.desktop_file_path.exists():
        a.desktop_file_path.unlink()
    if a.icon_path and a.icon_path.exists() and str(a.icon_path).startswith(str(ICONS_DIR)):
        a.icon_path.unlink()
    if a.file_path.exists():
        remove_file(a.file_path.name)
    refresh_menus()


def update_info(file_path, name, version, comment, categories, update_url, run_as_root=False):
    a = find(file_path)
    if not a or not a.desktop_file_path:
        raise ValueError("not integrated")
    write_desktop_file(a.desktop_file_path, name or a.name, a.file_path,
                       str(a.icon_path) if a.icon_path else "application-x-executable",
                       comment, categories or "Utility;", version, update_url, run_as_root, a.electron)
    refresh_menus()
    return find(file_path)


# ------------------------------------------------------------------ atualizações
def _parse_github_url(url):
    m = re.match(r"https?://github\.com/([^/]+)/([^/?#\s]+)", url)
    return (m.group(1), re.sub(r"\.git$", "", m.group(2))) if m else None


def _parse_gitlab_url(url):
    m = re.match(r"https?://gitlab\.com/([^/]+)/([^/?#\s]+)", url)
    return (m.group(1), re.sub(r"\.git$", "", m.group(2)), "/-/packages" in url) if m else None


def _parse_codeberg_url(url):
    m = re.match(r"https?://codeberg\.org/([^/]+)/([^/?#\s]+)", url)
    return ("codeberg.org", m.group(1), re.sub(r"\.git$", "", m.group(2))) if m else None


def update_mode(a):
    url = a.update_url
    if url:
        if _parse_github_url(url) or _parse_gitlab_url(url) or _parse_codeberg_url(url):
            return "api"
        if url.lower().endswith(".appimage"):
            return "direct"
    if shutil.which("appimageupdatetool") or shutil.which("AppImageUpdate"):
        return "tool"
    return "none"


def _ver(v):
    return [int(x) for x in re.sub(r"[^\d]+", ".", v).split(".") if x]


def check_update_api(a):
    url = a.update_url or ""
    gh, gl, cb = _parse_github_url(url), _parse_gitlab_url(url), _parse_codeberg_url(url)
    headers = dict(UA)
    if gh:
        api = "https://api.github.com/repos/%s/%s/releases/latest" % gh
        headers["Accept"] = "application/vnd.github+json"
    elif cb:
        api = "https://%s/api/v1/repos/%s/%s/releases?limit=1" % cb
    elif gl:
        enc = "%s%%2F%s" % (gl[0], gl[1])
        api = ("https://gitlab.com/api/v4/projects/%s/packages?sort=desc&order_by=created_at&per_page=10" % enc
               if gl[2] else "https://gitlab.com/api/v4/projects/%s/releases" % enc)
    else:
        return {"has_update": None, "message": "Not a valid GitHub, GitLab or Codeberg URL"}
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers=headers), timeout=15) as r:
            data = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        return {"has_update": None, "message": str(exc)}

    assets, latest = [], ""
    if cb:
        rels = data if isinstance(data, list) else [data]
        if not rels:
            return {"has_update": None, "message": "No releases found"}
        latest = rels[0].get("tag_name", "").lstrip("v")
        assets = [{"name": x["name"], "url": x.get("browser_download_url", ""), "size": x.get("size", 0)}
                  for x in rels[0].get("assets", []) if x.get("name", "").lower().endswith(".appimage")]
    elif gl:
        enc = "%s%%2F%s" % (gl[0], gl[1])
        if gl[2]:
            for pkg in (data if isinstance(data, list) else [data]):
                try:
                    req = urllib.request.Request(
                        "https://gitlab.com/api/v4/projects/%s/packages/%s/package_files" % (enc, pkg.get("id")),
                        headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as r:
                        files = json.loads(r.read())
                except Exception:  # noqa: BLE001
                    continue
                for f in files:
                    fn = f.get("file_name", "")
                    if fn.lower().endswith(".appimage"):
                        assets.append({"name": fn, "size": f.get("size", 0), "url":
                                       "https://gitlab.com/api/v4/projects/%s/packages/generic/%s/%s/%s"
                                       % (enc, pkg.get("name"), pkg.get("version"), fn)})
                if assets:
                    latest = pkg.get("version", "")
                    break
        else:
            if not isinstance(data, list) or not data:
                return {"has_update": None, "message": "No releases found on GitLab"}
            latest = data[0].get("tag_name", "").lstrip("v")
            for link in data[0].get("assets", {}).get("links", []):
                if ".appimage" in link.get("name", "").lower() or ".appimage" in link.get("url", "").lower():
                    assets.append({"name": link.get("name", ""), "url": link.get("url", ""), "size": 0})
    else:
        latest = data.get("tag_name", "").lstrip("v")
        assets = [{"name": x["name"], "url": x["browser_download_url"], "size": x.get("size", 0)}
                  for x in data.get("assets", []) if x["name"].lower().endswith(".appimage")]
    if not assets:
        return {"has_update": None, "message": "No AppImage assets found in the latest release"}

    current = (a.version or "").lstrip("v")
    if not current:
        m = re.search(r"[-_]v?(\d+\.\d+(?:\.\d+)?)", a.file_path.stem)
        current = m.group(1) if m else ""
    if not current:
        return {"has_update": None, "latest_version": latest,
                "message": "Cannot determine current version to compare against v%s." % latest}
    try:
        has = _ver(latest) > _ver(current)
    except Exception:  # noqa: BLE001
        has = latest != current
    aliases = {"x86_64": ["x86_64", "amd64", "x64"], "aarch64": ["aarch64", "arm64"]}
    pref = aliases.get(platform.machine().lower(), [platform.machine().lower()])
    best = next((x for x in assets if any(p in x["name"].lower() for p in pref)), assets[0])
    return {"has_update": has, "message": "v%s  (v%s)" % (latest, current), "latest_version": latest,
            "download_url": best["url"], "asset_name": best["name"], "asset_size": best.get("size", 0)}


def check_update_direct(a):
    url = a.update_url or ""
    name = Path(urlparse(url).path).name or a.file_path.name
    if not name.lower().endswith(".appimage"):
        name += ".AppImage"
    try:
        req = urllib.request.Request(url, headers=UA, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            last = r.headers.get("Last-Modified")
            length = int(r.headers.get("Content-Length", 0))
    except Exception as exc:  # noqa: BLE001
        return {"has_update": None, "message": str(exc)}
    has, msg = True, ""
    if last:
        try:
            import datetime
            remote = parsedate_to_datetime(last)
            local = datetime.datetime.fromtimestamp(a.file_path.stat().st_mtime, tz=datetime.timezone.utc)
            has = remote > local
            msg = remote.strftime("%Y-%m-%d") if has else ""
        except Exception:  # noqa: BLE001
            has = True
    return {"has_update": has, "message": msg, "latest_version": "", "download_url": url,
            "asset_name": name, "asset_size": length}


def check_update_tool(a):
    tool = shutil.which("appimageupdatetool") or shutil.which("AppImageUpdate")
    if not tool:
        return {"has_update": None, "message": "appimageupdatetool is not installed"}
    try:
        r = subprocess.run([tool, "--check-for-update", str(a.file_path)], capture_output=True,
                           text=True, timeout=30)
        out = (r.stdout + r.stderr).strip()
        if r.returncode == 1:
            return {"has_update": True, "message": out, "tool": True}
        if r.returncode == 0:
            return {"has_update": False, "message": out, "tool": True}
        return {"has_update": None, "message": out or "No update information found in binary"}
    except subprocess.TimeoutExpired:
        return {"has_update": None, "message": "Timeout while checking for updates"}
    except OSError as exc:
        return {"has_update": None, "message": str(exc)}


def check_update(file_path):
    a = find(file_path)
    if not a:
        return {"has_update": None, "message": "not found", "mode": "none"}
    mode = update_mode(a)
    if mode == "api":
        res = check_update_api(a)
    elif mode == "direct":
        res = check_update_direct(a)
    elif mode == "tool":
        res = check_update_tool(a)
    else:
        res = {"has_update": None, "message": "no source"}
    res["mode"] = mode
    return res


def download_update(file_path, url, asset_name, progress=None, cancelled=None):
    """Descarrega a nova versão, valida-a, substitui a antiga e volta a integrar."""
    a = find(file_path)
    if not a:
        raise ValueError("not found")
    if not asset_name.lower().endswith(".appimage"):
        asset_name += ".AppImage"
    new_path = APPIMAGES_DIR / asset_name
    if new_path.exists() and new_path != a.file_path:
        new_path = _unique(new_path)
    _ensure_dirs()
    tmp = TMP_DIR / (new_path.name + ".part")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                if cancelled and cancelled():
                    raise RuntimeError("cancelled")
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done * 100.0 / total)
        if not is_appimage_file(tmp):
            raise ValueError("downloaded file is not an AppImage")
        old_icon, old_desktop = a.icon_path, a.desktop_file_path
        meta = dict(name=a.name, update_url=a.update_url, run_as_root=a.run_as_root)
        put_file(str(tmp), new_path.name, replace=(new_path == a.file_path))
        if a.file_path.exists() and a.file_path != new_path:
            remove_file(a.file_path.name)
        if old_desktop and old_desktop.exists():
            old_desktop.unlink()
        fresh = _integrate(new_path, meta["name"])
        if fresh and (meta["update_url"] or meta["run_as_root"]):
            update_info(fresh.file_path, fresh.name, fresh.version, fresh.comment, fresh.categories,
                        meta["update_url"], meta["run_as_root"])
        return str(new_path)
    finally:
        tmp.unlink(missing_ok=True)
