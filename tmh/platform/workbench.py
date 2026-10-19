"""The workbench: clients, what they asked, the versions they got, and what the AI is doing right now.

The rest of the platform is organised around tickets. A person who talks to clients all day thinks in other
terms: "王总 asked for three things last week, where are they", "what went out since yesterday, and can the
client click it", "what is the AI doing now". This module answers those questions from what is already there,
and adds only what was missing:

- clients (a table in platform.db) and which conversations, requirement talks and tickets came from each
  (client_links). A ticket also carries links.client. A requirement talk or a group chat linked to a client hands
  the client on to the tickets made from it (sync), so nothing has to be linked twice.
- each requirement's state in plain words: 理解中 / 做着 / 等你看 / 等客户确认 / 已出版本.
- versions per project, from release.py's log, with which requirement and which client each change was for.
- the main line's standing preview: <project>-main, run with the same machinery as a ticket's preview
  (preview.py), restarted after every merge, and a link a client can open (/v/<token>), which shows the version
  and its notes for that client, then lets them into the preview and nothing else of the platform.
- the "today" feed: what waits for the owner, what the AI did since they last looked, what it is doing now, the
  new versions, and the requirement talks still waiting for answers.
"""
from __future__ import annotations

import hashlib
import html as H
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from .errors import ApiError
from .store import REFORM_LIKE, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT DEFAULT '', projects TEXT DEFAULT '[]', notes TEXT DEFAULT '',
  created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS client_links (
  id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, ts TEXT NOT NULL, who TEXT DEFAULT '',
  UNIQUE(kind, ref));
