from __future__ import annotations

import asyncio
import json
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
from app.logger_setup import LOG_STREAMS, read_log_lines, setup_logger
from app.update_manager import UpdateManager

ROOT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = ROOT_DIR / "exes" / "script.py"
RUN_SCRIPT_PATH = ROOT_DIR / "scripts" / "run_script.bat"
SHUTDOWN_MARKER = ROOT_DIR / ".vacnet_shutdown"
TUNNEL_STATE_FILE = ROOT_DIR / "logs" / "dashboard_tunnel.json"


def result_embed(title: str, description: str, *, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, description=description[:4096], color=color, timestamp=datetime.now(timezone.utc))


def output_text(value: bytes | None) -> str:
    return (value or b"").decode("utf-8", errors="replace").strip()


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
        )
        self.script_logger = setup_logger(
            "vacnet.script",
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            client=self,
            discord_channel_id=settings.script_log_channel_id,
        )
        self.update_logger = setup_logger(
            "vacnet.update",
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            client=self,
            discord_channel_id=settings.bot_log_channel_id,
        )
        self.git = GitManager(ROOT_DIR, self.logger)
        self.update_manager = UpdateManager(ROOT_DIR, self.update_logger, settings)
        self.started_at = datetime.now(timezone.utc)
        self.tunnel_url_task: asyncio.Task | None = None

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
    if client.tunnel_url_task is None or client.tunnel_url_task.done():
        client.tunnel_url_task = asyncio.create_task(watch_tunnel_url())


async def watch_tunnel_url() -> None:
    last_url: str | None = None
    while not client.is_closed():
        try:
            if TUNNEL_STATE_FILE.exists():
                state = json.loads(TUNNEL_STATE_FILE.read_text(encoding="utf-8"))
                url = state.get("url")
                if url and url != last_url:
                    await announce_tunnel_url(url)
                    last_url = url
                elif not url:
                    last_url = None
        except Exception:
            client.logger.exception("Unable to read dashboard tunnel state")
        await asyncio.sleep(5)


