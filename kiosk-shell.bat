@echo off
rem ===========================================================================
rem  kiosk-shell.bat — enable/disable/check the real kiosk shell (Plan B)
rem
rem  ENABLE:
rem    kiosk-shell.bat enable             configure the CURRENT user
rem                                       (run while logged in AS the student)
rem    kiosk-shell.bat enable Username    run as ADMIN; write to that user's
rem                                       offline hive (student may be logged off)
rem
rem  DISABLE:
rem    kiosk-shell.bat disable [Username] run as ADMIN; restore explorer.exe
rem                                       (student must be logged off)
rem
rem  CHECK:
rem    kiosk-shell.bat check  [Username]  print the current shell setting
rem
rem  Default student username is "Student".
rem ===========================================================================
setlocal EnableExtensions

set "KIOSK_EXE=C:\Kiosk\Kiosk.exe"

if /i "%~1"=="enable"  goto :enable
if /i "%~1"=="disable" goto :disable
if /i "%~1"=="check"   goto :check

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
set "TARGET_USER=%~2"
if not "%TARGET_USER%"=="" goto :enable_offline

echo Configuring kiosk shell for current user: %USERNAME% [%USERPROFILE%]
reg add "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "%KIOSK_EXE%" /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 1 /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 1 /f >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 1 /f >nul

echo.
echo Verifying - the Shell value should read:
reg query "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell
echo.
echo Log off and back on to enter kiosk mode.
exit /b 0

:enable_offline
set "HIVE=HKU\KioskStudent"
if not exist "C:\Users\%TARGET_USER%\NTUSER.DAT" (
    echo ERROR: C:\Users\%TARGET_USER%\NTUSER.DAT not found.
    exit /b 1
)
reg load "%HIVE%" "C:\Users\%TARGET_USER%\NTUSER.DAT" >nul
if errorlevel 1 (
    echo ERROR: could not load %TARGET_USER%'s hive. Is the user logged off?
    exit /b 1
)
echo Configuring kiosk shell for %TARGET_USER% (offline hive).
reg add "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "%KIOSK_EXE%" /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 1 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 1 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 1 /f >nul
reg unload "%HIVE%" >nul
echo.
echo Enabled for %TARGET_USER%. They must log off and back on.
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
reg add "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "explorer.exe" /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr /t REG_DWORD /d 0 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableLockWorkstation /t REG_DWORD /d 0 /f >nul
reg add "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableChangePassword /t REG_DWORD /d 0 /f >nul
reg unload "%HIVE%" >nul
echo.
echo Kiosk shell disabled for %STUDENT_USER%. They can now log in normally.
exit /b 0

:check
set "TARGET_USER=%~2"
if "%TARGET_USER%"=="" goto :check_current

set "HIVE=HKU\KioskStudent"
if not exist "C:\Users\%TARGET_USER%\NTUSER.DAT" (
    echo ERROR: C:\Users\%TARGET_USER%\NTUSER.DAT not found.
    exit /b 1
)
reg load "%HIVE%" "C:\Users\%TARGET_USER%\NTUSER.DAT" >nul
if errorlevel 1 (
    echo ERROR: could not load %TARGET_USER%'s hive. Is the user logged off?
    exit /b 1
)
echo Shell for %TARGET_USER%:
reg query "%HIVE%\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell
reg query "%HIVE%\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr
reg unload "%HIVE%" >nul
exit /b 0

:check_current
echo Shell for current user (%USERNAME%):
reg query "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v DisableTaskMgr
exit /b 0
