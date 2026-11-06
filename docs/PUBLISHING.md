# Publishing this repository on GitHub

The project is committed locally as `James Mulvaney` using the email associated with `KabusDev`. There is no remote GitHub repository until you create one.

## Using the included `.git` history

1. Extract the **repository ZIP** (not the source-only ZIP). It includes the local `.git` directory and the initial commit.
2. On GitHub, visit [New repository](https://github.com/new), select the **KabusDev** account, and name it `steam-manifest-updater`.
3. Make it **Public**. Do **not** tick the options to add a README, `.gitignore` or licence, since those are already committed locally.
4. Open a terminal in the extracted project folder:

   ```powershell
   git remote add origin https://github.com/KabusDev/steam-manifest-updater.git
   git push -u origin main
   ```

GitHub will require normal authentication (for example through Git Credential Manager). The original authored commit is preserved. If you prefer SSH, replace the `origin` URL with `git@github.com:KabusDev/steam-manifest-updater.git`.

`config.json`, run logs and local SteamCMD downloads are intentionally excluded from version control. Keep them excluded on every contribution.
