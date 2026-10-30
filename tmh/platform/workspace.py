"""Small, paginated daily workspace projection. Reads never start model work."""
from .errors import ApiError
from .store import _keyed
from . import handoffs, team, project_library, coordination
from .project_git import scoped

STAGES = {"requirement": "需求", "development": "研发", "testing": "测试",
          "delivery": "交付", "operations": "运维", "unrecorded": "未登记阶段"}


@scoped
def read(P, query, viewer):
    def arg(key, default=""):
        value = query.get(key, default)
        return value[0] if isinstance(value, list) and value else value
    from .tenant_policy import directory, visible_projects
    members = directory(P)
    visible = visible_projects(P, viewer)
    project_members = {p["key"]: directory(P, p, "contributor") for p in visible}
    allowed_ids = [p["id"] for p in visible]
    viewer = viewer if viewer in members else ""
    team.schema(P)
    project = arg("project", "*")
    scope = P.store.project(project) if project not in ("", "*", "all") else None
    if project not in ("", "*", "all") and not scope:
        raise ApiError(404, "没有这个项目")
    if scope and scope["id"] not in allowed_ids:
        raise ApiError(403, "没有此项目的访问权限")
    view = arg("view", "mine" if viewer else "team")
    if view not in ("mine", "incoming", "review", "unassigned", "team"):
        raise ApiError(400, "未知工作台视图")
    stage = arg("stage", "all")
    state = arg("handoff_state", "all")
    if stage not in ("all", *STAGES):
        raise ApiError(400, "未知交接阶段")
    if state not in ("all", "waiting", "received", "returned", "blocked", "withdrawn", "none"):
        raise ApiError(400, "未知交接状态")
    try:
        offset = max(0, int(arg("offset", 0)))
        limit = min(100, max(1, int(arg("limit", 30))))
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "分页参数必须是整数") from exc
    sql = "SELECT t.*,p.key AS pkey FROM tickets t JOIN projects p ON p.id=t.project_id"
    ids = [scope["id"]] if scope else allowed_ids
    rows = [_keyed(t) for t in P.store.q(sql + " WHERE t.project_id IN (%s) ORDER BY t.updated DESC,t.id DESC" %
             (",".join("?" for _ in ids) or "NULL"), ids)]
    summaries = handoffs.summary_rows(P.store, [t["id"] for t in rows])
    tickets = {t["key"]: t for t in rows}
    work_cache = {}
    items = []
    for t in rows:
        a = team.assignment(P, t)
        needs_review = t["status"] in ("confirm", "verify")
        if viewer and a["reviewer"] == viewer and t["status"] != "closed":
            has_candidate = P.store.one("SELECT id FROM code_candidates WHERE ticket_id=? LIMIT 1", (t["id"],))
            if has_candidate:
                work_cache[t["key"]] = team.item(P, t, viewer)
                needs_review = work_cache[t["key"]]["needs_review"]
            elif P.store.one("SELECT id FROM runs WHERE ticket_id=? AND mode='fix' AND status='done' AND decision='' LIMIT 1", (t["id"],)):
                needs_review = True
        handoff = summaries.get(t["id"])
        recorded_stage = handoff["stage"] if handoff else "unrecorded"
        items.append({"key": t["key"], "title": t["title"], "project": t["key"].rsplit("-", 1)[0], "status": t["status"],
                      "priority": t["priority"], "updated": t["updated"], "assignee": a["assignee"], "reviewer": a["reviewer"],
                      "needs_review": needs_review, "reform": bool((t.get("links") or {}).get("reform")),
                      "stage": recorded_stage, "stage_label": STAGES[recorded_stage],
                      "stage_source": "handoff" if handoff else "unrecorded", "handoff": handoff,
                      "next_actor": handoff["next_actor"] if handoff else (a["reviewer"] if needs_review and a["reviewer"] else a["assignee"]) or None,
                      "waiting_seconds": handoff["waiting_seconds"] if handoff else None})
    active = [t for t in items if t["status"] != "closed"]
    predicates = {"mine": lambda t: bool(viewer) and (t["assignee"] == viewer or (t["handoff"] and t["next_actor"] == viewer)),
                  "review": lambda t: bool(viewer) and t["reviewer"] == viewer and t["needs_review"],
                  "unassigned": lambda t: t["assignee"] not in project_members.get(t["project"], {}), "team": lambda t: True}
    counts = {k: sum(1 for t in active if pred(t)) for k, pred in predicates.items()}
    predicates["incoming"] = lambda t: bool(viewer) and bool(t["handoff"]) and t["handoff"]["receiver"] == viewer and (t["handoff"]["status"] == "waiting" or (t["handoff"]["status"] == "blocked" and t["handoff"].get("resume_status") == "waiting"))
    incoming_count = sum(1 for t in active if predicates["incoming"](t))
    q = arg("q").strip().casefold()
    selected = [t for t in active if predicates[view](t)
                and (state == "all" or (t["handoff"]["status"] if t["handoff"] else "none") == state)
                and (not q or q in " ".join([str(t[k] or "") for k in ("key", "title", "project", "assignee", "reviewer", "next_actor")]
                    + [tickets[t["key"]].get("body", ""), (t["handoff"] or {}).get("block_reason", "")]).casefold())]
    stage_counts = {key: sum(t["stage"] == key for t in selected) for key in STAGES}
    selected = [t for t in selected if stage == "all" or t["stage"] == stage]
    page = selected[offset:offset + limit]
    # Candidate checks can inspect Git and preview evidence: only inspect the
    # visible page (plus actual review-queue candidates needed above for counts).
    for t in page:
        t["meeting_action"] = coordination.ticket_action(P, tickets[t["key"]])
        work = work_cache.get(t["key"]) or team.item(P, tickets[t["key"]], viewer)
        t["needs_review"] = work["needs_review"]
        if not t["handoff"]:
            t["next_actor"] = (t["reviewer"] if work["needs_review"] and t["reviewer"] else t["assignee"]) or None
        t["work"] = {key: work[key] for key in ("state", "label", "technical", "human", "needs_review", "can_review")}
        t["work"]["candidate_id"] = (work.get("candidate") or {}).get("id")
        t["action_label"] = "查看复核与证据" if work["needs_review"] else "查看任务与执行"
        t["action_href"] = ("#/team/ticket/" if work["needs_review"] else "#/t/") + t["key"]
    projects = []
    for p in visible:
        if scope and p["id"] != scope["id"]:
            continue
        ts = [t for t in items if t["project"] == p["key"]]
        profile = project_library.profile(P.store, p)
        projects.append({"key": p["key"], "name": p["name"], "description": p.get("description", ""),
                         "roles": profile["roles"], "workflow": profile["workflow"],
                         "open": sum(t["status"] != "closed" for t in ts), "total": len(ts),
                         "review": sum(t["status"] in ("confirm", "verify") for t in ts)})
    return {"viewer": viewer, "view": view, "project": scope["key"] if scope else "*", "counts": counts,
            "incoming_count": incoming_count, "stage_counts": stage_counts, "stage": stage, "handoff_state": state,
            "items": page, "total": len(selected), "offset": offset,
            "has_more": offset + limit < len(selected), "projects": projects}
