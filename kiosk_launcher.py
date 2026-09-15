#!/usr/bin/env python3
"""
Kiosk Launcher — a cross-platform, locked-down app launcher for classrooms/labs.

It dynamically discovers installed applications (so you don't have to know
where they live on each machine) and shows them as big buttons. It is designed
to be usable as a Windows custom shell (replace explorer.exe) but also runs on
Linux for development and testing.

Features
--------
* Built-in presets: LibreOffice, Scratch, Visual Studio Code, VSCodium, Word
* Dynamic discovery: PATH, Program Files, Windows "App Paths" registry,
  .desktop files, /opt, snap/flatpak export dirs, AppData/Programs
* Password-protected admin area to add more apps by name + regex
  (one regex per line, matched case-insensitively against the exe path)
* App search templates live in an external apps.json file (easy to extend
  with an LLM and copy to other machines); settings/password live in
  kiosk_config.json

Usage
-----
    python3 kiosk_launcher.py                 # run the launcher (fullscreen)
    python3 kiosk_launcher.py --windowed      # run windowed (development)
    python3 kiosk_launcher.py --kiosk         # force frameless fullscreen
    python3 kiosk_launcher.py --scan          # print what was found, then exit
    python3 kiosk_launcher.py --set-password  # change the admin password
    python3 kiosk_launcher.py --config PATH   # use a different config file
    python3 kiosk_launcher.py --apps PATH     # use a different apps.json

Default admin password on first run: admin   (change it with --set-password!)
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys

APP_NAME = "Kiosk Launcher"
VERSION = "0.2.0"
DEFAULT_PASSWORD = "admin"

# --------------------------------------------------------------------------
# Presets. "patterns" are regular expressions matched (case-insensitive)
# against each discovered executable's full path.
# --------------------------------------------------------------------------
BUILTIN_APPS = [
    # Office / general
    {
        "name": "LibreOffice",
        "patterns": [r"soffice(?:\.exe)?$", r"libreoffice(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Word",
        "patterns": [r"winword(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Excel",
        "patterns": [r"excel(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft PowerPoint",
        "patterns": [r"powerpnt(?:\.exe)?$", r"powerpoint(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Outlook",
        "patterns": [r"outlook(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft OneNote",
        "patterns": [r"onenote(?:m)?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Access",
        "patterns": [r"msaccess(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Publisher",
        "patterns": [r"mspub(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Visio",
        "patterns": [r"visio(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Project",
        "patterns": [r"winproj(?:\.exe)?$"],
        "args": [],
    },
    # Coding / creativity
    {
        "name": "Scratch",
        "patterns": [r"scratch(?: ?3|desktop|2)?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Visual Studio Code",
        "patterns": [r"(?:^|[\\/])code(?:\.cmd|\.exe)?$", r"vscode(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "VSCodium",
        "patterns": [r"codium(?:\.exe)?$", r"vscodium(?:\.exe)?$"],
        "args": [],
    },
    # Text editors
    {
        "name": "Notepad++",
        "patterns": [r"notepad\+\+(?:portable)?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Sublime Text",
        "patterns": [r"sublime_text(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "gedit",
        "patterns": [r"gedit(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Kate",
        "patterns": [r"kate(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Vim",
        "patterns": [r"(?:^|[\\/])g?vim(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Emacs",
        "patterns": [r"(?:run)?emacs(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Geany",
        "patterns": [r"geany(?:\.exe)?$"],
        "args": [],
    },
    # IDEs / dev editors
    {
        "name": "PyCharm",
        "patterns": [r"pycharm(?:64)?(?:\.exe|\.sh)?$"],
        "args": [],
    },
    {
        "name": "IntelliJ IDEA",
        "patterns": [r"idea64(?:\.exe|\.sh)?$", r"(?:^|[\\/])idea(?:\.exe|\.sh)?$"],
        "args": [],
    },
    {
        "name": "Eclipse",
        "patterns": [r"eclipse(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Code::Blocks",
        "patterns": [r"codeblocks(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Dev-C++",
        "patterns": [r"devcpp(?:portable)?(?:\.exe)?$"],
        "args": [],
    },
    # Graphics
    {
        "name": "GIMP",
        "patterns": [r"gimp(?:[._-]?[\d.]+)?(?:\.exe)?$", r"gimpportable(?:\.exe)?$"],
        "args": [],
    },
    # Video editing (FOSS)
    {
        "name": "Kdenlive",
        "patterns": [r"kdenlive(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Shotcut",
        "patterns": [r"shotcut(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "OpenShot",
        "patterns": [r"openshot-qt(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Olive",
        "patterns": [r"olive(?:-editor)?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Avidemux",
        "patterns": [r"avidemux(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Blender",
        "patterns": [r"blender(?:\.exe)?$"],
        "args": [],
    },
    # Audio editing (FOSS)
    {
        "name": "Audacity",
        "patterns": [r"audacity(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Ardour",
        "patterns": [r"ardour[0-9]*(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "LMMS",
        "patterns": [r"lmms(?:\.exe)?$"],
        "args": [],
    },
    # PDF viewers (FOSS)
    {
        "name": "SumatraPDF",
        "patterns": [r"sumatrapdf(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Okular",
        "patterns": [r"okular(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "MuPDF",
        "patterns": [r"(?:^|[\\/])mupdf(?:-gl)?(?:\.exe)?$"],
        "args": [],
    },
    # Educational / creative coding
    {
        "name": "Thonny",
        "patterns": [r"thonnyw?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Mu Editor",
        "patterns": [r"(?:^|[\\/])mu(?:-editor)?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Sonic Pi",
        "patterns": [r"sonic-?pi(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Arduino IDE",
        "patterns": [r"arduino(?:[ -]?ide)?(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Processing",
        "patterns": [r"processing(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "DrRacket",
        "patterns": [r"drracket(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Greenfoot",
        "patterns": [r"greenfoot(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "BlueJ",
        "patterns": [r"bluej(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "OpenSCAD",
        "patterns": [r"openscad(?:\.exe)?$"],
        "args": [],
    },
    # Art & design
    {
        "name": "Krita",
        "patterns": [r"krita(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Inkscape",
        "patterns": [r"inkscape(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Tux Paint",
        "patterns": [r"tuxpaint(?:\.exe)?$"],
        "args": [],
    },
    # Math & science
    {
        "name": "GeoGebra",
        "patterns": [r"geogebra(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Stellarium",
        "patterns": [r"stellarium(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "wxMaxima",
        "patterns": [r"wxmaxima(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "FreeCAD",
        "patterns": [r"freecad(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "LibreCAD",
        "patterns": [r"librecad(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Fritzing",
        "patterns": [r"fritzing(?:\.exe)?$"],
        "args": [],
    },
    # Study & music
    {
        "name": "Anki",
        "patterns": [r"anki(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "MuseScore",
        "patterns": [r"musescore[0-9.]*(?:\.exe)?$", r"mscore[0-9.]*(?:\.exe)?$"],
        "args": [],
    },
    # Virtualization
    {
        "name": "VirtualBox",
        "patterns": [r"virtualbox(?:\.exe)?$"],
        "args": [],
    },
]

# Friendly icons shown on the buttons (cosmetic only).
EMOJI = {
    "libreoffice": "\U0001F4DD",
    "microsoft word": "\U0001F4C4",
    "scratch": "\U0001F431",
    "visual studio code": "\U0001F5A5\uFE0F",
    "vscodium": "\U0001F4A0",
    "gimp": "\U0001F3A8",
    "kdenlive": "\U0001F3AC",
    "shotcut": "\u2702\uFE0F",
    "openshot": "\U0001F39E\uFE0F",
    "olive": "\U0001F3A5",
    "avidemux": "\U0001F4FD\uFE0F",
    "blender": "\U0001F9CA",
    "audacity": "\U0001F3A7",
    "ardour": "\U0001F39B\uFE0F",
    "lmms": "\U0001F3B9",
    "sumatrapdf": "\U0001F4D5",
    "okular": "\U0001F4D6",
    "mupdf": "\U0001F4D1",
    "virtualbox": "\U0001F4E6",
    "thonny": "\U0001F40D",
    "mu editor": "\u270F\uFE0F",
    "sonic pi": "\U0001F3B5",
    "arduino ide": "\U0001F50C",
    "processing": "\U0001F300",
    "drracket": "\U0001F9EE",
    "greenfoot": "\U0001F998",
    "bluej": "\u2615",
    "openscad": "\u2699\uFE0F",
    "krita": "\U0001F58C\uFE0F",
    "inkscape": "\U0001F58B\uFE0F",
    "tux paint": "\U0001F427",
    "geogebra": "\U0001F4D0",
    "stellarium": "\U0001F52D",
    "wxmaxima": "\u2797",
    "freecad": "\U0001F4CF",
    "librecad": "\U0001F58A\uFE0F",
    "fritzing": "\U0001F50B",
    "anki": "\U0001F0CF",
    "musescore": "\U0001F3BC",
    "microsoft excel": "\U0001F4CA",
    "microsoft powerpoint": "\U0001F4FD\uFE0F",
    "microsoft outlook": "\U0001F4E7",
    "microsoft onenote": "\U0001F4D3",
    "microsoft access": "\U0001F5C4\uFE0F",
    "microsoft publisher": "\U0001F4F0",
    "microsoft visio": "\U0001F9E9",
    "microsoft project": "\U0001F4C5",
    "notepad++": "\U0001F4DD",
    "sublime text": "\u2728",
    "gedit": "\U0001F4C3",
    "kate": "\U0001F58A\uFE0F",
    "vim": "\u2328\uFE0F",
    "emacs": "\U0001F5A5\uFE0F",
    "geany": "\U0001F6E0\uFE0F",
    "pycharm": "\U0001F40D",
    "intellij idea": "\U0001F4A1",
    "eclipse": "\U0001F311",
    "code::blocks": "\U0001F9F1",
    "dev-c++": "\U0001F527",
}
DEFAULT_EMOJI = "\U0001F680"


# ==========================================================================
# Config
# ==========================================================================
def _base_dir():
    """Directory holding the script (or the frozen exe)."""
    if getattr(sys, "frozen", False):          # PyInstaller one-file build
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def default_config_path():
    return os.path.join(_base_dir(), "kiosk_config.json")


def default_apps_path():
    return os.path.join(_base_dir(), "apps.json")


def seed_config():
    salt, digest, iterations = hash_password(DEFAULT_PASSWORD)
    return {
        "password": {"salt": salt, "hash": digest, "iterations": iterations},
        "fullscreen": True,
        "columns": 4,
    }


def load_config(path):
    """Load config, creating/repairing it if needed. Returns (cfg, path)."""
    created = False
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            cfg = seed_config()
            created = True
    else:
        cfg = seed_config()
        created = True

    cfg.setdefault("fullscreen", True)
    cfg.setdefault("columns", 4)
    if "password" not in cfg or "salt" not in cfg.get("password", {}):
        cfg["password"] = seed_config()["password"]
        created = True

    if created:
        save_config(cfg, path)
    return cfg, path


def save_config(cfg, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ==========================================================================
# App search templates (apps.json)
# ==========================================================================
def normalize_app(entry):
    """Validate/coerce one app template. Returns a clean dict or None."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    patterns = entry.get("patterns")
    args = entry.get("args", [])
    if not isinstance(name, str) or not name.strip():
        return None
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list) or not patterns:
        return None
    patterns = [p for p in patterns if isinstance(p, str) and p.strip()]
    if not patterns:
        return None
    if isinstance(args, str):
        args = shlex.split(args, posix=(os.name == "posix"))
    if not isinstance(args, list):
        args = []
    return {"name": name.strip(), "patterns": patterns, "args": args}


