# AGENTS.md — guidance for AI coding agents working on this repository

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
tests/test_gui.py       # QTest behavior tests (clicks, dialogs, live reload)
apps.json              # app search templates (editable, copyable, TRACKED in git)
Kiosk.spec             # PyInstaller spec: windowed build, bundles apps.json
.github/workflows/build.yml  # CI: run tests + build Kiosk-windows.zip
kiosk.bat              # Windows: install + enable/disable the kiosk shell (HKCU)
diagnose-windows.ps1   # Windows: machine-level diagnostic (VC++ runtime, Qt plugin, event log)
README.md              # user-facing docs + Windows shell deployment recipe
AGENTS.md              # this file
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

# GUI tests drive real widgets/dialogs offscreen (QT_QPA_PLATFORM=offscreen)
python3 -m unittest tests.test_gui -v

# compile check
python3 -m py_compile kiosk_launcher.py

# headless GUI smoke test
QT_QPA_PLATFORM=offscreen python3 kiosk_launcher.py --smoke
```

### Testing the Windows batch scripts (Linux, via Wine)

The `*.bat` scripts are Windows-only. On a Linux dev box, if Wine is present
(`which wine`), use it to actually run them rather than only eyeballing them:
`wine cmd /c` maps `C:\` to a prefix's `drive_c`, so `C:\Kiosk` is just a
folder inside the prefix.

```bash
export WINEDEBUG=-all
export WINEPREFIX=$(mktemp -d)/prefix
wineboot -i                                   # one-time prefix init
mkdir -p "$WINEPREFIX/drive_c/src"
cp kiosk.bat "$WINEPREFIX/drive_c/src/"
printf x > "$WINEPREFIX/drive_c/src/Kiosk.exe"   # dummy payload for install
wine cmd /c 'cd /d C:\src && kiosk.bat install'
wine cmd /c 'cd /d C:\Kiosk && kiosk.bat status'
rm -rf "$WINEPREFIX"                          # throw the prefix away afterwards
```

Notes:

- Always use a throwaway `WINEPREFIX`; `reg add HKCU\...` writes land in that
  prefix, never on the real machine.
- Wine's `xcopy` / `mkdir` / `reg` are close enough to exercise control flow,
  error handling and exit codes, but they do **not** prove real Windows ACL/UAC
  behavior.
- Batch parsing of `goto`, labels and parenthesised blocks is the usual failure
  mode: exercise every subcommand (`install` / `enable` / `disable` / `status`)
  plus bad/absent arguments, and check `%ERRORLEVEL%`.
- If Wine is not installed, skip this and rely on the unit/GUI tests.

## Dependencies

- **Runtime GUI:** PySide6 (Qt 6) only. It is imported lazily inside
  `run_gui()`, so `--scan` and `--set-password` work with the stdlib alone.
- **Tests:** stdlib `unittest` + `unittest.mock` only. No pytest required.

## Architecture

Top-level functions (module `kiosk_launcher`):

- `BUILTIN_APPS` — seed presets, used only to populate `apps.json` when it is
  missing. Entries: `{"name", "patterns": [regex...], "args", "elevated"?}`.
  Regexes are matched **case-insensitively** against candidate exe **full
  paths** with `re.search`. Always anchor to the filename with `$`; when
  several suites ship the same binary name, anchor on the install directory
  (LibreOffice and OpenOffice both ship `soffice`).
- `seed_config()` / `load_config(path)` / `save_config(cfg, path)` — settings +
  password I/O (no app data). `load_config` repairs missing keys and is
  idempotent. Config is JSON.
- `normalize_app(entry)` / `load_apps(path)` / `save_apps(apps, path)` /
  `add_app(apps, entry)` / `remove_apps(apps, names)` — the app list lives in
  `apps.json` (source of truth). `normalize_app` coerces string patterns/args
  to lists, preserves a truthy `elevated` flag, and drops invalid entries. `load_apps` seeds the file from
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
  `(found, missing)` where `found` is a list of
  `{"name", "path", "args", "elevated"?}` and `missing` is a list of names.
  A bad regex is reported as missing (stderr
  warning) rather than crashing.
- `launch(app)` — `subprocess.Popen`, non-blocking; returns `None` or an error
  string. Windows Store aliases (paths containing `WindowsApps`) are launched
  via `cmd /c start`. When `app["elevated"]` is set it delegates to
  `_launch_elevated` → `_shell_execute_runas` (Windows `ShellExecuteW` with the
  `runas` verb / UAC; Linux `pkexec`). `_shell_execute` is a thin, patchable
  wrapper around the Win32 call.
- `find_terminal(kind)` / `shutdown_system()` / `logout_user()` — admin-menu
  helpers. `find_terminal` resolves `cmd` / `powershell` via `shutil.which`
  (`TERMINALS` maps kind → candidate exe names). The power actions call
  `_run_detached` (`shutdown /s|/l` on Windows; `systemctl poweroff` /
  `loginctl terminate-user` / `gnome-session-quit` on Linux). All return `None`
  or an error string.
- `is_blocked_hotkey(vk, alt_down, ctrl_down)` / `KioskHotkeyBlocker` (Windows
  only) — kiosk escape-hotkey blocking. `is_blocked_hotkey` is a pure,
  cross-platform decision function (unit-tested). `KioskHotkeyBlocker` installs
  a `WH_KEYBOARD_LL` ctypes hook on a background thread that swallows the Win
  key, Alt+Tab, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc, Alt+Space and Alt+F4, and
  calls a callback (which emits a Qt signal → password prompt) for each blocked
  combo. Ctrl+Alt+Del is flagged but Windows delivers the SAS to winlogon, not
  the hook — disable Task Manager/lock/change-password via policy instead.
- `AddAppDialog` / `RemoveAppDialog` / `MainWindow` (module-level, defined only
  when `_HAS_QT` is True) — importable for GUI tests.
  `MainWindow(cfg, cfg_path, apps, apps_path, kiosk)` is constructed explicitly
  (no closure variables). Widgets expose `objectName`s (e.g. `app:<name>`,
  `addapp_name`, `addapp_elevated`, `removeapp_list`) for deterministic lookup
  in tests. The password-gated admin menu offers add/remove/change-password/
  rescan, a **Terminal** submenu (Command Prompt / PowerShell, each optionally
  as administrator), and **Shut down** / **Log out** (both confirmed first).
- `fatal_error(message)` / `error_log_path()` / `_install_excepthook()` —
  errors in a windowed build are invisible (stderr is discarded), so fatal
  errors are appended to `kiosk-error.log` next to the exe and shown in a
  Windows message box; `sys.excepthook` is replaced so Qt slot exceptions are
  logged too. `run_gui` wraps setup in try/except and calls `fatal_error`.
- `_bundled_apps_path()` / `load_apps(path)` — when frozen, a bundled
  `apps.json` (from `sys._MEIPASS`) is copied next to the exe if none exists,
  so a user-edited `apps.json` always wins over the bundled default.
- `run_gui(args)` — PySide6 UI. `MainWindow` holds the grid, admin menu,
  password prompts, and close/keyboard handling. Admin add/remove app edits
  the in-memory app list and calls `save_apps`. A `QFileSystemWatcher` +
  debounced `QTimer` live-reloads `apps.json` when it changes on disk. `run_gui`
  builds `QApplication` + `MainWindow`, starts the Windows hotkey blocker in
  kiosk mode, and runs the event loop.
- CLI modes: `cmd_scan(args)`, `cmd_set_password(args)`, `cmd_diagnose(args)`.

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
- GUI tests live in `tests/test_gui.py`: create a `MainWindow` directly, drive
  modal dialogs/popups with `QTimer.singleShot` + helpers that type into the
  active modal and click OK, and use `QTest` for clicks/keys. They run under
  the offscreen platform (set at the top of the file).
- New behavior should come with a test in `tests/test_kiosk_launcher.py`.

## Versioning (handled automatically by the agent)

You are responsible for keeping the version current — the user should not have
to ask. Follow **SemVer** (`MAJOR.MINOR.PATCH`) and bump based on the size of
the change:

- **MAJOR** (`x.0.0`): breaking changes — config/`apps.json` format changes,
  removed features, or anything that breaks existing deployments.
- **MINOR** (`x.y.0`): new user-visible features or meaningful additions
  (new presets, new modes, new helper scripts, diagnostics, etc.).
- **PATCH** (`x.y.z`): bug fixes, robustness hardening, false-positive fixes,
  refactors with no behavior change, docs-only and test-only changes.

When bumping, keep all three in sync:

1. `VERSION` in `kiosk_launcher.py`
2. a new entry in `CHANGELOG.md` under the new version
3. an annotated git tag: `git tag v<X.Y.Z>`

Judgment: a small one-off fix that lands the same day as an existing
unreleased version does not need another bump — fold it into the current
version's changelog entry. Trivial doc/test tweaks may skip a bump entirely.

## Deployment notes (Windows custom shell)

Freeze with PyInstaller (`Kiosk.spec`, onedir + windowed), then install and set
the shell per-user — `kiosk.bat` only ever writes the current user's HKCU:

```bat
kiosk.bat install        :: copy the folder to C:\Kiosk (no elevation)
kiosk.bat enable         :: run AS the kiosk user; sets HKCU\...\Winlogon\Shell
kiosk.bat disable        :: restores explorer.exe for the current user
kiosk.bat status         :: show the current shell + policy values
```

See README.md for the full recipe, including why the **HKLM** shell value must
be avoided and why an admin escape-hatch account is required.

There is deliberately **no watchdog**: the `Shell` value must be an `.exe`, so
`Kiosk.exe` runs directly and a crash leaves a shell-less session. Recover by
logging in on the admin account and running `kiosk.bat disable` for the kiosk
user (e.g. `runas /user:Student "C:\Kiosk\kiosk.bat disable"`).
