"""Routes: comments, runs, rechecks, page checks, metrics, reports, prompts."""
from __future__ import annotations

import json
import time
from pathlib import Path
from ..metrics import report_md
from ..errors import ApiError
from . import route
from ..app import _routed_agent
from ._common import _allowed_project_ids, _human_action, _session_actor, _workspace_id


@route("POST", "/api/tickets/<key>/comments")
def api_comment(P, req, key):
    if "expected_workspace" in req.body and req.body["expected_workspace"] not in (str(P.data_dir), _workspace_id(P)):
        raise ApiError(409, "当前工作区已变化，本次请求未写入；请回到原工作区后核对或重试")
    if "expected_author" in req.body and req.body["expected_author"] != req.user:
        raise ApiError(409, "当前登录身份已变化，本次请求未写入；请切回原身份后核对或重试")
    t = P.ticket(key)
    body = req.body.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ApiError(400, "评论不能为空")
    request_id = req.body.get("request_id")
    if "request_id" in req.body and (not isinstance(request_id, str) or not request_id.strip()):
        raise ApiError(400, "评论请求编号不能为空，且必须是字符串")
    try:
        return P.store.comment(t["id"], req.user, body, request_id)
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc


@route("GET", "/api/tickets/<key>/related")
def api_ticket_related(P, req, key):
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    return P.kb.related(p, "%s %s" % (t["title"], (t.get("body") or "")[:600]))


@route("GET", "/api/tickets/<key>/context")
def api_ticket_context(P, req, key):
    from ..agents import knowledge
    from ..learning_decisions import runtime_policy
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    return {"text": knowledge(P.root(p), "%s %s" % (t["title"], (t.get("body") or "")[:600]),
                              runtime_policy(P.store, p)["context_budget"], store=P.store, project=p)}


@route("POST", "/api/tickets/<key>/runs")
def api_start_run(P, req, key):
    from .. import epic
    t = P.ticket(key)
    if epic.refuse(t, "run"):
        raise ApiError(409, epic.refuse(t, "run"))
    p = P.store.project(t["project_id"])
    mode, n = req.body.get("mode", "analyze"), int(req.body.get("kb_after") or 0)
    then = (lambda run: P.kb.kb_followup(p, P.store.ticket(t["id"]), run, n, req.user)) if n and mode == "analyze" else None
    try:
        sid = req.body.get("session")
        s = P.session_of(sid, req.user) if sid else None
        return P.runner.start(p, t, _routed_agent(P, p, req.body.get("agent"), "claude"), mode, req.user, req.body.get("target", ""), then,
                              session_id=s and s["id"], model=req.body.get("model"))
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/tickets/<key>/push")
def api_push(P, req, key):
    return P.push_comment(P.ticket(key), req.body.get("body", ""), bool(req.body.get("confirm")), req.user)


@route("POST", "/api/projects/<key>/runs")
def api_project_run(P, req, key):
    """Runs without a ticket, e.g. writing a knowledge page."""
    p = P.project(key)
    try:
        return P.runner.start(p, None, _routed_agent(P, p, req.body.get("agent"), "claude"), req.body.get("mode", "kb"), req.user, req.body.get("target", ""),
                              batch=str(req.body.get("batch") or "")[:40], model=req.body.get("model"))
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/runs")
def api_runs(P, req):
    pid = P.project(req.arg("project"))["id"] if req.arg("project") else None
    from .. import learning_experiment_views as V
    runs = V.runs(P, _session_actor(req) or req.user, project_id=pid, limit=200,
                  allowed_projects=_allowed_project_ids(P, req))
    keys = {}
    for r in runs:
        if r["ticket_id"] and r["ticket_id"] not in keys:
            t = P.store.ticket(r["ticket_id"])
            keys[r["ticket_id"]] = (t["key"], t["title"]) if t else ("", "")
        r["ticket"], r["ticket_title"] = keys.get(r["ticket_id"], ("", ""))
    names = {}
    for r in runs:
        if r["session_id"] and r["session_id"] not in names:
            s = P.store.session(r["session_id"])
            names[r["session_id"]] = s["title"] if s else ""
        r["session_title"] = names.get(r["session_id"], "")
    return runs


