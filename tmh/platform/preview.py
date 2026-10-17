"""A version the client can open: each change waiting for acceptance runs as a preview behind the platform.

When an automatic change is committed, its branch is checked out into a worktree of its own and started with the
project's preview command on a free local port. The platform passes requests to it under /pv/<ticket>/ (people who
are logged in) and /sign/<link>/pv/ (the client, whose sign-off link is the credential), so nothing new has to be
opened in the firewall or the reverse proxy. The command gets {port} and {prefix}; an app that can serve under a
path prefix (Spring's context-path, Vite's base) should be told {prefix}, so its own links keep working.

The preview command is the project's, in <data>/previews.json: {"OA": {"cmd": "...", "ready": "/"}}. Without one,
a few common layouts are recognised (Spring Boot on Maven, a package.json with a dev or start script, Django).
Previews start by themselves only with a command a person set; a recognised one is offered on the ticket page and
starts on a click. A preview is stopped when its ticket is closed, when the same ticket gets a newer change, or to make room: at most
MAX run at once, the oldest goes first.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .agents import git

MAX = 3
READY_S = 600  # a Java app compiling for the first time can take minutes
CONF = "previews.json"
_LOCK = threading.Lock()


def _state_file(data_dir: Path) -> Path:
    return Path(data_dir) / "previews" / "state.json"


def _load(data_dir: Path) -> dict:
    try:
        return json.loads(_state_file(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data_dir: Path, st: dict) -> None:
    f = _state_file(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def project_conf(data_dir: Path, key: str) -> dict:
    try:
        v = json.loads((Path(data_dir) / CONF).read_text(encoding="utf-8")).get(key) or {}
    except (OSError, ValueError, AttributeError):
        v = {}
    return v if isinstance(v, dict) else {}


def set_conf(data_dir: Path, key: str, cmd: str, ready: str = "/") -> dict:
    f = Path(data_dir) / CONF
    with _LOCK:
        try:
            all_ = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except ValueError:
            raise ValueError("%s 不是有效的 JSON，先修好它" % f)
        if cmd.strip():
            all_[key] = {"cmd": cmd.strip(), "ready": ready.strip() or "/"}
        else:
            all_.pop(key, None)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(all_, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    return project_conf(data_dir, key)


def detect(root: Path) -> str:
    """A start command for common layouts, or "" (then a person sets one)."""
    root = Path(root)
    pom = root / "pom.xml"
    if pom.exists() and "spring-boot" in pom.read_text(encoding="utf-8", errors="replace"):
        return "mvn -q -DskipTests spring-boot:run -Dspring-boot.run.arguments='--server.port={port} --server.servlet.context-path={prefix}'"
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except ValueError:
            scripts = {}
        if "dev" in scripts:
            return "npm install --silent && npm run dev -- --port {port} --base {prefix}/"
        if "start" in scripts:
            return "npm install --silent && PORT={port} npm start"
    if (root / "manage.py").exists():
        return "python3 manage.py runserver 127.0.0.1:{port}"
    return ""


def command(data_dir: Path, p: dict) -> tuple[str, str, bool]:
    """(cmd, ready path, configured by a person)."""
    c = project_conf(data_dir, p["key"])
    if c.get("cmd"):
        return c["cmd"], c.get("ready") or "/", True
    return detect(Path(p["root"])), "/", False


AUTO = "auto"  # unless autoflow.json says "preview": "off"


def settings(data_dir: Path) -> dict:
    conf = {"preview": AUTO}
    try:
        v = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("preview")
        if v in ("auto", "off"):
            conf["preview"] = v
    except (OSError, ValueError, AttributeError):
        pass
    return conf


def branch_of(P, t: dict) -> str:
    """The branch of the ticket's latest committed change, if it is still there."""
    from .learn import _adopted, _resolve
    ad, _ = _adopted(P.store, t["id"])
    b = (ad or {}).get("branch") or ""
    p = P.store.project(t["project_id"])
    if b and p and _resolve(Path(p["root"]), b):
        return b
    c = (ad or {}).get("commit") or ""  # merged and deleted: the commit itself is still a version to look at
    return c if c and p and _resolve(Path(p["root"]), c) else ""


def on_status(P, t: dict, old: str, new: str, by: str) -> None:
    """Waiting for acceptance with a committed change: start its preview. Left that state: stop it."""
    if new == "verify":
        if settings(P.data_dir)["preview"] != "auto":
            return
        b = branch_of(P, t)
        p = P.store.project(t["project_id"])
        if not b or not p or not command(P.data_dir, p)[2]:  # a guessed command waits for a person to start it once
            return

        def go():
            try:
                start(P, p, t, b, by or "平台")
            except Exception as e:  # noqa: BLE001 - a preview that will not start must not hold the ticket up
                P.store.event(t["id"], "预览", "preview", "预览没有起来：%s" % e, {"state": "failed"})
        threading.Thread(target=go, daemon=True).start()
    elif old == "verify" and (_load(P.data_dir).get(t["key"])):
        threading.Thread(target=stop, args=(P, t["key"], "工单离开了待验证"), daemon=True).start()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def status(data_dir: Path, key: str) -> dict:
    st = _load(data_dir).get(key) or {}
    if st and st.get("state") in ("starting", "up") and not _alive(st.get("pid") or 0):
        st = dict(st, state="failed", why=st.get("why") or "预览进程已经退出，看日志")
    if st.get("log"):
        try:
            st["tail"] = Path(st["log"]).read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            st["tail"] = ""
    return st


