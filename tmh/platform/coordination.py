"""Personal, project-scoped meeting actions and versioned task briefs.

These records coordinate people. They never execute agents, approve evidence,
advance ticket states or replace immutable source material. HTTP adapters must
pass the authenticated personal account, not an actor supplied in the payload.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from urllib.parse import quote
import hashlib
import json
import re

from .errors import ApiError
from . import signoff, tenant_policy
from .store import now


DDL = (
    """CREATE TABLE IF NOT EXISTS coordination_meetings (
      id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
      title TEXT NOT NULL, body TEXT NOT NULL, occurred_on TEXT NOT NULL,
      source_hash TEXT NOT NULL, created TEXT NOT NULL, created_by TEXT NOT NULL,
      revision INTEGER NOT NULL, extraction TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS coordination_actions (
      id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id INTEGER NOT NULL,
      title TEXT NOT NULL, owner TEXT NOT NULL, due_date TEXT NOT NULL,
      deliverable TEXT NOT NULL, criteria TEXT NOT NULL, source_start INTEGER,
      source_end INTEGER, source_quote TEXT NOT NULL, note TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('draft','withdrawn','published')),
      withdraw_reason TEXT NOT NULL DEFAULT '', ticket_id INTEGER UNIQUE,
      created TEXT NOT NULL, updated TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS coordination_action_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, action_id INTEGER NOT NULL,
      meeting_id INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
      ts TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS coordination_briefs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
      revision INTEGER NOT NULL, summary TEXT NOT NULL, decisions TEXT NOT NULL,
      next_step TEXT NOT NULL, owner TEXT NOT NULL, due_date TEXT NOT NULL,
      source TEXT NOT NULL, source_token TEXT NOT NULL,
      created TEXT NOT NULL, created_by TEXT NOT NULL, UNIQUE(ticket_id,revision))""",
    """CREATE TABLE IF NOT EXISTS coordination_requests (
      actor TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      result TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(actor,request_id))""",
    "CREATE INDEX IF NOT EXISTS coordination_meetings_project ON coordination_meetings(project_id,id)",
    "CREATE INDEX IF NOT EXISTS coordination_actions_meeting ON coordination_actions(meeting_id,id)",
    "CREATE INDEX IF NOT EXISTS coordination_events_meeting ON coordination_action_events(meeting_id,id)",
)
ACTION_FIELDS = frozenset(("title", "owner", "due_date", "deliverable", "criteria",
                           "source_start", "source_end", "note"))
ACTION_NAMES = ("add_action", "edit_action", "withdraw_action", "publish_action")
EXPLICIT_ACTION = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\[ \]\s+|(?:TODO|待办|行动项|action item)\s*[:：]\s*)(\S.*?)\s*$",
    re.IGNORECASE,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def _transaction(store):
    with store.lock:
        if store.db.in_transaction:
            raise RuntimeError("coordination transaction cannot nest")
        try:
            store.db.execute("BEGIN IMMEDIATE")
            yield store.db
            store.db.commit()
        except BaseException:
            store.db.rollback()
            raise


def schema(store):
    """Atomic, idempotent DDL; never commits somebody else's transaction."""
    with _transaction(store) as db:
        for statement in DDL:
            db.execute(statement)


@contextmanager
def _snapshot(store):
    with store.lock:
        store.db.execute("SAVEPOINT coordination_read")
        try:
            yield
        finally:
            store.db.execute("RELEASE coordination_read")


def _project(P, key):
    if not isinstance(key, (str, int)) or isinstance(key, bool) or not str(key):
        raise ApiError(404, "没有这个项目")
    if isinstance(key, int) and not 1 <= key <= 2 ** 63 - 1:
        raise ApiError(404, "没有这个项目")
    row = P.store.project(key)
    if not row:
        raise ApiError(404, "没有这个项目")
    return row


def _ticket(P, key):
    if not isinstance(key, (str, int)) or isinstance(key, bool):
        raise ApiError(400, "工单编号不正确")
    try:
        row = P.store.ticket(key)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ApiError(400, "工单编号不正确") from exc
    if not row:
        raise ApiError(404, "没有这个工单")
    return row