@route("GET", "/api/runs/<rid>")
def api_run(P, req, rid):
    r = P.store.run(int(rid))
    if not r:
        raise ApiError(404, "没有这个运行")
    from .. import learning_experiment_views as V
    managed = V.run(P, P.store.project(r["project_id"]), r["id"], _session_actor(req) or req.user,
                    since=int(req.arg("since") or 0), include_prompt=req.arg("prompt") == "1")
    if managed is not None:
        return managed
    from ..fixloop import verified
    t = P.store.ticket(r["ticket_id"]) if r["ticket_id"] else None
    r["ticket_key"] = t["key"] if t else ""
    r["verification"] = verified(P.data_dir, r["id"]) if r["mode"] == "fix" else None
    r["recheck"] = api_recheck_state(P, req, rid) if r["mode"] == "fix" else None
    from .. import review_feedback
    r["review_feedback"] = review_feedback.view(P, r, r["verification"])
    from .. import tenant_policy
    try:
        tenant_policy.authorize(P, "POST", "/api/runs/%s/review-feedback" % rid, {}, {}, req.user)
        r["review_feedback"]["can_record"] = True
    except ApiError as exc:
        if exc.code not in (401, 403):
            raise
        r["review_feedback"]["can_record"] = False
    r["human_review"] = None
    if t and r["mode"] == "fix" and r["status"] == "done":
        from .. import signoff
        evidence = signoff.state(P.data_dir, t["key"])
        bound = ((evidence.get("snapshot") or {}).get("change") or {}).get("run") == r["id"]
        current = bound and evidence.get("intact") and not evidence.get("stale") and not evidence.get("binding_blocked")
        r["human_review"] = {"current": bool(current), "review": evidence.get("review") if current else None,
                             "decision": evidence.get("decision") if current else None,
                             "proofs": evidence.get("proofs", []) if current else []}
    r["lifecycle"], r["lifecycle_error"] = None, ""
    try:
        receipt = Path(P.data_dir) / "runs" / str(r["id"]) / "lifecycle.json"
        if receipt.exists():
            record = json.loads(receipt.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("停止回执应为对象")
            r["lifecycle"] = record
    except (OSError, ValueError) as e:
        r["lifecycle_error"] = "运行停止回执不可读：%s" % e
    r.update(P.runner.retry_state(r["id"]))
    if r["lifecycle_error"]:
        r["can_retry"] = False
        r["retry_blocked"] = list(r.get("retry_blocked") or []) + [r["lifecycle_error"]]
    since = int(req.arg("since") or 0)
    r["output_len"] = len(r["output"])
    r["output"] = r["output"][since:]
    if req.arg("prompt") != "1":
        r["prompt"] = ""
    return r


def _require_unmanaged_run(P, rid):
    """Managed attempts can only stop/recover through their experiment ledger."""
    from .. import learning_experiments as X
    if X.run_owner(P.store, int(rid)) is not None:
        raise ApiError(409, "此运行属于受管实验，请从实验入口停止或查看；不能单独重试、恢复或决定")


@route("POST", "/api/runs/<rid>/cancel")
def api_cancel(P, req, rid):
    _require_unmanaged_run(P, rid)
    try:
        return P.runner.cancel(int(rid), req.user)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/runs/<rid>/review-feedback")
def api_review_feedback(P, req, rid):
    from .. import review_feedback
    run = P.store.run(int(rid))
    if not run:
        raise ApiError(404, "没有这次运行")
    if req.h.headers.get('X-Webuddy-Agent') or req.user.startswith('agent:'):
        raise ApiError(403, 'Review效果请由人工记录')
    actor = _session_actor(req)
    if not actor:
        from ..operator_access import require
        require(P, req.h.headers)
        actor = req.user
    return review_feedback.save(P, run, actor, req.body)


@route("POST", "/api/runs/<rid>/say")
def api_run_say(P, req, rid):
    """{"text": "..."}: a person's word to a running agent. It is appended to the run's notes file, which the agent
    reads between steps (agents.steer_hint), shown in the run's log and written on the ticket."""
    from ..agents import notes_file
    _require_unmanaged_run(P, rid)
    _human_action(P, req)
    r = P.store.run(int(rid))
    if not r:
        raise ApiError(404, "没有运行 #%s" % rid)
    if r["status"] not in ("running", "queued"):
        raise ApiError(409, "运行 #%s 已经结束，补充的话请写在工单讨论里，再让 AI 接着做" % rid)
    text = str(req.body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "插话内容不能为空")
    text = text[:2000]
    f = notes_file(P.data_dir, int(rid))
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write("[%s %s] %s\n" % (time.strftime("%H:%M:%S"), req.user, text))
    P.store.append_output(int(rid), "\n— %s 插话：%s\n" % (req.user, text))
    if r.get("ticket_id"):
        P.store.event(r["ticket_id"], req.user, "steer", text, {"run": int(rid)})
    return {"ok": True, "run": int(rid), "notes": len(f.read_text(encoding="utf-8").splitlines())}


@route("POST", "/api/runs/<rid>/retry")
def api_retry_run(P, req, rid):
    _require_unmanaged_run(P, rid)
    if not P.store.run(int(rid)):
        raise ApiError(404, "没有这个运行")
    try:
        return P.runner.retry(int(rid), req.user)
    except (ValueError, RuntimeError, OSError) as e:
        raise ApiError(409, str(e))


@route("POST", "/api/runs/<rid>/recover")
def api_recover_run(P, req, rid):
    _require_unmanaged_run(P, rid)
    if not P.store.run(int(rid)):
        raise ApiError(404, "没有这个运行")
    try:
        P.runner.recover_run(int(rid))
        return api_run(P, req, rid)
    except (ValueError, RuntimeError, OSError) as e:
        raise ApiError(409, str(e))


@route("POST", "/api/runs/<rid>/decide")
def api_decide(P, req, rid):
    _require_unmanaged_run(P, rid)
    run = P.store.run(int(rid))
    if not run:
        raise ApiError(404, "没有这个运行")
    _human_action(P, req, P.store.ticket(run["ticket_id"]) if run.get("ticket_id") else None, run=run)
    try:
        return P.runner.decide(int(rid), req.body.get("decision", ""), req.user)
    except (ValueError, RuntimeError) as e:
        raise ApiError(400, str(e))


@route("POST", "/api/runs/<rid>/recheck")
def api_recheck(P, req, rid):
    """Build a finished change again without redoing it; poll GET .../recheck for the result."""
    _require_unmanaged_run(P, rid)
    try:
        return P.flow.recheck(int(rid), req.user, wait=bool(req.body.get("wait")), kind=req.body.get("kind", "tests"))
    except (ValueError, RuntimeError) as e:
        raise ApiError(400, str(e))


@route("GET", "/api/runs/<rid>/recheck")
def api_recheck_state(P, req, rid):
    _require_unmanaged_run(P, rid)
    from ..fixloop import verified
    r = P.store.run(int(rid))
    if not r:
        raise ApiError(404, "没有这个运行")
    v = verified(P.data_dir, int(rid))
    from ..recheck_operations import read_status
    try:
        operation = read_status(P.data_dir, int(rid))
    except (ValueError, OSError) as exc:
        operation = {"status": "blocked", "running": False, "can_retry": False, "blocked": [str(exc)], "result": str(exc)}
    return {"running": bool(operation and operation.get("running")), "decision": r["decision"],
            "operation": operation, "verify": v or None}


@route("POST", "/api/runs/<rid>/page-check")
def api_page_check(P, req, rid):
    """Check this change in a real browser on the project's verification host; poll GET for the result."""
    _require_unmanaged_run(P, rid)
    from .. import browser_verify
    try:
        return browser_verify.page_check(P, int(rid), req.user)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/runs/<rid>/page-check")
def api_page_check_state(P, req, rid):
    _require_unmanaged_run(P, rid)
    from .. import browser_verify
    if not P.store.run(int(rid)):
        raise ApiError(404, "没有这个运行")
    return browser_verify.page_state(P, int(rid))


@route("POST", "/api/runs/<rid>/recheck/recover")
def api_recheck_recover(P, req, rid):
    _require_unmanaged_run(P, rid)
    if not P.store.run(int(rid)):
        raise ApiError(404, "没有这个运行")
    try:
        operation = P.flow.rechecks.status(int(rid))
        if not operation:
            raise ValueError("这次运行还没有重新验证记录")
        P.flow.rechecks.recover_one(operation["id"])
        return api_recheck_state(P, req, rid)
    except (ValueError, RuntimeError, OSError) as exc:
        raise ApiError(409, str(exc))


@route("GET", "/api/projects/<key>/metrics")
def api_metrics(P, req, key):
    return P.metrics(P.project(key), req.arg("month"))


@route("GET", "/api/projects/<key>/report")
def api_report(P, req, key):
    """《AI 提效报告》 as Markdown; /p/<key>/efficiency?month= serves the same as a printable page."""
    p = P.project(key)
    m = P.metrics(p, req.arg("month"))
    return {"markdown": report_md(m), "filename": "AI提效报告-%s-%s.md" % (p["key"], m["month"] or "全部")}


@route("GET", "/api/tickets/<key>/prompt")
def api_ticket_prompt(P, req, key):
    return P.ticket_prompt(P.ticket(key), req.arg("scene") or "bugfix")


@route("POST", "/api/tickets/<key>/prompt")
def api_use_prompt(P, req, key):
    return P.use_prompt(P.ticket(key), req.body.get("scene") or "bugfix", req.body.get("action") or "copy", req.user)


@route("GET", "/api/stats")
def api_stats(P, req):
    pid = P.project(req.arg("project"))["id"] if req.arg("project") else None
    return P.store.stats(pid)