def load_apps(path):
    """Load app search templates. Seeds apps.json from presets if absent.

    Returns (apps, path). If the file exists but is invalid, the built-in
    presets are used in memory (the file is NOT overwritten).
    """
    apps = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data if isinstance(data, list) else data.get("apps") if isinstance(data, dict) else None
            if isinstance(raw, list):
                apps = [a for a in (normalize_app(e) for e in raw) if a]
                if not apps and raw:
                    print(
                        f"WARNING: no valid app entries in {path}; "
                        "using built-in presets",
                        file=sys.stderr,
                    )
                    apps = [dict(a) for a in BUILTIN_APPS]
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"WARNING: could not parse {path}: {e}; using built-in presets",
                file=sys.stderr,
            )
            apps = None
    if apps is None:
        apps = [dict(a) for a in BUILTIN_APPS]
        if not os.path.exists(path):
            save_apps(apps, path)
    return apps, path


def save_apps(apps, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2, ensure_ascii=False)


def add_app(apps, entry):
    """Append a normalized app template to the list (in place)."""
    clean = normalize_app(entry)
    if clean is None:
        raise ValueError(
            "invalid app entry: needs a 'name' and non-empty 'patterns'"
        )
    apps.append(clean)
    return apps


def remove_apps(apps, names):
    """Remove apps by display name (case-insensitive). Returns count removed."""
    if isinstance(names, str):
        names = [names]
    lowered = {n.strip().lower() for n in names if isinstance(n, str) and n.strip()}
    kept = [a for a in apps if a.get("name", "").lower() not in lowered]
    removed = len(apps) - len(kept)
    apps[:] = kept
    return removed


