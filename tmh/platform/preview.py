"""A version the client can open: each change waiting for acceptance runs as a preview.

When a change is committed and its ticket waits for acceptance, its commit is checked out into a worktree of its
own and started with the project's preview command on a free local port, bound to this machine only. The platform
passes requests to it under /pv/<ticket>/. The command gets {port} and {prefix}; an app that can serve under a path
prefix (Spring's context-path, Vite's base, Django's FORCE_SCRIPT_NAME) should be told {prefix}, so its own links
keep working.

The code in a preview has not been accepted by anyone, so it must not be able to act as the person looking at it.
Two ways to keep it apart from the platform:
- its own address (serve --preview-port, and TMH_PREVIEW_BASE when a reverse proxy gives that port a name): a
  different origin, so the browser itself keeps its pages away from the platform's;
- otherwise, on the platform's own address, every preview page is sent with a CSP sandbox: the browser runs it as
  an origin of its own, without the platform's cookies. Pages, styles, scripts and images load; but a sandboxed
  page sends no Referer, so its scripts' calls back to its own app cannot be told from another site's and are
  not let through, and it has no localStorage. Server-rendered apps work there; single-page apps need their own
  address.
Either way a preview is opened with a grant: a signed cookie for that one preview, given to a person who is logged
in, or to the client through their sign-off link (and only while that link is valid).

The preview command is the project's, in <data>/previews.json: {"OA": {"cmd": "...", "ready": "/"}}. Without one,
a few common layouts are recognised (Spring Boot on Maven, a package.json with a dev or start script, Django).
Previews start by themselves only with a command a person set; a recognised one is offered on the ticket page and
starts on a click. A preview is stopped when its ticket leaves 待验证, when the same ticket gets a newer change, or
to make room: at most MAX run at once, the oldest goes first.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import secrets
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
GRANT_H = 12  # a person's grant; the client's lasts as long as their link
_LOCK = threading.Lock()  # state.json and previews.json
_KEYS: dict = {}  # one start or stop at a time for each ticket


def _key_lock(key: str) -> threading.Lock:
    with _LOCK:
        return _KEYS.setdefault(key, threading.Lock())


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


def set_conf(data_dir: Path, key: str, cmd: str, ready: str = "/", by: str = "") -> dict:
    """A command runs on this machine: who set it, and when, is kept with it and in previews.log."""
    f = Path(data_dir) / CONF
    with _LOCK:
        try:
            all_ = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except ValueError:
            raise ValueError("%s 不是有效的 JSON，先修好它" % f)
        if cmd.strip():
            all_[key] = {"cmd": cmd.strip(), "ready": ready.strip() or "/", "by": by, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        else:
            all_.pop(key, None)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(all_, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, f)
        with (Path(data_dir) / "previews.log").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "by": by, "project": key, "cmd": cmd.strip()}, ensure_ascii=False) + "\n")
    return project_conf(data_dir, key)


def detect(root: Path) -> str:
    """A start command for common layouts, or "" (then a person sets one). Each listens on this machine only."""
    root = Path(root)
    pom = root / "pom.xml"
    if pom.exists() and "spring-boot" in pom.read_text(encoding="utf-8", errors="replace"):
        return ("mvn -q -DskipTests spring-boot:run -Dspring-boot.run.arguments='--server.port={port} --server.address=127.0.0.1 "
                "--server.servlet.context-path={prefix}'")
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except ValueError:
            scripts = {}
        if "dev" in scripts:
            return "npm install --silent && npm run dev -- --host 127.0.0.1 --port {port} --base {prefix}/"
        if "start" in scripts:
            return "npm install --silent && HOST=127.0.0.1 PORT={port} npm start"
    if (root / "manage.py").exists():
        return "FORCE_SCRIPT_NAME={prefix} python3 manage.py runserver 127.0.0.1:{port}"
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
    elif old == "verify" and _load(P.data_dir).get(t["key"]):
        threading.Thread(target=stop, args=(P, t["key"]), daemon=True).start()


# ---------------------------------------------------------------- processes

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _alive(pid: int, wt: str = "") -> bool:
    """The process is running (not a zombie) and, where /proc tells, is still the one started in `wt`: after a
    restart of the machine the same number can belong to something else, which must never be killed."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    proc = Path("/proc/%d" % pid)
    if not proc.is_dir():
        return True  # no /proc (macOS): the signal check is all there is
    try:
        if proc.joinpath("stat").read_text().rsplit(")", 1)[1].split()[0] == "Z":
            return False
        if wt:
            return os.readlink(proc / "cwd").startswith(str(wt))
    except (OSError, IndexError):
        return False
    return True


