"""Where an open ticket stands, worked out from one table read top to bottom: the first row that holds is the stage.

Every row names who is waited on, so the inbox ("does anything need me now"), the "who is it waiting for" chip on
requirements, clients and the ticket page, and the progress bar all read the same answer instead of each guessing
from statuses.

who: "person" (the team must act), "client" (someone outside signs or answers), "agent" (the automatic line or a
check is on it), "assignee" (the person who took it over is writing it) or "none" (closed).
step: the progress-bar step the ticket is at."""
from __future__ import annotations

from .store import now as _now

# key, who, step, label, action: the rows in the order `decide` tries them
TABLE = [
    ("release_waiting", "person", "closed", "等你确认上线", "重试上线"),
    ("shipped", "none", "closed", "已上线", ""),
    ("closed", "none", "closed", "已关闭", ""),
    ("running", "agent", "", "AI 正在处理", "看实时过程"),
    ("handwork_check", "agent", "fix", "正在构建和检查提交", ""),
    ("client_change", "person", "intake", "客户改了已确认的检查项，等你决定", "去决定"),
    ("recovering", "agent", "intake", "AI 正在按已保存答复补全检查项", ""),
    ("recovery_stuck", "person", "intake", "客户答复已保存，AI 没理解完，等你处理", "去处理"),
    ("open_ac", "client", "intake", "等客户确认需求", "看要确认的问题"),
    ("recheck", "person", "verify", "等你重新验证", "去重新验证"),
    ("failed", "person", "", "AI 没做成，需要你看看", "看原因"),
    ("review", "person", "fix", "改好了，请你看一下改动", "看改动"),
    ("returned", "person", "verify", "客户退回了", "看退回原因"),
    ("rejected", "person", "verify", "验收没通过", "看退回原因"),
    ("expired", "person", "verify", "签收链接过期了", "重发链接"),
    ("signing", "client", "verify", "等客户签字", "看测试记录"),
    ("verify", "person", "verify", "改好了，请你验收", "去验收"),
    ("agent_request", "person", "", "CLI / MCP 已接上，等你给下一步", "去处理"),
    ("handwork_failed", "person", "fix", "提交检查没通过", "看检查结果"),
    ("handwork", "assignee", "fix", "人工在写", ""),
    ("hold", "person", "", "你已接管，AI 暂停", "去处理"),
    ("epic_paused", "person", "", "大需求暂停", "去处理"),
    ("later", "agent", "", "排队中", ""),
    ("accepted", "person", "verify", "改完了，等开始测试", "开始测试"),
    ("confirm", "person", "analyze", "AI 有结论了，等你确认", "看结论"),
    ("cancelled", "person", "", "AI 运行已取消，等你继续", "去处理"),
    ("ops", "person", "", "运维排查：查相似经验、只读查数据、记结论", "去排查"),
    ("stalled", "person", "", "没人在处理", "接手"),
    ("queued", "agent", "", "排队中", ""),
    ("idle", "person", "", "等你决定下一步", "去处理"),
]
ROW = {k: (who, step, label, action) for k, who, step, label, action in TABLE}
MODE_STEP = {"analyze": "analyze", "plan": "plan", "fix": "fix", "verify": "verify"}


def row(key: str, **extra) -> dict:
    who, step, label, action = ROW[key]
    out = {"key": key, "who": who, "step": step, "label": label, "action": action}
    out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out


