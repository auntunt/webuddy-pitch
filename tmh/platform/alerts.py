"""Alerts and error logs open tickets on their own.

Monitoring (Prometheus Alertmanager, SkyWalking, Grafana, Zabbix through a script, a log platform's watcher or
anything that can POST) sends to /hook/alert/<项目代号>. Each alert becomes a ticket that goes straight into the
automatic flow, unless one is already open for it: the same alert (by its fingerprint) only counts up on the
open ticket and leaves a comment at most every ten minutes, and its "resolved" notice is noted there.
Stack traces in the message (Java, Python, .NET) are matched to files in the repository, so the analysis
starts from the code that threw. At most `per_hour` new tickets per project an hour; the rest only count.

Configuration in <data>/alerts.json. Keys are environment variable names only, never values:

    {"TOG": {"key_env": "TMH_ALERT_KEY_TOG"}, "*": {"key_env": "TMH_ALERT_KEY", "per_hour": 20}}

The sender authenticates with `Authorization: Bearer <the key>` (or `?key=` for tools that can't set
headers). Accepted bodies: Alertmanager webhooks, SkyWalking alarm lists, a JSON object with
title/summary/message and description/text/stack/detail, or plain text (first line is the title).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path

from .store import now

BY = "告警"
SKIP_DIRS = {".git", ".tmh", "node_modules", "target", "bin", "obj", "dist", "build", "out", ".idea", ".vs", "__pycache__", ".venv", "venv"}


class AlertError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def conf(data_dir: Path) -> dict:
    f = Path(data_dir) / "alerts.json"
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def project_conf(data_dir: Path, key: str) -> dict | None:
    c = conf(data_dir)
    return c.get(key) or c.get("*")


def status(data_dir: Path, key: str) -> dict:
    c = project_conf(data_dir, key)
    if c is None:
        return {"configured": False, "path": "/hook/alert/%s" % key}
    env = c.get("key_env") or ""
    return {"configured": True, "ready": bool(env and os.environ.get(env)), "key_env": env, "per_hour": int(c.get("per_hour") or 20),
            "path": "/hook/alert/%s" % key}


def check(data_dir: Path, key: str, headers, query: dict) -> dict:
    c = project_conf(data_dir, key)
    if c is None:
        raise AlertError(404, "这个项目没有开告警接入（在数据目录的 alerts.json 里配置）")
    env = c.get("key_env") or ""
    want = os.environ.get(env, "") if env else ""
    if not want:
        raise AlertError(503, "告警接入未配置密钥（环境变量 %s）" % (env or "未指定"))
    got = (headers.get("Authorization") or "").replace("Bearer ", "", 1).strip() or (query.get("key") or [""])[0]
    if not got or not hmac.compare_digest(got, want):
        raise AlertError(401, "告警密钥不对")
    return c


# ---------------------------------------------------------------- parsing

def _s(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if v not in (None, "") else ""


def _first(d: dict, *keys) -> str:
    for k in keys:
        if d.get(k) not in (None, ""):
            return _s(d[k]).strip()
    return ""


def parse(raw: bytes) -> list:
    """Alerts in a webhook body: [{title, text, severity, status, service, fingerprint, source}]."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    try:
        d = json.loads(text)
    except ValueError:
        lines = text.splitlines()
        return [{"title": lines[0].strip()[:200], "text": text[:20000], "severity": _sev_in(text), "status": "firing", "service": "", "fingerprint": "", "source": "text"}]
    out = []
    if isinstance(d, dict) and isinstance(d.get("alerts"), list):  # Alertmanager (and Grafana's unified alerting)
        common = d.get("commonLabels") or {}
        for a in d["alerts"]:
            lb, an = dict(common, **(a.get("labels") or {})), a.get("annotations") or {}
            title = _first(an, "summary", "title") or lb.get("alertname") or "告警"
            body = "\n".join(x for x in [_first(an, "description", "message"), "标签：" + ", ".join("%s=%s" % kv for kv in sorted(lb.items())) if lb else "",
                                         "开始：" + a["startsAt"] if a.get("startsAt") else ""] if x)
            out.append({"title": title, "text": body, "severity": lb.get("severity") or lb.get("priority") or "", "status": a.get("status") or d.get("status") or "firing",
                        "service": lb.get("service") or lb.get("job") or lb.get("app") or "", "fingerprint": a.get("fingerprint") or "", "source": "alertmanager"})
        return out
    if isinstance(d, list):  # SkyWalking sends a list of alarms; also accept a list of generic objects
        for a in d:
            if not isinstance(a, dict):
                continue
            if "alarmMessage" in a:
                out.append({"title": a.get("alarmMessage", "")[:200], "text": _s(a), "severity": a.get("ruleName", ""), "status": "firing",
                            "service": a.get("name", ""), "fingerprint": "%s|%s" % (a.get("ruleName", ""), a.get("name", "")), "source": "skywalking"})
            else:
                out += _generic(a)
        return out
    return _generic(d) if isinstance(d, dict) else []


