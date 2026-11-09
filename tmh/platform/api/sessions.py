"""Routes: intake, path maps, pins, ticket ops, survey, assistant, sessions."""
from __future__ import annotations

import re
from ..agents import pick_model
from ..errors import ApiError
from ..store import now
from . import route
from ..app import _routed_agent
from ._common import _allowed_project_ids, _chooser, _human_action


@route("POST", "/api/projects/<key>/intake")
def api_intake_start(P, req, key):
    """A requirement conversation: split, classify, restate on the business map, ask only what is missing."""
    from .. import attachments, intake
    p = P.project(key)
    model = req.body.get("model", True) is not False
    files = attachments.save(P.data_dir, req.body.get("attachments") or [])
    return intake.start(P, p, req.body.get("text", ""), req.user, req.body.get("channel") or "web", _chooser(P, p) if model else None,
                        big=bool(req.body.get("big")), agent=model, wait=bool(req.body.get("wait")), attachments=files)


@route("GET", "/api/intake/<sid>")
def api_intake_get(P, req, sid):
    from .. import intake
    return intake.load(P.data_dir, sid, P)


@route("POST", "/api/intake/<sid>")
def api_intake_act(P, req, sid):
    """answer: {"answers": {"0": {"trigger": "…"}, "spec": {"goal": "…"}}}; big: {"on": true} makes it one feature with a
    规格卡; confirm: tickets from the items (all, or "items"), or for a big one a parent and its children ("deps":
    {"2": [0]}, "wave": 2); drop."""
    from .. import intake
    a = req.body.get("action")
    if a == "answer":
        return intake.answer(P, sid, req.user, req.body.get("answers") or {}, wait=bool(req.body.get("wait")))
    if a == "big":
        return intake.mark_big(P, sid, req.user, req.body.get("on", True) is not False)
    if a == "confirm":
        from .. import workbench
        s = intake.confirm(P, sid, req.user, req.body.get("items"), req.body.get("deps"), req.body.get("wave"), req.body.get("hand"))
        workbench.sync(P, req.user)  # the client of this talk goes on to the tickets it made
        return s
    if a == "drop":
        return intake.drop(P, sid, req.user)
    if a == "understand":  # recorded with the rules only; someone who may call a model hands it to AI
        return intake.understand(P, sid, req.user, wait=bool(req.body.get("wait")))
    if a == "ask_client":  # the open questions on a link of the client's own
        return intake.ask_client(P, sid, req.user, req.body.get("items"))
    raise ApiError(400, "action 只能是 answer、big、confirm、drop、understand、ask_client")


@route("POST", "/api/tickets/<key>/ask-client")
def api_ask_client(P, req, key):
    """A ticket (or a big requirement's child) waiting on 待确认 criteria: its questions go to the client."""
    from .. import intake
    t = P.ticket(key)
    s = intake.session_of(P, t["key"])
    if not s:
        raise ApiError(409, "这张工单不是从需求对话来的，没有要问客户的问题；在评论里写清楚再交给自动处理")
    only = [i for i, it in enumerate(s["items"]) if it.get("ticket") == t["key"]]
    if not only and s.get("epic") != t["key"]:
        raise ApiError(409, "在需求对话里找不到这张工单")
    return intake.ask_client(P, s["id"], req.user, only or None)


@route("POST", "/api/tickets/<key>/client-change")
def api_client_change(P, req, key):
    """A client's answer would change criteria already confirmed: the engineer takes it ({"accept": true}) or not."""
    from .. import intake
    t = P.ticket(key)
    return intake.accept_client_change(P, t["key"], req.user, bool(req.body.get("accept")))


@route("POST", "/api/tickets/<key>/intake-retry")
def api_intake_retry(P, req, key):
    """Retry interpretation of saved answers without resubmitting or replacing the customer's words."""
    from .. import intake
    t = P.ticket(key)
    return intake.retry_understanding(P, t["key"], req.user, wait=bool(req.body.get("wait")))


@route("GET", "/api/tickets/<key>/path-map")
def api_path_map(P, req, key):
    from .. import pathmap
    return pathmap.for_ticket(P, P.ticket(key))


