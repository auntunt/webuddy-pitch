"""The Platform facade: one object that owns the store, runner, knowledge and orchestra for a data directory."""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from .agents import Runner
from .metrics import compute as compute_metrics, ts_norm
from . import agent_routes
from .coderefs import FILE_LINE
from .errors import ApiError
from .knowledge import Knowledge
from .orchestra import Orchestra
from .store import PRIORITIES, RUN_MODES, STATUSES, Store, TYPES, now, timestamp_offset


def _routed_agent(P, project, requested=None, fallback=""):
    try:
        return agent_routes.resolve(P.data_dir, project, requested, fallback)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _section(text: str, names: tuple) -> str:
    """The text under the first heading that starts with one of names ("结论", ...), flattened to one line."""
    lines = (text or "").splitlines()
    head = re.compile(r"^\s*(#{1,4}\s+|\*\*|【)?\s*(\d+[.、)]\s*)?")
    for i, ln in enumerate(lines):
        m = head.sub("", ln)
        nm = next((n for n in names if m.startswith(n)), None)
        if not nm:
            continue
        out = [re.sub(r"^[\s*】:：]+", "", m[len(nm):])]
        for x in lines[i + 1:]:
            if re.match(r"^\s*#{1,4}\s", x) or re.match(r"^\s*\*\*[^*]{1,16}\*\*\s*[:：]?\s*$", x):
                break
            if any(out) and (not x.strip() or re.match(r"^\s*([-*•]|\d+[.、)])\s", x)):
                break  # the first paragraph is the answer; the list under it is evidence
            out.append(x.strip())
        t = re.sub(r"\s+", " ", re.sub(r"[*_`>#]", "", " ".join(o for o in out if o))).strip(" -•")
        if t:
            return t
    for para in re.split(r"\n\s*\n", text or ""):
        t = re.sub(r"\s+", " ", re.sub(r"[*_`>#]", "", para)).strip()
        if len(t) > 8:
            return t
    return ""