def _generic(d: dict) -> list:
    title = _first(d, "title", "summary", "subject", "message", "msg", "alertname", "name")
    body = _first(d, "description", "text", "body", "detail", "details", "content", "stack", "stacktrace", "exception", "log")
    if not title and not body:
        return []
    if not title:
        title = body.splitlines()[0]
    extra = _first(d, "stack", "stacktrace", "exception")
    if extra and extra not in body:
        body += "\n" + extra
    st = _first(d, "status", "state").lower()
    return [{"title": title.splitlines()[0][:200], "text": body[:20000], "severity": _first(d, "severity", "level", "priority"),
             "status": "resolved" if st in ("resolved", "ok", "recovered", "closed") else "firing",
             "service": _first(d, "service", "app", "application", "host", "instance"), "fingerprint": _first(d, "fingerprint", "id", "alert_id", "key"),
             "source": _first(d, "source") or "json"}]


def _sev_in(text: str) -> str:
    m = re.search(r"\b(FATAL|CRITICAL|ERROR|WARN(?:ING)?)\b", text)
    return m.group(1) if m else ""


PRI = [("urgent", ("critical", "fatal", "disaster", "emergency", "p0", "s0", "sev0", "sev1", "严重", "紧急", "致命")),
       ("high", ("error", "high", "major", "p1", "s1", "sev2", "错误", "重要")),
       ("low", ("info", "low", "minor", "p3", "p4", "提示")),
       ("normal", ("warning", "warn", "average", "p2", "s2", "一般", "警告"))]


def priority(sev: str) -> str:
    s = (sev or "").strip().lower()
    if not s:
        return "normal"
    tok = s.split()[0]
    for code, words in PRI:
        if s in words or tok in words:
            return code
    return "high"


