from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from app.git_manager import GitManager


class UpdateManager:
    def __init__(self, repo_root: Path, logger, settings, supervisor=None):
        self.repo_root = Path(repo_root)
        self.logger = logger
        self.settings = settings
        self.supervisor = supervisor
        self.git = GitManager(repo_root, logger)

    def install_requirements(self) -> None:
        venv_python = self.repo_root / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = self.repo_root / "venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            raise FileNotFoundError("Python virtual environment not found. Create .venv and install requirements first.")

        self.logger.info("Installing Python requirements using virtual environment.")
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
            cwd=str(self.repo_root),
            check=False,
        )
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Dependency installation failed:\n{result.stdout}\n{result.stderr}")

    def update_and_restart(self) -> dict:
        self.logger.info("Starting update process.")
        backup_name = None
        try:
            self.git.ensure_repo()
            backup_name = self.git.backup_current_state("pre-update")
            self.logger.info("Created backup marker: %s", backup_name)

            self.git.pull_latest(self.settings.git_branch)
            self.install_requirements()

            self.logger.info("Update succeeded. The supervisor will restart the bot after the process exits.")
            return {"status": "ok", "backup": backup_name, "commit": self.git.get_current_commit()}
        except Exception as exc:
            self.logger.exception("Update failed: %s", exc)
            if backup_name:
                try:
                    self.logger.warning("Attempting rollback to backup: %s", backup_name)
                    self.git.rollback_to_backup(backup_name)
                    self.logger.warning("Rollback succeeded.")
                except Exception as rollback_exc:
                    self.logger.exception("Rollback failed: %s", rollback_exc)
            return {"status": "failed", "error": str(exc), "backup": backup_name}

    def current_version(self) -> str:
        try:
            return self.git.get_current_commit()
        except Exception:
            return "unknown"
