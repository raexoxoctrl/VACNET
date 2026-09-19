from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class Launcher:
    def __init__(self, repo_root: Path, logger):
        self.repo_root = Path(repo_root)
        self.logger = logger

    def start_process(self, target: str | Path, *, name: str, env: dict | None = None) -> subprocess.Popen:
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = (self.repo_root / target_path).resolve()

        command = [sys.executable, str(target_path)]

        self.logger.info("Launching %s: %s", name, " ".join(command))

        final_env = os.environ.copy()
        if env:
            final_env.update(env)

        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            creation_flags = 0

        return subprocess.Popen(
            command,
            cwd=str(self.repo_root),
            env=final_env,
            creationflags=creation_flags,
        )
