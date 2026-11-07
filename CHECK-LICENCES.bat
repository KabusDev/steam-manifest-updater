@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo ==========================================
echo  CHECK ANONYMOUS STEAMCMD LICENCES
echo ==========================================
echo.
echo This reads installed manifests and checks anonymous licences.
echo It does NOT download or update any games.
echo Previously denied AppIDs are normally read from the 7-day cache.
echo To force a full recheck, run CHECK-LICENCES.bat refresh
echo.
if not exist "config.json" (
  echo ERROR: config.json not found. Run SETUP.bat first.
  pause
  exit /b 2
)
set "flags="
if /I "%~1"=="refresh" set "flags=--refresh"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m steam_manifest_updater licences %flags%
) else (
  python -m steam_manifest_updater licences %flags%
)
set "result=%errorlevel%"
echo.
echo Licence-check complete. See the logs folder for full results.
echo.
pause
exit /b %result%
