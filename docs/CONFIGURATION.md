# Configuration

`config.example.json` is copied to local `config.json` on `init` or setup. **Edit only `config.json`**; it is excluded from Git. Existing configurations are not overwritten.

| Key | Default | Meaning |
| --- | --- | --- |
| `steam_roots` | `[]` | Extra root folders containing `steamapps`; libraryfolders.vdf handles extra drives automatically |
| `steamcmd_path` | `tools/steamcmd/steamcmd.exe` | SteamCMD executable |
| `log_dir` | `logs` | Log files and JSON inventory/licence reports |
| `timeout_minutes` | `180` | Limit for each SteamCMD *download* (1–1440) |
| `licence_timeout_seconds` | `90` | Limit for one complete anonymous entitlement snapshot (10–600) |
| `auto_update.enabled` | **`true` in new template** | Scan local manifests and plan their AppIDs automatically |
| `auto_update.validate` | `false` | Run SteamCMD `validate` on auto jobs (more IO) |
| `auto_update.skip_if_steam_running` | `true` | Refuse in-place SteamCMD updates while Steam is open, or its state cannot be checked |
| `auto_update.exclude_appids` | `[]` | AppIDs to skip in automatic mode; **strings**, e.g. `["730"]` |
| `jobs` | `[]` | Optional manual jobs and per-AppID overrides |
| `licence_cache.denied_days` | `7` | Cache anonymous denials; 0 disables denial caching |
| `licence_cache.granted_hours` | `0` | Grant-cache lifespan; default rechecks grants each run |
| `licence_cache.cooldown_minutes` | `60` | Cooldown after a detected SteamCMD rate limit |
| `licence_fallback.enabled` | `true` | Enable bounded individual AppID checks when a bulk listing is incomplete |
| `licence_fallback.max_checks_per_run` | `8` | Maximum individual SteamCMD queries per run; 0 disables |
| `licence_fallback.retry_unknown_hours` | `48` | Minimum time before re-querying an inconclusive individual AppID |


**Backward compatibility:** If an existing `config.json` has no `auto_update.enabled`, auto mode stays **disabled**. This prevents old installs from silently beginning in-place downloads after a software upgrade. Add `"auto_update": {"enabled": true}` explicitly to opt in. All other missing auto settings use safe defaults.

## Precedence rules

1. A configured `jobs` entry with a matching `detect_appid` overrides automatic handling of that AppID, even when `enabled` is `false`.
2. If the manual entry is enabled, it runs using its configured **SteamCMD AppID** and **isolated target** (only when `require_manifest` is satisfied).
3. If no manual override exists and auto mode is enabled, an installed, valid manifest adds an automatic job unless its AppID is in `exclude_appids`.
4. **All enabled jobs require an active anonymous licence check**, with no bypass. No positive licence result means **no download attempt**.
5. Automatic *in-place* updates additionally require Steam to be closed. A failed process check also causes a skip.

A detected manifest whose target folder is missing is inventoried but not auto-updated. Duplicate AppIDs installed in multiple Steam libraries produce separate automatic jobs, but their licence is checked only once per execution. **Different AppIDs sharing the same install folder are skipped in automatic mode** to prevent conflicting in-place writes. Manual isolated jobs remain permitted.

## Manual job fields

| Field | Required? | Explanation |
| --- | --- | --- |
| `enabled` | Optional | Default `false`. When false, acts as an automatic-mode exclusion for its `detect_appid`. |
| `detect_appid` | Yes | AppID whose automatic handling is overridden; a condition if `require_manifest` is true |
| `steamcmd_appid` | Required when enabled | The actual app SteamCMD checks and updates; may differ from `detect_appid` |
| `install_dir` | Required when enabled | Absolute destination, outside Steam libraries and outside SteamCMD installation |
| `require_manifest` | Optional | Default `true`; set `false` for a maintenance-only server with no client manifest |
| `validate` | Optional | Default `false`; integrity validation increases disk activity |
| `login` | Optional | Only `anonymous` accepted; credentials are never accepted |
| `name` | Optional | Friendly name included in logs |

**Examples** (fragments; insert them inside the JSON object):

```json
"auto_update": {
  "enabled": true,
  "skip_if_steam_running": true,
  "exclude_appids": ["730", "570"]
},
"jobs": [
  {
    "enabled": true,
    "detect_appid": "896660",
    "steamcmd_appid": "896660",
    "install_dir": "D:\\DedicatedServers\\Example",
    "require_manifest": false
  },
  {"enabled": false, "detect_appid": "252490"}
]
```

This is **an example of configuration mechanics**, not a promise that any given AppID is currently downloadable anonymously.

For **manual-only deployment**, set `auto_update.enabled` to `false`. For **manifest-only deployment**, leave `jobs` empty.

## Safety, one-session preflight and cache

`SETUP.bat` runs a read-only anonymous preflight by default after SteamCMD is downloaded. It uses **one SteamCMD login** with `+licenses_print`, then checks the active package's explicit AppID listings against each detected manifest. Previously, each AppID required a separate SteamCMD login.

The result goes to `logs/licence-cache.json`. Denied AppIDs are cached for seven days by default and silently skipped on subsequent days (with the cache decision shown in logs). Granted entries are **rechecked by default**; expired and new AppIDs are inspected together in a single login.

To recheck all detected games manually, without any downloads:

```powershell
py -3 -m steam_manifest_updater licences --refresh
```

To disable the automatic setup scan, launch `scripts/setup.ps1 -SkipLicenceScan`. This does not disable checks before actual updates.

`unknown` and `rate_limited` decisions are never stored as seven-day denials. A rate limit instead starts a configured cooldown. A cached denial never bypasses manual overrides: an override for a **different SteamCMD AppID** gets its own entitlement decision. `--refresh-licences` forces a refresh during a normal run.

This check is read-only. It does not request free licences or attempt downloads to test ownership. An active package with a matching AppID is still **not proof that the target depots are downloadable**. SteamCMD's human-readable console format is not a supported stable API, so malformed, empty, truncated or unrecognised output fails closed as `unknown`.

**Caution:** Auto mode writes directly to the installation folder discovered in the manifest. SteamCMD can leave Steam's desktop-client tracking inconsistent. Test on a non-critical machine before use.

## Fallback rotation and status semantics

When a complete AppID listing cannot be extracted from Valve's anonymous SteamCMD output, the script keeps explicitly listed grants, then issues up to eight individual `licenses_for_app` read-only queries per run. It records probe timestamps in the cache so later runs progress to untested AppIDs instead of repeatedly checking the same few. Confirmed denials are cached for seven days; inconclusive checks retain their status as `unknown`. A rate-limit error halts further probes and starts cooldown.

The `--refresh` and `--refresh-licences` flags bypass retry ages and cached denials, **not** the per-run probe cap. Existing `config.json` files inherit the fallback defaults unless specified explicitly. `updated`, `already_up_to_date`, `skipped`, and `failed` are separate update result statuses. `already_up_to_date` counts as success but not a new update.

## Exit codes / reports

- `run`: `0` if no update *attempt* failed (including all skipped), `1` for attempted update failures, `2` for setup/config errors.
- `doctor`: returns `1` for missing Steam libraries or missing SteamCMD with planned jobs.
- Reports: `logs/YYYYMMDD-HHMMSS-ffffff.json`, including per-game `inventory`, `licence_checks`, `results` and skipped reasons; `.log` alongside for human review.
- `run --dry-run`: performs read-only anonymous entitlement probes (when SteamCMD exists), **never** runs `app_update`.
