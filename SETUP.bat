@echo off
cd /d "%~dp0"
echo Steam Manifest Auto-Updater: first-time setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -Time 03:00
if errorlevel 1 (
    echo.
    echo Setup did not finish. See the message above and README.md.
) else (
    echo.
    echo Setup complete. Edit config.json before enabling a SteamCMD job.
)
pause