# ==========================================================================
# Password handling
# ==========================================================================
def hash_password(password, salt=None, iterations=200_000):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return salt, digest.hex(), iterations


def verify_password(password, pw_cfg):
    salt = pw_cfg["salt"]
    digest = pw_cfg["hash"]
    iterations = pw_cfg.get("iterations", 200_000)
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return secrets.compare_digest(candidate.hex(), digest)


def set_password(cfg, new_password):
    """Replace cfg["password"] with a fresh hash of new_password (in place)."""
    cfg["password"] = dict(
        zip(("salt", "hash", "iterations"), hash_password(new_password))
    )
    return cfg


# ==========================================================================
# Application discovery
# ==========================================================================
def _walk_depth(root, max_depth, exts=None):
    """Yield files up to max_depth directory levels below root."""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= max_depth:
            dirnames[:] = []
        for name in filenames:
            if exts and not name.lower().endswith(exts):
                continue
            yield os.path.join(dirpath, name)


def _registry_app_paths():
    """Windows: resolve registered app paths (finds Word, etc. reliably)."""
    if os.name != "nt":
        return set()
    try:
        import winreg
    except ImportError:
        return set()

    out = set()
    views = [
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, 0),
    ]
    for root, view in views:
        try:
            key = winreg.OpenKey(
                root,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                0,
                winreg.KEY_READ | view,
            )
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(key, sub) as k:
                    value, _ = winreg.QueryValueEx(k, None)
                    if value:
                        out.add(value)
            except OSError:
                continue
    return out


