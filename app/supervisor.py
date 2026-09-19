from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.config import Settings
from app.launcher import Launcher
from app.logger_setup import setup_logger
from app.update_manager import UpdateManager

ROOT_DIR = Path(__file__).resolve().parent.parent
SHUTDOWN_MARKER = ROOT_DIR / ".vacnet_shutdown"


class Supervisor:
    def __init__(self, repo_root: Path, settings: Settings):
        self.repo_root = Path(repo_root)
        self.settings = settings
        self.logger = setup_logger(
            "vacnet.supervisor",
            level=getattr(__import__("logging"), settings.log_level.upper(), __import__("logging").INFO),
            discord_webhook_url=settings.discord_webhook_url,
        )
        self.launcher = Launcher(self.repo_root, self.logger)
        self.bot_process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start_bot_process(self) -> subprocess.Popen:
        with self._lock:
            if self.bot_process and self.bot_process.poll() is None:
                self.logger.info("Bot process already running.")
                return self.bot_process

            self.logger.info("Starting bot process from %s", self.repo_root)
            self.bot_process = self.launcher.start_process(
                self.repo_root / "bot.py",
                name="VACNET Bot",
            )
            return self.bot_process

    def stop_bot_process(self) -> None:
        with self._lock:
            if self.bot_process is None:
                return
            if self.bot_process.poll() is None:
                self.logger.info("Stopping bot process.")
                self.bot_process.terminate()
                try:
                    self.bot_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.logger.warning("Bot process did not terminate cleanly; forcing kill.")
                    self.bot_process.kill()
            self.bot_process = None

    def restart(self) -> None:
        self.logger.info("Restart requested.")
        self.stop_bot_process()
        time.sleep(1)
        self.start_bot_process()

    def status(self) -> dict:
        running = self.bot_process is not None and self.bot_process.poll() is None
        return {
            "running": running,
            "pid": self.bot_process.pid if self.bot_process else None,
        }


def main() -> None:
    settings = Settings.from_env()
    supervisor = Supervisor(ROOT_DIR, settings)
    logger = supervisor.logger

    logger.info("VACNET supervisor starting...")
    logger.info("Repository root: %s", ROOT_DIR)

    try:
        SHUTDOWN_MARKER.unlink(missing_ok=True)
        supervisor.start_bot_process()
        while True:
            time.sleep(5)
            if SHUTDOWN_MARKER.exists():
                logger.info("Shutdown requested by Discord command.")
                SHUTDOWN_MARKER.unlink(missing_ok=True)
                supervisor.stop_bot_process()
                return
            if supervisor.bot_process and supervisor.bot_process.poll() is not None:
                logger.warning("Bot process exited unexpectedly. Restarting.")
                supervisor.start_bot_process()
    except KeyboardInterrupt:
        logger.info("Supervisor stopping on keyboard interrupt.")
        supervisor.stop_bot_process()
        raise


if __name__ == "__main__":
    main()
