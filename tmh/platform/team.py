"""Authenticated team work, derived from actual tickets and version-bound evidence.

The HTTP adapter must authenticate a session before passing ``user`` to writes.
Account names are stable identities; display names and agent labels are not login
credentials. Hosted workers also require current tenant and project membership.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re

from . import candidates, filelock
from .errors import ApiError
from .store import now, _keyed
from .project_git import scoped, unavailable, repository


SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_team (
 ticket_id INTEGER PRIMARY KEY, reviewer TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL, updated_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS team_requests (
 actor TEXT NOT NULL, request_id TEXT NOT NULL, ticket_id INTEGER NOT NULL,
 fingerprint TEXT NOT NULL, state TEXT NOT NULL, result TEXT NOT NULL DEFAULT '',
 error TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL,
 PRIMARY KEY(actor,request_id));
"""


def schema(P):
    candidates.schema(P.store)
    with P.store.lock:
        P.store.db.executescript(SCHEMA)
        P.store.db.commit()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def require_user(P, user):
    from .tenant_policy import directory
    if not isinstance(user, str) or user not in directory(P):
        raise ApiError(403, "团队操作需要有效的个人登录账号，显示名和智能体标识不能代替登录")
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


def assignment(P, ticket):
    exists = P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_team'")
    row = P.store.one("SELECT * FROM ticket_team WHERE ticket_id=?", (ticket["id"],)) if exists else None
    return {"assignee": ticket.get("assignee") or "", "reviewer": row["reviewer"] if row else "",
            "revision": row["revision"] if row else 0, "updated": row["updated"] if row else ticket["updated"]}


def require_reviewer(P, ticket, user):
    """Use from legacy human approval routes too; never infer reviewer from author."""
    require_user(P, user)
    t = _ticket(P, ticket["id"] if isinstance(ticket, dict) else ticket)
    from .tenant_policy import require_member, directory
    require_member(P, user, t["project_id"])
    a = assignment(P, t)
    if not a["reviewer"]:
        raise ApiError(409, "请先分配独立复核人")
    if a["reviewer"] != user:
        raise ApiError(403, "这项工作由 %s 复核，请交给指定复核人" % a["reviewer"])
    if a["assignee"] not in directory(P, t["project_id"], "contributor"):
        raise ApiError(409, "请先为任务分配当前有效的个人负责人")
    if a["assignee"] == user:
        raise ApiError(403, "负责人不能同时作为本任务的独立复核人")
    return t


@contextmanager
def _guard(P, tid):
    folder = Path(P.data_dir) / "team-locks"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (str(tid) + ".lock")).open("a+b") as stream:
        try:
            filelock.try_lock(stream)
        except BlockingIOError as exc:
            raise ApiError(409, "此任务正在更新，请稍后刷新回执") from exc
        try:
            yield
        finally:
            filelock.unlock(stream)


def _assign(P, t, b, user):
    from .tenant_policy import directory, require_member
    members = directory(P, t["project_id"], "contributor")
    owner, reviewer = b.get("assignee", ""), b.get("reviewer", "")
    if not isinstance(owner, str) or not isinstance(reviewer, str):
        raise ApiError(400, "负责人和复核人必须是账号名")
    if any(name and name not in members for name in (owner, reviewer)):
        raise ApiError(400, "只能分配给当前存在的个人账号；历史署名仍保留在事件中")
    if owner and owner == reviewer:
        raise ApiError(400, "请为负责人选择另一位独立复核人")
    revision = b.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise ApiError(400, "请提交当前分配修订号 revision")
    st = P.store
    with st.lock:
        try:
            st.db.execute("BEGIN IMMEDIATE")
            fresh = _ticket(P, t["id"])
            require_member(P, user, fresh["project_id"], "manager")
            for name in (owner, reviewer):
                if name:
                    require_member(P, name, fresh["project_id"])
            old = assignment(P, fresh)
            # The owner is included in the optimistic token: legacy endpoints
            # can still edit tickets.assignee without changing this revision.
            if old["revision"] != revision or b.get("previous_assignee") != old["assignee"]:
                raise ApiError(409, "分配已被其他人修改，请刷新后再提交")
            if (old["assignee"], old["reviewer"]) == (owner, reviewer):
                st.db.commit()
                return old
            stamp = now()
            st.db.execute("UPDATE tickets SET assignee=?,updated=? WHERE id=?", (owner, stamp, t["id"]))
            st.db.execute("INSERT INTO ticket_team(ticket_id,reviewer,revision,updated,updated_by) VALUES(?,?,?,?,?) "
                          "ON CONFLICT(ticket_id) DO UPDATE SET reviewer=excluded.reviewer,revision=excluded.revision,updated=excluded.updated,updated_by=excluded.updated_by",
                          (t["id"], reviewer, revision + 1, stamp, user))
            st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'team_assignment',?,?)",
                          (t["id"], stamp, user, "负责人：%s；复核人：%s" % (owner or "未分配", reviewer or "未分配"),
                           _json({"before": old, "assignee": owner, "reviewer": reviewer, "revision": revision + 1})))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise
    return assignment(P, _ticket(P, t["id"]))


