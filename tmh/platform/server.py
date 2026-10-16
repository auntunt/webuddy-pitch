"""`tmh serve`: the platform's HTTP server (stdlib only) and JSON API.

Bound to 127.0.0.1 by default. Writes need the `X-TMH: 1` header (a browser
cannot send it cross-site without a preflight we never answer), and when
TMH_TOKEN is set every API call needs it too, as `X-TMH-Token` or `?token=`.
Serving to a team on the LAN: `tmh serve --host 0.0.0.0` with TMH_TOKEN set.
"""
from __future__ import annotations

import errno
import hmac
import json
import mimetypes
import os
import re
import threading
import time
import traceback
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from .agents import Runner, available, git, is_git, pick_model
from .metrics import compute as compute_metrics, md_html, report_md, ts_norm
from . import command
from .errors import ApiError
from .knowledge import Knowledge
from .orchestra import Orchestra
from .store import PRIORITIES, REFORM_LIKE, RUN_MODES, STATUSES, TYPES, Store, now




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
    def __init__(self, data_dir: Path, user: str = "", brand: str = ""):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data_dir / "platform.db")
        self.runner = Runner(self.store, self.data_dir)
        self.runner.recover()
        # three layers: what a project is (knowledge), how a change gets made right (the coding line), and the
        # apps on top that decide where tasks come from (apps.py wires them to the line)
        self.kb = Knowledge(self.store, self.runner)
        self.flow = Orchestra(self.store, self.runner, self.data_dir, self.kb)
        from . import apps
        apps.wire(self)
        self.user = user
        self.surveys = {}  # project id -> Survey (full-project analysis)
        self.brand = brand or os.environ.get("TMH_BRAND", "") or "webuddy"
        self.pricing = self._load_pricing()
        self.runner.charge = self._charge
        from . import signoff
        self.store.on_status.append(lambda t, old, new, who: signoff.on_status(self, t, old, new, who))
        from .survey import Survey
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
        return Path(p["root"])

    # ------------------------------------------------------------ points
    # Usage is shown as points so the cost of generating is visible where it happens.
    # Fixed prices per action (demo-friendly, no token counting on stage); override in <data>/pricing.json:
    # {"initial": 20000, "prices": {"ask": 3, "analyze": 10, ...}}. Reading and evidence lookups are free.
    PRICES = {"ask": 3, "analyze": 10, "plan": 10, "fix": 30, "kb": 5}
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
    def loop(self, p: dict | None) -> dict:
        """The closed-loop board for one project, or for every project when p is None."""
        st = self.store
        ps = [p] if p else st.projects()
        ids = [x["id"] for x in ps] or [-1]
        # 运维 only: reform pieces are followed on the reform service's own pages
        tinn = "project_id IN (%s) AND links NOT LIKE '%s'" % (",".join("?" * len(ids)), REFORM_LIKE)
        inn = "project_id IN (%s) AND (ticket_id IS NULL OR ticket_id NOT IN (SELECT id FROM tickets WHERE links LIKE '%s'))" % (",".join("?" * len(ids)), REFORM_LIKE)
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
        today = now()[:10]
        t_new = st.one("SELECT COUNT(*) n FROM tickets WHERE %s AND substr(created,1,10)=?" % tinn, ids + [today])["n"]
        t_closed = st.one("SELECT COUNT(*) n FROM tickets WHERE %s AND status='closed' AND substr(updated,1,10)=?" % tinn, ids + [today])["n"]
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
                "waiting": len(self.flow.waiting(p)) if open_ else 0,
                "metrics": [
                    {"key": "loop", "label": "闭环完成率", "pct": pct(closed, total), "sub": "共 %d 单 · 已闭环 %d" % (total, closed)},
                    {"key": "agent", "label": "智能体分析覆盖", "pct": pct(analyzed, total), "sub": "%d 单有分析结论" % analyzed},
                    {"key": "accept", "label": "代码改动采纳率", "pct": pct(accepted, len(fixes)), "sub": "已审 %d · 采纳 %d" % (len(fixes), accepted)},
                    {"key": "kb", "label": "知识库覆盖", "pct": pct(written, inscope), "sub": "已写 %d / %d 页" % (written, inscope) if built else "尚未构建"},
                ],
                "today": {"created": t_new, "closed": t_closed}, "insight": "，".join(facts) + "。",
                "points": sum(self.balance(x) for x in ps), "projects": len(ps)}

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
        tickets = st.tickets(limit=100000, svc="ops")  # reform pieces are counted on the reform service's own page
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
    FILE_LINE = re.compile(r"([\w./\\-]+\.(?:java|cs|xml|sql|jsp|aspx|cshtml|config|properties|yml|yaml|vb|js|ts|vue|kt|py)):(\d+)")

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
        if mode == "evidence" or kind in ("help", "retry", "state"):
            ans = assist.answer(self, p, t, q, hist, kind)
            self.store.chat_add(p["id"], s["ticket_id"], "assistant", ans.get("source", "知识库"), ans["body"],
                                {"mode": "evidence", "cards": ans.get("cards") or [], "no_evidence": ans.get("no_evidence", False), "points": 0,
                                 "next": ans.get("next", ""), "intent": kind, "source": ans.get("source", ""),
                                 "actions": ans.get("actions") or [], "follow": ans.get("follow") or [], "topic": ans.get("topic") or {},
                                 "deep": bool(ans.get("deep")), "weak": bool(ans.get("weak"))}, session_id=s["id"])
            return
        try:
            r = self.runner.start(p, t, agent or "codex", "ask", user, question=q, history=hist, session_id=s["id"], model=model)
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


# ---------------------------------------------------------------- routing

ROUTES = []


def route(method: str, pattern: str):
    rx = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


@route("GET", "/api/meta")
def api_meta(P, req):
    from .login import load_users
    return {"version": __version__, "user": req.user, "login": bool(load_users(P.data_dir)), "brand": P.brand, "statuses": STATUSES, "types": TYPES, "priorities": PRIORITIES,
            "modes": RUN_MODES, "agents": available(P.data_dir), "data_dir": str(P.data_dir), "autoflow": P.flow.autoflow(),
            "apps": __import__("tmh.platform.apps", fromlist=["APPS"]).APPS}


@route("GET", "/api/projects")
def api_projects(P, req):
    out = []
    for p in P.store.projects():
        s = P.store.stats(p["id"])
        p["open"] = sum(v for k, v in s["by_status"].items() if k != "closed")
        p["exists"] = Path(p["root"]).is_dir()
        out.append(p)
    return out


@route("POST", "/api/projects")
def api_add_project(P, req):
    b = req.body
    try:
        return P.store.add_project(b.get("key", ""), b.get("name", ""), os.path.expanduser(b.get("root", "")), b.get("description", ""))
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/projects/<key>")
def api_project(P, req, key):
    p = P.project(key)
    return {"project": p, "stats": P.store.stats(p["id"]), "kb": P.kb.kb_overview(p),
            "runs": P.store.runs(project_id=p["id"], limit=8),
            "recent": P.store.tickets(project_id=p["id"], limit=8)}


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


@route("GET", "/api/projects/<key>/atlas")
def api_atlas(P, req, key):
    return P.kb.atlas(P.project(key))


@route("GET", "/api/projects/<key>/atlas/flow/<fid>")
def api_atlas_flow(P, req, key, fid):
    return P.kb.atlas_flow(P.project(key), unquote(fid))


@route("GET", "/api/projects/<key>/arch")
def api_arch(P, req, key):
    return P.kb.arch(P.project(key))


@route("GET", "/api/projects/<key>/arch/<did>")
def api_arch_domain(P, req, key, did):
    return P.kb.domain_detail(P.project(key), did)


@route("GET", "/api/projects/<key>/kb/page")
def api_kb_page(P, req, key):
    return P.kb.kb_page(P.project(key), req.arg("id"))


@route("POST", "/api/projects/<key>/kb/confirm")
def api_kb_confirm(P, req, key):
    from .. import kb
    p = P.project(key)
    try:
        kb.confirm(P.root(p), req.body.get("id", ""), req.user, req.body.get("note", ""))
    except KeyError:
        raise ApiError(404, "知识页不存在")
    return {"ok": True}


@route("GET", "/api/projects/<key>/kb/questions")
def api_kb_questions(P, req, key):
    from .. import kbqa
    root = P.root(P.project(key))
    return {"questions": kbqa.questions(root), "stats": kbqa.stats(root), "router": {k: v for k, v in kbqa.router_conf(root).items() if k != "key_env"}}


