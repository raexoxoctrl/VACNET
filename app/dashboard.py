from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.config import Settings
from app.logger_setup import setup_logger
from app.supervisor import Supervisor
from app.update_manager import UpdateManager

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT_DIR / "logs" / "vacnet.log"
SCRIPT_RUNNER = ROOT_DIR / "scripts" / "run_script.bat"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VACNET Dev Console</title>
<style>
:root{color-scheme:dark;--bg:#101418;--panel:#191f25;--line:#303943;--text:#eef2f4;--muted:#9aa6ad;--cyan:#48d7c2;--amber:#f4b860;--red:#f27777}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0,#1b3435 0,transparent 34%),var(--bg);color:var(--text);font:14px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}
main{max-width:1120px;margin:0 auto;padding:42px 24px 56px}.kicker{color:var(--cyan);letter-spacing:.16em;font-size:11px}.top{display:flex;align-items:end;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:24px;margin-bottom:22px}h1{font:700 38px/1.1 Georgia,serif;margin:8px 0 0;letter-spacing:0}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.panel{background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);padding:18px;border-radius:7px}.wide{grid-column:span 2}.label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.12em}.value{font-size:20px;margin-top:8px}.online{color:var(--cyan)}.offline{color:var(--red)}.actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}button{border:1px solid var(--line);background:#242c33;color:var(--text);padding:10px 13px;border-radius:5px;font:inherit;cursor:pointer}button:hover{border-color:var(--cyan);color:var(--cyan)}button.warn:hover{border-color:var(--amber);color:var(--amber)}button.danger:hover{border-color:var(--red);color:var(--red)}pre{white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;color:#c9d4d8;margin:12px 0 0;font-size:12px}.meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}.meta div{border-top:1px solid var(--line);padding-top:8px}.toast{position:fixed;right:22px;bottom:22px;background:#26353a;border:1px solid var(--cyan);padding:12px 15px;border-radius:5px;display:none}.footer{margin-top:18px;color:var(--muted);font-size:11px}@media(max-width:760px){.grid{grid-template-columns:1fr}.wide{grid-column:span 1}.top{display:block}h1{font-size:30px}}
</style></head>
<body><main>
<div class="top"><div><div class="kicker">LOCAL DEVELOPMENT CONSOLE</div><h1>VACNET</h1><div class="muted">Supervisor controls, diagnostics, and logs</div></div><div class="muted" id="clock">--:--:--</div></div>
<section class="grid">
<div class="panel"><div class="label">Bot process</div><div class="value" id="bot-state">Loading</div><div class="meta"><div><span class="label">PID</span><br><span id="pid">-</span></div><div><span class="label">Port</span><br>localhost only</div></div></div>
<div class="panel"><div class="label">Repository</div><div class="value" id="commit">Loading</div><div class="meta"><div><span class="label">Branch</span><br><span id="branch">-</span></div><div><span class="label">Script</span><br><span id="script">-</span></div></div></div>
<div class="panel"><div class="label">Controls</div><div class="actions"><button onclick="act('start')">Start</button><button class="warn" onclick="act('restart')">Restart</button><button class="danger" onclick="act('stop')">Stop</button><button onclick="act('execute')">Execute</button><button class="warn" onclick="act('update')">Update</button></div><div class="footer">Development-only controls. This page is bound to 127.0.0.1.</div></div>
<div class="panel wide"><div class="label">Recent logs</div><pre id="logs">Loading...</pre></div>
<div class="panel"><div class="label">Last action</div><div class="value" id="action">None</div><div class="footer" id="detail">Ready.</div></div>
</section></main><div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);function toast(t){$('toast').textContent=t;$('toast').style.display='block';setTimeout(()=>{$('toast').style.display='none'},3500)}
async function refresh(){try{const r=await fetch('/api/status');const d=await r.json();$('bot-state').textContent=d.running?'RUNNING':'STOPPED';$('bot-state').className='value '+(d.running?'online':'offline');$('pid').textContent=d.pid||'-';$('commit').textContent=d.commit;$('branch').textContent=d.branch;$('script').textContent=d.script;$('logs').textContent=d.logs||'No logs yet.';$('clock').textContent=new Date().toLocaleTimeString()}catch(e){toast('Dashboard connection lost')}}
async function act(name){$('action').textContent=name.toUpperCase();$('detail').textContent='Working...';try{const r=await fetch('/api/action/'+name,{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.error||'Action failed');$('detail').textContent=d.message||'Complete';toast(d.message||'Complete');refresh()}catch(e){$('detail').textContent=e.message;toast(e.message)}}
refresh();setInterval(refresh,4000);
</script></body></html>"""


class DashboardState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = setup_logger("vacnet.dashboard", level=getattr(logging, settings.log_level.upper(), logging.INFO))
        self.supervisor = Supervisor(ROOT_DIR, settings)
        self.update_manager = UpdateManager(ROOT_DIR, self.logger, settings)
        self.lock = threading.Lock()

    def status(self) -> dict:
        state = self.supervisor.status()
        try:
            commit = self.update_manager.current_version()
            branch = self.update_manager.git.get_current_branch()
        except Exception:
            commit, branch = "unknown", "unknown"
        return {
            **state,
            "commit": commit,
            "branch": branch,
            "script": "available" if (ROOT_DIR / "exes" / "script.py").exists() else "missing",
            "logs": self.read_logs(),
        }

    @staticmethod
    def read_logs() -> str:
        if not LOG_FILE.exists():
            return "No logs yet."
        return "\n".join(LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-45:])

    def action(self, name: str) -> str:
        with self.lock:
            if name == "start":
                self.supervisor.start_bot_process()
                return "Bot started."
            if name == "stop":
                self.supervisor.stop_bot_process()
                return "Bot stopped."
            if name == "restart":
                self.supervisor.restart()
                return "Bot restarted."
            if name == "execute":
                environment = os.environ.copy()
                environment["VACNET_NONINTERACTIVE"] = "1"
                subprocess.Popen(["cmd.exe", "/d", "/c", str(SCRIPT_RUNNER)], cwd=str(ROOT_DIR), env=environment)
                self.logger.info("Dashboard started script execution.")
                return "Script execution started."
            if name == "update":
                result = self.update_manager.update_and_restart()
                if result.get("status") != "ok":
                    raise RuntimeError(result.get("error", "Update failed"))
                self.supervisor.restart()
                return f"Updated to {result.get('commit')} and restarted."
            raise ValueError("Unknown action")


class DashboardHandler(BaseHTTPRequestHandler):
    state: DashboardState

    def log_message(self, format: str, *args) -> None:
        self.state.logger.info("dashboard | " + format, *args)

    def send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            self.send_json(self.state.status())
        else:
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/action/"):
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            message = self.state.action(path.rsplit("/", 1)[-1])
            self.send_json({"message": message})
        except Exception as exc:
            self.state.logger.exception("Dashboard action failed: %s", exc)
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    settings = Settings.from_env()
    state = DashboardState(settings)
    DashboardHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 8765), DashboardHandler)
    state.logger.info("Dev dashboard listening at http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        state.supervisor.stop_bot_process()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
