# VACNET

VACNET is a Windows-oriented Discord bot project that acts as a remote controller and self-updating manager for a local application.

The current implementation includes:
- Discord slash commands for status, execution, updates, and logs
- A persistent supervisor that launches and monitors the bot process
- Git-based self-updating behavior from a configured GitHub repository
- Strict admin restrictions by Discord user ID
- File, console, and Discord channel logging with safe rollback handling for failed updates
- A modular structure so you can replace the temporary `/execute` command later with your real Immich or image-server startup logic

## Project structure

```text
VACNET/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── main.py
├── install.bat
├── uninstall.bat
├── app/
│   ├── __init__.py
│   ├── bot.py
│   ├── config.py
│   ├── git_manager.py
│   ├── launcher.py
│   ├── logger_setup.py
│   ├── supervisor.py
│   └── update_manager.py
├── logs/
│   └── .gitkeep
├── scripts/
│   ├── run_bot.bat
│   ├── run_script.bat
│   ├── run_dashboard.bat
│   └── install_cloudflared.bat
├── exes/
│   └── script.py
├── tests/
│   └── test_config.py
└── .venv/
```

## Batch scripts

- `install.bat` — clones or updates the GitHub checkout, creates `.venv`, preserves an existing `.env`, installs dependencies and `cloudflared`, generates a dashboard token when the template is still in use, and registers `VACNET Bot` in Task Scheduler to run at Windows startup. Run it as Administrator. You can optionally pass a repository URL as its first argument.
- `uninstall.bat` — requests administrator access, asks for confirmation, stops and removes the `VACNET Bot` scheduled task, terminates VACNET Python and tunnel processes, and retries removal of the complete installation directory, including `.env`, `.venv`, logs, and the Git checkout.
- `scripts\run_bot.bat` — starts the supervisor through the virtual environment. It is called by the scheduled task and uses the hidden `pythonw.exe` when available.
- `scripts\run_dashboard.bat` — starts the development dashboard at `http://127.0.0.1:8765`.
- `scripts\install_cloudflared.bat` — installs the Cloudflare Quick Tunnel client through `winget`.
- `exes\script.py` — the bot-invoked script entry point. It currently prints `hello` in a visible command window and is the file to replace later with the Immich/image-server command.

## Quick start on Windows

1. Open PowerShell in the project folder.
2. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your values:

```powershell
Copy-Item .env.example .env
```

Update the following keys in `.env`:
- `DISCORD_TOKEN`
- `ALLOWED_USER_IDS`
- `GIT_REPO_URL`
- `GIT_BRANCH`
- `LOG_LEVEL`
- `DASHBOARD_URL_CHANNEL_ID` — Discord channel where the bot announces temporary dashboard URLs
- `DASHBOARD_AUTH_TOKEN` — long random password required by the dashboard
- `DASHBOARD_SESSION_MINUTES` — dashboard session lifetime, from 5 to 1440 minutes
- `DASHBOARD_PORT` — local dashboard port, normally `8765`
- `CLOUDFLARED_PATH` — `cloudflared` if it is on PATH, or an absolute executable path

4. Or use the root installer, which performs the environment and dependency setup:

```bat
install.bat
```

5. Start the persistent supervisor:

```powershell
python main.py
```

The supervisor will launch the Discord bot and keep it running.

## Local development dashboard

Run `scripts\run_dashboard.bat` from the project folder for a localhost-only control panel. It provides live process status, recent logs, and Start, Stop, Restart, Execute, and Update controls. The dashboard is intended for development only, binds to `127.0.0.1`, and should be run instead of `main.py` when using its process controls.

The supervisor also starts the dashboard automatically. If `cloudflared` is installed, it creates a temporary HTTPS Quick Tunnel and writes the generated URL to local tunnel state. The Discord bot reads that state and announces the URL as an embed in `DASHBOARD_URL_CHANNEL_ID` (falling back to `BOT_LOG_CHANNEL_ID`). The URL changes when the tunnel restarts. No router port is opened. The dashboard requires `DASHBOARD_AUTH_TOKEN` and uses expiring HttpOnly sessions plus CSRF-protected controls.

For Discord, create a private `#vacnet-dashboard` channel and set its ID as `DASHBOARD_URL_CHANNEL_ID`. Grant the bot View Channel, Send Messages, Embed Links, Attach Files, and Read Message History, and do not grant Administrator. The bot sends the temporary URL directly; no webhook is used.

## GitHub repository setup

This project is designed to be stored in a GitHub repo and updated from GitHub using the bot's `/update` command.

Example:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/yourusername/VACNET.git
git push -u origin main
```

Then keep `.env` local and do not commit it. The bot reads secrets from `.env` only.

## Bot commands

- `/status` — shows detailed bot uptime, process, Python, Git, script, and supervisor status
- `/execute` — temporarily opens a Windows `cmd.exe` and prints `hello`
- `/update` — overwrites the local checkout with the configured remote branch, removes non-ignored untracked files, installs dependencies, and restarts the bot
- `/restart` — restarts the bot through the supervisor
- `/shutdown` — stops VACNET without the supervisor immediately restarting it
- `/fetchscript` — sends the current `exes/script.py` to Discord
- `/updatescript <link>` — downloads an HTTPS Python script, syntax-checks it, and activates it atomically
- `/logs` — shows recent log content

Administrative commands are restricted to user IDs listed in `ALLOWED_USER_IDS`.

## Update behavior

The update process does the following:
1. Creates a temporary backup branch before the update.
2. Pulls the latest repository state from GitHub.
3. Installs or upgrades Python dependencies.
4. Restarts the bot process via the supervisor.
5. If anything fails, it attempts a rollback to the saved backup reference.

This gives you a practical rollback path without risking a broken update loop.

## Logging

Logs are separated into rotating streams under `logs/`:

- `all.log` — unified current log
- `bot.log` — Discord commands and bot lifecycle
- `supervisor.log` — managed process lifecycle
- `dashboard.log` — local dashboard requests and actions
- `script.log` — script execution and script updates
- `update.log` — Git and dependency update operations
- `error.log` — errors and critical failures only
- `vacnet.log` — compatibility aggregate for existing tooling

Streams rotate at midnight or 10 MB and retain five backups. The `/logs` command accepts a stream, minimum severity, and line count. The local dashboard has the same stream and severity filters.

Warnings, errors, and explicitly marked operational events are sent as severity-colored embeds through the bot's configured Discord channels with source, logger, PID, and timestamp. Routine internal INFO events remain in files and the dashboard. Channel logging remains available through `BOT_LOG_CHANNEL_ID`, `SCRIPT_LOG_CHANNEL_ID`, and the dashboard URL channel.

Script updates are restricted to administrator IDs and HTTPS URLs. The downloaded file must compile as Python before it replaces the current script. The repository update is intentionally destructive: it resets tracked files to the configured remote branch and removes non-ignored untracked files before reinstalling dependencies. Ignored runtime files such as `.env`, `.venv`, and logs are preserved.

## Important security notes

- Keep `.env` outside of GitHub.
- Never check in Discord tokens or secret keys.
- The project includes `.env.example` as a template only.

## Future extension

The `/execute` command is intentionally minimal: it invokes `exes\script.py` in a visible `cmd.exe` window, which currently prints `hello`. Replace that Python script later with your real Immich or image-server startup logic without changing the Discord command architecture.

MHMH