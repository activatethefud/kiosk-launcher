# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Kiosk Launcher (Windows, windowed build).
# Build with:  pyinstaller --noconfirm --clean Kiosk.spec
#
# This uses --onedir (a folder), NOT --onefile. Onefile extracts to a temp dir
# at runtime and antivirus frequently quarantines the extracted Qt DLLs, which
# shows up as "PySide6 missing". Onedir is faster to start and easier to debug.

from PyInstaller.utils.hooks import collect_all

# Force-collect PySide6 so the Qt DLLs and platform plugins (qwindows.dll etc.)
# are always bundled, even if automatic detection misses them.
datas, binaries, hiddenimports = collect_all('PySide6')

a = Analysis(
    ['kiosk_launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas + [('apps.json', '.')],   # bundle the default app templates
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Kiosk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                            # UPX can corrupt Qt plugins — keep off
    console=False,                        # windowed (no console)
    disable_windowed_traceback=False,     # let PyInstaller show a dialog on crash
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Kiosk',
)
