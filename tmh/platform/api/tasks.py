"""Routes: /next/ task list and creation. A task is an ordinary ticket; creating one enters the existing flow."""
from __future__ import annotations

from ..errors import ApiError
from . import route
from ._common import _allowed_project_ids

STAGES = ("出方案", "修改并测试")


@route("GET", "/api/projects/<key>/tasks")
def api_tasks(P, req, key):
    p = P.project(key)
    rows = P.store.tickets(project_id=p["id"], limit=200, allowed_projects=_allowed_project_ids(P, req))
    return {"items": [{"key": t["key"], "title": t["title"], "stage": t["status"],
                       "first_line": (t.get("body") or "").strip().split("\n", 1)[0]} for t in rows]}


@route("POST", "/api/projects/<key>/tasks")
def api_new_task(P, req, key):
    p = P.project(key)
    b = req.body or {}
    title, body = (b.get("title") or "").strip(), (b.get("body") or "").strip()
    goal = b.get("goal") or "修改并测试"
    if not title or not body:
        raise ApiError(400, "任务名和工作内容必填")
    if goal not in STAGES:
        raise ApiError(400, "要做到哪一步只能是 出方案 或 修改并测试")
    try:
        t = P.store.create_ticket(p["id"], title, req.user, body=body, type="feature")
    except ValueError as e:
        raise ApiError(400, str(e))
    from .. import task_secrets
    names = task_secrets.save(P.data_dir, t["key"], b.get("secrets") or [])
    P.store.event(t["id"], req.user, "flow", "任务创建：要做到 %s" % goal + ("；测试环境项：" + "、".join(names) if names else ""))
    if goal == "修改并测试":
        P.flow.submit(p, t)
    return {"key": t["key"], "goal": goal, "secret_names": names}
