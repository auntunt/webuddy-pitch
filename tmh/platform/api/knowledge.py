"""Routes: flows, knowledge base, code maps, architecture, knowledge questions."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote
from ..errors import ApiError
from . import route
from ._common import _direct_api_allowed, _human_action, _platform_admin, _session_actor


@route("GET", "/api/projects/<key>/related")
def api_related(P, req, key):
    return P.kb.related(P.project(key), req.arg("q"), int(req.arg("limit") or 8))


@route("GET", "/api/projects/<key>/flows/<fid>")
def api_flow(P, req, key, fid):
    return P.kb.flow_detail(P.project(key), unquote(fid))


@route("GET", "/api/projects/<key>/kb")
def api_kb(P, req, key):
    p = P.project(key)
    return {"overview": P.kb.kb_overview(p), "pages": P.kb.kb_pages(p, req.arg("status"), req.arg("q"), req.arg("kind"))}


@route("GET", "/api/projects/<key>/kb/tree")
def api_kb_tree(P, req, key):
    p = P.project(key)
    t = P.kb.kb_tree(p)
    t["coverage"] = P.kb.kb_overview(p).get("coverage") if t["built"] else None
    t["built_at"] = P.kb.kb_overview(p).get("built_at", "") if t["built"] else ""
    return t


@route("GET", "/api/projects/<key>/maps")
def api_code_maps(P, req, key):
    from .. import code_maps
    from ...agent_contract import validate
    operation='map_get' if req.arg('map_id') else 'maps_list'
    args={'project':key}
    for name in ('map_id','node_id','knowledge_id','request_id'):
        if req.arg(name):args[name]=req.arg(name)
    try:
        for name in ('line','limit','after'):
            if req.arg(name):args[name]=int(req.arg(name))
        args=validate(operation,args)
    except ValueError as exc:raise ApiError(400,str(exc)) from exc
    return code_maps.execute(P,P.project(key),req.user,operation,args)


@route("POST", "/api/projects/<key>/maps")
def api_code_map_create(P, req, key):
    from .. import code_maps
    from ...agent_contract import validate
    try:args=validate('map_create',dict(req.body,project=key))
    except ValueError as exc:raise ApiError(400,str(exc)) from exc
    return code_maps.create(P,P.project(key),req.user,args)


@route("GET", "/api/projects/<key>/statecharts")
def api_statecharts(P, req, key):
    return P.kb.statecharts(P.project(key))


@route("GET", "/api/projects/<key>/statecharts/renderer")
def api_statechart_renderer(P, req, key):
    """The chart renderer (vendor/pele.global.js) as JSON, so tenant pages fetch it with their context header like any read."""
    P.project(key)
    return {"js": (Path(__file__).parent.parent / "vendor" / "pele.global.js").read_text(encoding="utf-8")}


@route("POST", "/api/projects/<key>/entries/detect")
def api_entries_detect(P, req, key):
    """Model-detected entry rules: writes .tmh/entry-rules.json; needs the router model configured."""
    _platform_admin(P, req, "检测未覆盖入口")
    from ... import entry_rules
    from .. import llm
    p = P.project(key)
    conf = llm.conf(P, p)
    try:
        return entry_rules.detect(Path(p["root"]), conf)
    except ValueError as exc:
        raise ApiError(400, str(exc))


@route("GET", "/api/projects/<key>/arch")
def api_arch(P, req, key):
    return P.kb.arch(P.project(key))


@route("GET", "/api/projects/<key>/arch/<did>")
def api_arch_domain(P, req, key, did):
    return P.kb.domain_detail(P.project(key), did)


@route("GET", "/api/projects/<key>/kb/page")
def api_kb_page(P, req, key):
    return P.kb.kb_page(P.project(key), req.arg("id"))


def _kb_confirm_actor(P, req):
    """Who confirms a knowledge page.

    With no accounts, no tenant and no session, an explicit same-origin browser POST
    from the machine itself is allowed and recorded as a local operator — not a
    verified personal account or a supplied display name. Every account, tenant,
    agent or forwarded request keeps the original personal-login rule."""
    from .. import login
    handler = getattr(req, "h", None)
    headers = getattr(handler, "headers", {})
    if (getattr(P, "tenant_context", None) is not None or login.has_accounts(P.data_dir)
            or _session_actor(req) or headers.get("X-Webuddy-Agent") or str(req.user).startswith("agent:")):
        return _human_action(P, req, strict=True)
    import ipaddress
    from urllib.parse import urlsplit

    def loopback(value):
        try:
            return ipaddress.ip_address(value).is_loopback
        except (ValueError, TypeError):
            return False

    peer = getattr(handler, "client_address", ("",))[0]
    bound = getattr(getattr(handler, "server", None), "server_address", ("",))[0]
    origin, host = headers.get("Origin", ""), headers.get("Host", "")
    try:
        source = urlsplit(origin)
        target = urlsplit("http://" + host)
        same_origin = (source.scheme == "http" and source.netloc == host and
                       source.path in ("", "/") and not source.query and not source.fragment and
                       not source.username and not target.username and
                       (target.hostname == "localhost" or loopback(target.hostname)))
    except ValueError:
        same_origin = False
    # A LAN listener can still serve a loopback-only browser operation.
    if not (loopback(peer) and (loopback(bound) or bound in ("0.0.0.0", "::")) and same_origin and
            headers.get("X-TMH") == "1" and headers.get("Sec-Fetch-Site") == "same-origin" and
            not headers.get("Forwarded") and not headers.get("X-Forwarded-For")):
        raise ApiError(403, "免账号知识确认仅支持本机单用户网页，请从本机地址打开知识页后手动确认")
    return "本机操作者(%s)" % (os.environ.get("USERNAME") or os.environ.get("USER") or "local")


@route("POST", "/api/projects/<key>/kb/confirm")
def api_kb_confirm(P, req, key):
    from ... import kb
    actor = _kb_confirm_actor(P, req)
    if req.body.get("by") not in (None, "", actor):
        raise ApiError(403, "人工确认必须记在当前登录账号下，不能代用他人姓名")
    p = P.project(key)
    try:
        kb.confirm(P.root(p), req.body.get("id", ""), actor, req.body.get("note", ""))
    except KeyError:
        raise ApiError(404, "知识页不存在")
    return {"ok": True}


@route("GET", "/api/projects/<key>/kb/questions")
def api_kb_questions(P, req, key):
    from ... import kbqa
    root = P.root(P.project(key))
    return {"questions": kbqa.questions(root), "stats": kbqa.stats(root), "router": {k: v for k, v in kbqa.router_conf(root).items() if k != "key_env"}}


@route("POST", "/api/projects/<key>/kb/ask")
def api_kb_ask(P, req, key):
    from ... import kbqa
    q = (req.body.get("question") or "").strip()
    if not q:
        raise ApiError(400, "问题不能为空")
    n = kbqa.ask(P.root(P.project(key)), q, [x for x in req.body.get("pages") or [] if isinstance(x, str)], req.body.get("to", ""), req.user)
    return {"n": n}


@route("POST", "/api/projects/<key>/kb/answer")
def api_kb_answer(P, req, key):
    """A person records the business side's answer, word for word; the pages it concerns are queued for revision."""
    from ... import kbqa
    actor = _human_action(P, req, strict=True)
    if req.body.get("by") not in (None, "", actor):
        raise ApiError(403, "人工答复必须记在当前登录账号下，不能代用他人姓名")
    text = (req.body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "答复不能为空")
    try:
        return kbqa.answer(P.root(P.project(key)), int(req.body.get("n") or 0), text, actor)
    except KeyError as e:
        raise ApiError(404, e.args[0])
    except ValueError as e:
        raise ApiError(400, e.args[0])


@route("POST", "/api/projects/<key>/kb/triage")
def api_kb_triage(P, req, key):
    from ... import kbqa
    p = P.project(key)
    root = P.root(p)
    text = (req.body.get("request") or "").strip()
    if not text:
        raise ApiError(400, "需求不能为空")
    if req.body.get("model", True) is not False and not _direct_api_allowed(P, p):
        raise ApiError(400, "此项目仅通过配置执行器调用模型，请使用任务分析或设置 model=false 使用规则分类")
    res = kbqa.triage(root, text, use_model=req.body.get("model", True) is not False, channel="web", sender=req.user)
    if req.body.get("record"):
        res["recorded"] = kbqa.record(root, res, req.user)
    return res
