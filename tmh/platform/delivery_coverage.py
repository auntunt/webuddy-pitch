"""Version-bound material coverage; never a test, stage review or acceptance.

The HTTP adapter supplies a strict personal-session actor. This module rechecks
live membership, persists only its four own tables and never initializes legacy
schema, invokes Git, starts work or changes a delivery/ticket state.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re

from .errors import ApiError

BOUNDARY = "材料核对只记录本人核对了这份具体材料，不代表测试通过、阶段复核、业务验收或关单。"
TEMPLATE_ID = "software-delivery-v1"
TEMPLATE = (
    {"key": "requirements", "stage": "requirements", "title": "需求与验收标准", "requirement": "逐项列明用户场景、范围及可核对的验收标准。"},
    {"key": "implementation", "stage": "develop", "title": "实现说明", "requirement": "说明实现内容、对应需求、具体版本和仍未完成的事项。"},
    {"key": "testing", "stage": "quality", "title": "测试结果", "requirement": "提供实际测试命令、执行结果及未执行或未通过的项目；文字说明不等于测试通过。"},
    {"key": "delivery", "stage": "release", "title": "交付与回退", "requirement": "记录具体交付版本、运行检查、部署步骤及可实施的回退依据。"},
)
DDL = (
    """CREATE TABLE IF NOT EXISTS delivery_coverage_heads (
        delivery_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS delivery_coverage_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id TEXT NOT NULL,
        title TEXT NOT NULL, requirement TEXT NOT NULL, required INTEGER NOT NULL,
        artifact_id INTEGER, note TEXT NOT NULL, binding TEXT NOT NULL,
        verification TEXT, withdrawn INTEGER NOT NULL DEFAULT 0,
        withdraw_reason TEXT NOT NULL DEFAULT '', template_key TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL, updated TEXT NOT NULL)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS delivery_coverage_template
        ON delivery_coverage_items(delivery_id,template_key) WHERE template_key<>''""",
    """CREATE TABLE IF NOT EXISTS delivery_coverage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id TEXT NOT NULL,
        revision INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
        note TEXT NOT NULL, created TEXT NOT NULL, before_json TEXT NOT NULL,
        after_json TEXT NOT NULL, UNIQUE(delivery_id,revision))""",
    """CREATE TABLE IF NOT EXISTS delivery_coverage_requests (
        actor TEXT NOT NULL, request_id TEXT NOT NULL, delivery_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL, receipt TEXT NOT NULL, created TEXT NOT NULL,
        PRIMARY KEY(actor,request_id))""",
    "CREATE INDEX IF NOT EXISTS delivery_coverage_by_delivery ON delivery_coverage_items(delivery_id,id)",
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _body_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def _transaction(store):
    with store.lock:
        if store.db.in_transaction:
            raise RuntimeError("coverage transaction cannot nest")
        try:
            store.db.execute("BEGIN IMMEDIATE")
            yield store.db
            store.db.commit()
        except BaseException:
            store.db.rollback()
            raise


def schema(store):
    """Called independently at Store startup; all DDL rolls back together."""
    with _transaction(store) as db:
        for statement in DDL:
            db.execute(statement)


@contextmanager
def _snapshot(store):
    with store.lock:
        store.db.execute("SAVEPOINT coverage_read")
        try:
            yield
        finally:
            store.db.execute("RELEASE coverage_read")


def _exists(db, table):
    return db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _delivery(P, did):
    if not isinstance(did, str) or not re.fullmatch(r"[0-9a-f]{12}", did):
        raise ApiError(404, "没有这个交付工作项")
    db = P.store.db
    if not _exists(db, "delivery_items"):
        raise ApiError(404, "没有这个交付工作项")
    raw = db.execute("SELECT * FROM delivery_items WHERE id=?", (did,)).fetchone()
    if not raw:
        raise ApiError(404, "没有这个交付工作项")
    d = dict(raw)
    d["stages"] = json.loads(d["stages"])
    p = db.execute("SELECT * FROM projects WHERE id=?", (d["project_id"],)).fetchone()
    if not p:
        raise ApiError(404, "交付所属项目不存在")
    return d, dict(p)


def _authorize(P, actor, project, write=False):
    from . import tenant_policy
    from .signoff import human
    if not isinstance(actor, str) or not human(actor):
        raise ApiError(403, "材料核对需要有效的个人登录账号")
    level = "contributor" if write else "viewer"
    tenant_policy.require_member(P, actor, project["id"], level)
    if not tenant_policy.enabled(P) and actor not in tenant_policy.directory(P):
        raise ApiError(403, "材料核对需要有效的个人登录账号")


def _can_edit(P, actor, project):
    try:
        _authorize(P, actor, project, True)
        return True
    except ApiError:
        return False


def _facts(P, d, project):
    """Database-only source identity. It does not certify runtime evidence."""
    db = P.store.db
    artifacts = []
    for raw in db.execute("SELECT * FROM delivery_artifacts WHERE delivery_id=? ORDER BY stage,version,id", (d["id"],)):
        a = dict(raw)
        a["inputs"] = json.loads(a["inputs"])
        a["body_sha256"] = _body_hash(a["body"])
        artifacts.append(a)
    latest = {a["stage"]: a for a in artifacts}
    reviews = {}
    if _exists(db, "delivery_reviews"):
        for raw in db.execute("SELECT r.* FROM delivery_reviews r JOIN delivery_artifacts a ON a.id=r.artifact_id WHERE a.delivery_id=? ORDER BY r.id", (d["id"],)):
            r = dict(raw)
            r["inputs"] = json.loads(r["inputs"])
            reviews[r["artifact_id"]] = r
    runs, runs_by_id = {}, {}
    if _exists(db, "delivery_runs"):
        for raw in db.execute("SELECT * FROM delivery_runs WHERE delivery_id=? ORDER BY id", (d["id"],)):
            link = dict(raw)
            run = db.execute("SELECT * FROM runs WHERE id=?", (link["run_id"],)).fetchone()
            # All registered run fields matter, including changed inputs, adopted
            # commit or result. No file/Git verification is implied here.
            record = {"link": link, "run": dict(run) if run else None}
            runs[link["stage"]] = record
            runs_by_id[link["run_id"]] = record
    return {"delivery": {k: d[k] for k in ("id", "project_id", "title", "goal", "stages", "ticket_id")},
            "project": {k: project[k] for k in ("id", "key", "root")},
            "artifacts": artifacts, "latest": latest, "reviews": reviews, "runs": runs,
            "runs_by_id": runs_by_id}


def _artifact_identity(a):
    if not a:
        return None
    return {k: a[k] for k in ("id", "delivery_id", "stage", "version", "title", "body_sha256", "inputs", "source_run")}


def _binding(facts, aid):
    if aid is None:
        return None
    artifact = next((a for a in facts["artifacts"] if a["id"] == aid), None)
    if artifact is None:
        raise ApiError(400, "材料必须属于当前交付工作项")
    from .delivery import _deps
    def checked_run(record, key):
        if record is None:
            raise ApiError(400, "材料实际来源运行未登记在当前交付")
        run, link = record["run"], record["link"]
        if (not run or run["project_id"] != facts["project"]["id"]
                or run["ticket_id"] != facts["delivery"]["ticket_id"]
                or link["delivery_id"] != facts["delivery"]["id"] or link["stage"] != key):
            raise ApiError(400, "材料运行来源与交付项目、工单或阶段不一致")
        return record

    def actual_source(item):
        if not item or item["source_run"] is None:
            return None
        return checked_run(facts["runs_by_id"].get(item["source_run"]), item["stage"])

    stage = artifact["stage"]
    relevant = {stage}
    todo = [stage]
    while todo:
        for key in _deps(todo.pop(), facts["delivery"]["stages"]):
            if key not in relevant:
                relevant.add(key)
                todo.append(key)
    dependencies = {}
    for key in sorted(relevant):
        current = facts["latest"].get(key)
        dependencies[key] = {"artifact": _artifact_identity(current),
                             "artifact_source": actual_source(current),
                             "review": facts["reviews"].get(current["id"]) if current else None,
                             "run": checked_run(facts["runs"][key], key) if key in facts["runs"] else None}
    return {"delivery": facts["delivery"], "project": facts["project"],
            "artifact": _artifact_identity(artifact), "artifact_source": actual_source(artifact),
            "dependencies": dependencies}


def _row(raw):
    row = dict(raw)
    row["required"] = bool(row["required"])
    row["withdrawn"] = bool(row["withdrawn"])
    row["binding"] = json.loads(row["binding"])
    row["verification"] = json.loads(row["verification"]) if row["verification"] else None
    return row


def _present(row, facts, can_edit):
    reasons = []
    current = None
    if row["artifact_id"] is not None:
        try:
            current = _binding(facts, row["artifact_id"])
        except ApiError as exc:
            reasons.append(str(exc))
        if current:
            artifact = current["artifact"]
            latest = facts["latest"].get(artifact["stage"])
            if artifact["stage"] not in facts["delivery"]["stages"] or not latest or latest["id"] != artifact["id"]:
                reasons.append("该阶段已有新版本或不再属于当前交付范围，请重新绑定当前材料")
            if current != row["binding"]:
                reasons.append("材料内容、关联输入或项目来源已变化，请更新覆盖行后重新核对")
    token = _hash({"item": {k: row[k] for k in ("id", "delivery_id", "title", "requirement", "required", "artifact_id", "note", "binding", "updated")},
                   "current_source": current})
    verification = row["verification"]
    if row["withdrawn"]:
        status = "withdrawn"
    elif row["artifact_id"] is None:
        status = "missing"
    elif reasons:
        status = "stale"
    elif verification and verification["source_token"] == token:
        status = "checked"
    elif verification:
        status = "stale"
        reasons.append("覆盖条目或核对依据已变化")
    else:
        status = "pending"
    return dict(row, status=status, source_token=token, stale_reasons=reasons,
                can_verify=can_edit and status in ("pending", "checked"))


def _read(P, d, project, actor, facts=None):
    facts = facts or _facts(P, d, project)
    db = P.store.db
    can_edit = _can_edit(P, actor, project)
    head = db.execute("SELECT revision FROM delivery_coverage_heads WHERE delivery_id=?", (d["id"],)).fetchone()
    rows = [_present(_row(r), facts, can_edit) for r in db.execute("SELECT * FROM delivery_coverage_items WHERE delivery_id=? ORDER BY id", (d["id"],))]
    counts = dict.fromkeys(("total", "required", "required_checked", "missing", "pending", "checked", "stale", "withdrawn"), 0)
    for row in rows:
        counts[row["status"]] += 1
        if not row["withdrawn"]:
            counts["total"] += 1
            counts["required"] += row["required"]
            counts["required_checked"] += row["required"] and row["status"] == "checked"
    counts["complete"] = counts["required"] > 0 and counts["required_checked"] == counts["required"]
    history = []
    for raw in db.execute("SELECT * FROM delivery_coverage_events WHERE delivery_id=? ORDER BY id", (d["id"],)):
        event = dict(raw)
        event["before"] = json.loads(event.pop("before_json"))
        event["after"] = json.loads(event.pop("after_json"))
        history.append(event)
    existing = {r["template_key"] for r in rows}
    template = [dict(item) for item in TEMPLATE if item["stage"] in d["stages"]]
    artifacts = [dict(a, current=a["stage"] in d["stages"] and facts["latest"][a["stage"]]["id"] == a["id"]) for a in facts["artifacts"]]
    return {"delivery": {"id": d["id"], "title": d["title"], "goal": d["goal"], "project": project["key"], "project_id": project["id"], "stages": d["stages"]},
            "revision": head["revision"] if head else 0, "items": rows, "artifacts": artifacts,
            "history": history, "can_edit": can_edit, "counts": counts, "boundary": BOUNDARY,
            "template": {"id": TEMPLATE_ID, "available": can_edit and any(TEMPLATE_ID + ":" + x["key"] not in existing for x in template), "items": template}}


def read(P, did, actor):
    with _snapshot(P.store):
        d, project = _delivery(P, did)
        _authorize(P, actor, project)
        return _read(P, d, project, actor)


def _validate(body):
    if not isinstance(body, dict):
        raise ApiError(400, "覆盖请求必须是对象")
    action = body.get("action")
    extras = {"add": {"title", "requirement", "required", "artifact_id", "note"},
              "update": {"item_id", "title", "requirement", "required", "artifact_id", "note"},
              "withdraw": {"item_id", "note"}, "verify": {"item_id", "source_token", "note"},
              "seed_template": {"template_id"}}
    if not isinstance(action, str) or action not in extras:
        raise ApiError(400, "未知覆盖操作")
    if set(body) - ({"action", "revision", "request_id"} | extras[action]):
        raise ApiError(400, "不能自报核对状态、身份或未知字段")
    if type(body.get("revision")) is not int or body["revision"] < 0:
        raise ApiError(400, "需要当前 revision")
    if not isinstance(body.get("request_id"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", body["request_id"]):
        raise ApiError(400, "需要稳定的 request_id；重试请沿用原编号和完整内容")
    if action in ("update", "withdraw", "verify") and (type(body.get("item_id")) is not int or not 1 <= body["item_id"] < 2**63):
        raise ApiError(400, "需要当前覆盖行 item_id")
    if action in ("add", "update"):
        for field in ("title", "requirement"):
            if not isinstance(body.get(field), str) or not body[field].strip():
                raise ApiError(400, "标题和覆盖要求必须是完整非空文本")
        if type(body.get("required")) is not bool:
            raise ApiError(400, "required 必须是布尔值")
        if "artifact_id" not in body or body["artifact_id"] is not None and (type(body["artifact_id"]) is not int or not 1 <= body["artifact_id"] < 2**63):
            raise ApiError(400, "artifact_id 必须是材料编号或 null")
    if action != "seed_template" and (not isinstance(body.get("note", ""), str) or action in ("withdraw", "verify") and not body.get("note", "").strip()):
        raise ApiError(400, "请完整填写核对依据或撤回原因")
    if action == "verify" and (not isinstance(body.get("source_token"), str) or not re.fullmatch(r"[0-9a-f]{64}", body["source_token"])):
        raise ApiError(400, "请先读取当前行的 source_token")
    if action == "seed_template" and body.get("template_id") != TEMPLATE_ID:
        raise ApiError(400, "请选择内置软件交付模板 software-delivery-v1")
    return action


def _save_item(db, did, values, stamp, template_key=""):
    return db.execute("INSERT INTO delivery_coverage_items(delivery_id,title,requirement,required,artifact_id,note,binding,created,updated,template_key) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (did, values["title"], values["requirement"], int(values["required"]), values["artifact_id"], values.get("note", ""), _json(values["binding"]), stamp, stamp, template_key)).lastrowid


def act(P, did, body, actor):
    action = _validate(body)
    with _transaction(P.store) as db:
        d, project = _delivery(P, did)
        _authorize(P, actor, project, True)
        fingerprint = _hash({"delivery_id": did, "body": body})
        old = db.execute("SELECT * FROM delivery_coverage_requests WHERE actor=? AND request_id=?", (actor, body["request_id"])).fetchone()
        if old:
            if old["delivery_id"] != did or old["fingerprint"] != fingerprint:
                raise ApiError(409, "同一请求编号已用于不同内容")
            receipt = dict(json.loads(old["receipt"]), replayed=True)
            return dict(_read(P, d, project, actor), receipt=receipt)
        head = db.execute("SELECT revision FROM delivery_coverage_heads WHERE delivery_id=?", (did,)).fetchone()
        revision = head["revision"] if head else 0
        if revision != body["revision"]:
            raise ApiError(409, "覆盖表已更新，请刷新后再操作")
        facts = _facts(P, d, project)
        stamp, before, ids = _now(), [], []
        if action in ("add", "update"):
            values = dict(body, binding=_binding(facts, body["artifact_id"]))
            if values["binding"]:
                a = values["binding"]["artifact"]
                if a["stage"] not in d["stages"] or facts["latest"][a["stage"]]["id"] != a["id"]:
                    raise ApiError(409, "只能绑定当前阶段的最新材料")
        if action in ("update", "withdraw", "verify"):
            raw = db.execute("SELECT * FROM delivery_coverage_items WHERE id=? AND delivery_id=?", (body["item_id"], did)).fetchone()
            if not raw:
                raise ApiError(404, "覆盖行不属于当前交付")
            row = _row(raw)
            before = [row]
            if row["withdrawn"]:
                raise ApiError(409, "已撤回的覆盖行保持历史，不能再次修改或核对")
            ids = [row["id"]]
        if action == "add":
            ids = [_save_item(db, did, values, stamp)]
        elif action == "update":
            db.execute("UPDATE delivery_coverage_items SET title=?,requirement=?,required=?,artifact_id=?,note=?,binding=?,verification=NULL,updated=? WHERE id=?",
                       (values["title"], values["requirement"], int(values["required"]), values["artifact_id"], values.get("note", ""), _json(values["binding"]), stamp, row["id"]))
        elif action == "withdraw":
            db.execute("UPDATE delivery_coverage_items SET withdrawn=1,withdraw_reason=?,updated=? WHERE id=?", (body["note"], stamp, row["id"]))
        elif action == "verify":
            current = _present(row, facts, True)
            if not current["can_verify"] or current["source_token"] != body["source_token"]:
                raise ApiError(409, "材料或覆盖要求已变化或缺失，请刷新并重新绑定后核对")
            verification = {"actor": actor, "note": body["note"], "created": stamp, "source_token": current["source_token"]}
            # Do not update the content timestamp: it is part of the exact row
            # token being acknowledged. The event/verification have their own time.
            db.execute("UPDATE delivery_coverage_items SET verification=? WHERE id=?", (_json(verification), row["id"]))
        else:
            keys = {r["template_key"] for r in db.execute("SELECT template_key FROM delivery_coverage_items WHERE delivery_id=?", (did,))}
            for item in TEMPLATE:
                key = TEMPLATE_ID + ":" + item["key"]
                if item["stage"] not in d["stages"] or key in keys:
                    continue
                ids.append(_save_item(db, did, dict(item, required=True, artifact_id=None, note="", binding=None), stamp, key))
            if not ids:
                raise ApiError(409, "当前阶段没有尚未插入的模板项；重复点击不会复制已存在或已撤回的项")
        revision += 1
        db.execute("INSERT INTO delivery_coverage_heads VALUES(?,?) ON CONFLICT(delivery_id) DO UPDATE SET revision=excluded.revision", (did, revision))
        after = [_row(db.execute("SELECT * FROM delivery_coverage_items WHERE id=?", (iid,)).fetchone()) for iid in ids]
        db.execute("INSERT INTO delivery_coverage_events(delivery_id,revision,action,actor,note,created,before_json,after_json) VALUES(?,?,?,?,?,?,?,?)",
                   (did, revision, action, actor, body.get("note", ""), stamp, _json(before), _json(after)))
        receipt = {"request_id": body["request_id"], "action": action, "revision": revision, "item_ids": ids, "replayed": False}
        db.execute("INSERT INTO delivery_coverage_requests VALUES(?,?,?,?,?,?)", (actor, body["request_id"], did, fingerprint, _json(receipt), stamp))
        return dict(_read(P, d, project, actor, facts), receipt=receipt)