CREATE INDEX IF NOT EXISTS ix_client_links ON client_links(client_id);
"""
KINDS = ("intake", "chat", "ticket")
SHARE_DAYS = 30
MAX_STANDING = int(os.environ.get("TMH_MAX_STANDING") or 2)  # main-line previews running at once, across projects
IDLE_H = float(os.environ.get("TMH_STANDING_IDLE_H") or 12)  # one nobody opened for this long is stopped
DEBOUNCE = 3.0  # seconds: merges in a row restart the main line's preview once, for the last of them
_LOCK = threading.Lock()

# a requirement's state, said the way one says it to a client
STATES = [("talk", "理解中"), ("doing", "做着"), ("you", "等你看"), ("client", "等客户确认"), ("shipped", "已出版本"), ("done", "已完成")]
STATE_LABEL = dict(STATES)


def _db(P) -> None:
    if getattr(P.store, "_wb", False):
        return
    with P.store.lock:
        P.store.db.executescript(SCHEMA)
        P.store.db.commit()
    P.store._wb = True


# ---------------------------------------------------------------- clients

def _client_row(r: dict) -> dict:
    try:
        r["projects"] = json.loads(r.get("projects") or "[]")
    except ValueError:
        r["projects"] = []
    return r


def clients(P) -> list:
    _db(P)
    rows = [_client_row(r) for r in P.store.q("SELECT * FROM clients ORDER BY updated DESC")]
    n = {r["client_id"]: r["n"] for r in P.store.q("SELECT client_id, COUNT(*) n FROM client_links WHERE kind!='noclient' GROUP BY client_id")}
    for r in rows:
        r["links"] = n.get(r["id"], 0)
    return rows


def summary(P) -> list:
    """Every client with how many of their things are owed, waiting on them, and shipped: the 客户 page."""
    rows = clients(P)
    ts = [t for t in _tickets(P) if (t.get("links") or {}).get("client")]
    st = states(P, ts)
    talks = {}
    for s in _talks(P):
        if s.get("state") not in ("confirmed", "dropped"):
            cid = client_of(P, "intake", s["id"])
            if cid:
                talks[cid] = talks.get(cid, 0) + 1
    for r in rows:
        mine = [st[t["key"]]["state"] for t in ts if t["links"]["client"] == r["id"] and not t["links"].get("parent")]
        r["counts"] = {"owed": sum(1 for x in mine if x not in ("shipped", "done")) + talks.get(r["id"], 0), "talk": talks.get(r["id"], 0),
                       "client": mine.count("client"), "you": mine.count("you"), "shipped": mine.count("shipped")}
        last = max([t["updated"] for t in ts if t["links"]["client"] == r["id"]] + [r["updated"]])
        r["last"] = last
    return rows


def client(P, cid) -> dict:
    _db(P)
    try:
        r = P.store.one("SELECT * FROM clients WHERE id=?", (int(cid),))
    except (TypeError, ValueError):
        r = None
    if not r:
        raise ApiError(404, "没有这个客户")
    return _client_row(r)


def _clean(f: dict) -> dict:
    out = {}
    for k, n in (("name", 40), ("contact", 80), ("notes", 2000)):
        if k in f and f[k] is not None:
            if not isinstance(f[k], str):
                raise ApiError(400, "%s 要是文字" % k)
            out[k] = f[k].strip()[:n]
    if "projects" in f and f["projects"] is not None:
        ps = f["projects"]
        if isinstance(ps, str):
            ps = [x for x in re.split(r"[\s,，、]+", ps) if x]
        if not isinstance(ps, list):
            raise ApiError(400, "projects 要是项目代号的列表")
        out["projects"] = sorted({str(x).upper()[:10] for x in ps})
    return out


def create_client(P, f: dict, by: str = "") -> dict:
    _db(P)
    f = _clean(f)
    if not f.get("name"):
        raise ApiError(400, "写上客户的称呼，比如“王总（某某公司）”")
    if P.store.one("SELECT id FROM clients WHERE name=?", (f["name"],)):
        raise ApiError(409, "已经有叫“%s”的客户了" % f["name"])
    for k in f.get("projects") or []:
        P.project(k)
    t = now()
    cid = P.store.x("INSERT INTO clients(name,contact,projects,notes,created,updated) VALUES(?,?,?,?,?,?)",
                    (f["name"], f.get("contact", ""), json.dumps(f.get("projects") or []), f.get("notes", ""), t, t))
    return client(P, cid)


def update_client(P, cid, f: dict) -> dict:
    c = client(P, cid)
    f = _clean(f)
    if "name" in f and not f["name"]:
        raise ApiError(400, "客户的称呼不能是空的")
    if f.get("name") and f["name"] != c["name"] and P.store.one("SELECT id FROM clients WHERE name=?", (f["name"],)):
        raise ApiError(409, "已经有叫“%s”的客户了" % f["name"])
    for k in f.get("projects") or []:
        P.project(k)
    if f:
        if "projects" in f:
            f["projects"] = json.dumps(f["projects"])
        f["updated"] = now()
        P.store.x("UPDATE clients SET %s WHERE id=?" % ",".join(k + "=?" for k in f), list(f.values()) + [c["id"]])
    return client(P, c["id"])


def delete_client(P, cid) -> dict:
    c = client(P, cid)
    for t in P.store.q("SELECT id, links FROM tickets WHERE links LIKE ?", ('%"client": ' + str(c["id"]) + "%",)):
        links = dict(t["links"] or {})
        if links.get("client") == c["id"]:
            links.pop("client")
            P.store.update_ticket(t["id"], "", links=links, drop_client=True)
    P.store.x("DELETE FROM client_links WHERE client_id=?", (c["id"],))
    P.store.x("DELETE FROM clients WHERE id=?", (c["id"],))
    return {"deleted": c["id"]}


def _add_project(P, c: dict, key: str) -> None:
    if key and key not in c["projects"]:
        P.store.x("UPDATE clients SET projects=?, updated=? WHERE id=?", (json.dumps(sorted(c["projects"] + [key])), now(), c["id"]))


def _set_client(P, t: dict, cid, by: str, why: str) -> None:
    """Put a ticket under a client (or none), with a line on its timeline saying so."""
    links = dict(t.get("links") or {})
    old = links.get("client")
    if old == cid:
        return
    if cid:
        links["client"] = cid
    else:
        links.pop("client", None)
    P.store.update_ticket(t["id"], by, links=links, drop_client=not cid)
    names = {c["id"]: c["name"] for c in clients(P)}
    if cid:
        text = "记为客户 %s 提的需求" % names.get(cid, cid) + ("（原先记在 %s 名下）" % names.get(old, old) if old else "") + (("，" + why) if why else "")
    else:
        text = "不再记为客户 %s 提的需求" % names.get(old, old) + (("，" + why) if why else "")
    P.store.event(t["id"], by or "平台", "client", text, {"client": cid, "from": old})


def _keys_of(P, kind: str, ref: str) -> list:
    """The tickets made from a requirement talk or a group conversation."""
    if kind == "intake":
        s = _session(P, ref) or {}
        keys = list(s.get("tickets") or []) + list(s.get("children") or []) + [it.get("ticket") for it in s.get("items") or []]
    elif kind == "chat":
        keys = list((_convs(P).get(ref) or {}).get("tickets") or [])
    else:
        keys = [ref]
    return [k for k in dict.fromkeys(keys) if k]


def _children(P, key: str) -> list:
    return [P.store.ticket(r["id"]) for r in P.store.q("SELECT id, links FROM tickets WHERE links LIKE ?", ('%"parent": "' + key + '"%',))
            if (r["links"] or {}).get("parent") == key]


def link(P, cid, kind: str, ref: str, by: str = "") -> dict:
    """This requirement talk / group conversation / ticket came from this client. A later link replaces an earlier
    one, and moves the tickets already made from that talk or conversation to the new client."""
    c = client(P, cid)
    if kind not in KINDS:
        raise ApiError(400, "只能关联到需求对话（intake）、群聊（chat）或工单（ticket）")
    ref = str(ref or "")
    if kind == "intake":
        from . import intake
        s = intake.load(P.data_dir, ref)
        _add_project(P, c, s.get("project", ""))
    elif kind == "ticket":
        t = P.ticket(ref)
        ref = t["key"]
        _set_client(P, t, c["id"], by, "")
        P.store.x("DELETE FROM client_links WHERE kind='noclient' AND ref=?", (ref,))
        _add_project(P, c, ref.rsplit("-", 1)[0])
    else:
        conv = _convs(P).get(ref)
        if not conv:
            raise ApiError(404, "没有这个群聊对话")
        _add_project(P, c, conv.get("project", ""))
    prev = client_of(P, kind, ref)
    P.store.x("INSERT INTO client_links(client_id,kind,ref,ts,who) VALUES(?,?,?,?,?) "
              "ON CONFLICT(kind, ref) DO UPDATE SET client_id=excluded.client_id, ts=excluded.ts, who=excluded.who",
              (c["id"], kind, ref, now(), by or ""))
    if kind != "ticket" and prev and prev != c["id"]:
        for k in _keys_of(P, kind, ref):
            for t in [P.store.ticket(k)] + _children(P, k):
                if t and (t.get("links") or {}).get("client") == prev:
                    _set_client(P, t, c["id"], by, "整段对话改记到新客户名下")
    sync(P, by)
    return {"client": c["id"], "kind": kind, "ref": ref}


def unlink(P, cid, kind: str, ref: str, by: str = "") -> dict:
    """Take a talk, conversation or ticket off this client. A ticket taken off stays off: sync will not put the
    client back from the talk it came from."""
    c = client(P, cid)
    ref = str(ref or "")
    if kind == "ticket":
        t = P.store.ticket(ref)
        if not t:
            raise ApiError(404, "没有这个工单")
        ref = t["key"]
        row = P.store.one("SELECT client_id FROM client_links WHERE kind='ticket' AND ref=?", (ref,))
        if (t.get("links") or {}).get("client") != c["id"] and not (row and row["client_id"] == c["id"]):
            raise ApiError(409, "%s 没有记在 %s 名下" % (ref, c["name"]))
        P.store.x("DELETE FROM client_links WHERE kind='ticket' AND ref=? AND client_id=?", (ref, c["id"]))
        P.store.x("INSERT INTO client_links(client_id,kind,ref,ts,who) VALUES(0,'noclient',?,?,?) "
                  "ON CONFLICT(kind, ref) DO UPDATE SET ts=excluded.ts, who=excluded.who", (ref, now(), by or ""))
        if (t.get("links") or {}).get("client") == c["id"]:
            _set_client(P, t, None, by, "")
        return {"unlinked": ref}
    if kind not in KINDS:
        raise ApiError(400, "只能取消需求对话（intake）、群聊（chat）或工单（ticket）的关联")
    row = P.store.one("SELECT client_id FROM client_links WHERE kind=? AND ref=?", (kind, ref))
    if not row or row["client_id"] != c["id"]:
        raise ApiError(409, "这段对话没有关联到 %s" % c["name"])
    P.store.x("DELETE FROM client_links WHERE kind=? AND ref=? AND client_id=?", (kind, ref, c["id"]))
    return {"unlinked": ref}


def _links(P, cid=None) -> list:
    _db(P)
    if cid is None:
        return P.store.q("SELECT * FROM client_links WHERE kind!='noclient' ORDER BY id")
    return P.store.q("SELECT * FROM client_links WHERE client_id=? ORDER BY id", (int(cid),))


def client_of(P, kind: str, ref: str):
    _db(P)
    r = P.store.one("SELECT client_id FROM client_links WHERE kind=? AND ref=?", (kind, str(ref)))
    return r["client_id"] if r else None


def _convs(P) -> dict:
    try:
        return json.loads((Path(P.data_dir) / "chat" / "convs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _session(P, sid: str) -> dict | None:
    from . import intake
    try:
        return intake.load(P.data_dir, sid)
    except ApiError:
        return None


def sync(P, by: str = "") -> int:
    """Hand a client on from a requirement talk or a group chat to the tickets made from it, and from a big
    requirement's parent to its children. Runs when something is written (a link, a confirmed talk, a ticket made
    in a group chat or under a parent), never on a read. Only tickets with no client yet and not taken off one by
    hand; returns how many were set."""
    _db(P)
    n = 0
    want = {}
    for r in _links(P):
        if r["kind"] in ("intake", "chat"):
            for k in _keys_of(P, r["kind"], r["ref"]):
                want.setdefault(k, (r["client_id"], "来自%s" % ("需求对话" if r["kind"] == "intake" else "群聊")))
    off = {r["ref"] for r in P.store.q("SELECT ref FROM client_links WHERE kind='noclient'")}
    for t in P.store.q("SELECT id, links FROM tickets WHERE links LIKE '%\"parent\"%'"):
        par = (t["links"] or {}).get("parent")
        if par:
            pt = P.store.ticket(par)
            pc = (pt.get("links") or {}).get("client") if pt else None
            if pc or (pt and pt["key"] in want):
                want.setdefault(P.store.ticket(t["id"])["key"], (pc or want[pt["key"]][0], "跟着大需求 %s" % pt["key"]))
    for k, (cid, why) in want.items():
        if k in off:
            continue
        t = P.store.ticket(k)
        if t and not (t.get("links") or {}).get("client"):
            _set_client(P, t, cid, by or "平台", why)
            n += 1
    return n


# ---------------------------------------------------------------- plain states

def _released(P, tids: list) -> dict:
    """ticket id -> the version it went out in (its latest release event)."""
    if not tids:
        return {}
    rows = P.store.q("SELECT ticket_id, data FROM events WHERE kind='release' AND ticket_id IN (%s) ORDER BY id" % ",".join("?" * len(tids)), tids)
    return {r["ticket_id"]: (r["data"] or {}).get("version", "") for r in rows}


def states(P, tickets: list) -> dict:
    """The shared state for requirements, clients and ticket details: who is actually working or waiting.

    A paused or failed run is not work in progress. A hand-written submission has already finished its synthetic
    run while its real build/review is still busy, so look at the handwork check as well as agent runs.
    """
    if not tickets:
        return {}
    from . import handwork, intake
    from .store import RUN_MODES
    box = P.inbox(None)
    mine = {x["key"]: x for x in box["mine"]}
    others = {x["key"]: x for x in box["others"]}
    ids = [t["id"] for t in tickets]
    rel = _released(P, ids)
    marks = ",".join("?" * len(ids))
    latest = {r["ticket_id"]: r for r in P.store.q(
        "SELECT r.id, r.ticket_id, r.agent, r.mode, r.status FROM runs r JOIN "
        "(SELECT ticket_id, MAX(id) id FROM runs WHERE ticket_id IN (%s) AND mode!='ask' GROUP BY ticket_id) x "
        "ON r.id=x.id" % marks, ids)}
    running = {r["ticket_id"]: r for r in P.store.q(
        "SELECT ticket_id, mode, status FROM runs WHERE ticket_id IN (%s) AND status IN ('queued','running') "
        "AND mode!='ask' ORDER BY id" % marks, ids)}
    checks = {}
    for e in P.store.q("SELECT ticket_id, data FROM events WHERE ticket_id IN (%s) "
                       "AND author='我来写' AND kind='flow' ORDER BY id" % marks, ids):
        data, run = e.get("data") or {}, latest.get(e["ticket_id"], {})
        # Reminders are also flow events. Keep the actual check for the current submission, never an older
        # submission's failure after a new one arrives, nor a reminder in place of the latest verdict.
        if run.get("agent") == "人工" and data.get("run") == run["id"] and data.get("verdict") in ("pass", "fail", "unknown"):
            checks[e["ticket_id"]] = data
    modes = dict(RUN_MODES)
    out = {}
    for t in tickets:
        k, links = t["key"], t.get("links") or {}
        recovery = intake.recovery_state(P, k) if links.get("open_ac") else {}
        v = rel.get(t["id"], "")
        last, live = latest.get(t["id"], {}), running.get(t["id"])
        manual = links.get("handwork") or (links.get("hold") if last.get("agent") == "人工" else "")
        check = checks.get(t["id"], {})
        if t["status"] == "closed":
            s, why = ("shipped", "已出版本 " + v) if v else ("done", "已关闭")
        elif live:
            s, why = "doing", "等待智能体开始%s" % modes.get(live["mode"], "处理") if live["status"] == "queued" else "AI 正在%s" % modes.get(live["mode"], "处理")
            if links.get("hold"):
                why += "；当前步骤结束后暂停"
        elif handwork.busy(k):
            s, why = "doing", "正在构建和审查%s的提交" % (manual or "人工")
        elif links.get("client_change"):
            s, why = "you", "客户的答复改动了已确认的验收标准，等你决定"
        elif recovery.get("status") == "running":
            s, why = "doing", "正在根据已保存答复补全验收标准"
        elif recovery.get("status") in ("failed", "blocked"):
            s, why = "you", "客户答复已保存，再理解未完成，等工程师处理"
        elif links.get("open_ac"):
            s, why = "client", "有 %d 条验收标准要和客户确认" % links["open_ac"]
        elif k in mine and mine[k].get("reason") == "recheck":
            s, why = mine[k].get("state", "you"), mine[k]["label"]
        elif k in others:
            s, why = "client", others[k]["label"]
        elif t["status"] == "verify":
            s, why = "you", mine[k]["label"] if k in mine else "改好了，等你验收"
        elif manual:
            if check.get("verdict") in ("fail", "unknown"):
                s, why = "you", ("提交检查没通过" if check["verdict"] == "fail" else "提交还没检查完") + "，等 %s 处理" % manual
            else:
                s, why = "doing", "%s 在写" % manual
        elif links.get("hold"):
            s, why = "you", "%s 已接管，自动处理暂停" % links["hold"]
        elif (links.get("epic") or {}).get("paused"):
            s, why = "you", "大需求暂停：" + links["epic"]["paused"]
        elif links.get("later"):
            s, why = "doing", links["later"]
        elif k in mine:
            s, why = "you", mine[k]["label"]
        elif last.get("status") in ("failed", "cancelled"):
            s, why = "you", "智能体没跑成，等你处理" if last["status"] == "failed" else "运行已取消，等你继续"
        elif not box.get("auto"):
            s, why = "you", "自动处理已关闭，等人继续"
        elif not box.get("agent"):
            s, why = "you", "没有可用的智能体，等你处理"
        else:
            step, _ = P.flow.next_step(t)
            if step:
                s, why = "doing", "等待自动处理继续"
            else:
                s, why = "you", {"analyze": "分析已完成，等你确认下一步", "plan": "方案已完成，等你决定如何实现"}.get(last.get("mode"), "没有可自动执行的下一步，等你处理")
        out[k] = {"state": s, "label": STATE_LABEL[s], "why": why, "version": v}
    return out


def _tickets(P, project=None, client_id=None) -> list:
    sql, args = "SELECT t.*, p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id WHERE t.links NOT LIKE ?", [REFORM_LIKE]
    if project:
        sql += " AND p.key=?"
        args.append(project)
    sql += " ORDER BY t.updated DESC LIMIT 500"
    from .store import _keyed
    ts = [_keyed(t) for t in P.store.q(sql, args)]
    if client_id is not None:
        ts = [t for t in ts if (t.get("links") or {}).get("client") == client_id]
    return ts


def _said(t: dict) -> str:
    """What the client said, from the ticket body's 原话 section when the requirement talk wrote one."""
    body = t.get("body") or ""
    m = re.search(r"^#{1,4}\s*原话\s*\n+(.+?)(?:\n#{1,4}\s|\Z)", body, re.S | re.M)
    text = (m.group(1) if m else body).strip()
    text = re.sub(r"^\s*#{1,4}\s.*$", "", text, flags=re.M).strip()
    return re.sub(r"\s+", " ", text)[:300] or t["title"]


