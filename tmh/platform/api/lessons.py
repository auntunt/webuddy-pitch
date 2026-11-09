"""Routes: commands, acceptance, learning, lessons, evals, alerts."""
from __future__ import annotations

import re
from ..agents import is_git
from .. import command
from ..errors import ApiError
from . import route
from ..app import _routed_agent
from ._common import _direct_api_allowed, _human_action, _lesson_human_actor


@route("POST", "/api/projects/<key>/command")
def api_command(P, req, key):
    """Plan one sentence from the side panel as UI steps (see command.py). The browser runs them; saves wait for the person.

    With a session, the sentence and the plan are kept in that session so the history shows what was done."""
    from ... import kbqa
    p = P.project(key)
    b = req.body
    text = (b.get("text") or "").strip()
    if not text:
        raise ApiError(400, "指令是空的")
    sessions = [P.session_info(s) for s in P.store.sessions(p["id"], req.user) if not s["archived_at"]]
    projects = [{"key": x["key"], "name": x["name"]} for x in P.store.projects()]
    direct_api = _direct_api_allowed(P, p)
    conf = kbqa.router_conf(P.root(p)) if b.get("model", True) and direct_api else {}
    pl = command.plan(text, b.get("page") or {}, sessions, projects, conf)
    out = {"plan": pl}
    if b.get("model", True) and not direct_api:
        out["model_skipped"] = "项目配置关闭直接 API 调用，本次使用规则生成操作建议"
    if pl["kind"] == "command" and b.get("session"):
        s = P.session_of(b["session"], req.user)
        if not s["archived_at"]:
            P.store.chat_add(p["id"], s["ticket_id"], "user", req.user, text, {"kind": "cmd"}, session_id=s["id"])
            out["message"] = P.store.chat_add(p["id"], s["ticket_id"], "assistant", "助手", pl["summary"],
                                              {"kind": "cmd", "plan": pl, "state": "proposed", "done": 0}, session_id=s["id"])
    return out


@route("POST", "/api/sessions/<sid>/command/<mid>")
def api_command_state(P, req, sid, mid):
    """Record how a planned command went: done, cancelled, failed or undone, how many steps ran, and what puts it back."""
    s = P.session_of(sid, req.user)
    rows = P.store.q("SELECT * FROM chats WHERE id=? AND session_id=?", (int(mid) if str(mid).isdigit() else -1, s["id"]))
    if not rows or (rows[0]["data"] or {}).get("kind") != "cmd":
        raise ApiError(404, "没有这条指令")
    m = rows[0]
    d = dict(m["data"] or {})
    st = req.body.get("state")
    if st not in ("proposed", "waiting", "done", "cancelled", "failed", "undone"):
        raise ApiError(400, "状态不对")
    d["state"] = st
    u = req.body.get("undo")
    if isinstance(u, dict) and u.get("target") in ("fs", "fy", "fp") and str(u.get("route") or "").startswith("#/t/"):
        d["undo"] = {"target": u["target"], "value": str(u.get("value") or "")[:40], "text": str(u.get("text") or "")[:40], "route": str(u["route"])[:60]}
    d["done"] = max(0, min(int(req.body.get("done") or 0), len((d.get("plan") or {}).get("steps") or [])))
    if req.body.get("note"):
        d["note"] = str(req.body["note"])[:300]
    P.store.chat_update(m["id"], m["body"], d)
    return {"ok": True, "data": d}


@route("POST", "/api/sessions/<sid>/ticket-draft")
def api_ticket_draft(P, req, sid):
    return P.ticket_draft(P.session_of(sid, req.user))


@route("POST", "/api/sessions/<sid>/ticket")
def api_session_ticket(P, req, sid):
    """Submit a reviewed draft: a new ticket, or a note on the session's existing ticket. Same idem key → same result."""
    s = P.session_of(sid, req.user)
    b = req.body
    key = "ticket:%s" % (b.get("idem") or "")
    if b.get("idem"):
        done = P.store.idem_get(key)
        if done is not None:
            return done
    p = P.store.project(s["project_id"])
    body = (b.get("body") or "").strip()
    if (b.get("accept") or "").strip():
        body += "\n\n## 验收条件\n" + b["accept"].strip()
    if b.get("target") == "existing" and s["ticket_id"]:
        t = P.store.ticket(s["ticket_id"])
        P.store.event(t["id"], req.user, "comment", "（从助手会话「%s」补充）\n\n%s" % (s["title"], body))
        P.store.touch(t["id"])
        res = {"key": t["key"], "created": False}
    else:
        try:
            t = P.store.create_ticket(p["id"], b.get("title", ""), req.user, body=body, type=b.get("type"), priority=b.get("priority"),
                                      assignee=b.get("assignee", ""), links={"flows": list(b.get("flows") or []), "session": s["id"]})
        except ValueError as e:
            raise ApiError(400, str(e))
        P.store.event(t["id"], req.user, "comment", "由助手会话「%s」起草，经 %s 核对后提交" % (s["title"], req.user))
        P.flow.submit(p, t)
        if not s["ticket_id"]:
            P.store.session_update(s["id"], ticket_id=t["id"])
        if s["matter_id"]:
            m = P.store.matter(s["matter_id"])
            if m and not m["ticket_id"]:
                P.store.matter_update(m["id"], ticket_id=t["id"])
        res = {"key": t["key"], "created": True}
    if b.get("idem"):
        P.store.idem_put(key, res)
    return res


