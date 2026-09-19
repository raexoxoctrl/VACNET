from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)


@dataclass(frozen=True)
class Settings:
    discord_token: str
    allowed_user_ids: tuple[str, ...]
    git_repo_url: str
    git_branch: str
    log_level: str = "INFO"
    bot_log_channel_id: str | None = None
    script_log_channel_id: str | None = None
    discord_webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        token = (os.getenv("DISCORD_TOKEN") or "").strip()
        repo_url = (os.getenv("GIT_REPO_URL") or "").strip()
        branch = (os.getenv("GIT_BRANCH") or "main").strip() or "main"
        log_level = (os.getenv("LOG_LEVEL") or "INFO").strip().upper() or "INFO"
        raw_allowed = (os.getenv("ALLOWED_USER_IDS") or "").strip()
        allowed_ids = tuple(item.strip() for item in raw_allowed.split(",") if item.strip())
        bot_log_channel_id = (os.getenv("BOT_LOG_CHANNEL_ID") or "").strip() or None
        script_log_channel_id = (os.getenv("SCRIPT_LOG_CHANNEL_ID") or "").strip() or None
        discord_webhook_url = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip() or None

        if not token:
            raise ValueError("DISCORD_TOKEN is not set. Add it to your .env file.")
        if not repo_url:
            raise ValueError("GIT_REPO_URL is not set. Add it to your .env file.")
        if not allowed_ids:
            raise ValueError("ALLOWED_USER_IDS is not set. Add at least one Discord user ID.")

        return cls(
            discord_token=token,
            allowed_user_ids=allowed_ids,
            git_repo_url=repo_url,
            git_branch=branch,
            log_level=log_level,
            bot_log_channel_id=bot_log_channel_id,
            script_log_channel_id=script_log_channel_id,
            discord_webhook_url=discord_webhook_url,
        )
