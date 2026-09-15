@echo off
rem ===========================================================================
rem  kiosk-shell.bat — enable/disable/check the real kiosk shell (Plan B)
rem
rem  This script SELF-ELEVATES (UAC prompt) and writes to the STUDENT user's
rem  offline registry hive, so the student account is always targeted correctly
rem  (writing the per-user Shell key unelevated is blocked on many machines).
rem
rem  Usage:
rem    kiosk-shell.bat enable  [Username]   enable kiosk shell (default: Student)
rem    kiosk-shell.bat disable [Username]   restore explorer.exe
rem    kiosk-shell.bat check   [Username]   show the current setting
rem
rem  * enable/disable/check <Username> run elevated; the target user must be
rem    LOGGED OFF (their hive can't be loaded while in use).
rem  * "check" with NO username reads the CURRENT user's HKCU (no admin needed,
rem    so you can run it while logged in as the student to see what they have).
rem ===========================================================================
setlocal EnableExtensions

set "KIOSK_EXE=C:\Kiosk\Kiosk.exe"

rem --- "check" with no username: read the current user's hive, no elevation ---
if /i "%~1"=="check" if "%~2"=="" goto :check_current

rem --- Everything else needs admin; self-elevate if necessary ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

set "STUDENT_USER=%~2"
if "%STUDENT_USER%"=="" set "STUDENT_USER=Student"
set "HIVE=HKU\KioskStudent"

if /i "%~1"=="enable"  goto :enable
if /i "%~1"=="disable" goto :disable
if /i "%~1"=="check"   goto :check_offline

echo Usage:
echo   kiosk-shell.bat enable  [Username]
echo   kiosk-shell.bat disable [Username]
echo   kiosk-shell.bat check   [Username]
exit /b 1

:enable
if not exist "%KIOSK_EXE%" (
    echo ERROR: %KIOSK_EXE% not found. Build and copy it there first.
    exit /b 1
)
if not exist "C:\Users\%STUDENT_USER%\NTUSER.DAT" (
    echo ERROR: C:\Users\%STUDENT_USER%\NTUSER.DAT not found.
    exit /b 1
)
reg load "%HIVE%" "C:\Users\%STUDENT_USER%\NTUSER.DAT" >nul
if errorlevel 1 (
    echo ERROR: could not load %STUDENT_USER%'s hive. Is the user logged off?
    exit /b 1
)
echo Enabling kiosk shell for %STUDENT_USER% ...
reg add "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "%KIOSK_EXE%" /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 1 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 1 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 1 /f >nul
echo Verifying - the Shell value should read:
reg query "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell
reg unload "%HIVE%" >nul
echo.
echo Enabled. %STUDENT_USER% must log off and back on.
exit /b 0

:disable
if not exist "C:\Users\%STUDENT_USER%\NTUSER.DAT" (
    echo ERROR: C:\Users\%STUDENT_USER%\NTUSER.DAT not found.
    exit /b 1
)
reg load "%HIVE%" "C:\Users\%STUDENT_USER%\NTUSER.DAT" >nul
if errorlevel 1 (
    echo ERROR: could not load %STUDENT_USER%'s hive. Is the user logged off?
    exit /b 1
)
echo Disabling kiosk shell for %STUDENT_USER% ...
reg add "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "explorer.exe" /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 0 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 0 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 0 /f >nul
reg unload "%HIVE%" >nul
echo.
echo Disabled for %STUDENT_USER%. They can now log in normally.
exit /b 0

:check_offline
if not exist "C:\Users\%STUDENT_USER%\NTUSER.DAT" (
    echo ERROR: C:\Users\%STUDENT_USER%\NTUSER.DAT not found.
    exit /b 1
)
reg load "%HIVE%" "C:\Users\%STUDENT_USER%\NTUSER.DAT" >nul
if errorlevel 1 (
    echo ERROR: could not load %STUDENT_USER%'s hive. Is the user logged off?
    exit /b 1
)
echo Shell for %STUDENT_USER%:
reg query "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell
reg query "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr
reg unload "%HIVE%" >nul
exit /b 0

:check_current
echo Shell for current user (%USERNAME%):
reg query "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr
exit /b 0