class Platform:
    def __init__(self, data_dir: Path, user: str = "", brand: str = "", *, tenant_context=None):
        self.tenant_context = tenant_context
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        from .operator_access import initialize
        self.operator_key_path = initialize(self.data_dir)
        self.store = Store(self.data_dir / "platform.db")
        from .external_requirements import initialize as initialize_external_requirements
        initialize_external_requirements(self.store)
        self.runner = Runner(self.store, self.data_dir)
        self.runner.tenant_context = tenant_context
        if tenant_context is not None:
            tenant_context.platform = self
        if tenant_context is None:
            self.runner.recover()
        from . import learning_runs
        if tenant_context is None:
            learning_runs.recover(self)
        # three layers: what a project is (knowledge), how a change gets made right (the coding line), and the
        # apps on top that decide where tasks come from (apps.py wires them to the line)
        self.kb = Knowledge(self.store, self.runner)
        self.flow = Orchestra(self.store, self.runner, self.data_dir, self.kb)
        self.flow.tenant_context = tenant_context
        self.flow.rechecks.runner.tenant_context = tenant_context
        if tenant_context is None:
            self.flow.rechecks.recover()
        from . import apps
        apps.wire(self)
        self.user = user
        self.surveys = {}  # project id -> Survey (full-project analysis)
        self.brand = brand or os.environ.get("TMH_BRAND", "") or "webuddy"
        self.pricing = self._load_pricing()
        self.runner.charge = self._charge
        from . import ai_accept, signoff
        self.store.on_status.append(lambda t, old, new, who: signoff.on_status(self, t, old, new, who))
        self.flow.committed.append(lambda p, tid, rid: ai_accept.after_commit(self, p, tid, rid))
        from . import preview
        if tenant_context is None:
            self.store.on_status.append(lambda t, old, new, who: preview.on_status(self, t, old, new, who))
        self.preview_port = 0  # set by serve(): previews have an address of their own
        self.public_url = os.environ.get("TMH_PUBLIC_URL", "").rstrip("/")  # else learnt from requests, for links sent to chats
        if tenant_context is None:
            preview.resume(self)
        from . import chat
        chat.wire(self)
        from . import workbench
        workbench.wire(self, background=tenant_context is None)  # clients, versions and the main line's standing preview
        from .survey import Survey
        if tenant_context is None:
            Survey.resume_all(self)  # a full-project analysis the last process was in the middle of

    # ------------------------------------------------------------ helpers
    def project(self, key) -> dict:
        p = self.store.project(key)
        if not p:
            raise ApiError(404, "没有这个项目：%s" % key)
        return p

    def ticket(self, key) -> dict:
        t = self.store.ticket(key)
        if not t:
            raise ApiError(404, "没有这个工单：%s" % key)
        return t

    def root(self, p: dict) -> Path:
        from .project_library import require_development
        try:
            require_development(self.store, p)
        except ValueError as exc:
            raise ApiError(409, str(exc)) from exc
        return Path(p["root"])

    # ------------------------------------------------------------ points
    # Usage is shown as points so the cost of generating is visible where it happens.
    # Fixed prices per action (demo-friendly, no token counting on stage); override in <data>/pricing.json:
    # {"initial": 20000, "prices": {"ask": 3, "analyze": 10, ...}}. Reading and evidence lookups are free.
    PRICES = {"ask": 3, "analyze": 10, "plan": 10, "fix": 30, "kb": 5, "chart": 10}
    INITIAL = 20000

    def _load_pricing(self) -> dict:
        conf = {"initial": self.INITIAL, "prices": dict(self.PRICES)}
        f = self.data_dir / "pricing.json"
        if f.exists():
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                conf["initial"] = int(j.get("initial", conf["initial"]))
                conf["prices"].update({k: int(v) for k, v in (j.get("prices") or {}).items()})
            except (ValueError, TypeError):
                pass
        return conf

    def balance(self, p: dict) -> int:
        b, n = self.store.points_balance(p["id"])
        if n == 0:
            self.store.add_points(p["id"], self.pricing["initial"], "初始额度（演示）", "system")
            b = self.pricing["initial"]
        return b

    def _charge(self, run: dict) -> None:
        n = self.pricing["prices"].get(run["mode"], 0)
        if run["mode"] == "kb":
            n *= max(1, len((run.get("target") or "").split()))  # priced per page, also when one run writes several
        if n:
            p = self.store.project(run["project_id"])
            self.balance(p)
            self.store.add_points(run["project_id"], -n, dict(RUN_MODES).get(run["mode"], run["mode"]), run["author"], run["id"], run["ticket_id"])

    # ------------------------------------------------------------ closed-loop board
    def loop(self, p: dict | None, allowed_projects=None) -> dict:
        """The closed-loop board for one project, or for every project when p is None."""
        st = self.store
        ps = [p] if p else st.projects()
        if allowed_projects is not None:
            ps = [x for x in ps if x["id"] in allowed_projects]
        ids = [x["id"] for x in ps] or [-1]
        tinn = "project_id IN (%s)" % ",".join("?" * len(ids))
        inn = "project_id IN (%s)" % ",".join("?" * len(ids))
        by = {}
        for r in st.q("SELECT status, COUNT(*) n FROM tickets WHERE %s GROUP BY status" % tinn, ids):
            by[r["status"]] = r["n"]
        total = sum(by.values())
        closed = by.get("closed", 0)
        # a ticket "fails" when the latest agent run on it failed and it is still open
        failed = [r["ticket_id"] for r in st.q(
            "SELECT r.ticket_id, r.status FROM runs r JOIN (SELECT ticket_id, MAX(id) m FROM runs WHERE %s AND ticket_id IS NOT NULL AND mode!='ask' GROUP BY ticket_id) x "
            "ON r.id=x.m JOIN tickets t ON t.id=r.ticket_id WHERE r.status='failed' AND t.status!='closed'" % inn, ids)]
        analyzed = st.one("SELECT COUNT(DISTINCT ticket_id) n FROM runs WHERE %s AND mode IN ('analyze','plan') AND status='done'" % inn, ids)["n"]
        fixes = st.q("SELECT decision FROM runs WHERE %s AND mode='fix' AND status='done' AND decision!=''" % inn, ids)
        accepted = sum(1 for r in fixes if r["decision"].startswith("accepted"))
        today = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600))
        t_new = st.one("SELECT COUNT(*) n FROM tickets WHERE %s AND date(created || ?, '+8 hours')=?" % tinn, ids + [timestamp_offset(), today])["n"]
        t_closed = st.one("SELECT COUNT(*) n FROM tickets WHERE %s AND status='closed' AND date(updated || ?, '+8 hours')=?" % tinn, ids + [timestamp_offset(), today])["n"]
        written = inscope = 0
        built = False
        for x in ps:
            kb = self.kb.kb_overview(x)
            built = built or bool(kb.get("built"))
            cov = (kb.get("coverage") or {}).get("total") or {}
            w = cov.get("待确认", 0) + cov.get("已确认", 0)
            written += w
            inscope += w + cov.get("未分析", 0) + cov.get("过期", 0)
        open_ = total - closed
        pct = lambda a, b: round(a * 100 / b) if b else 0  # noqa: E731
        facts = []
        if total:
            facts.append("当前 %d 单在流转" % open_)
            if failed:
                facts.append("%d 单最近一次智能体运行失败" % len(failed))
            if by.get("verify"):
                facts.append("%d 单等人工验收" % by["verify"])
            if by.get("confirm"):
                facts.append("%d 单分析已出结论待确认" % by["confirm"])
        else:
            facts.append("还没有工单")
        return {"total": total, "by_status": by, "failed": len(failed), "failed_ids": failed, "open": open_, "closed": closed,
                "waiting": sum(len(self.flow.waiting(x)) for x in ps) if open_ else 0,
                "metrics": [
                    {"key": "loop", "label": "闭环完成率", "pct": pct(closed, total), "sub": "共 %d 单 · 已闭环 %d" % (total, closed)},
                    {"key": "agent", "label": "智能体分析覆盖", "pct": pct(analyzed, total), "sub": "%d 单有分析结论" % analyzed},
                    {"key": "accept", "label": "代码改动采纳率", "pct": pct(accepted, len(fixes)), "sub": "已审 %d · 采纳 %d" % (len(fixes), accepted)},
                    {"key": "kb", "label": "知识库覆盖", "pct": pct(written, inscope), "sub": "已写 %d / %d 页" % (written, inscope) if built else "尚未构建"},
                ],
                "today": {"created": t_new, "closed": t_closed}, "insight": "，".join(facts) + "。",
                "points": sum(self.balance(x) for x in ps), "projects": len(ps), "kb_built": built}

    # ------------------------------------------------------------ inbox
    # What is waiting for a person right now, one line per ticket with the one thing to do, most urgent and longest
    # waiting first; and, apart, what waits on someone outside the team (a client's sign-off link that is out).
    PRI_RANK = {"urgent": 0, "high": 1, "normal": 2, "medium": 2, "low": 3}

    def inbox(self, p: dict | None, allowed_projects=None) -> dict:
        st = self.store
        ps = [p] if p else st.projects()
        if allowed_projects is not None:
            ps = [x for x in ps if x["id"] in allowed_projects]
        ids = [x["id"] for x in ps] or [-1]
        keys = {x["id"]: x["key"] for x in ps}
        q = ",".join("?" * len(ids))
        tickets = st.q("SELECT id, project_id, num, title, status, priority, assignee, updated, links FROM tickets WHERE project_id IN (%s) "
                       "AND (status!='closed' OR id IN (SELECT ticket_id FROM events WHERE kind='flow' AND data LIKE '%%\"release\": \"waiting\"%%')) "
                       % q, ids)
        running = st.one("SELECT COUNT(*) n FROM runs WHERE project_id IN (%s) AND status IN ('queued','running') AND mode!='ask'" % q, ids)["n"]
        conf = self.flow.autoflow()
        try:
            agent = self.flow.agent(conf)
        except ValueError:
            agent = ""
        from .stage import compute
        rows = []
        for t in tickets:
            try:
                links = json.loads(t["links"]) if isinstance(t["links"], str) else (t["links"] or {})
            except ValueError:
                links = {}
            rows.append(dict(t, links=links, key="%s-%d" % (keys.get(t["project_id"], "?"), t["num"])))
        stages = compute(self, rows)
        mine, others = [], []
        for t in rows:
            g = stages[t["key"]]
            if g["who"] not in ("person", "client"):
                continue
            item = {"key": t["key"], "title": t["title"], "priority": t["priority"], "assignee": t["assignee"] or "",
                    "reason": g["key"], "label": g["label"], "action": g["action"], "since": g.get("since") or t["updated"]}
            item.update({k: g[k] for k in ("note", "state") if k in g})
            (mine if g["who"] == "person" else others).append(item)
        order = lambda x: (self.PRI_RANK.get(x["priority"], 2), x["since"] or "")  # noqa: E731
        mine.sort(key=order)
        others.sort(key=order)
        return {"mine": mine, "others": others, "running": running, "open": sum(t["status"] != "closed" for t in tickets), "agent": agent, "auto": bool(conf.get("on"))}

    # ------------------------------------------------------------ leader view
    # What the ops team got done, across every project, in numbers a manager can read at a glance. Everything is
    # counted from the ticket timeline, agent runs and the knowledge base; nothing here is estimated.
    MACHINE = {"system", "知识库", "自动流转", "codex", "claude", "agent", ""}

    def lead(self, days: int = 30) -> dict:
        from .. import kb
        from .. import kbqa
        from .metrics import _hours, _stat
        st = self.store
        ps = st.projects()
        agents = {a["name"] for a in __import__("tmh.platform.agents", fromlist=["available"]).available(self.data_dir)} | self.MACHINE
        since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - days * 86400))
        tickets = st.tickets(limit=100000)
        tid = {t["id"]: t for t in tickets}
        evs = [e for e in st.q("SELECT ticket_id, ts, author, kind, body FROM events WHERE ts>=? ORDER BY id", (since,)) if e["ticket_id"] in tid]
        closed_at = {}
        for e in st.q("SELECT ticket_id, ts, kind, data FROM events WHERE kind IN ('status','accept') ORDER BY id"):
            d = json.loads(e["data"] or "{}") if isinstance(e["data"], str) else (e["data"] or {})
            if e["kind"] == "accept" or d.get("to") == "closed":
                closed_at[e["ticket_id"]] = e["ts"]
            elif d.get("from") == "closed":
                closed_at.pop(e["ticket_id"], None)
        closed = [(tid[k], v) for k, v in closed_at.items() if k in tid and v >= since and tid[k]["status"] == "closed"]
        cycles = [_hours(t["created"], ts) for t, ts in closed]
        created = [t for t in tickets if t["created"] >= since]
        open_ = [t for t in tickets if t["status"] != "closed"]
        aged = [t for t in open_ if (_hours(t["created"], now()) or 0) > 72]
        runs = st.q("SELECT id, project_id, ticket_id, mode, status, author, created, ended, decision FROM runs WHERE created>=?", (since,))
        touched = {e["ticket_id"] for e in evs}
        with_ai = {r["ticket_id"] for r in runs if r["ticket_id"] and r["mode"] != "ask" and r["status"] == "done"}

        # people: everything a person did on tickets in the period, machines and agents left out
        people = {}

        def pp(name):
            return people.setdefault(name, {"name": name, "tickets": set(), "closed": 0, "comments": 0, "actions": 0, "reviews": 0, "kb": 0})
        for e in evs:
            t = tid.get(e["ticket_id"])
            # the people who raise tickets are clients, not the team: their filing and follow-ups are not ops work
            if e["author"] in agents or e["kind"] in ("created", "import") or (t and e["author"] == t["reporter"] and e["kind"] == "comment"):
                continue
            x = pp(e["author"])
            x["tickets"].add(e["ticket_id"])
            x["actions"] += 1
            if e["kind"] == "comment":
                x["comments"] += 1
            if e["kind"] in ("accept", "adopt", "discard", "reject"):
                x["reviews"] += 1
        for t, ts in closed:
            who = t["assignee"] or ""
            if who and who not in agents:
                pp(who)["closed"] += 1
                pp(who)["tickets"].add(t["id"])

        # knowledge: pages written or confirmed in the period, per project and per person
        kb_rows, kb_total, kb_new = [], 0, 0
        for p in ps:
            try:
                reg = kb.load_registry(self.root(p))
            except Exception:  # noqa: BLE001
                reg = {}
            w = sum(1 for r in reg.values() if r.get("status") in (kb.STATUS_DRAFT, kb.STATUS_OK))
            ok = sum(1 for r in reg.values() if r.get("status") == kb.STATUS_OK)
            new = 0
            for r in reg.values():
                if (r.get("updated") or "") >= since[:16]:
                    new += 1
                    if r.get("by") and r["by"] not in agents:
                        pp(r["by"])["kb"] += 1
                if (r.get("confirmed_at") or "") >= since[:16] and r.get("confirmed_by") and r["confirmed_by"] not in agents:
                    pp(r["confirmed_by"])["kb"] += 1
            kb_total += w
            kb_new += new
            q = {}
            try:
                q = kbqa.metrics(self.root(p), days=days)
            except Exception:  # noqa: BLE001
                pass
            pt = [t for t in tickets if t["project_id"] == p["id"]]
            pc = [c for (t, ts), c in zip(closed, cycles) if t["project_id"] == p["id"]]
            kb_rows.append({"key": p["key"], "name": p["name"], "open": sum(1 for t in pt if t["status"] != "closed"),
                            "created": sum(1 for t in pt if t["created"] >= since), "closed": len(pc), "cycle": _stat([c for c in pc if c is not None]),
                            "ai": sum(1 for t in pt if t["id"] in with_ai), "kb_written": w, "kb_confirmed": ok, "kb_new": new,
                            "answers": q.get("auto", 0), "spent": -sum(x["delta"] for x in st.q(
                                "SELECT delta FROM points WHERE project_id=? AND delta<0 AND ts>=?", (p["id"], since)))})

        # weekly trend, oldest first
        weeks = []
        for i in range(min(12, max(1, days // 7)) - 1, -1, -1):
            a = time.strftime("%Y-%m-%d", time.localtime(time.time() - (i + 1) * 7 * 86400))
            b = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 7 * 86400))
            weeks.append({"from": a, "to": b, "created": sum(1 for t in tickets if a <= t["created"][:10] < b or (i == 0 and t["created"][:10] == b)),
                          "closed": sum(1 for t, ts in closed if a <= ts[:10] < b or (i == 0 and ts[:10] == b)),
                          "ai": sum(1 for r in runs if r["mode"] in ("analyze", "plan", "fix") and r["status"] == "done" and (a <= r["created"][:10] < b or (i == 0 and r["created"][:10] == b)))})
        by_type = Counter(t["type"] for t in created)
        modes = Counter(r["mode"] for r in runs if r["status"] == "done")
        fixes = [r for r in runs if r["mode"] == "fix" and r["status"] == "done" and r["decision"]]
        # the four numbers a manager reads first, each against the previous period
        allev = st.q("SELECT ticket_id, ts, author, kind FROM events ORDER BY id")
        first_resp, rejects = {}, {}
        for e in allev:
            t = tid.get(e["ticket_id"])
            if not t or e["author"] in agents or e["kind"] in ("created", "import") or e["author"] == t["reporter"]:
                continue
            first_resp.setdefault(e["ticket_id"], e["ts"])
            if e["kind"] == "reject":
                rejects.setdefault(e["ticket_id"], []).append(e["ts"])
        all_closed = [(tid[k], v) for k, v in closed_at.items() if k in tid and tid[k]["status"] == "closed"]

        def window(a, b):
            made = [t for t in tickets if a <= t["created"] < b]
            resp = [_hours(t["created"], first_resp[t["id"]]) for t in made if t["id"] in first_resp]
            shut = [(t, ts) for t, ts in all_closed if a <= ts < b]
            res = [_hours(t["created"], ts) for t, ts in shut]
            ftf = sum(1 for t, ts in shut if not rejects.get(t["id"]))
            back = sum(1 for t in tickets if t["created"] < b and (t["status"] != "closed" or closed_at.get(t["id"], "9") >= b)
                       and (_hours(t["created"], b.rstrip("~")) or 0) > 72)
            return {"resp": _stat(resp)["median_h"], "res": _stat(res)["median_h"],
                    "ftf": round(ftf * 100 / len(shut)) if shut else None, "backlog": back, "closed": len(shut)}
        nowts = now()
        prev_since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 2 * days * 86400))
        cur_w, prev_w = window(since, nowts + "~"), window(prev_since, since)

        core = [{"key": k, "label": l, "value": cur_w[k], "prev": prev_w[k], "unit": u, "lower_better": lb}
                for k, l, u, lb in (("resp", "响应时长", "h", True), ("res", "解决时长", "h", True), ("ftf", "一次解决率", "%", False), ("backlog", "积压", "张", True))]

        # what got done: one line per closed ticket, from the analysis the team acted on
        last_an = {}
        for r in st.q("SELECT ticket_id, mode, result FROM runs WHERE mode IN ('analyze','plan') AND status='done' ORDER BY id"):
            if r["mode"] == "analyze" or r["ticket_id"] not in last_an:
                last_an[r["ticket_id"]] = r["result"] or ""
        acc_by = {e["ticket_id"]: e["author"] for e in allev if e["kind"] == "accept"}
        done_list = [{"key": t["key"], "title": t["title"], "reporter": t["reporter"] or "", "cause": _section(last_an.get(t["id"], ""), ("结论", "原因分析", "原因"))[:90],
                      "by": t["assignee"] or acc_by.get(t["id"], ""), "closed": ts, "cycle_h": _hours(t["created"], ts), "rejected": len(rejects.get(t["id"], []))}
                     for t, ts in sorted(closed, key=lambda x: x[1], reverse=True)[:12]]

        # the agents' share, only as countable facts; a feature nobody has switched on says so instead of showing 0
        ever = {r["mode"] for r in st.q("SELECT DISTINCT mode FROM runs WHERE status='done'")}
        located = sum(1 for r in runs if r["mode"] == "analyze" and r["status"] == "done" and r["ticket_id"]
                      and self.FILE_LINE.search(st.one("SELECT result FROM runs WHERE id=?", (r["id"],))["result"] or ""))
        ai_facts = [{"label": "智能体先给出定位的工单", "value": located if "analyze" in ever else None, "unit": "张"},
                    {"label": "代码改动被采纳", "value": sum(1 for r in fixes if r["decision"].startswith("accepted")) if "fix" in ever else None, "unit": "次"},
                    {"label": "自动写成的知识页", "value": modes.get("kb", 0) if "kb" in ever else None, "unit": "页"},
                    {"label": "群里自动答复", "value": sum(r["answers"] for r in kb_rows) or None, "unit": "次"}]
        for x in people.values():
            x["rejected"] = sum(len(v) for k, v in rejects.items() if tid.get(k) and tid[k]["assignee"] == x["name"] and any(ts >= since for ts in v))
            cyc = [_hours(t["created"], ts) for t, ts in closed if t["assignee"] == x["name"]]
            x["avg_h"] = _stat(cyc)["avg_h"]
        people_out = sorted(({**x, "tickets": len(x["tickets"])} for x in people.values()), key=lambda x: (-x["closed"], -x["tickets"], -x["actions"]))
        recent = sorted(closed, key=lambda x: x[1], reverse=True)[:8]
        return {"days": days, "since": since[:10], "projects": len(ps),
                "kpi": {"handled": len(touched), "created": len(created), "closed": len(closed), "open": len(open_), "aged": len(aged),
                        "cycle": _stat([c for c in cycles if c is not None]),
                        "ai_rate": round(len(with_ai & touched) * 100 / len(touched)) if touched else None, "ai_tickets": len(with_ai),
                        "kb_total": kb_total, "kb_new": kb_new, "answers": sum(r["answers"] for r in kb_rows), "people": len(people_out)},
                "agent": {"analyze": modes.get("analyze", 0), "plan": modes.get("plan", 0), "fix": modes.get("fix", 0), "kb": modes.get("kb", 0),
                          "ask": modes.get("ask", 0), "fix_accepted": sum(1 for r in fixes if r["decision"].startswith("accepted")), "fix_reviewed": len(fixes),
                          "spent": sum(r["spent"] for r in kb_rows)},
                "weeks": weeks, "people": people_out, "by_project": kb_rows,
                "by_type": [{"type": k, "label": dict(TYPES).get(k, k), "n": v} for k, v in by_type.most_common()],
                "recent": [{"key": t["key"], "title": t["title"], "assignee": t["assignee"], "closed": ts, "cycle_h": _hours(t["created"], ts)} for t, ts in recent],
                "core": core, "done": done_list, "ai": ai_facts,
                "aged": [{"key": t["key"], "title": t["title"], "status": t["status"], "assignee": t["assignee"], "age_h": _hours(t["created"], now())}
                         for t in sorted(aged, key=lambda t: t["created"])[:8]]}

    # ------------------------------------------------------------ assistant
    CITE = re.compile(r"\b((?:flow|tbl|dom|mod):[A-Za-z0-9_.\-]*[A-Za-z0-9_]|index)\b")
    FILE_LINE = FILE_LINE

    def cite(self, p: dict, text: str, limit: int = 8) -> list:
        """Evidence cards for the ids and file:line references an answer names; unknown ones are dropped."""
        from .. import kb
        from ..graph import Graph, graph_path
        root = self.root(p)
        out, seen = [], set()
        reg = kb.load_registry(root) if graph_path(root).exists() else {}
        g = Graph(root) if reg else None
        for m in self.CITE.finditer(text or ""):
            pid = m.group(1)
            if pid in seen or (pid == "index" and "index" not in reg):
                continue
            seen.add(pid)
            n = g.node(pid) if g else None
            r = reg.get(pid)
            if not n and not r:
                continue
            kind = pid.split(":")[0]
            title = (r or {}).get("title") or (n["name"] if n else pid)
            card = {"kind": kind, "id": pid, "title": title, "status": "过期" if (r or {}).get("stale") else (r or {}).get("status", ""),
                    "summary": (r or {}).get("summary", "")}
            if n and kind == "flow":
                card["sub"] = "%s → %s" % (n["data"].get("trigger", ""), n["data"].get("handler", ""))
                card["file"], card["line"] = n["file"], n["line"]
            out.append(card)
        for f, ln in self.FILE_LINE.findall(text or ""):
            k = "%s:%s" % (f, ln)
            if k in seen:
                continue
            seen.add(k)
            fp = root / f
            if fp.is_file():
                out.append({"kind": "code", "id": k, "title": k, "file": f, "line": int(ln)})
        return out[:limit]

    def evidence(self, p: dict, t: dict | None, q: str) -> dict:
        """Answer from the knowledge base alone, without a model: the closest flows, tables, pages and code."""
        text = q + (" " + t["title"] + " " + (t.get("body") or "")[:300] if t else "")
        r = self.kb.related(p, text, limit=5)
        cards = []
        for f in r["flows"][:4]:
            cards.append({"kind": "flow", "id": f["id"], "title": f["name"], "sub": "%s → %s" % (f["trigger"], f["handler"]),
                          "file": f["file"], "line": f["line"], "status": f.get("page", ""),
                          "summary": "读写表：" + "、".join("%s(%s)" % (a, b) for a, b in f["tables"][:4]) if f["tables"] else ""})
        for pg in r["pages"][:3]:
            if pg["id"] not in {c["id"] for c in cards}:
                cards.append({"kind": pg["id"].split(":")[0] if ":" in pg["id"] else "page", "id": pg["id"], "title": pg["title"],
                              "status": pg["status"], "summary": pg["summary"]})
        for tb in r["tables"][:3]:
            cards.append({"kind": "tbl", "id": tb["id"], "title": tb["name"], "summary": "%d 条业务流使用" % tb["users"]})
        for c in r["code"][:2]:
            cards.append({"kind": "code", "id": "%s:%s" % (c["file"], c["line"]), "title": c["label"], "file": c["file"], "line": c["line"]})
        if not cards:
            return {"body": "未检索到依据。知识库里没有和这个问题对得上的业务流、表、知识页或代码。可以换个说法，或切到“分析与起草”让智能体去代码里找。",
                    "cards": [], "no_evidence": True}
        f0 = r["flows"][0] if r["flows"] else None
        if f0:
            head = "最相关的是业务流「%s」（%s → %s）" % (f0["name"], f0["trigger"], f0["handler"])
            if f0["tables"]:
                head += "，读写 " + "、".join(a for a, _ in f0["tables"][:3])
        else:
            head = "知识库里找到 %d 条相关依据" % len(cards)
        return {"body": "**结论与边界**\n" + head + "。这是按知识库检索到的位置，不是对原因的判断。",
                "cards": cards, "next": "要结论和原因，切到“分析与起草”让本机智能体读代码；问题确认后可以“起草工单”。"}

    def ticket_evidence(self, p: dict, t: dict, runs: list) -> dict:
        """The fixed fields of a ticket's detail: what the agents concluded and how well it is backed."""
        from .. import kb
        last = {}
        for r in runs:  # newest first
            if r["mode"] in ("analyze", "plan", "fix") and r["mode"] not in last:
                last[r["mode"]] = r
        a = last.get("analyze") or last.get("plan")
        res = (a or {}).get("result") or ""
        flows = list(dict.fromkeys(((t.get("links") or {}).get("flows") or []) + re.findall(r"flow:[A-Za-z0-9_.\-]*[A-Za-z0-9_]", res)))
        reg = kb.load_registry(self.root(p))
        known = [f for f in flows if f in reg]
        written = [f for f in known if reg[f].get("status") not in (None, kb.STATUS_NEW) and not reg[f].get("stale")]
        fx = last.get("fix")
        return {"analysis": a and {"run": a["id"], "mode": a["mode"], "status": a["status"], "agent": a["agent"], "ended": a["ended"]},
                "fix": fx and {"run": fx["id"], "status": fx["status"], "decision": fx["decision"], "has_diff": None},
                "refs": len(self.FILE_LINE.findall(res)), "verified": res.count("【核实】"), "guesses": res.count("【推断】"),
                "flows": len(known), "flows_written": len(written)}

    def session_view(self, sid: int) -> list:
        """A session's messages; answers whose run has finished are filled in (with evidence cards) on the way out."""
        msgs = self.store.session_chats(sid)
        for m in msgs:
            d = m["data"] or {}
            if m["role"] == "assistant" and d.get("run") and d.get("state") == "running":
                r = self.store.run(d["run"])
                if r and r["status"] not in ("queued", "running"):
                    p = self.store.project(r["project_id"])
                    d["state"] = r["status"]
                    body = (r["result"] or "").strip() or ("智能体没有给出回答" if r["status"] == "done" else "运行%s：%s" % ({"failed": "失败", "cancelled": "被停止"}.get(r["status"], r["status"]), (r["result"] or "")[:300]))
                    if r["status"] == "done":
                        d["cards"] = self.cite(p, body)
                        d["no_evidence"] = not d["cards"] or "未检索到依据" in body[:40]
                    d["points"] = self.store.run_points([r["id"]]).get(r["id"], 0)
                    self.store.chat_update(m["id"], body, d)
                    m["body"], m["data"] = body, d
        return msgs

    def session_info(self, s: dict) -> dict:
        """A session row plus what it belongs to, in words the UI can show."""
        s = dict(s)
        if s.get("ticket_id"):
            t = self.store.ticket(s["ticket_id"])
            s["ticket"] = t and {"key": t["key"], "title": t["title"], "status": t["status"]}
        if s.get("matter_id"):
            m = self.store.matter(s["matter_id"])
            s["matter"] = m and {"id": m["id"], "title": m["title"], "ticket_id": m["ticket_id"]}
        return s

    def ticket_session(self, p: dict, t: dict, user: str) -> dict:
        """The person's working session for a ticket, created on first use."""
        for s in self.store.sessions(p["id"], user):
            if s["ticket_id"] == t["id"] and not s["archived_at"]:
                return s
        return self.store.session_create(p["id"], "ticket", "%s 处理讨论" % t["key"], user, ticket_id=t["id"])

    def session_of(self, sid, user: str) -> dict:
        s = self.store.session(int(sid)) if str(sid or "").isdigit() else None
        if not s or (s["created_by"] and s["created_by"] != user):
            raise ApiError(404, "没有这个会话")
        return s

    def ask(self, s: dict, q: str, mode: str, agent: str, user: str, model=None) -> None:
        """One question in one session. History comes from this session only, never from another one."""
        p = self.store.project(s["project_id"])
        t = self.store.ticket(s["ticket_id"]) if s["ticket_id"] else None
        from . import assist
        hist = [m for m in self.store.session_chats(s["id"], limit=8) if m["body"] and (m["data"] or {}).get("kind") != "cmd"]
        self.store.chat_add(p["id"], s["ticket_id"], "user", user, q, session_id=s["id"])
        kind = assist.intent(q, t, hist)
        # the platform's own records answer questions about the platform even in deep mode: an agent cannot see them
        ans = None
        if mode != "evidence" and kind == "kb" and not assist.needs_code(q):
            ans = assist.llm_answer(self, p, t, q, hist)  # business rules and usage: knowledge base + plain LLM, no agent
        if ans or mode == "evidence" or kind in ("help", "retry", "state"):
            ans = ans or assist.answer(self, p, t, q, hist, kind)
            self.store.chat_add(p["id"], s["ticket_id"], "assistant", ans.get("source", "知识库"), ans["body"],
                                {"mode": "evidence", "cards": ans.get("cards") or [], "no_evidence": ans.get("no_evidence", False), "points": 0,
                                 "next": ans.get("next", ""), "intent": kind, "source": ans.get("source", ""),
                                 "actions": ans.get("actions") or [], "follow": ans.get("follow") or [], "topic": ans.get("topic") or {},
                                 "deep": bool(ans.get("deep")), "weak": bool(ans.get("weak"))}, session_id=s["id"])
            return
        try:
            r = self.runner.start(p, t, _routed_agent(self, p, agent, "codex"), "ask", user, question=q, history=hist, session_id=s["id"], model=model)
        except ValueError as e:
            raise ApiError(400, str(e))
        self.store.chat_add(p["id"], s["ticket_id"], "assistant", r["agent"], "", {"mode": "draft", "run": r["id"], "state": "running", "agent": r["agent"], "model": r.get("model", "")},
                            session_id=s["id"])

    def ticket_draft(self, s: dict) -> dict:
        """A ticket draft from one session, without a model: what the person said, what the assistant found, what is still open.

        Nothing unknown is invented: the root cause stays 待确认, owner and acceptance criteria stay empty."""
        msgs = [m for m in self.session_view(s["id"]) if (m["data"] or {}).get("kind") != "cmd"]
        asks = [m["body"].strip() for m in msgs if m["role"] == "user" and m["body"].strip()]
        answers = [m for m in msgs if m["role"] == "assistant" and m["body"].strip() and (m["data"] or {}).get("state") != "running"]
        cards, seen = [], set()
        for m in answers[::-1]:
            for c in (m["data"] or {}).get("cards") or []:
                if c["id"] not in seen:
                    seen.add(c["id"])
                    cards.append(c)
        first = asks[0] if asks else s["title"]
        title = re.split(r"[。！？!?\n]", first)[0][:40] or s["title"]
        said = ["- " + a.replace("\n", " ")[:300] for a in asks[:4]] or ["- （待补充：单据类型、发生时间、复现步骤）"]
        lines = ["## 现象与复现"] + said + ["", "## 排查情况（助手整理，未经人工确认）"]
        if answers:
            lines.append(re.sub(r"\n{2,}", "\n", answers[-1]["body"].strip())[:800])
        else:
            lines.append("（会话里还没有助手的排查结论）")
        if cards:
            lines += ["", "## 相关依据"]
            for c in cards[:6]:
                loc = " %s:%s" % (c["file"], c["line"]) if c.get("file") and c["kind"] != "code" else ""
                lines.append("- %s「%s」%s" % ({"flow": "业务流", "tbl": "表", "code": "代码", "dom": "业务域"}.get(c["kind"], "知识页"), c["title"], loc))
        lines += ["", "## 根因", "待确认", "", "来源：助手会话「%s」" % s["title"]]
        t = self.store.ticket(s["ticket_id"]) if s["ticket_id"] else None
        return {"title": title, "body": "\n".join(lines), "type": "bug", "priority": "normal", "assignee": "", "accept": "",
                "flows": [c["id"] for c in cards if c["kind"] == "flow"][:6],
                "existing": t and {"key": t["key"], "title": t["title"]}}

    # ------------------------------------------------------------ integrations
    def integrations(self, p: dict) -> list:
        from .. import integrations as im
        out = []
        for name, conf in im.tools(self.root(p)).items():
            try:
                inst = im.make(self.root(p), name, conf)
                caps = list(inst.CAPABILITIES)
                t = inst.TITLE or inst.TYPE
            except Exception as e:  # noqa: BLE001 - a broken config should still be listed
                caps, t = [], "配置有误：%s" % e
            out.append({"name": name, "type": conf.get("type", name), "title": t, "capabilities": caps, "url": conf.get("url", "")})
        return out

    def import_issues(self, p: dict, via: str, keys: list, query: str, author: str) -> list:
        from .. import integrations as im
        root = self.root(p)
        inst = im.pick(root, "issues", via, dry_run=False)
        issues = [inst.get_issue(k) for k in keys] if keys else inst.search_issues(query, limit=50)
        existing = self._imported(p)
        return [self._import_one(p, inst, i, author, existing)["key"] for i in issues]

    def _imported(self, p: dict) -> dict:
        return {(t.get("external") or {}).get("key"): t for t in self.store.tickets(project_id=p["id"], limit=20000)
                if (t.get("external") or {}).get("key")}

    def _import_one(self, p: dict, inst, i, author: str, existing: dict, pr: str = "") -> dict:
        ext = {"system": inst.name, "type": inst.TYPE, "key": i.key, "url": i.url, "status": i.status}
        # original dates: imported history that was already closed in the tool is the baseline for 提效报告
        ext.update({k: v for k, v in (("created", ts_norm(i.created)), ("updated", ts_norm(i.updated)),
                                      ("resolved", ts_norm(i.resolved)), ("assignee", i.assignee)) if v})
        prs = list(dict.fromkeys(((existing.get(i.key) or {}).get("external") or {}).get("prs", []) + ([pr] if pr else [])))
        if prs:
            ext["prs"] = prs
        if i.key in existing:
            t = self.store.update_ticket(existing[i.key]["id"], author, external=ext)
        else:
            t = self.store.create_ticket(p["id"], i.title or i.key, author, body=i.description, type=_map_type(i.type),
                                         priority=_map_pri(i.priority), assignee=i.assignee, labels=i.labels, external=ext)
            for c in (i.comments or [])[-5:]:
                self.store.event(t["id"], c.get("author", ""), "comment", c.get("body", ""), {"external": True})
            self.store.event(t["id"], author, "import", "从 %s 导入 %s" % (inst.name, i.key), ext)
            if not ext.get("resolved"):  # closed history is a baseline, not new work
                self.flow.submit(p, t)
        existing[i.key] = t
        return t

    def import_refs(self, p: dict, via: str, since: str, until: str, limit: int, author: str) -> dict:
        """The closed tickets the commit history names (and, on GitHub, those closed by the merged pull requests it
        names), imported so history replay has their original text. Open ones are left alone; ids that led nowhere
        are remembered so the next run (after a rate limit, say) carries on where this one stopped."""
        from .. import integrations as im
        from . import learn
        root = self.root(p)
        inst = im.pick(root, "issues", via, dry_run=False)
        kind = {"github": "#", "gitlab": "#", "zentao": "zt", "jira": "jira"}.get(inst.TYPE)
        existing = self._imported(p)
        done = {str(k).lower() for k in existing} | {x.lower() for t in existing.values() for x in (t.get("external") or {}).get("prs", [])}
        seen = learn.seen_refs(self.data_dir, p["key"])
        zt = lambda r: r.split("-")[0] in ("bug", "story", "task")  # noqa: E731
        fits = {"#": lambda r: r[0] == "#", "zt": lambda r: r[0] != "#" and zt(r), "jira": lambda r: r[0] != "#" and not zt(r)}
        todo = [r for r in learn.ref_log(root, since, until) if r not in done and r not in seen and fits.get(kind, bool)(r)]
        out = {"refs": len(todo), "checked": 0, "imported": [], "open": 0, "failed": 0, "stopped": ""}
        try:
            for r in todo[:limit]:
                key = r.upper() if kind == "jira" else r
                try:
                    pairs = inst.issues_for_ref(key)
                except im.IntegrationError as e:
                    if "rate limit" in str(e).lower() or "HTTP 429" in str(e):
                        out["stopped"] = "%s 的调用次数到上限了，过一会再点，会接着往下导" % inst.name
                        break
                    out["failed"] += 1
                    seen.add(r)
                    continue
                out["checked"] += 1
                kept = False
                for i, pr in pairs:
                    if not i.resolved:
                        out["open"] += 1
                        continue
                    t = self._import_one(p, inst, i, author, existing, pr)
                    out["imported"].append(t["key"])
                    kept = True
                if not kept:
                    seen.add(r)
        finally:
            learn.save_seen(self.data_dir, p["key"], seen)
        out["imported"] = list(dict.fromkeys(out["imported"]))
        out["left"] = max(0, len(todo) - out["checked"] - out["failed"])
        return out

    # ------------------------------------------------------------ efficiency
    def metrics(self, p: dict, month: str = "") -> dict:
        from .. import usage
        if month and not re.match(r"^\d{4}-\d\d$", month):
            raise ApiError(400, "月份写成 2026-10")
        from .. import kbqa
        from . import books
        m = compute_metrics(self.store, p, usage.read(self.root(p)), month, self.kb.kb_overview(p),
                            sealed=books.load_baseline(self.data_dir, p["key"]), books=books.settings(self.data_dir, self.pricing),
                            packages=books.packages(self.data_dir))
        m["qa"] = kbqa.metrics(self.root(p), month=month)
        from . import upstream
        m["upstream"] = upstream.metrics(self, p, month)
        from . import review_feedback
        m["review_feedback"] = review_feedback.summary(self, p["id"])
        return m

    # ------------------------------------------------------------ ticket prompts
    # One prompt per scenario, assembled from the ticket, what the knowledge base links to it and where the code is,
    # so a developer can paste it into any agent (or have it written into Cursor rules / CLAUDE.md).
    SCENES = [
        ("bugfix", "修复缺陷", "先复现并定位，再做最小修改。",
         ["写出复现路径（入口页面或接口、操作步骤、触发数据）。",
          "定位到 文件:行号 和所在业务流，说清根因；每条结论标【核实】（读过代码）或【推断】。",
          "给出最小改动方案，等我确认后再改。",
          "列出影响面：读写同一张表、走同一业务流的其他入口。",
          "给出回归要点：至少覆盖原问题和受影响入口。"],
         ["不改与本单无关的代码，不顺手重构。", "不靠修改测试或断言让结果变绿。"]),
        ("field", "新增字段", "沿着整条链路把字段加全，不漏层。",
         ["列出这条链路的每一层和对应文件：表结构 → 实体/Mapper → 服务 → 接口 → 页面表单和列表 → 导入导出和报表。",
          "给出建表变更脚本和回滚脚本，说明历史数据的默认值。",
          "检查同一张表的其他读写方，确认不会因为新字段出错。",
          "按层给出改动，最后列出需要手工验证的页面。"],
         ["字段名、类型和长度沿用项目现有风格。", "数据库脚本要能在项目实际使用的数据库上执行。"]),
        ("xinchuang", "信创适配", "先扫描出不兼容点，再分批改。",
         ["扫描与本单相关的 SQL 和配置：分页写法、NVL/IFNULL/DECODE 等函数、日期函数、自增和序列、大小写敏感、保留字。",
          "检查中间件和运行环境相关的写法（应用服务器、JDK 版本、字体、文件路径）。",
          "每个不兼容点给出 文件:行号、原写法、目标数据库上的写法。",
          "按影响面分批，先改公共方法，再改单点。"],
         ["同一段 SQL 需要兼容原数据库时，用项目已有的方言机制，不另起一套。"]),
        ("test", "补测试", "先把现在的行为固定下来，再动代码。",
         ["针对本单涉及的业务流写表征测试：按当前代码的实际行为断言，包括状态流转和表读写。",
          "列出测试用例清单（正常、边界、异常），说明每条对应哪段代码。",
          "测试能在本地一条命令跑通。"],
         ["这一步不改业务代码。", "测不了的地方（依赖外部系统）说明原因和替代办法。"]),
        ("explain", "解释业务", "用业务语言讲清楚这块是怎么运转的。",
         ["从入口讲起：谁在什么页面做什么操作，触发哪个接口。",
          "讲清中间的业务规则、状态变化和读写的表。",
          "指出和本单描述对应的位置，以及容易误解的地方。"],
         ["面向甲方或新人，少用代码术语；需要引用代码时给 文件:行号。"]),
    ]

    def ticket_prompt(self, t: dict, scene: str) -> dict:
        sc = next((x for x in self.SCENES if x[0] == scene), self.SCENES[0])
        p = self.store.project(t["project_id"])
        text = "%s %s" % (t["title"], (t.get("body") or "")[:600])
        rel = self.kb.related(p, text, limit=6)
        runs = self.store.runs(ticket_id=t["id"], limit=50)
        last = next((self.store.run(r["id"]) for r in runs if r["mode"] in ("analyze", "plan") and r["status"] == "done"), None)
        res = (last or {}).get("result") or ""
        linked = ((t.get("links") or {}).get("flows") or [])
        flows = {f["id"]: f for f in rel["flows"]}
        if linked:
            from ..graph import Graph, graph_path
            if graph_path(self.root(p)).exists():
                g = Graph(self.root(p))
                for fid in linked:
                    n = g.node(fid)
                    if n and fid not in flows:
                        dd = n["data"]
                        flows[fid] = {"id": fid, "name": n["name"], "trigger": dd.get("trigger", ""), "handler": dd.get("handler", ""),
                                      "file": n["file"], "line": n["line"], "tables": list((dd.get("crud") or {}).items())[:8]}
        order = [f for f in linked if f in flows] + [f for f in flows if f not in linked]
        comments = [e for e in self.store.events(t["id"]) if e["kind"] == "comment"][-3:]
        tl = dict(TYPES)
        L = ["你在维护项目「%s」（%s）。任务：%s" % (p["name"], p["key"], sc[1] + "，" + sc[2]), "",
             "如果你接了 tmh 的 MCP 工具，先调用 context，参数里带上工单号 %s；没有接就按下面给的位置读代码。" % t["key"], "",
             "## 工单 %s：%s" % (t["key"], t["title"]),
             "类型：%s · 优先级：%s · 状态：%s" % (tl.get(t["type"], t["type"]), dict(PRIORITIES).get(t["priority"], t["priority"]),
                                             dict(STATUSES).get(t["status"], t["status"])), ""]
        body = (t.get("body") or "").strip()
        L += [body[:2000] + ("……（已截断）" if len(body) > 2000 else ""), ""] if body else ["（工单没有描述）", ""]
        if comments:
            L += ["最近评论："] + ["- %s：%s" % (c["author"] or "某人", c["body"].replace("\n", " ")[:200]) for c in comments] + [""]
        if res:
            L += ["## 已有的分析结论（%s，运行 #%d）" % (dict(RUN_MODES).get(last["mode"]), last["id"]), res.strip()[:1500], ""]
        sources = []
        if order:
            L.append("## 相关业务流" + ("（前 %d 条已人工关联）" % len([f for f in linked if f in flows]) if linked else ""))
            for fid in order[:6]:
                f = flows[fid]
                tb = "；读写 " + "、".join("%s(%s)" % (a, b) for a, b in f["tables"][:5]) if f["tables"] else ""
                L.append("- %s `%s`：%s → %s，%s:%s%s" % (f["name"], fid, f["trigger"], f["handler"], f["file"], f["line"], tb))
                sources.append({"kind": "flow", "id": fid, "title": f["name"]})
            L.append("")
        if rel["tables"]:
            L += ["## 相关表"] + ["- %s（%s，%d 条业务流使用）" % (x["name"], x["entity"] or "无实体", x["users"]) for x in rel["tables"][:5]] + [""]
            sources += [{"kind": "tbl", "id": x["id"], "title": x["name"]} for x in rel["tables"][:5]]
        code = [(c["file"], c["line"], c["label"]) for c in rel["code"][:5]]
        code += [(f, int(ln), "分析结论提到") for f, ln in self.FILE_LINE.findall(res)[:5]]
        if code:
            seen = set()
            L.append("## 代码位置")
            for f, ln, lb in code:
                if (f, ln) not in seen:
                    seen.add((f, ln))
                    L.append("- %s:%s（%s）" % (f, ln, lb))
                    sources.append({"kind": "code", "id": "%s:%s" % (f, ln), "title": lb})
            L.append("")
        if rel["pages"]:
            L += ["## 知识页（项目 .tmh/knowledge 下，可直接读）"]
            for x in rel["pages"][:5]:
                L.append("- %s `%s`（%s）%s" % (x["title"], x["id"], x["status"], "：" + x["summary"][:120] if x["summary"] else ""))
                sources.append({"kind": "page", "id": x["id"], "title": x["title"]})
            L.append("")
        if not (order or rel["tables"] or code or rel["pages"]):
            L += ["## 项目知识", "知识库里没有检索到和本单对得上的业务流、表或代码，请先按工单描述在代码里搜索定位。", ""]
        L += ["## 要做的事"] + ["%d. %s" % (i + 1, x) for i, x in enumerate(sc[3])] + ["", "## 约束"] + ["- " + x for x in sc[4]]
        L += ["- 结论里引用代码一律写 文件:行号。", "- 回复和提交说明里写上工单号 %s，方便追溯。" % t["key"]]
        prompt = "\n".join(L)
        return {"scene": sc[0], "label": sc[1], "text": prompt, "chars": len(prompt), "sources": sources,
                "scenes": [{"key": x[0], "label": x[1], "hint": x[2]} for x in self.SCENES], "written": self.prompt_written(p)}

    CLAUDE_START, CLAUDE_END = "<!-- tmh:ticket:start -->", "<!-- tmh:ticket:end -->"

    def prompt_written(self, p: dict) -> dict:
        from .. import usage
        root = self.root(p)
        return {"ticket": usage.current_ticket(root), "cursor": (root / ".cursor" / "rules" / "tmh-ticket.mdc").exists(),
                "claude": self.CLAUDE_START in self._read(root / "CLAUDE.md")}

    @staticmethod
    def _read(f: Path) -> str:
        try:
            return f.read_text(encoding="utf-8")
        except OSError:
            return ""

    def use_prompt(self, t: dict, scene: str, action: str, author: str) -> dict:
        """copy: only recorded. cursor / claude: also written into the project as a temporary section. clear: removed again."""
        from ..config import tmh_dir
        p = self.store.project(t["project_id"])
        root = self.root(p)
        mdc, cmd, cur = root / ".cursor" / "rules" / "tmh-ticket.mdc", root / "CLAUDE.md", tmh_dir(root) / "current-ticket"
        old = self._read(cmd)
        i, j = old.find(self.CLAUDE_START), old.find(self.CLAUDE_END)
        rest = (old[:i].rstrip("\n") + ("\n" if old[:i].strip() else "") + old[j + len(self.CLAUDE_END):].lstrip("\n")) if i >= 0 and j > i else old
        if action == "clear":
            if mdc.exists():
                mdc.unlink()
            if i >= 0:
                cmd.write_text(rest, encoding="utf-8")
            if cur.exists():
                cur.unlink()
            self.store.event(t["id"], author, "prompt-clear", "清除了项目里的工单提示词")
            return {"ok": True, "written": self.prompt_written(p)}
        if action not in ("copy", "cursor", "claude"):
            raise ApiError(400, "action 只能是 copy、cursor、claude 或 clear")
        pr = self.ticket_prompt(t, scene)
        files = []
        if action == "cursor":
            mdc.parent.mkdir(parents=True, exist_ok=True)
            mdc.write_text("---\ndescription: 当前工单 %s 的上下文（tmh 平台生成，换单时覆盖）\nalwaysApply: true\n---\n\n%s\n" % (t["key"], pr["text"]), encoding="utf-8")
            files.append(".cursor/rules/tmh-ticket.mdc")
        if action == "claude":
            block = "%s\n## 当前工单 %s（tmh 平台写入的临时段落，换单时覆盖，用完可在平台上清除）\n\n%s\n%s\n" % (
                self.CLAUDE_START, t["key"], pr["text"], self.CLAUDE_END)
            cmd.write_text((rest.rstrip("\n") + "\n\n" if rest.strip() else "") + block, encoding="utf-8")
            files.append("CLAUDE.md")
        if action != "copy":
            if tmh_dir(root).is_dir():
                cur.write_text(t["key"], encoding="utf-8")
        what = {"copy": "复制了", "cursor": "写入 Cursor 规则：", "claude": "写入 CLAUDE.md："}[action]
        self.store.event(t["id"], author, "prompt", "%s「%s」提示词" % (what, pr["label"]), {"scene": pr["scene"], "action": action, "chars": pr["chars"], "files": files})
        return {"ok": True, "files": files, "written": self.prompt_written(p)}

    def push_comment(self, t: dict, body: str, confirm: bool, author: str) -> dict:
        from .. import integrations as im
        ext = t.get("external") or {}
        if not ext.get("key"):
            raise ApiError(400, "这个工单没有关联外部工单")
        p = self.store.project(t["project_id"])
        inst = im.make(self.root(p), ext["system"], dry_run=not confirm)
        res = inst.add_comment(ext["key"], body)
        if confirm:
            self.store.event(t["id"], author, "sync", "同步评论到 %s %s" % (ext["system"], ext["key"]), {"body": body[:400]})
        return {"dry_run": not confirm, "result": res}


def _map_type(s: str) -> str:
    s = (s or "").lower()
    if any(w in s for w in ("bug", "缺陷", "故障", "defect", "incident")):
        return "bug"
    if any(w in s for w in ("story", "需求", "feature", "task", "任务")):
        return "feature"
    return "change" if "变更" in s or "change" in s else "bug"


def _map_pri(s: str) -> str:
    s = (s or "").lower()
    if any(w in s for w in ("highest", "blocker", "urgent", "紧急", "1")):
        return "urgent"
    if any(w in s for w in ("high", "critical", "高", "2")):
        return "high"
    if any(w in s for w in ("low", "低", "4")):
        return "low"
    return "normal"