@route("POST", "/api/projects/<key>/kb/ask")
def api_kb_ask(P, req, key):
    from .. import kbqa
    q = (req.body.get("question") or "").strip()
    if not q:
        raise ApiError(400, "问题不能为空")
    n = kbqa.ask(P.root(P.project(key)), q, [x for x in req.body.get("pages") or [] if isinstance(x, str)], req.body.get("to", ""), req.user)
    return {"n": n}


@route("POST", "/api/projects/<key>/kb/answer")
def api_kb_answer(P, req, key):
    """A person records the business side's answer, word for word; the pages it concerns are queued for revision."""
    from .. import kbqa
    text = (req.body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "答复不能为空")
    try:
        return kbqa.answer(P.root(P.project(key)), int(req.body.get("n") or 0), text, req.body.get("by") or req.user)
    except KeyError as e:
        raise ApiError(404, e.args[0])
    except ValueError as e:
        raise ApiError(400, e.args[0])


@route("POST", "/api/projects/<key>/kb/triage")
def api_kb_triage(P, req, key):
    from .. import kbqa
    root = P.root(P.project(key))
    text = (req.body.get("request") or "").strip()
    if not text:
        raise ApiError(400, "需求不能为空")
    res = kbqa.triage(root, text, use_model=req.body.get("model", True) is not False, channel="web", sender=req.user)
    if req.body.get("record"):
        res["recorded"] = kbqa.record(root, res, req.user)
    return res


def _chooser(P, p: dict):
    """The routing model as a typed chooser for the requirement conversation, or None when not configured."""
    from .. import kbqa
    conf = kbqa.router_conf(P.root(p))
    if not conf["ready"]:
        return None
    return lambda text, q, opts: kbqa.choose(conf, "需求原话：%s" % text, q, opts)["index"]


@route("POST", "/api/projects/<key>/intake")
def api_intake_start(P, req, key):
    """A requirement conversation: split, classify, restate on the business map, ask only what is missing."""
    from . import intake
    p = P.project(key)
    model = req.body.get("model", True) is not False
    return intake.start(P, p, req.body.get("text", ""), req.user, req.body.get("channel") or "web", _chooser(P, p) if model else None)


@route("GET", "/api/intake/<sid>")
def api_intake_get(P, req, sid):
    from . import intake
    return intake.load(P.data_dir, sid)


@route("POST", "/api/intake/<sid>")
def api_intake_act(P, req, sid):
    """answer: {"answers": {"0": {"trigger": "…"}}}; confirm: tickets from the items (all, or "items"); drop."""
    from . import intake
    a = req.body.get("action")
    if a == "answer":
        return intake.answer(P, sid, req.user, req.body.get("answers") or {})
    if a == "confirm":
        return intake.confirm(P, sid, req.user, req.body.get("items"))
    if a == "drop":
        return intake.drop(P, sid, req.user)
    raise ApiError(400, "action 只能是 answer、confirm、drop")


@route("POST", "/api/projects/<key>/pins")
def api_pin_add(P, req, key):
    """A box drawn on the system's page: texts, elements and requests in it, located in the code."""
    from . import pinpoint
    return pinpoint.save(P, P.project(key), req.body, req.user, "platform")


@route("GET", "/api/projects/<key>/pins")
def api_pins(P, req, key):
    from . import pinpoint
    p = P.project(key)
    return {"pins": [dict(x, summary=pinpoint.summary(x)) for x in pinpoint.recent(P.data_dir, p["key"])],
            "has_token": pinpoint.has_token(P.data_dir, p["key"])}


@route("POST", "/api/projects/<key>/capture-token")
def api_capture_token(P, req, key):
    """The bookmarklet for the client's own pages. Issuing a new one switches the old one off."""
    from . import pinpoint
    p = P.project(key)
    base = (req.body.get("base") or "").strip()
    if not re.match(r"^https?://[^/\s]+$", base):
        proto = req.h.headers.get("X-Forwarded-Proto") or "http"
        base = "%s://%s" % (proto, req.h.headers.get("Host") or "127.0.0.1")
    tok = pinpoint.issue_token(P.data_dir, p["key"], req.user)
    return {"bookmarklet": pinpoint.bookmarklet(base, tok), "endpoint": base + "/capture/<token>"}


@route("GET", "/api/pins/<pid>")
def api_pin(P, req, pid):
    from . import pinpoint
    x = pinpoint.load(P.data_dir, pid)
    return dict(x, summary=pinpoint.summary(x))


@route("POST", "/api/pins/<pid>/intake")
def api_pin_intake(P, req, pid):
    """Start the requirement conversation from a box: the note is what they said, the location rides along."""
    from . import intake, pinpoint
    x = pinpoint.load(P.data_dir, pid)
    p = P.project(x["project"])
    text = (req.body.get("text") or x["capture"].get("note") or "").strip()
    if len(text) < 4:
        text = "页面上这里有问题：%s" % "、".join(x["capture"]["texts"][:3])
    model = req.body.get("model", True) is not False
    return intake.start(P, p, text, req.user, "pin", _chooser(P, p) if model else None,
                        pin={"id": x["id"], "summary": pinpoint.summary(x)})


@route("GET", "/api/projects/<key>/kb/metrics")
def api_kb_metrics(P, req, key):
    """少找人: requests answered without a person, overrules, handoffs per week, business answer wait."""
    from .. import kbqa
    root = P.root(P.project(key))
    try:
        days = int(req.arg("days") or 0)
    except ValueError:
        raise ApiError(400, "days 要写数字")
    return {"metrics": kbqa.metrics(root, days, req.arg("month") or ""), "recent": kbqa.triages(root, 30)}


@route("GET", "/api/tickets/<key>/similar")
def api_ticket_similar(P, req, key):
    """Earlier tickets that read like this one (相似工单查重)."""
    from .similar import similar
    t = P.ticket(key)
    return {"similar": similar(P.store.tickets(project_id=t["project_id"], limit=5000), t["title"], t["body"], exclude=t["id"])}


@route("POST", "/api/projects/<key>/similar")
def api_project_similar(P, req, key):
    """While a new ticket is being written: does it repeat an existing one?"""
    from .similar import similar
    p = P.project(key)
    title, body = str(req.body.get("title") or ""), str(req.body.get("body") or "")
    if len((title + body).strip()) < 2:
        return {"similar": []}
    return {"similar": similar(P.store.tickets(project_id=p["id"], limit=5000), title, body, limit=int(req.body.get("limit") or 5))}


@route("GET", "/api/projects/<key>/bots")
def api_bots(P, req, key):
    """Which chat robots this project has and whether their environment variables are set; callback paths to paste."""
    from .. import bots
    p = P.project(key)
    st = bots.status(P.root(p))
    st["paths"] = {k: "/bot/%s/%s" % (k, p["key"]) for k in bots.KINDS}
    return st


@route("POST", "/api/projects/<key>/kb/overrule")
def api_kb_overrule(P, req, key):
    from .. import kbqa
    try:
        return kbqa.overrule(P.root(P.project(key)), req.body.get("id") or "", req.body.get("by") or req.user,
                             (req.body.get("reason") or "").strip(), req.body.get("verdict") or "")
    except KeyError as e:
        raise ApiError(404, e.args[0])
    except ValueError as e:
        raise ApiError(400, e.args[0])


@route("GET", "/api/projects/<key>/integrations")
def api_ints(P, req, key):
    return P.integrations(P.project(key))


@route("POST", "/api/projects/<key>/import")
def api_import(P, req, key):
    b = req.body
    keys = [k.strip() for k in re.split(r"[,\s，]+", b.get("keys", "")) if k.strip()]
    if not keys and not b.get("query"):
        raise ApiError(400, "填写外部工单号，或一个搜索条件")
    return {"imported": P.import_issues(P.project(key), b.get("via", ""), keys, b.get("query", ""), req.user)}


@route("GET", "/api/projects/<key>/survey")
def api_survey(P, req, key):
    p = P.project(key)
    sv = P.surveys.get(p["id"])
    if sv:
        return sv.view()
    from .. import kb
    reg = kb.load_registry(P.root(p))
    return {"state": "idle", "coverage": kb.coverage(reg) if reg else None}


