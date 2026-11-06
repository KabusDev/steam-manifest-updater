# Troubleshooting

### Nothing happens when the task runs

Run `py -3 -m steam_manifest_updater discover` in the repository directory. If games appear, run `... doctor`. By design, there are **zero updates unless an enabled allowlist job matches an installed game**. Look in `logs/` for timestamped run summaries.

### No Steam libraries found

Set `steam_roots` in `config.json` to the parent folder of `steamapps`, such as `"D:\\SteamLibrary"`, then run `discover` again. Do not put `steamapps` itself in that list.

### SteamCMD missing

Run `powershell -ExecutionPolicy Bypass -File .\scripts\install-steamcmd.ps1` from the repo root, or install Valve's SteamCMD yourself and set `steamcmd_path` in `config.json`.

### SteamCMD reports “No subscription” / access denied

Not all AppIDs can be downloaded with anonymous authentication. This initial version **does not support Steam account logins**, especially passwords in scheduled tasks. Check that the selected application supports SteamCMD anonymous access. A regular consumer game can still appear in the manifest inventory but cannot automatically become an allowed SteamCMD download.

### SteamCMD exits successfully but the report says FAILED

SteamCMD occasionally exits with code zero even when an update has not clearly completed. This tool requires a recognizable `Success! App ...` message in its output. Inspect the `.log` file; file an issue with sanitized output if your SteamCMD version uses a different success format.

### “Target overlaps Steam library”

This check is intentional. SteamCMD jobs must use a **separate** install directory outside Steam client-managed libraries to avoid disrupting Steam's own manifests and download state. Do not disable this safety check to make a regular Steam game update work.

### Task does not run overnight

The guided setup creates a current-user **interactive** task. You must remain logged in, and Windows power settings may prevent an asleep machine from starting a job. Confirm it in **Task Scheduler > Task Scheduler Library > Steam Manifest Auto-Updater**, check Last Run Result, and test while signed in. For unattended signed-out operation, institutional configuration and a properly managed service account are outside v0.1's scope.

### Error about execution policy

The README commands pass `-ExecutionPolicy Bypass` for this one script execution. If your organisation enforces PowerShell policy through Group Policy, consult your IT team instead of bypassing central controls.

### Where are credentials stored?

They aren't. SteamCMD uses `+login anonymous`. The program never changes Steam configuration, Steam manifests, or registry keys.
