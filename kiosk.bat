@echo off
rem ===========================================================================
rem  kiosk.bat - Kiosk Launcher control script (Windows)
rem
rem    install   copy this folder to C:\Kiosk
rem    enable    set THIS user's shell to the kiosk  (run as the kiosk user)
rem    disable   restore explorer.exe for THIS user  (run as the kiosk user)
rem    status    show the current shell + policy values
rem
rem  Everything here is per-user (HKCU / the user's own files), so NO command
rem  needs admin: run enable/disable while logged in as the kiosk user, then
rem  log off and back on. (If C:\Kiosk already exists with a restrictive ACL,
rem  a standard user's xcopy may fail - then copy the folder as admin once.)
rem
rem  Do NOT set the HKLM Shell value - a bad machine-wide shell can lock every
rem  account out. Always keep an admin account on the normal explorer shell.
rem ===========================================================================
setlocal EnableExtensions

set "KIOSK_DIR=C:\Kiosk"
set "EXE=%KIOSK_DIR%\Kiosk.exe"
set "SHELL_KEY=HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
set "POLICY_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System"

if /i "%~1"=="install" goto :install
if /i "%~1"=="enable"  goto :enable
if /i "%~1"=="disable" goto :disable
if /i "%~1"=="status"  goto :status
if /i "%~1"=="check"   goto :status
goto :usage

:usage
echo Usage: kiosk.bat {install ^| enable ^| disable ^| status}
exit /b 1

:install
rem Already running from C:\Kiosk? Nothing to copy.
if /i "%~dp0"=="%KIOSK_DIR%\" goto :install_check
echo Copying to %KIOSK_DIR% ...
if not exist "%KIOSK_DIR%" mkdir "%KIOSK_DIR%" 2>nul
if not exist "%KIOSK_DIR%" (
    echo ERROR: could not create %KIOSK_DIR%. Run as admin, or create it manually.
    exit /b 1
)
xcopy "%~dp0*" "%KIOSK_DIR%\" /E /I /Y >nul
if errorlevel 1 (
    echo ERROR: copy failed - is %KIOSK_DIR% writable?
    exit /b 1
)
:install_check
if not exist "%EXE%" (
    echo ERROR: %EXE% is missing from the copy. Build/copy the full Kiosk folder.
    exit /b 1
)
echo Installed to %KIOSK_DIR%.
echo Next: log in as the kiosk user and run  %KIOSK_DIR%\kiosk.bat enable
exit /b 0

:enable
if not exist "%EXE%" (
    echo ERROR: %EXE% not found. Run "kiosk.bat install" first.
    exit /b 1
)
reg add "%SHELL_KEY%" /v Shell /t REG_SZ /d "%EXE%" /f
call :policies 1
echo Kiosk shell ENABLED for %USERNAME%. Log off and back on.
exit /b 0

:disable
reg add "%SHELL_KEY%" /v Shell /t REG_SZ /d "explorer.exe" /f
call :policies 0
echo Kiosk shell DISABLED for %USERNAME%. Log off and back on.
exit /b 0

:status
echo Shell for %USERNAME% (should be %EXE% when enabled):
reg query "%SHELL_KEY%" /v Shell 2>nul
for %%P in (DisableTaskMgr DisableLockWorkstation DisableChangePassword) do (
    reg query "%POLICY_KEY%" /v %%P 2>nul
)
exit /b 0

:policies
rem %1 = 1 to lock the Ctrl+Alt+Del options, 0 to restore them
for %%P in (DisableTaskMgr DisableLockWorkstation DisableChangePassword) do (
    reg add "%POLICY_KEY%" /v %%P /t REG_DWORD /d %1 /f >nul
)
exit /b 0
