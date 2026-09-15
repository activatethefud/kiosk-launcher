@echo off
rem ===========================================================================
rem  kiosk-shell.bat — enable/disable the real kiosk shell (Plan B)
rem
rem  ENABLE  (run while logged in AS THE STUDENT user):
rem    kiosk-shell.bat enable
rem    -> sets the student's shell to C:\Kiosk\Kiosk.exe and disables
rem       Task Manager / Lock / Change Password for that user.
rem
rem  DISABLE (run AS ADMINISTRATOR; the student must be logged off):
rem    kiosk-shell.bat disable [StudentUsername]
rem    -> restores explorer.exe and re-enables the CAD options.
rem
rem  The default student username is "Student".
rem ===========================================================================
setlocal EnableExtensions

set "KIOSK_EXE=C:\Kiosk\Kiosk.exe"

if /i "%~1"=="enable"  goto :enable
if /i "%~1"=="disable" goto :disable

echo Usage:
echo   kiosk-shell.bat enable              (run as the student user)
echo   kiosk-shell.bat disable [Username]  (run as administrator)
exit /b 1

:enable
rem Fail fast rather than lock the account to a missing shell.
if not exist "%KIOSK_EXE%" (
    echo ERROR: %KIOSK_EXE% not found. Build and copy it there first.
    exit /b 1
)

reg add "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "%KIOSK_EXE%" /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 1 /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 1 /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 1 /f

echo.
echo Kiosk shell enabled for this user. Log off and back on to enter kiosk mode.
exit /b 0

:disable
set "STUDENT_USER=%~2"
if "%STUDENT_USER%"=="" set "STUDENT_USER=Student"
set "HIVE=HKU\KioskStudent"

if not exist "C:\Users\%STUDENT_USER%\NTUSER.DAT" (
    echo ERROR: Could not find C:\Users\%STUDENT_USER%\NTUSER.DAT
    exit /b 1
)

reg load "%HIVE%" "C:\Users\%STUDENT_USER%\NTUSER.DAT" >nul
if errorlevel 1 (
    echo ERROR: Could not load the registry hive. Is %STUDENT_USER% logged off?
    exit /b 1
)

reg add "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "explorer.exe" /f
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 0 /f
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 0 /f
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 0 /f

reg unload "%HIVE%" >nul

echo.
echo Kiosk shell disabled for %STUDENT_USER%. They can now log in normally.
exit /b 0
