@echo off
rem Stop Claude Hub Lite from starting with Windows. The tray keeps running until you quit it.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run install.cmd first. & pause & exit /b 1)
".venv\Scripts\python.exe" -m claudetray.install off
"%SystemRoot%\System32\timeout.exe" /t 4 >nul
