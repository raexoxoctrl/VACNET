from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import discord

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "vacnet.log"


def log_embed(record: logging.LogRecord, message: str) -> dict:
    level = record.levelname.upper()
    colors = {
        "DEBUG": 0x95A5A6,
        "INFO": 0x3498DB,
        "WARNING": 0xF1C40F,
        "ERROR": 0xE67E22,
        "CRITICAL": 0xE74C3C,
    }
    return {
        "title": f"VACNET {level}",
        "description": message[:4096],
        "color": colors.get(level, 0x3498DB),
        "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        "fields": [
            {"name": "Logger", "value": record.name, "inline": True},
            {"name": "Level", "value": level, "inline": True},
        ],
    }


def discord_embed(record: logging.LogRecord, message: str) -> discord.Embed:
    payload = log_embed(record, message)
    embed = discord.Embed(
        title=payload["title"],
        description=payload["description"],
        color=payload["color"],
        timestamp=datetime.fromtimestamp(record.created, timezone.utc),
    )
    for field in payload["fields"]:
        embed.add_field(**field)
    return embed


class DiscordChannelHandler(logging.Handler):
    def __init__(self, client, channel_id: str | int, level: int = logging.INFO):
        super().__init__(level=level)
        self.client = client
        self.channel_id = int(channel_id)

    async def _send(self, embed: discord.Embed) -> None:
        try:
            channel = self.client.get_channel(self.channel_id)
            if channel is not None:
                await channel.send(embed=embed)
        except Exception:
            logging.getLogger("vacnet.discord").exception("Unable to send log to Discord channel")

    def emit(self, record: logging.LogRecord) -> None:
        if self.client is None or not self.client.is_ready():
            return

        embed = discord_embed(record, self.format(record))
        try:
            target_loop = self.client.loop
            if target_loop.is_closed() or not target_loop.is_running():
                return
            target_loop.call_soon_threadsafe(asyncio.create_task, self._send(embed))
        except Exception:
            return


class DiscordWebhookHandler(logging.Handler):
    def __init__(self, webhook_url: str, level: int = logging.INFO):
        super().__init__(level=level)
        self.webhook_url = webhook_url

    async def _send(self, embed: dict) -> None:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.webhook_url, json={"embeds": [embed]}) as response:
                    if response.status >= 300:
                        logging.getLogger("vacnet.webhook").error(
                            "Discord webhook returned HTTP %s", response.status
                        )
        except Exception:
            logging.getLogger("vacnet.webhook").exception("Unable to send log to Discord webhook")

    def emit(self, record: logging.LogRecord) -> None:
        embed = log_embed(record, self.format(record))
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send(embed))
        except RuntimeError:
            try:
                asyncio.run(self._send(embed))
            except RuntimeError:
                return


def setup_logger(
    name: str = "vacnet",
    level: int = logging.INFO,
    *,
    client=None,
    discord_channel_id: str | int | None = None,
    discord_webhook_url: str | None = None,
) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    if client is not None and discord_channel_id:
        channel_handler = DiscordChannelHandler(client, discord_channel_id, level)
        channel_handler.setFormatter(formatter)
        logger.addHandler(channel_handler)

    if discord_webhook_url:
        webhook_handler = DiscordWebhookHandler(discord_webhook_url, level)
        webhook_handler.setFormatter(formatter)
        logger.addHandler(webhook_handler)

    return logger
