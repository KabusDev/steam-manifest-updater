@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo ======================================================
echo  STEAM MANIFEST AUTO-UPDATER - LIVE UPDATE TEST
echo ======================================================
echo.
echo WARNING: This is NOT a dry run.
echo Eligible games may be downloaded or modified via SteamCMD.
echo Anonymous licence checks run before any updates.
echo Close Steam and all running games before continuing.
echo SteamCMD updates to Steam client game folders can interfere
echo with the Steam client's installation tracking.
echo.
if not exist "config.json" (
    echo ERROR: config.json was not found.
    echo Run SETUP.bat first and review config.json.
    echo.
    pause
    exit /b 2
)
set "confirm="
set /p "confirm=Type UPDATE to start the live update test: "
if /I not "%confirm%"=="UPDATE" (
    echo Cancelled. Nothing was updated.
    pause
    exit /b 0
)
echo.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m steam_manifest_updater run
) else (
    python -m steam_manifest_updater run
)
set "result=%errorlevel%"
echo.
if "%result%"=="0" (
    echo Run completed. See logs for licence decisions and update results.
) else (
    echo Run exited with code %result%. See logs for details.
)
echo.
pause
exit /b %result%