@route("POST", "/api/projects/<key>/survey")
def api_survey_start(P, req, key):
    """Full-project analysis: agents write the knowledge base page by page."""
    from .agents import load_config
    from .survey import Survey
    p = P.project(key)
    sv = P.surveys.get(p["id"])
    if sv and sv.busy:
        raise ApiError(409, "这个项目的全项目分析还在进行")
    agent = req.body.get("agent", "codex")
    if agent not in load_config(P.data_dir):
        raise ApiError(400, "没有这个智能体：%s" % agent)
    try:
        pick_model(load_config(P.data_dir)[agent], "kb", req.body.get("model"))
    except ValueError as e:
        raise ApiError(400, str(e))
    sv = Survey(P, p, agent, req.body.get("parallel", 2), req.body.get("limit", 0), req.user, req.body.get("scope", "all"), req.body.get("model"))
    P.surveys[p["id"]] = sv
    sv.start()
    return sv.view()


@route("POST", "/api/projects/<key>/survey/stop")
def api_survey_stop(P, req, key):
    sv = P.surveys.get(P.project(key)["id"])
    if not sv or not sv.busy:
        raise ApiError(400, "没有进行中的全项目分析")
    sv.stop()
    return sv.view()


@route("GET", "/api/lead")
def api_lead(P, req):
    try:
        days = max(1, min(366, int(req.arg("days") or 30)))
    except ValueError:
        raise ApiError(400, "days 写成天数，例如 30")
    return P.lead(days)


@route("POST", "/api/projects/<key>/catchup")
def api_catchup(P, req, key):
    """Hand every open ticket that is not on the automatic line yet over to it (one or two at a time)."""
    return {"queued": P.flow.catch_up(None if key in ("*", "all") else P.project(key), req.user)}


@route("GET", "/api/projects/<key>/loop")
def api_loop(P, req, key):
    return P.loop(None if key in ("*", "all") else P.project(key))


@route("GET", "/api/projects/<key>/points")
def api_points(P, req, key):
    p = P.project(key)
    return {"balance": P.balance(p), "prices": P.pricing["prices"], "log": P.store.points_log(p["id"])}


@route("POST", "/api/projects/<key>/points")
def api_points_add(P, req, key):
    p = P.project(key)
    try:
        n = int(req.body.get("delta") or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "点数必须是整数")
    if not n:
        raise ApiError(400, "点数不能为 0")
    P.balance(p)
    P.store.add_points(p["id"], n, req.body.get("reason") or ("充值" if n > 0 else "调整"), req.user)
    return {"balance": P.balance(p)}


@route("GET", "/api/assist")
def api_assist_list(P, req):
    """Older entry point: the person's session for a ticket, or their latest project session."""
    p = P.project(req.arg("project"))
    s = _default_session(P, req, p, req.arg("ticket"))
    return {"session": P.session_info(s), "messages": P.session_view(s["id"]), "balance": P.balance(p), "price": P.pricing["prices"].get("ask", 0)}


@route("POST", "/api/assist")
def api_assist(P, req):
    b = req.body
    p = P.project(b.get("project", ""))
    s = P.session_of(b["session"], req.user) if b.get("session") else _default_session(P, req, p, b.get("ticket"))
    q = (b.get("question") or "").strip()
    if not q:
        raise ApiError(400, "问题是空的")
    P.ask(s, q, b.get("mode"), b.get("agent"), req.user, b.get("model"))
    return {"session": P.session_info(P.store.session(s["id"])), "messages": P.session_view(s["id"]), "balance": P.balance(p)}


def _default_session(P, req, p, ticket_key):
    if ticket_key:
        return P.ticket_session(p, P.ticket(ticket_key), req.user)
    for s in P.store.sessions(p["id"], req.user):
        if not s["archived_at"] and not s["ticket_id"]:
            return s
    return P.store.session_create(p["id"], "consult", "项目咨询", req.user)


# ---- assistant sessions
@route("GET", "/api/projects/<key>/sessions")
def api_sessions(P, req, key):
    p = P.project(key)
    ms = {m["id"]: m for m in P.store.matters(p["id"])}
    out = []
    for s in P.store.sessions(p["id"], req.user):
        s = dict(s)
        if s["ticket_id"]:
            t = P.store.ticket(s["ticket_id"])
            s["ticket"] = t and {"key": t["key"], "title": t["title"], "status": t["status"]}
        if s["matter_id"] in ms:
            s["matter"] = {"id": s["matter_id"], "title": ms[s["matter_id"]]["title"]}
        out.append(s)
    return {"sessions": out, "matters": [m for m in ms.values() if m["created_by"] in (req.user, "")]}


@route("POST", "/api/projects/<key>/sessions")
def api_new_session(P, req, key):
    """New session: a project question (consult), a maintenance matter (new or existing), or a ticket's working session."""
    p = P.project(key)
    b = req.body
    kind = b.get("kind") or "consult"
    if kind == "ticket":
        t = P.ticket(b.get("ticket", ""))
        if t["project_id"] != p["id"]:
            raise ApiError(400, "工单不属于这个项目")
        s = P.ticket_session(p, t, req.user) if not b.get("fresh") else \
            P.store.session_create(p["id"], "ticket", b.get("title") or "%s 处理讨论" % t["key"], req.user, ticket_id=t["id"])
        return P.session_info(s)
    mid = None
    if kind == "matter":
        if b.get("matter_id"):
            m = P.store.matter(int(b["matter_id"]))
            if not m or m["project_id"] != p["id"]:
                raise ApiError(404, "没有这个维护事项")
            mid = m["id"]
        else:
            mid = P.store.matter_create(p["id"], b.get("matter_title") or b.get("title") or "维护事项", req.user)["id"]
    try:
        s = P.store.session_create(p["id"], kind, b.get("title") or ("问题排查" if kind == "matter" else "项目咨询"), req.user, matter_id=mid)
    except ValueError as e:
        raise ApiError(400, str(e))
    return P.session_info(s)


@route("GET", "/api/sessions/<sid>")
def api_session(P, req, sid):
    s = P.session_of(sid, req.user)
    p = P.store.project(s["project_id"])
    return {"session": P.session_info(s), "messages": P.session_view(s["id"]), "balance": P.balance(p),
            "price": P.pricing["prices"].get("ask", 0)}


@route("POST", "/api/sessions/<sid>")
def api_update_session(P, req, sid):
    """Rename, archive or restore. Archiving keeps every message and does not stop a running answer."""
    s = P.session_of(sid, req.user)
    b, f = req.body, {}
    if "title" in b:
        if not (b["title"] or "").strip():
            raise ApiError(400, "会话名称不能为空")
        f["title"] = b["title"].strip()[:60]
    if "archived" in b:
        f["archived_at"] = now() if b["archived"] else ""
    return P.session_info(P.store.session_update(s["id"], **f))


@route("POST", "/api/sessions/<sid>/messages")
def api_session_ask(P, req, sid):
    s = P.session_of(sid, req.user)
    if s["archived_at"]:
        raise ApiError(400, "会话已归档，恢复后才能继续发送")
    q = (req.body.get("question") or "").strip()
    if not q:
        raise ApiError(400, "问题是空的")
    key = req.body.get("idem")
    if key and P.store.idem_get("ask:" + key) is not None:
        return api_session(P, req, sid)
    P.ask(s, q, req.body.get("mode"), req.body.get("agent"), req.user, req.body.get("model"))
    if key:
        P.store.idem_put("ask:" + key, s["id"])
    return api_session(P, req, sid)


@route("POST", "/api/projects/<key>/command")
def api_command(P, req, key):
    """Plan one sentence from the side panel as UI steps (see command.py). The browser runs them; saves wait for the person.

    With a session, the sentence and the plan are kept in that session so the history shows what was done."""
    from .. import kbqa
    p = P.project(key)
    b = req.body
    text = (b.get("text") or "").strip()
    if not text:
        raise ApiError(400, "指令是空的")
    sessions = [P.session_info(s) for s in P.store.sessions(p["id"], req.user) if not s["archived_at"]]
    projects = [{"key": x["key"], "name": x["name"]} for x in P.store.projects()]
    conf = kbqa.router_conf(P.root(p)) if b.get("model", True) else {}
    pl = command.plan(text, b.get("page") or {}, sessions, projects, conf)
    out = {"plan": pl}
    if pl["kind"] == "command" and b.get("session"):
        s = P.session_of(b["session"], req.user)
        if not s["archived_at"]:
            P.store.chat_add(p["id"], s["ticket_id"], "user", req.user, text, {"kind": "cmd"}, session_id=s["id"])
            out["message"] = P.store.chat_add(p["id"], s["ticket_id"], "assistant", "助手", pl["summary"],
                                              {"kind": "cmd", "plan": pl, "state": "proposed", "done": 0}, session_id=s["id"])
    return out


