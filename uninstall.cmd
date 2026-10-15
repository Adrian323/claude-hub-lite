@echo off
rem Removes Claude Hub Lite completely: stops the tray and usage panel, takes it out of Windows
rem startup, then deletes this folder. Python, Node.js, AgTop and cswap are left installed.
setlocal
cd /d "%~dp0"
set "DIR=%~dp0"
title Claude Hub Lite uninstaller
echo This removes Claude Hub Lite and deletes the folder
echo   %DIR%
echo.
echo Press any key to continue, or close this window to cancel.
pause >nul

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m claudetray.install off
  ".venv\Scripts\python.exe" -m claudetray.install stop
)
rem Leave the folder so nothing (not even this window) is working inside it, then delete it
rem from a separate window once this one has closed.
cd /d "%TEMP%"
echo.
echo Claude Hub Lite is removed. The folder is deleted when this window closes.
echo Press any key to close this window.
pause >nul
start "" /min cmd /d /c ""%SystemRoot%\System32\timeout.exe" /t 2 /nobreak >nul & rmdir /s /q "%DIR%""
exit
