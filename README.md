# Steam Manifest Auto-Updater

**Windows-first | Python 3.10+ | MIT-licensed | v0.1.0 (first draft)**

Discover what Steam has installed on a PC using its own `appmanifest_<appid>.acf` files, then run **explicitly configured SteamCMD maintenance jobs** on a daily schedule. Designed for lab PCs, gaming setups, and managed game/server installations.

> [!IMPORTANT]
> **This is not a universal Steam client game updater.** SteamCMD cannot reliably update arbitrary consumer Steam titles directly inside a Steam client library. For ordinary PC games, use **Steam > Settings > Downloads** and configure automatic updates in Steam. This project's SteamCMD jobs are **opt-in only** and **must use separate install directories**. The example is disabled until you configure it.

## What it does

- Finds Steam via the Windows registry, usual Steam folders, `STEAM_PATH`, or configurable `steam_roots`.
- Reads `libraryfolders.vdf` and `appmanifest_*.acf` to discover installs across multiple drives.
- Shows AppID, game name, installation location, and missing-folder warnings.
- Runs only the SteamCMD jobs you explicitly allow and only when the detection AppID is installed.
- Never writes to a Steam client library or attempts direct manifest editing.
- Supports non-destructive `--dry-run`, daily Task Scheduler setup, logs, JSON reports, and a no-overlap lock.
- Needs no third-party Python packages. SteamCMD is downloaded separately from Valve if requested.

## Start here (Windows)

**Requirements:** Windows 10/11, Python 3.10+ from [python.org](https://www.python.org/downloads/windows/), and a Steam installation to scan. SteamCMD is needed only if you enable a SteamCMD job.

1. Download or clone this repository and unzip it somewhere permanent, e.g. `C:\Tools\steam-manifest-updater`. For the simplest setup, **double-click `SETUP.bat`** and follow its messages; steps 2–3 below are the equivalent terminal method.
2. In that folder, right-click an empty area, open **Terminal** or **PowerShell**.
3. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Time 03:00
   ```

   This creates your local `config.json`, detects games, and registers a daily **03:00** scheduled task for your Windows account. The task runs only **while you are logged in**. It does not elevate privileges or store a password.

4. Inspect discovered games:

   ```powershell
   py -3 -m steam_manifest_updater discover
   ```

5. **If you have an actual SteamCMD-compatible application to update**, edit `config.json` and enable a matching job (see below). Download Valve's SteamCMD using:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\install-steamcmd.ps1
   ```

6. Test your plan before any update:

   ```powershell
   py -3 -m steam_manifest_updater run --dry-run
   ```

7. Run once manually:

   ```powershell
   py -3 -m steam_manifest_updater run
   ```

**Nothing is downloaded or updated by default.** The task can run, scan and log daily, but the sample update job is disabled until you deliberately enable it.

### An example configuration

The shipped `config.example.json` includes an *illustrative, disabled* mapping: detect the Counter-Strike client AppID `730` and use SteamCMD AppID `740` for an **isolated dedicated-server directory**. These AppIDs identify different applications. This is not a method of updating the client game itself.

```json
{
  "steam_roots": [],
  "steamcmd_path": "tools/steamcmd/steamcmd.exe",
  "log_dir": "logs",
  "timeout_minutes": 180,
  "jobs": [
    {
      "enabled": false,
      "detect_appid": "730",
      "steamcmd_appid": "740",
      "install_dir": "C:\\GameServers\\csgo-legacy",
      "login": "anonymous",
      "validate": false
    }
  ]
}
```

Change `enabled` to `true` only after verifying that the requested SteamCMD AppID is available and that the isolated target folder is correct. The program does **not** automatically turn normal games into dedicated servers.

For additional drives, use `steam_roots` only when autodetection is incomplete, e.g. `["D:\\SteamLibrary"]` if that directory contains `steamapps/`; normally the Steam `libraryfolders.vdf` index handles additional drives automatically.

## Daily scheduling

The setup script registers a Windows Scheduled Task called **Steam Manifest Auto-Updater** (default 03:00 local time). It runs `python -m steam_manifest_updater run` as the current user.

```powershell
# Choose a different time:
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Time 02:30

# Configure only, with no scheduled task:
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -NoSchedule

# Configure and download Valve's SteamCMD too:
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -InstallSteamCMD

# Remove the daily task (without deleting your config/logs):
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-task.ps1
```

The account **must remain signed in** for this interactive-user schedule. If the PC is asleep, execution depends on Windows power and Task Scheduler settings. This initial release does not install a background service, create service accounts or store Steam credentials. If you need updates while users are logged out, use a managed Windows task/service account with IT approval, or run SteamCMD jobs on a designated server. For client games, configure Steam's own auto-update window instead.

## Logs & troubleshooting

Each `run` creates timestamped files in `logs/`: a human-readable `.log` and a structured `.json`. `config.json`, `logs/`, and the downloaded SteamCMD folder are Git-ignored. No passwords are stored or passed to SteamCMD.

```powershell
py -3 -m steam_manifest_updater doctor
py -3 -m unittest discover -s tests -v
```

See [Configuration](docs/CONFIGURATION.md) and [Troubleshooting](docs/TROUBLESHOOTING.md).

## Limitations / roadmap

- Does not forcibly update consumer games in the Steam client.
- Does not check Valve's servers to determine whether a client game has an update pending; a local manifest is not proof of an update.
- SteamCMD is limited by the app's delivery model and access rights. Only anonymous login is supported in v0.1.
- No production Windows runtime test has been performed yet; automated parser and runner tests use a mocked SteamCMD process.
- Future candidates: optional read-only reporting dashboard, notifications, signed Windows release package, supported Windows Server deployment mode, and advanced dedicated-server mappings.

## Contributing / licence

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) , [SECURITY.md](SECURITY.md), and [Publishing](docs/PUBLISHING.md). Licensed under [MIT](LICENSE).

### References

- [Valve SteamCMD documentation](https://developer.valvesoftware.com/wiki/SteamCMD)
- [Steam Support: Managing Steam Downloads & Updates](https://help.steampowered.com/en/faqs/view/71AB-698D-57EB-178C)
- [Steam Support: Installed games appearing as uninstalled](https://help.steampowered.com/en/faqs/view/4578-18A7-C819-8620)
