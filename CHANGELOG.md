# Changelog

## 0.3.1 (preview)

- Added bounded round-robin single-AppID licence fallback when anonymous package listings are truncated.
- Persist per-AppID unknown-probe timestamps and respect rate-limit cooldowns.
- Skip automatic updates for shared installation folders belonging to different AppIDs.
- Report `already_up_to_date` separately from updates; add regression tests and configuration settings.

## 0.3.0 (preview)

- One-session anonymous entitlement snapshot using SteamCMD `licenses_print`, replacing per-AppID logins for CLI users.
- Read-only licence preflight runs during guided setup; skip with `-SkipLicenceScan`.
- Persistent seven-day denial cache, uncached grant checks, and explicit refresh commands.
- Cooldown on detected SteamCMD rate limiting; unrecognised or incomplete output safely skips updates.
- Condensed console logging with complete inventory and per-app decisions retained in JSON reports.
- Closed Windows log handles after each run; improved Windows CI coverage and licence-cache tests.
- Original Steam desktop client and depot-access compatibility warnings remain applicable.

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
