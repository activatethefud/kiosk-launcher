# Changelog

All notable changes to Kiosk Launcher.

## [0.7.0] - 2026-09-16

- **Deployment scripts unified:** one `kiosk.bat` with
  `install` / `enable` / `disable` / `status` replaces `install.bat` and
  `kiosk-shell.bat`. Enable/disable write the *current user's*
  `HKCU\...\Winlogon\Shell` key, so the whole script is **elevation-free** —
  no more self-elevation, offline `NTUSER.DAT` hive loading, or username
  arguments. (`install` copies the folder; no admin needed either, and it now
  reports a failed/partial copy instead of silently claiming success.)
- Added `status` (shows the current shell + Task Manager/Lock/Change Password
  policy values) for diagnosing "works on one PC, not another".
- **Removed `kiosk-watchdog.bat`:** with `Shell` pointing straight at
  `Kiosk.exe` a watchdog has nowhere to run (the `Shell` value must be an
  `.exe`, and a Startup shortcut never executes under a replaced shell), so the
  "run on top of Windows" deployment mode is gone. `kiosk.bat enable` now also
  sets the Ctrl+Alt+Del hardening the watchdog used to mention.
- **Removed `install.bat` and `kiosk-shell.bat`** (superseded by `kiosk.bat`).

## [0.6.0] - 2026-09-15

- Added `install.bat`: one-shot client installer (self-elevates, copies to
  `C:\Kiosk`, enables the kiosk shell). Bundled into the CI release zip.

## [0.5.0] - 2026-09-15

- GitHub Actions workflow: runs the test suite, builds the bundled Windows
  `Kiosk-windows.zip`, and attaches it to GitHub Releases on `v*` tags.

## [0.4.1] - 2026-09-15

- `kiosk-shell.bat` now self-elevates (UAC) and defaults to the offline
  `Student` hive, since the per-user `Shell` key can't be written unelevated
  on many machines.

## [0.4.0] - 2026-09-15

- `kiosk-shell.bat`: added `check` subcommand and offline `enable <Username>`,
  plus self-verification after writing — to diagnose the "works on one PC,
  not another" shell-replacement issue.

## [0.3.0] - 2026-09-15

- **Diagnostics:** `--diagnose` in-app report + `diagnose-windows.ps1` machine-level report
- **Versioning:** version label in the GUI, `--version` CLI flag, window title shows version
- **Adaptive grid:** card-size presets (`small`/`medium`/`large`/`auto`) and auto-fit columns that re-layout on resize
- **Robustness:** repair malformed config/password, tolerate bad app entries, survive per-directory scan errors, visible error logging (`kiosk-error.log`) and startup marker
- **Fixes:** gedit no longer matches `regedit`; Emacs no longer matches `ctags.emacs`
- **Build:** `Kiosk.spec` force-collects PySide6 and disables UPX for reliability

## [0.2.0] - 2026-09-14

- **External `apps.json`** with live reload (`QFileSystemWatcher`)
- **Kiosk lockdown:** Windows low-level keyboard hook (Win key, Alt+Tab, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc, Alt+Space, Alt+F4), Esc/F11 prompt
- **Deployment helpers:** `kiosk-watchdog.bat`, `kiosk-shell.bat` (Plan B registry shell)
- **Presets expanded:** Microsoft Office suite, text editors, dev editors, FOSS video/audio, PDF viewers, VirtualBox, educational software
- Fullscreen by default, fixed card sizing, wrapped card text

## [0.1.0] - 2026-09-13

- Initial release: cross-platform launcher with dynamic app discovery,
  regex-based app templates, password-protected admin area