def _talks(P) -> list:
    """Requirement talks (intake sessions), newest first."""
    from . import intake
    d = intake.idir(P.data_dir)
    out = []
    if d.is_dir():
        for f in d.glob("*.json"):
            if not re.fullmatch(r"[0-9a-f]{12}", f.stem):  # asks.json (the client question links) is not a talk
                continue
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return sorted(out, key=lambda s: s.get("created") or "", reverse=True)


def _open_questions(s: dict) -> int:
    n = sum(len(it.get("questions") or []) for it in s.get("items") or [])
    return n + len(s.get("spec_q") or [])


def requirements(P, project=None) -> dict:
    """Every requirement, in plain-word columns: the talks still being understood, then the tickets."""
    project = (project or "").upper() or None
    cl = {c["id"]: c["name"] for c in clients(P)}
    cols = {k: [] for k, _ in STATES}
    for s in _talks(P):
        if s.get("state") in ("confirmed", "dropped") or (project and s.get("project") != project):
            continue
        cid = client_of(P, "intake", s["id"])
        cols["talk"].append({"kind": "talk", "id": s["id"], "project": s.get("project"), "title": re.sub(r"\s+", " ", s.get("text") or "")[:80],
                             "client": cid, "client_name": cl.get(cid, ""), "since": s.get("created"), "questions": _open_questions(s),
                             "why": "还有 %d 个问题没答" % _open_questions(s) if _open_questions(s) else "理清了，等你确认建单"})
    ts = _tickets(P, project)
    st = states(P, ts)
    for t in ts:
        x = st[t["key"]]
        cid = (t.get("links") or {}).get("client")
        cols[x["state"]].append({"kind": "ticket", "key": t["key"], "title": t["title"], "client": cid, "client_name": cl.get(cid, ""),
                                 "why": x["why"], "version": x["version"], "since": t["updated"], "status": t["status"],
                                 "epic": bool((t.get("links") or {}).get("epic")), "parent": (t.get("links") or {}).get("parent", "")})
    cols["done"] = cols["done"][:30]
    cols["shipped"] = cols["shipped"][:30]
    return {"columns": [{"key": k, "label": lb, "items": cols[k]} for k, lb in STATES]}


