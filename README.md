# Kiosk Launcher

A cross-platform, locked-down app launcher for school/classroom computers.
It dynamically discovers installed apps (so paths don't have to be known in
advance), shows them as big buttons, and keeps an admin-only area for adding
more apps by regex.

## Features

- **Presets:** LibreOffice, Scratch, VS Code, VSCodium, Microsoft Word
- **Dynamic discovery** (no hard-coded paths):
  - *Windows:* `PATH`, `Program Files`, `Program Files (x86)`, `ProgramData`,
    `%LOCALAPPDATA%\Programs`, Windows "App Paths" registry, Store app aliases
  - *Linux:* `PATH`, `/opt`, `/usr/local/bin`, snap/flatpak export dirs,
    `~/.local/bin`, and `.desktop` files
- **Admin area (password-protected):**
  - Add an app by name + one-or-more regexes (matched against the exe path)
  - Remove apps, change the password, rescan
- **Kiosk mode:** frameless fullscreen; exiting requires the admin password
- **One config file** (`kiosk_config.json`) — auto-generated on first run
  (gitignored), so each machine can build its own.

## Project layout

```
kiosk_launcher.py           # the entire application (single file)
tests/test_kiosk_launcher.py
AGENT.md                    # guidance for AI coding agents
README.md
kiosk_config.json           # runtime-generated, not committed
```

## Quick start

```bash
# install the GUI toolkit (Debian)
pip install --user --break-system-packages pyside6-essentials
# or: sudo apt install python3-pyside6

python3 kiosk_launcher.py                # windowed (development)
python3 kiosk_launcher.py --kiosk        # frameless fullscreen (locked)
python3 kiosk_launcher.py --scan         # show what was found, no GUI
python3 kiosk_launcher.py --set-password # change admin password
python3 kiosk_launcher.py --config X.json
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

The added entry is saved to `kiosk_config.json` and the launcher rescans
immediately.

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
2. Copy `Kiosk.exe` + `kiosk_config.json` to `C:\Kiosk\`.
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

## Config reference (`kiosk_config.json`)

```jsonc
{
  "password": { "salt": "...", "hash": "...", "iterations": 200000 },
  "fullscreen": false,          // true = start in kiosk mode
  "columns": 4,                 // buttons per row
  "apps": [
    { "name": "GIMP", "patterns": ["gimp(?:\\.exe)?$"], "args": [] }
  ]
}
```

## License

MIT — use it however you like in your lab.
