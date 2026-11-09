"""Routes: clients, workbench intake, systems, requirements, versions, production requests, shares, today."""
from __future__ import annotations

import os
import re
from ..errors import ApiError
from . import route
from ._common import _chooser, _human_action, _private


@route("GET", "/api/clients")
def api_clients(P, req):
    from .. import workbench
    return {"clients": workbench.summary(P) if req.arg("counts") else workbench.clients(P)}


@route("POST", "/api/clients")
def api_client_new(P, req):
    from .. import workbench
    return workbench.create_client(P, req.body, req.user)


@route("GET", "/api/clients/<cid>")
def api_client(P, req, cid):
    from .. import workbench
    return workbench.client_view(P, cid)


@route("POST", "/api/clients/<cid>")
def api_client_act(P, req, cid):
    """{"action": "update", ...fields} | {"action": "delete"} | {"action": "link", "kind": "intake|chat|ticket", "ref": "..."} |
    {"action": "unlink", "kind", "ref"}"""
    from .. import workbench
    a = req.body.get("action") or "update"
    if a == "update":
        return workbench.update_client(P, cid, req.body)
    if a == "delete":
        return workbench.delete_client(P, cid)
    if a == "link":
        return workbench.link(P, cid, req.body.get("kind", ""), req.body.get("ref", ""), req.user)
    if a == "unlink":
        return workbench.unlink(P, cid, req.body.get("kind", ""), req.body.get("ref", ""), req.user)
    raise ApiError(400, "action 只能是 update、delete、link、unlink")


@route("POST", "/api/workbench/intake")
def api_workbench_intake(P, req):
    """What a client said, pasted once: {"project", "text", "client": id | "client_name": "新客户"} starts the requirement
    conversation (intake.py, unchanged) and records whose words they were."""
    from .. import intake, workbench
    b = req.body
    p = P.project(b.get("project") or "")
    cid = b.get("client")
    if cid:
        workbench.client(P, cid)
    elif (b.get("client_name") or "").strip():
        name = b["client_name"].strip()[:40]
        hit = next((c for c in workbench.clients(P) if c["name"] == name), None)
        if hit:
            cid = hit["id"]
        else:
            try:
                cid = workbench.create_client(P, {"name": name, "projects": [p["key"]]}, req.user)["id"]
            except ApiError as e:  # someone else added the same name a moment ago: theirs is ours
                hit = next((c for c in workbench.clients(P) if c["name"] == name), None) if e.code == 409 else None
                if not hit:
                    raise
                cid = hit["id"]
    sid = b.get("system")
    if sid:
        if workbench.system(P, sid)["project"] != p["key"]:
            raise ApiError(409, "这个系统不属于项目 %s" % p["key"])
    elif (b.get("system_name") or "").strip():
        name = b["system_name"].strip()[:40]
        hit = next((x for x in workbench.systems(P, p["key"]) if x["name"] == name), None)
        sid = hit["id"] if hit else workbench.create_system(P, p["key"], name, "", req.user)["id"]
    s = intake.start(P, p, b.get("text", ""), req.user, b.get("channel") or "web", _chooser(P, p) if b.get("model", True) is not False else None,
                     big=bool(b.get("big")), agent=b.get("model", True) is not False)
    if cid:
        workbench.link(P, cid, "intake", s["id"], req.user)
    if sid:
        workbench.link_system(P, sid, "intake", s["id"], req.user)
    return dict(s, client=int(cid) if cid else None, system=int(sid) if sid else None)


@route("GET", "/api/projects/<key>/systems")
def api_systems(P, req, key):
    from .. import workbench
    return {"systems": workbench.systems(P, P.project(key)["key"])}


@route("POST", "/api/projects/<key>/systems")
def api_system_new(P, req, key):
    """{"name", "notes"}: a deployment of this project (客户 → 项目 → 系统)."""
    from .. import workbench
    return workbench.create_system(P, key, req.body.get("name", ""), req.body.get("notes", ""), req.user)


@route("POST", "/api/tickets/<key>/system")
def api_ticket_system(P, req, key):
    """{"system": id | null}: file the ticket under one system of its project."""
    from .. import workbench
    return workbench.link_system(P, req.body.get("system"), "ticket", key, req.user)


@route("GET", "/api/requirements")
def api_requirements(P, req):
    from .. import workbench
    pk = req.arg("project")
    if pk not in ("", "*"):
        P.project(pk)
    return workbench.requirements(P, "" if pk in ("", "*") else pk)


