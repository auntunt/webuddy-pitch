"""Routes: projects, project library, knowledge search, project import, deliveries."""
from __future__ import annotations

import os
from pathlib import Path
from ..errors import ApiError
from . import route
from ._common import _human_action, _route_metadata, _session_actor


@route("GET", "/api/projects")
def api_projects(P, req):
    from .. import project_library
    out = []
    from ..tenant_policy import visible_projects
    for p in visible_projects(P, _session_actor(req)):
        s = P.store.stats(p["id"])
        p["open"] = sum(v for k, v in s["by_status"].items() if k != "closed")
        p["exists"] = Path(p["root"]).is_dir()
        p.update(project_library.profile(P.store, p))
        p.update(_route_metadata(P, p))
        out.append(p)
    return out


@route("POST", "/api/projects")
def api_add_project(P, req):
    b = req.body
    from .. import project_library as library
    roles, workflow = b.get('roles', []), b.get('workflow', 'development')
    library.validate_profile(roles, workflow)
    try:
        return P.store.add_project(b.get("key", ""), b.get("name", ""), os.path.expanduser(b.get("root", "")),
                                   b.get("description", ""), roles=roles, workflow=workflow)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/projects/<key>/library")
def api_library(P, req, key):
    from ..project_library import view
    return view(P.store, P.project(key))


@route("POST", "/api/projects/<key>/library")
def api_library_action(P, req, key):
    from ..project_library import act
    if req.h.headers.get('X-Webuddy-Agent') or req.user.startswith('agent:'):
        raise ApiError(403, '智能体请使用专用知识接口；共享授权与工作区创建由操作者发起')
    sensitive = req.body.get('action') in ('configure', 'add_source', 'grant', 'revoke', 'derive', 'maintain') or req.body.get('grant') is True
    if sensitive:
        # X-TMH-User is an audit label, not operator authentication. A valid
        # signed login session or the existing independent credential is needed.
        if not getattr(req.h, '_who', ''):
            from ..operator_access import require
            require(P, req.h.headers)
        from ..signoff import human
        if not human(getattr(req.h, '_who', '') or req.user):
            raise ApiError(403, '请由已登录的操作者管理共享与开发工作区')
    try:
        return act(P, P.project(key), req.body, req.user)
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc


@route("GET", "/api/projects/<key>/knowledge/search")
def api_knowledge_search(P, req, key):
    from ..project_library import search
    try:
        return search(P.store, P.project(key), req.arg('q'), int(req.arg('limit') or 20), int(req.arg('offset') or 0))
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


@route("GET", "/api/projects/<key>/knowledge/file")
def api_knowledge_file(P, req, key):
    from ..project_library import read
    try:
        return read(P.store, P.project(key), req.arg('revision_id'), req.arg('path'))
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc


@route("GET", "/api/org/knowledge")
def api_org_knowledge(P, req):
    """Organization knowledge v0: a read-only roll-up across every project (G8).

    No q: the build summary (type counts / projects read). With q: search results
    with provenance. Never writes, never runs a build, an agent or a command.
    """
    from .. import org_knowledge as org
    from ..tenant_policy import visible_projects
    allowed = {p["key"] for p in visible_projects(P, req.user)}
    q = (req.arg("q") or "").strip()
    types = [t.strip() for t in (req.arg("type") or "").split(",") if t.strip()]
    bad = [t for t in types if t not in org.TYPES]
    if bad:
        raise ApiError(400, "未知类型：%s（可选 %s）" % ("、".join(bad), "、".join(org.TYPES)))
    try:
        limit = int(req.arg("limit") or 20)
    except ValueError as exc:
        raise ApiError(400, "limit 必须是整数") from exc
    if limit < 1 or limit > 200:
        raise ApiError(400, "limit 取值范围 1–200")
    if q:
        items = org.search(P.store, q, limit=limit, types=types or None, allowed_project_keys=allowed)
        return {"query": q, "types": types or list(org.TYPES), "limit": limit,
                "items": items, "count": len(items), "readonly": True}
    built = org.build(P.store, allowed_project_keys=allowed)
    filtered = [i for i in built["items"] if not types or i["type"] in types]
    items = filtered[:limit]
    return {"query": "", "summary": built["stats"], "projects": built["projects_read"],
            "provenance_projects": built["provenance_projects"], "items": items,
            "count": len(filtered), "returned": len(items), "notice": built["notice"], "readonly": True}


