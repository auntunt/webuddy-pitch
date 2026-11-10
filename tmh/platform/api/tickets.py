"""Routes: tickets, epics, evidence, upstream, baseline, ledger."""
from __future__ import annotations

from ..agents import git
from ..errors import ApiError
from . import route
from ..app import _routed_agent
from ._common import _allowed_project_ids, _human_action, _personal_review_access


@route("GET", "/api/tickets")
def api_tickets(P, req):
    pid = P.project(req.arg("project"))["id"] if req.arg("project") not in (None, "", "*", "all") else None
    return P.store.tickets(project_id=pid, status=req.arg("status") or None, text=req.arg("q") or None,
                           assignee=req.arg("assignee") or None, limit=int(req.arg("limit") or 500), svc=req.arg("svc") or None,
                           allowed_projects=_allowed_project_ids(P, req))


@route("POST", "/api/tickets")
def api_new_ticket(P, req):
    b = req.body
    p = P.project(b.get("project", ""))
    # Validate the selected route before persisting an explicitly executed ticket.
    agent = _routed_agent(P, p, b["agent"]) if not b.get("handwork") and b.get("agent") and b.get("mode") else None
    links = {}
    if b.get("flows"):
        links["flows"] = list(b["flows"])
    if b.get("code_at"):  # the ticket is about an older version of the code (replaying real history)
        sha = git(P.root(p), "rev-parse", "--verify", "-q", str(b["code_at"]) + "^{commit}", check=False).strip()
        if not sha:
            raise ApiError(400, "代码版本 %s 在项目仓库里找不到" % b["code_at"])
        links["code_at"] = sha
    body, typ = b.get("body", ""), b.get("type")
    if not typ or typ == "auto":  # its kind from the words, and criteria from the description when it has none
        from .. import intake
        typ, body = intake.direct(P, p, b.get("title", ""), body)
    if b.get("handwork"):  # 我来写 from the start: the automatic line never picks it up
        links["hold"] = links["handwork"] = req.user
    try:
        t = P.store.create_ticket(p["id"], b.get("title", ""), req.user, body=body, type=typ,
                                  priority=b.get("priority"), assignee=b.get("assignee", "") or (req.user if b.get("handwork") else ""),
                                  labels=b.get("labels") or [], links=links)
    except ValueError as e:
        raise ApiError(400, str(e))
    if b.get("handwork"):
        P.store.event(t["id"], req.user, "flow", "%s 认领：我来写。自动处理不会接这张单，推到分支 wb/%s 后平台自动构建、审查" % (req.user, t["key"]))
    elif b.get("agent") and b.get("mode"):
        P.runner.start(p, t, agent, b["mode"], req.user, model=b.get("model"))
    elif b.get("auto", True) and not getattr(P, "tenant_context", None):
        P.flow.submit(p, t)
    return P.store.ticket(t["id"])


@route("GET", "/api/tickets/<key>")
def api_ticket(P, req, key):
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    runs = P.store.runs(ticket_id=t["id"])
    pts = P.store.run_points([r["id"] for r in runs])
    from ..fixloop import verified
    from ..task_preparation import view as preparation_view
    for r in runs:
        r.update(preparation_view(P.data_dir, r))
        r["points"] = pts.get(r["id"], 0)
        if r["mode"] == "fix":
            r["diff_bytes"] = len((P.store.run(r["id"]) or {}).get("diff") or "")
            v = verified(P.data_dir, r["id"])
            r["verify"] = {k: v.get(k) for k in ("check", "skip", "verdict", "rounds", "split", "beyond_plan", "verification_current", "recheck_operation", "stalled", "outcome")} if v else None
            r["recheck_wait"] = P.flow.verification_wait(r["id"]) if v.get("verification_current") is False else None
            if v:
                r["verify"]["files"] = len(v.get("files") or [])
    from .. import epic, signoff, stage, workbench, intake, team, ai_accept, development
    from .. import reform_state
    par = P.store.ticket(t["links"]["parent"]) if (t.get("links") or {}).get("parent") else None
    return {"ticket": t, "project": p, "events": P.store.events(t["id"]), "runs": [r for r in runs if r["mode"] != "ask"],
            "team_assignment": team.assignment(P, t),
            "development": development.read(P.store, t),
            "workflow_policy": ai_accept.mandate(P.flow.autoflow(), p["key"], P.data_dir),
            "intake_recovery": intake.recovery_state(P, t["key"]),
            "plain_state": workbench.states(P, [t])[t["key"]],
            "stage": stage.compute(P, [t])[t["key"]],
            "evidence": P.ticket_evidence(p, t, runs), "auto_next": P.flow.next_step(t, retry=True)[0],
            "package": dict(signoff.brief(P.data_dir, t["key"]), personal_review=_personal_review_access(P, req, t)), "epic": epic.view(P, t) if epic.is_parent(t) else None,
            "reform_state": reform_state.ticket(P,p,t) if t["links"].get("reform") else None,
            "parent": {"key": par["key"], "title": par["title"], "status": par["status"]} if par else None}