def _set(data_dir: Path, key: str, pid: int, **kv) -> bool:
    """Update a preview's record if it is still the run `pid` started."""
    with _LOCK:
        st = _load(data_dir)
        if key in st and st[key].get("pid") == pid:
            st[key].update(kv, at=time.strftime("%Y-%m-%d %H:%M:%S"))
            _save(data_dir, st)
            return True
    return False


def status(data_dir: Path, key: str) -> dict:
    st = _load(data_dir).get(key) or {}
    if st and st.get("state") in ("starting", "up") and not _alive(st.get("pid") or 0, st.get("dir", "")):
        st = dict(st, state="failed", why=st.get("why") or "预览进程已经退出，看日志")
    if st.get("log"):
        try:
            st["tail"] = Path(st["log"]).read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            st["tail"] = ""
    return st


def _kill(rec: dict) -> None:
    pid = rec.get("pid") or 0
    if not _alive(pid, rec.get("dir", "")):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
        for _ in range(50):
            if not _alive(pid):
                return
            time.sleep(0.1)
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


def _clean(rec: dict) -> None:
    wt = Path(rec.get("dir") or "")
    if rec.get("root") and wt.is_dir():
        git(Path(rec["root"]), "worktree", "remove", "--force", str(wt), check=False)


def stop(P, key: str, why: str = "") -> None:
    """Stop a preview and remove its worktree; `why` goes on the ticket when someone else's action stopped it."""
    with _key_lock(key):
        with _LOCK:
            st = _load(P.data_dir)
            cur = st.pop(key, None)
            _save(P.data_dir, st)
        if not cur:
            return
        _kill(cur)
        _clean(cur)
    if why:
        t = P.store.ticket(key)
        if t:
            P.store.event(t["id"], "预览", "preview", "预览停了：%s" % why, {"state": "stopped"})


SAFE_ENV = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TZ", "TMPDIR", "TERM", "JAVA_HOME", "MAVEN_HOME", "M2_HOME",
            "GRADLE_HOME", "NODE_PATH", "NVM_DIR", "PYTHONPATH", "VIRTUAL_ENV", "GOPATH", "GOROOT", "DOTNET_ROOT")


def _env(port: int, prefix: str) -> dict:
    """What a preview gets from the platform's environment: tools, not secrets (no TMH_TOKEN, no API keys)."""
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV or k.startswith(("LC_", "MAVEN_OPTS", "JAVA_OPTS", "npm_config_"))}
    env.update(PORT=str(port), BASE_PATH=prefix, HOST="127.0.0.1")
    return env