@route("POST", "/api/tickets/<key>/path-map")
def api_path_map_record(P, req, key):
    from .. import pathmap, signoff
    # Serialize selection against ticket/run updates. Recompute the candidate
    # receipt before recording so stale pages cannot bind another code version.
    with P.store.lock:
        ticket = P.ticket(key)
        if ticket["status"] == "closed":
            raise ApiError(409, "工单已关闭，不能记录新的代码关联")
        mapping = pathmap.for_ticket(P, ticket)
        body = req.body
        if not mapping["can_record"] or body.get("commit") != mapping["source"]["commit"] or body.get("digest") != mapping["digest"]:
            raise ApiError(409, "候选版本或代码关联已变化，请重新加载后核对")
        selected = body.get("flows")
        valid = {f["id"] for f in mapping["flows"]}
        if not isinstance(selected, list) or not selected or any(not isinstance(f, str) or f not in valid for f in selected):
            raise ApiError(400, "请选择当前候选版本中可核对的代码入口")
        selected = list(dict.fromkeys(selected))
        links = dict(ticket.get("links") or {})
        # Keep existing human confirmations intact, but do not manufacture one.
        prior = set((links.get("code_path") or {}).get("flows", [])) - set(links.get("flows_ok") or [])
        links["flows"] = list(dict.fromkeys([f for f in links.get("flows", []) if f not in prior] + selected))
        links["code_path"] = {"commit": mapping["source"]["commit"], "digest": mapping["digest"], "flows": selected,
                              "basis": "python-static-functions", "by": req.user}
        ticket = P.store.update_ticket(ticket["id"], req.user, links=links)
        P.store.event(ticket["id"], req.user, "code-map", "记录候选版本的静态代码关联；不代表业务验收或人工复核", links["code_path"])
        if ticket["status"] == "verify":
            signoff.pack(P, ticket, req.user, "更新候选代码关联")
        mapping["selected"] = selected
        return mapping


@route("POST", "/api/projects/<key>/pins")
def api_pin_add(P, req, key):
    """A box drawn on the system's page: texts, elements and requests in it, located in the code."""
    from .. import pinpoint
    return pinpoint.save(P, P.project(key), req.body, req.user, "platform")


@route("GET", "/api/projects/<key>/pins")
def api_pins(P, req, key):
    from .. import pinpoint
    p = P.project(key)
    return {"pins": [dict(x, summary=pinpoint.summary(x)) for x in pinpoint.recent(P.data_dir, p["key"])],
            "has_token": pinpoint.has_token(P.data_dir, p["key"])}


@route("POST", "/api/projects/<key>/capture-token")
def api_capture_token(P, req, key):
    """The bookmarklet for the client's own pages. Issuing a new one switches the old one off."""
    from .. import pinpoint
    p = P.project(key)
    base = (req.body.get("base") or "").strip()
    if not re.match(r"^https?://[^/\s]+$", base):
        proto = req.h.headers.get("X-Forwarded-Proto") or "http"
        base = "%s://%s" % (proto, req.h.headers.get("Host") or "127.0.0.1")
    tok = pinpoint.issue_token(P.data_dir, p["key"], req.user)
    return {"bookmarklet": pinpoint.bookmarklet(base, tok), "endpoint": base + "/capture/<token>"}


@route("GET", "/api/pins/<pid>")
def api_pin(P, req, pid):
    from .. import pinpoint
    x = pinpoint.load(P.data_dir, pid)
    return dict(x, summary=pinpoint.summary(x))


@route("POST", "/api/pins/<pid>/intake")
def api_pin_intake(P, req, pid):
    """Start the requirement conversation from a box: the note is what they said, the location rides along."""
    from .. import intake, pinpoint
    x = pinpoint.load(P.data_dir, pid)
    p = P.project(x["project"])
    text = (req.body.get("text") or x["capture"].get("note") or "").strip()
    if len(text) < 4:
        text = "页面上这里有问题：%s" % "、".join(x["capture"]["texts"][:3])
    model = req.body.get("model", True) is not False
    return intake.start(P, p, text, req.user, "pin", _chooser(P, p) if model else None,
                        pin={"id": x["id"], "summary": pinpoint.summary(x)}, agent=model)


@route("GET", "/api/projects/<key>/kb/metrics")
def api_kb_metrics(P, req, key):
    """少找人: requests answered without a person, overrules, handoffs per week, business answer wait."""
    from ... import kbqa
    root = P.root(P.project(key))
    try:
        days = int(req.arg("days") or 0)
    except ValueError:
        raise ApiError(400, "days 要写数字")
    return {"metrics": kbqa.metrics(root, days, req.arg("month") or ""), "recent": kbqa.triages(root, 30)}


