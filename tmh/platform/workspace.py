"""Small, paginated daily workspace projection. Reads never start model work."""
from .errors import ApiError
from .store import _keyed
from . import login, team, project_library


def read(P, query, viewer):
    def arg(key, default=""):
        value = query.get(key, default)
        return value[0] if isinstance(value, list) and value else value
    members = login.load_users(P.data_dir)
    viewer = viewer if viewer in members else ""
    team.schema(P)
    project = arg("project", "*")
    scope = P.store.project(project) if project not in ("", "*", "all") else None
    if project not in ("", "*", "all") and not scope:
        raise ApiError(404, "没有这个项目")
    view = arg("view", "mine" if viewer else "team")
    if view not in ("mine", "review", "unassigned", "team"):
        raise ApiError(400, "未知工作台视图")
    try:
        offset = max(0, int(arg("offset", 0)))
        limit = min(100, max(1, int(arg("limit", 30))))
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "分页参数必须是整数") from exc
    sql = "SELECT t.*,p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id"
    rows = [_keyed(t) for t in P.store.q(sql + (" WHERE t.project_id=?" if scope else "") + " ORDER BY t.updated DESC,t.id DESC", (scope["id"],) if scope else ())]
    items = []
    for t in rows:
        a = team.assignment(P, t)
        needs_review = t["status"] in ("confirm", "verify")
        if viewer and a["reviewer"] == viewer and t["status"] != "closed":
            has_candidate = P.store.one("SELECT id FROM code_candidates WHERE ticket_id=? LIMIT 1", (t["id"],))
            if has_candidate:
                needs_review = team.item(P, t, viewer)["needs_review"]
            elif P.store.one("SELECT id FROM runs WHERE ticket_id=? AND mode='fix' AND status='done' AND decision='' LIMIT 1", (t["id"],)):
                needs_review = True
        items.append({"key": t["key"], "title": t["title"], "project": t["key"].rsplit("-", 1)[0], "status": t["status"],
                      "priority": t["priority"], "updated": t["updated"], "assignee": a["assignee"], "reviewer": a["reviewer"],
                      "needs_review": needs_review, "reform": bool((t.get("links") or {}).get("reform"))})
    active = [t for t in items if t["status"] != "closed"]
    predicates = {"mine": lambda t: bool(viewer) and t["assignee"] == viewer,
                  "review": lambda t: bool(viewer) and t["reviewer"] == viewer and t["needs_review"],
                  "unassigned": lambda t: t["assignee"] not in members, "team": lambda t: True}
    counts = {k: sum(1 for t in active if pred(t)) for k, pred in predicates.items()}
    q = arg("q").strip().casefold()
    selected = [t for t in active if predicates[view](t) and (not q or q in " ".join(str(t[k]) for k in ("key", "title", "project", "assignee", "reviewer")).casefold())]
    projects = []
    for p in P.store.projects():
        if scope and p["id"] != scope["id"]:
            continue
        ts = [t for t in items if t["project"] == p["key"]]
        profile = project_library.profile(P.store, p)
        projects.append({"key": p["key"], "name": p["name"], "description": p.get("description", ""),
                         "roles": profile["roles"], "workflow": profile["workflow"],
                         "open": sum(t["status"] != "closed" for t in ts), "total": len(ts),
                         "review": sum(t["status"] in ("confirm", "verify") for t in ts)})
    return {"viewer": viewer, "view": view, "project": scope["key"] if scope else "*", "counts": counts,
            "items": selected[offset:offset + limit], "total": len(selected), "offset": offset,
            "has_more": offset + limit < len(selected), "projects": projects}