async def announce_tunnel_url(url: str) -> None:
    channel_id = client.settings.dashboard_url_channel_id or client.settings.bot_log_channel_id
    if not channel_id:
        client.logger.error("Dashboard URL cannot be announced: no dashboard or bot channel ID configured.")
        return
    channel = client.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await client.fetch_channel(int(channel_id))
        except Exception:
            client.logger.exception("Unable to access dashboard URL channel %s", channel_id)
            return
    embed = discord.Embed(
        title="VACNET dashboard is online",
        description="A new temporary HTTPS dashboard URL is available.",
        url=url,
        color=discord.Color.teal(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Open dashboard", value=f"[Launch dashboard]({url})", inline=False)
    embed.add_field(name="Authentication", value="Sign in with the dashboard password from the VACNET PC `.env` file.", inline=False)
    embed.add_field(name="Lifetime", value="Temporary URL; a new link will be posted if the tunnel restarts.", inline=False)
    await channel.send(embed=embed)
    client.logger.info("event=tunnel_url_announced channel=%s", channel_id, extra={"discord_notify": True})


@client.tree.command(name="status", description="Show detailed bot, script, and update status.")
async def status_command(interaction: discord.Interaction) -> None:
    client.logger.info("event=command_received command=status user=%s", interaction.user.id, extra={"discord_notify": True})
    running = client.is_ready()
    commit = client.git.get_current_commit()
    uptime = int((datetime.now(timezone.utc) - client.started_at).total_seconds())
    script_status = "missing"
    script_details = ""
    if SCRIPT_PATH.exists():
        script_status = "available"
        script_details = f" | updated {datetime.fromtimestamp(SCRIPT_PATH.stat().st_mtime).astimezone().isoformat()}"
    await interaction.response.send_message(
        embed=result_embed(
            "VACNET status",
            "The supervisor and bot are responding.",
            color=discord.Color.green() if running else discord.Color.red(),
        ).add_field(name="Bot", value="Running" if running else "Not running")
        .add_field(name="Process", value=f"PID {os.getpid()}\nUptime {uptime}s")
        .add_field(name="Runtime", value=f"Python {sys.version.split()[0]}\nCommit `{commit}`")
        .add_field(name="Script", value=f"{script_status}{script_details}", inline=False)
        .add_field(name="Supervisor", value="Managed by supervisor"),
        ephemeral=True,
    )


@client.tree.command(name="execute", description="Run the script and report its complete output.")
async def execute_command(interaction: discord.Interaction) -> None:
    client.logger.info("event=command_received command=execute user=%s", interaction.user.id, extra={"discord_notify": True})
    started_at = datetime.now(timezone.utc)
    client.script_logger.info("execution started | user=%s | timestamp=%s", interaction.user.id, started_at.isoformat())
    await interaction.response.defer(ephemeral=True)
    try:
        environment = os.environ.copy()
        environment["VACNET_NONINTERACTIVE"] = "1"
        process = await asyncio.create_subprocess_exec(
            "cmd.exe",
            "/d",
            "/c",
            str(RUN_SCRIPT_PATH),
            cwd=str(ROOT_DIR),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        stdout_text = output_text(stdout)
        stderr_text = output_text(stderr)
        for line in stdout_text.splitlines():
            client.script_logger.info("stdout | %s", line)
        for line in stderr_text.splitlines():
            client.script_logger.error("stderr | %s", line)
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        success = process.returncode == 0
        client.script_logger.log(
            logging.INFO if success else logging.ERROR,
            "execution finished | user=%s | exit_code=%s | duration=%.2fs | status=%s",
            interaction.user.id,
            process.returncode,
            duration,
            "success" if success else "failed",
        )
        details = stdout_text or "No standard output."
        if stderr_text:
            details += f"\n\nSTDERR:\n{stderr_text}"
        embed = result_embed(
            "Script execution complete" if success else "Script execution failed",
            details,
            color=discord.Color.green() if success else discord.Color.red(),
        )
        embed.add_field(name="Exit code", value=str(process.returncode))
        embed.add_field(name="Duration", value=f"{duration:.2f}s")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as exc:
        client.logger.exception("Execute command failed: %s", exc)
        client.script_logger.exception("execution failed | user=%s | error=%s", interaction.user.id, exc)
        await interaction.followup.send(
            embed=result_embed("Execution could not start", str(exc), color=discord.Color.red()),
            ephemeral=True,
        )


@client.tree.command(name="logs", description="Show recent bot logs.")
@app_commands.describe(stream="Log stream to inspect", minimum_level="Minimum severity", lines="Number of recent lines")
async def logs_command(interaction: discord.Interaction, stream: str = "all", minimum_level: str = "INFO", lines: int = 20) -> None:
    client.logger.info("Received /logs command from %s", interaction.user.id)
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message(
            embed=result_embed("Access denied", "You are not authorized to use this command.", color=discord.Color.red()),
            ephemeral=True,
        )
        return

    try:
        if stream not in LOG_STREAMS:
            raise ValueError(f"Unknown log stream. Choose: {', '.join(LOG_STREAMS)}")
        entries = read_log_lines(stream, minimum_level, lines)
        if not entries:
            await interaction.response.send_message(
                embed=result_embed("Logs", f"No entries found in `{stream}` at `{minimum_level}` or above.", color=discord.Color.orange()),
                ephemeral=True,
            )
            return
        recent = "\n".join(entries)
        embed = result_embed("Recent VACNET logs", f"Stream `{stream}` | minimum `{minimum_level}`", color=discord.Color.blurple())
        embed.add_field(name="Output", value=f"```text\n{recent[:1000]}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as exc:
        client.logger.exception("Unable to read log file: %s", exc)
        await interaction.response.send_message(
            embed=result_embed("Unable to read logs", str(exc), color=discord.Color.red()),
            ephemeral=True,
        )


@client.tree.command(name="update", description="Pull latest code, install dependencies, and restart the bot safely.")
async def update_command(interaction: discord.Interaction) -> None:
    client.update_logger.info("event=command_received command=update user=%s", interaction.user.id, extra={"discord_notify": True})
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    await interaction.response.send_message(
        embed=result_embed("Update started", "The repository will be overwritten and dependencies reinstalled.", color=discord.Color.orange()),
        ephemeral=True,
    )

    try:
        result = await asyncio.to_thread(client.update_manager.update_and_restart)
        if result.get("status") == "ok":
            client.logger.info("Bot update completed successfully. Restarting.")
            await interaction.followup.send(
                embed=result_embed(
                    "Update succeeded",
                    f"Commit: `{result.get('commit')}`\nRestarting in a moment.",
                    color=discord.Color.green(),
                ),
                ephemeral=True,
            )
            raise SystemExit(0)
        await interaction.followup.send(
            embed=result_embed(
                "Update failed",
                str(result.get("error", "unknown error")),
                color=discord.Color.red(),
            ),
            ephemeral=True,
        )
    except SystemExit:
        raise
    except Exception as exc:
        client.logger.exception("Unexpected update failure: %s", exc)
        await interaction.followup.send(
            embed=result_embed("Update failed unexpectedly", str(exc), color=discord.Color.red()),
            ephemeral=True,
        )


@client.tree.command(name="restart", description="Restart the bot through the supervisor.")
async def restart_command(interaction: discord.Interaction) -> None:
    client.logger.info("event=command_received command=restart user=%s", interaction.user.id, extra={"discord_notify": True})
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=result_embed("Restarting VACNET", "The supervisor will launch the bot again.", color=discord.Color.orange()),
        ephemeral=True,
    )
    client.logger.warning("Restart requested by user %s", interaction.user.id)
    await client.close()


@client.tree.command(name="shutdown", description="Stop VACNET until it is started again.")
async def shutdown_command(interaction: discord.Interaction) -> None:
    client.logger.info("event=command_received command=shutdown user=%s", interaction.user.id, extra={"discord_notify": True})
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    SHUTDOWN_MARKER.write_text("shutdown requested\n", encoding="utf-8")
    await interaction.response.send_message(
        embed=result_embed("VACNET shutting down", "The supervisor will leave the bot stopped.", color=discord.Color.orange()),
        ephemeral=True,
    )
    client.logger.warning("Shutdown requested by user %s", interaction.user.id)
    await client.close()


@client.tree.command(name="fetchscript", description="Download the current script file.")
async def fetchscript_command(interaction: discord.Interaction) -> None:
    client.script_logger.info("event=command_received command=fetchscript user=%s", interaction.user.id, extra={"discord_notify": True})
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    if not SCRIPT_PATH.exists():
        await interaction.response.send_message(
            embed=result_embed("Script unavailable", "The current script does not exist.", color=discord.Color.red()),
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        embed=result_embed("Current script", "Attached as `script.py`.", color=discord.Color.blurple()),
        file=discord.File(str(SCRIPT_PATH), filename="script.py"),
        ephemeral=True,
    )


@client.tree.command(name="updatescript", description="Download and activate a Python script from a link.")
@app_commands.describe(link="Direct HTTPS link to the replacement script")
async def updatescript_command(interaction: discord.Interaction, link: str) -> None:
    client.script_logger.info("event=command_received command=updatescript user=%s", interaction.user.id, extra={"discord_notify": True})
    if not client.is_admin(interaction.user.id):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    if not link.lower().startswith("https://"):
        await interaction.response.send_message(
            embed=result_embed("Invalid script link", "Only HTTPS script links are allowed.", color=discord.Color.red()),
            ephemeral=True,
        )
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
        await interaction.followup.send(
            embed=result_embed(
                "Script updated",
                "The replacement downloaded and passed Python syntax validation.",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        if backup_path.exists() and not SCRIPT_PATH.exists():
            backup_path.replace(SCRIPT_PATH)
        client.logger.exception("Script update failed: %s", exc)
        await interaction.followup.send(
            embed=result_embed("Script update failed", str(exc), color=discord.Color.red()),
            ephemeral=True,
        )


async def main() -> None:
    async with client:
        await client.start(settings.discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot interrupted.")
        raise
