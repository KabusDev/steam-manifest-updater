@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -m steam_manifest_updater run --dry-run
) else (
    python -m steam_manifest_updater run --dry-run
)
pause
