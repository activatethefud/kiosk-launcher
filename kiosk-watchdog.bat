@echo off
rem ===========================================================================
rem  Kiosk Launcher watchdog
rem
rem  Relaunches the launcher if it crashes or is killed, and stops when:
rem    * the launcher exits cleanly (exit code 0 = admin entered the password
rem      and chose Exit from the menu), or
rem    * a file named "stop.kiosk" exists in C:\Kiosk.
rem
rem  Usage:
rem    kiosk-watchdog.bat           (uses the fullscreen setting in config)
rem    kiosk-watchdog.bat --kiosk   (force locked fullscreen)
rem
rem  Ctrl+Alt+Del cannot be blocked by any application (Windows winlogon
rem  handles it first). Neuter the CAD screen by un-commenting the hardening
rem  lines below and running this script once as the student user.
rem ===========================================================================
setlocal EnableExtensions

set "KIOSK_DIR=C:\Kiosk"
set "APP=%KIOSK_DIR%\Kiosk.exe"
set "STOPFILE=%KIOSK_DIR%\stop.kiosk"

rem Fall back to this script's own folder if Kiosk.exe isn't in C:\Kiosk yet.
if not exist "%APP%" set "APP=%~dp0Kiosk.exe"

rem --- Optional hardening (remove "rem" to apply) ---
rem reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 1 /f
rem reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 1 /f
rem reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 1 /f

:loop
if exist "%STOPFILE%" (
    del "%STOPFILE%" >nul 2>&1
    exit /b 0
)

"%APP%" %*

if "%ERRORLEVEL%"=="0" (
    rem Clean exit via the admin menu (password). Do not relaunch.
    exit /b 0
)

rem Non-zero exit: crash or kill. Pause, then relaunch.
timeout /t 2 /nobreak >nul
goto loop