def _desktop_exec_paths():
    """Linux: extract binary paths from .desktop launchers."""
    if os.name == "nt":
        return set()
    out = set()
    dirs = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
    ]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".desktop"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8", errors="ignore") as f:
                    exec_line = None
                    for line in f:
                        if line.startswith("Exec="):
                            exec_line = line[5:].strip()
                            break
                if not exec_line:
                    continue
                exec_line = exec_line.split("%", 1)[0].strip()
                parts = shlex.split(exec_line)
                if not parts:
                    continue
                exe = parts[0]
                if exe == "env":                      # e.g. `env VAR=x /path/app`
                    for t in parts[1:]:
                        if "/" in t:
                            exe = t
                            break
                if os.sep in exe:
                    if os.path.exists(exe):
                        out.add(exe)
                else:
                    found = shutil.which(exe)
                    if found:
                        out.add(found)
            except Exception:
                continue
    return out


def gather_candidates():
    """Return a set of candidate executable paths for this machine."""
    cands = set()

    def add(p):
        if p:
            cands.add(os.path.normcase(os.path.normpath(p)))

    if os.name == "nt":
        roots = []
        for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            v = os.environ.get(var)
            if v:
                roots.append((v, 3))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append((os.path.join(local, "Programs"), 3))
            roots.append((os.path.join(local, "Microsoft", "WindowsApps"), 1))
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d:
                roots.append((d, 1))
        for root, depth in roots:
            for p in _walk_depth(root, depth, exts=(".exe",)):
                add(p)
        for p in _registry_app_paths():
            add(p)
    else:
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d and os.path.isdir(d):
                for fn in os.listdir(d):
                    add(os.path.join(d, fn))
        extra = [
            "/opt",
            "/usr/local/bin",
            "/snap/bin",
            "/var/lib/flatpak/exports/bin",
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/.local/share/flatpak/exports/bin"),
            os.path.expanduser("~/Applications"),
        ]
        for root in extra:
            if os.path.isdir(root):
                for p in _walk_depth(root, 3):
                    add(p)
        for p in _desktop_exec_paths():
            add(p)

    return cands


def discover_apps(apps):
    """Return (found, missing) for the given app templates."""
    candidates = sorted(gather_candidates(), key=str.lower)
    found, missing = [], []
    for app in apps:
        try:
            # Case-insensitive: a candidate "GIMP.EXE" matches pattern "gimp".
            pats = [re.compile(p, re.IGNORECASE) for p in app["patterns"]]
        except re.error as e:
            print(f"WARNING: bad regex in '{app['name']}': {e}", file=sys.stderr)
            missing.append(app["name"])
            continue
        hit = None
        for c in candidates:
            if any(p.search(c) for p in pats):
                hit = c
                break
        if hit:
            found.append(
                {"name": app["name"], "path": hit, "args": list(app.get("args", []))}
            )
        else:
            missing.append(app["name"])
    return found, missing


# Keep references to launched children so they aren't GC'd while running
# (avoids ResourceWarning) and are pruned once finished.
_children = []


