@echo off
rem ===========================================================================
rem  install.bat — one-shot client installer for Kiosk Launcher (Plan B shell)
rem
rem  Run this from the unzipped folder. It self-elevates, copies everything to
rem  C:\Kiosk, and enables the kiosk shell for the student user.
rem
rem  Usage:
rem    install.bat [StudentUsername]     (default: Student)
rem
rem  The student user must be LOGGED OFF (their registry hive is written
rem  directly). To recover afterwards:  C:\Kiosk\kiosk-shell.bat disable
rem ===========================================================================
setlocal EnableExtensions

set "KIOSK_DIR=C:\Kiosk"
set "STUDENT_USER=%~1"
if "%STUDENT_USER%"=="" set "STUDENT_USER=Student"

rem --- self-elevate (needs admin to write the registry) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

rem --- copy all files to %KIOSK_DIR% unless we are already running there ---
if /i "%~dp0"=="%KIOSK_DIR%\" goto :already_there
echo Copying files to %KIOSK_DIR% ...
if not exist "%KIOSK_DIR%" mkdir "%KIOSK_DIR%"
xcopy "%~dp0*" "%KIOSK_DIR%\" /E /I /Y >nul
:already_there

if not exist "%KIOSK_DIR%\Kiosk.exe" (
    echo ERROR: %KIOSK_DIR%\Kiosk.exe not found. Copy the build there first.
    exit /b 1
)
if not exist "%KIOSK_DIR%\kiosk-shell.bat" (
    echo ERROR: %KIOSK_DIR%\kiosk-shell.bat not found.
    exit /b 1
)

echo.
echo Enabling kiosk shell for %STUDENT_USER% ...
call "%KIOSK_DIR%\kiosk-shell.bat" enable %STUDENT_USER%

echo.
echo Installation complete.
echo   - %STUDENT_USER% must log off and back on to enter kiosk mode.
echo   - Start the admin password change from the kiosk: Admin -^> Change password.
echo   - To recover:  %KIOSK_DIR%\kiosk-shell.bat disable %STUDENT_USER%
exit /b 0
