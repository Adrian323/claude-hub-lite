@echo off
rem Removes the Startup shortcut. Quit the tray from its menu, then delete this folder.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m claudetray.install --uninstall
pause
