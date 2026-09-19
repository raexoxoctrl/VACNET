from __future__ import annotations

import logging
import shutil
import re
import subprocess
import threading
import time
import json
from pathlib import Path

QUICK_TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


class CloudflareQuickTunnel:
    def __init__(self, executable: str, local_url: str, state_path: Path, logger: logging.Logger):
        self.executable = executable
        self.local_url = local_url
        self.state_path = state_path
        self.logger = logger
        self.process: subprocess.Popen[str] | None = None
        self.url: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                return
            self._stop.clear()
            executable = self._resolve_executable()
            try:
                self.process = subprocess.Popen(
                    [executable, "tunnel", "--no-autoupdate", "--url", self.local_url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except FileNotFoundError as exc:
                self.logger.error("event=tunnel_missing executable=%s", self.executable)
                raise RuntimeError("cloudflared was not found. Install it and set CLOUDFLARED_PATH.") from exc
            self._thread = threading.Thread(target=self._watch, name="cloudflare-tunnel", daemon=True)
            self._thread.start()
            self.logger.info("event=tunnel_started", extra={"discord_notify": True})

    def _resolve_executable(self) -> str:
        if Path(self.executable).exists():
            return self.executable
        found = shutil.which(self.executable)
        if found:
            return found
        if self.executable.lower() == "cloudflared" and Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe").exists():
            return r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
        raise FileNotFoundError(self.executable)

    def stop(self) -> None:
        self._stop.set()
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        self.process = None
        self.url = None
        self._write_state(None)

    def status(self) -> dict:
        process = self.process
        return {"running": bool(process and process.poll() is None), "pid": process.pid if process else None, "url": self.url}

    def _watch(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            self.logger.debug("tunnel_output=%s", line)
            match = QUICK_TUNNEL_PATTERN.search(line)
            if match and match.group(0) != self.url:
                self.url = match.group(0)
                self.logger.info("event=tunnel_url_ready url=%s", self.url, extra={"discord_notify": True})
                self._write_state(self.url)
        if not self._stop.is_set():
            self.logger.warning("event=tunnel_exited", extra={"discord_notify": True})
            time.sleep(2)
            if not self._stop.is_set():
                try:
                    self.start()
                except Exception:
                    self.logger.exception("event=tunnel_restart_failed", extra={"discord_notify": True})

    def _write_state(self, url: str | None) -> None:
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps({"url": url}), encoding="utf-8")
        temporary_path.replace(self.state_path)
