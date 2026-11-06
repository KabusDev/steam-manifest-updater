# Contributing

All contributions are welcome, especially realistic Windows 10/11 behaviour reports, better Valve KeyValues parsing, and test fixtures using **synthetic** app manifests.

1. Fork the repository and create a feature branch.
2. Keep runtime dependencies optional. Prefer the Python standard library.
3. Run `python -m unittest discover -s tests -v` before opening a PR.
4. Add tests for manifest parsing and any changes to SteamCMD process generation.
5. Preserve the safety invariant: never write into a discovered Steam client library through SteamCMD.
6. Do not post Steam credentials, user tokens, real school computer/user names, or unredacted logs.

Changes that promise SteamCMD updates for all Steam client games must include reproducible evidence and a safe implementation, not just an assumption from matching AppIDs.