def start(P, p: dict, t: dict, branch: str, by: str) -> dict:
    """Run the branch as a preview. Returns its state; the app comes up in the background."""
    cmd, ready, _ = command(P.data_dir, p)
    if not cmd:
        return {"state": "none", "why": "这个项目还没有预览命令：在项目设置里填一条能启动它的命令"}
    key = t["key"]
    with _LOCK:
        st = _load(P.data_dir)
        live = sorted((v.get("started", ""), k) for k, v in st.items() if k != key and v.get("state") in ("starting", "up"))
    for _, old in live[:max(0, len(live) - MAX + 1)]:  # in the background: the person who clicked does not wait for it
        threading.Thread(target=stop, args=(P, old, "同时最多 %d 个预览，给 %s 腾地方；需要时在工单页重新启动" % (MAX, key)), daemon=True).start()
    root = Path(p["root"])
    with _key_lock(key):
        with _LOCK:  # the same ticket's older preview (a newer change, or two clicks at once) goes first
            st = _load(P.data_dir)
            cur = st.pop(key, None)
            _save(P.data_dir, st)
        if cur:
            _kill(cur)
        commit = git(root, "rev-parse", "--verify", branch + "^{commit}").strip()
        base = Path(P.data_dir) / "previews"
        wt = base / key
        git(root, "worktree", "prune", check=False)
        if wt.exists():
            git(root, "worktree", "remove", "--force", str(wt), check=False)
        base.mkdir(parents=True, exist_ok=True)
        git(root, "worktree", "add", "--detach", "-f", str(wt), commit)
        port, prefix = _free_port(), "/pv/" + key
        log = base / (key + ".log")
        line = cmd.replace("{port}", str(port)).replace("{prefix}", prefix)
        with log.open("w", encoding="utf-8") as fh:
            fh.write("$ %s\n" % line)
            fh.flush()
            proc = subprocess.Popen(line, shell=True, cwd=str(wt), stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    env=_env(port, prefix), start_new_session=True)
        rec = {"key": key, "project": p["key"], "branch": branch, "commit": commit[:10], "port": port, "prefix": prefix, "pid": proc.pid,
               "dir": str(wt), "root": str(root), "log": str(log), "cmd": line, "ready": ready, "state": "starting",
               "started": time.strftime("%Y-%m-%d %H:%M:%S"), "by": by}
        with _LOCK:
            st = _load(P.data_dir)
            st[key] = rec
            _save(P.data_dir, st)
    threading.Thread(target=_watch, args=(P, rec, proc), daemon=True).start()
    return rec


def _watch(P, rec: dict, proc=None) -> None:
    """Wait for the app to answer, then for it to end. `proc` is None for a preview this process did not start
    (found running after a restart of the platform): then it is watched through /proc."""
    key, pid = rec["key"], rec["pid"]
    gone = (lambda: proc.poll() is not None) if proc else (lambda: not _alive(pid, rec["dir"]))
    url = "http://127.0.0.1:%d%s" % (rec["port"], _join(rec["prefix"], rec.get("ready", "/")))
    state, why = ("up" if rec.get("state") == "up" else "failed"), "%d 秒内没有起来，看日志" % READY_S
    deadline = time.time() + READY_S
    while state != "up" and time.time() < deadline:
        if gone():
            why = "启动命令退出了%s，看日志" % ("（退出码 %s）" % proc.returncode if proc else "")
            break
        if _answers(url) or _answers("http://127.0.0.1:%d/" % rec["port"]):
            state = "up"
            break
        time.sleep(2)
    if state == "up":
        if rec.get("state") != "up" and _set(P.data_dir, key, pid, state="up", why=""):
            _note(P, key, "预览版本已经可以打开", "up", rec)
        while not gone():  # the app ends (crashed, killed): say so, instead of sending people to a dead page
            if proc:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            else:
                time.sleep(5)
        why = "预览进程退出了%s，看日志" % ("（退出码 %s）" % proc.returncode if proc else "")
    if _set(P.data_dir, key, pid, state="failed", why=why):
        _note(P, key, "预览没有起来：%s" % why if state != "up" else why, "failed", rec)
        _kill(rec)
        _clean(rec)  # the log stays; the checkout (node_modules and all) does not pile up


def _note(P, key: str, body: str, state: str, rec: dict) -> None:
    t = P.store.ticket(key)
    if t:
        P.store.event(t["id"], "预览", "preview", body, {"state": state, "commit": rec.get("commit")})


def resume(P) -> None:
    """At start: previews still running from before are watched again; records whose process is gone say so."""
    for key, rec in list(_load(P.data_dir).items()):
        if rec.get("state") not in ("starting", "up"):
            continue
        if _alive(rec.get("pid") or 0, rec.get("dir", "")):
            threading.Thread(target=_watch, args=(P, rec), daemon=True).start()
        elif _set(P.data_dir, key, rec.get("pid"), state="failed", why="平台重启时预览进程已经不在了，在工单页重新启动"):
            _clean(rec)


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


# ---------------------------------------------------------------- who may open a preview

def _secret(data_dir: Path) -> bytes:
    f = Path(data_dir) / "previews" / "secret"
    with _LOCK:
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(f), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(secrets.token_hex(32))
        return f.read_text().strip().encode()


