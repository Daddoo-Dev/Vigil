@echo off
REM Double-click friendly wrapper. PowerShell does the real work (modern Windows standard).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 pause
