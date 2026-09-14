# Kiosk Launcher

A cross-platform, locked-down app launcher for school/classroom computers.
It dynamically discovers installed apps (so paths don't have to be known in
advance), shows them as big buttons, and keeps an admin-only area for adding
more apps by regex.

## Features

- **Presets:** LibreOffice, Word, Scratch, VS Code, VSCodium, GIMP — plus FOSS
  video editors (Kdenlive, Shotcut, OpenShot, Olive, Avidemux, Blender), audio
  tools (Audacity, Ardour, LMMS), PDF viewers (SumatraPDF, Okular, MuPDF),
  VirtualBox, and educational software (Thonny, Mu Editor, Sonic Pi,
  Arduino IDE, Processing, DrRacket, Greenfoot, BlueJ, OpenSCAD, Krita,
  Inkscape, Tux Paint, GeoGebra, Stellarium, wxMaxima, FreeCAD, LibreCAD,
  Fritzing, Anki, MuseScore). No browsers or games.
- **Dynamic discovery** (no hard-coded paths):
  - *Windows:* `PATH`, `Program Files`, `Program Files (x86)`, `ProgramData`,
    `%LOCALAPPDATA%\Programs`, Windows "App Paths" registry, Store app aliases
  - *Linux:* `PATH`, `/opt`, `/usr/local/bin`, snap/flatpak export dirs,
    `~/.local/bin`, and `.desktop` files
- **Admin area (password-protected):**
  - Add an app by name + one-or-more regexes (matched against the exe path)
  - Remove apps, change the password, rescan
- **Kiosk mode:** frameless fullscreen; exiting requires the admin password.
  Escape hotkeys (Win key, Alt+Tab, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc,
  Alt+Space) are intercepted on Windows and route to the admin password prompt.
- **One config file** (`kiosk_config.json`) — auto-generated on first run
  (gitignored), so each machine can build its own.
- **App list is a plain data file** (`apps.json`) — extend it with an LLM and
  copy it to every machine; no code changes needed.

## Project layout

```
kiosk_launcher.py           # the entire application (single file)
apps.json                   # app search templates (editable, copyable)
tests/test_kiosk_launcher.py
AGENT.md                    # guidance for AI coding agents
README.md
kiosk_config.json           # runtime-generated settings + password, not committed
```

## Quick start

```bash
# install the GUI toolkit (Debian)
pip install --user --break-system-packages pyside6-essentials
# or: sudo apt install python3-pyside6

python3 kiosk_launcher.py                # fullscreen (kiosk mode)
python3 kiosk_launcher.py --windowed     # windowed (development)
python3 kiosk_launcher.py --kiosk        # force frameless fullscreen
python3 kiosk_launcher.py --scan         # show what was found, no GUI
python3 kiosk_launcher.py --set-password # change admin password
python3 kiosk_launcher.py --config X.json
python3 kiosk_launcher.py --apps A.json      # use a different app list
```

**Default admin password: `admin`** — change it with `--set-password`.

## Admin: adding an app

1. Click **⚙ Admin**, enter the password.
2. Choose **Add app…**.
3. Fill in a display name and one regex per line, e.g.:

   ```
   winword\.exe$
   firefox(?:\.exe)?$
   gimp(?:\.exe)?$
   ```

   The regex is matched case-insensitively against each discovered
   executable's full path. Use `$` to anchor to the filename.

The added entry is saved to `apps.json` and the launcher rescans
immediately.

## Customizing the app list (`apps.json`)

`apps.json` is a simple JSON array of search templates — one per app:

```jsonc
[
  {
    "name": "GIMP",
    "patterns": ["gimp(?:\\.exe)?$", "gimp-2\\.10(?:\\.exe)?$"],
    "args": []
  },
  { "name": "Firefox", "patterns": "firefox(?:\\.exe)?$", "args": "--kiosk" }
]
```

- `name` — the button label.
- `patterns` — one or more regexes, matched case-insensitively against each
  discovered executable's **full path**. Anchor with `$`. A bare string is
  accepted and treated as a single pattern.
- `args` — optional launch arguments (string or list).

