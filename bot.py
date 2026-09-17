from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import discord
from discord import app_commands

from app.config import Settings
from app.executor import open_cmd_with_hello
from app.git_manager import GitManager
from app.logger_setup import setup_logger
from app.update_manager import UpdateManager

ROOT_DIR = Path(__file__).resolve().parent


class VacnetBot(discord.Client):
    def __init__(self, *, intents: discord.Intents, settings: Settings):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.settings = settings
        self.logger = setup_logger("vacnet.bot", level=getattr(logging, settings.log_level.upper(), logging.INFO))
        self.git = GitManager(ROOT_DIR, self.logger)
        self.update_manager = UpdateManager(ROOT_DIR, self.logger, settings)

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


@client.tree.command(name="status", description="Check whether the bot is running and the current Git commit.")
async def status_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /status command from %s", interaction.user.id)
    running = client.is_ready()
    commit = client.git.get_current_commit()
    await interaction.response.send_message(
        f"Status: {'running' if running else 'not running'}\nCommit: {commit}",
        ephemeral=True,
    )


@client.tree.command(name="execute", description="Open a Windows CMD window and print hello.")
async def execute_command(interaction: discord.Interaction) -> None:
    client.logger.info("Received /execute command from %s", interaction.user.id)
    try:
        open_cmd_with_hello()
        await interaction.response.send_message("Opened a Windows CMD window and printed: hello", ephemeral=True)
    except Exception as exc:
        client.logger.exception("Execute command failed: %s", exc)
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


async def main() -> None:
    async with client:
        await client.start(settings.discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot interrupted.")
        raise