def grant(data_dir: Path, key: str, link_hash: str = "", until: float = 0) -> str:
    """A signed pass to one preview: until when, and the sign-off link it came from (checked again on each use)."""
    exp = int(until or time.time() + GRANT_H * 3600)
    msg = "%s|%d|%s" % (key, exp, link_hash)
    sig = hmac.new(_secret(data_dir), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return "%d.%s.%s" % (exp, link_hash, sig)


def granted(data_dir: Path, key: str, g: str) -> bool:
    try:
        exp, lh, sig = (g or "").split(".")
        if int(exp) < time.time():
            return False
    except ValueError:
        return False
    want = hmac.new(_secret(data_dir), ("%s|%s|%s" % (key, exp, lh)).encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(want, sig):
        return False
    if lh:  # the client's: only while their link is still the one to use
        from . import signoff
        from .. import evidence as ev
        x = signoff._links(data_dir).get(lh)
        if not x or x.get("key") != key or x.get("used") or x["expires"] < ev.now():
            return False
    return True


def base_url(headers, port: int) -> str:
    """Where previews live when they have an address of their own: TMH_PREVIEW_BASE, or this host on `port`."""
    b = os.environ.get("TMH_PREVIEW_BASE", "").rstrip("/")
    if b or not port:
        return b
    host = (headers.get("X-Forwarded-Host") or headers.get("Host") or "127.0.0.1").split(",")[0].strip()
    host = host.rsplit(":", 1)[0] if not host.endswith("]") else host
    return "http://%s:%d" % (host, port)


# ---------------------------------------------------------------- passing requests on

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade",
       "host", "content-length", "accept-encoding", "server", "date"}
OURS = ("tmh_session", "tmh_token", "tmh_pv")  # the platform's own cookies never reach the preview
SANDBOX = "sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads"


def _app_cookies(header: str) -> str:
    keep = [c.strip() for c in header.split(";") if c.strip() and not c.strip().split("=", 1)[0].startswith(OURS)]
    return "; ".join(keep)


def forward(data_dir: Path, key: str, method: str, path: str, headers, body: bytes, sandboxed: bool = False, https: bool = False):
    """Pass one request to the preview of `key`. `path` is the full path asked for (under /pv/<key>/), which is
    also where the app was told it lives. Returns (status, headers, response): the caller streams the response
    (and closes it), so a download or a server-sent stream is not held in memory."""
    st = _load(data_dir).get(key)
    if not st or st.get("state") != "up" or not _alive(st.get("pid") or 0, st.get("dir", "")):
        raise LookupError("这张工单现在没有在运行的预览")
    port, inner = st["port"], st["prefix"]
    out = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP or lk.startswith("x-forwarded-"):
            continue
        if lk == "cookie":
            v = _app_cookies(v)
            if not v:
                continue
        out[k] = v
    out.update({"Host": "127.0.0.1:%d" % port, "X-Forwarded-Prefix": inner, "Accept-Encoding": "identity"})
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    conn.request(method, path, body=body if body or method not in ("GET", "HEAD") else None, headers=out)
    r = conn.getresponse()
    hdrs = []
    for k, v in r.getheaders():
        lk = k.lower()
        if lk in HOP and not (lk == "content-length" and method == "HEAD"):
            continue
        if lk == "location":
            for origin in ("http://127.0.0.1:%d" % port, "http://localhost:%d" % port):
                if v.startswith(origin):
                    v = v[len(origin):] or "/"
        if lk == "set-cookie":  # the app's cookies stay under its prefix, so they cannot replace the platform's
            parts = [x for x in v.split(";") if not x.strip().lower().startswith(("path=", "samesite=", "secure"))]
            v = ";".join(parts) + "; Path=%s/" % inner + ("; SameSite=None; Secure" if sandboxed and https else "")
        if lk in ("content-security-policy", "x-frame-options") and sandboxed:
            continue
        hdrs.append((k, v))
    if sandboxed:  # an origin of its own: pages, styles, scripts and images load; its scripts' own calls back do not
        hdrs.append(("Content-Security-Policy", SANDBOX + "; frame-ancestors 'self'"))
    hdrs.append(("X-Robots-Tag", "noindex"))
    length = r.getheader("Content-Length")
    return r.status, hdrs, r, (int(length) if length and length.isdigit() else None)
