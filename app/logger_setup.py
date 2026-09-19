from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import discord

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = ROOT_DIR / "logs" / "vacnet.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5
_CONFIGURED_LOGGERS: set[str] = set()
LOG_STREAMS = {
    "all": "all.log",
    "bot": "bot.log",
    "supervisor": "supervisor.log",
    "dashboard": "dashboard.log",
    "script": "script.log",
    "update": "update.log",
    "error": "error.log",
    "legacy": "vacnet.log",
}


def read_log_lines(stream: str = "all", minimum_level: str = "DEBUG", limit: int = 50) -> list[str]:
    path = LOG_DIR / LOG_STREAMS.get(stream, LOG_STREAMS["all"])
    if not path.exists():
        return []
    levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    threshold = levels.get(minimum_level.upper(), 10)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    filtered = []
    for line in lines:
        if any(f"| {name} |" in line for name, value in levels.items() if value >= threshold):
            filtered.append(line)
    return filtered[-max(1, min(limit, 200)):]


class CombinedRotatingFileHandler(TimedRotatingFileHandler):
    """Rotate at midnight or when the current file reaches MAX_BYTES."""

    def shouldRollover(self, record: logging.LogRecord) -> int:
        if self.stream is None:
            self.stream = self._open()
        if super().shouldRollover(record):
            return 1
        message = f"{self.format(record)}{self.terminator}"
        size = len(message.encode(self.encoding or "utf-8"))
        return 1 if self.stream.tell() + size >= MAX_BYTES else 0


class DiscordNotifyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or bool(getattr(record, "discord_notify", False))


def _category_for_logger(name: str) -> str:
    if name.startswith("vacnet.supervisor"):
        return "supervisor"
    if name.startswith("vacnet.dashboard"):
        return "dashboard"
    if name.startswith("vacnet.script"):
        return "script"
    if name.startswith("vacnet.update") or name.startswith("vacnet.git"):
        return "update"
    return "bot"


def _formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | pid=%(process)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def log_embed(record: logging.LogRecord, message: str) -> dict:
    level = record.levelname.upper()
    colors = {"DEBUG": 0x95A5A6, "INFO": 0x3498DB, "WARNING": 0xF1C40F, "ERROR": 0xE67E22, "CRITICAL": 0xE74C3C}
    return {
        "title": f"VACNET {level}",
        "description": message[:4096],
        "color": colors.get(level, 0x3498DB),
        "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        "fields": [
            {"name": "Source", "value": _category_for_logger(record.name), "inline": True},
            {"name": "Logger", "value": record.name, "inline": True},
            {"name": "PID", "value": str(record.process), "inline": True},
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
        self.addFilter(DiscordNotifyFilter())

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
        try:
            loop = self.client.loop
            if loop.is_closed() or not loop.is_running():
                return
            loop.call_soon_threadsafe(asyncio.create_task, self._send(discord_embed(record, self.format(record))))
        except Exception:
            return


def _file_handler(path: Path, level: int, formatter: logging.Formatter) -> logging.Handler:
    handler = CombinedRotatingFileHandler(path, when="midnight", interval=1, backupCount=BACKUP_COUNT, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def setup_logger(
    name: str = "vacnet",
    level: int = logging.INFO,
    *,
    client=None,
    discord_channel_id: str | int | None = None,
) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    if name in _CONFIGURED_LOGGERS:
        return logger

    formatter = _formatter()
    category = _category_for_logger(name)
    logger.addHandler(_file_handler(LOG_DIR / "all.log", level, formatter))
    logger.addHandler(_file_handler(LOG_FILE, level, formatter))
    logger.addHandler(_file_handler(LOG_DIR / f"{category}.log", level, formatter))
    logger.addHandler(_file_handler(LOG_DIR / "error.log", logging.ERROR, formatter))

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if client is not None and discord_channel_id:
        channel_handler = DiscordChannelHandler(client, discord_channel_id, level)
        channel_handler.setFormatter(formatter)
        logger.addHandler(channel_handler)
    _CONFIGURED_LOGGERS.add(name)
    return logger