def stop(P, key: str, why: str = "") -> None:
    with _LOCK:
        st = _load(P.data_dir)
        cur = st.pop(key, None)
        _save(P.data_dir, st)
    if not cur:
        return
    pid = cur.get("pid") or 0
    if pid and _alive(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
            for _ in range(50):
                if not _alive(pid):
                    break
                time.sleep(0.1)
            else:
                os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    wt = Path(cur.get("dir") or "")
    if cur.get("root") and wt.is_dir():
        git(Path(cur["root"]), "worktree", "remove", "--force", str(wt), check=False)


def start(P, p: dict, t: dict, branch: str, by: str) -> dict:
    """Run the branch as a preview. Returns its state; the app comes up in the background."""
    cmd, ready, _ = command(P.data_dir, p)
    if not cmd:
        return {"state": "none", "why": "这个项目还没有预览命令：在项目设置里填一条能启动它的命令"}
    key = t["key"]
    stop(P, key)
    with _LOCK:
        st = _load(P.data_dir)
        live = sorted((v.get("started", ""), k) for k, v in st.items() if v.get("state") in ("starting", "up"))
    for _, old in live[:max(0, len(live) - MAX + 1)]:
        stop(P, old, "腾地方给 %s" % key)
    root = Path(p["root"])
    commit = git(root, "rev-parse", "--verify", branch + "^{commit}").strip()
    base = Path(P.data_dir) / "previews"
    wt = base / key
    if wt.exists():
        git(root, "worktree", "remove", "--force", str(wt), check=False)
    base.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "--detach", "-f", str(wt), commit)
    port, prefix = _free_port(), "/pv/" + key
    log = base / (key + ".log")
    line = cmd.replace("{port}", str(port)).replace("{prefix}", prefix)
    env = dict(os.environ, PORT=str(port), BASE_PATH=prefix)
    with log.open("w", encoding="utf-8") as fh:
        fh.write("$ %s\n" % line)
        fh.flush()
        proc = subprocess.Popen(line, shell=True, cwd=str(wt), stdout=fh, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    rec = {"key": key, "project": p["key"], "branch": branch, "commit": commit[:10], "port": port, "prefix": prefix, "pid": proc.pid,
           "dir": str(wt), "root": str(root), "log": str(log), "cmd": line, "ready": ready, "state": "starting",
           "started": time.strftime("%Y-%m-%d %H:%M:%S"), "by": by}
    with _LOCK:
        st = _load(P.data_dir)
        st[key] = rec
        _save(P.data_dir, st)
    threading.Thread(target=_watch, args=(P, key, proc), daemon=True).start()
    return rec


def _watch(P, key: str, proc) -> None:
    rec = _load(P.data_dir).get(key) or {}
    url = "http://127.0.0.1:%d%s" % (rec.get("port", 0), _join(rec.get("prefix", ""), rec.get("ready", "/")))
    deadline = time.time() + READY_S
    state, why = "failed", "%d 秒内没有起来，看日志" % READY_S
    while time.time() < deadline:
        if proc.poll() is not None:
            why = "启动命令退出了（退出码 %s），看日志" % proc.returncode
            break
        if _answers(url) or _answers("http://127.0.0.1:%d/" % rec.get("port", 0)):
            state, why = "up", ""
            break
        time.sleep(2)
    with _LOCK:
        st = _load(P.data_dir)
        if key in st and st[key].get("pid") == rec.get("pid"):
            st[key].update(state=state, why=why, at=time.strftime("%Y-%m-%d %H:%M:%S"))
            _save(P.data_dir, st)
    t = P.store.ticket(key)
    if t:
        P.store.event(t["id"], "预览", "preview", "预览版本已经可以打开" if state == "up" else "预览没有起来：%s" % why,
                      {"state": state, "commit": rec.get("commit")})
    if state != "up" and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass


def _join(prefix: str, path: str) -> str:
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except (OSError, ValueError):
        return False


HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade",
       "host", "content-length", "accept-encoding"}
OURS = ("tmh_session", "tmh_token", "tmh_pv")  # the platform's own cookies never reach the preview


def _app_cookies(header: str) -> str:
    keep = [c.strip() for c in header.split(";") if c.strip() and not c.strip().split("=", 1)[0].startswith(OURS)]
    return "; ".join(keep)


def forward(data_dir: Path, key: str, method: str, path: str, headers, body: bytes) -> tuple[int, list, bytes]:
    """Pass one request to the preview of `key`. `path` is the full path the browser asked for (under /pv/<key>/), which
    is also where the app itself was told it lives, so its links and redirects need no rewriting beyond the port."""
    st = _load(data_dir).get(key)
    if not st or st.get("state") != "up":
        raise LookupError("这张工单现在没有在运行的预览")
    port, inner = st["port"], st["prefix"]
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=body if method not in ("GET", "HEAD") else None, method=method)
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP:
            continue
        if lk == "cookie":
            v = _app_cookies(v)
            if not v:
                continue
        req.add_header(k, v)
    req.add_header("X-Forwarded-Prefix", inner)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        r = urllib.request.build_opener(NoRedirect).open(req, timeout=60)
        code, hdrs, data = r.status, r.getheaders(), r.read()
    except urllib.error.HTTPError as e:
        code, hdrs, data = e.code, e.headers.items(), e.read()
    out = []
    for k, v in hdrs:
        lk = k.lower()
        if lk in HOP:
            continue
        if lk == "location":
            v = re.sub(r"^https?://(127\.0\.0\.1|localhost):%d" % port, "", v)
        if lk == "set-cookie":  # the app's cookies stay under its prefix, so they cannot replace the platform's
            v = re.sub(r"(?i);\s*path=[^;]*", "", v) + "; Path=%s/" % inner
        out.append((k, v))
    return code, out, data