@route("POST", "/api/sessions/<sid>/command/<mid>")
def api_command_state(P, req, sid, mid):
    """Record how a planned command went: done, cancelled, failed or undone, how many steps ran, and what puts it back."""
    s = P.session_of(sid, req.user)
    rows = P.store.q("SELECT * FROM chats WHERE id=? AND session_id=?", (int(mid) if str(mid).isdigit() else -1, s["id"]))
    if not rows or (rows[0]["data"] or {}).get("kind") != "cmd":
        raise ApiError(404, "没有这条指令")
    m = rows[0]
    d = dict(m["data"] or {})
    st = req.body.get("state")
    if st not in ("proposed", "waiting", "done", "cancelled", "failed", "undone"):
        raise ApiError(400, "状态不对")
    d["state"] = st
    u = req.body.get("undo")
    if isinstance(u, dict) and u.get("target") in ("fs", "fy", "fp") and str(u.get("route") or "").startswith("#/t/"):
        d["undo"] = {"target": u["target"], "value": str(u.get("value") or "")[:40], "text": str(u.get("text") or "")[:40], "route": str(u["route"])[:60]}
    d["done"] = max(0, min(int(req.body.get("done") or 0), len((d.get("plan") or {}).get("steps") or [])))
    if req.body.get("note"):
        d["note"] = str(req.body["note"])[:300]
    P.store.chat_update(m["id"], m["body"], d)
    return {"ok": True, "data": d}


@route("POST", "/api/sessions/<sid>/ticket-draft")
def api_ticket_draft(P, req, sid):
    return P.ticket_draft(P.session_of(sid, req.user))


@route("POST", "/api/sessions/<sid>/ticket")
def api_session_ticket(P, req, sid):
    """Submit a reviewed draft: a new ticket, or a note on the session's existing ticket. Same idem key → same result."""
    s = P.session_of(sid, req.user)
    b = req.body
    key = "ticket:%s" % (b.get("idem") or "")
    if b.get("idem"):
        done = P.store.idem_get(key)
        if done is not None:
            return done
    p = P.store.project(s["project_id"])
    body = (b.get("body") or "").strip()
    if (b.get("accept") or "").strip():
        body += "\n\n## 验收条件\n" + b["accept"].strip()
    if b.get("target") == "existing" and s["ticket_id"]:
        t = P.store.ticket(s["ticket_id"])
        P.store.event(t["id"], req.user, "comment", "（从助手会话「%s」补充）\n\n%s" % (s["title"], body))
        P.store.touch(t["id"])
        res = {"key": t["key"], "created": False}
    else:
        try:
            t = P.store.create_ticket(p["id"], b.get("title", ""), req.user, body=body, type=b.get("type"), priority=b.get("priority"),
                                      assignee=b.get("assignee", ""), links={"flows": list(b.get("flows") or []), "session": s["id"]})
        except ValueError as e:
            raise ApiError(400, str(e))
        P.store.event(t["id"], req.user, "comment", "由助手会话「%s」起草，经 %s 核对后提交" % (s["title"], req.user))
        P.flow.submit(p, t)
        if not s["ticket_id"]:
            P.store.session_update(s["id"], ticket_id=t["id"])
        if s["matter_id"]:
            m = P.store.matter(s["matter_id"])
            if m and not m["ticket_id"]:
                P.store.matter_update(m["id"], ticket_id=t["id"])
        res = {"key": t["key"], "created": True}
    if b.get("idem"):
        P.store.idem_put(key, res)
    return res


@route("POST", "/api/tickets/<key>/accept")
def api_accept(P, req, key):
    """Human acceptance: only a person passes or fails a ticket; the assistant may only draft the note."""
    t = P.ticket(key)
    res, note = req.body.get("result"), (req.body.get("note") or "").strip()
    if res not in ("pass", "fail"):
        raise ApiError(400, "result 只能是 pass 或 fail")
    if res == "fail" and not note:
        raise ApiError(400, "验收不通过时必须写明原因")
    from . import signoff
    sealed = signoff.record_accept(P, t, req.user, res == "pass", note)
    P.store.event(t["id"], req.user, "accept" if res == "pass" else "reject", ("验收通过" if res == "pass" else "验收不通过") + ("：" + note if note else ""),
                  dict({"result": res}, **({"evidence": sealed} if sealed else {})))
    P.store.update_ticket(t["id"], req.user, status="closed" if res == "pass" else "doing")
    P.flow.accepted(P.store.project(t["project_id"]), P.store.ticket(t["id"]), res == "pass", note, req.user)
    return P.store.ticket(t["id"])


@route("GET", "/api/projects/<key>/learn")
def api_learn(P, req, key):
    """What the outcomes taught: lessons, the eval set and its scores, and where alerts come in."""
    from . import alerts, learn
    p = P.project(key)
    al = [{"key": t["key"], "title": t["title"], "status": t["status"], "priority": t["priority"], "created": t["created"],
           "count": t["links"]["alert"].get("count", 1), "source": t["links"]["alert"].get("source", "")}
          for t in P.store.tickets(project_id=p["id"], limit=2000) if (t.get("links") or {}).get("alert")][:30]
    return {"lessons": learn.lessons(P.data_dir, p["key"], 50), "cases": learn.cases(P.data_dir, p["key"]),
            "batches": learn.batches(P.data_dir, p["key"]), "running": learn.RUNNING.get(p["key"], ""),
            "alerts": dict(alerts.status(P.data_dir, p["key"]), tickets=al), "refix": P.flow.autoflow().get("refix")}


@route("POST", "/api/projects/<key>/evals/run")
def api_eval_run(P, req, key):
    from . import learn
    p = P.project(key)
    agent = req.body.get("agent") or P.flow.agent()
    try:
        return learn.run_evals(P.flow, p, agent, req.body.get("model"), req.user, req.body.get("cases") or None)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/projects/<key>/evals/cases")
def api_eval_case(P, req, key):
    from . import learn
    p, b = P.project(key), req.body
    if b.get("remove"):
        return {"removed": learn.remove_case(P.data_dir, p["key"], str(b["remove"]))}
    gold = b.get("gold") or []
    if isinstance(gold, str):
        gold = [x for x in re.split(r"[\s,，]+", gold) if x]
    try:
        return learn.add_case(P.data_dir, p["key"], {"title": b.get("title", ""), "body": b.get("body", ""), "base": (b.get("base") or "").strip(),
                                                     "gold": gold, "source": "manual"})
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/projects/<key>/evals/history")
def api_eval_history(P, req, key):
    """Closed tickets matched to the commits that fixed them: a preview, or (apply) new eval cases."""
    from . import learn
    p, b = P.project(key), req.body
    if not is_git(P.root(p)):
        raise ApiError(400, "项目目录不是 git 仓库，没法按提交找修复")
    return learn.from_history(P, p, str(b.get("since") or "")[:10], str(b.get("until") or "")[:10], bool(b.get("apply")), bool(b.get("flagged")))


@route("POST", "/api/projects/<key>/evals/history/import")
def api_eval_history_import(P, req, key):
    """Import the closed tickets that commit messages name, so the preview above has something to match."""
    p, b = P.project(key), req.body
    if not is_git(P.root(p)):
        raise ApiError(400, "项目目录不是 git 仓库，没法从提交信息里找工单号")
    try:
        limit = max(1, min(1000, int(b.get("limit") or 200)))
    except (TypeError, ValueError):
        limit = 200
    return P.import_refs(p, str(b.get("via") or ""), str(b.get("since") or "")[:10], str(b.get("until") or "")[:10], limit, req.user)


@route("POST", "/api/projects/<key>/alerts")
def api_alert_paste(P, req, key):
    """A person pastes an alert or an error log: same handling as the webhook, without its key."""
    from . import alerts
    p = P.project(key)
    text = (req.body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "把告警或报错日志贴进来")
    return alerts.receive(P, p, alerts.parse(text.encode("utf-8")), 10 ** 6)