@route("GET", "/api/tickets/<key>/epic")
def api_epic(P, req, key):
    """A big requirement's parent: the spec, every child with its status and version, and the batch it is on."""
    from .. import epic
    t = P.ticket(key)
    if not epic.is_parent(t):
        raise ApiError(404, "这张工单不是大需求的父单")
    return epic.view(P, t)


@route("POST", "/api/tickets/<key>/epic")
def api_epic_act(P, req, key):
    """{"action": "release"} puts the next batch out by hand; "resume" after a pause; "auto" {"on"}; "wave" {"n"}."""
    from .. import epic
    try:
        return epic.act(P, P.ticket(key), req.body, req.user)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/tickets/<key>/evidence")
def api_evidence(P, req, key):
    """The ticket's evidence package: latest snapshot, what was added, what is missing, the seal."""
    from .. import signoff
    t = P.ticket(key)
    s = signoff.state(P.data_dir, t["key"])
    s["label"] = signoff.STATUS_LABEL[s["status"]]
    s["page"] = "/e/%s" % t["key"]
    s["personal_review"] = _personal_review_access(P, req, t)
    return s


@route("POST", "/api/tickets/<key>/evidence")
def api_evidence_add(P, req, key):
    """kind=attach (screenshot/note for one AC), review (provider's internal review), pack (re-pack now),
    link (a one-time sign-off link for the client's signer)."""
    from .. import signoff
    t = P.ticket(key)
    b = req.body
    kind = b.get("kind")
    if kind == "attach":
        r = signoff.attach(P, t, req.user, b.get("ac", ""), b.get("note", ""), b.get("image", ""))
    elif kind == "review":
        _human_action(P, req, t)
        r = signoff.review(P, t, req.user, b.get("note", ""), bool(b.get("scope_ok")), bool(b.get("path_ok")),
                           b.get("waive") if isinstance(b.get("waive"), dict) else None)
    elif kind == "pack":
        r = signoff.pack(P, t, req.user, "手动重新打包") or {"unchanged": True}
    elif kind == "link":
        return signoff.issue(P, t, req.user, b.get("signer", ""), b.get("role", ""), int(b.get("days") or signoff.LINK_DAYS), b.get("note", ""))
    else:
        raise ApiError(400, "kind 只能是 attach、review、pack 或 link")
    return {"record": {k: r.get(k) for k in ("seq", "hash", "ts", "unchanged") if k in r}, "state": signoff.brief(P.data_dir, t["key"])}


@route("GET", "/api/tickets/<key>/upstream")
def api_upstream(P, req, key):
    from .. import upstream
    return upstream.view(P, P.ticket(key))


@route("POST", "/api/tickets/<key>/upstream")
def api_upstream_act(P, req, key):
    """An external pull request: link (repo, issue, pr), draft (title, body, head, base), approve (a person),
    submit (confirm=true to really open it; dry run otherwise), sync (read GitHub), reason (why it was closed)."""
    from .. import upstream
    t, b = P.ticket(key), req.body
    a = b.get("action")
    if a == "link":
        upstream.link(P, t, req.user, b.get("repo", ""), b.get("issue", ""), b.get("pr", ""))
    elif a == "draft":
        upstream.draft(P, t, req.user, b.get("title", ""), b.get("body", ""), b.get("head", ""), b.get("base", ""))
    elif a == "approve":
        upstream.approve(P, t, req.user, b.get("note", ""))
    elif a == "submit":
        r = upstream.submit(P, t, req.user, bool(b.get("confirm")))
        if r.get("dry_run"):
            return r
    elif a == "sync":
        from ...integrations.base import IntegrationError
        try:
            return upstream.sync(P, t, req.user)
        except IntegrationError as e:
            raise ApiError(502, "读 GitHub 失败：%s" % e)
    elif a == "reason":
        upstream.outcome_reason(P, t, req.user, b.get("reason", ""), b.get("note", ""))
    else:
        raise ApiError(400, "action 只能是 link、draft、approve、submit、sync、reason")
    return upstream.view(P, P.ticket(t["id"]))


