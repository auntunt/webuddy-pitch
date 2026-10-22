"""Platform data: projects, tickets, their timeline and agent runs (one SQLite file).

The platform is a peer of Jira / 禅道: it owns its own tickets. A ticket can
also mirror one in an external tool (`external` = {"system", "key", "url"}) so
teams that keep Jira as the system of record can still work here.
"""
from __future__ import annotations

import json
import threading
import time
import sqlite3
from pathlib import Path

from ..fsutil import open_db

STATUSES = [("new", "新建"), ("analyzing", "分析中"), ("confirm", "待确认"), ("doing", "处理中"), ("verify", "待验证"), ("closed", "已关闭")]
TYPES = [("bug", "缺陷"), ("feature", "需求"), ("change", "变更"), ("question", "咨询"), ("ops", "运维")]
PRIORITIES = [("urgent", "紧急"), ("high", "高"), ("normal", "中"), ("low", "低")]
RUN_MODES = [("analyze", "分析定位"), ("plan", "修改方案"), ("fix", "修改代码"), ("kb", "撰写知识页"), ("ask", "助手问答"), ("understand", "理解需求")]
RUN_STATES = ("queued", "running", "done", "failed", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, name TEXT NOT NULL, root TEXT NOT NULL,
  description TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, num INTEGER NOT NULL, title TEXT NOT NULL,
  body TEXT DEFAULT '', type TEXT DEFAULT 'bug', status TEXT DEFAULT 'new', priority TEXT DEFAULT 'normal',
  assignee TEXT DEFAULT '', reporter TEXT DEFAULT '', labels TEXT DEFAULT '[]', links TEXT DEFAULT '{}',
  external TEXT DEFAULT '{}', created TEXT NOT NULL, updated TEXT NOT NULL,
  UNIQUE(project_id, num));
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, ts TEXT NOT NULL, author TEXT DEFAULT '',
  kind TEXT NOT NULL, body TEXT DEFAULT '', data TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, ticket_id INTEGER, project_id INTEGER NOT NULL, agent TEXT NOT NULL, mode TEXT NOT NULL,
  status TEXT NOT NULL, author TEXT DEFAULT '', created TEXT NOT NULL, started TEXT DEFAULT '', ended TEXT DEFAULT '',
  prompt TEXT DEFAULT '', output TEXT DEFAULT '', result TEXT DEFAULT '', diff TEXT DEFAULT '',
  exit_code INTEGER, workdir TEXT DEFAULT '', target TEXT DEFAULT '', decision TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS points (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, ts TEXT NOT NULL, delta INTEGER NOT NULL,
  reason TEXT DEFAULT '', run_id INTEGER, ticket_id INTEGER, author TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS chats (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, ticket_id INTEGER, ts TEXT NOT NULL, role TEXT NOT NULL,
  author TEXT DEFAULT '', body TEXT DEFAULT '', data TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS matters (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, title TEXT NOT NULL, summary TEXT DEFAULT '', ticket_id INTEGER,
  created_by TEXT DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, matter_id INTEGER, ticket_id INTEGER, kind TEXT NOT NULL DEFAULT 'consult',
  title TEXT NOT NULL, created_by TEXT DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL, archived_at TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS idem (key TEXT PRIMARY KEY, result TEXT NOT NULL, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comment_receipts (
  ticket_id INTEGER NOT NULL, author TEXT NOT NULL, request_id TEXT NOT NULL,
  body TEXT NOT NULL, event_id INTEGER NOT NULL, ts TEXT NOT NULL,
  PRIMARY KEY(ticket_id, author, request_id));
CREATE INDEX IF NOT EXISTS ix_sessions ON sessions(project_id, created_by);
CREATE INDEX IF NOT EXISTS ix_points_project ON points(project_id);
CREATE INDEX IF NOT EXISTS ix_chats ON chats(project_id, ticket_id);
CREATE INDEX IF NOT EXISTS ix_tickets_project ON tickets(project_id, status);
CREATE INDEX IF NOT EXISTS ix_events_ticket ON events(ticket_id);
CREATE INDEX IF NOT EXISTS ix_runs_ticket ON runs(ticket_id);
"""

REFORM_LIKE = '%"reform":%'  # tickets released by a reform plan carry links.reform
JSON_COLS = {"labels", "links", "external", "data"}
SESSION_KINDS = [("consult", "项目咨询"), ("matter", "维护事项"), ("ticket", "关联工单")]
# columns added after the first release; older platform.db files get them on open
LATER_COLS = {"chats": [("session_id", "INTEGER")], "runs": [("session_id", "INTEGER"), ("batch", "TEXT DEFAULT ''"), ("model", "TEXT DEFAULT ''"), ("retry_of", "INTEGER")]}


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = open_db(self.path, check_same_thread=False)  # shared by the server's threads, guarded by self.lock
        self.db.row_factory = _row
        self.on_status = []  # fn(ticket, old, new, author) after a status change; the platform packs evidence on 待验证
        self.on_create = []  # fn(ticket, author) after a ticket is made
        with self.lock:
            self.db.executescript(SCHEMA)
            for table, cols in LATER_COLS.items():
                have = {r["name"] for r in self.db.execute("PRAGMA table_info(%s)" % table).fetchall()}
                for name, typ in cols:
                    if name not in have:
                        self.db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, typ))
            self.db.execute("CREATE INDEX IF NOT EXISTS ix_chats_session ON chats(session_id)")
            self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_runs_retry_of ON runs(retry_of) WHERE retry_of IS NOT NULL")
            # adopting a code change used to be logged as "accept", the same kind as passing acceptance
            self.db.execute("UPDATE events SET kind='adopt' WHERE kind='accept' AND data LIKE '%\"branch\"%'")
            self.db.commit()
        self._migrate_chats()
        from .project_library import schema as library_schema
        library_schema(self)
        from .learning import schema as learning_schema
        learning_schema(self)
        from .learning_runs import schema as learning_runs_schema
        learning_runs_schema(self)

    def _migrate_chats(self) -> None:
        """Assistant messages from before sessions existed: one session per ticket, one '旧版未分类会话' per project.

        Nothing is guessed from message content; the source ids stay on the rows."""
        groups = self.q("SELECT project_id, ticket_id, MIN(ts) t0, MAX(ts) t1, MIN(author) who FROM chats WHERE session_id IS NULL GROUP BY project_id, ticket_id")
        for g in groups:
            if g["ticket_id"]:
                t = self.ticket(g["ticket_id"])
                kind, title = "ticket", "%s 讨论" % (t["key"] if t else "工单")
            else:
                kind, title = "consult", "旧版未分类会话"
            sid = self.x("INSERT INTO sessions(project_id,ticket_id,kind,title,created_by,created,updated) VALUES(?,?,?,?,?,?,?)",
                         (g["project_id"], g["ticket_id"], kind, title, "", g["t0"], g["t1"]))
            if g["ticket_id"]:
                self.x("UPDATE chats SET session_id=? WHERE session_id IS NULL AND project_id=? AND ticket_id=?", (sid, g["project_id"], g["ticket_id"]))
            else:
                self.x("UPDATE chats SET session_id=? WHERE session_id IS NULL AND project_id=? AND ticket_id IS NULL", (sid, g["project_id"]))

    # ---- helpers
    def q(self, sql: str, args=()) -> list:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def one(self, sql: str, args=()):
        r = self.q(sql, args)
        return r[0] if r else None

    def x(self, sql: str, args=()) -> int:
        with self.lock:
            try:
                cur = self.db.execute(sql, args)
                self.db.commit()
                return cur.lastrowid
            except sqlite3.Error:
                self.db.rollback()
                raise

    # ---- projects
    def projects(self) -> list:
        return self.q("SELECT * FROM projects ORDER BY id")

    def project(self, pid) -> dict | None:
        return self.one("SELECT * FROM projects WHERE id=? OR key=?", (pid, str(pid).upper()))

    def add_project(self, key: str, name: str, root: str, description: str = "", *, roles=None, workflow='development') -> dict:
        from .project_library import validate_profile
        roles = [] if roles is None else roles
        validate_profile(roles, workflow)
        key = key.upper()
        if not key.isalnum() or not key[0].isalpha() or len(key) > 10:
            raise ValueError("项目代号只能是字母开头的字母数字，最多 10 位，例如 TOG")
        if not Path(root).is_dir():
            raise ValueError("目录不存在：%s" % root)
        if self.project(key):
            raise ValueError("项目代号已存在：%s" % key)
        root = str(Path(root).resolve())
        with self.lock, self.db:
            pid = self.db.execute("INSERT INTO projects(key,name,root,description,created) VALUES(?,?,?,?,?)",
                                  (key, name or key, root, description, now())).lastrowid
            self.db.execute('INSERT INTO project_profiles VALUES(?,?,?)', (pid, json.dumps(roles), workflow))
            self.db.execute('INSERT INTO project_sources(project_id,root,label,created) VALUES(?,?,?,?)', (pid, root, '主仓库', now()))
        return self.project(pid)

    # ---- tickets
    def tickets(self, project_id=None, status=None, text=None, assignee=None, limit=500, svc=None) -> list:
        """`svc` picks a service: "reform" for pieces of reform plans, "ops" for everything else."""
        sql, args = "SELECT t.*, p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id WHERE 1=1", []
        if svc in ("ops", "reform"):
            sql += " AND t.links %s ?" % ("LIKE" if svc == "reform" else "NOT LIKE")
            args.append(REFORM_LIKE)
        if project_id:
            sql += " AND t.project_id=?"
            args.append(project_id)
        if status:
            sql += " AND t.status=?"
            args.append(status)
        if assignee:
            sql += " AND t.assignee=?"
            args.append(assignee)
        if text:
            sql += " AND (t.title LIKE ? OR t.body LIKE ?)"
            args += ["%" + text + "%"] * 2
        sql += " ORDER BY t.updated DESC LIMIT ?"
        args.append(limit)
        return [_keyed(t) for t in self.q(sql, args)]

    def ticket(self, tid) -> dict | None:
        """By numeric id or by key like TOG-12."""
        if isinstance(tid, str) and "-" in tid:
            k, n = tid.upper().rsplit("-", 1)
            if not n.isdigit():  # OA-main: the main line's standing preview, not a ticket
                return None
            t = self.one("SELECT t.*, p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id WHERE p.key=? AND t.num=?", (k, int(n)))
        else:
            t = self.one("SELECT t.*, p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id WHERE t.id=?", (int(tid),))
        return _keyed(t) if t else None

    def create_ticket(self, project_id: int, title: str, author: str = "", **f) -> dict:
        if not (title or "").strip():
            raise ValueError("标题不能为空")
        with self.lock:
            n = (self.one("SELECT MAX(num) AS m FROM tickets WHERE project_id=?", (project_id,)) or {}).get("m") or 0
            ts = now()
            tid = self.x("INSERT INTO tickets(project_id,num,title,body,type,status,priority,assignee,reporter,labels,links,external,created,updated)"
                         " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (project_id, n + 1, title.strip(), f.get("body", ""), _pick(f.get("type"), TYPES, "bug"), "new",
                          _pick(f.get("priority"), PRIORITIES, "normal"), f.get("assignee", ""), author,
                          json.dumps(f.get("labels") or [], ensure_ascii=False), json.dumps(f.get("links") or {}, ensure_ascii=False),
                          json.dumps(f.get("external") or {}, ensure_ascii=False), ts, ts))
        self.event(tid, author, "created", "创建工单")
        t = self.ticket(tid)
        for fn in self.on_create:
            fn(t, author)
        return t

    def update_ticket(self, tid: int, author: str = "", **f) -> dict:
        t = self.ticket(tid)
        if not t:
            raise KeyError(tid)
        sets, args = [], []
        labels = dict(STATUSES)
        for k in ("title", "body", "type", "status", "priority", "assignee", "labels", "links", "external"):
            if k not in f or f[k] is None:
                continue
            v = f[k]
            if k == "links" and isinstance(v, dict) and (t.get("links") or {}).get("client") and "client" not in v and not f.get("drop_client"):
                v = dict(v, client=t["links"]["client"])  # written from an older copy of the ticket: whose it is stays
            if k == "status":
                v = _pick(v, STATUSES, None)
                if not v:
                    raise ValueError("未知状态：%s" % f[k])
            if k == "type":
                v = _pick(v, TYPES, t["type"])
            if k == "priority":
                v = _pick(v, PRIORITIES, t["priority"])
            if v == t.get(k):
                continue
            if k == "status":
                self.event(tid, author, "status", "%s → %s" % (labels.get(t["status"], t["status"]), labels[v]), {"from": t["status"], "to": v})
            elif k == "assignee":
                self.event(tid, author, "assign", "指派给 %s" % (v or "（无人）"))
            elif k in ("title", "body", "priority", "type"):
                self.event(tid, author, "edit", "修改了%s" % {"title": "标题", "body": "描述", "priority": "优先级", "type": "类型"}[k])
            sets.append(k + "=?")
            args.append(json.dumps(v, ensure_ascii=False) if k in JSON_COLS else v)
        if sets:
            sets.append("updated=?")
            args += [now(), tid]
            self.x("UPDATE tickets SET %s WHERE id=?" % ",".join(sets), args)
        after = self.ticket(tid)
        if after["status"] != t["status"]:
            for fn in self.on_status:
                fn(after, t["status"], after["status"], author)
        return after

    def touch(self, tid: int) -> None:
        self.x("UPDATE tickets SET updated=? WHERE id=?", (now(), tid))

    # ---- timeline
    def event(self, tid: int, author: str, kind: str, body: str = "", data: dict | None = None) -> int:
        return self.x("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                      (tid, now(), author or "", kind, body or "", json.dumps(data or {}, ensure_ascii=False)))

    def comment(self, tid: int, author: str, body: str, request_id: str | None = None) -> dict:
        """Atomically append a comment, touch its ticket, and seal an optional retry receipt.

        SQLite's writer lock also serializes separate server processes. A retry never
        changes the timeline or timestamp. Keep full text here, including whitespace:
        same request ID with even a small text change is a conflict, not a new comment.
        """
        author = author or ""
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                if request_id is not None:
                    receipt = self.db.execute(
                        "SELECT body,event_id FROM comment_receipts WHERE ticket_id=? AND author=? AND request_id=?",
                        (tid, author, request_id)).fetchone()
                    if receipt:
                        if receipt["body"] != body:
                            raise ValueError("这次评论已用不同内容发送，原评论已保留；请核对后作为新评论发送")
                        self.db.commit()
                        return {"ok": True, "event_id": receipt["event_id"], "request_id": request_id}
                ts = now()
                event_id = self.db.execute(
                    "INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                    (tid, ts, author, "comment", body, "{}")).lastrowid
                self.db.execute("UPDATE tickets SET updated=? WHERE id=?", (ts, tid))
                if request_id is not None:
                    self.db.execute(
                        "INSERT INTO comment_receipts(ticket_id,author,request_id,body,event_id,ts) VALUES(?,?,?,?,?,?)",
                        (tid, author, request_id, body, event_id, ts))
                self.db.commit()
                return ({"ok": True, "event_id": event_id, "request_id": request_id}
                        if request_id is not None else {"ok": True})
            except BaseException:
                self.db.rollback()
                raise

    def events(self, tid: int) -> list:
        return self.q("SELECT * FROM events WHERE ticket_id=? ORDER BY id", (tid,))

    # ---- runs
    def create_run(self, project_id: int, ticket_id, agent: str, mode: str, author: str, prompt: str, target: str = "",
                   session_id=None, batch: str = "", model: str = "", retry_of=None, *, expected_root=None, reference_inputs=None) -> dict:
        from .project_library import require_development, bindings, _write_run_inputs
        try:
            # Only eligibility and registration share the writer transaction.
            # Prompt preparation stays concurrent; UNIQUE retry_of still decides
            # the winner across independent Runner / Store instances.
            with self.lock, self.db:
                self.db.execute("BEGIN IMMEDIATE")
                require_development(self, {"id": project_id})
                project = self.project(project_id)
                if expected_root is not None and project['root'] != expected_root:
                    raise ValueError('准备运行期间项目工作区已变化，请重新启动任务')
                current_inputs = bindings(self, project)
                if reference_inputs is not None and reference_inputs != current_inputs:
                    raise ValueError('参考知识在登记期间已变化，请重新启动任务')
                if any(not value['available'] for value in current_inputs):
                    raise ValueError('参考知识授权已变化，请先处理不可用引用')
                rid = self.db.execute("INSERT INTO runs(ticket_id,project_id,agent,mode,status,author,created,prompt,target,session_id,batch,model,retry_of) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                      (ticket_id, project_id, agent, mode, "queued", author, now(), prompt, target, session_id, batch or "", model or "", retry_of)).lastrowid
                _write_run_inputs(self, project, rid, current_inputs)
        except sqlite3.IntegrityError:
            successor = self.one("SELECT id FROM runs WHERE retry_of=?", (retry_of,)) if retry_of is not None else None
            if successor:
                raise ValueError("已创建后续运行 #%s，请查看该运行" % successor["id"]) from None
            raise
        return self.run(rid)

    def run(self, rid: int) -> dict | None:
        return self.one("SELECT * FROM runs WHERE id=?", (rid,))

    def runs(self, ticket_id=None, project_id=None, limit=100) -> list:
        sql, args = "SELECT id,ticket_id,project_id,agent,mode,status,author,created,started,ended,exit_code,target,decision,result,session_id,batch,model FROM runs WHERE 1=1", []
        if ticket_id:
            sql += " AND ticket_id=?"
            args.append(ticket_id)
        if project_id:
            sql += " AND project_id=?"
            args.append(project_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return self.q(sql, args)

    def update_run(self, rid: int, **f) -> None:
        if not f:
            return
        self.x("UPDATE runs SET %s WHERE id=?" % ",".join(k + "=?" for k in f), list(f.values()) + [rid])

    def append_output(self, rid: int, text: str) -> None:
        self.x("UPDATE runs SET output = output || ? WHERE id=?", (text, rid))

    # ---- points (usage shown in the UI; no payment behind it yet)
    def points_balance(self, project_id: int) -> int:
        r = self.one("SELECT COALESCE(SUM(delta),0) b, COUNT(*) n FROM points WHERE project_id=?", (project_id,))
        return int(r["b"]), int(r["n"])

    def add_points(self, project_id: int, delta: int, reason: str, author: str = "", run_id=None, ticket_id=None) -> int:
        return self.x("INSERT INTO points(project_id,ts,delta,reason,run_id,ticket_id,author) VALUES(?,?,?,?,?,?,?)",
                      (project_id, now(), int(delta), reason, run_id, ticket_id, author))

    def points_log(self, project_id: int, limit: int = 50) -> list:
        return self.q("SELECT * FROM points WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))

    def run_points(self, run_ids: list) -> dict:
        if not run_ids:
            return {}
        rows = self.q("SELECT run_id, -SUM(delta) n FROM points WHERE run_id IN (%s) GROUP BY run_id" % ",".join("?" * len(run_ids)), run_ids)
        return {r["run_id"]: r["n"] for r in rows}

    # ---- assistant sessions: each one keeps its own messages and model context
    def session_create(self, project_id: int, kind: str, title: str, author: str, matter_id=None, ticket_id=None) -> dict:
        if kind not in dict(SESSION_KINDS):
            raise ValueError("未知的会话类型：%s" % kind)
        t = now()
        sid = self.x("INSERT INTO sessions(project_id,matter_id,ticket_id,kind,title,created_by,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                     (project_id, matter_id, ticket_id, kind, (title or "新会话").strip()[:60], author or "", t, t))
        return self.session(sid)

    def session(self, sid) -> dict | None:
        return self.one("SELECT * FROM sessions WHERE id=?", (sid,))

    def sessions(self, project_id: int, author: str = "") -> list:
        """A person's sessions in one project (migrated ones have no owner and show for everyone), newest first."""
        return self.q("""SELECT s.*, (SELECT COUNT(*) FROM chats c WHERE c.session_id=s.id) n,
                 (SELECT COUNT(*) FROM runs r WHERE r.session_id=s.id AND r.status IN ('queued','running')) running
                 FROM sessions s WHERE s.project_id=? AND (s.created_by=? OR s.created_by='') ORDER BY s.updated DESC LIMIT 300""",
                      (project_id, author or ""))

    def session_update(self, sid: int, **f) -> dict:
        f = {k: v for k, v in f.items() if k in ("title", "archived_at", "ticket_id", "matter_id", "kind")}
        if f:
            f["updated"] = now() if "archived_at" not in f else self.session(sid)["updated"]
            self.x("UPDATE sessions SET %s WHERE id=?" % ",".join(k + "=?" for k in f), list(f.values()) + [sid])
        return self.session(sid)

    def touch_session(self, sid: int) -> None:
        self.x("UPDATE sessions SET updated=? WHERE id=?", (now(), sid))

    def matter_create(self, project_id: int, title: str, author: str, summary: str = "") -> dict:
        mid = self.x("INSERT INTO matters(project_id,title,summary,created_by,created) VALUES(?,?,?,?,?)",
                     (project_id, (title or "维护事项").strip()[:60], summary or "", author or "", now()))
        return self.matter(mid)

    def matter(self, mid) -> dict | None:
        return self.one("SELECT * FROM matters WHERE id=?", (mid,))

    def matters(self, project_id: int) -> list:
        return self.q("SELECT * FROM matters WHERE project_id=? ORDER BY id DESC", (project_id,))

    def matter_update(self, mid: int, **f) -> None:
        f = {k: v for k, v in f.items() if k in ("title", "summary", "ticket_id")}
        if f:
            self.x("UPDATE matters SET %s WHERE id=?" % ",".join(k + "=?" for k in f), list(f.values()) + [mid])

    # ---- idempotency: a repeated submit with the same key returns the first result
    def idem_get(self, key: str):
        r = self.one("SELECT result FROM idem WHERE key=?", (key,))
        return json.loads(r["result"]) if r else None

    def idem_put(self, key: str, result) -> None:
        self.x("INSERT OR IGNORE INTO idem(key,result,ts) VALUES(?,?,?)", (key, json.dumps(result, ensure_ascii=False), now()))

    # ---- assistant messages
    def chat_add(self, project_id: int, ticket_id, role: str, author: str, body: str, data: dict | None = None, session_id=None) -> int:
        cid = self.x("INSERT INTO chats(project_id,ticket_id,ts,role,author,body,data,session_id) VALUES(?,?,?,?,?,?,?,?)",
                     (project_id, ticket_id, now(), role, author or "", body or "", json.dumps(data or {}, ensure_ascii=False), session_id))
        if session_id:
            self.touch_session(session_id)
        return cid

    def session_chats(self, sid: int, limit: int = 60) -> list:
        return self.q("SELECT * FROM chats WHERE session_id=? ORDER BY id DESC LIMIT ?", (sid, limit))[::-1]

    def chat_update(self, cid: int, body: str, data: dict) -> None:
        self.x("UPDATE chats SET body=?, data=? WHERE id=?", (body, json.dumps(data, ensure_ascii=False), cid))

    def chats(self, project_id: int, ticket_id=None, limit: int = 40) -> list:
        if ticket_id:
            rows = self.q("SELECT * FROM chats WHERE project_id=? AND ticket_id=? ORDER BY id DESC LIMIT ?", (project_id, ticket_id, limit))
        else:
            rows = self.q("SELECT * FROM chats WHERE project_id=? AND ticket_id IS NULL ORDER BY id DESC LIMIT ?", (project_id, limit))
        return rows[::-1]

    # ---- dashboard
    def stats(self, project_id=None) -> dict:
        w, a = ("WHERE project_id=?", (project_id,)) if project_id else ("", ())
        by_status = {r["status"]: r["n"] for r in self.q("SELECT status, COUNT(*) n FROM tickets %s GROUP BY status" % w, a)}
        by_type = {r["type"]: r["n"] for r in self.q("SELECT type, COUNT(*) n FROM tickets %s GROUP BY type" % w, a)}
        by_pri = {r["priority"]: r["n"] for r in self.q("SELECT priority, COUNT(*) n FROM tickets %s AND status!='closed' GROUP BY priority" % (w or "WHERE 1=1"), a)}
        runs = {r["status"]: r["n"] for r in self.q("SELECT status, COUNT(*) n FROM runs %s GROUP BY status" % w, a)}
        days = self.q("SELECT substr(created,1,10) d, COUNT(*) n FROM tickets %s GROUP BY d ORDER BY d DESC LIMIT 14" % w, a)
        closed = self.q("SELECT substr(updated,1,10) d, COUNT(*) n FROM tickets %s %s status='closed' GROUP BY d ORDER BY d DESC LIMIT 14"
                        % (w, "AND" if w else "WHERE"), a)
        return {"by_status": by_status, "by_type": by_type, "open_by_priority": by_pri, "runs": runs,
                "created_by_day": [[r["d"], r["n"]] for r in days][::-1], "closed_by_day": [[r["d"], r["n"]] for r in closed][::-1]}


def _row(cur, row):
    d = {c[0]: v for c, v in zip(cur.description, row)}
    for k in JSON_COLS & set(d):
        try:
            d[k] = json.loads(d[k] or "null")
        except ValueError:
            pass
    return d


def _keyed(t: dict) -> dict:
    t["key"] = "%s-%d" % (t.pop("pkey", "") or "T", t["num"])
    return t


def _pick(v, pairs, default):
    """Accept either the code ('bug') or its Chinese label ('缺陷')."""
    if v in (None, ""):
        return default
    for code, label in pairs:
        if v in (code, label):
            return code
    return default
