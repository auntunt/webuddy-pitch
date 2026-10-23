"""Durable collaboration handoffs; receiving materials is never acceptance.

HTTP adapters must pass a validated personal session, never an agent-supplied
name. All collaboration mutations, timeline entries and replay receipts share a
single SQLite transaction. Candidate inspection happens before the write lock.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re

from . import candidates, signoff
from .errors import ApiError
from .store import now

STAGES = ("requirement", "development", "testing", "delivery", "operations")
ACTIONS = ("send", "receive", "return", "block", "resume", "withdraw")
BOUNDARY = "交接接收只确认协作材料，不代表技术复核、业务验收或关单。当前为共享工作区，责任视图不是访问权限隔离。"
DDL = (
    """CREATE TABLE IF NOT EXISTS ticket_handoff_heads (
      ticket_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, current_id INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS ticket_handoffs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
      stage TEXT NOT NULL, status TEXT NOT NULL, sender TEXT NOT NULL, receiver TEXT NOT NULL,
      next_actor TEXT NOT NULL, note TEXT NOT NULL, materials TEXT NOT NULL,
      source TEXT NOT NULL, source_token TEXT NOT NULL, sent_at TEXT NOT NULL,
      updated TEXT NOT NULL, resolved_at TEXT, waiting_since TEXT,
      block_reason TEXT NOT NULL DEFAULT '', resume_status TEXT NOT NULL DEFAULT '',
      resume_waiting_since TEXT)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS ticket_handoff_pending ON ticket_handoffs(ticket_id)
      WHERE status IN ('waiting','blocked')""",
    """CREATE TABLE IF NOT EXISTS ticket_handoff_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, handoff_id INTEGER NOT NULL,
      ticket_id INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
      note TEXT NOT NULL, ts TEXT NOT NULL, revision INTEGER NOT NULL,
      status TEXT NOT NULL, next_actor TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS ticket_handoff_requests (
      actor TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      ticket_id INTEGER NOT NULL, result TEXT NOT NULL, created TEXT NOT NULL,
      PRIMARY KEY(actor,request_id))""",
    "CREATE INDEX IF NOT EXISTS ticket_handoffs_ticket ON ticket_handoffs(ticket_id,id)",
    "CREATE INDEX IF NOT EXISTS ticket_handoff_events_ticket ON ticket_handoff_events(ticket_id,id)",
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def _transaction(store):
    with store.lock:
        if store.db.in_transaction:
            raise RuntimeError("handoff transaction cannot nest")
        try:
            store.db.execute("BEGIN IMMEDIATE")
            yield store.db
            store.db.commit()
        except BaseException:
            store.db.rollback()
            raise


def schema(store):
    # executescript and Store.x implicitly commit, including a caller's work.
    with _transaction(store) as db:
        for statement in DDL:
            db.execute(statement)


@contextmanager
def _read_snapshot(store):
    """Keep related reads coherent across other Store connections as well."""
    with store.lock:
        store.db.execute("SAVEPOINT handoff_read")
        try:
            yield
        finally:
            store.db.execute("RELEASE handoff_read")


def _members(P, project=None):
    from .tenant_policy import eligible_members
    return eligible_members(P, project)


def _user(P, user):
    if not isinstance(user, str) or user not in _members(P):
        raise ApiError(403, "交接操作需要有效的个人登录账号，智能体或显示名不能代替登录")
    return user


def _ticket(P, key):
    if not isinstance(key, (str, int)) or isinstance(key, bool):
        raise ApiError(400, "请选择实际工单")
    try:
        t = P.store.ticket(key)
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "工单编号不正确") from exc
    if not t:
        raise ApiError(404, "没有这个工单")
    return t


def _exists(st, table):
    return bool(st.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)))


def _db_source(P, t):
    """No schema initialization, external commands or HTTP inside transactions."""
    from .project_library import bindings, profile
    st = P.store
    project = st.project(t["project_id"])
    assignment = st.one("SELECT * FROM ticket_team WHERE ticket_id=?", (t["id"],)) if _exists(st, "ticket_team") else None
    latest = st.one("SELECT * FROM code_candidates WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (t["id"],)) if _exists(st, "code_candidates") else None
    state = {"ticket": t, "project": project, "workflow": profile(st, project)["workflow"], "assignment": assignment, "bindings": bindings(st, project),
             "discussion": st.q("SELECT * FROM events WHERE ticket_id=? AND kind IN ('comment','reject','conflict') ORDER BY id", (t["id"],)),
             "candidate": latest}
    if latest:
        state["assessment"] = st.one("SELECT * FROM candidate_assessments WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (latest["id"],))
        state["probe"] = st.one("SELECT * FROM harness_probe_runs WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (latest["id"],)) if _exists(st, "harness_probe_runs") else None
        state["run"] = st.run(latest["run_id"])
        state["run_inputs"] = st.one("SELECT * FROM knowledge_run_inputs WHERE run_id=?", (latest["run_id"],))
    return state


def _source(P, key):
    """An observed source, stabilized against concurrent database changes.

    A handoff does not make the observed evidence trustworthy for acceptance;
    existing independent review/acceptance paths must recheck their own gates.
    """
    from .agent_api import _requirement
    for unused in range(3):
        with _read_snapshot(P.store):
            t = _ticket(P, key)
            before = _db_source(P, t)
            requirement = _requirement(t, P.store)
        candidate = None
        row = before["candidate"]
        if row:
            try:
                v = candidates.view(P, row["id"])
                candidate = {k: v[k] for k in ("id", "commit", "base_commit", "evidence_hash", "current", "blocked", "criteria", "summary")}
                if not re.fullmatch(r"[0-9a-f]{40}", candidate["commit"]):
                    raise ValueError("候选缺少完整提交编号")
            except (ApiError, OSError, ValueError) as exc:
                candidate = {"id": row["id"], "commit": row["commit_sha"], "base_commit": row["base_commit"],
                             "evidence_hash": None, "current": False, "blocked": ["候选证据暂不可核对：" + str(exc)]}
        with _read_snapshot(P.store):
            fresh = _ticket(P, key)
            if _db_source(P, fresh) != before or _requirement(fresh, P.store) != requirement:
                continue
            contracts = [r for r in signoff.records(P.store.path.parent, t["key"]) if r["kind"] == "intake"]
            if _requirement(fresh, P.store) != requirement:
                continue
            source = {"requirement_hash": requirement, "ticket": t,
                      "project": {"id": before["project"]["id"], "key": before["project"]["key"], "root": before["project"]["root"]},
                      "assignment": {"assignee": t.get("assignee", ""), "reviewer": (before["assignment"] or {}).get("reviewer", ""),
                                     "revision": (before["assignment"] or {}).get("revision", 0)},
                      "bindings": before["bindings"], "discussion": before["discussion"],
                      "workflow": before["workflow"], "client_contract": contracts[-1] if contracts else None, "candidate": candidate}
            # Incidental ticket.updated/comments about this handoff do not alter
            # source identity. Requirement, authority and evidence do.
            token = _hash({k: source[k] for k in ("requirement_hash", "project", "workflow", "assignment", "bindings", "candidate")})
            return source, token, _hash(before)
    raise ApiError(409, "读取期间来源持续变化，请刷新后再交接")


def _head(st, tid):
    return st.one("SELECT * FROM ticket_handoff_heads WHERE ticket_id=?", (tid,)) or {"ticket_id": tid, "revision": 0, "current_id": None}


def _current(st, tid):
    head = _head(st, tid)
    row = st.one("SELECT * FROM ticket_handoffs WHERE id=?", (head["current_id"],)) if head["current_id"] else None
    return head, row


def _seconds(stamp):
    if not stamp:
        return None
    try:
        return max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()))
    except (ValueError, TypeError):
        return None


def _actions(t, row, user, members, stale=False, source_valid=True):
    out = dict.fromkeys(ACTIONS, False)
    if user not in members or t["status"] == "closed":
        return out
    pending = row and row["status"] in ("waiting", "blocked")
    owner = row["next_actor"] if row else t.get("assignee", "")
    out["send"] = bool(not pending and user in (owner, t.get("assignee")) and source_valid)
    if row:
        out["receive"] = row["status"] == "waiting" and user == row["receiver"] and not stale and source_valid
        out["return"] = row["status"] == "waiting" and user == row["receiver"]
        out["block"] = row["status"] in ("waiting", "received", "returned", "withdrawn") and user == owner
        out["resume"] = row["status"] == "blocked" and user == owner
        out["withdraw"] = bool(pending and user in (row["sender"], t.get("assignee")))
    return out


def _valid_source(source):
    return source["workflow"] != "reference" and not any(not b["available"] for b in source["bindings"]) and (source["candidate"] is None or source["candidate"]["current"])


def _present(row, source, token, t, user, members):
    saved = json.loads(row["source"])
    stale = row["source_token"] != token or not _valid_source(source)
    reasons = []
    if saved["requirement_hash"] != source["requirement_hash"]:
        reasons.append("需求、沟通或参考知识来源已变化")
    if saved["project"] != source["project"]:
        reasons.append("项目工作区已变化")
    if source["workflow"] == "reference":
        reasons.append("项目当前仅供查阅，请先建立独立维护工作区")
    if saved["assignment"] != source["assignment"]:
        reasons.append("任务负责人或复核分配已变化")
    if saved["candidate"] != source["candidate"] or source["candidate"] and not source["candidate"]["current"]:
        reasons.append("固定候选或验证证据已变化或失效")
    if saved["bindings"] != source["bindings"] or any(not b["available"] for b in source["bindings"]):
        reasons.append("参考知识版本或共享授权已变化")
    result = dict(row, source=saved, stale=bool(stale), stale_reasons=reasons,
                  sender_active=row["sender"] in members, receiver_active=row["receiver"] in members,
                  next_actor_active=row["next_actor"] in members,
                  waiting_seconds=_seconds(row["waiting_since"]),
                  actions=_actions(t, row, user, members, stale, _valid_source(source)))
    return result


def _read(P, t, user, source, token, members):
    from .tenant_policy import enabled
    head, current = _current(P.store, t["id"])
    history = []
    for row in P.store.q("SELECT * FROM ticket_handoffs WHERE ticket_id=? ORDER BY id", (t["id"],)):
        item = _present(row, source, token, t, user, members)
        item["events"] = P.store.q("SELECT * FROM ticket_handoff_events WHERE handoff_id=? ORDER BY id", (row["id"],))
        # Only the latest handoff can be changed, even if an old received row
        # still happens to name the viewer as next_actor.
        if row["id"] != head["current_id"]:
            item["actions"] = dict.fromkeys(ACTIONS, False)
        history.append(item)
    latest = history[-1] if history else None
    actions = _actions(t, current, user, members, latest and latest["stale"], _valid_source(source))
    return {"ticket": t, "revision": head["revision"], "current": latest, "history": history,
            "members": [{"id": name, "name": name} for name in members], "source": source, "source_token": token,
            "can_send": actions["send"], "actions": actions,
            "next_actor": current["next_actor"] if current else t.get("assignee") or None,
            "waiting_since": current["waiting_since"] if current else None,
            "waiting_seconds": _seconds(current["waiting_since"]) if current else None,
            "boundary": ("交接接收只确认协作材料，不代表技术复核、业务验收或关单。访问范围由当前租户与项目授权决定。" if enabled(P) else BOUNDARY)}


def read(P, ticket, user):
    _user(P, user)
    from .tenant_policy import require_member
    require_member(P, user, _ticket(P, ticket)["project_id"], "viewer")
    source, token, fingerprint = _source(P, ticket)
    with _read_snapshot(P.store):
        t = _ticket(P, ticket)
        if _hash(_db_source(P, t)) != fingerprint:
            raise ApiError(409, "来源已变化，请刷新")
        return _read(P, t, user, source, token, _members(P, t["project_id"]))


def summary_rows(store, ticket_ids):
    """Cheap current rows for workspace projections; never claims source freshness.

    Return a dict keyed by integer ticket id. Absent keys mean no recorded
    handoff; callers must preserve unknown stage/wait information.
    """
    ids = list(dict.fromkeys(ticket_ids))
    result = {}
    for offset in range(0, len(ids), 400):
        part = ids[offset:offset + 400]
        rows = store.q("SELECT h.ticket_id,h.id,h.stage,h.status,h.sender,h.receiver,h.next_actor,h.note,h.block_reason,h.resume_status,"
                       "h.sent_at,h.updated,h.waiting_since,x.revision FROM ticket_handoff_heads x "
                       "JOIN ticket_handoffs h ON h.id=x.current_id WHERE x.ticket_id IN (" + ",".join("?" for _ in part) + ")", part)
        for row in rows:
            result[row["ticket_id"]] = dict(row, waiting_seconds=_seconds(row["waiting_since"]), source_checked=False)
    return result


def _validate(body):
    if not isinstance(body, dict):
        raise ApiError(400, "交接请求必须是对象")
    action = body.get("action")
    if action not in ACTIONS:
        raise ApiError(400, "未知交接操作")
    allowed = {"ticket", "action", "revision", "request_id", "note"}
    allowed |= {"receiver", "stage", "materials", "source_token"} if action == "send" else {"handoff_id"}
    if set(body) - allowed:
        raise ApiError(400, "交接请求含未知字段，不能指定人工身份或伪造来源证据")
    if not isinstance(body.get("revision"), int) or isinstance(body["revision"], bool) or body["revision"] < 0:
        raise ApiError(400, "需要当前交接修订号 revision")
    if not isinstance(body.get("request_id"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", body["request_id"]):
        raise ApiError(400, "需要稳定的 request_id，重试请沿用同一编号")
    note = body.get("note", "")
    if not isinstance(note, str) or action in ("send", "return", "block", "withdraw") and not note.strip():
        raise ApiError(400, "请完整填写交接、退回、阻塞或撤回说明")
    if action == "send":
        if body.get("stage") not in STAGES:
            raise ApiError(400, "请选择协作阶段")
        if not isinstance(body.get("receiver"), str) or not isinstance(body.get("materials", ""), str):
            raise ApiError(400, "接收人必须是账号，交接材料必须是完整文本")
        if not isinstance(body.get("source_token"), str) or not re.fullmatch(r"[0-9a-f]{64}", body["source_token"]):
            raise ApiError(400, "请先读取当前材料与来源版本，再发起交接")
    elif not isinstance(body.get("handoff_id"), int) or isinstance(body["handoff_id"], bool):
        raise ApiError(400, "请选择当前交接记录")


@contextmanager
def _source_lock(P, tid):
    # All candidate mutations take this lock before source_guard. Same order
    # here prevents a candidate or verification publication racing our capture.
    with candidates.guard(P, tid):
        row = P.store.one("SELECT run_id FROM code_candidates WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (tid,)) if _exists(P.store, "code_candidates") else None
        if row:
            from .recheck_operations import source_guard
            try:
                with source_guard(P.data_dir, row["run_id"]):
                    yield
            except ValueError as exc:
                raise ApiError(409, str(exc)) from exc
        else:
            yield


def dispatch_action(P, body, user):
    _user(P, user)
    _validate(body)
    t = _ticket(P, body.get("ticket"))
    from .tenant_policy import require_member
    require_member(P, user, t["project_id"])
    st, action = P.store, body["action"]
    fingerprint = _hash(body)
    # Fast replay also works after a later source change or ticket closure.
    old = st.one("SELECT * FROM ticket_handoff_requests WHERE actor=? AND request_id=?", (user, body["request_id"]))
    if old:
        if old["fingerprint"] != fingerprint:
            raise ApiError(409, "同一请求编号已用于不同内容")
        result = json.loads(old["result"])
        result["receipt"]["replayed"] = True
        return result
    with _source_lock(P, t["id"]):
        source, token, source_fingerprint = _source(P, t["id"])
        with _transaction(st) as db:
            _user(P, user)
            require_member(P, user, t["project_id"])
            members = _members(P, t["project_id"])
            old = st.one("SELECT * FROM ticket_handoff_requests WHERE actor=? AND request_id=?", (user, body["request_id"]))
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ApiError(409, "同一请求编号已用于不同内容")
                result = json.loads(old["result"])
                result["receipt"]["replayed"] = True
                return result
            t = _ticket(P, t["id"])
            if _hash(_db_source(P, t)) != source_fingerprint:
                raise ApiError(409, "准备交接期间来源或分配已变化，请刷新")
            from .agent_api import _requirement
            if _requirement(t, st) != source["requirement_hash"]:
                raise ApiError(409, "准备交接期间需求来源已变化，请刷新")
            head, current = _current(st, t["id"])
            if head["revision"] != body["revision"]:
                raise ApiError(409, "交接已被其他人更新，请刷新后再操作")
            stale = bool(current and (current["source_token"] != token or not _valid_source(source)))
            permitted = _actions(t, current, user, members, stale, _valid_source(source))
            if not permitted[action]:
                if t["status"] == "closed":
                    raise ApiError(409, "工单已关闭，交接历史只读")
                if action == "receive" and stale:
                    raise ApiError(409, "交接来源已变化或失效，请退回后重新交接")
                raise ApiError(403 if user not in (t.get("assignee"), (current or {}).get("next_actor"), (current or {}).get("sender")) else 409,
                               "当前身份或交接状态不允许此操作")
            stamp, note = _now(), body.get("note", "")
            if action == "send":
                if body["receiver"] not in members:
                    raise ApiError(400, "接收人必须是当前有效个人账号")
                if body["receiver"] == user:
                    raise ApiError(400, "交接需要另一位接收人")
                if body["source_token"] != token:
                    raise ApiError(409, "材料来源、候选或任务分配已变化，请刷新后再发送")
                hid = db.execute("INSERT INTO ticket_handoffs(ticket_id,stage,status,sender,receiver,next_actor,note,materials,source,source_token,sent_at,updated,waiting_since) "
                                 "VALUES(?,?,'waiting',?,?,?,?,?,?,?,?,?,?)",
                                 (t["id"], body["stage"], user, body["receiver"], body["receiver"], note, body.get("materials", ""), _json(source), token, stamp, stamp, stamp)).lastrowid
                status, next_actor = "waiting", body["receiver"]
            else:
                if body["handoff_id"] != current["id"]:
                    raise ApiError(409, "只能操作当前交接，历史记录保持不变")
                hid = current["id"]
                status, next_actor = current["status"], current["next_actor"]
                waiting, resolved = current["waiting_since"], current["resolved_at"]
                block, resume_status, resume_waiting = current["block_reason"], current["resume_status"], current["resume_waiting_since"]
                if action in ("receive", "return", "withdraw"):
                    status = {"receive": "received", "return": "returned", "withdraw": "withdrawn"}[action]
                    next_actor = current["receiver"] if action == "receive" else current["sender"] if current["sender"] in members else t.get("assignee", "")
                    waiting, resolved, block, resume_status, resume_waiting = None, stamp, "", "", None
                elif action == "block":
                    resume_status, resume_waiting = status, waiting
                    status, waiting, block = "blocked", stamp, note
                else:
                    status, waiting, block = resume_status, resume_waiting, ""
                    resume_status, resume_waiting = "", None
                db.execute("UPDATE ticket_handoffs SET status=?,next_actor=?,updated=?,resolved_at=?,waiting_since=?,block_reason=?,resume_status=?,resume_waiting_since=? WHERE id=?",
                           (status, next_actor, stamp, resolved, waiting, block, resume_status, resume_waiting, hid))
            revision = head["revision"] + 1
            db.execute("INSERT INTO ticket_handoff_heads(ticket_id,revision,current_id) VALUES(?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET revision=excluded.revision,current_id=excluded.current_id",
                       (t["id"], revision, hid))
            db.execute("INSERT INTO ticket_handoff_events(handoff_id,ticket_id,action,actor,note,ts,revision,status,next_actor) VALUES(?,?,?,?,?,?,?,?,?)",
                       (hid, t["id"], action, user, note, stamp, revision, status, next_actor))
            db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                       (t["id"], now(), user, "handoff_" + action, note,
                        _json({"handoff_id": hid, "revision": revision, "status": status, "next_actor": next_actor, "source_token": token, "acceptance": False})))
            result = _read(P, t, user, source, token, members)
            result["receipt"] = {"request_id": body["request_id"], "replayed": False, "revision": revision}
            db.execute("INSERT INTO ticket_handoff_requests(actor,request_id,fingerprint,ticket_id,result,created) VALUES(?,?,?,?,?,?)",
                       (user, body["request_id"], fingerprint, t["id"], _json(result), stamp))
            return result