def client_view(P, cid) -> dict:
    """One client: what they asked (with dates), each requirement's state, the versions they got, what is owed."""
    c = client(P, cid)
    from . import release
    asked = []
    links = _links(P, c["id"])
    for r in links:
        if r["kind"] == "intake":
            s = _session(P, r["ref"])
            if s:
                asked.append({"kind": "talk", "id": s["id"], "ts": s.get("created"), "text": s.get("text", "")[:600], "project": s.get("project"),
                              "channel": s.get("channel", "web"), "state": s.get("state"), "questions": _open_questions(s)
                              if s.get("state") not in ("confirmed", "dropped") else 0, "tickets": s.get("tickets") or []})
        elif r["kind"] == "chat":
            conv = _convs(P).get(r["ref"]) or {}
            asked.append({"kind": "chat", "id": r["ref"], "ts": conv.get("seen") or r["ts"], "channel": conv.get("channel", ""),
                          "project": conv.get("project"), "text": "群聊 %s：提了 %d 件事" % (conv.get("channel", ""), len(conv.get("tickets") or [])),
                          "tickets": conv.get("tickets") or []})
    ts = _tickets(P, client_id=c["id"])
    st = states(P, ts)
    reqs = []
    from_talk = {k for a in asked for k in a.get("tickets") or []}
    for t in ts:
        x = st[t["key"]]
        reqs.append({"key": t["key"], "title": t["title"], "said": _said(t), "created": t["created"], "updated": t["updated"],
                     "state": x["state"], "label": x["label"], "why": x["why"], "version": x["version"],
                     "parent": (t.get("links") or {}).get("parent", "")})
        if t["key"] not in from_talk:
            asked.append({"kind": "ticket", "id": t["key"], "ts": t["created"], "text": _said(t), "project": t["key"].rsplit("-", 1)[0],
                          "tickets": [t["key"]]})
    asked.sort(key=lambda a: a.get("ts") or "", reverse=True)
    mine = {t["key"] for t in ts}
    versions = []
    for proj in sorted({t["key"].rsplit("-", 1)[0] for t in ts} | set(c["projects"])):
        for r in release.releases(P.data_dir, proj, 200):
            got = [x for x in r.get("tickets") or [] if x.get("key") in mine]
            if got:
                versions.append({"project": proj, "version": r["version"], "ts": r.get("ts"), "items": got, "commit": r.get("commit")})
    versions.sort(key=lambda v: v.get("ts") or "", reverse=True)
    owed = [x for x in reqs if x["state"] not in ("shipped", "done") and not (x["parent"] and x["parent"] in mine)]
    owed += [{"kind": "talk", "key": "", "title": a["text"][:60], "state": "talk", "label": STATE_LABEL["talk"],
              "why": "还有 %d 个问题没答" % a["questions"] if a.get("questions") else "理清了，等你确认建单", "talk": a["id"]}
             for a in asked if a["kind"] == "talk" and a.get("state") not in ("confirmed", "dropped")]
    return {"client": c, "asked": asked[:50], "requirements": reqs, "versions": versions[:30], "owed": owed,
            "counts": {k: sum(1 for x in reqs if x["state"] == k) for k, _ in STATES}}


