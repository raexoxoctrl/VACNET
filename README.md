# VACNET

VACNET is a Windows-oriented Discord bot project that acts as a remote controller and self-updating manager for a local application.

The current implementation includes:
- Discord slash commands for status, execution, updates, and logs
- A persistent supervisor that launches and monitors the bot process
- Git-based self-updating behavior from a configured GitHub repository
- Strict admin restrictions by Discord user ID
- Logging and safe rollback handling for failed updates
- A modular structure so you can replace the temporary `/execute` command later with your real Immich or image-server startup logic

## Project structure

```text
VACNET/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── main.py
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
│   ├── start_bot.bat
│   └── start_supervisor.bat
├── tests/
│   └── test_config.py
└── .venv/
```

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

4. Start the persistent supervisor:

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

- `/status` — shows whether the bot/application is running and the current Git commit/version
- `/execute` — temporarily opens a Windows `cmd.exe` and prints `hello`
- `/update` — pulls the repository, installs dependencies, and restarts the bot safely
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

Logs are written to `logs/vacnet.log` and include command execution, updates, restarts, Git operations, and errors.

## Important security notes

- Keep `.env` outside of GitHub.
- Never check in Discord tokens or secret keys.
- The project includes `.env.example` as a template only.

## Future extension

The `/execute` command is intentionally minimal: it only opens a Windows console and prints `hello`. You can later replace that implementation with your real Immich or image-server startup logic without changing the rest of the architecture.
