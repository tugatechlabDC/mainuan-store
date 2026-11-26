#!/usr/bin/python3
"""Programa auxiliar da Mainuan Store (corre como root via pkexec).

Modos:
  helper.py apt <ficheiro-cancelar> <argumentos apt-get>      (instalar/remover/atualizar com cancelamento)
  helper.py flatpak <ficheiro-cancelar> <argumentos flatpak>  (instalação system-wide com palavra-passe)
  helper.py <ficheiro> <índice> <yes|no>                      (ativar/desativar fonte APT)

  helper.py appimage put <origem> <nome.AppImage> [replace]  (copia para /appimage, protegido)
  helper.py appimage rm <nome.AppImage>                       (remove de /appimage)
  helper.py appimage sync                                     (reaplica a proteção)

Só aceita argumentos de uma lista restrita; recusa tudo o resto."""
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:~-]*$")
APT_SUB = {"install", "remove", "update", "upgrade"}
APT_FLAGS = {"-y", "--only-upgrade"}
APT_OPT_VALUES = {"APT::Status-Fd=1", "Dpkg::Use-Pty=0"}
FLATPAK_SUB = {"install", "uninstall", "update"}
FLATPAK_FLAGS = {"--system", "-y", "--noninteractive", "--appstream"}


def toggle_sources(text, idx, flag):
    stanzas = re.split(r"\n\s*\n", text.strip("\n"))
    lines = [l for l in stanzas[idx].split("\n") if not l.lower().startswith("enabled:")]
    lines.append("Enabled: " + flag)
    stanzas[idx] = "\n".join(lines)
    return "\n\n".join(stanzas) + "\n"


def toggle_list(text, idx, flag):
    lines = text.split("\n")
    m = re.match(r"^(\s*)(#\s*)?(deb\s+.*)$", lines[idx])
    if not m:
        raise ValueError("linha inválida")
    lines[idx] = m.group(1) + ("" if flag == "yes" else "# ") + m.group(3)
    return "\n".join(lines)


def valid_apt(args):
    i = 0
    while i < len(args) and args[i] == "-o":
        if i + 1 >= len(args) or args[i + 1] not in APT_OPT_VALUES:
            return False
        i += 2
    if i >= len(args) or args[i] not in APT_SUB:
        return False
    for a in args[i + 1:]:
        if a in APT_FLAGS or NAME_RE.match(a):
            continue
        if a.startswith("/") and a.endswith(".deb") and "\0" not in a and os.path.isfile(a):
            continue
        return False
    return True


def valid_flatpak(args):
    if not args or args[0] not in FLATPAK_SUB:
        return False
    return all(a in FLATPAK_FLAGS or NAME_RE.match(a) for a in args[1:])


def valid_cancel(path):
    return (os.path.basename(path).startswith("cancel-")
            and os.path.dirname(path).endswith("/.cache/mainuan-store")
            and not os.path.islink(path))


def run_guarded(prog, args, cancel):
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "DEBIAN_FRONTEND": "noninteractive",
           "HOME": "/root", "LANG": "C.UTF-8"}
    p = subprocess.Popen([prog] + args, env=env)
    while True:
        try:
            return p.wait(timeout=0.3)
        except subprocess.TimeoutExpired:
            pass
        if os.path.exists(cancel):
            p.send_signal(signal.SIGINT)
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.terminate()
                p.wait(timeout=10)
            return 130


def toggle_main(argv):
    if len(argv) != 3:
        return 2
    path, flag = argv[0], argv[2]
    real = os.path.realpath(path)
    allowed = real == "/etc/apt/sources.list" or (
        real.startswith("/etc/apt/sources.list.d/") and real.endswith((".list", ".sources")))
    if not allowed or flag not in ("yes", "no"):
        return 2
    try:
        idx = int(argv[1])
        with open(real, encoding="utf-8") as f:
            text = f.read()
        new = toggle_sources(text, idx, flag) if real.endswith(".sources") else toggle_list(text, idx, flag)
        tmp = real + ".mainuan-tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.chmod(tmp, 0o644)
        os.replace(tmp, real)
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- pasta /appimage
APPDIR = "/appimage"
AI_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+()-]{0,200}\.[Aa]pp[Ii]mage$")


