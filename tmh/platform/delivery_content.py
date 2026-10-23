"""Atomic personal drafting of delivery materials without callbacks or execution.

This deliberately separate entry point never reviews a stage, collects a run,
invokes Git or uses delivery's lazy schema/view functions. Existing execution
and acceptance paths retain their own gates.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid

from . import delivery, delivery_coverage as C
from .errors import ApiError
from .store import now

BOUNDARY = "这里仅创建交付和保存手工材料，不执行模型、构建或测试，不产生阶段复核、验收或关单。"
DDL = (
    """CREATE TABLE IF NOT EXISTS delivery_content_heads (
        delivery_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS delivery_content_requests (
        actor TEXT NOT NULL, request_id TEXT NOT NULL, delivery_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL, receipt TEXT NOT NULL, created TEXT NOT NULL,
        PRIMARY KEY(actor,request_id))""",
)


def _legacy_statements():
    # complete_statement handles SQL quoted semicolons; no executescript or
    # implicit commit, and an unexpected multi-statement line fails closed.
    pending = ""
    for line in delivery.SCHEMA.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise RuntimeError("incomplete legacy delivery schema")


def schema(store):
    with C._transaction(store) as db:
        for statement in _legacy_statements():
            db.execute(statement)
        columns = {r["name"] if isinstance(r, dict) else r[1] for r in db.execute("PRAGMA table_info(delivery_runs)")}
        if "binding" not in columns:
            db.execute("ALTER TABLE delivery_runs ADD COLUMN binding TEXT NOT NULL DEFAULT '{}'")
        for statement in DDL:
            db.execute(statement)


def _development(P, project):
    from .project_library import require_development
    try:
        require_development(P.store, project)
    except ValueError as exc:
        raise ApiError(403, str(exc)) from exc


def _authorize(P, actor, project, write=False):
    C._authorize(P, actor, project, write)
    if write:
        _development(P, project)


def _can_edit(P, actor, project):
    try:
        _authorize(P, actor, project, True)
        return True
    except ApiError:
        return False


def _source(facts):
    return C._hash({"delivery": facts["delivery"], "project": facts["project"],
                    "artifacts": [C._artifact_identity(a) for a in facts["artifacts"]],
                    "reviews": facts["reviews"], "runs": facts["runs_by_id"]})


def _busy(P, did):
    return bool(P.store.db.execute("SELECT 1 FROM delivery_runs d JOIN runs r ON r.id=d.run_id WHERE d.delivery_id=? AND r.status IN ('queued','running') LIMIT 1", (did,)).fetchone())


def _read(P, d, project, actor, facts=None):
    facts = facts or C._facts(P, d, project)
    head = P.store.db.execute("SELECT revision FROM delivery_content_heads WHERE delivery_id=?", (d["id"],)).fetchone()
    can_edit = _can_edit(P, actor, project)
    busy = _busy(P, d["id"])
    stages = []
    for key in d["stages"]:
        materials = [a for a in facts["artifacts"] if a["stage"] == key]
        stages.append({"key": key, "name": delivery.STAGE[key]["name"],
                       "artifact": materials[-1] if materials else None, "history": materials[:-1],
                       "version": materials[-1]["version"] if materials else 0,
                       "can_save": can_edit and not busy,
                       "blocked": "交付已有阶段正在运行，请完成后再录入材料" if busy else ""})
    ticket = P.store.db.execute("SELECT num FROM tickets WHERE id=? AND project_id=?", (d["ticket_id"],project["id"])).fetchone() if d["ticket_id"] else None
    summary = {k:d[k] for k in ("id","title","goal","type","created","updated","ticket_id")}
    summary.update(project=project["key"],project_id=project["id"],project_name=project["name"],
                   type_name=delivery.TYPE[d["type"]],stages=d["stages"],
                   ticket=project["key"]+"-"+str(ticket["num"]) if ticket else "")
    return {"delivery":summary,"revision":head["revision"] if head else 0,
            "source_token":_source(facts),"stages":stages,"can_edit":can_edit,
            "boundary":BOUNDARY,"technical_review_evaluated":False}


def read(P, did, actor):
    with C._snapshot(P.store):
        d,project=C._delivery(P,did)
        _authorize(P,actor,project)
        return _read(P,d,project,actor)


def _validate(body, action):
    if not isinstance(body,dict) or body.get("action")!=action:
        raise ApiError(400,"请选择有效的手工交付操作")
    fields={"action","request_id","revision"}
    fields |= {"project","type","title","goal","stages"} if action=="create" else {"source_token","stage","title","body"}
    if set(body)-fields:
        raise ApiError(400,"不能自报身份、复核、执行或工单分配字段")
    if not isinstance(body.get("request_id"),str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",body["request_id"]):
        raise ApiError(400,"需要稳定 request_id，重试请使用原编号和完整内容")
    if type(body.get("revision")) is not int or not 0<=body["revision"]<2**63:
        raise ApiError(400,"需要当前 revision")
    if action=="create" and body["revision"]!=0:
        raise ApiError(409,"新建交付的起始 revision 必须是 0")
    delivery._text(body.get("title"),"标题",160)
    if action=="create":
        if not isinstance(body.get("project"),str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,9}",body["project"]):
            raise ApiError(400,"请选择实际项目")
        delivery._text(body.get("goal"),"目标",24_000)
        if not isinstance(body.get("type"),str) or body["type"] not in delivery.TYPE:
            raise ApiError(400,"请选择有效的交付类型")
        selected=body.get("stages",delivery.DEFAULTS.get(body["type"],list(delivery.STAGE)))
        if not isinstance(selected,list) or not selected or any(not isinstance(k,str) or k not in delivery.STAGE for k in selected) or len(set(selected))!=len(selected):
            raise ApiError(400,"阶段必须是有效且不重复的列表")
        if "develop" in selected and not {"requirements","design"}.issubset(selected):
            raise ApiError(400,"实现阶段必须包含需求与设计阶段")
    else:
        if not isinstance(body.get("stage"),str) or body["stage"] not in delivery.STAGE:
            raise ApiError(400,"请选择有效阶段")
        delivery._text(body.get("body"),"材料正文",delivery.MAX_BODY)
        if not isinstance(body.get("source_token"),str) or not re.fullmatch(r"[0-9a-f]{64}",body["source_token"]):
            raise ApiError(400,"请先读取完整当前材料和 source_token")


def _receipt(db, actor, body, did, fingerprint, revision, ticket, artifact_id=None):
    receipt={"request_id":body["request_id"],"action":body["action"],"delivery_id":did,
             "revision":revision,"ticket":ticket,"artifact_id":artifact_id,"replayed":False}
    db.execute("INSERT INTO delivery_content_requests VALUES(?,?,?,?,?,?)",(actor,body["request_id"],did,fingerprint,C._json(receipt),C._now()))
    return receipt


def _replay(P, db, actor, body, fingerprint, expected_did=None):
    old=db.execute("SELECT * FROM delivery_content_requests WHERE actor=? AND request_id=?",(actor,body["request_id"])).fetchone()
    if not old:
        return None
    if old["fingerprint"]!=fingerprint or expected_did is not None and old["delivery_id"]!=expected_did:
        raise ApiError(409,"同一请求编号已用于不同内容")
    d,project=C._delivery(P,old["delivery_id"])
    _authorize(P,actor,project,True)
    return dict(_read(P,d,project,actor),receipt=dict(json.loads(old["receipt"]),replayed=True))


def create(P, body, actor):
    _validate(body,"create")
    with C._transaction(P.store) as db:
        project=P.store.project(body["project"])
        if not project:
            raise ApiError(404,"没有这个项目")
        _authorize(P,actor,project,True)
        fingerprint=C._hash({"operation":"create","body":body})
        replay=_replay(P,db,actor,body,fingerprint)
        if replay:
            return replay
        did=uuid.uuid4().hex[:12]
        stamp=now()
        selected=body.get("stages",delivery.DEFAULTS.get(body["type"],list(delivery.STAGE)))
        selected=[k for k in delivery.STAGE if k in selected]
        number=(db.execute("SELECT MAX(num) AS number FROM tickets WHERE project_id=?",(project["id"],)).fetchone()["number"] or 0)+1
        links={"delivery":did,"hold":delivery._owned_hold(did)}
        if body["type"]=="new_product":
            links["greenfield"]=True
        tid=db.execute("INSERT INTO tickets(project_id,num,title,body,type,status,priority,assignee,reporter,labels,links,external,created,updated) VALUES(?,?,?,?,?,'new','normal','',?,'[]',?,'{}',?,?)",
                       (project["id"],number,body["title"],"## 交付目标\n"+body["goal"],"bug" if body["type"]=="bugfix" else "feature",actor,C._json(links),stamp,stamp)).lastrowid
        db.execute("INSERT INTO delivery_items(id,project_id,type,title,goal,stages,ticket_id,created,updated,author) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (did,project["id"],body["type"],body["title"],body["goal"],C._json(selected),tid,stamp,stamp,actor))
        db.execute("INSERT INTO delivery_content_heads VALUES(?,1)",(did,))
        for kind,text in (("created","创建工单"),("delivery","手工创建交付；材料草稿不代表执行或验收，普通自动处理保持暂停")):
            db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",(tid,stamp,actor,kind,text,C._json({"delivery":did,"request_id":body["request_id"],"execution":False})))
        ticket=project["key"]+"-"+str(number)
        receipt=_receipt(db,actor,body,did,fingerprint,1,ticket)
        d,project=C._delivery(P,did)
        return dict(_read(P,d,project,actor),receipt=receipt)


def _manual_inputs(d, facts, stage):
    # Pure existing dependency rules; no run receives verification/acceptance
    # from this content editor. Code-source gates are deliberately unresolved.
    artifacts={key:[dict(a) for a in facts["artifacts"] if a["stage"]==key] for key in d["stages"]}
    rows=delivery._stage_rows(d,artifacts,facts["reviews"],{key:[] for key in d["stages"]})
    return delivery._inputs(rows,stage,d["stages"])


def act(P, did, body, actor):
    _validate(body,"save_artifact")
    with C._transaction(P.store) as db:
        d,project=C._delivery(P,did)
        _authorize(P,actor,project,True)
        fingerprint=C._hash({"operation":"save_artifact","delivery_id":did,"body":body})
        replay=_replay(P,db,actor,body,fingerprint,did)
        if replay:
            return replay
        head=db.execute("SELECT revision FROM delivery_content_heads WHERE delivery_id=?",(did,)).fetchone()
        revision=head["revision"] if head else 0
        if revision!=body["revision"]:
            raise ApiError(409,"交付材料已更新，请刷新后再保存")
        facts=C._facts(P,d,project)
        if _source(facts)!=body["source_token"]:
            raise ApiError(409,"材料、关联运行或复核已变化，请完整重读后再保存")
        stage=body["stage"]
        if stage not in d["stages"]:
            raise ApiError(400,"这个交付没有选择该阶段")
        if _busy(P,did):
            raise ApiError(409,"交付已有阶段正在运行，请完成后再录入材料")
        latest=facts["latest"].get(stage)
        version=(latest["version"] if latest else 0)+1
        stamp=now()
        aid=db.execute("INSERT INTO delivery_artifacts(delivery_id,stage,version,title,body,created,author,source_run,inputs) VALUES(?,?,?,?,?,?,?,NULL,?)",
                       (did,stage,version,body["title"],body["body"],stamp,actor,C._json(_manual_inputs(d,facts,stage)))).lastrowid
        db.execute("UPDATE delivery_items SET updated=? WHERE id=?",(stamp,did))
        revision+=1
        db.execute("INSERT INTO delivery_content_heads VALUES(?,?) ON CONFLICT(delivery_id) DO UPDATE SET revision=excluded.revision",(did,revision))
        if d["ticket_id"]:
            ticket=db.execute("SELECT id FROM tickets WHERE id=? AND project_id=?",(d["ticket_id"],project["id"])).fetchone()
            if not ticket:
                raise ApiError(409,"交付关联工单与项目不一致")
            db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                       (d["ticket_id"],stamp,actor,"delivery_material","保存手工材料草稿「"+body["title"]+"」；未执行或复核",C._json({"delivery":did,"artifact_id":aid,"version":version,"request_id":body["request_id"],"revision":revision,"execution":False})))
        d,project=C._delivery(P,did)
        result=_read(P,d,project,actor)
        receipt=_receipt(db,actor,body,did,fingerprint,revision,result["delivery"]["ticket"],aid)
        return dict(result,receipt=receipt)
