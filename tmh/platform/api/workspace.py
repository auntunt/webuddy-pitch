"""Routes: meta, agent, workspace, pilots, meetings, briefs, CI, development, team, handoffs, memory, learning."""
from __future__ import annotations

import traceback
from ... import __version__
from ..agents import available
from ..errors import ApiError
from ..store import PRIORITIES, RUN_MODES, STATUSES, TYPES, timestamp_offset
from . import route
from ._common import _allowed_project_ids, _human_action, _lesson_human_actor, _route_metadata, _session_actor, _workspace_id


@route("GET", "/api/meta")
def api_meta(P, req):
    from ..login import has_accounts
    managed = getattr(P, "tenant_context", None) is not None
    actor = _session_actor(req)
    can_execute = not managed or P.tenant_context.runtime_allowed(actor)
    member_execution = {"projects": [], "agents": []}
    if managed and actor and not can_execute:
        from .. import project_git, tenant_policy
        try:
            identity = tenant_policy.identity(P, actor)
            if not identity.get('tool_connection') and identity['role'] in ('member', 'admin'):
                for project in tenant_policy.visible_projects(P, actor):
                    try:
                        if project_git.available(P, project, actor):
                            member_execution['projects'].append(project['key'])
                    except (ApiError, OSError, ValueError):
                        continue
                if member_execution['projects']:
                    member_execution['agents'] = [a for a in available(P.data_dir)
                                                  if a.get('engine') == 'codex' and a.get('available')
                                                  and not a.get('custom')]
        except (ApiError, OSError, ValueError):
            pass
    return {"version": __version__, "user": req.user, "login": managed or has_accounts(P.data_dir),
            "display_timezone": "Asia/Shanghai", "timestamp_offset": timestamp_offset(),
            "operator_authenticated": bool(getattr(req.h, '_who', '')), "brand": P.brand, "statuses": STATUSES, "types": TYPES, "priorities": PRIORITIES,
            "modes": RUN_MODES, "agents": available(P.data_dir) if can_execute else [], "data_dir": "" if managed else str(P.data_dir), "workspace": _workspace_id(P), "autoflow": P.flow.autoflow(),
            "member_execution": member_execution,
            "agent_route_default": _route_metadata(P, None)["agent_route"] if can_execute else {},
            "apps": __import__("tmh.platform.apps", fromlist=["APPS"]).APPS}


@route("POST", "/api/agent/<operation>")
def api_agent(P, req, operation):
    from ..agent_api import dispatch
    return dispatch(P, req, operation)


@route("GET", "/api/workspace")
def api_workspace(P, req):
    from .. import workspace
    return workspace.read(P, req.query, _session_actor(req))


@route("GET", "/api/projects/<key>/meetings")
def api_meetings(P, req, key):
    from .. import coordination
    # Req.query is parse_qs output. Preserve the module's scalar contract and
    # reject duplicate parameters instead of choosing an ambiguous page.
    query = {}
    for name, values in req.query.items():
        if not isinstance(values, list) or len(values) != 1:
            raise ApiError(400, "分页参数只能出现一次")
        query[name] = values[0]
    return coordination.meetings(P, key, query, _session_actor(req))


@route("GET", "/api/projects/<key>/pilots")
def api_pilots(P, req, key):
    from .. import pilots
    if req.query:
        raise ApiError(400, "试点列表不接受隐藏筛选")
    return pilots.listing(P, key, _session_actor(req))


