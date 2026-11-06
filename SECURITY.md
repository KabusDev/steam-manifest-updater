# Security policy

This repository is a first draft, not production-hardened. Test on a non-critical Windows computer first.

- Only download SteamCMD from Valve's official source; no SteamCMD binaries are redistributed here.
- Do not commit your local `config.json`, logs, session files, or personal Steam credentials.
- The updater supports only `anonymous` SteamCMD authentication. Avoid scheduled tasks containing account passwords.
- Review downloaded scripts before executing them, and follow institutional security policy.
- The updater does not edit Steam manifests, bypass DRM, defeat licensing checks, or circumvent network policy.
- Please report security vulnerabilities privately to the repository maintainer using GitHub's private vulnerability reporting if enabled.

This initial release has no formal support window or signed release artifacts.