def launch(app):
    """Launch a discovered app without waiting. Returns None or error str."""
    path = app["path"]
    args = list(app.get("args", []))
    cwd = os.path.dirname(path) or None
    try:
        if os.name == "nt":
            if "WindowsApps" in path:   # App Execution Alias stub
                proc = subprocess.Popen(
                    ["cmd", "/c", "start", "", path] + args, cwd=cwd
                )
            else:
                proc = subprocess.Popen([path] + args, cwd=cwd)
        else:
            proc = subprocess.Popen([path] + args, cwd=cwd, start_new_session=True)
    except Exception as e:              # noqa: BLE001 - we surface the message
        return str(e)
    _children.append(proc)
    _children[:] = [p for p in _children if p.poll() is None]
    return None


# ==========================================================================
# Escape-hotkey blocking (kiosk mode)
# ==========================================================================
# Virtual-key codes (Windows). Plain ints used only for the blocking decision.
VK_TAB = 0x09
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_F4 = 0x73
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1


def is_blocked_hotkey(vk, alt_down, ctrl_down):
    """True if this keydown combo is an escape hotkey that should be blocked.

    Blocks: Win key (all Win+... shortcuts), Alt+Tab, Alt+Esc, Ctrl+Esc,
    Ctrl+Shift+Esc (Task Manager), Alt+Space, and Alt+F4. Also flags
    Ctrl+Alt+Del for blocking, though Windows delivers the Secure Attention
    Sequence to winlogon (not to this hook) — disable it via policy too.

    Alt+Shift (language/layout switching) is explicitly allowed.
    """
    # Allow Alt+Shift — the standard Windows language/layout switch.
    if alt_down and vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
        return False
    if vk in (VK_LWIN, VK_RWIN):
        return True
    if vk == VK_ESCAPE and (alt_down or ctrl_down):
        return True
    if alt_down and vk in (VK_TAB, VK_SPACE, VK_F4):
        return True
    if vk == VK_DELETE and alt_down and ctrl_down:
        return True
    return False


if os.name == "nt":
    import ctypes
    import threading
    from ctypes import wintypes

    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_SYSKEYDOWN = 0x0104
    WM_QUIT = 0x0012
    LLKHF_ALTDOWN = 0x20

    LRESULT = ctypes.c_ssize_t
    WPARAM_T = ctypes.c_size_t

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM_T, ctypes.c_void_p)

    _user32 = ctypes.windll.user32
    _user32.SetWindowsHookExW.restype = ctypes.c_void_p
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD,
    ]
    _user32.CallNextHookEx.restype = LRESULT
    _user32.CallNextHookEx.argtypes = [
        ctypes.c_void_p, ctypes.c_int, WPARAM_T, ctypes.c_void_p,
    ]
    _user32.UnhookWindowsHookEx.restype = ctypes.c_int
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    _user32.GetMessageW.restype = ctypes.c_int
    _user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), ctypes.c_void_p,
        wintypes.UINT, wintypes.UINT,
    ]
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.PostThreadMessageW.restype = ctypes.c_int
    _user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, WPARAM_T, ctypes.c_void_p,
    ]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


    class KioskHotkeyBlocker:
        """Low-level keyboard hook that swallows escape hotkeys system-wide.

        On a blocked combo it calls on_blocked() (from the hook thread) and
        returns 1 so Windows drops the keystroke. Requires a message loop,
        which is pumped in a dedicated thread.
        """

        def __init__(self, on_blocked):
            self.on_blocked = on_blocked
            self._thread = None
            self._hook = None
            self._proc = None

        def start(self):
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run, name="kiosk-hotkey-hook", daemon=True
            )
            self._thread.start()

        def _run(self):
            def proc(nCode, wParam, lParam):
                if nCode >= 0:
                    kb = ctypes.cast(
                        lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)
                    ).contents
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        vk = kb.vkCode
                        alt = bool(kb.flags & LLKHF_ALTDOWN)
                        ctrl = False
                        if vk in (VK_ESCAPE, VK_DELETE):
                            ctrl = bool(
                                _user32.GetAsyncKeyState(VK_CONTROL) & 0x8000
                            )
                        if is_blocked_hotkey(vk, alt, ctrl):
                            try:
                                self.on_blocked()
                            except Exception:
                                pass
                            return 1  # swallow the keystroke
                return _user32.CallNextHookEx(None, nCode, wParam, lParam)

            self._proc = HOOKPROC(proc)
            self._hook = _user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._proc, None, 0
            )
            if not self._hook:
                return
            msg = wintypes.MSG()
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

        def stop(self):
            if self._thread is not None:
                try:
                    _user32.PostThreadMessageW(
                        self._thread.ident, WM_QUIT, 0, None
                    )
                    self._thread.join(timeout=2)
                finally:
                    self._thread = None


