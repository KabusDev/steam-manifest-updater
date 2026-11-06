# Changelog

## 0.2.0 (preview)

- Automatic detection mode enabled in newly generated configurations. Installed manifests become candidate SteamCMD jobs without a per-game allowlist.
- Read-only anonymous licence checks via `licenses_for_app`, with granted/denied/unknown statuses and fail-closed download gating.
- Per-AppID manual job overrides, exclusions, manual-only mode, and `require_manifest: false` maintenance jobs.
- Explicit Steam-client-running guard for in-place automatic jobs.
- New JSON report inventory, entitlement results, and per-job skip reasons.
- Guided Windows setup installs SteamCMD by default; `-SkipSteamCMD` optional.
- Legacy configurations without `auto_update.enabled` remain opt-in rather than silently enabling downloads.

## 0.1.0

- Read-only discovery of Steam libraries and manifests, opt-in SteamCMD maintenance jobs, daily scheduling, logs and unit tests.