@route("GET", "/api/projects/<key>/habits")
def api_habits(P, req, key):
    """Development-habit signals (G9), read-only: personal (redacted by default) or anonymous team."""
    from .. import habits
    p = P.project(key)  # unknown project -> the platform's usual 404
    team = (req.arg("team") or "").strip().lower() in ("1", "true", "yes", "on")
    if team:
        return habits.team(P.store, p["id"])
    user = (req.arg("user") or "").strip() or req.user
    if not user:
        raise ApiError(400, "个人视图需要 user=<成员>；团队视图请用 team=1")
    redact = (req.arg("redact") or "").strip().lower() not in ("0", "false", "no", "off")
    try:
        return habits.personal(P.store, user, p["id"], redact=redact)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


@route("GET", "/api/projects/<key>")
def api_project(P, req, key):
    p = P.project(key)
    p.update(_route_metadata(P, p))
    from .. import learning_experiment_views as V
    return {"project": p, "stats": P.store.stats(p["id"]), "kb": P.kb.kb_overview(p),
            "runs": V.runs(P, _session_actor(req) or req.user, project_id=p["id"], limit=8),
            "recent": P.store.tickets(project_id=p["id"], limit=8)}


@route("POST", "/api/projects/bootstrap")
def api_bootstrap_project(P, req):
    from ..project_bootstrap import create
    return create(P, req.body, req.user)


def _importer(req):
    if req.h.headers.get('X-Webuddy-Agent') or req.user.startswith('agent:'):
        raise ApiError(403, '导入项目代码需由登录的操作者发起')


@route("POST", "/api/projects/import")
def api_import_project(P, req):
    from ..project_import import start
    _importer(req)
    return start(P, req.body, req.user)


@route("GET", "/api/projects/import/<job>")
def api_import_status(P, req, job):
    from ..project_import import status
    return status(P, job)


@route("POST", "/api/projects/import/<job>/chunk")
def api_import_chunk(P, req, job):
    from ..project_import import chunk
    _importer(req)
    return chunk(P, job, req.body, req.user)


@route("POST", "/api/projects/import/<job>/finish")
def api_import_finish(P, req, job):
    from ..project_import import finish
    _importer(req)
    return finish(P, job, req.user)


@route("GET", "/api/delivery/catalog")
def api_delivery_catalog(P, req):
    from ..delivery import catalog
    return catalog()


@route("POST", "/api/delivery-content")
def api_create_delivery_content(P, req):
    from .. import delivery_content
    return delivery_content.create(P, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/deliveries/<did>/content")
def api_delivery_content(P, req, did):
    from .. import delivery_content
    return delivery_content.read(P, did, _session_actor(req))


@route("POST", "/api/deliveries/<did>/content")
def api_save_delivery_content(P, req, did):
    from .. import delivery_content
    return delivery_content.act(P, did, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/deliveries/<did>/coverage")
def api_delivery_coverage(P, req, did):
    from .. import delivery_coverage
    return delivery_coverage.read(P, did, _session_actor(req))


@route("POST", "/api/deliveries/<did>/coverage")
def api_delivery_coverage_action(P, req, did):
    from .. import delivery_coverage
    return delivery_coverage.act(P, did, req.body, _human_action(P, req, strict=True))


@route("GET", "/api/deliveries")
def api_deliveries(P, req):
    from ..delivery import list_deliveries
    return list_deliveries(P, req.arg("project"))


@route("POST", "/api/deliveries")
def api_create_delivery(P, req):
    from ..delivery import create
    return create(P, req.body, req.user)


@route("GET", "/api/deliveries/<did>")
def api_delivery(P, req, did):
    from ..delivery import view
    return view(P, did)


@route("POST", "/api/deliveries/<did>")
def api_delivery_action(P, req, did):
    from ..delivery import act
    return act(P, did, req.body, req.user)