def _request(P, t, user, body, fn):
    rid = body.get("request_id")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", rid):
        raise ApiError(400, "操作需要稳定的 request_id；重试请沿用同一编号")
    fingerprint = hashlib.sha256(_json(body).encode()).hexdigest()
    st = P.store
    with st.lock:
        try:
            st.db.execute("BEGIN IMMEDIATE")
            old = st.one("SELECT * FROM team_requests WHERE actor=? AND request_id=?", (user, rid))
            if old:
                st.db.commit()
                if old["fingerprint"] != fingerprint:
                    raise ApiError(409, "同一请求编号已用于不同内容")
                if old["state"] == "complete":
                    return json.loads(old["result"])
                if not (body["action"] == "candidate_merge" and old["state"] in ("pending", "uncertain")):
                    raise ApiError(409, "原请求状态为 %s：%s。请核对已有记录，勿重复启动" % (old["state"], old["error"]))
                # The merge operation itself reconciles its durable Git intent.
                st.db.execute("BEGIN IMMEDIATE")
                st.db.execute("UPDATE team_requests SET state='pending',updated=? WHERE actor=? AND request_id=?", (now(), user, rid))
                st.db.commit()
                old_merge = True
            else:
                old_merge = False
            if not old_merge and body["action"] != "candidate_cancel" and st.one("SELECT request_id FROM team_requests WHERE ticket_id=? AND state IN ('pending','uncertain')", (t["id"],)):
                raise ApiError(409, "此工单有未确认的操作回执，请先核对，不能重复启动")
            stamp = now()
            if not old_merge:
                st.db.execute("INSERT INTO team_requests(actor,request_id,ticket_id,fingerprint,state,created,updated) VALUES(?,?,?,?,'pending',?,?)",
                              (user, rid, t["id"], fingerprint, stamp, stamp))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise
    changed = False
    def mutation():
        nonlocal changed
        require_user(P, user)
        from .tenant_policy import require_member
        require_member(P, user, t["project_id"])
        changed = True
    try:
        result = fn(mutation)
    except BaseException as exc:
        st.x("UPDATE team_requests SET state=?,error=?,updated=? WHERE actor=? AND request_id=?",
             ("uncertain" if changed else "failed", str(exc), now(), user, rid))
        raise
    st.x("UPDATE team_requests SET state='complete',result=?,updated=? WHERE actor=? AND request_id=?", (_json(result), now(), user, rid))
    return result


def _candidate(P, t, cid):
    if not isinstance(cid, int) or isinstance(cid, bool) or cid < 1:
        raise ApiError(400, "请选择固定候选编号")
    row = candidates._row(P, cid)
    if row["ticket_id"] != t["id"]:
        raise ApiError(409, "候选不属于这张工单")
    return row


def _recheck_reason(P, run):
    """Read-only eligibility: a known refusal must not poison the request journal."""
    if run["mode"] != "fix" or run["status"] != "done" or not (run.get("diff") or run.get("has_diff")):
        return "这次运行没有已完成且可重新验证的代码改动"
    if run["decision"] and not run["decision"].startswith("accepted:"):
        return "这次改动已经放弃，不能重新验证"
    if run["id"] in P.flow.rechecking:
        return "这次改动正在重新验证"
    previous = P.flow.rechecks.status(run["id"])
    if previous and not previous["can_retry"]:
        return "；".join(previous["blocked"])
    return ""


