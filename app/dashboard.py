from __future__ import annotations

import json
import hashlib
import hmac
import logging
import os
import secrets
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import Settings
from app.logger_setup import LOG_STREAMS, read_log_lines, setup_logger
from app.supervisor import Supervisor
from app.tunnel import CloudflareQuickTunnel
from app.update_manager import UpdateManager

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT_DIR / "logs" / "vacnet.log"
SCRIPT_RUNNER = ROOT_DIR / "scripts" / "run_script.bat"
TUNNEL_STATE_FILE = ROOT_DIR / "logs" / "dashboard_tunnel.json"

LOGIN_PAGE = """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>VACNET Login</title><style>body{background:#101418;color:#eef2f4;font:16px monospace;display:grid;place-items:center;min-height:100vh}form{background:#191f25;border:1px solid #303943;padding:28px;border-radius:7px;min-width:min(360px,80vw)}input,button{display:block;width:100%;padding:12px;margin-top:12px;background:#242c33;color:#eef2f4;border:1px solid #48545d;border-radius:4px;font:inherit}button{cursor:pointer;border-color:#48d7c2}h1{font:700 28px Georgia,serif}</style></head><body><form method='post' action='/login'><h1>VACNET</h1><p>Development dashboard authentication</p><input name='token' type='password' placeholder='Dashboard password' autocomplete='current-password' required><button type='submit'>Sign in</button></form></body></html>"""

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
<div class="panel wide"><div class="label">Recent logs</div><div class="actions"><select id="log-stream" onchange="refreshLogs()"><option value="all">all</option><option value="bot">bot</option><option value="supervisor">supervisor</option><option value="dashboard">dashboard</option><option value="script">script</option><option value="update">update</option><option value="error">error</option><option value="legacy">legacy</option></select><select id="log-level" onchange="refreshLogs()"><option>DEBUG</option><option selected>INFO</option><option>WARNING</option><option>ERROR</option><option>CRITICAL</option></select></div><pre id="logs">Loading...</pre></div>
<div class="panel"><div class="label">Last action</div><div class="value" id="action">None</div><div class="footer" id="detail">Ready.</div></div>
</section></main><div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);function toast(t){$('toast').textContent=t;$('toast').style.display='block';setTimeout(()=>{$('toast').style.display='none'},3500)}
async function refreshLogs(){try{const stream=$('log-stream').value,level=$('log-level').value;const r=await fetch('/api/logs?stream='+stream+'&minimum_level='+level);const d=await r.json();$('logs').textContent=d.logs||'No matching logs.'}catch(e){toast('Unable to load logs')}}
async function refresh(){try{const r=await fetch('/api/status');const d=await r.json();$('bot-state').textContent=d.running?'RUNNING':'STOPPED';$('bot-state').className='value '+(d.running?'online':'offline');$('pid').textContent=d.pid||'-';$('commit').textContent=d.commit;$('branch').textContent=d.branch;$('script').textContent=d.script;$('clock').textContent=new Date().toLocaleTimeString();refreshLogs()}catch(e){toast('Dashboard connection lost')}}
let csrf='';
async function refresh(){try{const r=await fetch('/api/status');const d=await r.json();if(!r.ok)throw Error(d.error||'Authentication required');csrf=d.csrf||csrf;$('bot-state').textContent=d.running?'RUNNING':'STOPPED';$('bot-state').className='value '+(d.running?'online':'offline');$('pid').textContent=d.pid||'-';$('commit').textContent=d.commit;$('branch').textContent=d.branch;$('script').textContent=d.script;$('clock').textContent=new Date().toLocaleTimeString();refreshLogs()}catch(e){toast('Dashboard connection lost')}}
async function act(name){$('action').textContent=name.toUpperCase();$('detail').textContent='Working...';try{const r=await fetch('/api/action/'+name,{method:'POST',headers:{'X-CSRF-Token':csrf}});const d=await r.json();if(!r.ok)throw Error(d.error||'Action failed');$('detail').textContent=d.message||'Complete';toast(d.message||'Complete');refresh()}catch(e){$('detail').textContent=e.message;toast(e.message)}}
refresh();setInterval(refresh,4000);
</script></body></html>"""


class DashboardState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = setup_logger("vacnet.dashboard", level=getattr(logging, settings.log_level.upper(), logging.INFO))
        self.supervisor = Supervisor(ROOT_DIR, settings)
        self.update_manager = UpdateManager(ROOT_DIR, self.logger, settings)
        self.lock = threading.Lock()
        self.tunnel = CloudflareQuickTunnel(
            settings.cloudflared_path,
            f"http://127.0.0.1:{settings.dashboard_port}",
            TUNNEL_STATE_FILE,
            self.logger,
        )
        self.sessions: dict[str, tuple[float, str]] = {}
        self.session_lock = threading.Lock()

    def create_session(self) -> tuple[str, str]:
        session = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        expires = time.time() + self.settings.dashboard_session_minutes * 60
        with self.session_lock:
            self.sessions[session] = (expires, csrf)
        return session, csrf

    def session(self, token: str | None) -> tuple[str, str] | None:
        if not token:
            return None
        with self.session_lock:
            value = self.sessions.get(token)
            if value and value[0] > time.time():
                return token, value[1]
            self.sessions.pop(token, None)
        return None

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
            "tunnel": self.tunnel.status(),
        }

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

    def cookies(self):
        from http.cookies import SimpleCookie
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return {key: value.value for key, value in cookie.items()}

    def authenticated(self) -> bool:
        return self.state.session(self.cookies().get("vacnet_session")) is not None

    def csrf_valid(self) -> bool:
        session = self.state.session(self.cookies().get("vacnet_session"))
        return bool(session and hmac.compare_digest(session[1], self.headers.get("X-CSRF-Token", "")))

    def redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            if not self.authenticated():
                body = LOGIN_PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            if not self.authenticated():
                self.send_json({"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
                return
            payload = self.state.status()
            session = self.state.session(self.cookies().get("vacnet_session"))
            payload["csrf"] = session[1] if session else ""
            self.send_json(payload)
        elif path == "/api/logs":
            if not self.authenticated():
                self.send_json({"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
                return
            query = parse_qs(urlparse(self.path).query)
            stream = query.get("stream", ["all"])[0]
            minimum_level = query.get("minimum_level", ["INFO"])[0]
            if stream not in LOG_STREAMS:
                self.send_json({"error": "Unknown log stream"}, HTTPStatus.BAD_REQUEST)
                return
            lines = read_log_lines(stream, minimum_level, 100)
            self.send_json({"stream": stream, "minimum_level": minimum_level, "logs": "\n".join(lines)})
        else:
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            length = int(self.headers.get("Content-Length", "0"))
            values = parse_qs(self.rfile.read(length).decode("utf-8"))
            supplied = values.get("token", [""])[0]
            expected = self.state.settings.dashboard_auth_token or ""
            if hmac.compare_digest(supplied, expected):
                session, csrf = self.state.create_session()
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                self.redirect("/", f"vacnet_session={session}; HttpOnly; SameSite=Lax; Max-Age={self.state.settings.dashboard_session_minutes * 60}{secure}")
            else:
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                body = b"Invalid dashboard password."
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        if path == "/logout":
            self.redirect("/", "vacnet_session=; HttpOnly; SameSite=Lax; Max-Age=0")
            return
        if not self.authenticated():
            self.send_json({"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
            return
        if not self.csrf_valid():
            self.send_json({"error": "Invalid CSRF token"}, HTTPStatus.FORBIDDEN)
            return
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
    server = ThreadingHTTPServer(("127.0.0.1", settings.dashboard_port), DashboardHandler)
    state.logger.info("Dev dashboard listening at http://127.0.0.1:8765")
    try:
        state.tunnel.start()
    except Exception as exc:
        state.logger.error("event=tunnel_start_failed error=%s", exc, extra={"discord_notify": True})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        state.supervisor.stop_bot_process()
    finally:
        state.tunnel.stop()
        server.server_close()


if __name__ == "__main__":
    main()