@route("GET", "/api/projects/<key>/reforms")
def api_reforms(P, req, key):
    """Reform plans (restructuring, upgrades, migrations) with the live state of their tickets, and the domains to choose from."""
    from . import reform
    p = P.project(key)
    at = P.kb.atlas(p)
    doms = [{"id": d["id"], "title": d["title"], "flows": d["flows"], "tables": d["tables"]} for d in at.get("domains") or []]
    return {"kinds": {k: {"label": v[0], "desc": v[1]} for k, v in reform.KINDS.items()}, "built": bool(at.get("built")), "domains": doms,
            "plans": [reform.view(P, p, x) for x in reform.plans(P.data_dir, p["key"])][::-1]}


@route("GET", "/api/projects/<key>/reforms/deps")
def api_reform_deps(P, req, key):
    from . import reform
    return {"deps": reform.dependencies(P.root(P.project(key)))}


@route("POST", "/api/projects/<key>/reforms")
def api_reform_new(P, req, key):
    """{"kind", "title", "goal", "keep", "domains": [...], "wave"}; {"preview": true} only splits, saves nothing."""
    from . import reform
    p = P.project(key)
    at = P.kb.atlas(p)
    if req.body.get("preview"):
        return {"items": reform.split(at, list(req.body.get("domains") or [])) if at.get("built") else []}
    try:
        return reform.view(P, p, reform.create(P.data_dir, p["key"], at, req.body, req.user))
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/projects/<key>/reforms/<pid>")
def api_reform_act(P, req, key, pid):
    """{"action": "release", "n": 3} opens the next tickets; {"action": "remove"} drops the plan (its tickets stay)."""
    from . import reform
    p = P.project(key)
    try:
        if req.body.get("action") == "remove":
            reform.remove(P.data_dir, p["key"], pid)
            return {"removed": pid}
        if req.body.get("action") == "release":
            n = req.body.get("n")
            keys = reform.release(P, p, pid, int(n) if n else None, req.user)
            return dict(reform.view(P, p, reform.plan(P.data_dir, p["key"], pid)), opened=keys)
        if req.body.get("action") in ("auto", "resume"):
            auto = req.body.get("on") if req.body.get("action") == "auto" else None
            reform.configure(P.data_dir, p["key"], pid, None if auto is None else bool(auto), req.body.get("action") == "resume")
            return reform.view(P, p, reform.plan(P.data_dir, p["key"], pid))
    except KeyError:
        raise ApiError(404, "没有这个改造计划")
    except ValueError as e:
        raise ApiError(400, str(e))
    raise ApiError(400, "action 只能是 release、auto、resume 或 remove")


@route("GET", "/api/tickets")
def api_tickets(P, req):
    pid = P.project(req.arg("project"))["id"] if req.arg("project") not in (None, "", "*", "all") else None
    return P.store.tickets(project_id=pid, status=req.arg("status") or None, text=req.arg("q") or None,
                           assignee=req.arg("assignee") or None, limit=int(req.arg("limit") or 500), svc=req.arg("svc") or None)


@route("POST", "/api/tickets")
def api_new_ticket(P, req):
    b = req.body
    p = P.project(b.get("project", ""))
    links = {}
    if b.get("flows"):
        links["flows"] = list(b["flows"])
    if b.get("code_at"):  # the ticket is about an older version of the code (replaying real history)
        sha = git(P.root(p), "rev-parse", "--verify", "-q", str(b["code_at"]) + "^{commit}", check=False).strip()
        if not sha:
            raise ApiError(400, "代码版本 %s 在项目仓库里找不到" % b["code_at"])
        links["code_at"] = sha
    try:
        t = P.store.create_ticket(p["id"], b.get("title", ""), req.user, body=b.get("body", ""), type=b.get("type"),
                                  priority=b.get("priority"), assignee=b.get("assignee", ""), labels=b.get("labels") or [], links=links)
    except ValueError as e:
        raise ApiError(400, str(e))
    if b.get("agent") and b.get("mode"):
        P.runner.start(p, t, b["agent"], b["mode"], req.user, model=b.get("model"))
    elif b.get("auto", True):
        P.flow.submit(p, t)
    return P.store.ticket(t["id"])


@route("GET", "/api/tickets/<key>")
def api_ticket(P, req, key):
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    runs = P.store.runs(ticket_id=t["id"])
    pts = P.store.run_points([r["id"] for r in runs])
    from .fixloop import verified
    for r in runs:
        r["points"] = pts.get(r["id"], 0)
        if r["mode"] == "fix":
            v = verified(P.data_dir, r["id"])
            r["verify"] = {k: v.get(k) for k in ("check", "skip", "verdict", "rounds", "split", "beyond_plan")} if v else None
            if v:
                r["verify"]["files"] = len(v.get("files") or [])
    from . import signoff
    return {"ticket": t, "project": p, "events": P.store.events(t["id"]), "runs": [r for r in runs if r["mode"] != "ask"],
            "evidence": P.ticket_evidence(p, t, runs), "auto_next": P.flow.next_step(t, retry=True)[0],
            "package": signoff.brief(P.data_dir, t["key"])}


@route("GET", "/api/tickets/<key>/evidence")
def api_evidence(P, req, key):
    """The ticket's evidence package: latest snapshot, what was added, what is missing, the seal."""
    from . import signoff
    t = P.ticket(key)
    s = signoff.state(P.data_dir, t["key"])
    s["label"] = signoff.STATUS_LABEL[s["status"]]
    s["page"] = "/e/%s" % t["key"]
    return s


@route("POST", "/api/tickets/<key>/evidence")
def api_evidence_add(P, req, key):
    """kind=attach (screenshot/note for one AC), review (provider's internal review), pack (re-pack now),
    link (a one-time sign-off link for the client's signer)."""
    from . import signoff
    t = P.ticket(key)
    b = req.body
    kind = b.get("kind")
    if kind == "attach":
        r = signoff.attach(P, t, req.user, b.get("ac", ""), b.get("note", ""), b.get("image", ""))
    elif kind == "review":
        r = signoff.review(P, t, req.user, b.get("note", ""), bool(b.get("scope_ok")), bool(b.get("path_ok")),
                           b.get("waive") if isinstance(b.get("waive"), dict) else None)
    elif kind == "pack":
        r = signoff.pack(P, t, req.user, "手动重新打包") or {"unchanged": True}
    elif kind == "link":
        return signoff.issue(P, t, req.user, b.get("signer", ""), b.get("role", ""), int(b.get("days") or signoff.LINK_DAYS), b.get("note", ""))
    else:
        raise ApiError(400, "kind 只能是 attach、review、pack 或 link")
    return {"record": {k: r.get(k) for k in ("seq", "hash", "ts", "unchanged") if k in r}, "state": signoff.brief(P.data_dir, t["key"])}


@route("GET", "/api/tickets/<key>/upstream")
def api_upstream(P, req, key):
    from . import upstream
    return upstream.view(P, P.ticket(key))


@route("POST", "/api/tickets/<key>/upstream")
def api_upstream_act(P, req, key):
    """An external pull request: link (repo, issue, pr), draft (title, body, head, base), approve (a person),
    submit (confirm=true to really open it; dry run otherwise), sync (read GitHub), reason (why it was closed)."""
    from . import upstream
    t, b = P.ticket(key), req.body
    a = b.get("action")
    if a == "link":
        upstream.link(P, t, req.user, b.get("repo", ""), b.get("issue", ""), b.get("pr", ""))
    elif a == "draft":
        upstream.draft(P, t, req.user, b.get("title", ""), b.get("body", ""), b.get("head", ""), b.get("base", ""))
    elif a == "approve":
        upstream.approve(P, t, req.user, b.get("note", ""))
    elif a == "submit":
        r = upstream.submit(P, t, req.user, bool(b.get("confirm")))
        if r.get("dry_run"):
            return r
    elif a == "sync":
        from ..integrations.base import IntegrationError
        try:
            return upstream.sync(P, t, req.user)
        except IntegrationError as e:
            raise ApiError(502, "读 GitHub 失败：%s" % e)
    elif a == "reason":
        upstream.outcome_reason(P, t, req.user, b.get("reason", ""), b.get("note", ""))
    else:
        raise ApiError(400, "action 只能是 link、draft、approve、submit、sync、reason")
    return upstream.view(P, P.ticket(t["id"]))


@route("GET", "/api/projects/<key>/upstream")
def api_upstream_list(P, req, key):
    from . import upstream
    return upstream.metrics(P, P.project(key), req.arg("month"))