# ---------------------------------------------------------------- versions and the standing preview

def standing_key(project: str) -> str:
    from .preview import STANDING
    return project.upper() + STANDING


def standing(P, p: dict) -> dict:
    """The main line's preview: whether it runs, which commit, and what to do when it cannot."""
    from . import preview, release
    from .agents import is_git
    key = standing_key(p["key"])
    cmd, ready, mine = preview.command(P.data_dir, p)
    st = preview.status(P.data_dir, key)
    root = Path(p["root"])
    main = release.main_branch(root, P.data_dir, p["key"]) if is_git(root) else ""
    head = ""
    if main:
        from .agents import git
        head = git(root, "rev-parse", "--short", main, check=False).strip()
    fix = ""
    if not mine:
        fix = ("这个项目还没有预览命令。在下面填一条能把它跑起来的命令（用 {port} 表示端口、{prefix} 表示路径前缀），"
               "填好后每出一个版本，这里都会自动换成最新的。" + ("按项目结构猜的是：%s" % cmd if cmd else ""))
    elif not main:
        fix = "找不到主干分支：项目目录不是 git 仓库，或者没有 main / master。在 autoflow.json 的 main 里写上它。"
    return {"key": key, "state": st.get("state", ""), "why": st.get("why", ""), "commit": st.get("commit", ""), "head": head, "main": main,
            "stale": bool(st.get("commit") and head and not head.startswith(st["commit"][:7]) and not st["commit"].startswith(head[:7])),
            "url": "/pv/%s/" % key if st.get("state") == "up" else "", "cmd": cmd, "configured": mine, "fix": fix,
            "started": st.get("started", ""), "tail": st.get("tail", "") if st.get("state") == "failed" else ""}


def _afile(data_dir: Path) -> Path:
    return Path(data_dir) / "versions" / "standing.json"


