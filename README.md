# Steam Manifest Auto-Updater

**Windows-first | Python 3.10+ | MIT licence | v0.3.0 (preview)**

Discovers locally installed Steam apps from `appmanifest_<AppID>.acf` files, checks **SteamCMD anonymous licences before attempting downloads**, and runs eligible updates on a daily schedule. Also supports **explicit config-only maintenance jobs** for dedicated servers and other special cases.

> [!WARNING]
> **SteamCMD is not a universal replacement for the Steam desktop client.** An installed manifest does not mean an anonymous account has an entitlement. `licenses_for_app` is a *read-only preflight*, not a guarantee that every depot can be downloaded. A valid licence can still fail at update time. Some Steam-client games are unsupported by SteamCMD. **In-place SteamCMD updates can leave the desktop Steam client's manifest/build tracking out of sync**, even when downloads succeed. Test on a non-critical PC before using in a lab; the Steam client remains the recommended way to maintain ordinary client games.

## Quick start (Windows 10/11)

1. Install [Python 3.10+](https://www.python.org/downloads/windows/) if necessary.
2. Download this repository as a ZIP, extract it to a permanent folder, and double-click **`SETUP.bat`**.
3. Setup creates `config.json` (without overwriting an existing one), downloads SteamCMD **directly from Valve** if it is not installed, scans Steam libraries, performs a **read-only, single-session anonymous licence inventory**, and registers the daily **03:00** current-user scheduled task.
4. Open a terminal in the extracted folder and run the dry run **before allowing the daily task to update anything**:

   ```powershell
   py -3 -m steam_manifest_updater discover
   py -3 -m steam_manifest_updater doctor
   py -3 -m steam_manifest_updater run --dry-run
   ```

5. To test an actual update, double-click **`TEST-UPDATE.bat`**. It requires you to type `UPDATE` before launching SteamCMD; unlike `TEST-DRY-RUN.bat`, it can change installed game files. Close Steam and running games first. Alternatively, run once manually:

   ```powershell
   py -3 -m steam_manifest_updater run
   ```

6. Inspect `logs/` and `config.json` to see the licence checks, skipped games, and results.

### SteamCMD distribution and installation

**SteamCMD is not redistributed in this project, source archives, or releases.** `SETUP.bat` runs `scripts/setup.ps1`, which invokes `scripts/install-steamcmd.ps1` to download Valve's official [Windows SteamCMD ZIP](https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip) over HTTPS, extract its bootstrap executable into the Git-ignored `tools/steamcmd/` folder, and clean up the temporary download. SteamCMD retrieves its own updates from Valve when launched. Set `-SkipSteamCMD` only if you already provide SteamCMD via a separately managed installation, and adjust `steamcmd_path` in `config.json` accordingly.

**Release maintainers:** do not bundle `tools/`, `steamcmd.exe`, SteamCMD archives, Steam content, or user configuration in published assets. The MIT licence applies to the project's own source code, not Valve's binaries.

The task **only runs while the Windows account is logged in**. If you need a different schedule, see [Scheduling](#scheduling). The updater never stores Steam usernames or passwords; SteamCMD always logs in anonymously.

## How the two modes work

| Mode | How AppIDs are selected | Update destination | Licence check |
| --- | --- | --- | --- |
| **Automatic** (new installs: enabled) | Reads *all* valid, installed manifests, except excluded/overridden AppIDs | Detected local Steam game folder | Mandatory anonymous `licenses_for_app` preflight |
| **Manual** (optional) | Explicit `jobs` entries in `config.json`, optionally without a local manifest | Separate absolute path *outside* all Steam client libraries | Same mandatory preflight |

**Automatic mode is on in the newly generated config.** It scans installed games and **attempts updates only after a positive anonymous-licence response**. Missing or unclear licence results are logged as `denied` or `unknown` and cause a skip. The updater does **not** equate a public Steam store page or `app_info_print` with download rights, and it does not try `app_update` to discover whether an unlicensed game is accessible.

**Manual jobs override automatic selection** for their `detect_appid`. A disabled manual entry also suppresses automatic updates of that AppID. This makes it possible to maintain a few specific apps or dedicated server installations without duplicate downloads.

If a previously created `config.json` does **not** contain an `auto_update` section, automatic updates remain **off** for backward compatibility. Add `"auto_update": { "enabled": true }` to opt in; `init` never overwrites your existing configuration.

### Example configuration

The supplied [`config.example.json`](config.example.json) has no required per-game list:

```json
{
  "steam_roots": [],
  "steamcmd_path": "tools/steamcmd/steamcmd.exe",
  "log_dir": "logs",
  "timeout_minutes": 180,
  "licence_timeout_seconds": 90,
  "auto_update": {
    "enabled": true,
    "validate": false,
    "skip_if_steam_running": true,
    "exclude_appids": []
  },
  "jobs": []
}
```

#### Update selected apps only

Set `"auto_update": {"enabled": false}` and add explicit jobs:

```json
"jobs": [
  {
    "enabled": true,
    "detect_appid": "730",
    "steamcmd_appid": "740",
    "name": "Counter-Strike dedicated server example",
    "install_dir": "C:\\GameServers\\csgo-legacy",
    "require_manifest": true,
    "validate": false
  }
]
```

This example **does not update Counter-Strike itself**: it updates a *different* SteamCMD AppID to an isolated server directory, provided that anonymous SteamCMD currently grants access. It is an illustration, not a verified recommendation for a current server build. To update a particular server even if the associated client manifest does not exist, set `"require_manifest": false`.

You can also keep `auto_update.enabled: true` while listing manual overrides. For example, `{"enabled": false, "detect_appid": "730"}` excludes 730 from auto mode, and `auto_update.exclude_appids` provides another exclusion mechanism.

See [Configuration](docs/CONFIGURATION.md) for precedence and examples.

## Fast anonymous licence preflight, caching and logs

**New in v0.3:** a single SteamCMD session runs `+login anonymous +licenses_print +quit`, parses the anonymous account's active packages and their explicit AppID lists, and compares those AppIDs to the installed manifests. This replaces the previous **one-SteamCMD-login-per-game** approach. The preflight does not download game content.

During setup this check runs automatically, before registering the daily task. To run it again without updating games:

```powershell
py -3 -m steam_manifest_updater licences
```

To ignore previously cached denials and force a full new entitlement check:

```powershell
py -3 -m steam_manifest_updater licences --refresh
```

To force a new check during a regular update, use `run --refresh-licences`. `TEST-DRY-RUN.bat` remains read-only.

Results are stored in `logs/licence-cache.json` and reflected in timestamped `.log` and `.json` reports. Denied AppIDs are cached for **seven days**, so a typical subsequent run only checks new or expired entries. Granted entries are **rechecked on every run by default**, because package visibility does not guarantee depot download access. Cache settings are adjustable via `licence_cache` in `config.json`.

| Result | Action |
| --- | --- |
| `granted` | Eligible to try SteamCMD update; depot access remains unverified |
| `denied` | Skip; cache for seven days by default |
| `unknown` | Skip; do **not** store a long-lived denial |
| `rate_limited` | Skip; persist a 60-minute cooldown and stop new entitlement requests |

The parser requires recognised active packages with explicit AppID lists. Missing lists, truncated package information, unexpected responses and failed logins are treated as **unknown**. As Valve's console output is not a documented stable API, production testing on Windows is essential.

> [!IMPORTANT]
> An anonymous SteamCMD package can grant access to **server depots** without granting the regular desktop game's content. A `granted` licence is only a preliminary eligibility check; updates may still fail. Local manifests do not prove ownership by the anonymous account.

> [!IMPORTANT]
> **Steam must be closed for automatic in-place jobs.** The updater skips these jobs if Steam is running or the process check fails. Manual jobs must target separate folders.

## Scheduling

Default: **03:00 local time, each day, while the Windows account is signed in**.

```powershell
# Install/update the schedule and SteamCMD (default):
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Time 03:00

# Different time:
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Time 02:30

# Prepare config, but do not create a scheduled task:
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -NoSchedule

# Keep an existing manual SteamCMD installation / skip Valve download:
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -SkipSteamCMD

# Skip the read-only setup licence preflight:\npowershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -SkipLicenceScan\n\n# Uninstall the scheduled task (leaves config and logs alone):
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-task.ps1
```

To inspect scheduled tasks use **Windows Task Scheduler > Task Scheduler Library > Steam Manifest Auto-Updater**. Scheduled runs require the machine to be awake or Task Scheduler power settings to allow a start. The current-user guided setup does not install a service or store credentials.

## Limitations

- Installed manifest ≠ anonymous entitlement ≠ SteamCMD-compatible download. None of these imply one another.
- SteamCMD licence output is not a documented, stable machine-readable API. If Valve changes it, this tool **fails closed** and logs `unknown` rather than guessing.
- Automatic mode updates in-place using SteamCMD, which may interfere with the Steam client's own update bookkeeping. Use Steam's built-in updater for ordinary consumer games when possible.
- This does not query a Steam account's personal purchases or attempt to work around paid-game licensing.
- No live SteamCMD/Windows integration run has been completed yet. Unit tests mock SteamCMD output; start with a dry run.
- GitHub Actions runs the Python test suite, **not** real Steam content downloads.

## Contributing and support

- [Configuration reference](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Contributing](CONTRIBUTING.md) and [Security](SECURITY.md)

Licence: [MIT](LICENSE). Community bug reports welcome; please remove local paths and any personal details from logs.

**References:** [Valve SteamCMD](https://developer.valvesoftware.com/wiki/SteamCMD), [Valve Steamworks licensing diagnostics](https://partner.steamgames.com/doc/store/testing), [Steam Support: Downloads and updates](https://help.steampowered.com/en/faqs/view/71AB-698D-57EB-178C).