@route("GET", "/api/projects/<key>/baseline")
def api_baseline(P, req, key):
    from . import books
    p = P.project(key)
    return {"sealed": books.load_baseline(P.data_dir, p["key"]), "candidate": books.candidate(P.store, p, req.arg("from"), req.arg("to"))}


@route("POST", "/api/projects/<key>/baseline/seal")
def api_baseline_seal(P, req, key):
    """Seal the baseline once: window, method and sample are written down and hashed; it cannot be changed after."""
    from . import books
    p = P.project(key)
    b = req.body
    return books.seal(P.store, P.data_dir, p, b.get("from", ""), b.get("to", ""), req.user, b.get("note", ""))


@route("GET", "/api/projects/<key>/ledger")
def api_ledger(P, req, key):
    m = P.metrics(P.project(key), req.arg("month"))
    return {"ledger": m["ledger"], "sealed": m["sealed"], "gate": m["gate"]}


@route("POST", "/api/tickets/<key>")
def api_update_ticket(P, req, key):
    t = P.ticket(key)
    b = dict(req.body)
    if b.get("status") == "closed" and t["status"] != "closed":
        # closing is acceptance: a person's "验收通过" (POST /accept), never a status edit (docs/acceptance.md)
        raise ApiError(400, "关单只能走验收：由人点“验收通过”（POST /api/tickets/%s/accept）" % t["key"])
    if "link_flow" in b or "unlink_flow" in b or "confirm_flows" in b:
        # flows the automatic flow linked stay "suggested" until a person links or confirms them (flows_ok)
        links = dict(t.get("links") or {})
        fl = list(links.get("flows") or [])
        ok = list(links.get("flows_ok") or [])
        if b.get("link_flow") and b["link_flow"] not in fl:
            fl.append(b["link_flow"])
            P.store.event(t["id"], req.user, "link", "关联业务流 %s" % b["link_flow"])
        if b.get("link_flow") and b["link_flow"] not in ok:
            ok.append(b["link_flow"])
        if b.get("unlink_flow") in fl:
            fl.remove(b["unlink_flow"])
            P.store.event(t["id"], req.user, "link", "取消关联 %s" % b["unlink_flow"])
        ok = [f for f in ok if f in fl]
        cf = b.get("confirm_flows")
        if cf:
            new = [f for f in (fl if cf == "*" else cf if isinstance(cf, list) else []) if f in fl and f not in ok]
            if new:
                ok += new
                P.store.event(t["id"], req.user, "link", "确认关联业务流 %s" % "、".join(f.replace("flow:", "") for f in new))
        links["flows"], links["flows_ok"] = fl, ok
        b["links"] = links
    if b.get("auto") == "go":  # hand a ticket that is not on the automatic line yet over to it
        P.flow.resume(P.store.project(t["project_id"]), t)
        return P.store.ticket(t["id"])
    if "hold" in b:
        t = P.flow.take_over(t, bool(b["hold"]), req.user)
        if not any(k in b for k in ("title", "body", "type", "status", "priority", "assignee", "labels", "links")):
            return t
    try:
        return P.store.update_ticket(t["id"], req.user, **{k: b.get(k) for k in ("title", "body", "type", "status", "priority", "assignee", "labels", "links")})
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/testbox")
def api_testbox(P, req):
    from . import testbox
    f = P.data_dir / "testbox-check.json"
    last = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return {"conf": testbox.settings(P.data_dir), "last": last}


@route("POST", "/api/testbox")
def api_testbox_save(P, req):
    """Where the test machine is: {host: "user@host" or an ~/.ssh/config alias, port (empty: the alias's own), dir}; an empty host turns it off. Key login only."""
    host = str(req.body.get("host") or "").strip()
    if host and not re.match(r"^[\w.-]+@[\w.-]+$", host):
        raise ApiError(400, "地址写成 用户名@主机，比如 auntu@43.153.76.85")
    f = P.data_dir / "autoflow.json"
    conf = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    if host:
        conf["testbox"] = {"host": host, "port": int(req.body.get("port") or 0), "dir": str(req.body.get("dir") or "").strip()}
    else:
        conf.pop("testbox", None)
    f.write_text(json.dumps(conf, ensure_ascii=False, indent=1), encoding="utf-8")
    return api_testbox(P, req)


