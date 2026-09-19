from __future__ import annotations

import asyncio
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "vacnet.log"


class DiscordChannelHandler(logging.Handler):
    def __init__(self, client, channel_id: str | int, level: int = logging.INFO):
        super().__init__(level=level)
        self.client = client
        self.channel_id = int(channel_id)

    def emit(self, record: logging.LogRecord) -> None:
        if self.client is None or not self.client.is_ready():
            return

        channel = self.client.get_channel(self.channel_id)
        if channel is None:
            return

        message = self.format(record)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(channel.send(message[:2000]))
        except RuntimeError:
            asyncio.run(channel.send(message[:2000]))


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

    return logger