def _access(P, project, actor, level="viewer"):
    # Legacy require_member alone does not authenticate a real account.
    if not isinstance(actor, str) or not signoff.human(actor) or actor not in tenant_policy.directory(P):
        raise ApiError(403, "协作记录需要有效的个人登录账号，智能体或显示名不能代替登录")
    tenant_policy.require_member(P, actor, project, level)


def _editable(P, project, actor):
    try:
        _access(P, project, actor, "contributor")
        return True
    except ApiError:
        return False


def _members(P, project):
    return [{"id": name, "name": name} for name in tenant_policy.eligible_members(P, project)]


def _fields(body, allowed):
    if not isinstance(body, dict) or any(key not in allowed for key in body):
        raise ApiError(400, "请求包含未知字段")


def _text(body, key, required=False):
    value = body.get(key, "")
    if not isinstance(value, str) or (required and not value.strip()):
        raise ApiError(400, "%s 必须是%s文本" % (key, "非空" if required else ""))
    return value


def _date(body, key):
    value = _text(body, key)
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ApiError(400, "%s 必须是 YYYY-MM-DD 日期或空字符串" % key) from exc
        if parsed.isoformat() != value:
            raise ApiError(400, "%s 必须是 YYYY-MM-DD 日期或空字符串" % key)
    return value


def _positive(value, name):
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        if len(value) > 19:
            raise ApiError(400, "%s 超出有效编号范围" % name)
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 2 ** 63 - 1:
        raise ApiError(400, "%s 必须是正整数" % name)
    return value


def _revision(body, expected):
    revision = body.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ApiError(400, "请提交有效 revision")
    if revision != expected:
        raise ApiError(409, "协作记录已变化，请保留草稿并核对最新版本")


def _request(body, resource):
    rid = _text(body, "request_id", True)
    if len(rid) > 200:
        raise ApiError(400, "request_id 最多 200 个字符")
    return rid, _digest({"resource": resource, "payload": body})


def _replay(store, actor, request_id, fingerprint):
    row = store.one("SELECT fingerprint,result FROM coordination_requests WHERE actor=? AND request_id=?",
                    (actor, request_id))
    if not row:
        return None
    if row["fingerprint"] != fingerprint:
        raise ApiError(409, "request_id 已用于其他内容，请使用新的请求编号")
    result = json.loads(row["result"])
    result["receipt"]["replayed"] = True
    return result


def _save_receipt(store, actor, request_id, fingerprint, result):
    result["receipt"] = {"request_id": request_id, "revision": result["revision"], "replayed": False}
    store.db.execute("INSERT INTO coordination_requests(actor,request_id,fingerprint,result,created) VALUES(?,?,?,?,?)",
                     (actor, request_id, fingerprint, _json(result), _now()))
    return result


def _meeting_row(P, project, mid):
    row = P.store.one("SELECT * FROM coordination_meetings WHERE id=? AND project_id=?",
                      (_positive(mid, "meeting_id"), project["id"]))
    if not row:
        raise ApiError(404, "没有这个项目下的会议记录")
    return row


def _meeting_meta(row, project):
    return dict(row, project=project["key"], extraction=json.loads(row["extraction"]))


def _action_values(P, project, meeting_row, body, previous=None):
    values = {key: (previous[key] if previous else (None if key in ("source_start", "source_end") else ""))
              for key in ACTION_FIELDS}
    values.update({key: body[key] for key in ACTION_FIELDS if key in body})
    for key in ACTION_FIELDS - {"source_start", "source_end", "due_date"}:
        values[key] = _text(values, key)
    values["due_date"] = _date(values, "due_date")
    if values["owner"] and values["owner"] not in tenant_policy.eligible_members(P, project):
        raise ApiError(400, "负责人必须是当前项目有效的可写个人成员")
    start, end = values["source_start"], values["source_end"]
    values["source_quote"] = ""
    if start is not None or end is not None:
        if any(not isinstance(v, int) or isinstance(v, bool) for v in (start, end)):
            raise ApiError(400, "来源必须同时提交从 1 开始的 source_start/source_end 行号")
        lines = meeting_row["body"].splitlines(keepends=True)
        if not 1 <= start <= end <= len(lines):
            raise ApiError(400, "来源行范围不属于会议原文")
        values["source_quote"] = "".join(lines[start - 1:end])
    return values