def _action(P, t, b, user, mutation):
    action = b["action"]
    if action == "claim":
        if t.get("assignee") != user:
            raise ApiError(403, "请先将此任务分配给自己，再接管提交")
        from . import handwork
        mutation()
        return handwork.claim(P, t, user, True)
    if action == "comment":
        text = b.get("body")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(400, "交接内容不能为空")
        mutation()
        return P.store.comment(t["id"], user, text, b["request_id"])
    if action == "run_recheck":
        run = P.store.run(b.get("run_id"))
        if not run or run["ticket_id"] != t["id"]:
            raise ApiError(404, "此工单没有指定运行")
        why = _recheck_reason(P, run)
        if why:
            raise ApiError(409, why)
        from .project_library import require_run_current
        try:
            require_run_current(P.store, P.store.project(run["project_id"]), run["id"])
        except ValueError as exc:
            raise ApiError(409, str(exc)) from exc
        mutation()
        return P.flow.recheck(run["id"], user)
    from ..agent_contract import validate
    if action == "candidate_submit":
        if t.get("assignee") != user:
            raise ApiError(403, "请由任务负责人提交，或先完成负责人分配")
        fields = ("ticket", "base_commit", "commit", "requirement_hash", "criteria", "summary", "request_id")
        args = {k: b[k] for k in fields if k in b}
        op = action
    else:
        row = _candidate(P, t, b.get("candidate_id"))
        if action in ("review", "candidate_assess", "candidate_merge", "business_accept"):
            require_reviewer(P, t, user)
        if action == "business_accept":
            if b.get("result") not in ("pass", "fail"):
                raise ApiError(400, "业务验收结果必须是 pass 或 fail")
            return candidates.browser_accept(P, row["id"], user, b.get("evidence_hash", ""), b["result"] == "pass", b.get("note", ""), mutation)
        if action == "candidate_merge":
            return candidates.browser_merge(P, row["id"], user, b.get("evidence_hash", ""), b["request_id"], mutation)
        op = "candidate_decide" if action == "review" else action
        fields = {"candidate_decide": ("candidate_id", "evidence_hash", "decision", "note", "request_id"),
                  "candidate_assess": ("candidate_id", "verification_hash", "preview_hash", "results", "note", "request_id"),
                  "candidate_verify": ("candidate_id", "request_id"), "candidate_cancel": ("candidate_id", "request_id"),
                  "candidate_preview": ("candidate_id", "request_id")}.get(op)
        if not fields:
            raise ApiError(400, "未知团队操作")
        args = {k: b[k] for k in fields if k in b}
    try:
        args = validate(op, args)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    if op == "candidate_decide":
        return candidates.browser_decide(P, user, args, mutation)
    if op == "candidate_assess":
        def checked():
            require_reviewer(P, t, user)
            mutation()
        return candidates.execute(P, user, op, args, checked)
    return candidates.execute(P, user, op, args, mutation)


@scoped
def dispatch_action(P, body, user):
    require_user(P, user)
    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
        raise ApiError(400, "请选择团队操作")
    t = _ticket(P, body.get("ticket"))
    from .tenant_policy import require_member
    require_member(P, user, t["project_id"], "manager" if body["action"] == "assign" else "contributor")
    schema(P)
    from .project_library import require_development
    try:
        require_development(P.store, P.store.project(t["project_id"]))
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc
    with _guard(P, t["id"]):
        result = _assign(P, t, body, user) if body["action"] == "assign" else _request(P, t, user, body, lambda mutation: _action(P, _ticket(P, t["id"]), body, user, mutation))
    return {"result": result, "item": item(P, _ticket(P, t["id"]), user)}