@route("GET", "/api/tickets/<key>/similar")
def api_ticket_similar(P, req, key):
    """Earlier tickets that read like this one (相似工单查重)."""
    from ..similar import similar
    t = P.ticket(key)
    lk = t.get("links") or {}
    family = {lk.get("parent"), t["key"]} | set(lk.get("children") or [])  # one feature's parts are not duplicates of each other
    pool = [x for x in P.store.tickets(project_id=t["project_id"], limit=5000)
            if not (x["key"] in family or (lk.get("parent") and (x.get("links") or {}).get("parent") == lk["parent"])
                    or (x.get("links") or {}).get("parent") == t["key"])]
    return {"similar": similar(pool, t["title"], t["body"], exclude=t["id"])}


@route("GET", "/api/tickets/<key>/ops")
def api_ticket_ops(P, req, key):
    """Ops investigation: similar tickets, matching experience, read-only queries so far, the conclusion."""
    from .. import ops_diag
    return ops_diag.look(P, P.ticket(key))


@route("POST", "/api/tickets/<key>/ops")
def api_ticket_ops_act(P, req, key):
    """{"action": "query", "sql"} read-only look at the business data, or
    {"action": "conclude", "cause", "text", "fix", "distill"} write down the cause (no code change unless cause=code)."""
    from .. import ops_diag
    t = P.ticket(key)
    b = req.body if isinstance(req.body, dict) else {}
    by = _human_action(P, req)
    if b.get("action") == "query":
        return ops_diag.query(P, t, b.get("sql", ""), by)
    if b.get("action") == "conclude":
        return ops_diag.conclude(P, t, str(b.get("cause") or ""), b.get("text", ""), b.get("fix", ""), by, bool(b.get("distill")))
    raise ApiError(400, "action 只能是 query 或 conclude")


@route("POST", "/api/projects/<key>/similar")
def api_project_similar(P, req, key):
    """While a new ticket is being written: does it repeat an existing one?"""
    from ..similar import similar
    p = P.project(key)
    title, body = str(req.body.get("title") or ""), str(req.body.get("body") or "")
    if len((title + body).strip()) < 2:
        return {"similar": []}
    return {"similar": similar(P.store.tickets(project_id=p["id"], limit=5000), title, body, limit=int(req.body.get("limit") or 5))}


@route("GET", "/api/projects/<key>/bots")
def api_bots(P, req, key):
    """Which chat robots this project has and whether their environment variables are set; callback paths to paste."""
    from ... import bots
    p = P.project(key)
    st = bots.status(P.root(p))
    ctx = getattr(P, "tenant_context", None)
    st["paths"] = {k: "%s/bot/%s/%s" % ("/t/" + ctx.tenant_id if ctx else "", k, p["key"]) for k in bots.KINDS}
    return st


@route("POST", "/api/projects/<key>/kb/overrule")
def api_kb_overrule(P, req, key):
    from ... import kbqa
    actor = _human_action(P, req, strict=True)
    if req.body.get("by") not in (None, "", actor):
        raise ApiError(403, "人工改判必须记在当前登录账号下，不能代用他人姓名")
    try:
        return kbqa.overrule(P.root(P.project(key)), req.body.get("id") or "", actor,
                             (req.body.get("reason") or "").strip(), req.body.get("verdict") or "")
    except KeyError as e:
        raise ApiError(404, e.args[0])
    except ValueError as e:
        raise ApiError(400, e.args[0])


@route("GET", "/api/projects/<key>/integrations")
def api_ints(P, req, key):
    return P.integrations(P.project(key))


@route("POST", "/api/projects/<key>/import")
def api_import(P, req, key):
    b = req.body
    keys = [k.strip() for k in re.split(r"[,\s，]+", b.get("keys", "")) if k.strip()]
    if not keys and not b.get("query"):
        raise ApiError(400, "填写外部工单号，或一个搜索条件")
    return {"imported": P.import_issues(P.project(key), b.get("via", ""), keys, b.get("query", ""), req.user)}