def _activity(data_dir: Path) -> dict:
    try:
        return json.loads(_afile(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_TOUCHED: dict = {}


def touch(data_dir: Path, key: str, what: str = "opened", at: float | None = None) -> None:
    """Someone opened (or a person started) the main line's preview: it is in use. Opening counts once a minute."""
    at = time.time() if at is None else at
    tk = (str(data_dir), key)
    if what == "opened" and at - _TOUCHED.get(tk, 0) < 60:
        return
    if what == "opened":
        _TOUCHED[tk] = at
    with _LOCK:
        d = _activity(data_dir)
        d.setdefault(key, {})[what] = at
        f = _afile(data_dir)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        os.replace(tmp, f)


def _last_used(data_dir: Path, key: str) -> float:
    a = _activity(data_dir).get(key) or {}
    return max(a.get("opened", 0), a.get("started", 0))


def wanted(P, project: str) -> str:
    """Why the main line's preview should follow each new version ("" when nobody would open it): a client has a
    link that still works, or someone opened or started it lately."""
    if shares(P, project):
        return "有客户链接"
    if time.time() - _last_used(P.data_dir, standing_key(project)) < IDLE_H * 3600:
        return "最近有人打开过"
    return ""


def _live_standing(data_dir: Path) -> list:
    from . import preview
    return [k for k, v in preview._load(data_dir).items() if k.endswith(preview.STANDING) and v.get("state") in ("starting", "up")]


def start_standing(P, p: dict, by: str, person: bool = True) -> dict:
    from . import preview, release
    key = standing_key(p["key"])
    cmd, _, mine = preview.command(P.data_dir, p)
    if not cmd:
        raise ApiError(409, "这个项目还没有预览命令，先填一条能把它跑起来的命令")
    main = release.main_branch(Path(p["root"]), P.data_dir, p["key"])
    if not main:
        raise ApiError(409, "找不到主干分支，在 autoflow.json 的 main 里写上它")
    others = sorted((k for k in _live_standing(P.data_dir) if k != key), key=lambda k: _last_used(P.data_dir, k))
    for old in others[:max(0, len(others) - MAX_STANDING + 1)]:  # the one used least lately makes room
        preview.stop(P, old)
    if person:
        touch(P.data_dir, key, "started")
    r = preview.start(P, p, {"key": key}, main, by or "平台")
    if r.get("state") == "none":
        raise ApiError(409, r["why"])
    return standing(P, p)


_SEQ: dict = {}
_RUN: dict = {}


def on_release(P):
    """After a merge: the standing preview moves to the new version, if the project has a command a person set
    (as a ticket's preview starts by itself only then), previews are on, and someone would open it. Merges in a
    row restart it once, for the last."""
    def fn(p, t, r):
        from . import preview
        if preview.settings(P.data_dir)["preview"] != "auto" or not preview.command(P.data_dir, p)[2]:
            return
        if not wanted(P, p["key"]) and not (t.get("links") or {}).get("client"):  # a client's own change: they will want to open it
            return
        pk = (str(P.data_dir), p["key"])
        with _LOCK:
            _SEQ[pk] = n = _SEQ.get(pk, 0) + 1
            lock = _RUN.setdefault(pk, threading.Lock())

        def go():
            time.sleep(DEBOUNCE)
            if _SEQ.get(pk) != n:  # a newer version came out meanwhile: that one restarts it
                return
            with lock:
                if _SEQ.get(pk) != n:
                    return
                try:
                    start_standing(P, P.project(p["key"]), "新版本 %s" % r.get("version", ""), person=False)
                except Exception as e:  # noqa: BLE001 - the version is out whatever happens to its preview
                    P.store.event(t["id"], "预览", "preview", "当前版本的预览没有换上新版本：%s" % e, {"state": "failed"})
        threading.Thread(target=go, daemon=True).start()
    return fn


def _started_at(data_dir: Path, key: str) -> float:
    from . import preview
    s = (preview._load(data_dir).get(key) or {}).get("started") or ""
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return 0


def reap(P, at: float | None = None) -> list:
    """Stop main-line previews nobody opened for IDLE_H hours. Returns the keys stopped."""
    from . import preview
    at = time.time() if at is None else at
    out = []
    for key in _live_standing(P.data_dir):
        last = _last_used(P.data_dir, key) or _started_at(P.data_dir, key)
        if last and at - last > IDLE_H * 3600:
            preview.stop(P, key)
            out.append(key)
    return out


def _inherit(P, t: dict, who: str) -> None:
    """A ticket made under a parent (a big requirement's child) is for the parent's client."""
    par = (t.get("links") or {}).get("parent")
    if not par or (t.get("links") or {}).get("client"):
        return
    pt = P.store.ticket(par)
    cid = (pt.get("links") or {}).get("client") if pt else None
    if cid:
        _set_client(P, t, cid, who or "平台", "跟着大需求 %s" % pt["key"])


def wire(P) -> None:
    from .. import bots
    P.flow.on_release.append(on_release(P))
    P.store.on_create.append(lambda t, who: _inherit(P, t, who))
    inner = bots.INTAKE
    if inner:
        def intake_then_sync(*a, **kw):  # a group chat's talk made tickets: they get the chat's client now
            out = inner(*a, **kw)
            try:
                sync(P, "群聊")
            except Exception:  # noqa: BLE001 - the reply to the chat matters more
                pass
            return out
        bots.INTAKE = intake_then_sync

    def reaper():
        while True:
            time.sleep(600)
            try:
                reap(P)
            except Exception:  # noqa: BLE001
                pass
    threading.Thread(target=reaper, daemon=True).start()


def versions(P, project: str) -> dict:
    """A project's versions, newest first, each with what it holds in plain words: which requirement, for which client."""
    from . import release
    p = P.project(project)
    cl = {c["id"]: c["name"] for c in clients(P)}
    out = []
    for r in release.releases(P.data_dir, p["key"], 200):
        items = []
        for x in r.get("tickets") or []:
            t = P.store.ticket(x.get("key", ""))
            cid = (t.get("links") or {}).get("client") if t else None
            items.append({"key": x.get("key"), "title": (t or x).get("title", ""), "said": _said(t) if t else "",
                          "type": x.get("type", ""), "client": cid, "client_name": cl.get(cid, "")})
        out.append({"version": r["version"], "ts": r.get("ts"), "commit": r.get("commit"), "tag": r.get("tag"), "by": r.get("by"),
                    "main": r.get("main"), "items": items,
                    "note": "；".join(("给%s：" % i["client_name"] if i["client_name"] else "") + i["title"] for i in items)})
    return {"project": {"key": p["key"], "name": p["name"]}, "versions": out, "standing": standing(P, p),
            "shares": shares(P, p["key"]), "merge": release.settings(P.data_dir)["merge"]}


# ---------------------------------------------------------------- links a client opens: /v/<token>

def _sfile(data_dir: Path) -> Path:
    return Path(data_dir) / "versions" / "shares.json"


def _shares(data_dir: Path) -> dict:
    try:
        return json.loads(_sfile(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_shares(data_dir: Path, d: dict) -> None:
    f = _sfile(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def _sh(token: str) -> str:
    return "v" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:40]


def share(P, project: str, by: str, client_id=None, days: int = SHARE_DAYS) -> dict:
    """A link to the project's current version for a client. Only its hash is kept: the link is shown once."""
    p = P.project(project)
    c = client(P, client_id) if client_id not in (None, "", 0) else None
    try:
        days = max(1, min(int(days or SHARE_DAYS), 180))
    except (TypeError, ValueError):
        raise ApiError(400, "有效天数要是数字")
    token = secrets.token_urlsafe(24)
    rec = {"project": p["key"], "key": standing_key(p["key"]), "client": c["id"] if c else None, "client_name": c["name"] if c else "",
           "by": by, "created": now(), "expires": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + days * 86400)), "revoked": ""}
    with _LOCK:
        d = _shares(P.data_dir)
        d[_sh(token)] = rec
        _save_shares(P.data_dir, d)
    return dict(rec, id=_sh(token)[:12], token=token, path="/v/%s" % token)


def shares(P, project: str) -> list:
    out = []
    for h, r in _shares(P.data_dir).items():
        if r.get("project") == project.upper() and not r.get("revoked") and r["expires"] > now():
            out.append(dict(r, id=h[:12]))
    return sorted(out, key=lambda r: r["created"], reverse=True)


def revoke(P, project: str, sid: str, by: str) -> dict:
    with _LOCK:
        d = _shares(P.data_dir)
        hit = [h for h, r in d.items() if h[:12] == sid and r.get("project") == project.upper()]
        if not hit:
            raise ApiError(404, "没有这个链接")
        d[hit[0]].update(revoked=now(), revoked_by=by)
        _save_shares(P.data_dir, d)
    return {"revoked": sid}


def share_of(data_dir: Path, token: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,64}", token or ""):
        raise ApiError(404, "这个链接不对")
    r = _shares(data_dir).get(_sh(token))
    if not r:
        raise ApiError(404, "这个链接不对，或者已经作废")
    if r.get("revoked") or r["expires"] < now():
        raise ApiError(410, "这个链接已经过期或被收回了，请找发给你的人要一个新的")
    return r


def share_ok(data_dir: Path, key: str, lh: str) -> bool:
    """For preview.granted: the pass came from a version link that is still good, for this preview."""
    r = _shares(data_dir).get(lh)
    return bool(r and r.get("key") == key and not r.get("revoked") and r["expires"] >= now())


def share_page(P, token: str) -> str:
    """What the client sees: the version, what changed for them, and a button into it. Nothing of the platform."""
    from .. import evidence as ev
    from . import preview, release
    r = share_of(P.data_dir, token)
    p = P.project(r["project"])
    st = preview.status(P.data_dir, r["key"])
    rels = release.releases(P.data_dir, p["key"], 50)
    cur = rels[0] if rels else None
    mine = []
    others = 0
    for rr in rels[:10]:
        for x in rr.get("tickets") or []:
            t = P.store.ticket(x.get("key", ""))
            if not r.get("client") or not t or (t.get("links") or {}).get("client") != r["client"]:
                others += 1
                continue
            mine.append((rr["version"], rr.get("ts", "")[:10], x.get("title", "")))
    E = H.escape
    up = st.get("state") == "up"
    btn = ('<p><a class="go" href="/v/%s/open">打开现在的版本 →</a></p>' % E(token) if up else
           '<p class="sub">%s</p>' % ("正在换上最新的版本，过一两分钟刷新这个页面。" if st.get("state") == "starting" else
                                    "现在的版本暂时没有在运行，已经告诉负责的人了。"))
    lis = "".join("<li><b>%s</b> %s <span class=sub>%s</span></li>" % (E(v), E(title), E(d)) for v, title, d in mine[:12])
    body = ("<h1>%s · 现在的版本</h1>" % E(p["name"]) +
            ("<p class=sub>版本 %s · %s 出的</p>" % (E(cur["version"]), E((cur.get("ts") or "")[:16])) if cur else "<p class=sub>还没有出过版本</p>") +
            btn + ("<h2>%s这几版做了什么</h2><ul>%s</ul>" % ("给您" if r.get("client") else "", lis) if lis else "") +
            (("<p class=sub>以及其他客户的 %d 项改进。</p>" if r.get("client") else "<p>本版包含 %d 项改进。</p>") % others if others else "") +
            "<p class=sub>这个链接 %s 前有效。试用时有问题，直接告诉我们。</p>" % E(r["expires"][:10]))
    css = (".go{display:inline-block;background:#1677FF;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-size:16px}"
           ".sub{color:#666;font-size:13px}ul{padding-left:18px}li{margin:6px 0}")
    return ev.page("%s · 现在的版本" % p["name"], body, css)


def message_page(msg: str) -> str:
    from .. import evidence as ev
    return ev.page("现在的版本", "<h1>现在的版本</h1><p>%s</p>" % H.escape(msg))


def share_grant(P, token: str) -> tuple[str, str]:
    """(preview key, pass) for a good link: the pass lasts as long as the link."""
    from . import preview
    r = share_of(P.data_dir, token)
    touch(P.data_dir, r["key"])
    until = time.mktime(time.strptime(r["expires"][:19], "%Y-%m-%d %H:%M:%S"))
    return r["key"], preview.grant(P.data_dir, r["key"], _sh(token), until)


# ---------------------------------------------------------------- today

MACHINE_KINDS = ("release", "adopt", "conflict")


_TODAY: dict = {}
TODAY_TTL = 4.0  # seconds; every open page asks every few seconds


def today(P, since: str = "") -> dict:
    """One screen: what needs the owner, what the AI did since `since`, what it is doing now, new versions, and the
    requirement talks with questions still open. Reads only. The same answer is kept a few seconds while nothing
    new was written to any ticket's timeline and no run started or ended."""
    since = since if re.fullmatch(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d(:\d\d)?", since or "") else ""
    since = since.replace("T", " ")
    ev = P.store.one("SELECT MAX(id) m FROM events") or {}
    ru = P.store.one("SELECT MAX(id) m, COUNT(*) n FROM runs WHERE status IN ('queued','running')") or {}
    mark = (ev.get("m"), ru.get("m"), ru.get("n"))
    ck = (str(P.data_dir), since)
    hit = _TODAY.get(ck)
    if hit and hit[1] == mark and time.time() - hit[0] < TODAY_TTL:
        return hit[2]
    out = _today(P, since)
    if len(_TODAY) > 64:
        _TODAY.clear()
    _TODAY[ck] = (time.time(), mark, out)
    return out


def _today(P, since: str) -> dict:
    from . import preview, release
    st = P.store
    cl = {c["id"]: c["name"] for c in clients(P)}
    keys = {p["id"]: p["key"] for p in st.projects()}
    tickets = {}

    def tk(tid):
        if tid not in tickets:
            tickets[tid] = st.ticket(tid) if tid else None
        return tickets[tid]
    now_ = []
    for r in st.q("SELECT id, ticket_id, project_id, agent, mode, status, created, started, author FROM runs "
                  "WHERE status IN ('queued','running') AND mode!='ask' ORDER BY id"):
        t = tk(r["ticket_id"])
        now_.append({"run": r["id"], "project": keys.get(r["project_id"], ""), "key": t["key"] if t else "", "title": t["title"] if t else "",
                     "client_name": cl.get((t.get("links") or {}).get("client")) if t else "", "mode": r["mode"], "status": r["status"],
                     "agent": r["agent"], "since": r["started"] or r["created"], "auto": r["author"] == P.flow.BY})
    from . import handwork
    box = P.inbox(None)
    did = []
    if since:
        rows = st.q("SELECT e.*, t.title, t.num, t.project_id, t.links FROM events e JOIN tickets t ON t.id=e.ticket_id WHERE e.ts>? "
                    "AND (e.kind IN ('release','adopt','conflict') OR (e.kind='status' AND (e.data LIKE '%\"to\": \"verify\"%' OR e.data LIKE '%\"to\": \"closed\"%'))) "
                    "ORDER BY e.id DESC LIMIT 40", (since,))
        for e in rows:
            links = json.loads(e["links"] or "{}") if isinstance(e["links"], str) else (e["links"] or {})
            did.append({"key": "%s-%d" % (keys.get(e["project_id"], "?"), e["num"]), "title": e["title"], "ts": e["ts"], "kind": e["kind"],
                        "text": e["body"], "by": e["author"], "client_name": cl.get(links.get("client"), "")})
    vers = []
    from . import preview
    for p in st.projects():
        up = preview.status(P.data_dir, standing_key(p["key"])).get("state") == "up"
        for r in release.releases(P.data_dir, p["key"], 20):
            if since and (r.get("ts") or "") <= since:
                break
            vers.append({"project": p["key"], "version": r["version"], "ts": r.get("ts"),
                         "items": [{"key": x.get("key"), "title": x.get("title")} for x in r.get("tickets") or []],
                         "standing": "/pv/%s/" % standing_key(p["key"]) if up else ""})
    vers.sort(key=lambda v: v.get("ts") or "", reverse=True)
    if not since:
        vers = vers[:5]
    talks = []
    for s in _talks(P):
        if s.get("state") in ("confirmed", "dropped"):
            continue
        cid = client_of(P, "intake", s["id"])
        talks.append({"id": s["id"], "project": s.get("project"), "text": re.sub(r"\s+", " ", s.get("text") or "")[:120], "since": s.get("updated") or s.get("created"),
                      "questions": _open_questions(s), "client": cid, "client_name": cl.get(cid, ""), "channel": s.get("channel", "web"),
                      "state": s.get("state")})
    waiting_ac = []
    for t in st.q("SELECT t.id FROM tickets t WHERE t.status!='closed' AND t.links LIKE '%\"open_ac\"%'"):
        x = tk(t["id"])
        if x and (x.get("links") or {}).get("open_ac"):
            waiting_ac.append({"key": x["key"], "title": x["title"], "open": x["links"]["open_ac"], "client_name": cl.get(x["links"].get("client"), "")})
    for x in box["mine"] + box["others"]:
        t = st.ticket(x["key"])
        x["client_name"] = cl.get((t.get("links") or {}).get("client"), "") if t else ""
    failed = []
    for p in st.projects():
        key = standing_key(p["key"])
        s_ = preview.status(P.data_dir, key)
        if s_.get("state") == "failed":
            failed.append({"project": p["key"], "name": p["name"], "key": key, "why": s_.get("why", ""), "since": s_.get("started", "")})
    return {"now": now_, "mine": box["mine"], "others": box["others"], "did": did, "versions": vers, "talks": talks, "open_ac": waiting_ac,
            "standing_failed": failed,
            "auto": box["auto"], "agent": box["agent"], "since": since, "server_time": now(),
            "handwork": handwork.settings(P.data_dir)["handwork"]}
