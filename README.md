# Kiosk Launcher

A cross-platform, locked-down app launcher for school/classroom computers.
It dynamically discovers installed apps (so paths don't have to be known in
advance), shows them as big buttons, and keeps an admin-only area for adding
more apps by regex.

## Features

- **Presets:** the Microsoft Office suite (Word, Excel, PowerPoint, Outlook,
  OneNote, Access, Publisher, Visio, Project), LibreOffice, Scratch, VS Code,
  VSCodium, GIMP, text editors (Notepad++, Sublime Text, gedit, Kate, Vim,
  Emacs, Geany), dev editors (PyCharm, IntelliJ IDEA, Eclipse, Code::Blocks,
  Dev-C++), FOSS video editors (Kdenlive, Shotcut, OpenShot, Olive, Avidemux,
  Blender), audio tools (Audacity, Ardour, LMMS), PDF viewers (SumatraPDF,
  Okular, MuPDF), VirtualBox, and educational software (Thonny, Mu Editor,
  Sonic Pi, Arduino IDE, Processing, DrRacket, Greenfoot, BlueJ, OpenSCAD,
  Krita, Inkscape, Tux Paint, GeoGebra, Stellarium, wxMaxima, FreeCAD,
  LibreCAD, Fritzing, Anki, MuseScore). No browsers or games.
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
Kiosk.spec                  # PyInstaller spec (windowed build, bundles apps.json)
kiosk-watchdog.bat          # Windows: relaunch the launcher on crash
kiosk-shell.bat             # Windows: enable/disable the registry kiosk shell
tests/test_kiosk_launcher.py
tests/test_gui.py           # QTest behavior tests (clicks, dialogs, live reload)
AGENT.md                    # guidance for AI coding agents
README.md
.gitattributes              # CRLF line endings for *.bat
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

## Deploy on Windows