# ==========================================================================
# CLI modes (no GUI needed)
# ==========================================================================
def cmd_scan(args):
    cfg_path = args.config or default_config_path()
    cfg, _ = load_config(cfg_path)
    apps, apps_path = load_apps(args.apps or default_apps_path())
    found, missing = discover_apps(apps)
    print(f"Config: {cfg_path}")
    print(f"Apps:   {apps_path} ({len(apps)} templates)")
    print("Found:")
    for a in found:
        print(f"  \u2714 {a['name']}: {a['path']}")
    print("Not found:")
    for name in missing:
        print(f"  \u2716 {name}")


def cmd_set_password(args):
    import getpass

    cfg, path = load_config(args.config or default_config_path())
    pw1 = getpass.getpass("New admin password: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)
    if len(pw1) < 1:
        print("Password must not be empty.", file=sys.stderr)
        sys.exit(1)
    set_password(cfg, pw1)
    save_config(cfg, path)
    print(f"Password updated in {path}")


# ==========================================================================
# GUI
# ==========================================================================
try:
    from PySide6.QtCore import Qt, QPoint, QTimer, QFileSystemWatcher, QObject, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGridLayout,
        QInputDialog,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QAbstractItemView,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QVBoxLayout,
        QWidget,
        QLabel,
        QHBoxLayout,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

GUI_IMPORT_ERROR = (
    "PySide6 is required for the GUI.\n"
    "Install it with:  pip install pyside6  (or apt install python3-pyside6)"
)


if _HAS_QT:

    class AddAppDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Add app")
            self.setMinimumWidth(420)
            form = QFormLayout(self)
            self.name_edit = QLineEdit()
            self.name_edit.setObjectName("addapp_name")
            self.name_edit.setPlaceholderText("e.g. GIMP")
            self.patterns_edit = QPlainTextEdit()
            self.patterns_edit.setObjectName("addapp_patterns")
            self.patterns_edit.setPlaceholderText(
                "One regex per line, matched against the exe path, e.g.\n"
                "gimp(?:\\.exe)?$\n"
                "firefox(?:\\.exe)?$"
            )
            self.args_edit = QLineEdit()
            self.args_edit.setObjectName("addapp_args")
            self.args_edit.setPlaceholderText("optional arguments")
            form.addRow("Name:", self.name_edit)
            form.addRow("Match (regex):", self.patterns_edit)
            form.addRow("Arguments:", self.args_edit)
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            )
            buttons.accepted.connect(self._on_accept)
            buttons.rejected.connect(self.reject)
            form.addRow(buttons)

        def _on_accept(self):
            name = self.name_edit.text().strip()
            patterns = [
                l.strip()
                for l in self.patterns_edit.toPlainText().splitlines()
                if l.strip()
            ]
            if not name or not patterns:
                QMessageBox.warning(self, "Incomplete", "Name and at least one pattern are required.")
                return
            for p in patterns:
                try:
                    re.compile(p)
                except re.error as e:
                    QMessageBox.warning(self, "Invalid regex", f"{p}\n\n{e}")
                    return
            self.accept()

        def values(self):
            args_text = self.args_edit.text().strip()
            args = shlex.split(args_text, posix=(os.name == "posix")) if args_text else []
            return {
                "name": self.name_edit.text().strip(),
                "patterns": [
                    l.strip()
                    for l in self.patterns_edit.toPlainText().splitlines()
                    if l.strip()
                ],
                "args": args,
                "custom": True,
            }

    class RemoveAppDialog(QDialog):
        def __init__(self, apps, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Remove apps")
            self.setMinimumWidth(360)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Select apps to remove:"))
            self.list_widget = QListWidget()
            self.list_widget.setObjectName("removeapp_list")
            self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
            for a in apps:
                item = QListWidgetItem(a["name"])
                item.setData(Qt.UserRole, a)
                self.list_widget.addItem(item)
            layout.addWidget(self.list_widget)
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def selected(self):
            return [
                self.list_widget.item(i).data(Qt.UserRole)
                for i in range(self.list_widget.count())
                if self.list_widget.item(i).isSelected()
            ]

    class MainWindow(QWidget):
        def __init__(self, cfg, cfg_path, apps, apps_path, kiosk):
            super().__init__()
            self.cfg = cfg
            self.cfg_path = cfg_path
            self.apps = apps
            self.apps_path = apps_path
            self.kiosk = kiosk
            self.setWindowTitle(APP_NAME)

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 12)

            self.status_label = QLabel("")
            self.status_label.setObjectName("status_label")
            self.status_label.setStyleSheet("color: #a6adc8; font-size: 14px;")

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            self.grid_host = QWidget()
            self.grid = QGridLayout(self.grid_host)
            self.grid.setSpacing(14)
            self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            scroll.setWidget(self.grid_host)

            self.admin_btn = QPushButton("\u2699  Admin")
            self.admin_btn.setObjectName("admin_btn")
            self.admin_btn.setStyleSheet(
                "QPushButton { background: #313244; color: #cdd6f4; border-radius: 8px;"
                " padding: 8px 16px; font-size: 14px; }"
                "QPushButton:hover { background: #45475a; }"
            )
            self.admin_btn.clicked.connect(self.on_admin)

            bar = QHBoxLayout()
            bar.addWidget(self.status_label, 1)
            bar.addWidget(self.admin_btn)

            root.addWidget(scroll, 1)
            root.addLayout(bar)

            self.setStyleSheet(
                """
                QWidget { background: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI', 'DejaVu Sans', sans-serif; }
                QPushButton.app {
                    background: #313244; color: #cdd6f4; border-radius: 14px;
                    font-size: 20px; font-weight: 600; padding: 18px;
                }
                QPushButton.app:hover { background: #45475a; }
                QPushButton.app:pressed { background: #585b70; }
                QLabel { background: transparent; }
                """
            )

            if self.kiosk:
                self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            else:
                self.resize(1000, 700)
            self.rebuild()

            # Live-reload apps.json whenever it changes on disk.
            self._reload_timer = QTimer(self)
            self._reload_timer.setSingleShot(True)
            self._reload_timer.setInterval(400)
            self._reload_timer.timeout.connect(self._reload_apps)
            self._watcher = QFileSystemWatcher(self)
            self._watcher.fileChanged.connect(self._schedule_reload)
            self._ensure_watched()

        def _schedule_reload(self, changed_path=None):
            # Debounce: editors may write the file multiple times (or replace
            # it atomically), firing several change events in quick succession.
            self._reload_timer.start()

        def _ensure_watched(self):
            if self.apps_path and os.path.exists(self.apps_path):
                if self.apps_path not in self._watcher.files():
                    self._watcher.addPath(self.apps_path)

        def _reload_apps(self):
            self.apps, self.apps_path = load_apps(self.apps_path)
            self._ensure_watched()
            self.rebuild()
            self.status_label.setText(
                f"Reloaded {len(self.apps)} app templates from "
                f"{os.path.basename(self.apps_path)}"
            )

        def rebuild(self):
            while self.grid.count():
                item = self.grid.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            found, missing = discover_apps(self.apps)
            cols = max(1, int(self.cfg.get("columns", 4)))
            for i, a in enumerate(found):
                key = a["name"].lower()
                icon = EMOJI.get(key, DEFAULT_EMOJI)
                btn = QPushButton(f"{icon}\n{a['name']}")
                btn.setProperty("class", "app")
                btn.setObjectName("app:" + a["name"])
                btn.setFixedSize(180, 130)
                btn.setToolTip(a["path"])
                btn.clicked.connect(lambda _=False, a=a: self.launch(a))
                self.grid.addWidget(btn, i // cols, i % cols)
            self.grid.setRowStretch((len(found) // cols) + 1, 1)
            if missing:
                self.status_label.setText(
                    f"\u2714 {len(found)} available   \u2716 missing: {', '.join(missing)}"
                )
            else:
                self.status_label.setText(f"\u2714 {len(found)} available")

        def launch(self, app):
            err = launch(app)
            if err:
                QMessageBox.warning(self, "Launch failed", err)
            else:
                self.status_label.setText(f"Launched {app['name']}")

        def on_admin(self):
            if getattr(self, "_admin_prompt_open", False):
                return
            self._admin_prompt_open = True
            try:
                pw, ok = QInputDialog.getText(
                    self, "Admin access", "Password:", QLineEdit.Password
                )
                if not ok:
                    return
                if not verify_password(pw, self.cfg["password"]):
                    QMessageBox.warning(self, "Denied", "Wrong password.")
                    return
                menu = QMenu(self)
                menu.addAction("\U0001F4DD  Add app\u2026", self.add_app)
                menu.addAction("\u2796  Remove app\u2026", self.remove_app)
                menu.addAction("\U0001F511  Change password\u2026", self.change_password)
                menu.addAction("\U0001F504  Rescan", self.rebuild)
                menu.addAction("\U0001F6AA  Exit", self.quit_now)
                menu.exec(
                    self.admin_btn.mapToGlobal(QPoint(0, self.admin_btn.height()))
                )
            finally:
                self._admin_prompt_open = False

        def add_app(self):
            dlg = AddAppDialog(self)
            if dlg.exec() == QDialog.Accepted:
                add_app(self.apps, dlg.values())
                save_apps(self.apps, self.apps_path)
                self._ensure_watched()
                self.rebuild()

        def remove_app(self):
            dlg = RemoveAppDialog(self.apps, self)
            if dlg.exec() == QDialog.Accepted:
                selected = dlg.selected()
                if not selected:
                    return
                names = [a["name"] for a in selected]
                remove_apps(self.apps, names)
                save_apps(self.apps, self.apps_path)
                self._ensure_watched()
                self.rebuild()

        def change_password(self):
            new1, ok1 = QInputDialog.getText(
                self, "Change password", "New password:", QLineEdit.Password
            )
            if not ok1:
                return
            new2, ok2 = QInputDialog.getText(
                self, "Change password", "Confirm new password:", QLineEdit.Password
            )
            if not ok2:
                return
            if new1 != new2:
                QMessageBox.warning(self, "Mismatch", "Passwords do not match.")
                return
            if not new1:
                QMessageBox.warning(self, "Empty", "Password must not be empty.")
                return
            set_password(self.cfg, new1)
            save_config(self.cfg, self.cfg_path)
            QMessageBox.information(self, "Done", "Password updated.")

        def quit_now(self):
            QApplication.instance().quit()

        def closeEvent(self, event):
            # Only user-initiated closes (Alt+F4 / window X) need the password.
            # Programmatic quits (admin Exit, app.quit()) arrive non-spontaneously
            # and must not re-prompt or block shutdown.
            if self.kiosk and event.spontaneous():
                if getattr(self, "_admin_prompt_open", False):
                    event.ignore()
                    return
                self._admin_prompt_open = True
                try:
                    pw, ok = QInputDialog.getText(
                        self, "Exit", "Exit requires the admin password:",
                        QLineEdit.Password,
                    )
                    if ok and verify_password(pw, self.cfg["password"]):
                        event.accept()
                    else:
                        event.ignore()
                finally:
                    self._admin_prompt_open = False
            else:
                event.accept()

        def keyPressEvent(self, event):
            if self.kiosk and event.key() in (Qt.Key_Escape, Qt.Key_F11):
                self.on_admin()
                return
            super().keyPressEvent(event)


def run_gui(args):
    if not _HAS_QT:
        sys.exit(GUI_IMPORT_ERROR)

    cfg, path = load_config(args.config or default_config_path())
    apps, apps_path = load_apps(args.apps or default_apps_path())
    kiosk = args.kiosk or (cfg.get("fullscreen", False) and not args.windowed)

    app = QApplication(sys.argv)
    win = MainWindow(cfg, path, apps, apps_path, kiosk)
    if os.name == "nt" and win.kiosk:
        class HotkeyBridge(QObject):
            hotkeyBlocked = Signal()

            def notify(self):
                self.hotkeyBlocked.emit()

        bridge = HotkeyBridge()
        bridge.hotkeyBlocked.connect(win.on_admin)
        blocker = KioskHotkeyBlocker(bridge.notify)
        blocker.start()
        win._kiosk_hotkey_blocker = blocker
        app.aboutToQuit.connect(blocker.stop)
    if getattr(args, "smoke", False):
        QTimer.singleShot(600, app.quit)
    if win.kiosk:
        win.showFullScreen()
    else:
        win.show()
    sys.exit(app.exec())


# ==========================================================================
def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{VERSION} — locked-down classroom app launcher."
    )
    parser.add_argument("--config", help="path to kiosk_config.json")
    parser.add_argument("--apps", help="path to apps.json (app search templates)")
    parser.add_argument("--scan", action="store_true", help="print discovery results and exit")
    parser.add_argument("--set-password", action="store_true", help="change the admin password and exit")
    parser.add_argument("--kiosk", action="store_true", help="frameless fullscreen, exit requires password")
    parser.add_argument("--windowed", action="store_true", help="force windowed mode")
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.set_password:
        cmd_set_password(args)
    elif args.scan:
        cmd_scan(args)
    else:
        run_gui(args)


if __name__ == "__main__":
    main()
