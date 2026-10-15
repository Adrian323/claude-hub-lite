@echo off
rem Claude Hub Lite: double-click to install, update or repair. Installs whatever is missing
rem (Python, Node.js, AgTop, cswap), adds the tray to Windows startup and starts it.
setlocal
cd /d "%~dp0"
title Claude Hub Lite installer
echo Claude Hub Lite installer
echo.

rem ---- Python 3.10+ (required) ----------------------------------------------
call :find_python
if defined PY goto :python_ok
echo Installing Python...
call :winget Python.Python.3.13 --scope user || goto :fail
call :find_python
if not defined PY (
  echo Python was installed but could not be found. Restart Windows and run this again.
  goto :fail
)
:python_ok
echo [ok] Python  %PY%

rem ---- tray packages --------------------------------------------------------
if not exist ".venv\Scripts\pythonw.exe" "%PY%" -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto :fail
echo [ok] Tray packages

rem ---- Node.js + AgTop (optional: only the AgTop menu item needs them) ------
set "PATH=%ProgramFiles%\nodejs;%APPDATA%\npm;%USERPROFILE%\.local\bin;%PATH%"
where node >nul 2>&1 && goto :node_ok
echo Installing Node.js (Windows may ask for permission)...
call :winget OpenJS.NodeJS.LTS
where node >nul 2>&1 || (echo [skip] Node.js not installed, AgTop will not work & goto :cswap)
:node_ok
echo [ok] Node.js
where agtop >nul 2>&1 || call npm i -g @ldegio/agtop >nul 2>&1
where agtop >nul 2>&1 && (echo [ok] AgTop) || echo [skip] AgTop could not be installed

rem ---- cswap (optional: lets the usage panel show and switch several accounts)
:cswap
where cswap >nul 2>&1 && goto :cswap_ok
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check uv >nul 2>&1
".venv\Scripts\uv.exe" tool install -q claude-swap >nul 2>&1
".venv\Scripts\uv.exe" tool update-shell >nul 2>&1
where cswap >nul 2>&1 || (echo [skip] cswap could not be installed & goto :startup)
:cswap_ok
echo [ok] cswap

rem ---- start with Windows, and start now ------------------------------------
:startup
".venv\Scripts\python.exe" -m claudetray.install on || goto :fail
".venv\Scripts\python.exe" -m claudetray.install restart || goto :fail
echo.
echo ============================================================
echo  Claude Hub Lite is installed and running.
echo  Find its icon in the system tray (bottom right of the
echo  taskbar; click the ^^ arrow if it is hidden). Right-click it.
echo ============================================================
echo.
echo Press any key to close this window.
pause >nul
exit /b 0

:fail
echo.
echo Install failed, see the message above.
pause
exit /b 1

rem ---- helpers ---------------------------------------------------------------
:find_python
set "PY="
for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2^>nul') do set "PY=%%i"
if defined PY exit /b 0
for /f "delims=" %%i in ('python -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2^>nul') do set "PY=%%i"
if defined PY exit /b 0
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "PY=%%d\python.exe"
exit /b 0

:winget
where winget >nul 2>&1 || (
  echo winget is missing. Install "App Installer" from the Microsoft Store, then run this again.
  exit /b 1
)
winget install -e --id %* --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
exit /b 0