The launcher ships as a folder (`dist\Kiosk\`) containing `Kiosk.exe` and its
runtime. Two deployment modes are supported; pick one per lab.

### 1. Build once (on any Windows machine or VM)

PyInstaller cannot cross-compile, so build on Windows:

```powershell
pip install pyinstaller pyside6-essentials
pyinstaller --noconfirm --clean Kiosk.spec
```

- `Kiosk.spec` bundles `apps.json`, keeps the build windowed, and enables
  PyInstaller's own crash dialog as a fallback.
- Output: `dist\Kiosk\Kiosk.exe`

### 2. Client install (repeat on every lab machine)

Common to both modes:

1. Create two local accounts:
   - **Admin** — administrator, normal desktop (your escape hatch).
   - **Student** — *standard* (non-admin) user.
2. Copy the whole `dist\Kiosk\` folder to `C:\Kiosk\`. Drop your customized
   `apps.json` next to `Kiosk.exe` if you have one.
3. Log in as Student and confirm the launcher finds the installed apps:
   `C:\Kiosk\Kiosk.exe --scan` (or use **Admin → Rescan**). Then change the
   admin password via **Admin → Change password…** (the windowed exe has no
   console, so use the GUI rather than `--set-password`).

Then choose one mode:

#### Mode A — autostart on top of Windows (lower risk, easy to revert)

- Put a shortcut in the Student's Startup folder (`shell:startup`) with target
  `C:\Kiosk\kiosk-watchdog.bat --kiosk`.
- Lock policies with [Policy Plus](https://github.com/Fleex255/PolicyPlus)
  (Home) or `gpedit.msc` (Pro): disable Task Manager, Win+X, Alt+Tab, etc.

#### Mode B — replace explorer.exe (true kiosk shell, works on Home + Pro)

The repo includes `kiosk-shell.bat` to do this safely.

Enable (run **as the Student user**):

```bat
C:\Kiosk\kiosk-shell.bat enable
```

This sets the student's shell to `C:\Kiosk\Kiosk.exe` and disables Task
Manager, Lock, and Change Password for that user. Log off and back on.

> Do **not** set the HKLM `Shell` value or you can lock yourself out. Keep the
> Admin account on the normal explorer shell.

Recovery (run **as an Administrator**, with the student logged off):

```bat
C:\Kiosk\kiosk-shell.bat disable Student
```

This restores `explorer.exe` and re-enables the CAD options for the student.

#### Verify on each client

- [ ] Launcher starts fullscreen and app cards appear
- [ ] `Alt+Tab`, Win key, `Ctrl+Esc`, and `Alt+F4` prompt for the password
- [ ] Task Manager is disabled (Ctrl+Alt+Del has no Task Manager)
- [ ] Editing `apps.json` shows up without restarting (live reload)
- [ ] Admin → Exit (password) stops the watchdog (Mode A)

> **Always test in a VM or on a spare machine first**, and keep an admin
> account with a normal desktop.

### 3. If the exe shows nothing

Errors in a windowed build go to stderr, which is invisible. The launcher
**writes every fatal error to `kiosk-error.log` next to the exe** and pops a
message box on Windows. To see errors live, build a console version:

```powershell
pyinstaller --noconfirm --clean --onedir --console --name KioskDebug kiosk_launcher.py
.\dist\KioskDebug\KioskDebug.exe
```

or run the existing exe from a terminal:

```powershell
.\dist\Kiosk\Kiosk.exe
```

#### "PySide6 is required" / missing Qt DLLs

This almost always means PyInstaller didn't bundle Qt. In order of likelihood:

1. Build in the **same Python environment** where PySide6 is installed:
   ```powershell
   python -m pip install pyinstaller pyside6-essentials
   python -c "import PySide6.QtWidgets; print('ok')"
   python -m PyInstaller --noconfirm --clean Kiosk.spec
   ```
   (`python -m PyInstaller` guarantees you use the same interpreter.)
2. `Kiosk.spec` now **force-collects PySide6** (`collect_all`), so rebuilding
   with the spec pulls in every Qt DLL and platform plugin.
3. Use **`--onedir`** (the spec's default), **not `--onefile`** — onefile
   extracts to a temp dir at runtime and antivirus often quarantines the
   extracted Qt DLLs, which produces exactly this symptom.
4. As a last resort, add `--collect-all PySide6` on the command line.

#### Works on some machines but silently fails on one

Look at `kiosk-error.log` next to the exe on the failing machine:

- **No `START ...` line** → Python never started. This is a machine-level
  problem: install the **Visual C++ Redistributable** (Qt needs
  `vcruntime140.dll` / `msvcp140.dll`), and check antivirus quarantine and
  SmartScreen.
- **`START` line but nothing after it** → Python started then died early; the
  following lines (or the message box) show the reason.
- Also check **Event Viewer → Windows Logs → Application** for the crash
  record.

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

`kiosk-watchdog.bat` supervises the launcher in a loop:

```text
:loop
   if stop.kiosk exists → delete it, stop
   run Kiosk.exe %*
   if exit code == 0  → stop          (admin exited via password)
   else              → wait 2 s → loop again
```

| Kiosk.exe exit | Watchdog action |
|---|---|
| `0` — admin menu → Exit (password) | **stop** (so you can get back in) |
| non-zero — crash or `taskkill /f` | wait 2 s, **relaunch** |
| `stop.kiosk` marker file present | delete the marker, **stop** |

Notes:

- It looks for `Kiosk.exe` in **`C:\Kiosk`** (falls back to the script's own
  folder if not found there).
- It's for **Mode A**: drop a shortcut in `shell:startup` pointing at
  `C:\Kiosk\kiosk-watchdog.bat --kiosk`.
- It **can't be the shell itself** — the registry `Shell` value must be an
  `.exe`, so Mode B runs `Kiosk.exe` directly.
- Three commented-out `reg add` lines (DisableTaskMgr / DisableLockWorkstation
  / DisableChangePassword) harden the Ctrl+Alt+Del screen if un-commented.

## Config reference (`kiosk_config.json`)

Settings + password only (the app list is in `apps.json`):

```jsonc
{
  "password": { "salt": "...", "hash": "...", "iterations": 200000 },
  "fullscreen": true,           // start fullscreen (kiosk); false = windowed
  "columns": 0,                 // 0 = auto-fit; >0 = fixed number of columns
  "card_size": "auto"           // auto | small | medium | large
}
```

Card grid presets (built in, but the config above can pin one):

| preset | card | font | typical screen |
|---|---|---|---|
| `small` | 150×110 | 16px | < 1280 wide |
| `medium` | 180×130 | 20px | 1280–1919 |
| `large` | 220×160 | 24px | ≥ 1920 |

`"card_size": "auto"` picks the preset by screen width; `"columns": 0`
auto-fits the number of columns to the window width (both adapt live on resize).

App templates (`apps.json`):

```jsonc
[
  { "name": "GIMP", "patterns": ["gimp(?:\\.exe)?$"], "args": [] }
]
```

## License

MIT — use it however you like in your lab.