@route("GET", "/api/projects/<key>/upstream")
def api_upstream_list(P, req, key):
    from .. import upstream
    return upstream.metrics(P, P.project(key), req.arg("month"))


@route("GET", "/api/projects/<key>/baseline")
def api_baseline(P, req, key):
    from .. import books
    p = P.project(key)
    return {"sealed": books.load_baseline(P.data_dir, p["key"]), "candidate": books.candidate(P.store, p, req.arg("from"), req.arg("to"))}


@route("POST", "/api/projects/<key>/baseline/seal")
def api_baseline_seal(P, req, key):
    """Seal the baseline once: window, method and sample are written down and hashed; it cannot be changed after."""
    from .. import books
    p = P.project(key)
    b = req.body
    return books.seal(P.store, P.data_dir, p, b.get("from", ""), b.get("to", ""), req.user, b.get("note", ""))


@route("GET", "/api/projects/<key>/ledger")
def api_ledger(P, req, key):
    m = P.metrics(P.project(key), req.arg("month"))
    return {"ledger": m["ledger"], "sealed": m["sealed"], "gate": m["gate"]}


@route("POST", "/api/tickets/<key>")
def api_update_ticket(P, req, key):
    if "assignee" in req.body:
        from .. import team
        with team._guard(P, P.ticket(key)["id"]):
            return _api_update_ticket(P, req, key)
    return _api_update_ticket(P, req, key)


def _api_update_ticket(P, req, key):
    t = P.ticket(key)
    b = dict(req.body)
    if "assignee" in b and b["assignee"] != t.get("assignee"):
        from .. import team
        if team.assignment(P, t)["revision"]:
            raise ApiError(409, "请在团队协作中调整负责人和复核人，保留分配版本与复核记录")
    if (t.get("links") or {}).get("epic") and ((b.get("status") and b["status"] != t["status"]) or b.get("auto") == "go" or "hold" in b or "links" in b):
        from .. import epic  # its status follows its children; reopening a finished feature means a new requirement
        raise ApiError(409, epic.refuse(t, "status"))
    if b.get("status") == "closed" and t["status"] != "closed":
        # closing is acceptance: a person's "验收通过" (POST /accept), never a status edit (docs/acceptance.md)
        raise ApiError(400, "关单只能走验收：由人点“验收通过”（POST /api/tickets/%s/accept）" % t["key"])
    if "link_flow" in b or "unlink_flow" in b or "confirm_flows" in b:
        # flows the automatic flow linked stay "suggested" until a person links or confirms them (flows_ok)
        links = dict(t.get("links") or {})
        fl = list(links.get("flows") or [])
        ok = list(links.get("flows_ok") or [])
        if b.get("link_flow") and b["link_flow"] not in fl:
            fl.append(b["link_flow"])
            P.store.event(t["id"], req.user, "link", "关联业务流 %s" % b["link_flow"])
        if b.get("link_flow") and b["link_flow"] not in ok:
            ok.append(b["link_flow"])
        if b.get("unlink_flow") in fl:
            fl.remove(b["unlink_flow"])
            P.store.event(t["id"], req.user, "link", "取消关联 %s" % b["unlink_flow"])
        ok = [f for f in ok if f in fl]
        cf = b.get("confirm_flows")
        if cf:
            new = [f for f in (fl if cf == "*" else cf if isinstance(cf, list) else []) if f in fl and f not in ok]
            if new:
                ok += new
                P.store.event(t["id"], req.user, "link", "确认关联业务流 %s" % "、".join(f.replace("flow:", "") for f in new))
        links["flows"], links["flows_ok"] = fl, ok
        b["links"] = links
    if b.get("auto") == "go":  # hand a ticket that is not on the automatic line yet over to it
        lk = dict(t.get("links") or {})
        if lk.pop("open_ac", None) is not None:  # a person handing it over one by one has settled what was 待确认
            P.store.update_ticket(t["id"], req.user, links=lk)
            t = P.store.ticket(t["id"])
        P.flow.resume(P.store.project(t["project_id"]), t)
        return P.store.ticket(t["id"])
    if "hold" in b:
        t = P.flow.take_over(t, bool(b["hold"]), req.user)
        if not any(k in b for k in ("title", "body", "type", "status", "priority", "assignee", "labels", "links")):
            return t
    try:
        return P.store.update_ticket(t["id"], req.user, **{k: b.get(k) for k in ("title", "body", "type", "status", "priority", "assignee", "labels", "links")})
    except ValueError as e:
        raise ApiError(400, str(e))
