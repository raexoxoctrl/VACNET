from __future__ import annotations

import subprocess
from pathlib import Path


class GitManager:
    def __init__(self, repo_root: Path, logger):
        self.repo_root = Path(repo_root)
        self.logger = logger

    def run_git(self, *args: str, check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
        command = ["git", *args]
        self.logger.info("Running git command: %s", " ".join(command))
        result = subprocess.run(
            command,
            cwd=str(self.repo_root),
            capture_output=capture_output,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git command failed: {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        return result

    def ensure_repo(self) -> None:
        if not (self.repo_root / ".git").exists():
            raise RuntimeError(f"Repository not initialized at {self.repo_root}")

    def get_current_commit(self) -> str:
        result = self.run_git("rev-parse", "--short", "HEAD")
        return result.stdout.strip() or "unknown"

    def pull_latest(self, branch: str) -> str:
        self.ensure_repo()
        self.run_git("fetch", "origin", branch)
        self.logger.warning("Overwriting local repository files with origin/%s.", branch)
        self.run_git("checkout", "-B", branch, f"origin/{branch}")
        self.run_git("reset", "--hard", f"origin/{branch}")
        self.run_git("clean", "-fd")
        return self.git_head_message(branch)

    def git_head_message(self, branch: str) -> str:
        result = self.run_git("log", "-1", "--oneline", f"origin/{branch}")
        return result.stdout.strip()

    def backup_current_state(self, label: str) -> str:
        self.ensure_repo()
        backup_name = f"backup/{label}"
        self.run_git("branch", "-f", backup_name)
        return backup_name

    def rollback_to_backup(self, backup_name: str) -> str:
        self.ensure_repo()
        self.run_git("checkout", backup_name)
        self.run_git("reset", "--hard", backup_name)
        return backup_name
