# Troubleshooting

### Manifest detected, but no update took place

Open the latest `logs/*.json`. Check `inventory`, then `licence_checks`, then `results`:

- `inventory` is `skipped`: check missing install folders, `auto_update.enabled`, `exclude_appids`, and manual overrides.
- `licence_checks` is `denied`: SteamCMD reported no matching active anonymous licence. The tool **will not try to download** this AppID.
- `licence_checks` is `unknown`: SteamCMD missing, login failed, timed out, or output is not recognised. The tool skips rather than guessing.
- `results` says Steam is open: fully exit Steam and close running games before in-place updates.
- `results` is `failed`: active licence did not translate into successful depot access, SteamCMD could not complete the update, or the completion message was not recognised.

### No Steam libraries found

Set `steam_roots` in `config.json` to the **parent of `steamapps`**, e.g. `"D:\\SteamLibrary"`. Use `py -3 -m steam_manifest_updater discover` to check.

### SteamCMD missing

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-steamcmd.ps1
```

`SETUP.bat` and `scripts/setup.ps1` install SteamCMD by default unless you use `-SkipSteamCMD`.

### SteamCMD anonymous licence is unknown / denied

The app manifest belongs to the **local Steam client**. It says nothing about the rights of SteamCMD's **anonymous** session. The tool uses `licenses_for_app` to check active packages and will not start downloads for unknown or missing access. SteamCMD may change its output format, so please report sanitised output if an AppID you know supports anonymous access is being skipped.

### The update still fails despite an active licence

Licence state is not proof that the requested depot or branch is anonymously downloadable. A `granted` preflight allows an attempt but does not guarantee success; check the SteamCMD log and the app publisher's server documentation.

### Game updated, but the Steam desktop client later wants to re-download

Automatic SteamCMD updates are **in-place**, so Steam desktop may disagree about its own `appmanifest` build state. This is a limitation of using SteamCMD for client games. For ordinary consumer installations, use Steam's built-in updater instead.

### Steam is running / task runs while students are playing

Auto mode will skip while `steam.exe` is running or the process check fails. Close Steam and games before maintenance. Manual jobs target separate directories and are not subject to the Steam process guard.

### Only update selected apps

Set `"auto_update": {"enabled": false}` and enable explicit `jobs` entries. For hybrid use, keep auto enabled and add per-AppID overrides. A disabled manual entry prevents that AppID from being processed by automatic mode.

### Task doesn't run overnight

The default task runs **only while your Windows account is logged in**. The PC must also be awake or configured to wake for scheduled tasks. Inspect **Task Scheduler > Task Scheduler Library > Steam Manifest Auto-Updater**. Setup does not store a Windows password or install a system service.

### Errors about execution policy

The README uses `-ExecutionPolicy Bypass` for the one script invocation. If organisational Group Policy blocks scripts, contact your IT administrator. Don't try to bypass centrally managed policy.

### Where are credentials stored?

Nowhere. The only Steam login supported is `+login anonymous`. The tool never asks for Steam usernames, passwords or tokens.