@route("POST", "/api/testbox/<action>")
def api_testbox_act(P, req, action):
    """check: what the machine has; install: unpack the missing tools there (a person asked for it on the page)."""
    from . import testbox
    conf = testbox.settings(P.data_dir)
    if not conf:
        raise ApiError(400, "还没设置测试机")
    box = testbox.TestBox(conf, P.data_dir)
    if action == "check":
        r = box.check()
    elif action == "install":
        r = box.install(req.body.get("tools") or None)
        r = dict(r["check"], log=r["log"]) if r.get("check") else r
    else:
        raise ApiError(404, "没有这个操作")
    r["at"] = now()
    (P.data_dir / "testbox-check.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    return r


@route("POST", "/api/tickets/<key>/comments")
def api_comment(P, req, key):
    t = P.ticket(key)
    body = (req.body.get("body") or "").strip()
    if not body:
        raise ApiError(400, "评论不能为空")
    P.store.event(t["id"], req.user, "comment", body)
    P.store.touch(t["id"])
    return {"ok": True}


@route("GET", "/api/tickets/<key>/related")
def api_ticket_related(P, req, key):
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    return P.kb.related(p, "%s %s" % (t["title"], (t.get("body") or "")[:600]))


@route("GET", "/api/tickets/<key>/context")
def api_ticket_context(P, req, key):
    from .agents import knowledge
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    return {"text": knowledge(P.root(p), "%s %s" % (t["title"], (t.get("body") or "")[:600]), 8000)}


@route("POST", "/api/tickets/<key>/runs")
def api_start_run(P, req, key):
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    mode, n = req.body.get("mode", "analyze"), int(req.body.get("kb_after") or 0)
    then = (lambda run: P.kb.kb_followup(p, P.store.ticket(t["id"]), run, n, req.user)) if n and mode == "analyze" else None
    try:
        sid = req.body.get("session")
        s = P.session_of(sid, req.user) if sid else None
        return P.runner.start(p, t, req.body.get("agent", "claude"), mode, req.user, req.body.get("target", ""), then,
                              session_id=s and s["id"], model=req.body.get("model"))
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/tickets/<key>/push")
def api_push(P, req, key):
    return P.push_comment(P.ticket(key), req.body.get("body", ""), bool(req.body.get("confirm")), req.user)


@route("POST", "/api/projects/<key>/runs")
def api_project_run(P, req, key):
    """Runs without a ticket, e.g. writing a knowledge page."""
    p = P.project(key)
    try:
        return P.runner.start(p, None, req.body.get("agent", "claude"), req.body.get("mode", "kb"), req.user, req.body.get("target", ""),
                              batch=str(req.body.get("batch") or "")[:40], model=req.body.get("model"))
    except ValueError as e:
        raise ApiError(400, str(e))


@route("GET", "/api/runs")
def api_runs(P, req):
    pid = P.project(req.arg("project"))["id"] if req.arg("project") else None
    runs = P.store.runs(project_id=pid, limit=200)
    keys = {}
    for r in runs:
        if r["ticket_id"] and r["ticket_id"] not in keys:
            t = P.store.ticket(r["ticket_id"])
            keys[r["ticket_id"]] = (t["key"], t["title"]) if t else ("", "")
        r["ticket"], r["ticket_title"] = keys.get(r["ticket_id"], ("", ""))
    names = {}
    for r in runs:
        if r["session_id"] and r["session_id"] not in names:
            s = P.store.session(r["session_id"])
            names[r["session_id"]] = s["title"] if s else ""
        r["session_title"] = names.get(r["session_id"], "")
    return runs


@route("GET", "/api/runs/<rid>")
def api_run(P, req, rid):
    r = P.store.run(int(rid))
    if not r:
        raise ApiError(404, "没有这个运行")
    since = int(req.arg("since") or 0)
    r["output_len"] = len(r["output"])
    r["output"] = r["output"][since:]
    if req.arg("prompt") != "1":
        r["prompt"] = ""
    return r


@route("POST", "/api/runs/<rid>/cancel")
def api_cancel(P, req, rid):
    try:
        return P.runner.cancel(int(rid), req.user)
    except ValueError as e:
        raise ApiError(400, str(e))


@route("POST", "/api/runs/<rid>/decide")
def api_decide(P, req, rid):
    try:
        return P.runner.decide(int(rid), req.body.get("decision", ""), req.user)
    except (ValueError, RuntimeError) as e:
        raise ApiError(400, str(e))

@route("POST", "/api/runs/<rid>/recheck")
def api_recheck(P, req, rid):
    """Build a finished change again without redoing it; poll GET .../recheck for the result."""
    try:
        return P.flow.recheck(int(rid), req.user, wait=bool(req.body.get("wait")))
    except (ValueError, RuntimeError) as e:
        raise ApiError(400, str(e))


@route("GET", "/api/runs/<rid>/recheck")
def api_recheck_state(P, req, rid):
    from .fixloop import verified
    r = P.store.run(int(rid))
    if not r:
        raise ApiError(404, "没有这个运行")
    v = verified(P.data_dir, int(rid))
    return {"running": int(rid) in P.flow.rechecking, "decision": r["decision"],
            "verify": {k: v.get(k) for k in ("check", "skip", "verdict", "rechecked")} if v else None}



@route("GET", "/api/projects/<key>/metrics")
def api_metrics(P, req, key):
    return P.metrics(P.project(key), req.arg("month"))


@route("GET", "/api/projects/<key>/report")
def api_report(P, req, key):
    """《AI 提效报告》 as Markdown; /p/<key>/efficiency?month= serves the same as a printable page."""
    p = P.project(key)
    m = P.metrics(p, req.arg("month"))
    return {"markdown": report_md(m), "filename": "AI提效报告-%s-%s.md" % (p["key"], m["month"] or "全部")}


@route("GET", "/api/tickets/<key>/prompt")
def api_ticket_prompt(P, req, key):
    return P.ticket_prompt(P.ticket(key), req.arg("scene") or "bugfix")


@route("POST", "/api/tickets/<key>/prompt")
def api_use_prompt(P, req, key):
    return P.use_prompt(P.ticket(key), req.body.get("scene") or "bugfix", req.body.get("action") or "copy", req.user)


@route("GET", "/api/stats")
def api_stats(P, req):
    pid = P.project(req.arg("project"))["id"] if req.arg("project") else None
    return P.store.stats(pid)


# ---------------------------------------------------------------- HTTP

class Req:
    def __init__(self, h, query: dict, body: dict, user: str):
        self.h, self.query, self.body, self.user = h, query, body, user

    def arg(self, k: str) -> str:
        return (self.query.get(k) or [""])[0]


def make_handler(P: Platform, token: str = ""):
    from . import login as L
    from .ui import page
    throttle = L.Throttle()

    class H(BaseHTTPRequestHandler):
        server_version = "tmh/" + __version__

        def log_message(self, fmt, *args):  # quiet; errors are printed below
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _authorized(self, q: dict) -> bool:
            self._who = ""
            accounts = bool(L.load_users(P.data_dir))
            if accounts:
                self._who = L.read_session(P.data_dir, _cookie(self.headers.get("Cookie", ""), "tmh_session"))
                if self._who:
                    return True
            if not token:
                return not accounts
            got = self.headers.get("X-TMH-Token") or (q.get("token") or [""])[0] or _cookie(self.headers.get("Cookie", ""), "tmh_token")
            return hmac.compare_digest(got.encode("utf-8"), token.encode("utf-8"))

        def _client(self) -> str:
            ip = self.client_address[0]
            fwd = self.headers.get("X-Forwarded-For") or ""
            if ip in ("127.0.0.1", "::1") and fwd:  # behind our own Caddy/nginx: it appends the real client last
                ip = fwd.split(",")[-1].strip()
            return ip

        def _session_cookie(self, value: str, age: int) -> str:
            secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") or "") == "https" else ""
            return "tmh_session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (value, age, secure)

        def _login(self, method: str, q: dict):
            if method == "GET":
                if self._authorized(q) and self._who:
                    return self._send(303, b"", "text/plain", {"Location": L.safe_next((q.get("next") or ["/"])[0])})
                return self._send(200, L.page(P.brand, next_=(q.get("next") or ["/"])[0]).encode("utf-8"), "text/html; charset=utf-8")
            n = int(self.headers.get("Content-Length") or 0)
            if n > 8192:
                return self._send(413, b"too large", "text/plain")
            f = parse_qs(self.rfile.read(n).decode("utf-8", "replace") if n else "")
            name, pw = (f.get("username") or [""])[0].strip(), (f.get("password") or [""])[0]
            nxt = (f.get("next") or ["/"])[0]
            who = self._client()
            if throttle.blocked(who):
                return self._send(429, L.page(P.brand, "密码错误次数太多，请 10 分钟后再试", name, nxt).encode("utf-8"), "text/html; charset=utf-8")
            if not L.verify(P.data_dir, name, pw):
                throttle.fail(who)
                return self._send(401, L.page(P.brand, "账号或密码不正确", name, nxt).encode("utf-8"), "text/html; charset=utf-8")
            throttle.ok(who)
            return self._send(303, b"", "text/plain", {"Location": L.safe_next(nxt),
                                                       "Set-Cookie": self._session_cookie(L.make_session(P.data_dir, name), L.SESSION_DAYS * 86400)})

        def _local_host(self) -> bool:
            # without a token, only answer requests addressed to this machine (blocks DNS rebinding)
            if token:
                return True
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ("127.0.0.1", "localhost", "::1", "")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def _bot(self, method: str, path: str, q: dict):
            from .. import bots
            m = re.match(r"^/bot/(dingtalk|feishu|wecom|api)/([^/]+)$", path)
            if not m:
                return self._json(404, {"error": "没有这个机器人地址"})
            kind = m.group(1)
            if method != "POST" and kind != "wecom":
                return self._json(405, {"error": "method"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1024 * 1024:
                return self._json(413, {"error": "请求太大"})
            raw = self.rfile.read(n) if n else b""
            try:
                root = P.root(P.project(unquote(m.group(2))))
                if kind == "wecom":
                    code, text = bots.wecom(root, method, {k: v[0] for k, v in q.items()}, raw)
                    return self._send(code, text.encode("utf-8"), "text/plain; charset=utf-8")
                code, obj = getattr(bots, kind)(root, self.headers, raw)
                return self._json(code, obj)
            except bots.BotError as e:
                return self._json(e.code, {"error": str(e)})
            except ApiError as e:
                return self._json(e.code, {"error": str(e)})
            except ValueError:
                return self._json(400, {"error": "请求格式不对"})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": type(e).__name__})

        def _alert(self, method: str, path: str, q: dict):
            from . import alerts
            m = re.match(r"^/hook/alert/([^/]+)$", path)
            if not m or method != "POST":
                return self._json(404 if not m else 405, {"error": "告警地址是 POST /hook/alert/<项目代号>"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 2 * 1024 * 1024:
                return self._json(413, {"error": "请求太大"})
            raw = self.rfile.read(n) if n else b""
            try:
                p = P.project(unquote(m.group(1)))
                c = alerts.check(P.data_dir, p["key"], self.headers, q)
                return self._json(200, alerts.receive(P, p, alerts.parse(raw), int(c.get("per_hour") or 20)))
            except alerts.AlertError as e:
                return self._json(e.code, {"error": str(e)})
            except ApiError as e:
                return self._json(e.code, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": type(e).__name__})

        def _dispatch(self, method: str):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            path = u.path
            if path.startswith("/bot/"):  # chat-platform callbacks: signed by the platform, not by our token
                return self._bot(method, path, q)
            if path.startswith("/hook/alert/"):  # monitoring webhooks: their own key, not our token
                return self._alert(method, path, q)
            if path.startswith("/capture/"):  # the bookmarklet on the client's page: its token can only add a capture
                return self._capture(method, path)
            if not self._local_host():
                return self._send(403, "只接受本机访问；对局域网开放请设置 TMH_TOKEN".encode("utf-8"), "text/plain; charset=utf-8")
            if path == "/login":
                return self._login(method, q)
            if path.startswith("/sign/"):  # the client's sign-off page: the one-time link is the credential, no account
                return self._sign(method, path)
            if path == "/logout":
                return self._send(303, b"", "text/plain", {"Location": "/login", "Set-Cookie": self._session_cookie("", 0)})
            if not path.startswith("/api/"):
                if method != "GET":
                    return self._json(405, {"error": "method"})
                if path in ("/", "/index.html"):
                    extra = {}
                    if token and (q.get("token") or [""])[0] == token:
                        extra["Set-Cookie"] = "tmh_token=%s; Path=/; HttpOnly; SameSite=Strict" % token
                    if not self._authorized(q):
                        if L.load_users(P.data_dir):
                            return self._send(303, b"", "text/plain", {"Location": "/login"})
                        return self._send(401, "需要访问令牌：在地址后加 ?token=…".encode("utf-8"), "text/plain; charset=utf-8")
                    return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8", extra)
                m = re.match(r"^/p/([^/]+)/efficiency$", path)
                if m:
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    try:
                        p = P.project(unquote(m.group(1)))
                        mt = P.metrics(p, (q.get("month") or [""])[0])
                    except ApiError as e:
                        return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    return self._send(200, md_html(report_md(mt), "AI 提效报告 %s %s" % (p["key"], mt["period"])).encode("utf-8"), "text/html; charset=utf-8")
                m = re.match(r"^/e/([A-Za-z0-9]+-\d+)(?:/f/([0-9a-f]{64}\.[a-z]+))?$", path)
                if m:  # a ticket's evidence package as one page (for the provider and the client's auditors)
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    from . import signoff
                    try:
                        if m.group(2):
                            signoff.owns(P.data_dir, m.group(1).upper(), m.group(2))
                            data, ctype = signoff.file_bytes(P.data_dir, m.group(2))
                            return self._send(200, data, ctype)
                        return self._send(200, signoff.package_page(P, m.group(1)).encode("utf-8"), "text/html; charset=utf-8")
                    except ApiError as e:
                        return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                m = re.match(r"^/p/([^/]+)/report/(.*)$", path)
                if m:
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    return self._report(unquote(m.group(1)), unquote(m.group(2)) or "index.html")
                return self._send(404, b"not found", "text/plain")
            if not self._authorized(q):
                return self._json(401, {"error": "需要访问令牌"})
            if method == "POST" and self.headers.get("X-TMH") != "1":
                return self._json(403, {"error": "缺少 X-TMH 请求头"})
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 5 * 1024 * 1024:
                    return self._json(413, {"error": "请求太大"})
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except ValueError:
                    return self._json(400, {"error": "请求不是 JSON"})
            user = self._who or unquote(self.headers.get("X-TMH-User") or "") or P.user or "我"
            for mth, rx, fn in ROUTES:
                if mth != method:
                    continue
                m = rx.match(path)
                if m:
                    try:
                        res = fn(P, Req(self, q, body, user[:40]), **{k: unquote(v) for k, v in m.groupdict().items()})
                        return self._json(200, res)
                    except ApiError as e:
                        return self._json(e.code, {"error": str(e)})
                    except FileNotFoundError as e:
                        return self._json(404, {"error": str(e)})
                    except Exception as e:  # noqa: BLE001 - report, keep serving
                        traceback.print_exc()
                        return self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})
            return self._json(404, {"error": "没有这个接口：%s %s" % (method, path)})

        def _capture(self, method: str, path: str):
            from . import pinpoint
            cors = {"Access-Control-Allow-Origin": "*"}
            m = re.match(r"^/capture/([A-Za-z0-9_\-]{20,64})$", path)
            if not m:
                return self._send(404, b'{"error":"no"}', "application/json", cors)
            if method != "POST":
                return self._send(405, b'{"error":"method"}', "application/json", cors)
            key = pinpoint.token_project(P.data_dir, m.group(1))
            n = int(self.headers.get("Content-Length") or 0)
            reply = lambda code, obj: self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cors)
            if not key:
                return reply(401, {"message": "这个书签已经失效，请到 webuddy 重新拖一个"})
            if n > 512 * 1024:
                return reply(413, {"message": "框得太大了，框小一点再试"})
            try:
                cap = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                pin = pinpoint.save(P, P.project(key), cap if isinstance(cap, dict) else {}, "页面框选", "bookmarklet")
            except ValueError:
                return reply(400, {"message": "发送的内容不对"})
            except ApiError as e:
                return reply(e.code, {"message": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return reply(500, {"message": "webuddy 出错了：%s" % type(e).__name__})
            n1, n2 = len(pin["found"]["layer1"]) + len(pin["found"]["layer2"]), len(pin["found"]["layer3"])
            return reply(200, {"id": pin["id"], "message": "已发送到 webuddy：找到 %d 个候选文件、%d 个后端入口" % (n1, n2)})

        def _sign(self, method: str, path: str):
            from . import signoff
            m = re.match(r"^/sign/([A-Za-z0-9_\-]{20,64})(?:/f/([0-9a-f]{64}\.[a-z]+))?$", path)
            html_t = "text/html; charset=utf-8"
            if not m:
                return self._send(404, "签收链接不对".encode("utf-8"), "text/plain; charset=utf-8")
            token, f = m.group(1), m.group(2)
            try:
                if method == "GET" and f:
                    signoff.owns(P.data_dir, signoff.link_of(P.data_dir, token)["key"], f)
                    data, ctype = signoff.file_bytes(P.data_dir, f)
                    return self._send(200, data, ctype)
                if method == "GET":
                    return self._send(200, signoff.sign_page(P, token).encode("utf-8"), html_t)
                if method != "POST" or f:
                    return self._send(405, b"method", "text/plain")
                n = int(self.headers.get("Content-Length") or 0)
                if n > 64 * 1024:
                    return self._send(413, b"too large", "text/plain")
                form = parse_qs(self.rfile.read(n).decode("utf-8", "replace") if n else "")
                g = lambda k: (form.get(k) or [""])[0]
                verdicts = {k[3:]: v[0] for k, v in form.items() if k.startswith("ac_")}
                try:
                    done = signoff.decide(P, token, g("action"), g("name"), verdicts, g("note"), self._client())
                except ApiError as e:
                    if e.code in (400,):
                        return self._send(400, signoff.sign_page(P, token, msg=str(e)).encode("utf-8"), html_t)
                    raise
                return self._send(200, signoff.sign_page(P, token, done=done).encode("utf-8"), html_t)
            except ApiError as e:
                return self._send(e.code, signoff.message_page(str(e)).encode("utf-8"), html_t)

        def _report(self, key: str, rel: str):
            p = P.store.project(key)
            if not p:
                return self._send(404, b"no project", "text/plain")
            base = (Path(p["root"]) / ".tmh" / "report").resolve()
            f = (base / rel).resolve()
            if base not in f.parents and f != base or not f.is_file():
                return self._send(404, "还没有业务全景报告，在项目目录运行 tmh report 生成".encode("utf-8"), "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._send(200, f.read_bytes(), ctype)

    return H


def _cookie(header: str, name: str) -> str:
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def serve(data_dir: Path, host: str = "127.0.0.1", port: int = 8790, user: str = "", project: Path | None = None,
          key: str = "", open_browser: bool = False, brand: str = "") -> int:
    P = Platform(data_dir, user, brand)
    token = os.environ.get("TMH_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        print("对外开放（--host %s）必须先设置环境变量 TMH_TOKEN 作为访问令牌" % host)
        return 2
    if project:
        project = Path(project).resolve()
        known = [p for p in P.store.projects() if Path(p["root"]) == project]
        if not known:
            k = key or re.sub(r"[^A-Za-z0-9]", "", project.name)[:6].upper() or "PRJ"
            if not k[0].isalpha():
                k = "P" + k[:5]
            name = project.name
            try:
                from .. import config as cfgmod
                name = cfgmod.load(project).get("project", {}).get("name") or name
            except Exception:  # noqa: BLE001
                pass
            P.store.add_project(k, name, str(project))
            print("已添加项目 %s（%s）" % (k, project))
    try:
        httpd = ThreadingHTTPServer((host, port), make_handler(P, token))
    except OSError as e:
        if e.errno not in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
            raise
        print("端口 %d 已被占用：平台可能已经在另一个窗口运行。关掉那个窗口再启动，或用 --port 换一个端口。" % port)
        return 1
    httpd.daemon_threads = True
    url = "http://%s:%d/" % ("127.0.0.1" if host in ("0.0.0.0", "::") else host, port)
    print("%s 已启动：%s%s" % (P.brand, url, "?token=<TMH_TOKEN>" if token else ""))
    print("数据目录：%s　按 Ctrl+C 停止" % P.data_dir)
    if open_browser:
        import webbrowser
        webbrowser.open(url + ("?token=" + token if token else ""))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0
