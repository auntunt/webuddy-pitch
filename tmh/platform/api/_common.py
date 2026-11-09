"""Helpers shared by more than one API route module."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import unquote
from .. import agent_routes
from ..errors import ApiError


def _direct_api_allowed(P, project):
    try:
        return agent_routes.direct_api_allowed(P.data_dir, project)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _route_metadata(P, project):
    """Only this visible project's non-secret policy; never probe an executable."""
    try:
        return {"agent_route": agent_routes.route(P.data_dir, project), "agent_route_error": ""}
    except ValueError as exc:
        return {"agent_route": {}, "agent_route_error": str(exc)}


def _workspace_id(P) -> str:
    """Names the data directory to a page that is not shown its path, so writes can still refuse a switched workspace."""
    return "ws-" + hashlib.sha256(str(P.data_dir).encode("utf-8")).hexdigest()[:32]


def _session_actor(req):
    """A display-name header is never an individual team identity."""
    handler = getattr(req, "h", None)
    return getattr(handler, "_who", "") if not getattr(handler, "headers", {}).get("X-Webuddy-Agent") else ""


def _human_action(P, req, ticket=None, strict=False, run=None):
    from .. import login, team
    actor = _session_actor(req)
    if getattr(getattr(req, "h", None), "headers", {}).get("X-Webuddy-Agent") or ((strict or getattr(P, "tenant_context", None) or login.has_accounts(P.data_dir)) and not actor):
        raise ApiError(403, "请用个人账号登录后操作；共享令牌或显示名不能代替人工确认")
    managed = getattr(P, "tenant_context", None)
    member = managed.current_actor(actor) if managed else None
    if ticket and (team.assignment(P, ticket)["revision"] or member and not member.get("platform_owner")):
        team.require_reviewer(P, ticket, actor)
    if ticket and member and not member.get("platform_owner"):
        # Reassigning responsibility must not erase the immutable author of
        # the implementation this personal decision is reviewing.
        if run is None:
            from .. import signoff
            pack = signoff.ev.latest(signoff.records(P.data_dir, ticket["key"]), "pack")
            data=(pack or {}).get('data') or {}
            snapshot=data.get('snapshot') if isinstance(data,dict) else None
            change=snapshot.get('change') if isinstance(snapshot,dict) else None
            if pack and not isinstance(change,dict):
                raise ApiError(409,'证据包的实现来源不完整，请重新生成后复核')
            source=(change or {}).get('run')
            run = P.store.run(source) if source else None
            if source and (not run or run['ticket_id']!=ticket['id'] or run['project_id']!=ticket['project_id']):
                raise ApiError(409,'证据包的实现运行与当前工单不一致，请重新生成后复核')
        from ..agent_api import member_actor
        if run and run.get("author") in (actor, member_actor(actor)):
            raise ApiError(403, "实现运行的发起人不能复核或验收自己的实现，请交给另一位指定复核人")
    return actor or req.user


def _personal_review_access(P, req, ticket):
    """UI hint only; each write repeats the actual identity and evidence checks."""
    if req is None:
        return {"allowed": False, "kind": "evidence_review", "reason": "没有请求身份，无法判断个人复核权限"}
    try:
        _human_action(P, req, ticket)
        return {"allowed": True, "kind": "evidence_review"}
    except ApiError as exc:
        return {"allowed": False, "kind": "evidence_review", "reason": str(exc)}


def _lesson_human_actor(P, req):
    """Bind the reviewed identity; the header never authenticates its sender."""
    actor = _human_action(P, req, strict=True)
    expected = req.h.headers.get("X-Webuddy-Lesson-Actor", "")
    try:
        if not expected or re.search(r"%(?![0-9a-fA-F]{2})", expected):
            raise ValueError("missing or malformed identity binding")
        expected = unquote(expected, encoding="utf-8", errors="strict")
    except (ValueError, UnicodeError):
        error = ApiError(400, "人工决定必须绑定阅读时的个人身份，请重新打开经验卡片")
        error.reason = "invalid_lesson_decision"
        raise error
    if expected != actor:
        error = ApiError(409, "当前登录身份与阅读经验时不同，本次决定未写入，请重新登录并阅读")
        error.reason = "lesson_identity_changed"
        raise error
    return actor


def _allowed_project_ids(P, req):
    if not getattr(P, "tenant_context", None):
        return None
    from ..tenant_policy import visible_projects
    return [p["id"] for p in visible_projects(P, _session_actor(req))]


def _chooser(P, p: dict):
    """The routing model as a typed chooser for the requirement conversation, or None when not configured."""
    from ... import kbqa
    if not _direct_api_allowed(P, p):
        return None
    conf = kbqa.router_conf(P.root(p))
    if not conf["ready"]:
        return None
    return lambda text, q, opts: kbqa.choose(conf, "需求原话：%s" % text, q, opts)["index"]


def _platform_admin(P, req, what):
    actor = _human_action(P, req)
    ctx = getattr(P, "tenant_context", None)
    if ctx is not None and not ((ctx.current_actor(actor) or {}).get("platform_owner") and ctx.trusted_host()):
        raise ApiError(403, "只有平台管理员能" + what)
    return actor


def _private(host: str) -> bool:
    """An address only this machine or this network knows (an ssh tunnel, a LAN IP): no use in a link to a client."""
    import ipaddress
    h = host.rsplit(":", 1)[0].strip("[]") if not host.endswith("]") else host.strip("[]")
    if h in ("localhost",) or h.endswith(".local"):
        return True
    try:
        return not ipaddress.ip_address(h).is_global
    except ValueError:
        return False
