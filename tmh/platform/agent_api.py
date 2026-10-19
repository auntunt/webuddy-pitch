"""Typed agent workbench operations behind the platform's existing HTTP authentication.

An agent name is an audit label, never a human approval or an authentication
credential. The durable journal deliberately fails closed after an uncertain
write: reconnecting a model must not silently launch a second execution.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

from ..agent_contract import SPECS
from .errors import ApiError
from .store import now, _keyed


WRITES = frozenset(name for name, spec in SPECS.items() if spec["write"])
EXECUTIONS = frozenset(name for name, spec in SPECS.items() if spec["execution"])
BOUNDARIES = {
    "identity": "agent audit labels are self-declared; server authentication is separate",
    "messages": "durable ticket messages, not delivery to an external running assistant; recipients poll messages_list",
    "approval": "agent actions never record human acceptance, review, merge, or release",
    "candidate": "immutable external candidates support independent verification, preview and technical assessment; human decisions use the operator CLI",
    "execution": "execution requires X-Webuddy-Execution: 1; runs remain subject to existing lifecycle and verification controls",
}


def _schema(st):
    from .candidates import schema
    schema(st)
    with st.lock:
        st.db.execute("""CREATE TABLE IF NOT EXISTS agent_requests (
          agent TEXT NOT NULL, request_id TEXT NOT NULL, operation TEXT NOT NULL,
          fingerprint TEXT NOT NULL, arguments TEXT NOT NULL, resource TEXT NOT NULL,
          state TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
          created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(agent, request_id))""")
        st.db.execute("""CREATE TABLE IF NOT EXISTS agent_run_sources (
          run_id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, requirement_hash TEXT NOT NULL,
          agent TEXT NOT NULL, created TEXT NOT NULL)""")
        st.db.commit()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _requirement(t, store):
    """Bind requirement sources, including conversation and the client contract.

    This is deliberately conservative: even an informational comment invalidates
    a previous plan. It is not a hash of all repository/model context or proof
    that every source was understood. Keep full source records, not prompt clips.
    """
    from .signoff import records
    links = t.get("links") or {}
    discussion = store.q("SELECT * FROM events WHERE ticket_id=? AND kind IN ('comment','reject','conflict') ORDER BY id", (t["id"],))
    contracts = [record for record in records(store.path.parent, t["key"]) if record["kind"] == "intake"]
    return _digest({"schema": 2, "ticket": t["id"], "title": t["title"], "body": t["body"], "type": t["type"],
                    "priority": t["priority"], "reporter": t.get("reporter"), "external": t.get("external"),
                    "discussion": discussion, "client_contract": contracts[-1] if contracts else None,
                    "source": {k: links.get(k) for k in ("base", "code_at", "flows", "delivery", "delivery_plan_run")}})


def _actor(req):
    value = req.h.headers.get("X-Webuddy-Agent", "")
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
        raise ApiError(400, "X-Webuddy-Agent 必须是 1–32 位字母、数字、下划线或连字符；不能使用人的登录名代替智能体标识")
    return "agent:" + value


def _ticket(P, key):
    t = P.store.ticket(key)
    if not t:
        raise ApiError(404, "没有这个工单")
    return t


def _project(P, key):
    p = P.store.project(key)
    if not p:
        raise ApiError(404, "没有这个项目")
    return p


def _run(P, rid):
    r = P.store.run(rid)
    if not r:
        raise ApiError(404, "没有这个运行")
    return r


def _req(req, actor, body=None, query=None):
    q = query or {}
    return SimpleNamespace(h=req.h, body=body or {}, user=actor, query=q,
                           arg=lambda key: (q.get(key) or [""])[0])


def _resource(P, operation, args):
    if "candidate_id" in args:
        from .candidates import _row
        return "ticket:%d" % _row(P, args["candidate_id"])["ticket_id"]
    if "ticket" in args:
        return "ticket:%d" % _ticket(P, args["ticket"])["id"]
    if "run_id" in args:
        r = _run(P, args["run_id"])
        return "ticket:%d" % r["ticket_id"] if r["ticket_id"] else "run:%d" % r["id"]
    if operation == "ticket_create":
        return "project:%d:create" % _project(P, args["project"])["id"]
    return ""


def _receipt(row):
    return {"request_id": row["request_id"], "operation": row["operation"], "agent": row["agent"],
            "state": row["state"], "created": row["created"], "updated": row["updated"],
            "arguments": json.loads(row["arguments"]), "resource": row["resource"],
            "needs_reconcile": row["state"] in ("pending", "uncertain"),
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": json.loads(row["error"]) if row["error"] else None}


def _replay(row):
    if row["state"] == "complete":
        return json.loads(row["result"])
    if row["state"] == "failed":
        error = json.loads(row["error"])
        raise ApiError(error["code"], error["message"])
    raise ApiError(409, "needs_reconcile: 请求 %s 的执行结果尚未确认；先用 request_get 核对运行、工单和原始回执，不能自动重发新请求" % row["request_id"])


def _write(P, req, actor, operation, args):
    st = P.store
    request_id = args["request_id"]
    fingerprint = _digest({"operation": operation, "arguments": args})
    resource = _resource(P, operation, args)
    with st.lock:
        try:
            st.db.execute("BEGIN IMMEDIATE")
            row = st.db.execute("SELECT * FROM agent_requests WHERE agent=? AND request_id=?", (actor, request_id)).fetchone()
            if row:
                st.db.commit()
                if row["fingerprint"] != fingerprint:
                    raise ApiError(409, "同一 request_id 已用于不同操作或内容，请保留原回执并为新操作使用新编号")
                return _replay(row)
            # A lost launch receipt must prevent another launch, but must never
            # prevent stopping that run or discussing what happened. Cancellation
            # and message receipts do not themselves own an execution resource.
            pending = None
            if operation not in ("run_cancel", "candidate_cancel", "message_send"):
                pending = st.db.execute("SELECT request_id FROM agent_requests WHERE resource=? AND state IN ('pending','uncertain') AND operation IN ('ticket_create','run_start','run_retry','run_recheck','preview_start','candidate_submit','candidate_verify','candidate_preview','candidate_decide','candidate_assess') LIMIT 1", (resource,)).fetchone()
            if pending:
                raise ApiError(409, "needs_reconcile: 此对象还有未确认的请求 %s；先核对原始回执，不会开始重复操作" % pending["request_id"])
            ts = now()
            st.db.execute("INSERT INTO agent_requests(agent,request_id,operation,fingerprint,arguments,resource,state,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                          (actor, request_id, operation, fingerprint, _json(args), resource, "pending", ts, ts))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise
    try:
        req.agent_side_effect_started = False
        result = _execute(P, req, actor, operation, args)
    except ApiError as exc:
        # Only failures before entering a mutating helper are known not to have
        # acted. An ApiError alone does not prove a write never happened.
        uncertain = getattr(req, "agent_side_effect_started", False)
        st.x("UPDATE agent_requests SET state=?,error=?,updated=? WHERE agent=? AND request_id=?",
             ("uncertain" if uncertain else "failed", _json({"code": exc.code, "message": str(exc)}), now(), actor, request_id))
        if uncertain:
            raise ApiError(409, "needs_reconcile: 操作返回错误且可能已产生结果；请用 request_get 核对，不能自动重复执行") from exc
        raise
    except Exception as exc:
        # An unexpected exception can follow an already committed side effect.
        st.x("UPDATE agent_requests SET state='uncertain',error=?,updated=? WHERE agent=? AND request_id=?",
             (_json({"code": 500, "message": "执行结果未确认", "type": type(exc).__name__}), now(), actor, request_id))
        raise ApiError(409, "needs_reconcile: 执行结果未确认；请用 request_get 核对，不能自动重复执行") from exc
    st.x("UPDATE agent_requests SET state='complete',result=?,updated=? WHERE agent=? AND request_id=?",
         (_json(result), now(), actor, request_id))
    return result


def dispatch(P, req, operation):
    from ..agent_contract import validate
    operator = bool(SPECS.get(operation, {}).get("operator"))
    if operator:
        if req.h.headers.get("X-Webuddy-Operator") != "1" or req.h.headers.get("X-Webuddy-Agent"):
            raise ApiError(403, "此操作仅供明确确认的操作者终端，Agent/MCP不能代签")
        from .operator_access import require
        require(P, req.h.headers)
        from .signoff import human
        if not human(req.user):
            raise ApiError(403, "当前登录身份不是人工操作者")
        actor = "operator:" + req.user
    else:
        actor = _actor(req)
    try:
        args = validate(operation, req.body)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    if operation in EXECUTIONS and req.h.headers.get("X-Webuddy-Execution") != "1":
        raise ApiError(403, "此操作会启动模型、构建或预览进程；客户端需显式启用执行权限 X-Webuddy-Execution: 1")
    _schema(P.store)
    if operation in WRITES:
        return _write(P, req, actor, operation, args)
    return _execute(P, req, actor, operation, args)


def _page(rows, limit, after=0):
    more = len(rows) > limit
    items = rows[:limit]
    return {"items": items, "has_more": more, "next_after": items[-1]["id"] if items else after}


def _ready(P, t):
    from . import epic
    if t["status"] == "closed":
        raise ApiError(409, "工单已关闭，请先明确新的需求")
    why = epic.refuse(t, "run")
    if why:
        raise ApiError(409, why)
    if (t.get("links") or {}).get("delivery"):
        raise ApiError(409, "交付工单必须从交付阶段页执行，不能绕过已复核方案、固定版本和阶段条件")
    if (t.get("links") or {}).get("later"):
        raise ApiError(409, "此工单仍在等待上游步骤：%s" % t["links"]["later"])
    if not (t.get("links") or {}).get("hold"):
        raise ApiError(409, "此工单仍由自动流程管理；请先在现有工单页认领，再启动独立智能体执行，避免并行改动或自动采纳")
    active = P.store.one("SELECT id FROM runs WHERE ticket_id=? AND status IN ('queued','running')", (t["id"],))
    if active:
        raise ApiError(409, "同一工单已有运行 #%d；先等待或停止它" % active["id"])
    # A fresh request ID must not bypass retry_state's process cleanup boundary.
    # Cancellation changes the database status before all descendants exit.
    for old in P.store.q("SELECT id,started FROM runs WHERE ticket_id=? AND status IN ('failed','cancelled')", (t["id"],)):
        rid = old["id"]
        path = Path(P.data_dir) / "runs" / str(rid) / "lifecycle.json"
        clean = rid not in P.runner.procs
        try:
            life = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(life, dict):
                raise ValueError("invalid lifecycle")
            clean = clean and life.get("finished") is True
            recovery = life.get("recovery")
            clean = clean and (recovery is None or isinstance(recovery, dict) and recovery.get("state") == "complete")
            attempts = life.get("attempts")
            clean = clean and isinstance(attempts, list)
            if isinstance(attempts, list):
                for attempt in attempts:
                    clean = clean and isinstance(attempt, dict)
                    if isinstance(attempt, dict) and (attempt.get("pid") is not None or attempt.get("supervised")):
                        clean = clean and isinstance(attempt.get("cleanup"), dict) and attempt["cleanup"].get("complete") is True
        except FileNotFoundError:
            clean = clean and not old["started"]
        except (OSError, ValueError, UnicodeError):
            clean = False
        if not clean:
            raise ApiError(409, "运行 #%d 的停止或进程回收回执尚未完整；先读取 run_get 并完成原运行的停止检查，不能换请求编号绕过" % rid)


def _execute(P, req, actor, operation, a):
    from . import server
    st = P.store
    if operation.startswith("candidate_") or operation == "candidates_list":
        from .candidates import execute
        try:
            return execute(P, actor, operation, a, lambda: setattr(req, "agent_side_effect_started", True))
        except ValueError as exc:
            raise ApiError(409, str(exc)) from exc
    if operation == "status":
        meta = server.api_meta(P, _req(req, actor))
        return {"version": meta["version"], "agent": actor, "workspace": str(P.data_dir),
                "engines": meta["agents"], "boundaries": dict(BOUNDARIES)}
    if operation == "projects_list":
        return _page(st.q("SELECT * FROM projects WHERE id>? ORDER BY id LIMIT ?", (a.get("after", 0), a.get("limit", 20) + 1)), a.get("limit", 20), a.get("after", 0))
    if operation == "tickets_list":
        sql = "SELECT t.*,p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id WHERE t.id>?"
        values = [a.get("after", 0)]
        if a.get("project"):
            sql += " AND t.project_id=?"
            values.append(_project(P, a["project"])["id"])
        if a.get("status"):
            sql += " AND t.status=?"
            values.append(a["status"])
        if a.get("q"):
            sql += " AND (instr(t.title,?)>0 OR instr(t.body,?)>0)"
            values += [a["q"], a["q"]]
        limit = a.get("limit", 20)
        return _page([_keyed(row) for row in st.q(sql + " ORDER BY t.id LIMIT ?", values + [limit + 1])], limit, a.get("after", 0))
    if operation == "ticket_get":
        from .. import config
        from .agents import git, is_git
        t = _ticket(P, a["ticket"])
        p = _project(P, t["project_id"])
        root = Path(p["root"])
        packet = server.api_ticket(P, _req(req, actor), t["key"])
        # The web view intentionally loads only its newest 100 runs. An agent
        # packet must not silently hide older evidence: return every reference,
        # with run_get available for full logs, prompts and lifecycle receipts.
        enriched = {r["id"]: r for r in packet["runs"]}
        refs = st.q("SELECT id,ticket_id,project_id,agent,mode,status,author,created,started,ended,exit_code,target,decision,result,session_id,batch,model FROM runs WHERE ticket_id=? ORDER BY id DESC", (t["id"],))
        packet["runs"] = [enriched.get(r["id"], r) for r in refs]
        packet["repository"] = {"root": str(root), "head": git(root, "rev-parse", "HEAD", check=False).strip() if is_git(root) else "",
                                "commands": config.load(root).get("commands") or {}}
        packet["preview"] = server.api_preview(P, _req(req, actor), t["key"])
        packet["evidence_state"] = server.api_evidence(P, _req(req, actor), t["key"])
        packet["boundaries"] = dict(BOUNDARIES)
        packet["requirement_hash"] = _requirement(t, st)
        packet["external_candidates"] = st.q("SELECT id,run_id,commit_sha,base_commit,agent,created FROM code_candidates WHERE ticket_id=? ORDER BY id DESC", (t["id"],))
        packet["supported_actions"] = ["message_send", "messages_list", "run_get", "preview_get", "candidates_list", "candidate_get"] + ([] if t["status"] == "closed" or (t.get("links") or {}).get("delivery") else ["run_start", "candidate_submit"])
        return packet
    if operation == "ticket_create":
        p = _project(P, a["project"])
        req.agent_side_effect_started = True
        t = st.create_ticket(p["id"], a["title"], actor, body=a["body"], type=a.get("type", "feature"),
                             assignee=actor, links={"hold": actor, "handwork": actor, "agent_request": a["request_id"]})
        return {"ticket": t, "execution_started": False, "request_id": a["request_id"]}
    if operation == "message_send":
        t = _ticket(P, a["ticket"])
        reply = a.get("reply_to")
        if reply is not None:
            parent = st.one("SELECT id,ticket_id FROM events WHERE id=?", (reply,))
            if not parent or parent["ticket_id"] != t["id"]:
                raise ApiError(400, "reply_to 必须引用同一工单中的消息或事件")
        recipient = a.get("to_agent", "*")
        if recipient != "*" and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", recipient):
            raise ApiError(400, "to_agent 必须是智能体标识或 *")
        data = {"agent_message": True, "from_agent": actor[6:], "to_agent": recipient,
                "message_kind": a.get("kind", "note"), "reply_to": reply, "request_id": a["request_id"]}
        req.agent_side_effect_started = True
        eid = st.event(t["id"], actor, "comment", a["body"], data)
        st.x("UPDATE tickets SET updated=? WHERE id=?", (now(), t["id"]))
        return {"event_id": eid, "ticket": t["key"], "body": a["body"], "data": data,
                "delivery": "persisted; recipient must poll messages_list", "request_id": a["request_id"]}
    if operation == "messages_list":
        sql = "SELECT e.*,p.key || '-' || t.num AS ticket FROM events e JOIN tickets t ON t.id=e.ticket_id JOIN projects p ON p.id=t.project_id WHERE e.id>? AND e.kind='comment'"
        values = [a.get("after", 0)]
        if a.get("ticket"):
            sql += " AND e.ticket_id=?"
            values.append(_ticket(P, a["ticket"])["id"])
        # SQLite's JSON functions filter metadata, preserving each complete body.
        sql += " AND json_valid(e.data) AND json_extract(e.data,'$.agent_message')=1"
        if a.get("to_agent"):
            sql += " AND json_extract(e.data,'$.to_agent') IN (?, '*')"
            values.append(a["to_agent"])
        limit = a.get("limit", 20)
        return _page(st.q(sql + " ORDER BY e.id LIMIT ?", values + [limit + 1]), limit, a.get("after", 0))
    if operation == "run_get":
        return server.api_run(P, _req(req, actor, query={"since": [str(a.get("since", 0))]}), str(a["run_id"]))
    if operation == "run_start":
        from .agents import git, load_config, pick_model
        from .fixloop import plan_ac
        with P.runner.lock:
            t = _ticket(P, a["ticket"])
            _ready(P, t)
            p = _project(P, t["project_id"])
            conf = load_config(P.data_dir)
            if a["engine"] not in conf:
                raise ApiError(400, "没有这个执行器；请先调用 status 查看可用执行器")
            try:
                pick_model(conf[a["engine"]], a["mode"], a.get("model"))
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            base = ""
            requirement_hash = _requirement(t, st)
            if a["mode"] == "fix":
                plan = st.one("SELECT * FROM runs WHERE ticket_id=? AND mode='plan' ORDER BY id DESC LIMIT 1", (t["id"],))
                binding = st.one("SELECT * FROM agent_run_sources WHERE run_id=?", (plan["id"],)) if plan else None
                if not plan or plan["status"] != "done" or plan["exit_code"] != 0 or not plan_ac(plan["result"]) or not binding or binding["requirement_hash"] != requirement_hash:
                    raise ApiError(409, "需要先通过此接口为当前完整需求运行 plan，取得成功且含可检查验收标准的方案；旧方案或需求已变化时不能直接改代码")
                chosen = None
                for fn in P.flow.bases:
                    try:
                        chosen = fn(p, t)
                    except Exception as exc:
                        raise ApiError(409, "不能确定代码起点，未启动修改") from exc
                    if chosen is not None:
                        break
                chosen = chosen if chosen is not None else (t.get("links") or {}).get("base") or "HEAD"
                base = git(Path(p["root"]), "rev-parse", "--verify", str(chosen or "HEAD") + "^{commit}", check=False).strip()
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
                    raise ApiError(409, "代码起点无法解析，未启动修改")
            try:
                req.agent_side_effect_started = True
                r = P.runner.start(p, t, a["engine"], a["mode"], actor, model=a.get("model"), base=base)
            except ValueError as exc:
                raise ApiError(409, str(exc)) from exc
            st.x("INSERT INTO agent_run_sources(run_id,ticket_id,requirement_hash,agent,created) VALUES(?,?,?,?,?)",
                 (r["id"], t["id"], requirement_hash, actor, now()))
            return {"run": r, "request_id": a["request_id"], "human_acceptance": False}
    if operation == "run_cancel":
        _run(P, a["run_id"])
        req.agent_side_effect_started = True
        return server.api_cancel(P, _req(req, actor), str(a["run_id"]))
    if operation == "run_retry":
        r = _run(P, a["run_id"])
        if not r["ticket_id"]:
            raise ApiError(409, "此入口只能接续已认领工单的运行")
        _ready(P, _ticket(P, r["ticket_id"]))
        t = _ticket(P, r["ticket_id"])
        requirement_hash = _requirement(t, st)
        binding = st.one("SELECT * FROM agent_run_sources WHERE run_id=?", (r["id"],))
        if (binding and binding["requirement_hash"] != requirement_hash) or (r["mode"] == "fix" and not binding):
            raise ApiError(409, "原运行未绑定当前需求；请先为当前需求运行新方案，不能用旧上下文直接接续改代码")
        retry = P.runner.retry_state(r["id"])
        if not retry["can_retry"]:
            raise ApiError(409, "；".join(retry["retry_blocked"]))
        req.agent_side_effect_started = True
        retried = server.api_retry_run(P, _req(req, actor), str(a["run_id"]))
        st.x("INSERT INTO agent_run_sources(run_id,ticket_id,requirement_hash,agent,created) VALUES(?,?,?,?,?)",
             (retried["id"], t["id"], requirement_hash, actor, now()))
        return retried
    if operation == "run_recheck":
        r = _run(P, a["run_id"])
        if not r["ticket_id"] or not (st.ticket(r["ticket_id"]).get("links") or {}).get("hold"):
            raise ApiError(409, "独立重新验证要求工单处于已认领状态，避免自动流程在检查后采纳代码")
        _ready(P, _ticket(P, r["ticket_id"]))
        if r["mode"] != "fix" or r["status"] != "done" or not r["diff"] or (r["decision"] and not r["decision"].startswith("accepted:")):
            raise ApiError(409, "这次运行没有可以重新验证的改动")
        req.agent_side_effect_started = True
        return server.api_recheck(P, _req(req, actor), str(a["run_id"]))
    if operation == "preview_get":
        query = {"run_id": [str(a["run_id"])]} if "run_id" in a else {}
        return server.api_preview(P, _req(req, actor, query=query), a["ticket"])
    if operation == "preview_start":
        from .preview import run_binding
        run_binding(P, _ticket(P, a["ticket"]), a["run_id"])
        req.agent_side_effect_started = True
        return server.api_preview_do(P, _req(req, actor, body={"action": "start", "run_id": a["run_id"]}), a["ticket"])
    if operation == "request_get":
        row = st.one("SELECT * FROM agent_requests WHERE agent=? AND request_id=?", (actor, a["request_id"]))
        if not row:
            raise ApiError(404, "此智能体没有这个请求回执")
        return _receipt(row)
    raise ApiError(400, "未知的智能体操作")
