@echo off
rem Start Claude Hub Lite with Windows.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run install.cmd first. & pause & exit /b 1)
".venv\Scripts\python.exe" -m claudetray.install on
"%SystemRoot%\System32\timeout.exe" /t 4 >nul
