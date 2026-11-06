@echo off
cd /d "%~dp0"
echo Steam Manifest Auto-Updater: first-time setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -Time 03:00
if errorlevel 1 (
    echo.
    echo Setup did not finish. See the message above and README.md.
) else (
    echo.
    echo Setup complete. Review config.json and run a dry-run before the scheduled update.
)
pause
