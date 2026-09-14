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
* Config stored in kiosk_config.json next to this script (or --config)

Usage
-----
    python3 kiosk_launcher.py                 # run the launcher (windowed)
    python3 kiosk_launcher.py --kiosk         # frameless fullscreen (locked)
    python3 kiosk_launcher.py --scan          # print what was found, then exit
    python3 kiosk_launcher.py --set-password  # change the admin password
    python3 kiosk_launcher.py --config PATH   # use a different config file

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
VERSION = "0.1.0"
DEFAULT_PASSWORD = "admin"

# --------------------------------------------------------------------------
# Presets. "patterns" are regular expressions matched (case-insensitive)
# against each discovered executable's full path.
# --------------------------------------------------------------------------
BUILTIN_APPS = [
    {
        "name": "LibreOffice",
        "patterns": [r"soffice(?:\.exe)?$", r"libreoffice(?:\.exe)?$"],
        "args": [],
    },
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
        "patterns": [r"(?:^|[\\/])codium(?:\.exe)?$"],
        "args": [],
    },
    {
        "name": "Microsoft Word",
        "patterns": [r"winword(?:\.exe)?$"],
        "args": [],
    },
]

# Friendly icons shown on the buttons (cosmetic only).
EMOJI = {
    "libreoffice": "\U0001F4DD",
    "scratch": "\U0001F431",
    "visual studio code": "\U0001F5A5\uFE0F",
    "vscodium": "\U0001F489",
    "microsoft word": "\U0001F4C4",
}
DEFAULT_EMOJI = "\U0001F680"


# ==========================================================================
# Config
# ==========================================================================
def default_config_path():
    if getattr(sys, "frozen", False):          # PyInstaller one-file build
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "kiosk_config.json")


def seed_config():
    salt, digest, iterations = hash_password(DEFAULT_PASSWORD)
    return {
        "password": {"salt": salt, "hash": digest, "iterations": iterations},
        "fullscreen": False,
        "columns": 4,
        "apps": [dict(a) for a in BUILTIN_APPS],
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

    cfg.setdefault("fullscreen", False)
    cfg.setdefault("columns", 4)
    cfg.setdefault("apps", [dict(a) for a in BUILTIN_APPS])
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


def discover_apps(cfg):
    """Return (found, missing) for the configured app entries."""
    candidates = sorted(gather_candidates(), key=str.lower)
    found, missing = [], []
    for app in cfg["apps"]:
        try:
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
# CLI modes (no GUI needed)
# ==========================================================================
def cmd_scan(args):
    cfg, path = load_config(args.config or default_config_path())
    found, missing = discover_apps(cfg)
    print(f"Config: {path}")
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
    cfg["password"] = dict(zip(("salt", "hash", "iterations"), hash_password(pw1)))
    save_config(cfg, path)
    print(f"Password updated in {path}")


# ==========================================================================
# GUI
# ==========================================================================
def run_gui(args):
    try:
        from PySide6.QtCore import Qt, QPoint, QTimer
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
    except ImportError:
        sys.exit(
            "PySide6 is required for the GUI.\n"
            "Install it with:  pip install pyside6  (or apt install python3-pyside6)"
        )

    cfg, path = load_config(args.config or default_config_path())

    class AddAppDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Add app")
            self.setMinimumWidth(420)
            form = QFormLayout(self)
            self.name_edit = QLineEdit()
            self.name_edit.setPlaceholderText("e.g. GIMP")
            self.patterns_edit = QPlainTextEdit()
            self.patterns_edit.setPlaceholderText(
                "One regex per line, matched against the exe path, e.g.\n"
                "gimp(?:\\.exe)?$\n"
                "firefox(?:\\.exe)?$"
            )
            self.args_edit = QLineEdit()
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
        def __init__(self):
            super().__init__()
            self.cfg = cfg
            self.cfg_path = path
            self.kiosk = args.kiosk or (cfg.get("fullscreen", False) and not args.windowed)
            self.setWindowTitle(APP_NAME)

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 12)

            self.status_label = QLabel("")
            self.status_label.setStyleSheet("color: #a6adc8; font-size: 14px;")

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            self.grid_host = QWidget()
            self.grid = QGridLayout(self.grid_host)
            self.grid.setSpacing(14)
            scroll.setWidget(self.grid_host)

            self.admin_btn = QPushButton("\u2699  Admin")
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
            self.resize(1000, 700)
            self.rebuild()

        def rebuild(self):
            while self.grid.count():
                item = self.grid.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            found, missing = discover_apps(self.cfg)
            cols = max(1, int(self.cfg.get("columns", 4)))
            for i, a in enumerate(found):
                key = a["name"].lower()
                icon = EMOJI.get(key, DEFAULT_EMOJI)
                btn = QPushButton(f"{icon}\n{a['name']}")
                btn.setProperty("class", "app")
                btn.setMinimumSize(150, 110)
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

        def add_app(self):
            dlg = AddAppDialog(self)
            if dlg.exec() == QDialog.Accepted:
                self.cfg["apps"].append(dlg.values())
                save_config(self.cfg, self.cfg_path)
                self.rebuild()

        def remove_app(self):
            dlg = RemoveAppDialog(self.cfg["apps"], self)
            if dlg.exec() == QDialog.Accepted:
                selected = dlg.selected()
                if not selected:
                    return
                names = {a["name"] for a in selected}
                self.cfg["apps"] = [
                    a for a in self.cfg["apps"] if a["name"] not in names
                ]
                save_config(self.cfg, self.cfg_path)
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
            self.cfg["password"] = dict(
                zip(("salt", "hash", "iterations"), hash_password(new1))
            )
            save_config(self.cfg, self.cfg_path)
            QMessageBox.information(self, "Done", "Password updated.")

        def quit_now(self):
            QApplication.instance().quit()

        def closeEvent(self, event):
            if self.kiosk:
                pw, ok = QInputDialog.getText(
                    self, "Exit", "Exit requires the admin password:", QLineEdit.Password
                )
                if ok and verify_password(pw, self.cfg["password"]):
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()

        def keyPressEvent(self, event):
            if self.kiosk and event.key() == Qt.Key_Escape:
                self.on_admin()
            else:
                super().keyPressEvent(event)

    app = QApplication(sys.argv)
    win = MainWindow()
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
