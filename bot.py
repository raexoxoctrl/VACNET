from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands

from app.config import Settings
from app.git_manager import GitManager
from app.logger_setup import setup_logger
from app.update_manager import UpdateManager

ROOT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = ROOT_DIR / "exes" / "script.py"
SHUTDOWN_MARKER = ROOT_DIR / ".vacnet_shutdown"


class VacnetBot(discord.Client):
    def __init__(self, *, intents: discord.Intents, settings: Settings):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.settings = settings
        self.logger = setup_logger(
            "vacnet.bot",
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            client=self,
            discord_channel_id=settings.bot_log_channel_id,
            discord_webhook_url=settings.discord_webhook_url,
        )
        self.script_logger = setup_logger(
            "vacnet.script",
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            client=self,
            discord_channel_id=settings.script_log_channel_id,
            discord_webhook_url=settings.discord_webhook_url,
        )
        self.git = GitManager(ROOT_DIR, self.logger)
        self.update_manager = UpdateManager(ROOT_DIR, self.logger, settings)
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        await self.tree.sync()

    def is_admin(self, user_id: int | str) -> bool:
        user_id_str = str(user_id)
        return user_id_str in self.settings.allowed_user_ids


intents = discord.Intents.default()
intents.message_content = True

settings = Settings.from_env()
client = VacnetBot(intents=intents, settings=settings)


@client.event
async def on_ready() -> None:
    client.logger.info("Bot connected as %s", client.user)
    client.logger.info("Git commit: %s", client.git.get_current_commit())


@client.tree.command(name="status", description="Show detailed bot, script, and update status.")
async def status_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /status command from %s", interaction.user.id)
    running = client.is_ready()
    commit = client.git.get_current_commit()
    uptime = int((datetime.now(timezone.utc) - client.started_at).total_seconds())
    script_status = "missing"
    script_details = ""
    if SCRIPT_PATH.exists():
        script_status = "available"
        script_details = f" | updated {datetime.fromtimestamp(SCRIPT_PATH.stat().st_mtime).astimezone().isoformat()}"
    await interaction.response.send_message(
        f"**VACNET status**\n"
        f"Bot: {'running' if running else 'not running'}\n"
        f"PID: {os.getpid()}\n"
        f"Uptime: {uptime}s\n"
        f"Python: {sys.version.split()[0]}\n"
        f"Commit: {commit}\n"
        f"Script: {script_status}{script_details}\n"
        f"Supervisor: managed by supervisor",
        ephemeral=True,
    )


@client.tree.command(name="execute", description="Run the temporary hello command in the background.")
async def execute_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /execute command from %s", interaction.user.id)
    started_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    client.script_logger.info("execution started | user=%s | timestamp=%s", interaction.user.id, started_at)
    try:
        subprocess.Popen([sys.executable, str(SCRIPT_PATH)], cwd=str(ROOT_DIR))
        completed_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        client.script_logger.info("execution completed | user=%s | timestamp=%s | status=success", interaction.user.id, completed_at)
        await interaction.response.send_message("Execution started in the background and completed successfully.", ephemeral=True)
    except Exception as exc:
        failed_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        client.logger.exception("Execute command failed: %s", exc)
        client.script_logger.exception("execution failed | user=%s | timestamp=%s | error=%s", interaction.user.id, failed_at, exc)
        await interaction.response.send_message(f"Execution failed: {exc}", ephemeral=True)


@client.tree.command(name="logs", description="Show recent bot logs.")
async def logs_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /logs command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    log_file = ROOT_DIR / "logs" / "vacnet.log"
    try:
        if not log_file.exists():
            await interaction.response.send_message("No log file has been created yet.", ephemeral=True)
            return
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = "\n".join(lines[-20:]) if lines else "No log entries yet."
        await interaction.response.send_message(f"```\n{recent}\n```", ephemeral=True)
    except Exception as exc:
        client.logger.exception("Unable to read log file: %s", exc)
        await interaction.response.send_message(f"Failed to read logs: {exc}", ephemeral=True)


@client.tree.command(name="update", description="Pull latest code, install dependencies, and restart the bot safely.")
async def update_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /update command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    await interaction.response.send_message("Starting update and restart...", ephemeral=True)

    try:
        result = client.update_manager.update_and_restart()
        if result.get("status") == "ok":
            client.logger.info("Bot update completed successfully. Restarting.")
            await interaction.followup.send(
                f"Update succeeded. Commit: {result.get('commit')}. Restarting in a moment.",
                ephemeral=True,
            )
            raise SystemExit(0)
        await interaction.followup.send(
            f"Update failed: {result.get('error', 'unknown error')}. Rollback attempted if available.",
            ephemeral=True,
        )
    except SystemExit:
        raise
    except Exception as exc:
        client.logger.exception("Unexpected update failure: %s", exc)
        await interaction.followup.send(f"Update failed unexpectedly: {exc}", ephemeral=True)


@client.tree.command(name="restart", description="Restart the bot through the supervisor.")
async def restart_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /restart command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    await interaction.response.send_message("Restarting VACNET...", ephemeral=True)
    client.logger.warning("Restart requested by user %s", interaction.user.id)
    await client.close()


@client.tree.command(name="shutdown", description="Stop VACNET until it is started again.")
async def shutdown_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /shutdown command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    SHUTDOWN_MARKER.write_text("shutdown requested\n", encoding="utf-8")
    await interaction.response.send_message("VACNET is shutting down.", ephemeral=True)
    client.logger.warning("Shutdown requested by user %s", interaction.user.id)
    await client.close()


@client.tree.command(name="fetchscript", description="Download the current script file.")
async def fetchscript_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /fetchscript command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    if not SCRIPT_PATH.exists():
        await interaction.response.send_message("The current script does not exist.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Here is the current script.",
        file=discord.File(str(SCRIPT_PATH), filename="script.py"),
        ephemeral=True,
    )


@client.tree.command(name="updatescript", description="Download and activate a Python script from a link.")
@app_commands.describe(link="Direct HTTPS link to the replacement script")
async def updatescript_command(interaction: discord.Interaction, link: str) -> None:
    client.logger.info("Received /updatescript command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    if not link.lower().startswith("https://"):
        await interaction.response.send_message("Only HTTPS script links are allowed.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    temporary_path = SCRIPT_PATH.with_suffix(".download")
    backup_path = SCRIPT_PATH.with_suffix(".bak")
    try:
        urllib.request.urlretrieve(link, temporary_path)
        source = temporary_path.read_text(encoding="utf-8")
        compile(source, str(SCRIPT_PATH), "exec")
        if SCRIPT_PATH.exists():
            SCRIPT_PATH.replace(backup_path)
        temporary_path.replace(SCRIPT_PATH)
        backup_path.unlink(missing_ok=True)
        client.script_logger.info("Script updated by user=%s from=%s", interaction.user.id, link)
        await interaction.followup.send("Script updated and syntax-checked successfully.", ephemeral=True)
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        if backup_path.exists() and not SCRIPT_PATH.exists():
            backup_path.replace(SCRIPT_PATH)
        client.logger.exception("Script update failed: %s", exc)
        await interaction.followup.send(f"Script update failed: {exc}", ephemeral=True)


async def main() -> None:
    async with client:
        await client.start(settings.discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot interrupted.")
        raise
