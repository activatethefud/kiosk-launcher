# AGENT.md — guidance for AI coding agents working on this repository

## What this project is

A **single-file, cross-platform kiosk launcher** for school/classroom computers
(Linux + Windows). It dynamically discovers installed applications, shows them
as big buttons, and provides a password-protected admin area to add apps by
regex. It is designed to be usable as a Windows custom shell (replacing
`explorer.exe`) but runs on Linux for development/testing.

File layout:

```
kiosk_launcher.py      # the entire application
tests/test_kiosk_launcher.py
apps.json              # app search templates (editable, copyable, TRACKED in git)
kiosk-watchdog.bat     # Windows: relaunch the launcher if it crashes
README.md              # user-facing docs + Windows shell deployment recipe
AGENT.md               # this file
.gitattributes         # CRLF for *.bat on checkout
kiosk_config.json      # runtime-generated settings + password, GITIGNORED
```

## Commands

```bash
python3 kiosk_launcher.py                    # run fullscreen (default)
python3 kiosk_launcher.py --windowed         # windowed (dev)
python3 kiosk_launcher.py --kiosk            # force frameless fullscreen
python3 kiosk_launcher.py --scan             # print discovery results, no GUI
python3 kiosk_launcher.py --set-password     # change admin password (interactive)
python3 kiosk_launcher.py --config PATH      # use a specific config file
python3 kiosk_launcher.py --apps PATH        # use a specific apps.json

# tests (stdlib unittest; also runnable with pytest)
python3 -m unittest discover -s tests -v

# compile check
python3 -m py_compile kiosk_launcher.py

# headless GUI smoke test
QT_QPA_PLATFORM=offscreen python3 kiosk_launcher.py --smoke
```

## Dependencies

- **Runtime GUI:** PySide6 (Qt 6) only. It is imported lazily inside
  `run_gui()`, so `--scan` and `--set-password` work with the stdlib alone.
- **Tests:** stdlib `unittest` + `unittest.mock` only. No pytest required.

## Architecture

Top-level functions (module `kiosk_launcher`):

- `BUILTIN_APPS` — seed presets, used only to populate `apps.json` when it is
  missing. Entries: `{"name", "patterns": [regex...], "args"}`. Regexes are
  matched **case-insensitively** against candidate exe **full paths** with
  `re.search`. Always anchor to the filename with `$`.
- `seed_config()` / `load_config(path)` / `save_config(cfg, path)` — settings +
  password I/O (no app data). `load_config` repairs missing keys and is
  idempotent. Config is JSON.
- `normalize_app(entry)` / `load_apps(path)` / `save_apps(apps, path)` /
  `add_app(apps, entry)` / `remove_apps(apps, names)` — the app list lives in
  `apps.json` (source of truth). `normalize_app` coerces string patterns/args
  to lists and drops invalid entries. `load_apps` seeds the file from
  `BUILTIN_APPS` when absent, falls back to presets in memory on parse errors
  (without overwriting the user's file), and respects an explicitly empty
  list. `add_app` appends a normalized entry (raising `ValueError` on invalid
  input); `remove_apps` removes by name case-insensitively and returns the
  count removed.
- `hash_password(pw, salt=None, iterations=200_000)` / `verify_password(pw, pw_cfg)` /
  `set_password(cfg, new_password)` — PBKDF2-HMAC-SHA256, random salt via
  `secrets`, constant-time compare; `set_password` replaces the stored hash
  in place.
- `gather_candidates()` — returns a `set` of normalized executable paths,
  platform-specific (see "Discovery" below).
- `discover_apps(apps)` — takes the app template list (NOT the config); returns
  `(found, missing)` where `found` is a list of `{"name", "path", "args"}` and
  `missing` is a list of names. A bad regex is reported as missing (stderr
  warning) rather than crashing.
- `launch(app)` — `subprocess.Popen`, non-blocking; returns `None` or an error
  string. Windows Store aliases (paths containing `WindowsApps`) are launched
  via `cmd /c start`.
- `is_blocked_hotkey(vk, alt_down, ctrl_down)` / `KioskHotkeyBlocker` (Windows
  only) — kiosk escape-hotkey blocking. `is_blocked_hotkey` is a pure,
  cross-platform decision function (unit-tested). `KioskHotkeyBlocker` installs
  a `WH_KEYBOARD_LL` ctypes hook on a background thread that swallows the Win
  key, Alt+Tab, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc, Alt+Space and Alt+F4, and
  calls a callback (which emits a Qt signal → password prompt) for each blocked
  combo. Ctrl+Alt+Del is flagged but Windows delivers the SAS to winlogon, not
  the hook — disable Task Manager/lock/change-password via policy instead.
- `run_gui(args)` — PySide6 UI. `MainWindow` holds the grid, admin menu,
  password prompts, and close/keyboard handling. Admin add/remove app edits
  the in-memory app list and calls `save_apps`. A `QFileSystemWatcher` +
  debounced `QTimer` live-reloads `apps.json` when it changes on disk.
- CLI modes: `cmd_scan(args)`, `cmd_set_password(args)`.

### Discovery (the important part)

`gather_candidates()` must not assume install locations:

- **Windows:** `PATH` dirs, `ProgramFiles`, `ProgramFiles(x86)`, `ProgramData`,
  `%LOCALAPPDATA%\Programs`, `%LOCALAPPDATA%\Microsoft\WindowsApps`,
  plus the `App Paths` registry key (HKLM 64/32 + HKCU).
- **Linux:** `PATH` dirs, `/opt`, `/usr/local/bin`, `/snap/bin`, flatpak export
  dirs, `~/.local/bin`, `~/Applications`, plus binary paths parsed from
  `.desktop` files (`Exec=` field).

## Conventions

- Keep the launcher a **single file**. If you add a dependency, justify it; the
  only sanctioned runtime dependency is PySide6.
- Guard Windows-only code with `os.name == "nt"`; never hard-code paths.
- Cross-platform strings/args: use `shlex.split(posix=(os.name == "posix"))`.
- Config is **not** committed (gitignored). `apps.json` **is** committed — it
  is the canonical, centrally-managed template. Do not commit real password
  hashes.
- When adding a preset, add it to `BUILTIN_APPS` (and to the tracked
  `apps.json`) with filename-anchored regexes.
- Tests: prefer `mock.patch.object(kiosk_launcher, "gather_candidates", ...)`
  for discovery tests so they are deterministic and machine-independent.
- New behavior should come with a test in `tests/test_kiosk_launcher.py`.

## Deployment notes (Windows custom shell)

Freeze with PyInstaller (`--onefile --windowed`), then set the shell per-user:

```
reg add "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "C:\Kiosk\Kiosk.exe" /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 1 /f
```

See README.md for the full recipe, including why the **HKLM** shell value must
be avoided and why an admin escape-hatch account is required.

For the simpler "run on top of Windows" deployment, use `kiosk-watchdog.bat`
in the student's Startup folder to auto-relaunch on crash (stops on a clean
admin Exit, or when a `stop.kiosk` marker file is present).
