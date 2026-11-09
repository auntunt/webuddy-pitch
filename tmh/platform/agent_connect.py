"""Owner's executor connection methods: the CLI's own local login, a gateway's model list, and the saved API setup.

Only fixed login commands are run, chosen by engine on the server; nothing from the browser is executed. Output is streamed
to the caller through a bounded session that can be read by id, so the operator at the desk finishes any browser step.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .errors import ApiError

LOGIN_COMMANDS = {"codex": ["login"], "claude": ["setup-token"]}
SESSIONS: dict = {}
_LOCK = threading.Lock()
MAX_LINES = 400


class _Session:
    def __init__(self, proc, label):
        self.proc, self.label, self.lines, self.done, self.started = proc, label, [], False, time.time()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for raw in self.proc.stdout:
            with _LOCK:
                self.lines.append(raw.rstrip("\n"))
                del self.lines[:-MAX_LINES]
        self.proc.wait()
        with _LOCK:
            self.done = True
            self.lines.append("（已结束，退出码 %s）" % self.proc.returncode)


def start_login(engine: str, exe: str, env: dict) -> dict:
    if engine not in LOGIN_COMMANDS:
        raise ApiError(400, "这个执行器没有本机登录命令")
    proc = subprocess.Popen([exe, *LOGIN_COMMANDS[engine]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, env=env, text=True, encoding="utf-8", errors="replace")
    sid = uuid.uuid4().hex
    with _LOCK:
        SESSIONS[sid] = _Session(proc, engine)
    return {"session": sid, "command": "%s %s" % (engine, " ".join(LOGIN_COMMANDS[engine]))}


def read_login(sid: str) -> dict:
    with _LOCK:
        s = SESSIONS.get(sid)
        if s is None:
            raise ApiError(404, "没有这个登录会话")
        return {"lines": list(s.lines), "done": s.done}


_MODEL_ID = re.compile(r"^[A-Za-z0-9._:/\-]{1,120}$")


def probe_gateway(url: str, key: str = "") -> list[str]:
    """Lists model ids from an OpenAI-compatible gateway's GET /v1/models (e.g. magpie at http://127.0.0.1:3425)."""
    if not re.match(r"^https?://[^\s/]+", url or ""):
        raise ApiError(400, "网关地址必须以 http:// 或 https:// 开头")
    req = urllib.request.Request(url.rstrip("/") + "/v1/models", headers={"Authorization": "Bearer " + key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ApiError(400, "网关没有返回模型列表：%s" % exc) from exc
    models = [m.get("id", "") for m in body.get("data", []) if isinstance(m, dict)]
    models = [m for m in models if _MODEL_ID.match(m)]
    if not models:
        raise ApiError(400, "网关返回了空的模型列表")
    return models
