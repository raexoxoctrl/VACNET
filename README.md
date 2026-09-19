# VACNET

VACNET is a Windows-oriented Discord bot project that acts as a remote controller and self-updating manager for a local application.

The current implementation includes:
- Discord slash commands for status, execution, updates, and logs
- A persistent supervisor that launches and monitors the bot process
- Git-based self-updating behavior from a configured GitHub repository
- Strict admin restrictions by Discord user ID
- File, console, channel, and webhook logging with safe rollback handling for failed updates
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
│   └── run_script.bat
├── exes/
│   └── script.py
├── tests/
│   └── test_config.py
└── .venv/
```

## Batch scripts

- `install.bat` — clones or updates the GitHub checkout, creates `.venv`, preserves an existing `.env`, installs dependencies, and registers `VACNET Bot` in Task Scheduler to run at Windows startup. Run it as Administrator. You can optionally pass a repository URL as its first argument.
- `uninstall.bat` — requests administrator access, asks for confirmation, stops and removes the `VACNET Bot` scheduled task, terminates VACNET processes, and retries removal of the complete installation directory, including `.env`, `.venv`, logs, and the Git checkout.
- `scripts\run_bot.bat` — starts the supervisor through the virtual environment. It is called by the scheduled task and uses the hidden `pythonw.exe` when available.
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
- `DISCORD_WEBHOOK_URL` — optional Discord webhook for all bot and supervisor logs

4. Or use the root installer, which performs the environment and dependency setup:

```bat
install.bat
```

5. Start the persistent supervisor:

```powershell
python main.py
```

The supervisor will launch the Discord bot and keep it running.

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

Logs are written to `logs/vacnet.log` and include command execution, updates, restarts, Git operations, and errors. When `DISCORD_WEBHOOK_URL` is set, the same entries are also sent to the webhook as severity-colored embeds with the logger name and timestamp. Existing channel logging remains available through `BOT_LOG_CHANNEL_ID` and `SCRIPT_LOG_CHANNEL_ID`, using the same embed format.

Script updates are restricted to administrator IDs and HTTPS URLs. The downloaded file must compile as Python before it replaces the current script. The repository update is intentionally destructive: it resets tracked files to the configured remote branch and removes non-ignored untracked files before reinstalling dependencies. Ignored runtime files such as `.env`, `.venv`, and logs are preserved.

## Important security notes

- Keep `.env` outside of GitHub.
- Never check in Discord tokens or secret keys.
- The project includes `.env.example` as a template only.

## Future extension

The `/execute` command is intentionally minimal: it invokes `exes\script.py` in a visible `cmd.exe` window, which currently prints `hello`. Replace that Python script later with your real Immich or image-server startup logic without changing the Discord command architecture.
