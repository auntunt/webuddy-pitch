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
                       "first_line": (t.get("body") or "").strip().split("\n", 1)[0],
                       "agent": (t.get("links") or {}).get("agent", ""), "model": (t.get("links") or {}).get("model", "")} for t in rows]}


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
        from ..agents import available, pick_model, load_config
        from ..agent_page import default_executor
        agent = str(b.get("agent") or "")
        names = [a["name"] for a in available(P.data_dir) if a["available"]]
        if agent and agent not in names:
            raise ApiError(400, "执行器 %s 不可用" % agent)
        agent = agent or default_executor(P.data_dir, names) or (names[0] if names else "")
        if not agent:
            raise ApiError(400, "没有可用的执行器，请先在智能体页面连接一个")
        model = str(b.get("model") or "")
        conf_agent = load_config(P.data_dir)[agent]
        model = pick_model(conf_agent, "analyze", model or None) if model else ""
        t = P.store.create_ticket(p["id"], title, req.user, body=body, type="feature", links={"goal": goal, "agent": agent, "model": model})
    except ValueError as e:
        raise ApiError(400, str(e))
    from .. import task_secrets
    names = task_secrets.save(P.data_dir, t["key"], b.get("secrets") or [])
    P.store.event(t["id"], req.user, "flow", "任务创建：要做到 %s" % goal + ("；测试环境项：" + "、".join(names) if names else ""))
    P.flow.submit(p, t)  # both goals enter the existing line; 出方案 stops after the plan step
    return {"key": t["key"], "goal": goal, "secret_names": names}



@route("GET", "/api/task-executors")
def api_task_executors(P, req):
    from ..agents import available, load_config
    from ..agent_page import default_executor, last_result
    conf = load_config(P.data_dir)
    items = [a for a in available(P.data_dir) if a["available"]]
    rows = [{"name": a["name"], "title": a.get("title", a["name"]), "available": True,
             "last_ok": last_result(P.data_dir, a["name"]), "models": [m[0] for m in conf[a["name"]].get("models") or []]}
            for a in items]
    names = [r["name"] for r in rows]
    agent = default_executor(P.data_dir, names) or (names[0] if names else "")
    models = next((r["models"] for r in rows if r["name"] == agent), [])
    return {"executors": rows, "default_agent": agent,
            "default_model": (conf.get(agent, {}).get("defaults") or {}).get("plan") or (models[0] if models else "")}