def _insert_action(store, mid, values, stamp):
    keys = sorted(values)
    rowid = store.db.execute(
        "INSERT INTO coordination_actions(meeting_id,%s,status,created,updated) VALUES(%s)" %
        (",".join(keys), ",".join("?" for _ in range(len(keys) + 4))),
        (mid, *(values[key] for key in keys), "draft", stamp, stamp),
    ).lastrowid
    return store.one("SELECT * FROM coordination_actions WHERE id=?", (rowid,))


def _action_event(store, row, action, actor, revision):
    store.db.execute("INSERT INTO coordination_action_events(action_id,meeting_id,action,actor,ts,revision,snapshot) VALUES(?,?,?,?,?,?,?)",
                     (row["id"], row["meeting_id"], action, actor, _now(), revision, _json(row)))


def _meeting_view(P, project, row, actor):
    events = P.store.q("SELECT * FROM coordination_action_events WHERE meeting_id=? ORDER BY id", (row["id"],))
    history = {}
    for event in events:
        history.setdefault(event["action_id"], []).append(dict(event, snapshot=json.loads(event["snapshot"])))
    actions = []
    for item in P.store.q("SELECT * FROM coordination_actions WHERE meeting_id=? ORDER BY id", (row["id"],)):
        ticket = P.store.ticket(item["ticket_id"]) if item["ticket_id"] else None
        actions.append(dict(item, history=history.get(item["id"], []),
                            ticket={key: ticket[key] for key in ("id", "key", "status", "assignee")} if ticket else None))
    return {"meeting": _meeting_meta(row, project), "id": row["id"], "project": project["key"],
            "revision": row["revision"], "body": row["body"], "source_hash": row["source_hash"],
            "actions": actions, "members": _members(P, project), "can_edit": _editable(P, project, actor), "receipt": None}