@route("GET", "/api/projects/<key>/versions")
def api_versions(P, req, key):
    from .. import workbench
    return workbench.versions(P, key)


@route("GET", "/api/projects/<key>/prod-requests")
def api_prod_requests(P, req, key):
    from .. import prod_release
    p = P.project(key)
    return {"requests": prod_release.requests(P.data_dir, p["key"]), "deploy_command": bool(prod_release.deploy_command(P.data_dir, p["key"]))}


@route("POST", "/api/projects/<key>/prod-requests")
def api_prod_request_act(P, req, key):
    """{"action": "request", "version", "checked", "note"} | {"action": "approve" | "reject" | "deployed", "id", "note"}.
    Every step is a person's: tokens and agents cannot ask for, approve or record a production release."""
    from .. import prod_release
    _human_action(P, req)
    p, b = P.project(key), req.body
    a, note = b.get("action"), str(b.get("note") or "")
    if a == "request":
        return prod_release.request(P, p["key"], str(b.get("version") or ""), req.user, note, str(b.get("checked") or ""))
    r = prod_release.get(P.data_dir, str(b.get("id") or ""))
    if r["project"] != p["key"]:
        raise ApiError(404, "没有这条上生产申请")
    if a in ("approve", "reject"):
        return prod_release.decide(P, r["id"], a == "approve", req.user, note)
    if a == "deployed":
        return prod_release.deployed(P, r["id"], req.user, note)
    raise ApiError(400, "action 只能是 request、approve、reject、deployed")


@route("POST", "/api/projects/<key>/standing")
def api_standing(P, req, key):
    """{"action": "start" | "stop"}: the main line's current version, running for people and clients to open."""
    from .. import preview, workbench
    p = P.project(key)
    a = req.body.get("action")
    if a == "start":
        return workbench.start_standing(P, p, req.user)
    if a == "stop":
        preview.stop(P, workbench.standing_key(p["key"]))
        return workbench.standing(P, p)
    raise ApiError(400, "action 只能是 start 或 stop")


@route("POST", "/api/projects/<key>/shares")
def api_share_new(P, req, key):
    """A link to the current version for a client: {"client": id, "days": 30}. The link itself is only in this answer."""
    from .. import workbench
    r = workbench.share(P, key, req.user, req.body.get("client"), req.body.get("days") or workbench.SHARE_DAYS)
    return dict(r, **_public_link(P, req, r["path"]))


def _public_link(P, req, path: str) -> dict:
    """The whole address for a link sent outside: TMH_PUBLIC_URL, else where people reach us, else this request's
    host; with a warning when that is an address the client cannot reach."""
    base = os.environ.get("TMH_PUBLIC_URL", "").rstrip("/") or getattr(P, "public_url", "")
    if not base:
        host = (req.h.headers.get("Host") or "127.0.0.1").strip()
        base = "%s://%s" % ("https" if (req.h.headers.get("X-Forwarded-Proto") or "") == "https" else "http", host)
    host = re.sub(r"^https?://", "", base).split("/")[0]
    private = _private(host)
    return {"url": base + path, "private": private,
            "warn": "这个地址（%s）只有本机或内网能打开，客户点不开。启动前设置 TMH_PUBLIC_URL 为对外地址，或从对外地址登录一次再生成。" % host if private else ""}


@route("POST", "/api/projects/<key>/shares/<sid>/revoke")
def api_share_revoke(P, req, key, sid):
    from .. import workbench
    P.project(key)
    return workbench.revoke(P, key, sid, req.user)


@route("GET", "/api/today")
def api_today(P, req):
    """What needs the owner, what the AI did since ?since=, what it is doing now, new versions, open questions."""
    from .. import workbench
    return workbench.today(P, req.arg("since"))


@route("GET", "/api/chats")
def api_chats(P, req):
    """Group-chat conversations the robot has seen, for attaching one to a client."""
    from .. import workbench
    out = []
    for ck, c in workbench._convs(P).items():
        out.append({"id": ck, "project": c.get("project"), "channel": c.get("channel"), "seen": c.get("seen"),
                    "tickets": c.get("tickets") or [], "client": workbench.client_of(P, "chat", ck)})
    return {"chats": sorted(out, key=lambda x: x.get("seen") or "", reverse=True)}