def fingerprint(a: dict) -> str:
    if a.get("fingerprint"):
        return str(a["fingerprint"])[:64]
    title = re.sub(r"\d+", "#", a.get("title", "")).strip().lower()  # ids, counts and times differ between firings
    return hashlib.sha1(("%s|%s" % (a.get("service", ""), title)).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- stack traces → files

FRAMES = [("java", re.compile(r"at\s+([\w$.]+)\.([\w$<>]+)\(([\w$]+\.(?:java|kt|scala|groovy)):(\d+)\)")),
          ("python", re.compile(r'File "([^"]+\.py)", line (\d+)(?:, in (\S+))?')),
          ("dotnet", re.compile(r"\bat\s+([\w.`<>\[\],]+)\(.*?\)\s+in\s+(.+?\.(?:cs|vb)):line\s+(\d+)")),
          ("node", re.compile(r"at\s+(?:(\S+)\s+\()?(?:file://)?([^\s():]+\.(?:js|ts|mjs|cjs)):(\d+):\d+\)?"))]


def frames(text: str) -> list:
    """(path hint, line, symbol) for each stack frame in the text, outermost frameworks included."""
    out = []
    for kind, rx in FRAMES:
        for m in rx.finditer(text or ""):
            if kind == "java":
                cls, meth, fname, ln = m.groups()
                pkg = cls.split("$")[0].rsplit(".", 1)[0] if "." in cls else ""
                out.append((pkg.replace(".", "/") + "/" + fname if pkg else fname, int(ln), "%s.%s" % (cls.rsplit(".", 1)[-1], meth)))
            elif kind == "python":
                out.append((m.group(1), int(m.group(2)), m.group(3) or ""))
            elif kind == "dotnet":
                out.append((m.group(2), int(m.group(3)), m.group(1)))
            else:
                out.append((m.group(2), int(m.group(3)), m.group(1) or ""))
    return out


def _index(root: Path, names: set) -> dict:
    found = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fns:
            if f in names:
                found.setdefault(f, []).append(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    return found


def locate(root: Path, fr: list, limit: int = 8) -> list:
    """The stack frames that are this project's own code: [(repo path, line, symbol)]."""
    if not fr:
        return []
    names = {h.replace("\\", "/").rsplit("/", 1)[-1] for h, _, _ in fr}
    idx = _index(Path(root), names)
    out, seen = [], set()
    for hint, ln, sym in fr:
        hint = hint.replace("\\", "/")
        cands = idx.get(hint.rsplit("/", 1)[-1]) or []
        parts = hint.split("/")

        def common(c):
            cp, n = c.split("/"), 0
            while n < min(len(cp), len(parts)) and cp[-1 - n] == parts[-1 - n]:
                n += 1
            return n
        best = max(cands, key=common, default=None)
        if not best or (len(parts) > 1 and common(best) < 2 and len(cands) > 1):
            continue
        if (best, ln) not in seen:
            seen.add((best, ln))
            out.append((best, ln, sym))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- tickets

def _open_for(store, pid: int, fp: str) -> dict | None:
    for t in store.tickets(project_id=pid, limit=2000):
        if t["status"] != "closed" and ((t.get("links") or {}).get("alert") or {}).get("fp") == fp:
            return t
    return None


def _opened_last_hour(store, pid: int) -> int:
    since = now()[:13]  # same clock hour is close enough and needs no date arithmetic
    return sum(1 for t in store.tickets(project_id=pid, limit=2000)
               if (t.get("links") or {}).get("alert") and t["created"][:13] >= since)


def receive(P, p: dict, alerts: list, cap: int = 20) -> dict:
    st = P.store
    res = {"opened": [], "updated": [], "resolved": [], "skipped": 0}
    for a in alerts:
        fp = fingerprint(a)
        cur = _open_for(st, p["id"], fp)
        if a.get("status") == "resolved":
            if cur:
                st.event(cur["id"], BY, "comment", "告警已恢复：%s" % a["title"][:120])
                res["resolved"].append(cur["key"])
            continue
        if cur:
            lk = dict(cur.get("links") or {})
            al = dict(lk.get("alert") or {})
            al["count"] = int(al.get("count") or 1) + 1
            last_note = al.get("noted") or al.get("first") or ""
            al["last"] = now()
            if last_note[:15] < now()[:15]:  # ten-minute buckets: a storm of the same alert leaves one comment per bucket
                st.event(cur["id"], BY, "comment", "同一告警又触发（共 %d 次）：%s" % (al["count"], (a.get("text") or a["title"])[:300]))
                al["noted"] = now()
            lk["alert"] = al
            st.update_ticket(cur["id"], BY, links=lk)
            res["updated"].append(cur["key"])
            continue
        if _opened_last_hour(st, p["id"]) >= cap:
            res["skipped"] += 1
            continue
        res["opened"].append(open_ticket(P, p, a, fp)["key"])
    return res


def open_ticket(P, p: dict, a: dict, fp: str) -> dict:
    text = a.get("text") or ""
    own = locate(P.root(p), frames(text))
    body = ["来源：%s%s" % (a.get("source") or "告警", "，服务 " + a["service"] if a.get("service") else ""), "", text.strip()[:6000] if "\n" not in text
            else "```\n%s\n```" % text.strip()[:6000]]
    if own:
        body += ["", "## 堆栈里的项目代码"] + ["- %s:%d %s" % (f, ln, sym) for f, ln, sym in own]
    t = P.store.create_ticket(p["id"], "[告警] " + a["title"][:150], BY, body="\n".join(body), type="bug" if own else "ops",
                              priority=priority(a.get("severity", "")),
                              links={"alert": {"fp": fp, "source": a.get("source", ""), "service": a.get("service", ""), "count": 1, "first": now(), "last": now()}})
    P.store.event(t["id"], BY, "comment", "由%s自动开单%s" % (a.get("source") or "告警", "，堆栈定位到 %d 处项目代码" % len(own) if own else ""))
    P.flow.submit(p, t)
    return t