def decide(t: dict, f: dict) -> dict:
    """Pure: the stage of ticket `t` from the facts `f` gathered by `compute` (all optional):
    last (latest non-ask run, with dl = diff length), live (a queued/running run), handwork_busy, check (the
    hand-written submission's check), release_wait (a closed ticket's merge that waits for a person), recovery, wait (pending re-verification), ev (sign-off state), version (released),
    auto, agent, stall (why nothing will start it), now, modes (run mode names), next_step (callable)."""
    r, live, ev, lk, s = f.get("last") or {}, f.get("live"), f.get("ev") or {}, t.get("links") or {}, t["status"]
    modes = f.get("modes") or {}
    step = MODE_STEP.get(r.get("mode"), "")
    manual = lk.get("handwork") or (lk.get("hold") if r.get("agent") == "人工" else "")
    if isinstance(manual, bool):
        manual = (t.get("assignee") or "待分配") if manual else ""
    recovery = f.get("recovery") or {}
    if s == "closed":
        if f.get("release_wait"):
            return row("release_waiting", note=f["release_wait"][:120], state="done")
        return row("shipped", label="已上线 " + f["version"]) if f.get("version") else row("closed")
    if live:
        m = modes.get(live["mode"], "处理")
        why = "等待智能体开始%s" % m if live["status"] == "queued" else "AI 正在%s" % m
        return row("running", label=why + ("；当前步骤结束后暂停" if lk.get("hold") else ""), step=MODE_STEP.get(live["mode"], ""))
    if f.get("handwork_busy"):
        return row("handwork_check", label="正在构建和检查%s的提交" % (manual or "人工"))
    if lk.get("client_change"):
        return row("client_change")
    if recovery.get("status") == "running":
        return row("recovering")
    if recovery.get("status") in ("failed", "blocked"):
        return row("recovery_stuck")
    if lk.get("open_ac"):
        return row("open_ac", label="有 %s 项检查要和客户确认" % lk["open_ac"])
    wait = f.get("wait")
    if wait:
        g = row("recheck", label=wait.get("why"), since=r.get("ended"))
        if wait.get("state"):
            g["state"] = wait["state"]
        return g
    if r.get("status") == "failed":
        return row("failed", since=r.get("ended"), step=step)
    if r.get("mode") == "fix" and r.get("status") == "done" and not r.get("decision") and r.get("dl"):
        return row("review", since=r.get("ended"))
    if s == "doing" and ev.get("status") == "rejected":
        d = ev.get("decision") or {}
        note = (d.get("note") or "")[:80]
        if d.get("via") == "签收链接":  # the platform's own 验收不通过 is the team's verdict, not the client's
            return row("returned", label="%s退回了" % (d.get("signer") or "客户"), note=note, since=d.get("ts"))
        return row("rejected", label="%s验收没通过" % (d.get("signer") or ""), note=note, since=d.get("ts"))
    if s == "verify":
        link = (ev.get("links") or [None])[-1]
        if link and ev.get("status") in ("ready", "incomplete") and (link.get("expires") or "9") < (f.get("now") or _now()):
            return row("expired", label="给%s的签收链接过期了" % (link.get("signer") or "客户"), since=link.get("expires"))
        if link and ev.get("status") in ("ready", "incomplete"):
            return row("signing", label="等%s签字" % (link.get("signer") or "客户"), since=link.get("ts"))
        return row("verify", label="改好了，请你验收（测试记录还不齐）" if ev.get("status") == "incomplete" else "")
    if lk.get("agent_request"):
        return row("agent_request")
    if manual:
        verdict = (f.get("check") or {}).get("verdict")
        if verdict in ("fail", "unknown"):
            return row("handwork_failed", label=("提交检查没通过" if verdict == "fail" else "提交还没检查完") + "，等 %s 处理" % manual)
        return row("handwork", label="%s 在写" % manual)
    if lk.get("hold"):
        return row("hold", label="%s 已接管，AI 暂停" % lk["hold"], step=step)
    if (lk.get("epic") or {}).get("paused"):
        return row("epic_paused", label="大需求暂停：" + lk["epic"]["paused"])
    if lk.get("later"):
        return row("later", label=lk["later"])
    if r.get("mode") == "fix" and (r.get("decision") or "").startswith("accepted"):
        return row("accepted", label="改动在分支 %s，等开始测试" % r["decision"][9:].split("@")[0])
    if s == "confirm":
        return row("confirm")
    if r.get("status") == "cancelled":
        return row("cancelled", step=step)
    if t.get("type") == "ops" and not r:  # the automatic line never takes an ops ticket: it waits for ops, not a queue
        return row("ops")
    if not f.get("auto") or not f.get("agent"):
        if s in ("new", "analyzing") and not r and not t.get("assignee"):  # nothing has started it yet
            return row("stalled", label=f.get("stall") or "")
        return row("stalled", label="自动处理已关闭，等人继续" if not f.get("auto") else "没有可用的 AI，等你处理")
    if (s in ("new", "analyzing") and not r) or (f.get("next_step") and f["next_step"](t)):
        return row("queued", step=step)
    return row("idle", step=step, label={"analyze": "分析完了，等你确认下一步", "plan": "方案好了，等你决定怎么做"}.get(r.get("mode"), ""))