@route("GET", "/api/projects/<key>/survey")
def api_survey(P, req, key):
    p = P.project(key)
    sv = P.surveys.get(p["id"])
    if sv:
        return sv.view()
    from ... import kb
    reg = kb.load_registry(P.root(p))
    return {"state": "idle", "coverage": kb.coverage(reg) if reg else None}


@route("POST", "/api/projects/<key>/survey")
def api_survey_start(P, req, key):
    """Full-project analysis: agents write the knowledge base page by page."""
    from ..agents import load_config
    from ..survey import Survey
    p = P.project(key)
    sv = P.surveys.get(p["id"])
    if sv and sv.busy:
        raise ApiError(409, "这个项目的全项目分析还在进行")
    agent = _routed_agent(P, p, req.body.get("agent"), "codex")
    if agent not in load_config(P.data_dir):
        raise ApiError(400, "没有这个智能体：%s" % agent)
    try:
        pick_model(load_config(P.data_dir)[agent], "kb", req.body.get("model"))
    except ValueError as e:
        raise ApiError(400, str(e))
    sv = Survey(P, p, agent, req.body.get("parallel", 2), req.body.get("limit", 0), req.user, req.body.get("scope", "all"), req.body.get("model"),
                review=req.body.get("review", False), review_options=req.body.get("review_options"))
    P.surveys[p["id"]] = sv
    sv.start()
    return sv.view()


@route("POST", "/api/projects/<key>/survey/stop")
def api_survey_stop(P, req, key):
    sv = P.surveys.get(P.project(key)["id"])
    if not sv or not sv.busy:
        raise ApiError(400, "没有进行中的全项目分析")
    sv.stop()
    return sv.view()


@route("GET", "/api/lead")
def api_lead(P, req):
    try:
        days = max(1, min(366, int(req.arg("days") or 30)))
    except ValueError:
        raise ApiError(400, "days 写成天数，例如 30")
    return P.lead(days)


@route("POST", "/api/projects/<key>/catchup")
def api_catchup(P, req, key):
    """Hand every open ticket that is not on the automatic line yet over to it (one or two at a time)."""
    return {"queued": P.flow.catch_up(None if key in ("*", "all") else P.project(key), req.user)}


@route("GET", "/api/projects/<key>/loop")
def api_loop(P, req, key):
    return P.loop(None if key in ("*", "all") else P.project(key), allowed_projects=_allowed_project_ids(P, req))


@route("GET", "/api/projects/<key>/inbox")
def api_inbox(P, req, key):
    """What waits for a person now, and what waits on someone outside the team."""
    return P.inbox(None if key in ("*", "all") else P.project(key), allowed_projects=_allowed_project_ids(P, req))


@route("GET", "/api/projects/<key>/points")
def api_points(P, req, key):
    p = P.project(key)
    return {"balance": P.balance(p), "prices": P.pricing["prices"], "log": P.store.points_log(p["id"])}


@route("POST", "/api/projects/<key>/points")
def api_points_add(P, req, key):
    p = P.project(key)
    try:
        n = int(req.body.get("delta") or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "点数必须是整数")
    if not n:
        raise ApiError(400, "点数不能为 0")
    P.balance(p)
    P.store.add_points(p["id"], n, req.body.get("reason") or ("充值" if n > 0 else "调整"), req.user)
    return {"balance": P.balance(p)}


@route("GET", "/api/assist")
def api_assist_list(P, req):
    """Older entry point: the person's session for a ticket, or their latest project session."""
    p = P.project(req.arg("project"))
    s = _default_session(P, req, p, req.arg("ticket"))
    return {"session": P.session_info(s), "messages": P.session_view(s["id"]), "balance": P.balance(p), "price": P.pricing["prices"].get("ask", 0)}


@route("POST", "/api/assist")
def api_assist(P, req):
    b = req.body
    p = P.project(b.get("project", ""))
    s = P.session_of(b["session"], req.user) if b.get("session") else _default_session(P, req, p, b.get("ticket"))
    q = (b.get("question") or "").strip()
    if not q:
        raise ApiError(400, "问题是空的")
    P.ask(s, q, b.get("mode"), b.get("agent"), req.user, b.get("model"))
    return {"session": P.session_info(P.store.session(s["id"])), "messages": P.session_view(s["id"]), "balance": P.balance(p)}


