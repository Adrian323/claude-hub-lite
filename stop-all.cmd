@echo off
rem Closes everything Claude Hub Lite runs: the tray, the usage panel and AgTop.
rem Needs nothing from this folder, so it also works on an older or broken install.
title Claude Hub Lite: stop all
powershell -NoProfile -NonInteractive -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match '-m claudetray|agtop' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Claude Hub Lite is stopped: tray, usage panel and AgTop are closed.
echo.
echo Press any key to close this window.
pause >nul
