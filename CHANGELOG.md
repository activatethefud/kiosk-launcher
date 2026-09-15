# Changelog

All notable changes to Kiosk Launcher.

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