This file is intentionally plain and machine-editable: have an LLM add a
hundred app patterns, then copy the same `apps.json` to every client. On
first run (or whenever it's missing), the launcher seeds it from the built-in
presets. Invalid entries are skipped with a warning; a broken file falls back
in memory to the presets without overwriting your file.

The running launcher **watches `apps.json` and reloads it automatically** a
moment after you save — no restart needed.

## Development

```bash
# run the test suite (stdlib unittest; also works with pytest)
python3 -m unittest discover -s tests -v

# syntax check
python3 -m py_compile kiosk_launcher.py

# headless GUI smoke test
QT_QPA_PLATFORM=offscreen python3 kiosk_launcher.py --smoke
```

There are no runtime dependencies beyond PySide6, and the core (discovery,
config, password) is stdlib-only so `--scan`/`--set-password` work without
it. See [AGENT.md](AGENT.md) for architecture details and coding conventions.

## Deploy on Windows (as a custom shell)

Two options:

### A. Run on top of Windows (simplest)
Create a standard (non-admin) `Student` account, put a shortcut to the
launcher in its Startup folder, and lock policies down with
[Policy Plus](https://github.com/Fleex255/PolicyPlus) or Group Policy.

### B. Replace explorer.exe (true kiosk shell — works on Home + Pro)
1. Freeze to a single `.exe`:
   ```bash
   pip install pyinstaller
   pyinstaller --onefile --windowed --name Kiosk kiosk_launcher.py
   ```
2. Copy `Kiosk.exe` (and optionally a customized `apps.json`) to `C:\Kiosk\`.
3. Set the shell **for the Student account only** (keeps an admin escape
   hatch — do NOT set the HKLM value or you can lock yourself out):
   ```
   reg add "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" ^
       /v Shell /t REG_SZ /d "C:\Kiosk\Kiosk.exe" /f
   ```
   Run that *as the Student user* (or under HKCU while logged in as them).
4. Also disable Task Manager for the student, otherwise
   Ctrl+Alt+Del → Task Manager → *Run new task* → `explorer.exe` defeats it:
   ```
   reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" ^
       /v DisableTaskMgr /t REG_DWORD /d 1 /f
   ```
5. Keep an `Admin` account with the normal explorer shell to manage the
   machine and undo changes.

> **Always test in a VM or on a spare machine first**, and keep an admin
> account with a normal desktop.

### Hotkey lockdown (kiosk mode)

In `--kiosk` mode, escape attempts ask for the admin password instead:

- **Windows (system-wide):** a low-level keyboard hook swallows the **Win
  key** (all Win+… shortcuts), **Alt+Tab**, **Alt+Esc**, **Ctrl+Esc**,
  **Ctrl+Shift+Esc** (Task Manager), **Alt+Space**, and **Alt+F4** for as long
  as the launcher runs. Each attempt pops the admin password prompt.
- **Everywhere:** **Esc** and **F11** on the launcher itself prompt for the
  password rather than exiting.

**Alt+Shift** (language/layout switching) is explicitly allowed so students
can switch keyboard layouts; everything else listed above is blocked.

> **Ctrl+Alt+Del cannot be intercepted by any application** — it's the Windows
> Secure Attention Sequence, handled by winlogon before hooks see it. Neuter
> the CAD screen instead: disable Task Manager, Lock, and Change Password via
> Policy Plus / Group Policy, or the registry keys in `kiosk-watchdog.bat`.

### Watchdog (auto-relaunch on crash)

`kiosk-watchdog.bat` keeps the launcher alive: if `Kiosk.exe` crashes or is
killed (non-zero exit), it relaunches after 2 seconds. It stops when you exit
cleanly via the admin menu (password → Exit, exit code 0) or when a
`stop.kiosk` marker file exists next to it.

To start it with the student's session, drop a shortcut in the Startup folder
(`shell:startup`) pointing at the script with `--kiosk` in the target:

    C:\Kiosk\kiosk-watchdog.bat --kiosk

## Config reference (`kiosk_config.json`)

Settings + password only (the app list is in `apps.json`):

```jsonc
{
  "password": { "salt": "...", "hash": "...", "iterations": 200000 },
  "fullscreen": true,           // start fullscreen (kiosk); false = windowed
  "columns": 4                  // buttons per row
}
```

App templates (`apps.json`):

```jsonc
[
  { "name": "GIMP", "patterns": ["gimp(?:\\.exe)?$"], "args": [] }
]
```

## License

MIT — use it however you like in your lab.
