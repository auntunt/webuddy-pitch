"""提效指标：从工单事件、智能体运行、点数账本和 IDE 使用记录里算出来，并和导入的历史工单（基线）对比。

Two groups of tickets:
  基线 — imported from Jira/禅道 and already resolved there; their original created/resolved
         dates come from the tool (stored in tickets.external by import_issues).
  试点 — tickets that went through the platform (created here, or imported and then accepted here).

Every number says where it came from; nothing is estimated. There is no "person-days saved": the outside check is
external pull requests merged by maintainers who do not know us (upstream.py).
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from statistics import median

from .store import TYPES

DONE_WORDS = ("closed", "done", "resolved", "关闭", "已关闭", "已解决", "已完成", "完成", "已验收")
AI_SOURCES = [("run", "智能体运行"), ("chat", "助手对话"), ("prompt", "提示词"), ("mcp", "IDE（MCP 调用）")]


def ts_norm(v) -> str:
    """Tool timestamps (2024-03-01T10:22:33.000+0800, 2024-03-01 10:22:33, 2024-03-01T02:22:33Z) → local 'YYYY-MM-DD HH:MM:SS'."""
    v = (v or "").strip() if isinstance(v, str) else ""
    if not v or v.startswith("0000"):
        return ""
    s = v.replace("Z", "+00:00")
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)
    s = re.sub(r"\.\d+", "", s)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return v[:19].replace("T", " ") if re.match(r"\d{4}-\d\d-\d\d", v) else ""
    if d.tzinfo:
        d = d.astimezone().replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _t(s: str) -> float | None:
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError):
        return None


def _hours(a: str, b: str) -> float | None:
    x, y = _t(a), _t(b)
    if x is None or y is None or y < x:
        return None
    return (y - x) / 3600


def _stat(hs: list) -> dict:
    hs = [h for h in hs if h is not None]
    if not hs:
        return {"n": 0, "median_h": None, "avg_h": None, "p90_h": None}
    hs = sorted(hs)
    # the tail next to the median: a few tickets stuck for weeks is what a client remembers, and a mean hides it
    p90 = hs[min(len(hs) - 1, max(0, -(-len(hs) * 9 // 10) - 1))]
    return {"n": len(hs), "median_h": round(median(hs), 1), "avg_h": round(sum(hs) / len(hs), 1), "p90_h": round(p90, 1)}


def _in(ts: str, month: str) -> bool:
    return not month or (ts or "").startswith(month)


def dur(h) -> str:
    if h is None:
        return "—"
    if h < 1:
        return "%d 分钟" % max(1, round(h * 60))
    if h < 48:
        return "%.1f 小时" % h
    return "%.1f 天" % (h / 24)


def pct(a, b):
    return round(a * 100 / b, 1) if b else None


def _history_row(t: dict, evs: list, rs: list) -> dict | None:
    """An imported ticket that was closed in its own tool and never worked on here: a baseline sample."""
    x = t.get("external") or {}
    ext_done = x.get("resolved") or (x.get("updated") if (x.get("status") or "").lower() in DONE_WORDS else "")
    if x.get("key") and ext_done and not any(e["kind"] == "accept" for e in evs) and not rs:
        origin = x.get("created") or t["created"]
        return {"t": t, "origin": origin, "done": ext_done, "cycle": _hours(origin, ext_done), "who": x.get("assignee") or t["assignee"]}
    return None


def history(store, p: dict) -> list:
    """Every baseline sample of a project, oldest resolution first."""
    pid = p["id"]
    acc = {r["ticket_id"] for r in store.q("SELECT e.ticket_id FROM events e JOIN tickets t ON t.id=e.ticket_id "
                                           "WHERE t.project_id=? AND e.kind='accept'", (pid,))}
    ran = {r["ticket_id"] for r in store.q("SELECT DISTINCT ticket_id FROM runs WHERE project_id=? AND ticket_id IS NOT NULL", (pid,))}
    out = []
    for t in store.tickets(project_id=pid, limit=100000, svc="ops"):
        r = _history_row(t, [{"kind": "accept"}] if t["id"] in acc else [], [1] if t["id"] in ran else [])
        if r:
            out.append(r)
    return sorted(out, key=lambda r: r["done"])


def baseline_stats(base: list) -> dict:
    def by_type(rows):
        out = {}
        for code, label in TYPES:
            s = _stat([r["cycle"] for r in rows if r["t"]["type"] == code])
            if s["n"]:
                out[code] = dict(s, label=label)
        return out
    bdone = sorted(r["done"] for r in base)
    months_b = {}
    for r in base:
        months_b.setdefault(r["done"][:7], []).append(r["who"])
    tp_b = [len(v) / max(1, len({w for w in v if w})) for v in months_b.values()]
    return {"n": len(base), "range": [bdone[0][:10], bdone[-1][:10]] if bdone else None,
            "systems": sorted({(r["t"].get("external") or {}).get("system", "") for r in base} - {""}),
            "cycle": _stat([r["cycle"] for r in base]), "cycle_by_type": by_type(base),
            "per_person_month": round(sum(tp_b) / len(tp_b), 1) if tp_b else None}


HUMAN_KINDS = ("comment", "accept", "reject", "adopt", "discard", "link", "edit", "assign", "prompt", "evidence")
AGENT_AUTHORS = ("自动流转", "system", "告警", "平台", "")


HOLD_DAYS = 14  # an accepted change counts as done only if nothing sends it back within this many days


def _reopened(evs: list, accepted_at: str) -> bool:
    """Sent back within HOLD_DAYS of its first acceptance: rejected again, or moved out of 已闭环."""
    import json as _j
    for e in evs:
        if e["ts"] <= accepted_at or (_hours(accepted_at, e["ts"]) or 0) > HOLD_DAYS * 24:
            continue
        if e["kind"] == "reject":
            return True
        if e["kind"] == "status":
            try:
                d = _j.loads(e["data"] or "{}") if isinstance(e["data"], str) else (e["data"] or {})
            except ValueError:
                d = {}
            if d.get("from") == "closed":
                return True
    return False


def compute(store, p: dict, usage_rows: list, month: str = "", kb: dict | None = None, sealed: dict | None = None,
            books: dict | None = None, packages: dict | None = None) -> dict:
    pid = p["id"]
    tickets = store.tickets(project_id=pid, limit=100000, svc="ops")  # 提效报告 is the 运维 service's; reform pieces are reported on their plans
    ids = [t["id"] for t in tickets]
    by_id = {t["id"]: t for t in tickets}
    ev = {}
    if ids:
        for e in store.q("SELECT e.ticket_id, e.ts, e.kind, e.data FROM events e JOIN tickets t ON t.id=e.ticket_id "
                         "WHERE t.project_id=? AND e.kind IN ('accept','reject','prompt','status') ORDER BY e.id", (pid,)):
            ev.setdefault(e["ticket_id"], []).append(e)
    runs = {}
    for r in store.q("SELECT ticket_id, mode, status, ended FROM runs WHERE project_id=? AND ticket_id IS NOT NULL", (pid,)):
        runs.setdefault(r["ticket_id"], []).append(r)
    chatted = {r["ticket_id"] for r in store.q("SELECT DISTINCT ticket_id FROM chats WHERE project_id=? AND ticket_id IS NOT NULL AND role='user'", (pid,))}
    chatted |= {r["ticket_id"] for r in store.q("SELECT DISTINCT s.ticket_id FROM sessions s JOIN chats c ON c.session_id=s.id "
                                                 "WHERE s.project_id=? AND s.ticket_id IS NOT NULL AND c.role='user'", (pid,))}
    key_id = {t["key"]: t["id"] for t in tickets}
    ide = [u for u in usage_rows if not u.get("run")]
    mcp_by_ticket = {}
    for u in ide:
        tid = key_id.get((u.get("ticket") or "").upper())
        if tid:
            mcp_by_ticket.setdefault(tid, []).append(u)

    base, pilot = [], []
    for t in tickets:
        x = t.get("external") or {}
        evs = ev.get(t["id"], [])
        accepted = [e["ts"] for e in evs if e["kind"] == "accept"]
        origin = x.get("created") or t["created"]
        h = _history_row(t, evs, runs.get(t["id"], []))
        if h:
            base.append(h)
            continue
        rs = runs.get(t["id"], [])
        loc = sorted(r["ended"] for r in rs if r["mode"] in ("analyze", "plan") and r["status"] == "done" and r["ended"])
        src = set()
        if any(r["mode"] != "ask" and r["status"] != "cancelled" for r in rs):
            src.add("run")
        if t["id"] in chatted or any(r["mode"] == "ask" for r in rs):
            src.add("chat")
        if any(e["kind"] == "prompt" for e in evs):
            src.add("prompt")
        if t["id"] in mcp_by_ticket:
            src.add("mcp")
        pilot.append({"t": t, "origin": origin, "reopened": _reopened(evs, accepted[0]) if accepted else False, "done": accepted[0] if accepted else "", "cycle": _hours(origin, accepted[0]) if accepted else None,
                      "locate_at": loc[0] if loc else "", "locate": _hours(origin, loc[0]) if loc else None, "src": src,
                      "reviews": [e for e in evs if e["kind"] in ("accept", "reject")], "who": t["assignee"]})

    def by_type(rows):
        out = {}
        for code, label in TYPES:
            s = _stat([r["cycle"] for r in rows if r["t"]["type"] == code])
            if s["n"]:
                out[code] = dict(s, label=label)
        return out

    # ---- baseline: the whole imported history (a candidate); comparisons use only the sealed one
    baseline = baseline_stats(sorted(base, key=lambda r: r["done"]))
    good = sealed if sealed and not sealed.get("broken") else None
    sb = good["stats"] if good else None
    gate = {"sealed": bool(good), "reason": "" if good else (
        "基线文件被改过（%s），按没有基线处理" % sealed["broken"] if sealed and sealed.get("broken") else
        "还没有封存基线：报告只出本期实测，不出对比数")}

    # ---- pilot (this period)
    closed = [r for r in pilot if r["done"] and _in(r["done"], month)]
    located = [r for r in pilot if r["locate_at"] and _in(r["locate_at"], month)]
    reviewed, rejected, reworks = set(), set(), 0
    for r in pilot:
        for e in r["reviews"]:
            if _in(e["ts"], month):
                reviewed.add(r["t"]["id"])
                if e["kind"] == "reject":
                    rejected.add(r["t"]["id"])
                    reworks += 1
    # speed next to stability: of the tickets accepted this period whose 14 days are up, how many came back
    now_ = time.strftime("%Y-%m-%d %H:%M:%S")
    matured = [r for r in closed if (_hours(r["done"], now_) or 0) >= HOLD_DAYS * 24]
    back = [r for r in matured if r["reopened"]]
    handled = [r for r in pilot if _in(r["origin"], month) or (r["done"] and _in(r["done"], month))]
    with_ai = [r for r in handled if r["src"]]
    src_n = {k: sum(1 for r in handled if k in r["src"]) for k, _ in AI_SOURCES}
    pts = store.q("SELECT ticket_id, ts, delta FROM points WHERE project_id=? AND delta<0", (pid,))
    spent = [x for x in pts if _in(x["ts"], month)]
    per_t = {}
    for x in spent:
        if x["ticket_id"]:
            per_t[x["ticket_id"]] = per_t.get(x["ticket_id"], 0) - x["delta"]
    people = {r["who"] for r in closed if r["who"]}
    ide_p = [u for u in ide if _in(u.get("ts", ""), month)]
    clients = {}
    for u in ide_p:
        clients[u.get("client") or "未知客户端"] = clients.get(u.get("client") or "未知客户端", 0) + 1
    tools = {}
    for u in ide_p:
        tools[u.get("tool", "")] = tools.get(u.get("tool", ""), 0) + 1
    pilot_out = {
        "n": len(pilot), "handled": len(handled), "closed": len(closed),
        "cycle": _stat([r["cycle"] for r in closed]), "cycle_by_type": by_type(closed),
        "locate": _stat([r["locate"] for r in located]),
        "reopen": {"matured": len(matured), "reopened": len(back), "rate": pct(len(back), len(matured)), "pending": len(closed) - len(matured),
                   "keys": [r["t"]["key"] for r in back]},
        "reject": {"reviewed": len(reviewed), "rejected": len(rejected), "rate": pct(len(rejected), len(reviewed)), "reworks": reworks},
        "ai": {"tickets": len(with_ai), "total": len(handled), "rate": pct(len(with_ai), len(handled)),
               "by_source": [{"key": k, "label": lb, "n": src_n[k]} for k, lb in AI_SOURCES]},
        "cost": {"total": sum(-x["delta"] for x in spent), "tickets": len(per_t),
                 "per_ticket": round(sum(per_t.values()) / len(per_t), 1) if per_t else None,
                 "unattributed": sum(-x["delta"] for x in spent if not x["ticket_id"])},
        "throughput": {"people": len(people), "closed": len(closed), "per_person": round(len(closed) / len(people), 1) if people else None},
        "ide": {"calls": len(ide_p), "tickets": len({u.get("ticket") for u in ide_p if (u.get("ticket") or "").upper() in key_id}),
                "unlinked": sum(1 for u in ide_p if (u.get("ticket") or "").upper() not in key_id),
                "clients": sorted(clients.items(), key=lambda kv: -kv[1]), "tools": sorted(tools.items(), key=lambda kv: -kv[1])[:8]},
    }

    # ---- comparison (only against a sealed baseline)
    bc, pc = (sb["cycle"]["median_h"] if sb else None), pilot_out["cycle"]["median_h"]
    bpm = sb["per_person_month"] if sb else None
    NB = "未封存"
    compare = [
        {"key": "cycle", "label": "工单周期（中位数）", "baseline": dur(bc) if sb else NB,
         "pilot": dur(pc) + (" · P90 %s" % dur(pilot_out["cycle"]["p90_h"]) if pilot_out["cycle"]["n"] >= 5 else ""), "change": pct(pc - bc, bc) if bc and pc is not None else None,
         "better": "down", "basis": "实测"},
        {"key": "locate", "label": "首次定位耗时（中位数）", "baseline": "外部系统无记录", "pilot": dur(pilot_out["locate"]["median_h"]), "change": None,
         "better": "down", "basis": "实测"},
        {"key": "reject", "label": "验收退回率", "baseline": "外部系统无记录",
         "pilot": "—" if pilot_out["reject"]["rate"] is None else "%s%%" % pilot_out["reject"]["rate"], "change": None, "better": "down", "basis": "实测"},
        {"key": "reopen", "label": "验收后 %d 天内返工率" % HOLD_DAYS, "baseline": "外部系统无记录",
         "pilot": "—" if pilot_out["reopen"]["rate"] is None else "%s%%" % pilot_out["reopen"]["rate"], "change": None, "better": "down", "basis": "实测"},
        _lesson_row(store, p),
        {"key": "ai", "label": "AI 参与率", "baseline": "0%（导入前无记录）", "pilot": "—" if pilot_out["ai"]["rate"] is None else "%s%%" % pilot_out["ai"]["rate"],
         "change": None, "better": "up", "basis": "实测"},
        {"key": "cost", "label": "每单 AI 成本", "baseline": "—", "pilot": "—" if pilot_out["cost"]["per_ticket"] is None else "%s 点" % pilot_out["cost"]["per_ticket"],
         "change": None, "better": "down", "basis": "实测"},
        {"key": "throughput", "label": "人均月关闭工单", "baseline": (NB if not sb else "—" if bpm is None else "%s 张" % bpm),
         "pilot": "—" if pilot_out["throughput"]["per_person"] is None else "%s 张" % pilot_out["throughput"]["per_person"],
         "change": pct(pilot_out["throughput"]["per_person"] - bpm, bpm)
         if bpm and pilot_out["throughput"]["per_person"] is not None and month else None, "better": "up", "basis": "实测"},
    ]

    # ---- ledger: one row per ticket handled in the period
    bk = books or {"yuan_per_point": 1.0, "paid_yuan_per_point": None, "yuan_default": True}
    pk = packages or {}
    acts = {}
    for e in store.q("SELECT e.ticket_id, e.author, e.kind, e.ts FROM events e JOIN tickets t ON t.id=e.ticket_id WHERE t.project_id=? AND e.kind IN (%s)"
                     % ",".join("?" * len(HUMAN_KINDS)), (pid,) + HUMAN_KINDS):
        if e["author"] not in AGENT_AUTHORS and _in(e["ts"], month):
            acts[e["ticket_id"]] = acts.get(e["ticket_id"], 0) + 1
    yuan = lambda pts, rate: None if rate is None else round(pts * rate, 2)
    rows = []
    for r in sorted(handled, key=lambda r: r["t"]["num"]):
        t = r["t"]
        pts = per_t.get(t["id"], 0)
        e = pk.get(t["key"]) or {}
        rows.append({"key": t["key"], "title": t["title"], "type": t["type"], "status": t["status"], "created": r["origin"], "done": r["done"],
                     "cycle_h": None if r["cycle"] is None else round(r["cycle"], 1), "locate_h": None if r["locate"] is None else round(r["locate"], 1),
                     "reworks": sum(1 for x in r["reviews"] if x["kind"] == "reject" and _in(x["ts"], month)),
                     "ai_runs": sum(1 for x in runs.get(t["id"], []) if x["mode"] != "ask" and x["status"] != "cancelled"),
                     "points": pts, "list_yuan": yuan(pts, bk["yuan_per_point"]), "paid_yuan": yuan(pts, bk["paid_yuan_per_point"]),
                     "human_actions": acts.get(t["id"], 0),
                     "evidence": e.get("label") or "未生成", "evidence_status": e.get("status") or "none", "signer": e.get("signer", ""),
                     "signed_via": e.get("via", ""), "evidence_hash": e.get("hash", "")})
    tot_pts = sum(x["points"] for x in rows)
    ledger = {"rows": rows, "settings": bk,
              "totals": {"tickets": len(rows), "closed": sum(1 for x in rows if x["done"] and _in(x["done"], month)),
                         "points": tot_pts, "list_yuan": yuan(tot_pts, bk["yuan_per_point"]), "paid_yuan": yuan(tot_pts, bk["paid_yuan_per_point"]),
                         "reworks": sum(x["reworks"] for x in rows), "human_actions": sum(x["human_actions"] for x in rows),
                         "packed": sum(1 for x in rows if x["evidence_status"] != "none"),
                         "signed": sum(1 for x in rows if x["evidence_status"] == "signed"),
                         "client_signed": sum(1 for x in rows if x["evidence_status"] == "signed" and x["signed_via"] == "签收链接")},
              "method": {"list_yuan": "点数 × 标价（每点 %s 元%s）" % (bk["yuan_per_point"], "，演示默认值，可在 pricing.json 里改" if bk.get("yuan_default") else ""),
                         "paid_yuan": "点数 × 实付单价" + ("（每点 %s 元）" % bk["paid_yuan_per_point"] if bk["paid_yuan_per_point"] is not None else "（未录入）"),
                         "human_actions": "人工动作次数：评论、验收、采纳、补证据等，智能体和自动流转不算"}}

    # ---- last six months of the pilot
    trend = []
    cur = month or time.strftime("%Y-%m")
    y, m = int(cur[:4]), int(cur[5:7])
    for i in range(5, -1, -1):
        yy, mm = y, m - i
        while mm <= 0:
            yy, mm = yy - 1, mm + 12
        k = "%04d-%02d" % (yy, mm)
        c = [r["cycle"] for r in pilot if r["done"].startswith(k)]
        h = [r for r in pilot if r["origin"].startswith(k) or r["done"].startswith(k)]
        trend.append({"month": k, "closed": len(c), "cycle_median_h": _stat(c)["median_h"],
                      "ai_rate": pct(sum(1 for r in h if r["src"]), len(h))})

    cov = ((kb or {}).get("coverage") or {}).get("total") or {}
    written = cov.get("待确认", 0) + cov.get("已确认", 0)
    return {"project": {"key": p["key"], "name": p["name"]}, "month": month,
            "period": ("%s 年 %d 月" % (month[:4], int(month[5:7]))) if month else "全部时间",
            "generated": time.strftime("%Y-%m-%d %H:%M"),
            "baseline": baseline, "sealed": sealed, "gate": gate, "ledger": ledger,
            "pilot": pilot_out, "compare": compare, "trend": trend,
            "kb": {"built": bool((kb or {}).get("built")), "written": written,
                   "scope": written + cov.get("未分析", 0) + cov.get("过期", 0), "stale": cov.get("过期", 0),
                   "flows": (kb or {}).get("flows", 0), "flows_with_tables": (kb or {}).get("flows_with_tables", 0)}}


# ---------------------------------------------------------------- report

MIN_LESSON_N = 5


def _lesson_row(store, p: dict) -> dict:
    """The experience cards against tickets like them that went without (the comparison group), on first-time acceptance."""
    from . import learn
    im = learn.impact(store.path.parent, p["key"])
    c, h = im["carried"], im["held"]
    show = lambda x: "—（%d 张，不足 %d）" % (x["n"], im["min_n"]) if x["rate"] is None else "%s%%（%d 张）" % (round(x["rate"] * 100), x["n"])
    return {"key": "lessons", "label": "带经验的工单一次验收通过率", "baseline": show(h) + " 对照组" if im["holdout"] or h["n"] else "未开对照组",
            "pilot": show(c), "change": None, "better": "up", "basis": "实测"}


def report_md(m: dict) -> str:
    cand, p, k = m["baseline"], m["pilot"], m["kb"]
    gate, sealed = m.get("gate") or {"sealed": False, "reason": ""}, m.get("sealed") or {}
    b = sealed["stats"] if gate["sealed"] else dict(cand, n=0, cycle_by_type={})
    L = ["# AI 提效报告 · %s · %s" % (m["project"]["name"], m["period"]), "",
         "项目 %s · 生成于 %s · 数据来源：平台工单事件、智能体运行记录、点数账本、IDE 调用记录（.tmh/usage.jsonl）" % (m["project"]["key"], m["generated"]), ""]
    L += ["## 一、结论", ""]
    lines = []
    if b["n"] and p["cycle"]["n"]:
        ch = m["compare"][0]["change"]
        lines.append("工单周期中位数从封存基线的 %s 变为 %s%s。" % (dur(b["cycle"]["median_h"]), dur(p["cycle"]["median_h"]),
                                                       "（%s%.1f%%）" % ("+" if ch > 0 else "", ch) if ch is not None else ""))
    elif not gate["sealed"]:
        lines.append(gate["reason"] + "。" + ("已导入 %d 张历史工单，可在提效报告页选定窗口后封存。" % cand["n"] if cand["n"]
                                               else "先导入历史工单，再封存基线，方法见文末“口径”。"))
    if p["ai"]["rate"] is not None:
        lines.append("本期经手 %d 张工单，其中 %d 张有 AI 参与（%s%%）。" % (p["ai"]["total"], p["ai"]["tickets"], p["ai"]["rate"]))
    if p["locate"]["n"]:
        lines.append("首次定位耗时中位数 %s（%d 张）。" % (dur(p["locate"]["median_h"]), p["locate"]["n"]))
    if p["reject"]["reviewed"]:
        lines.append("验收 %d 张，退回 %d 张，退回率 %s%%。" % (p["reject"]["reviewed"], p["reject"]["rejected"], p["reject"]["rate"]))
    if p["cycle"]["n"]:
        lines.append("工单周期中位数 %s，最慢的一成在 %s 以上。" % (dur(p["cycle"]["median_h"]), dur(p["cycle"]["p90_h"])))
    if p["reopen"]["matured"]:
        lines.append("验收满 %d 天的 %d 张里，%d 张被退回或重开（%s%%）%s。" % (HOLD_DAYS, p["reopen"]["matured"], p["reopen"]["reopened"], p["reopen"]["rate"],
                                                         "：" + "、".join(p["reopen"]["keys"][:8]) if p["reopen"]["keys"] else ""))
    elif p["reopen"]["pending"]:
        lines.append("本期验收的 %d 张还不满 %d 天，返工率下期再出。" % (p["reopen"]["pending"], HOLD_DAYS))
    u = m.get("upstream") or {}
    if u.get("submitted"):
        lines.append("向开源项目提交 PR %d 个，已被维护者合并 %d 个%s。" % (u["submitted"], u["merged"],
                                                          "（合并率 %s%%）" % u["merge_rate"] if u.get("merge_rate") is not None else ""))
    L += ["- " + x for x in lines or ["本期还没有可统计的数据。"]] + [""]

    L += ["## 二、基线与本期对比（实测）", "", "| 指标 | 基线 | 本期 | 变化 |", "|---|---|---|---|"]
    for c in m["compare"]:
        L.append("| %s | %s | %s | %s |" % (c["label"], c["baseline"], c["pilot"],
                                             "—" if c["change"] is None else "%s%.1f%%" % ("+" if c["change"] > 0 else "", c["change"])))
    if gate["sealed"]:
        L += ["", "基线：%d 张从 %s 导入、并已在原系统关闭的工单，封存窗口 %s 至 %s，用原系统的创建和解决时间。%s 由 %s 封存，哈希 `%s`，封存后不可改。"
              % (b["n"], "、".join(b["systems"]) or "外部系统", sealed["window"][0], sealed["window"][1], sealed["sealed_at"], sealed["sealed_by"],
                 sealed["hash"][:16]), ""]
    else:
        L += ["", "基线：%s。对比列在封存基线以后才出。" % gate["reason"], ""]

    L += ["## 三、工单周期（按类型，实测）", "", "| 类型 | 基线中位数 | 基线样本 | 本期中位数 | 本期样本 |", "|---|---|---|---|---|"]
    for code, label in TYPES:
        x, y = b["cycle_by_type"].get(code), p["cycle_by_type"].get(code)
        if x or y:
            L.append("| %s | %s | %s | %s | %s |" % (label, dur(x and x["median_h"]), x["n"] if x else 0, dur(y and y["median_h"]), y["n"] if y else 0))
    L += ["", "周期从工单创建算到人工验收通过；导入后又在平台上处理的工单，创建时间取原系统的时间。", ""]

    L += ["## 四、AI 参与（实测）", "", "| 参与方式 | 工单数 |", "|---|---|"]
    L += ["| %s | %d |" % (s["label"], s["n"]) for s in p["ai"]["by_source"]]
    ide = p["ide"]
    L += ["", "IDE 里共 %d 次 MCP 调用，关联到 %d 张工单，%d 次没有关联工单。" % (ide["calls"], ide["tickets"], ide["unlinked"])]
    if ide["clients"]:
        L.append("客户端：" + "，".join("%s %d 次" % tuple(kv) for kv in ide["clients"]) + "。")
    if ide["tools"]:
        L.append("常用工具：" + "，".join("%s %d 次" % tuple(kv) for kv in ide["tools"]) + "。")
    L.append("")

    L += ["## 五、成本（实测）", "", "本期消耗 %d 点，涉及 %d 张工单，平均每单 %s 点；另有 %d 点不归属具体工单（知识库构建、项目咨询等）。"
          % (p["cost"]["total"], p["cost"]["tickets"], "—" if p["cost"]["per_ticket"] is None else p["cost"]["per_ticket"], p["cost"]["unattributed"]), ""]
    lg = m.get("ledger")
    if lg:
        bk, tt = lg["settings"], lg["totals"]
        ycost = lambda pts, rate: "—" if rate is None else "%.2f 元" % (pts * rate)
        L += ["| 口径 | 金额 |", "|---|---|",
              "| 标价折人民币 | %s |" % ycost(p["cost"]["total"], bk["yuan_per_point"]),
              "| 实付 | %s |" % ("未录入" if bk["paid_yuan_per_point"] is None else ycost(p["cost"]["total"], bk["paid_yuan_per_point"])), ""]
        L += ["## 账本（每单）", "",
              "本期经手 %d 张：关闭 %d 张，生成证据包 %d 张，已签收 %d 张（其中甲方通过签收链接签 %d 张），返工 %d 次，人工动作 %d 次。"
              % (tt["tickets"], tt["closed"], tt["packed"], tt["signed"], tt["client_signed"], tt["reworks"], tt["human_actions"]), "",
              "| 工单 | 周期 | 首次定位 | 返工 | AI 运行 | 点数 | 标价（元） | 实付（元） | 人工动作 | 证据包 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for x in lg["rows"][:60]:
            L.append("| %s %s | %s | %s | %d | %d | %d | %s | %s | %d | %s |" % (
                x["key"], x["title"][:24].replace("|", "/"), dur(x["cycle_h"]), dur(x["locate_h"]), x["reworks"], x["ai_runs"], x["points"],
                "—" if x["list_yuan"] is None else "%.2f" % x["list_yuan"], "—" if x["paid_yuan"] is None else "%.2f" % x["paid_yuan"], x["human_actions"],
                x["evidence"] + ("（%s）" % x["signer"] if x["signer"] else "")))
        if len(lg["rows"]) > 60:
            L.append("| …… 另有 %d 张，见平台账本 | | | | | | | | | |" % (len(lg["rows"]) - 60))
        L += ["", "每单的证据包在平台 `/e/<工单号>` 打开，签收记录和哈希都在里面。", ""]
        if u.get("submitted"):
            f1 = lambda v, unit="": "—" if v is None else "%s%s" % (v, unit)
            L += ["## 外部 PR（第三方验收）", "",
                  "| 指标 | 数值 |", "|---|---|",
                  "| 提交 | %d 个（在途 %d，已合并 %d，已关闭 %d） |" % (u["submitted"], u["open"], u["merged"], u["closed"]),
                  "| 合并率（已有结局的） | %s |" % f1(u["merge_rate"], "%"),
                  "| 合并前平均评审轮次 | %s |" % f1(u["rounds_avg"]),
                  "| 提交到合并（中位数） | %s |" % f1(u["hours_to_merge_median"], " 小时"),
                  "| 维护者合并前又加了提交 | %d 个 |" % u["maintainer_edited"],
                  "| 每个合并 PR 的 AI 点数 | %s |" % f1(u["points_per_merged"]), ""]
            if u["reasons"]:
                L += ["关闭原因：" + "，".join("%s %d 个" % (r["label"], r["n"]) for r in u["reasons"]) + "。", ""]
            L += ["| 工单 | PR | 状态 | 评审轮次 | 改动行数 |", "|---|---|---|---|---|"]
            L += ["| %s | %s#%s | %s | %s | %d |" % (r["key"], r["repo"], r["pr"], r["label"], r["summary"].get("rounds", "—"), r["lines"]) for r in u["rows"][:40]]
            L.append("")
        signed = [x for x in lg["rows"] if x["evidence_status"] == "signed"]
        L += ["## 验收证据抽样", ""]
        if signed:
            import random
            pick = sorted(random.Random("%s-%s" % (m["project"]["key"], m["month"] or "all")).sample(signed, min(5, len(signed))), key=lambda x: x["key"])
            L += ["从本期已签收的 %d 张里固定种子随机抽 %d 张（同一报告重复生成抽到的一样）：" % (len(signed), len(pick)), "",
                  "| 工单 | 签收人 | 方式 | 证据包哈希 |", "|---|---|---|---|"]
            L += ["| %s %s | %s | %s | `%s` |" % (x["key"], x["title"][:24].replace("|", "/"), x["signer"], x["signed_via"], x["evidence_hash"][:16]) for x in pick]
        else:
            L.append("本期还没有签收的证据包。")
        L.append("")

    L += ["## 六、知识库", ""]
    if k["built"]:
        L.append("业务理解页已写 %d / %d 页，过期 %d 页。%d 条业务流中 %d 条能追到表。" % (k["written"], k["scope"], k["stale"], k["flows"], k["flows_with_tables"]))
    else:
        L.append("项目尚未构建知识库。")
    L.append("")

    q = m.get("qa") or {}
    if not (q.get("triage") or q.get("answered") or q.get("waiting")):
        L += ["## 七、少找人（实测）", "", "本期没有需求预判和业务方问答记录。", ""]
    else:
        f = lambda x: "—" if x is None else "%.0f%%" % (x * 100)
        L += ["## 七、少找人（实测）", "",
              "| 指标 | 数值 |", "|---|---|",
              "| 需求预判次数 | %d |" % q["triage"],
              "| 不用找人直接答 | %d（%s） |" % (q["auto"], f(q["auto_rate"])),
              "| 直接答后被人改判 | %d |" % q["overruled"],
              "| 采纳率（直接答且未被改判） | %s |" % f(q["adopted_rate"]),
              "| 转人工 | %d |" % q["handoff"],
              "| 业务方答复平均等待 | %s |" % ("—" if q["answer_wait_hours"] is None else "%s 小时（%d 个）" % (q["answer_wait_hours"], q["answered"])),
              "| 还在等业务方答复 | %d |" % q["waiting"], ""]
        if q.get("channels"):
            L += ["来源：" + "，".join("%s %d 次" % kv for kv in sorted(q["channels"].items(), key=lambda x: -x[1])) + "。", ""]
    L += ["## 八、近六个月走势（实测）", "", "| 月份 | 关闭工单 | 周期中位数 | AI 参与率 |", "|---|---|---|---|"]
    L += ["| %s | %d | %s | %s |" % (t["month"], t["closed"], dur(t["cycle_median_h"]), "—" if t["ai_rate"] is None else "%s%%" % t["ai_rate"]) for t in m["trend"]]
    L += ["", "## 九、口径", "",
          "- **实测**：直接从平台记录计算，可以逐条追溯到工单事件、运行记录和点数流水。",
          "- 本报告不估算“节省人天”。外部验证看第三方：向开源项目提交的 PR 是否被维护者合并、评审几轮、维护者是否在合并前再改，全部可在 GitHub 上复查。",
          "- 基线来自 Jira 或禅道导入（平台“导入工单”或 `tmh issue` 适配器），只统计在原系统已关闭、且没有在平台上再处理的工单。"
          "基线在开工前按窗口封存一次（口径、样本清单、哈希写死），之后不能改；没有封存基线时不出对比数。",
          "- 账本：%s；%s；%s。" % ((m.get("ledger") or {}).get("method", {}).get("list_yuan", "点数 × 标价"),
                                       (m.get("ledger") or {}).get("method", {}).get("paid_yuan", "实付另录"),
                                       (m.get("ledger") or {}).get("method", {}).get("human_actions", "人工动作次数")),
          "- 证据包：工单转“待验证”时自动打包验收标准、方案、改动、构建测试、范围和入口路径检查结果；之后的补充、复核、签收都追加在后面，每条带前一条的哈希，改任何一条都会对不上。",
          "- 首次定位耗时：从工单创建到第一次“分析定位”或“修改方案”运行完成。",
          "- 验收退回率：本期有验收记录的工单中，至少被退回一次的比例。",
          "- 周期：从工单创建（导入的取原系统创建时间）到第一次验收通过。报中位数和 P90（最慢一成的起点），不报平均数：少数卡住几周的单会把平均数拉得不像任何一张单。",
          "- 验收后 %d 天内返工率：本期验收通过、且已满 %d 天的工单中，%d 天内又被退回或从“已闭环”改回其他状态的比例。不满 %d 天的不进分母，下期再算。只报速度不报稳定性，提速可能只是把问题推到了验收之后。" % ((HOLD_DAYS,) * 4),
          "- 带经验的工单一次验收通过率：本期第一次验收就通过的比例，只看每张工单的第一次验收。“基线”一列在这一行是对照组：有相近经验、但按固定比例故意不放经验的工单，两组问题相近，差别才算经验的作用。每组不足 %d 张不给比例。" % MIN_LESSON_N,
          "- 少找人：每次需求预判（命令行、网页、群机器人、开放 API）都记一条；结论不是“需要人判断”的算直接答；有人用“改判”标记不对的，从采纳率里扣掉。",
          "- AI 参与：工单有智能体运行、助手对话、提示词使用，或 IDE 里有带该工单号的 MCP 调用（含开发者在平台上“写入项目”后的调用）。",
          ""]
    return "\n".join(L)


def md_html(md: str, title: str) -> str:
    """Just enough Markdown (headings, tables, bullets, bold) for a printable standalone page."""
    out, rows, ul = [], [], False

    def inline(s):
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return re.sub(r"`(.+?)`", r"<code>\1</code>", s)

    def flush():
        nonlocal rows, ul
        if rows:
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                "".join("<th>%s</th>" % inline(c) for c in rows[0]),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in rows[2:])))
            rows = []
        if ul:
            out.append("</ul>")
            ul = False

    for line in md.splitlines():
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip("|").split("|")])
            continue
        if line.startswith("- "):
            if rows:
                flush()
            if not ul:
                out.append("<ul>")
                ul = True
            out.append("<li>%s</li>" % inline(line[2:]))
            continue
        flush()
        if line.startswith("# "):
            out.append("<h1>%s</h1>" % inline(line[2:]))
        elif line.startswith("## "):
            out.append("<h2>%s</h2>" % inline(line[3:]))
        elif line.strip():
            out.append("<p>%s</p>" % inline(line))
    flush()
    css = ("body{font:15px/1.7 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#1d2433;max-width:860px;margin:32px auto;padding:0 20px}"
           "h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px;padding-top:12px;border-top:1px solid #e3e7ef}"
           "p{margin:6px 0;color:#333}table{border-collapse:collapse;width:100%;margin:8px 0;font-variant-numeric:tabular-nums}"
           "th,td{border:1px solid #dfe3eb;padding:6px 10px;text-align:left}th{background:#f4f6fa;font-weight:600}"
           "code{background:#f1f3f7;padding:0 4px;border-radius:3px}ul{padding-left:20px}"
           "@media print{body{margin:0}h2{break-after:avoid}table{break-inside:avoid}}")
    return "<!doctype html><html lang=zh><meta charset=utf-8><title>%s</title><style>%s</style>%s</html>" % (html.escape(title), css, "".join(out))
