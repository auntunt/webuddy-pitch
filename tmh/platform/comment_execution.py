"""Explicit comment submission continues a task once, with a durable receipt."""
import json

from .errors import ApiError
from .store import now


def continue_comment(P, ticket, author, event_id):
    from .app import _routed_agent
    from .agents import git
    from pathlib import Path

    key = "comment-run:%s" % event_id
    with P.runner.lock:
        saved = P.store.one("SELECT result FROM idem WHERE key=?", (key,))
        if saved:
            receipt = json.loads(saved["result"])
            if receipt.get("run"):
                return receipt["run"]
            # Registration may have succeeded just before the process stopped.
            run = P.store.one("SELECT id FROM runs WHERE batch=?", (key,))
            if not run and receipt.get("retry_of"):
                run = P.store.one("SELECT id FROM runs WHERE retry_of=?", (receipt["retry_of"],))
            if run:
                return run["id"]
            raise ApiError(409, "评论已保存，续接登记中断；请检查执行记录，不会重复启动")
        if ticket["status"] == "closed":
            raise ApiError(409, "评论已保存；工单已关闭，请重新打开后继续")
        runs = P.store.runs(ticket_id=ticket["id"])
        if any(r["status"] in ("queued", "running") for r in runs):
            raise ApiError(409, "评论已保存；当前任务仍在执行，结束后点击确认上次发送即可继续")
        previous = runs[0] if runs else None
        retry = previous and previous["status"] in ("failed", "cancelled")
        mode = previous["mode"] if previous else "analyze"
        base = ""
        if retry:
            state = P.runner.retry_state(previous["id"])
            if not state["can_retry"]:
                raise ApiError(409, "评论已保存；" + "；".join(state["retry_blocked"]))
        elif previous and mode == "fix":
            old = P.store.run(previous["id"])
            if not old.get("workdir"):
                raise ApiError(409, "评论已保存；上次开发缺少工作目录，不能丢弃已有改动重新执行")
            workdir = Path(old["workdir"])
            if git(workdir, "status", "--porcelain").strip():
                raise ApiError(409, "评论已保存；上次工作树仍有未提交改动，请先处理已有成果再继续")
            base = git(workdir, "rev-parse", "HEAD").strip()
        project = P.store.project(ticket["project_id"])
        agent = _routed_agent(P, project, previous["agent"] if previous else None, "claude")
        # The database claim prevents duplicate starts even across server processes.
        with P.store.lock:
            cursor = P.store.db.execute("INSERT OR IGNORE INTO idem(key,result,ts) VALUES(?,?,?)",
                                       (key, json.dumps({"retry_of": previous["id"] if retry else None}), now()))
            P.store.db.commit()
            claimed = cursor.rowcount == 1
        if not claimed:
            return continue_comment(P, ticket, author, event_id)
        try:
            run = (P.runner.retry(previous["id"], author) if retry else
                   P.runner.start(project, ticket, agent, mode, author, base=base, batch=key,
                                  model=previous.get("model") or None if previous else None))
        except ValueError:
            # Validation failed before registration: allow a corrected retry.
            registered = P.store.one("SELECT id FROM runs WHERE batch=? OR retry_of=?",
                                     (key, previous["id"] if retry else None))
            if not registered:
                P.store.x("DELETE FROM idem WHERE key=?", (key,))
            raise
        P.store.x("UPDATE idem SET result=? WHERE key=?", (json.dumps({"run": run["id"]}), key))
        return run["id"]
