@echo off
rem Claude Hub Lite installer: run it from wherever you cloned the repo. Safe to re-run (updates).
setlocal
cd /d "%~dp0"

set "PY=python"
py -3 --version >nul 2>&1 && set "PY=py -3"
%PY% --version >nul 2>&1 || (
  echo Python 3.10 or newer is required: https://www.python.org/downloads/
  goto :end
)

echo Installing Python packages...
if not exist ".venv\Scripts\pythonw.exe" %PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto :fail

where agtop >nul 2>&1 || (
  where npm >nul 2>&1 && (
    echo Installing AgTop...
    call npm i -g @ldegio/agtop
  ) || echo Node.js not found, so AgTop is skipped. Install https://nodejs.org and re-run to add it.
)

".venv\Scripts\python.exe" -m claudetray.install || goto :fail
start "" ".venv\Scripts\pythonw.exe" -m claudetray
echo.
echo Done. The Claude Hub Lite icon is in the notification area (check the ^ overflow).
goto :end

:fail
echo.
echo Install failed, see the error above.
:end
pause