def meetings(P, project_key, query, actor):
    query = query or {}
    _fields(query, {"offset", "limit"})
    def page_value(name, default, low, high=None):
        value = query.get(name, default)
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            if len(value) > 19:
                raise ApiError(400, "无效的分页参数 %s" % name)
            value = int(value)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= 2 ** 63 - 1 or (high is not None and value > high):
            raise ApiError(400, "无效的分页参数 %s" % name)
        return value
    offset, limit = page_value("offset", 0, 0), page_value("limit", 50, 1, 100)
    with _snapshot(P.store):
        project = _project(P, project_key)
        _access(P, project, actor)
        total = P.store.one("SELECT COUNT(*) n FROM coordination_meetings WHERE project_id=?", (project["id"],))["n"]
        rows = P.store.q("SELECT * FROM coordination_meetings WHERE project_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (project["id"], limit, offset))
        items = []
        for row in rows:
            meta = _meeting_meta(row, project)
            # Listing is explicitly metadata; the immutable original lives in detail.
            del meta["body"]
            counts = {status: 0 for status in ("draft", "withdrawn", "published")}
            counts.update({v["status"]: v["n"] for v in P.store.q("SELECT status,COUNT(*) n FROM coordination_actions WHERE meeting_id=? GROUP BY status", (row["id"],))})
            items.append(dict(meta, action_counts=counts))
        return {"project": project["key"], "items": items, "total": total, "offset": offset, "limit": limit,
                "can_edit": _editable(P, project, actor), "members": _members(P, project)}


def meeting(P, project_key, mid, actor):
    with _snapshot(P.store):
        project = _project(P, project_key)
        _access(P, project, actor)
        return _meeting_view(P, project, _meeting_row(P, project, mid), actor)


def create_meeting(P, project_key, body, actor):
    _fields(body, {"title", "body", "occurred_on", "request_id"})
    title, original, occurred = _text(body, "title", True), _text(body, "body", True), _date(body, "occurred_on")
    with _transaction(P.store) as db:
        project = _project(P, project_key)
        _access(P, project, actor, "contributor")
        request_id, fingerprint = _request(body, ["create_meeting", project["id"]])
        replay = _replay(P.store, actor, request_id, fingerprint)
        if replay is not None:
            return replay
        proposals = [(i, match.group(1)) for i, line in enumerate(original.splitlines(), 1)
                     if (match := EXPLICIT_ACTION.match(line))]
        extraction = {"method": "explicit_markers", "count": len(proposals),
                      "notice": "仅识别独立的 TODO、待办、行动项、Action item 或未勾选清单行；这是待核对候选，不推断负责人、期限和验收条件。可手工补充遗漏。"}
        stamp = _now()
        mid = db.execute("INSERT INTO coordination_meetings(project_id,title,body,occurred_on,source_hash,created,created_by,revision,extraction) VALUES(?,?,?,?,?,?,?,?,?)",
                         (project["id"], title, original, occurred, hashlib.sha256(original.encode("utf-8")).hexdigest(), stamp, actor, 1, _json(extraction))).lastrowid
        row = _meeting_row(P, project, mid)
        for line, proposal in proposals:
            values = _action_values(P, project, row, {"title": proposal, "source_start": line, "source_end": line})
            action = _insert_action(P.store, mid, values, stamp)
            _action_event(P.store, action, "extract", actor, 1)
        result = _meeting_view(P, project, row, actor)
        return _save_receipt(P.store, actor, request_id, fingerprint, result)


def _meeting_url(P, project_key, mid):
    tenant = getattr(getattr(P, "tenant_context", None), "tenant_id", None)
    base = "/t/" + quote(tenant, safe="") if tenant else ""
    return "%s/#/meetings/%s/%s" % (base, mid, quote(project_key, safe=""))


def _publish(P, project, row, action, actor):
    from .project_library import require_development
    try:
        require_development(P.store, project)
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc
    if any(not action[key].strip() for key in ("title", "owner", "deliverable", "criteria")):
        raise ApiError(400, "发布前请补齐标题、负责人、交付物和验收条件；期限可明确留空")
    if action["owner"] not in tenant_policy.eligible_members(P, project):
        raise ApiError(400, "负责人已不可用，请选择当前项目有效的可写个人成员")
    api_url = "/api/projects/%s/meetings/%s" % (project["key"], row["id"])
    source_url = _meeting_url(P, project["key"], row["id"])
    location = "第 %s–%s 行" % (action["source_start"], action["source_end"]) if action["source_start"] else "人工补充，未指定原文行号"
    ticket_body = ("## 行动\n%s\n\n## 交付物\n%s\n\n## 验收条件\n%s\n\n## 协作约定\n负责人：%s\n期限：%s\n\n"
                   "## 会议来源\n会议：%s\n记录：%s\n逻辑接口：%s\n行动编号：%s\n来源位置：%s\n原文 SHA-256：%s\n\n## 补充说明\n%s" %
                   (action["title"], action["deliverable"], action["criteria"], action["owner"], action["due_date"] or "未约定",
                    row["title"], source_url, api_url, action["id"], location, row["source_hash"], action["note"]))
    links = {"coordination": {"meeting_id": row["id"], "action_id": action["id"], "source_hash": row["source_hash"],
                              "source_start": action["source_start"], "source_end": action["source_end"],
                              "due_date": action["due_date"], "url": source_url, "api_url": api_url}}
    stamp = now()
    number = P.store.one("SELECT COALESCE(MAX(num),0)+1 n FROM tickets WHERE project_id=?", (project["id"],))["n"]
    tid = P.store.db.execute("INSERT INTO tickets(project_id,num,title,body,type,status,assignee,reporter,links,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (project["id"], number, action["title"], ticket_body, "change", "new", action["owner"], actor, _json(links), stamp, stamp)).lastrowid
    P.store.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                       (tid, stamp, actor, "created", "从会议行动清单发布；仍需遵循既有确认与验收流程", _json(links)))
    P.store.db.execute("UPDATE coordination_actions SET status='published',ticket_id=?,updated=? WHERE id=?", (tid, _now(), action["id"]))


def meeting_action(P, project_key, mid, body, actor):
    if not isinstance(body, dict) or body.get("action") not in ACTION_NAMES:
        raise ApiError(400, "未知会议行动操作")
    operation = body["action"]
    allowed = {"action", "revision", "request_id"}
    if operation != "add_action":
        allowed.add("action_id")
    if operation in ("add_action", "edit_action"):
        allowed.update(ACTION_FIELDS)
    if operation == "withdraw_action":
        allowed.add("note")
    _fields(body, allowed)
    with _transaction(P.store) as db:
        project = _project(P, project_key)
        _access(P, project, actor, "contributor")
        row = _meeting_row(P, project, mid)
        request_id, fingerprint = _request(body, ["meeting_action", project["id"], row["id"]])
        replay = _replay(P.store, actor, request_id, fingerprint)
        if replay is not None:
            return replay
        _revision(body, row["revision"])
        revision = row["revision"] + 1
        if operation == "add_action":
            action = _insert_action(P.store, row["id"], _action_values(P, project, row, body), _now())
        else:
            action = P.store.one("SELECT * FROM coordination_actions WHERE id=? AND meeting_id=?", (_positive(body.get("action_id"), "action_id"), row["id"]))
            if not action:
                raise ApiError(404, "没有这条会议行动")
            if action["status"] != "draft":
                raise ApiError(409, "只有草稿可修改、撤回或发布；已发布工作请进入关联任务处理")
            if operation == "edit_action":
                values = _action_values(P, project, row, body, action)
                keys = sorted(values)
                db.execute("UPDATE coordination_actions SET %s,updated=? WHERE id=?" % ",".join(key + "=?" for key in keys),
                           (*(values[key] for key in keys), _now(), action["id"]))
            elif operation == "withdraw_action":
                note = _text(body, "note", True)
                db.execute("UPDATE coordination_actions SET status='withdrawn',withdraw_reason=?,updated=? WHERE id=?", (note, _now(), action["id"]))
            else:
                _publish(P, project, row, action, actor)
            action = P.store.one("SELECT * FROM coordination_actions WHERE id=?", (action["id"],))
        _action_event(P.store, action, operation, actor, revision)
        db.execute("UPDATE coordination_meetings SET revision=? WHERE id=?", (revision, row["id"]))
        result = _meeting_view(P, project, _meeting_row(P, project, row["id"]), actor)
        return _save_receipt(P.store, actor, request_id, fingerprint, result)


def _brief_source(P, project, ticket):
    """DB-only snapshot, coherent with the brief transaction; no Git/FS/model."""
    source = {"project": {key: project[key] for key in ("id", "key", "root")},
              "ticket": {key: ticket[key] for key in ("id", "key", "title", "body", "status", "assignee", "reporter", "links", "labels", "external")},
              "assignment": None,
              "discussion": P.store.q("SELECT id,ts,author,kind,body,data FROM events WHERE ticket_id=? AND kind IN ('comment','reject','conflict') ORDER BY id", (ticket["id"],)),
              "meeting_origin": None, "handoff": {"head": None, "current": None}}
    if P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_team'"):
        source["assignment"] = P.store.one("SELECT * FROM ticket_team WHERE ticket_id=?", (ticket["id"],))
    # Current handoff materials and responsibility are part of the work context.
    # Read persisted facts only, not a Git/preview recheck or elapsed-time view.
    head = P.store.one("SELECT * FROM ticket_handoff_heads WHERE ticket_id=?", (ticket["id"],))
    if head:
        current = P.store.one("SELECT * FROM ticket_handoffs WHERE id=? AND ticket_id=?", (head["current_id"], ticket["id"]))
        source["handoff"] = {"head": head, "current": current}
    # Trust the server-owned association, not a caller-edited links dictionary.
    origin = P.store.one("SELECT a.id action_id,a.meeting_id,m.source_hash,m.title,m.project_id FROM coordination_actions a JOIN coordination_meetings m ON m.id=a.meeting_id WHERE a.ticket_id=?", (ticket["id"],))
    if origin:
        if origin["project_id"] != project["id"]:
            raise ApiError(409, "会议来源与当前任务项目不一致")
        source["meeting_origin"] = origin
    return source


def ticket_action(P, ticket):
    """Small DB projection for an already-authorized workspace ticket.

    Owner and status come from the ticket itself, never the original proposal.
    A missing or cross-project association is not presented as valid provenance.
    """
    row = P.store.one(
        "SELECT a.id action_id,a.meeting_id,a.source_start,a.source_end,a.due_date,"
        "m.title meeting_title,m.source_hash,p.key project FROM coordination_actions a "
        "JOIN coordination_meetings m ON m.id=a.meeting_id JOIN projects p ON p.id=m.project_id "
        "WHERE a.ticket_id=? AND m.project_id=?", (ticket["id"], ticket["project_id"]))
    if row:
        project_key = row.pop("project")
        row["url"] = _meeting_url(P, project_key, row["meeting_id"])
        row["api_url"] = "/api/projects/%s/meetings/%s" % (project_key, row["meeting_id"])
    return row


def _brief_view(P, project, ticket, actor):
    source = _brief_source(P, project, ticket)
    token = _digest(source)
    rows = P.store.q("SELECT * FROM coordination_briefs WHERE ticket_id=? ORDER BY revision DESC", (ticket["id"],))
    history = [dict(row, source=json.loads(row["source"]), stale=row["source_token"] != token) for row in rows]
    return {"ticket": {key: ticket[key] for key in ("id", "key", "title", "status", "assignee")},
            "revision": history[0]["revision"] if history else 0, "source": source, "source_token": token,
            "current": history[0] if history else None, "history": history, "members": _members(P, project),
            "can_edit": _editable(P, project, actor), "receipt": None}


def brief(P, ticket_key, actor):
    with _snapshot(P.store):
        ticket = _ticket(P, ticket_key)
        project = _project(P, ticket["project_id"])
        _access(P, project, actor)
        return _brief_view(P, project, ticket, actor)


def save_brief(P, ticket_key, body, actor):
    _fields(body, {"source_token", "revision", "request_id", "summary", "decisions", "next_step", "owner", "due_date"})
    values = {key: _text(body, key, key == "summary") for key in ("summary", "decisions", "next_step", "owner")}
    values["due_date"] = _date(body, "due_date")
    with _transaction(P.store) as db:
        ticket = _ticket(P, ticket_key)
        project = _project(P, ticket["project_id"])
        _access(P, project, actor, "contributor")
        request_id, fingerprint = _request(body, ["save_brief", project["id"], ticket["id"]])
        replay = _replay(P.store, actor, request_id, fingerprint)
        if replay is not None:
            return replay
        view = _brief_view(P, project, ticket, actor)
        _revision(body, view["revision"])
        if not isinstance(body.get("source_token"), str) or body["source_token"] != view["source_token"]:
            raise ApiError(409, "任务依据已变化，请保留草稿并核对最新来源")
        if values["owner"] and values["owner"] not in tenant_policy.eligible_members(P, project):
            raise ApiError(400, "负责人必须是当前项目有效的可写个人成员")
        revision = view["revision"] + 1
        db.execute("INSERT INTO coordination_briefs(ticket_id,revision,summary,decisions,next_step,owner,due_date,source,source_token,created,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (ticket["id"], revision, values["summary"], values["decisions"], values["next_step"], values["owner"], values["due_date"], _json(view["source"]), view["source_token"], _now(), actor))
        db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                   (ticket["id"], now(), actor, "coordination_brief", "保存工作简报（不代表复核或验收）", _json({"revision": revision, "source_token": view["source_token"]})))
        return _save_receipt(P.store, actor, request_id, fingerprint, _brief_view(P, project, ticket, actor))