@route("POST", "/api/tickets/<key>/accept")
def api_accept(P, req, key):
    """Human acceptance: only a person passes or fails a ticket; the assistant may only draft the note."""
    t = P.ticket(key)
    _human_action(P, req, t)
    res, note = req.body.get("result"), (req.body.get("note") or "").strip()
    if res not in ("pass", "fail"):
        raise ApiError(400, "result 只能是 pass 或 fail")
    if res == "fail" and not note:
        raise ApiError(400, "验收不通过时必须写明原因")
    # External candidates have a distinct, exact-version chain. The legacy
    # evidence package may be empty and must not let /accept bypass that chain.
    from .. import candidates
    if P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='code_candidates'"):
        latest = P.store.one("SELECT id FROM code_candidates WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (t["id"],))
        if latest:
            if req.body.get("candidate_id") != latest["id"] or not req.body.get("evidence_hash"):
                raise ApiError(409, "这张工单使用固定候选，请到团队工作台核对当前版本、复核和合并后再做业务验收")
            return candidates.browser_accept(P, latest["id"], req.user, req.body["evidence_hash"], res == "pass", note)
    from .. import epic, signoff
    why = epic.refuse(t, "accept")
    if why:
        raise ApiError(409, why)
    with signoff.verification_guard(P, key):
        sealed = signoff._record_accept(P, t, req.user, res == "pass", note)
        P.store.event(t["id"], req.user, "accept" if res == "pass" else "reject", ("验收通过" if res == "pass" else "验收不通过") + ("：" + note if note else ""),
                      dict({"result": res}, **({"evidence": sealed} if sealed else {})))
        P.store.update_ticket(t["id"], req.user, status="closed" if res == "pass" else "doing")
        P.flow.accepted(P.store.project(t["project_id"]), P.store.ticket(t["id"]), res == "pass", note, req.user)
        return P.store.ticket(t["id"])


@route("GET", "/api/projects/<key>/learn")
def api_learn(P, req, key):
    """What the outcomes taught: lessons, the eval set and its scores, and where alerts come in."""
    from .. import alerts, learn
    p = P.project(key)
    al = [{"key": t["key"], "title": t["title"], "status": t["status"], "priority": t["priority"], "created": t["created"],
           "count": t["links"]["alert"].get("count", 1), "source": t["links"]["alert"].get("source", "")}
          for t in P.store.tickets(project_id=p["id"], limit=2000) if (t.get("links") or {}).get("alert")][:30]
    from ..memory import lesson_api_error
    try:
        snapshots = learn.lesson_snapshots(P.data_dir, p["key"], 500)
    except learn.LessonDecisionError as exc:
        raise lesson_api_error(exc) from exc
    ls = [{**snapshot["card"], "snapshot": snapshot} for snapshot in snapshots]
    return {"lessons": ls[:80], "lesson_summary": learn.summary(ls), "shared_in": learn.shared(P.data_dir, p["key"])[:40], "cases": learn.cases(P.data_dir, p["key"]),
            "batches": learn.batches(P.data_dir, p["key"]), "running": learn.RUNNING.get(p["key"], ""),
            "alerts": dict(alerts.status(P.data_dir, p["key"]), tickets=al), "refix": P.flow.autoflow().get("refix"),
            "impact": learn.impact(P.data_dir, p["key"])}


@route("POST", "/api/learn/holdout")
def api_learn_holdout(P, req):
    """The comparison group: the share of tickets (0–0.5) whose prompts carry no cards, to measure what the cards do."""
    from .. import learn
    try:
        rate = float(req.body.get("rate") or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "rate 要是 0 到 0.5 之间的数")
    if not 0 <= rate <= 0.5:
        raise ApiError(400, "对照组最多一半的工单")
    try:
        learn.set_holdout(P.data_dir, rate, req.user)
    except ValueError as e:
        raise ApiError(400, str(e))
    return {"holdout": learn.holdout_rate(P.data_dir)}


@route("GET", "/api/projects/<key>/lessons/<lid>")
def api_lesson_snapshot(P, req, key, lid):
    """Read one authorized project card and its version from the same material."""
    from .. import learn
    from ..memory import lesson_api_error
    p = P.project(key)
    try:
        return learn.lesson_snapshot(P.data_dir, p["key"], lid)
    except learn.LessonDecisionError as exc:
        raise lesson_api_error(exc) from exc


@route("GET", "/api/projects/<key>/lessons/<lid>/share")
def api_lesson_share_preview(P, req, key, lid):
    """What would go out if this card were shared: the redacted text, for the person to read and edit first."""
    from .. import learn
    p = P.project(key)
    cur = learn.lesson(P.data_dir, lid)
    if not cur or cur.get("project") != p["key"]:
        raise ApiError(404, "没有这条经验")
    return learn.share_preview(P.data_dir, lid, [p["key"], p.get("name", "")])


@route("POST", "/api/projects/<key>/lessons/<lid>")
def api_lesson(P, req, key, lid):
    """A personal decision binds a complete version; sharing keeps its policy."""
    from .. import learn, memory
    actor = _human_action(P, req, strict=True)
    p, b = P.project(key), req.body
    if not isinstance(b, dict):
        raise ApiError(400, "操作需要 JSON 对象")
    act = b.get("action", "")
    if act == "" and "fields" in b:
        act = "edit"
    if act in ("confirm", "restore", "retire", "edit"):
        actor = _lesson_human_actor(P, req)
        return memory.lesson_decision(P, p["key"], lid, actor, act, b)
    if act not in ("share", "unshare", "take", "untake"):
        error = ApiError(400, "action 只能是 confirm、restore、retire、edit、share、unshare、take、untake")
        error.reason = "invalid_lesson_decision"
        raise error
    try:
        if act in ("take", "untake"):
            return learn.take_shared(P.data_dir, lid, p["key"], act == "take", actor)
        cur = learn.lesson(P.data_dir, lid)
        if not cur or cur.get("project") != p["key"]:
            raise ApiError(404, "没有这条经验")
        if b.get("fields") and not isinstance(b["fields"], dict):
            raise ValueError("fields 要是 {字段: 内容}")
        if not isinstance(b.get("title") or "", str) or not isinstance(b.get("why") or "", str):
            raise ValueError("title、why 要是文字")
        return learn.set_shared(P.data_dir, lid, act == "share", actor, b.get("title") or "",
                                b.get("fields") if isinstance(b.get("fields"), dict) else {},
                                b.get("why") or "", [p["key"], p.get("name", "")])
    except ValueError as exc:
        raise ApiError(404 if act in ("take", "untake") else 400, str(exc)) from exc


@route("POST", "/api/projects/<key>/evals/run")
def api_eval_run(P, req, key):
    from .. import learn
    p = P.project(key)
    try:
        requested = req.body.get("agent")
        agent = _routed_agent(P, p, requested, "" if requested else P.flow.agent(project=p))
        return learn.run_evals(P.flow, p, agent, req.body.get("model"), req.user, req.body.get("cases") or None)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/projects/<key>/evals/cases")
def api_eval_case(P, req, key):
    from .. import learn
    p, b = P.project(key), req.body
    if b.get("remove"):
        return {"removed": learn.remove_case(P.data_dir, p["key"], str(b["remove"]))}
    gold = b.get("gold") or []
    if isinstance(gold, str):
        gold = [x for x in re.split(r"[\s,，]+", gold) if x]
    try:
        return learn.add_case(P.data_dir, p["key"], {"title": b.get("title", ""), "body": b.get("body", ""), "base": (b.get("base") or "").strip(),
                                                     "gold": gold, "source": "manual"})
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/projects/<key>/evals/history")
def api_eval_history(P, req, key):
    """Closed tickets matched to the commits that fixed them: a preview, or (apply) new eval cases."""
    from .. import learn
    p, b = P.project(key), req.body
    if not is_git(P.root(p)):
        raise ApiError(400, "项目目录不是 git 仓库，没法按提交找修复")
    return learn.from_history(P, p, str(b.get("since") or "")[:10], str(b.get("until") or "")[:10], bool(b.get("apply")), bool(b.get("flagged")))


@route("POST", "/api/projects/<key>/evals/history/import")
def api_eval_history_import(P, req, key):
    """Import the closed tickets that commit messages name, so the preview above has something to match."""
    p, b = P.project(key), req.body
    if not is_git(P.root(p)):
        raise ApiError(400, "项目目录不是 git 仓库，没法从提交信息里找工单号")
    try:
        limit = max(1, min(1000, int(b.get("limit") or 200)))
    except (TypeError, ValueError):
        limit = 200
    return P.import_refs(p, str(b.get("via") or ""), str(b.get("since") or "")[:10], str(b.get("until") or "")[:10], limit, req.user)


@route("POST", "/api/projects/<key>/alerts")
def api_alert_paste(P, req, key):
    """A person pastes an alert or an error log: same handling as the webhook, without its key."""
    from .. import alerts
    p = P.project(key)
    text = (req.body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "把告警或报错日志贴进来")
    return alerts.receive(P, p, alerts.parse(text.encode("utf-8")), 10 ** 6)


@route("POST", "/api/projects/<key>/external-requirements")
def api_external_requirement(P, req, key):
    from ..external_requirements import sync
    return sync(P,P.project(key),req.user,req.body)