def compute(P, tickets: list) -> dict:
    """The stage of every ticket in `tickets` (rows with id, project_id, num, status, links, assignee), by ticket key."""
    if not tickets:
        return {}
    from . import handwork, intake, signoff
    from .store import RUN_MODES
    from .server import now  # read at call time, so a patched clock reaches link expiry
    from .workbench import _released
    st = P.store
    ids = [t["id"] for t in tickets]
    marks = ",".join("?" * len(ids))
    keys = {x["id"]: x["key"] for x in st.projects()}
    latest = {r["ticket_id"]: r for r in st.q(
        "SELECT r.id, r.ticket_id, r.agent, r.mode, r.status, r.decision, r.ended, length(r.diff) AS dl FROM runs r JOIN "
        "(SELECT ticket_id, MAX(id) id FROM runs WHERE ticket_id IN (%s) AND mode!='ask' GROUP BY ticket_id) x "
        "ON r.id=x.id" % marks, ids)}
    live = {r["ticket_id"]: r for r in st.q(
        "SELECT ticket_id, mode, status FROM runs WHERE ticket_id IN (%s) AND status IN ('queued','running') "
        "AND mode!='ask' ORDER BY id" % marks, ids)}
    checks = {}
    for e in st.q("SELECT ticket_id, data FROM events WHERE ticket_id IN (%s) "
                  "AND author='我来写' AND kind='flow' ORDER BY id" % marks, ids):
        data, run = e.get("data") or {}, latest.get(e["ticket_id"], {})
        # Reminders are also flow events. Keep the actual check for the current submission, never an older
        # submission's failure after a new one arrives, nor a reminder in place of the latest verdict.
        if run.get("agent") == "人工" and data.get("run") == run["id"] and data.get("verdict") in ("pass", "fail", "unknown"):
            checks[e["ticket_id"]] = data
    rel = _released(P, ids)
    waits = {}
    closed = [t["id"] for t in tickets if t["status"] == "closed"]
    if closed:  # the latest word on merging: a release clears an earlier wait, a later wait (re-accepted) stands
        for e in st.q("SELECT ticket_id, kind, body, data FROM events WHERE ticket_id IN (%s) AND kind IN ('release','flow') "
                      "ORDER BY id" % ",".join("?" * len(closed)), closed):
            if e["kind"] == "release":
                waits.pop(e["ticket_id"], None)
            elif (e.get("data") or {}).get("release") == "waiting":
                waits[e["ticket_id"]] = e["body"] or "合并发布等人处理"
    conf = P.flow.autoflow()
    modes = dict(RUN_MODES)
    agents = {}
    out = {}
    for t in tickets:
        pk = keys.get(t["project_id"], "?")
        k = t.get("key") or "%s-%d" % (pk, t["num"])
        lk = t.get("links") or {}
        r = latest.get(t["id"]) or {}
        if pk not in agents:
            try:
                agents[pk] = (P.flow.agent(conf, {"key": pk}), "自动处理关着，没人接手" if not conf.get("on") else "这台机器上没有可用的智能体")
            except ValueError as exc:
                agents[pk] = ("", str(exc))
        agent, stall = agents[pk]
        on = P.flow.switched_on(conf, {"key": pk})
        f = {"now": now(), "last": r, "live": live.get(t["id"]), "modes": modes, "version": rel.get(t["id"], ""),
             "auto": on, "agent": agent, "stall": stall if on else "自动处理关着，没人接手", "check": checks.get(t["id"]),
             "release_wait": waits.get(t["id"]),
             "next_step": lambda x, conf=conf: P.flow.next_step(x, conf)[0]}
        if t["status"] != "closed" and not f["live"]:
            f["handwork_busy"] = handwork.busy(k)
            if lk.get("open_ac"):
                f["recovery"] = intake.recovery_state(P, k)
            if r.get("mode") == "fix":
                f["wait"] = P.flow.verification_wait(r["id"])
            if t["status"] in ("verify", "doing") and signoff.epath(P.data_dir, k).exists():
                f["ev"] = signoff.state(P.data_dir, k)
        out[k] = decide(t, f)
    return out