@route("POST", "/api/projects/<key>/pilots")
def api_pilot_create(P, req, key):
    from .. import pilots
    return pilots.act(P, key, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/projects/<key>/pilots/<pid>")
def api_pilot(P, req, key, pid):
    from .. import pilots
    if set(req.query) - {"revision"} or any(len(v) != 1 for v in req.query.values()):
        raise ApiError(400, "修订参数只能出现一次")
    revision = req.arg("revision")
    if revision and (not revision.isascii() or not revision.isdecimal() or len(revision) > 9 or int(revision) < 1):
        raise ApiError(400, "修订编号不正确")
    return pilots.read(P, key, pid, _session_actor(req), int(revision) if revision else None)


@route("POST", "/api/projects/<key>/pilots/<pid>")
def api_pilot_action(P, req, key, pid):
    from .. import pilots
    return pilots.act(P, key, req.body, _human_action(P, req, strict=True), pid)


@route("POST", "/api/projects/<key>/meetings")
def api_meeting_create(P, req, key):
    from .. import coordination
    return coordination.create_meeting(P, key, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/projects/<key>/meetings/<mid>")
def api_meeting(P, req, key, mid):
    from .. import coordination
    return coordination.meeting(P, key, mid, _session_actor(req))


@route("POST", "/api/projects/<key>/meetings/<mid>")
def api_meeting_action(P, req, key, mid):
    from .. import coordination
    return coordination.meeting_action(P, key, mid, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/tickets/<key>/brief")
def api_work_brief(P, req, key):
    from .. import coordination
    return coordination.brief(P, key, _session_actor(req))


@route("POST", "/api/tickets/<key>/brief")
def api_work_brief_save(P, req, key):
    from .. import coordination
    return coordination.save_brief(P, key, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/projects/<key>/ci")
def api_project_ci(P, req, key):
    from ..project_ci import configuration
    return configuration(P.data_dir, P.project(key)['key'])


@route("POST", "/api/projects/<key>/ci")
def api_project_ci_save(P, req, key):
    from ..project_ci import save
    _human_action(P, req, strict=True)
    return save(P.data_dir,P.project(key)['key'],req.body)


@route("GET", "/api/tickets/<key>/ci")
def api_ticket_ci(P, req, key):
    from ..candidates import _row
    from ..project_ci import check
    t = P.ticket(key)
    try:
        candidate = _row(P,int(req.arg('candidate_id')))
    except ValueError as exc:
        raise ApiError(400,'请选择候选编号') from exc
    if candidate['ticket_id'] != t['id']:
        raise ApiError(404,'此任务没有该候选')
    return check(P.data_dir,P.store.project(t['project_id'])['key'],candidate['commit_sha'])


@route("GET", "/api/tickets/<key>/delivery")
def api_delivery_packet(P, req, key):
    from .. import tool_read
    t = P.ticket(key)
    scope = _allowed_project_ids(P, req)
    return tool_read.delivery_get(P, key, scope if scope is not None else [t['project_id']])


@route("GET", "/api/tickets/<key>/development")
def api_development(P, req, key):
    from .. import development, team
    t = P.ticket(key)
    result = development.read(P.store,t)
    result['work'] = team.item(P,t,_session_actor(req))
    return result


@route("POST", "/api/tickets/<key>/development")
def api_development_action(P, req, key):
    from .. import development
    actor = _human_action(P, req, strict=True)
    body = dict(req.body)
    action = body.pop('action', '')
    if action not in ('answer', 'confirm', 'execution') or body.get('ticket') != key:
        raise ApiError(400, '请选择当前任务的回答或确认操作')
    return development.act(P,actor,action,body,human=True)


@route("GET", "/api/team")
def api_team(P, req):
    from .. import team
    return team.dispatch_read(P, req.query, _session_actor(req))


def _handoff_work(P, data, key, viewer):
    """The same candidate projection drives team review and handoff details."""
    from .. import team
    data["work"] = team.item(P, P.ticket(key), viewer)
    return data


@route("GET", "/api/handoffs")
def api_handoffs(P, req):
    from .. import handoffs, team
    key = req.arg("ticket")
    if not key:
        raise ApiError(400, "请选择需要查看交接的工单")
    ticket = P.ticket(key)
    project = req.arg("project")
    if project and project not in ("*", "all") and P.project(project)["id"] != ticket["project_id"]:
        raise ApiError(404, "此项目没有这张工单")
    team.schema(P)
    viewer = _session_actor(req)
    return _handoff_work(P, handoffs.read(P, key, viewer), key, viewer)


@route("POST", "/api/handoffs")
def api_handoff_action(P, req):
    from .. import handoffs, team
    viewer = _human_action(P, req, strict=True)
    team.schema(P)
    result = handoffs.dispatch_action(P, req.body, viewer)
    # The write result is durable even when a later candidate refresh fails.
    # Never turn a committed handoff into a misleading business rejection.
    try:
        return _handoff_work(P, result, req.body.get("ticket"), viewer)
    except Exception:
        traceback.print_exc()
        result["work"] = None
        result["work_error"] = "交接已登记，候选详情暂不可读取，请刷新详情核对。"
        return result


@route("POST", "/api/team")
def api_team_action(P, req):
    from .. import team
    return team.dispatch_action(P, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/memory")
def api_memory(P, req):
    from .. import memory
    return memory.dispatch_read(P, req.query, _session_actor(req) or req.user)


@route("GET", "/api/memory/brief")
def api_memory_brief(P, req):
    from .. import memory
    return memory.read_brief(P, req.arg("project"), req.arg("revision"))


@route("POST", "/api/memory")
def api_memory_action(P, req):
    from .. import memory
    action = req.body.get("action") if isinstance(req.body, dict) else None
    actor = _lesson_human_actor(P, req) if action in ("lesson_edit", "lesson_confirm", "lesson_restore", "lesson_retire") else _human_action(P, req, strict=True)
    return memory.dispatch_action(P, req.body, actor)


@route("GET", "/api/learning")
def api_learning(P, req):
    from .. import learning as L, learning_runs, learning_experiment_views as V
    if any(isinstance(v, list) and len(v) != 1 for v in req.query.values()):
        raise ApiError(400, "查询参数不能重复")
    p = L.project(P, req.arg("project"))
    actor = _session_actor(req) or req.user
    if req.arg("experiment"):
        return V.experiment(P, p, req.arg("experiment"), actor)
    if req.arg("experiments") == "1":
        return V.experiments(P, p, actor)
    if req.arg("revision"):
        managed = V.managed_detail(P, p, req.arg("revision"), actor)
        if managed is not None:
            return managed
        return V.learning_detail(P, p, L.detail(P, p, req.arg("revision"),
            recorded_jobs=lambda rid: V.catalog_jobs(P, p, actor, rid, detail=True)), actor)
    if req.arg("job"):
        managed = V.job(P, p, req.arg("job"), actor)
        if managed is not None:
            return managed
        return learning_runs.get(P, p, req.arg("job"))
    return V.catalog(P, p, L.catalog(P, p, req.arg("kind"), req.arg("q"),
        managed_revision=lambda rid: V.catalog_revision(P, p, rid, actor),
        recorded_jobs=lambda rid="": V.catalog_jobs(P, p, actor, rid)), actor)


@route("POST", "/api/learning")
def api_learning_action(P, req):
    from .. import learning as L, learning_runs, learning_experiment_views as V
    b = req.body
    if not isinstance(b, dict):
        raise ApiError(400, "操作需要 JSON 对象")
    action = b.get("action", "")
    if not isinstance(action, str):
        raise ApiError(400, "知识操作名称必须是字符串")
    human_action = action in ("adopt", "revoke", "retry_decision", "abandon_decision") or action.startswith("experiment_")
    if human_action or not req.h.headers.get("X-Webuddy-Agent"):
        actor = _human_action(P, req, strict=True)
        if human_action:
            from ..signoff import human
            if not human(actor):
                raise ApiError(403, "只有个人操作者可以记录人工决定")
    else:
        from ..agent_api import _actor
        actor = _actor(req)
        if action in ("review", "evaluate", "resume") and req.h.headers.get("X-Webuddy-Execution") != "1":
            raise ApiError(403, "运行知识任务需要 X-Webuddy-Execution: 1")
    p = L.project(P, b.get("project", ""))
    try:
        if action.startswith("experiment_"):
            from .. import learning_experiments as X, learning_experiment_runs as XR
            operations = {
                "experiment_create": {"contract"},
                "experiment_seal": {"experiment_id", "expected_hash"},
                "experiment_start": {"experiment_id"},
                "experiment_cancel": {"experiment_id"},
                "experiment_expose": {"experiment_id", "asset_ids", "expected_hash"},
            }
            if action not in operations or set(b) - (operations[action] | {"action", "project", "request_id"}):
                raise ApiError(400, "实验操作包含未知动作或字段")
            eid, request_id = b.get("experiment_id", ""), b.get("request_id", "")
            if action == "experiment_create":
                receipt = X.create_draft(P, p, b.get("contract"), actor, request_id)
            elif action == "experiment_seal":
                receipt = X.seal(P, p, eid, b.get("expected_hash"), actor, request_id)
            elif action == "experiment_start":
                receipt = XR.start_sealed(P, p, eid, actor, request_id)
            elif action == "experiment_cancel":
                receipt = X.cancel(P, p, eid, actor, request_id)
            else:
                receipt = X.expose(P, p, eid, b.get("asset_ids"), b.get("expected_hash"), actor, request_id)
            return {"receipt": receipt}
        if action == "capture":
            return V.revision(P, p, L.capture(P, p, b.get("key", ""), b.get("expected_fingerprint", ""), actor), actor)
        if action == "propose":
            return L.propose(P, p, b.get("revision_id", ""), b.get("content"), actor)
        if action == "policy_create":
            return L.policy_create(P, p, b.get("name", ""), b.get("title", ""), b.get("parameters"), b.get("applicability", ""), actor)
        if action in ("review", "evaluate"):
            options = {k: v for k, v in b.items() if k not in ("project", "action", "request_id", "revision_id")}
            result = learning_runs.start(P, p, action, b.get("revision_id", ""), options, actor, b.get("request_id", ""))
            managed = V.job(P, p, result["id"], actor)
            return managed if managed is not None else result
        if action in ("cancel", "resume"):
            result = getattr(learning_runs, action)(P, p, b.get("job_id", ""), actor)
            managed = V.job(P, p, result["id"], actor)
            return managed if managed is not None else result
        if action in ("adopt", "revoke"):
            from .. import learning_decisions as D
            if "expected_active" not in b:
                raise ApiError(400, "必须提交页面显示的预期采用版本")
            result = D.decide(P, p, action, b.get("revision_id", ""), actor, b.get("request_id", ""),
                              b["expected_active"], b.get("reason", ""), b.get("job_id", ""))
            return V.decision(P, p, result, actor)
        if action == "retry_decision":
            from .. import learning_decisions as D
            return V.decision(P, p, D.project_decision(P, p, b.get("decision_id", "")), actor)
        if action == "abandon_decision":
            from .. import learning_decisions as D
            return V.decision(P, p, D.abandon(P, p, b.get("decision_id", ""), actor, b.get("expected_token"), b.get("reason", "")), actor)
        raise ApiError(400, "未知知识操作")
    except ValueError as exc:
        error = ApiError(400, str(exc))
        if action.startswith("experiment_") and getattr(exc, "reason", "") == "experiment_not_written":
            error.reason = "experiment_not_written"
        raise error from exc