@scoped
def item(P, t, user):
    from .agent_api import _requirement
    from .fixloop import verified
    from .tenant_policy import directory
    members = directory(P, t["project_id"], "contributor")
    managed=getattr(P,'tenant_context',None)
    repo=repository(P,P.store.project(t['project_id']),user)
    metadata_review=not managed or managed.runtime_allowed(user)
    if managed and not metadata_review and user in members:
        from .project_git import available
        try:
            metadata_review=available(P,P.store.project(t['project_id']),user)
        except (ApiError,OSError,ValueError):
            metadata_review=False
    a = assignment(P, t)
    latest = P.store.one("SELECT id FROM code_candidates WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (t["id"],))
    candidate, error = None, ""
    if latest:
        try:
            candidate = candidates.view(P, latest["id"])
        except (ApiError, OSError, ValueError) as exc:
            error = str(exc)
            metadata_review=False
    metadata_unavailable=unavailable(P.store.project(t['project_id'])['root'])
    if metadata_unavailable or managed and not repo['ready']: metadata_review=False
    run = P.store.one("SELECT id,mode,status,author,agent,decision,created,ended,LENGTH(diff)>0 AS has_diff FROM runs WHERE ticket_id=? AND mode!='ask' ORDER BY id DESC LIMIT 1", (t["id"],))
    if run:
        run["can_recheck"] = not bool(_recheck_reason(P, run))
    technical, human, merge = "not_started", "not_requested", None
    state, label = ("closed", "任务已验收") if t["status"] == "closed" else ("working", "待提交代码")
    if candidate:
        verification = P.flow.rechecks.status(candidate["run_id"])
        technical = "passed" if candidate["technical_acceptance"] else "tests_passed" if candidate["verification_passed"] else "pending"
        team_accepted = candidate["human_accepted"] and candidates.browser_review_current(P, candidate["id"])
        human = "accepted" if team_accepted else "pending"
        decision = candidate.get("human_decision")
        rejected = decision and decision["decision"] == "reject" and decision["evidence_hash"] == candidate["evidence_hash"]
        if rejected:
            human = "rejected"
        merge = candidates.merge_receipt(P, candidate["id"])
        if merge and merge["state"] == "merged":
            state, label = "merged", "已合并，待业务验收"
        elif not candidate["current"]:
            state, label = "stale", "依据已变化，需重新提交"
        elif verification and verification.get("running"):
            state, label, technical = "checking", "技术检查中", "running"
        elif rejected:
            state, label = "changes_requested", "人工复核退回"
        elif team_accepted:
            state, label = "approved", "复核通过，待合并"
        elif candidate["ready_for_human"]:
            state, label = "review", "待人工复核"
        elif candidate["verification_passed"] and candidate["preview_ready"]:
            state, label = "assessment", "待逐项技术复核"
        elif candidate["verification_passed"]:
            state, label = "preview", "待启动固定版本预览"
        else:
            state, label = "verification", "待技术检查"
        candidate["recheck"] = verification
        business = P.store.one("SELECT * FROM events WHERE ticket_id=? AND kind IN ('accept','reject') ORDER BY id DESC LIMIT 1", (t["id"],))
        if business and business["data"].get("candidate") == candidate["id"]:
            if business["kind"] == "accept" and t["status"] == "closed":
                state, label, human = "closed", "业务验收完成", "accepted"
            elif business["kind"] == "reject":
                state, label, human = "changes_requested", "业务验收退回", "rejected"
    elif error:
        state, label = "blocked", "候选证据不可读取"
    elif run and run["status"] in ("queued", "running"):
        state, label = "working", "智能体处理中"
    elif run and run["status"] in ("failed", "cancelled"):
        state, label = "blocked", "执行中断，待处理"
    elif run and run["mode"] == "fix":
        check = verified(P.data_dir, run["id"])
        technical = "passed" if check.get("check") == "pass" and check.get("verification_current") is not False else "pending"
        if not run["decision"]:
            state, label = "legacy_review", "待审阅运行改动"
        elif t["status"] != "closed":
            state, label = "acceptance", "待工单业务验收"
    legacy_release = P.store.one("SELECT * FROM events WHERE ticket_id=? AND kind='release' ORDER BY id DESC LIMIT 1", (t["id"],))
    if not candidate and legacy_release:
        merge = {"state": "merged", **legacy_release["data"], "by": legacy_release["author"], "created": legacy_release["ts"]}
        if t["status"] != "closed":
            state, label = "acceptance", "已合并，待工单业务验收"
    if (metadata_unavailable or managed and not repo['ready'] and
            (candidate or run and run['mode']=='fix' and run['status']=='done' and run['has_diff'])) and t['status']!='closed':
        state,label='blocked','版本证据暂不可读取'
    can_review = user in members and a["reviewer"] == user and a["assignee"] in members and a["assignee"] != user and (not candidate or not candidates.implementation_author(candidate["author"],user))
    acceptance_memory = None
    business = P.store.one("SELECT * FROM events WHERE ticket_id=? AND kind IN ('accept','reject') ORDER BY id DESC LIMIT 1", (t["id"],))
    source = business and business["data"] or {}
    if source.get("memory_snapshot"):
        from . import learn
        status = learn.candidate_memory_status(P.data_dir, business["id"])
        acceptance_memory = {**status, "event_id": business["id"], "by": business["author"],
            "candidate_id": source["candidate"], "evidence_hash": source["evidence_hash"], "result": source["result"],
            "note": source["note"], "project": source["memory_snapshot"]["project"],
            "can_retry": bool(status["pending"] and can_review and business["author"] == user)}
    return {"ticket": t, "assignment": dict(a, assignee_active=a["assignee"] in members, reviewer_active=a["reviewer"] in members),
            "state": state, "label": label, "technical": technical, "human": human, "merge": merge,
            "candidate": candidate, "candidate_error": error, "run": run, "requirement_hash": _requirement(t, P.store),
            "acceptance_memory": acceptance_memory,
            "needs_review": state in ("assessment", "review", "approved", "merged", "legacy_review", "acceptance"),
            "can_review": can_review, "personal_decisions_available":metadata_review,
            "repository_ready":repo['ready'],"repository_reason":repo['reason'],
            "can_submit": user in members and t["assignee"] == user and t["status"] != "closed",
            "requests": P.store.q("SELECT actor,request_id,state,error,created,updated FROM team_requests WHERE ticket_id=? AND state IN ('pending','uncertain') ORDER BY created", (t["id"],)),
            "boundary": "人工复核不等于客户签收；本地合并不等于推送 GitHub 或部署上线。"}


@scoped
def dispatch_read(P, query, user):
    def arg(key, default=""):
        v = query.get(key, default)
        return v[0] if isinstance(v, list) and v else v
    from .tenant_policy import directory, require_member
    require_member(P, user)
    members = sorted(directory(P))
    viewer = user if user in members else ""
    request_id = arg("request_id")
    if request_id:
        if not viewer:
            raise ApiError(403, "操作回执只能由原登录成员读取")
        schema(P)
        receipt = P.store.one("SELECT ticket_id,request_id,state,error,created,updated FROM team_requests WHERE actor=? AND request_id=?", (viewer, request_id))
        if receipt:
            require_member(P, user, _ticket(P, receipt["ticket_id"])["project_id"], "viewer")
            receipt.pop("ticket_id")
        return {"request": receipt}
    view = arg("view", "mine")
    if view not in ("mine", "team", "review", "unassigned"):
        raise ApiError(400, "未知团队视图")
    project = arg("project")
    p = P.store.project(project) if project and project not in ("*", "all") else None
    if project and project not in ("*", "all") and not p:
        raise ApiError(404, "没有这个项目")
    if p:
        require_member(P, user, p, "viewer")
    sql = "SELECT t.*,p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id"
    values = []
    if p:
        sql += " WHERE t.project_id=?"
        values.append(p["id"])
    if arg("ticket"):
        selected_ticket = _ticket(P, arg("ticket"))
        require_member(P, user, selected_ticket["project_id"], "viewer")
        sql += (" AND" if p else " WHERE") + " t.id=?"
        values.append(selected_ticket["id"])
    member_project = p["id"] if p else selected_ticket["project_id"] if arg("ticket") else None
    from .tenant_policy import enabled, identity
    if member_project is None and enabled(P) and identity(P, user)["role"] != "admin":
        raise ApiError(403, "请明确选择获准的项目或工单")
    schema(P)
    members = sorted(directory(P, member_project, "contributor"))
    rows = [_keyed(t) for t in P.store.q(sql + " ORDER BY t.updated DESC,t.id DESC", values)]
    items = [item(P, t, viewer) for t in rows]
    mine = lambda x: bool(viewer) and x["assignment"]["assignee"] == viewer and x["state"] not in ("closed", "merged")
    review = lambda x: bool(viewer) and x["assignment"]["reviewer"] == viewer and x["needs_review"]
    unassigned = lambda x: not x["assignment"]["assignee_active"] and x["state"] not in ("closed", "merged")
    predicates = {"mine": mine, "team": lambda x: True, "review": review, "unassigned": unassigned}
    selected = [x for x in items if predicates[view](x)]
    try:
        offset, limit = max(0, int(arg("offset", 0))), max(1, min(100, int(arg("limit", 50))))
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "分页参数必须是整数") from exc
    return {"viewer": viewer, "members": [{"id": name, "name": name} for name in members], "view": view,
            "project": p["key"] if p else "*", "counts": {"mine": sum(map(mine, items)), "team": len(items), "review": sum(map(review, items)), "unassigned": sum(map(unassigned, items))},
            "items": selected[offset:offset + limit], "total": len(selected), "offset": offset,
            "has_more": offset + limit < len(selected), "next_offset": offset + limit,
            "boundary": ("当前访问范围由租户成员与项目授权决定。任务分配不会授予项目访问权限。" if enabled(P) else
                         "当前为共享工作区。任务分配明确协作责任，不代表项目级访问隔离。")}