def _chattr(flag, *paths):
    """Atributo imutável (melhor esforço: nem todos os sistemas de ficheiros o suportam)."""
    try:
        subprocess.run(["chattr", flag] + [p for p in paths if os.path.lexists(p)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def _ai_files():
    try:
        return [os.path.join(APPDIR, n) for n in sorted(os.listdir(APPDIR))
                if AI_NAME_RE.match(n) and os.path.isfile(os.path.join(APPDIR, n))
                and not os.path.islink(os.path.join(APPDIR, n))]
    except OSError:
        return []


def ai_unlock():
    os.makedirs(APPDIR, exist_ok=True)
    _chattr("-i", APPDIR, *_ai_files())


def ai_lock():
    """Regra: enquanto houver AppImages configuradas, a pasta e o seu conteúdo ficam
    com dono root, sem escrita para o utilizador e imutáveis. Sem AppImages, a pasta fica livre."""
    os.makedirs(APPDIR, exist_ok=True)
    files = _ai_files()
    os.chown(APPDIR, 0, 0)
    os.chmod(APPDIR, 0o755)
    for f in files:
        os.chown(f, 0, 0)
        os.chmod(f, 0o755)
    if files:
        _chattr("+i", *files)
        _chattr("+i", APPDIR)


def _caller():
    try:
        uid = int(os.environ.get("PKEXEC_UID", ""))
        return uid, pwd.getpwuid(uid).pw_gid
    except (ValueError, KeyError):
        return None, None


def _open_as_caller(path):
    """Abre o ficheiro de origem com as permissões do utilizador (nunca como root)."""
    uid, gid = _caller()
    if uid is None or uid == 0:
        return None
    os.setegid(gid)
    os.seteuid(uid)
    try:
        return os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    finally:
        os.seteuid(0)
        os.setegid(0)


def ai_put(argv):
    if len(argv) < 2 or not AI_NAME_RE.match(argv[1]) or "/" in argv[1]:
        return 2
    src, name = argv[0], argv[1]
    replace = len(argv) > 2 and argv[2] == "replace"
    if not os.path.isabs(src) or os.path.realpath(src).startswith(APPDIR + "/"):
        return 2
    fd = _open_as_caller(src)
    if fd is None:
        return 2
    try:
        st = os.fstat(fd)
        if not os.path.isfile(src) or st.st_size < 1024:
            return 2
        with os.fdopen(os.dup(fd), "rb") as f:
            if f.read(4) != b"\x7fELF":
                return 2
            f.seek(0)
            ai_unlock()
            dest = os.path.join(APPDIR, name)
            if os.path.lexists(dest) and not replace:
                ai_lock()
                return 17
            tmp = dest + ".mainuan-part"
            with open(tmp, "wb") as out:
                shutil.copyfileobj(f, out, 1 << 20)
            os.chown(tmp, 0, 0)
            os.chmod(tmp, 0o755)
            os.replace(tmp, dest)
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        try:
            os.unlink(os.path.join(APPDIR, name + ".mainuan-part"))
        except OSError:
            pass
        ai_lock()
        return 1
    finally:
        os.close(fd)
    ai_lock()
    return 0


def ai_rm(argv):
    if len(argv) != 1 or not AI_NAME_RE.match(argv[0]) or "/" in argv[0]:
        return 2
    target = os.path.join(APPDIR, argv[0])
    if os.path.islink(target) or os.path.realpath(target) != target:
        return 2
    try:
        ai_unlock()
        if os.path.isfile(target):
            os.unlink(target)
    except OSError as exc:
        print(exc, file=sys.stderr)
        ai_lock()
        return 1
    ai_lock()
    return 0


def appimage_main(argv):
    if not argv:
        return 2
    if argv[0] == "put":
        return ai_put(argv[1:])
    if argv[0] == "rm":
        return ai_rm(argv[1:])
    if argv[0] == "sync":
        ai_unlock()
        ai_lock()
        return 0
    return 2


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "appimage":
        return appimage_main(argv[1:])
    if argv and argv[0] in ("apt", "flatpak"):
        if len(argv) < 3 or not valid_cancel(argv[1]):
            return 2
        args = argv[2:]
        if argv[0] == "apt":
            return run_guarded("/usr/bin/apt-get", args, argv[1]) if valid_apt(args) else 2
        return run_guarded("/usr/bin/flatpak", args, argv[1]) if valid_flatpak(args) else 2
    return toggle_main(argv)


if __name__ == "__main__":
    sys.exit(main())