def _default_session(P, req, p, ticket_key):
    if ticket_key:
        return P.ticket_session(p, P.ticket(ticket_key), req.user)
    for s in P.store.sessions(p["id"], req.user):
        if not s["archived_at"] and not s["ticket_id"]:
            return s
    return P.store.session_create(p["id"], "consult", "项目咨询", req.user)


# ---- assistant sessions
@route("GET", "/api/projects/<key>/sessions")
def api_sessions(P, req, key):
    p = P.project(key)
    ms = {m["id"]: m for m in P.store.matters(p["id"])}
    out = []
    for s in P.store.sessions(p["id"], req.user):
        s = dict(s)
        if s["ticket_id"]:
            t = P.store.ticket(s["ticket_id"])
            s["ticket"] = t and {"key": t["key"], "title": t["title"], "status": t["status"]}
        if s["matter_id"] in ms:
            s["matter"] = {"id": s["matter_id"], "title": ms[s["matter_id"]]["title"]}
        out.append(s)
    return {"sessions": out, "matters": [m for m in ms.values() if m["created_by"] in (req.user, "")]}


@route("POST", "/api/projects/<key>/sessions")
def api_new_session(P, req, key):
    """New session: a project question (consult), a maintenance matter (new or existing), or a ticket's working session."""
    p = P.project(key)
    b = req.body
    kind = b.get("kind") or "consult"
    if kind == "ticket":
        t = P.ticket(b.get("ticket", ""))
        if t["project_id"] != p["id"]:
            raise ApiError(400, "工单不属于这个项目")
        s = P.ticket_session(p, t, req.user) if not b.get("fresh") else \
            P.store.session_create(p["id"], "ticket", b.get("title") or "%s 处理讨论" % t["key"], req.user, ticket_id=t["id"])
        return P.session_info(s)
    mid = None
    if kind == "matter":
        if b.get("matter_id"):
            m = P.store.matter(int(b["matter_id"]))
            if not m or m["project_id"] != p["id"]:
                raise ApiError(404, "没有这个维护事项")
            mid = m["id"]
        else:
            mid = P.store.matter_create(p["id"], b.get("matter_title") or b.get("title") or "维护事项", req.user)["id"]
    try:
        s = P.store.session_create(p["id"], kind, b.get("title") or ("问题排查" if kind == "matter" else "项目咨询"), req.user, matter_id=mid)
    except ValueError as e:
        raise ApiError(400, str(e))
    return P.session_info(s)


@route("GET", "/api/sessions/<sid>")
def api_session(P, req, sid):
    s = P.session_of(sid, req.user)
    p = P.store.project(s["project_id"])
    return {"session": P.session_info(s), "messages": P.session_view(s["id"]), "balance": P.balance(p),
            "price": P.pricing["prices"].get("ask", 0)}


@route("POST", "/api/sessions/<sid>")
def api_update_session(P, req, sid):
    """Rename, archive or restore. Archiving keeps every message and does not stop a running answer."""
    s = P.session_of(sid, req.user)
    b, f = req.body, {}
    if "title" in b:
        if not (b["title"] or "").strip():
            raise ApiError(400, "会话名称不能为空")
        f["title"] = b["title"].strip()[:60]
    if "archived" in b:
        f["archived_at"] = now() if b["archived"] else ""
    return P.session_info(P.store.session_update(s["id"], **f))


@route("POST", "/api/sessions/<sid>/messages")
def api_session_ask(P, req, sid):
    s = P.session_of(sid, req.user)
    if s["archived_at"]:
        raise ApiError(400, "会话已归档，恢复后才能继续发送")
    q = (req.body.get("question") or "").strip()
    if not q:
        raise ApiError(400, "问题是空的")
    key = req.body.get("idem")
    if key and P.store.idem_get("ask:" + key) is not None:
        return api_session(P, req, sid)
    P.ask(s, q, req.body.get("mode"), req.body.get("agent"), req.user, req.body.get("model"))
    if key:
        P.store.idem_put("ask:" + key, s["id"])
    return api_session(P, req, sid)


@route("POST", "/api/sessions/<sid>/assistant")
def api_session_assistant(P, req, sid):
    from .. import assistant
    session = P.session_of(sid, req.user)
    if session['archived_at']:
        raise ApiError(400, '会话已归档，恢复后才能继续')
    if req.body.get('message') is not None:
        return assistant.step(P, req, session, req.body['message'])
    return assistant.start(P, req, session)
