# Configuration reference

The setup command copies `config.example.json` into `config.json` (never overwriting an existing file). **Edit `config.json`, not `config.example.json`.** The private local configuration is excluded from Git.

| Key | Purpose | Default |
| --- | --- | --- |
| `steam_roots` | Steam root directories containing `steamapps` if autodetection misses them | `[]` |
| `steamcmd_path` | Location of `steamcmd.exe`, absolute or relative to repository root | `tools/steamcmd/steamcmd.exe` |
| `log_dir` | Directory for run logs and JSON reports | `logs` |
| `timeout_minutes` | Maximum *per-job* SteamCMD execution time (1 to 1440) | `180` |
| `jobs` | Explicit allowlist of jobs to consider | Sample disabled job |

## Job fields

| Key | Purpose |
| --- | --- |
| `enabled` | Must be `true` before SteamCMD can run for this job |
| `detect_appid` | Local Steam `appmanifest_<appid>.acf` ID that must exist with its install folder |
| `steamcmd_appid` | The SteamCMD AppID to download/update, which can be different from the local detected game |
| `install_dir` | **Absolute**, isolated directory for SteamCMD app content, outside *all* detected Steam libraries |
| `login` | Only `anonymous` is accepted in v0.1; no passwords, tokens, or personal Steam accounts |
| `validate` | Optional, defaults to `false`; `true` performs slower integrity validation |

All fields use standard JSON (double quotes, backslashes doubled). Disabled jobs are ignored. Duplicate local AppIDs in separate libraries count as a single match for a job. A detected manifest without its corresponding `common/<installdir>` folder **does not trigger an update**.

### Why the two AppIDs?

The detected AppID is a *condition*. The SteamCMD AppID is the *actual application being maintained*. For example, a PC with the Counter-Strike client installed (`730`) could trigger a dedicated-server maintenance action for `740` if that separate server app supports SteamCMD. This mapping is an example only and should not be enabled on an ordinary client PC without a reason to maintain that server.

Use the *same* ID for both values if the discovered app itself is compatible with SteamCMD. No auto-updates happen for IDs not added to the allowlist.

## Safer rollout process

1. Run `discover` and confirm the program found the right games and libraries.
2. Select one verified SteamCMD-compatible AppID, preferably a disposable test server installation.
3. Choose an isolated `install_dir` you can safely recreate. **Never point to an ordinary Steam game install or Steam library root.**
4. Set that job to `true`; run `run --dry-run`.
5. Install SteamCMD, run `run` once while monitoring the log, and verify the application works.
6. Allow the daily scheduled task to take over only after the manual test succeeds.

`run` returns exit code `0` if all attempted updates have confirmed success, `1` if any update fails, and `2` for invalid configuration or other setup errors. With no eligible jobs, it exits `0` and reports the scan. The `doctor` command returns `1` if no Steam libraries are discovered or an eligible job needs SteamCMD installed.

## Steam client games on classroom PCs

For games students actually launch, Valve's supported mechanism is the Steam **client**, not this updater's SteamCMD backend. In Steam, configure Downloads > automatic update hours and per-game updates. Keep Steam signed in on the maintenance machines as permitted by institutional policy, consider Steam PC Café / content caching in large labs, and coordinate network access with IT.

The manifest scanner can still be used as an inventory report without permitting any SteamCMD job.
