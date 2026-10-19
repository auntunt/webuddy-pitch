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
import re
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

from .agents import git
from .errors import ApiError

MAX = 3
STANDING = "-main"  # <project>-main: the main line's current version, kept running between merges (workbench.py)
READY_S = 600  # a Java app compiling for the first time can take minutes
HEALTH_S = 1.0  # total deadline, including a slow header or response body
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


def _commit(root: Path, value) -> str:
    """Resolve a stored commit id, including an older abbreviated id; never resolve a branch here."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{4,64}", value):
        return ""
    try:
        # Revision syntax can prefer a hex-named branch over an abbreviated object id.
        # Enumerate objects instead, and reject an ambiguous prefix rather than guessing.
        objects = git(root, "rev-parse", "--disambiguate=" + value.lower(), check=False).splitlines()
        if len(objects) != 1 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", objects[0]):
            return ""
        commit = objects[0]
        return commit if git(root, "cat-file", "-t", commit, check=False).strip() == "commit" else ""
    except (OSError, RuntimeError):
        return ""


def run_binding(P, t: dict, run_id) -> dict:
    """The accepted commit of exactly this run, independent of newer adoptions or moving branches."""
    if not ((type(run_id) is int and run_id > 0) or
            (isinstance(run_id, str) and re.fullmatch(r"[1-9][0-9]{0,18}", run_id))):
        raise ApiError(400, "run_id 必须是正整数")
    rid = int(run_id)
    if rid > 2 ** 63 - 1:
        raise ApiError(400, "run_id 超出有效范围")
    with P.store.lock:
        r = P.store.run(rid)
        if not r or r["ticket_id"] != t["id"] or r["project_id"] != t["project_id"]:
            raise ApiError(404, "这张工单没有这次运行")
        decision = re.fullmatch(r"accepted:(.+)@([0-9a-fA-F]{4,64})", r.get("decision") or "")
        if r["mode"] != "fix" or not decision:
            raise ApiError(409, "这次运行还没有已采纳的代码提交，暂时不能预览")
        p = P.store.project(t["project_id"])
        commit = _commit(Path(p["root"]), decision.group(2)) if p else ""
    if not commit:
        raise ApiError(409, "这次运行采纳的提交已经无法找到，不能替换成别的版本预览")
    return {"run_id": rid, "expected_commit": commit, "branch": decision.group(1)}


def ticket_view(P, t: dict, run_id=None) -> dict:
    binding = run_binding(P, t, run_id) if run_id is not None else None
    p = P.store.project(t["project_id"])
    cmd, ready, mine = command(P.data_dir, p)
    st = status(P.data_dir, t["key"])
    matches = bound_matches(st, t["key"], binding["expected_commit"]) if binding else None
    url = bound_prefix(t["key"], binding["expected_commit"]) + "/" if binding else "/pv/%s/" % t["key"]
    return {"preview": st, "url": url if st.get("state") == "up" and matches is not False else "",
            "branch": binding["branch"] if binding else branch_of(P, t), "cmd": cmd, "configured": mine,
            "auto": settings(P.data_dir)["preview"], "own_address": bool(getattr(P, "preview_port", 0)),
            "run_id": binding["run_id"] if binding else None,
            "expected_commit": binding["expected_commit"] if binding else "", "matches_run": matches}


def start_for_ticket(P, t: dict, by: str, run_id=None) -> dict:
    binding = run_binding(P, t, run_id) if run_id is not None else None
    target = binding["expected_commit"] if binding else branch_of(P, t)
    if not target:
        raise ApiError(409, "这张工单还没有提交过代码改动，没有可以预览的版本")
    p = P.store.project(t["project_id"])
    r = start(P, p, t, target, by, expected_commit=target) if binding else start(P, p, t, target, by)
    if r.get("state") == "none":
        raise ApiError(409, r["why"])
    event = {"state": "starting"}
    if binding:
        event.update(run=binding["run_id"], commit=binding["expected_commit"])
    P.store.event(t["id"], by, "preview", "启动预览（%s，提交 %s）" % (target, r["commit"]), event)
    return ticket_view(P, t, run_id)


def stop_for_ticket(P, t: dict, by: str, run_id=None) -> dict:
    binding = run_binding(P, t, run_id) if run_id is not None else None
    if binding:
        stop(P, t["key"], expected_commit=binding["expected_commit"])
    else:
        stop(P, t["key"])
    P.store.event(t["id"], by, "preview", "停掉了预览", {"state": "stopped"})
    return ticket_view(P, t, run_id)


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
    elif st.get("state") in ("starting", "up"):
        health = _health(st)
        current = _load(data_dir).get(key) or {}
        identity = ("pid", "port", "prefix", "commit_full", "started", "cmd", "ready", "state")
        if any(current.get(k) != st.get(k) for k in identity):
            # Never publish a healthy response for a preview replaced mid-request.
            return dict(current, state="checking", why="预览已更换，刷新后重新核对") if current else {}
        st = dict(st, health=health)
        if not _alive(st.get("pid") or 0, st.get("dir", "")):
            st.update(state="failed", why="预览进程已经退出，看日志")
        elif not health["ok"]:
            st.update(state="unhealthy" if st["state"] == "up" else "starting", why=health["reason"])
        # Health observations are read-only. Recovery of the same process does
        # not restart it, alter its data, or erase an earlier human decision.
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


def stop(P, key: str, why: str = "", *, expected_commit: str = "") -> None:
    """Stop a preview and remove its worktree; `why` goes on the ticket when someone else's action stopped it."""
    with _key_lock(key):
        with _LOCK:
            st = _load(P.data_dir)
            cur = st.get(key)
            # Check while holding the same lock as start. A replacement preview must never be
            # killed between a run-specific request's preliminary read and its actual stop.
            if expected_commit and (not cur or _commit(Path(cur.get("root") or ""), cur.get("commit_full") or cur.get("commit")) != expected_commit):
                raise ApiError(409, "当前预览不是指定运行，未停止其他版本的预览")
            st.pop(key, None)
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


def start(P, p: dict, t: dict, branch: str, by: str, *, expected_commit: str = "") -> dict:
    """Run the branch as a preview. Returns its state; the app comes up in the background."""
    cmd, ready, _ = command(P.data_dir, p)
    if not cmd:
        return {"state": "none", "why": "这个项目还没有预览命令：在项目设置里填一条能启动它的命令"}
    key = t["key"]
    with _LOCK:
        st = _load(P.data_dir)
        live = sorted((v.get("started", ""), k) for k, v in st.items() if k != key and v.get("state") in ("starting", "up")
                      and not k.endswith(STANDING))  # the main line's standing preview is not one of the MAX
    for _, old in ([] if key.endswith(STANDING) else live[:max(0, len(live) - MAX + 1)]):  # in the background: the person who clicked does not wait for it
        threading.Thread(target=stop, args=(P, old, "同时最多 %d 个预览，给 %s 腾地方；需要时在工单页重新启动" % (MAX, key)), daemon=True).start()
    root = Path(p["root"])
    with _key_lock(key):
        commit = _commit(root, expected_commit) if expected_commit else git(root, "rev-parse", "--verify", branch + "^{commit}").strip()
        if not commit or (expected_commit and commit != expected_commit):
            raise ApiError(409, "指定运行的提交已经无法找到")
        with _LOCK:  # the same ticket's older preview (a newer change, or two clicks at once) goes first
            st = _load(P.data_dir)
            cur = st.pop(key, None)
            _save(P.data_dir, st)
        if cur:
            _kill(cur)
        base = Path(P.data_dir) / "previews"
        wt = base / key
        git(root, "worktree", "prune", check=False)
        if wt.exists():
            git(root, "worktree", "remove", "--force", str(wt), check=False)
        base.mkdir(parents=True, exist_ok=True)
        git(root, "worktree", "add", "--detach", "-f", str(wt), commit)
        port, prefix = _free_port(), bound_prefix(key, commit) if expected_commit else "/pv/" + key
        logs = base / "logs" / key
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / (str(time.time_ns()) + ".log")
        line = cmd.replace("{port}", str(port)).replace("{prefix}", prefix)
        with log.open("x", encoding="utf-8") as fh:
            fh.write("$ %s\n" % line)
            fh.flush()
            proc = subprocess.Popen(line, shell=True, cwd=str(wt), stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    env=_env(port, prefix), start_new_session=True)
        rec = {"key": key, "project": p["key"], "branch": branch, "commit": commit[:10], "commit_full": commit,
               "port": port, "prefix": prefix, "pid": proc.pid,
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
    state, why = ("up" if rec.get("state") == "up" else "failed"), "%d 秒内没有起来，看日志" % READY_S
    deadline = time.monotonic() + READY_S
    while state != "up" and time.monotonic() < deadline:
        if gone():
            why = "启动命令退出了%s，看日志" % ("（退出码 %s）" % proc.returncode if proc else "")
            break
        health = _health(rec)
        if health["ok"] and not gone() and time.monotonic() < deadline:
            state = "up"
            break
        why = "%d 秒内健康检查未通过：%s" % (READY_S, health["reason"])
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
    return _http_health(url)["ok"]


def _health(rec: dict) -> dict:
    try:
        port = rec["port"]
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError("invalid port")
        url = "http://127.0.0.1:%d%s" % (port, _join(rec["prefix"], rec.get("ready") or "/"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"ok": False, "reason": "预览健康检查配置无效", "checked_at": time.time()}
    return _http_health(url)


def _http_health(url: str) -> dict:
    """Direct local GET, no redirects/proxy, complete 2xx response by one deadline.

    This is endpoint availability, not proof of the application's business rules.
    The caller keeps the process/configuration identity separate from this volatile
    observation so successful polling cannot invalidate an unchanged approval.
    """
    started = time.monotonic()
    result = {"ok": False, "url": url, "checked_at": time.time(), "timeout_s": HEALTH_S,
              "status_code": None, "reason": "预览健康检查未通过"}
    conn, timer, response = None, None, None
    expired = threading.Event()
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError("only the configured local preview endpoint is supported")
        conn = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=HEALTH_S)
        conn.connect()
        sock = conn.sock

        def expire():
            expired.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        remaining = HEALTH_S - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("health deadline")
        sock.settimeout(remaining)
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        conn.request("GET", path, headers={"Accept-Encoding": "identity", "Connection": "close"})
        response = conn.getresponse()
        result["status_code"] = response.status
        if not 200 <= response.status < 300:
            result["reason"] = "预览健康检查未通过：HTTP %d（需要约定路径直接返回 2xx）" % response.status
            return result
        digest, size = hashlib.sha256(), 0
        while chunk := response.read(64 * 1024):
            digest.update(chunk)
            size += len(chunk)
        if response.length not in (None, 0):
            raise http.client.IncompleteRead(b"", response.length)
        if expired.is_set() or time.monotonic() - started >= HEALTH_S:
            raise TimeoutError("health deadline")
        result.update(ok=True, reason="约定健康端点已响应", body_bytes=size, body_sha256=digest.hexdigest())
    except (OSError, ValueError, http.client.HTTPException) as exc:
        result["reason"] = ("预览健康检查超时" if expired.is_set() or isinstance(exc, TimeoutError)
                            else "预览健康检查未通过：" + type(exc).__name__)
    finally:
        if timer:
            timer.cancel()
        if response:
            response.close()
        if conn:
            conn.close()
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    return result


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


def bound_prefix(key: str, commit: str) -> str:
    return "/pv/%s/__commit/%s" % (key, commit)


def bound_matches(st: dict, key: str, commit: str) -> bool:
    # Prefix is part of the binding: an older process serving /pv/<ticket>/ must be
    # restarted so its forms, links, cookies and assets keep the immutable address.
    return st.get("commit_full") == commit and st.get("prefix") == bound_prefix(key, commit)


def require_bound(data_dir: Path, key: str, commit: str, st=None) -> None:
    current = (_load(data_dir).get(key) or {}) if st is None else st
    if commit and not bound_matches(current, key, commit):
        raise ApiError(409, "预览版本已经切换或停止：请回到这次运行重新启动，旧地址不会打开其他版本")


def route(key: str, rest: str) -> tuple[str, str, str]:
    """Return (prefix, app-relative path, expected commit), preserving legacy paths."""
    if not rest.startswith("/__commit"):
        return "/pv/" + key, rest, ""
    m = re.fullmatch(r"/__commit/([0-9a-f]{40}|[0-9a-f]{64})(/.*)?", rest)
    if not m:
        raise ApiError(404, "无效的运行预览地址")
    return bound_prefix(key, m.group(1)), m.group(2) or "", m.group(1)


def cookie_name(key: str, expected_commit: str = "") -> str:
    return "tmh_pv_" + key + ("_" + expected_commit if expected_commit else "")


def grant(data_dir: Path, key: str, link_hash: str = "", until: float = 0, *, expected_commit: str = "") -> str:
    """A signed pass to one preview, optionally scoped to its immutable commit path."""
    exp = int(until or time.time() + GRANT_H * 3600)
    fields = [str(exp), link_hash] + ([expected_commit] if expected_commit else [])
    msg = "|".join([key] + fields)
    sig = hmac.new(_secret(data_dir), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return ".".join(fields + [sig])


def granted(data_dir: Path, key: str, g: str, *, expected_commit: str = "") -> bool:
    try:
        parts = (g or "").split(".")
        exp, lh, sig = parts[0], parts[1], parts[-1]
        commit = parts[2] if len(parts) == 4 else ""
        if len(parts) not in (3, 4) or commit != expected_commit or int(exp) < time.time():
            return False
    except (ValueError, IndexError):
        return False
    want = hmac.new(_secret(data_dir), ("|".join([key] + parts[:-1])).encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(want, sig):
        return False
    if lh.startswith("v"):  # a version link given to a client: only while it is not revoked or expired
        from . import workbench
        return workbench.share_ok(data_dir, key, lh)
    if lh:  # the client's: only while their link is still the one to use
        from . import signoff
        from .. import evidence as ev
        x = signoff._links(data_dir).get(lh)
        if not x or x.get("key") != key or x.get("used") or x["expires"] < ev.now():
            return False
        try:
            state = signoff.state(data_dir, key)
            signoff._require_current_binding(state)
            if not state.get("intact") or state.get("stale") or not signoff._link_matches(x, state):
                return False
            binding = (state.get("snapshot") or {}).get("delivery_binding")
            if binding is not None:
                bound_commit = binding.get("commit") if isinstance(binding, dict) else ""
                if (not isinstance(bound_commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", bound_commit)
                        or bound_commit != expected_commit):
                    return False
        except (ApiError, OSError, ValueError, KeyError, TypeError):
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


def forward(data_dir: Path, key: str, method: str, path: str, headers, body: bytes, sandboxed: bool = False, https: bool = False, *, expected_commit: str = ""):
    """Pass one request to the preview of `key`. `path` is the full path asked for (under /pv/<key>/), which is
    also where the app was told it lives. Returns (status, headers, response): the caller streams the response
    (and closes it), so a download or a server-sent stream is not held in memory."""
    # Connect while start/stop cannot replace the process. Once connected, a later
    # replacement can close this socket but cannot redirect it to the new version.
    with _key_lock(key):
        st = _load(data_dir).get(key) or {}
        require_bound(data_dir, key, expected_commit, st)
        if not st or st.get("state") != "up" or not _alive(st.get("pid") or 0, st.get("dir", "")):
            raise LookupError("这个项目现在的版本没有开着：在“版本”页点“启动”，或者重新生成客户链接" if key.endswith(STANDING)
                              else "这张工单现在没有在运行的预览")
        port, inner = st["port"], st["prefix"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        try:
            conn.connect()
        except Exception:
            conn.close()
            raise
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
