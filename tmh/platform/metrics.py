"""提效指标：从工单事件、智能体运行、点数账本和 IDE 使用记录里算出来，并和导入的历史工单（基线）对比。

Two groups of tickets:
  基线 — imported from Jira/禅道 and already resolved there; their original created/resolved
         dates come from the tool (stored in tickets.external by import_issues).
  试点 — tickets that went through the platform (created here, or imported and then accepted here).

Every number says where it came from. Only 节省人天 is derived, and it is marked 估算.
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
        return {"n": 0, "median_h": None, "avg_h": None}
    return {"n": len(hs), "median_h": round(median(hs), 1), "avg_h": round(sum(hs) / len(hs), 1)}


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


def compute(store, p: dict, usage_rows: list, month: str = "", kb: dict | None = None) -> dict:
    pid = p["id"]
    tickets = store.tickets(project_id=pid, limit=100000, svc="ops")  # 提效报告 is the 运维 service's; reform pieces are reported on their plans
    ids = [t["id"] for t in tickets]
    by_id = {t["id"]: t for t in tickets}
    ev = {}
    if ids:
        for e in store.q("SELECT e.ticket_id, e.ts, e.kind, e.data FROM events e JOIN tickets t ON t.id=e.ticket_id "
                         "WHERE t.project_id=? AND e.kind IN ('accept','reject','prompt') ORDER BY e.id", (pid,)):
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
        ext_done = x.get("resolved") or (x.get("updated") if (x.get("status") or "").lower() in DONE_WORDS else "")
        origin = x.get("created") or t["created"]
        if x.get("key") and ext_done and not accepted and not runs.get(t["id"]):
            base.append({"t": t, "origin": origin, "done": ext_done, "cycle": _hours(origin, ext_done), "who": x.get("assignee") or t["assignee"]})
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
        pilot.append({"t": t, "origin": origin, "done": accepted[0] if accepted else "", "cycle": _hours(origin, accepted[0]) if accepted else None,
                      "locate_at": loc[0] if loc else "", "locate": _hours(origin, loc[0]) if loc else None, "src": src,
                      "reviews": [e for e in evs if e["kind"] in ("accept", "reject")], "who": t["assignee"]})

    def by_type(rows):
        out = {}
        for code, label in TYPES:
            s = _stat([r["cycle"] for r in rows if r["t"]["type"] == code])
            if s["n"]:
                out[code] = dict(s, label=label)
        return out

    # ---- baseline (whole imported history)
    bdone = sorted(r["done"] for r in base)
    months_b = {}
    for r in base:
        months_b.setdefault(r["done"][:7], []).append(r["who"])
    tp_b = [len(v) / max(1, len({w for w in v if w})) for v in months_b.values()]
    baseline = {"n": len(base), "range": [bdone[0][:10], bdone[-1][:10]] if bdone else None,
                "systems": sorted({(r["t"].get("external") or {}).get("system", "") for r in base} - {""}),
                "cycle": _stat([r["cycle"] for r in base]), "cycle_by_type": by_type(base),
                "per_person_month": round(sum(tp_b) / len(tp_b), 1) if tp_b else None}

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

    # ---- comparison and the one estimate
    bc, pc = baseline["cycle"]["median_h"], pilot_out["cycle"]["median_h"]
    compare = [
        {"key": "cycle", "label": "工单周期（中位数）", "baseline": dur(bc), "pilot": dur(pc), "change": pct(pc - bc, bc) if bc and pc is not None else None,
         "better": "down", "basis": "实测"},
        {"key": "locate", "label": "首次定位耗时（中位数）", "baseline": "外部系统无记录", "pilot": dur(pilot_out["locate"]["median_h"]), "change": None,
         "better": "down", "basis": "实测"},
        {"key": "reject", "label": "验收退回率", "baseline": "外部系统无记录",
         "pilot": "—" if pilot_out["reject"]["rate"] is None else "%s%%" % pilot_out["reject"]["rate"], "change": None, "better": "down", "basis": "实测"},
        {"key": "ai", "label": "AI 参与率", "baseline": "0%（导入前无记录）", "pilot": "—" if pilot_out["ai"]["rate"] is None else "%s%%" % pilot_out["ai"]["rate"],
         "change": None, "better": "up", "basis": "实测"},
        {"key": "cost", "label": "每单 AI 成本", "baseline": "—", "pilot": "—" if pilot_out["cost"]["per_ticket"] is None else "%s 点" % pilot_out["cost"]["per_ticket"],
         "change": None, "better": "down", "basis": "实测"},
        {"key": "throughput", "label": "人均月关闭工单", "baseline": "—" if baseline["per_person_month"] is None else "%s 张" % baseline["per_person_month"],
         "pilot": "—" if pilot_out["throughput"]["per_person"] is None else "%s 张" % pilot_out["throughput"]["per_person"],
         "change": pct(pilot_out["throughput"]["per_person"] - baseline["per_person_month"], baseline["per_person_month"])
         if baseline["per_person_month"] and pilot_out["throughput"]["per_person"] is not None and month else None, "better": "up", "basis": "实测"},
    ]
    saved = round((bc - pc) / 24 * len(closed), 1) if bc and pc is not None and len(closed) else None
    estimate = {"saved_days": saved, "basis": "估算",
                "formula": "（基线周期中位数 − 本期周期中位数）× 本期关闭工单数；周期是日历时间，不等于实际投入工时"}

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
            "baseline": baseline, "pilot": pilot_out, "compare": compare, "estimate": estimate, "trend": trend,
            "kb": {"built": bool((kb or {}).get("built")), "written": written,
                   "scope": written + cov.get("未分析", 0) + cov.get("过期", 0), "stale": cov.get("过期", 0),
                   "flows": (kb or {}).get("flows", 0), "flows_with_tables": (kb or {}).get("flows_with_tables", 0)}}


# ---------------------------------------------------------------- report

def report_md(m: dict) -> str:
    b, p, k = m["baseline"], m["pilot"], m["kb"]
    L = ["# AI 提效报告 · %s · %s" % (m["project"]["name"], m["period"]), "",
         "项目 %s · 生成于 %s · 数据来源：平台工单事件、智能体运行记录、点数账本、IDE 调用记录（.tmh/usage.jsonl）" % (m["project"]["key"], m["generated"]), ""]
    L += ["## 一、结论", ""]
    lines = []
    if b["n"] and p["cycle"]["n"]:
        ch = m["compare"][0]["change"]
        lines.append("工单周期中位数从基线的 %s 变为 %s%s。" % (dur(b["cycle"]["median_h"]), dur(p["cycle"]["median_h"]),
                                                     "（%s%.1f%%）" % ("+" if ch > 0 else "", ch) if ch is not None else ""))
    elif not b["n"]:
        lines.append("还没有导入历史工单，周期只能看本期绝对值，无法和基线比较。导入方法见文末“口径”。")
    if p["ai"]["rate"] is not None:
        lines.append("本期经手 %d 张工单，其中 %d 张有 AI 参与（%s%%）。" % (p["ai"]["total"], p["ai"]["tickets"], p["ai"]["rate"]))
    if p["locate"]["n"]:
        lines.append("首次定位耗时中位数 %s（%d 张）。" % (dur(p["locate"]["median_h"]), p["locate"]["n"]))
    if p["reject"]["reviewed"]:
        lines.append("验收 %d 张，退回 %d 张，退回率 %s%%。" % (p["reject"]["reviewed"], p["reject"]["rejected"], p["reject"]["rate"]))
    if m["estimate"]["saved_days"] is not None:
        lines.append("按周期缩短推算，本期约节省 %s 天（估算，口径见下）。" % m["estimate"]["saved_days"])
    L += ["- " + x for x in lines or ["本期还没有可统计的数据。"]] + [""]

    L += ["## 二、基线与本期对比（实测）", "", "| 指标 | 基线 | 本期 | 变化 |", "|---|---|---|---|"]
    for c in m["compare"]:
        L.append("| %s | %s | %s | %s |" % (c["label"], c["baseline"], c["pilot"],
                                             "—" if c["change"] is None else "%s%.1f%%" % ("+" if c["change"] > 0 else "", c["change"])))
    L += ["", "基线：%s" % ("%d 张从 %s 导入、并已在原系统关闭的工单，时间范围 %s 至 %s，用原系统的创建和解决时间。"
                           % (b["n"], "、".join(b["systems"]) or "外部系统", b["range"][0], b["range"][1]) if b["n"] else "无（尚未导入历史工单）。"), ""]

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
          "- **估算**：节省天数 = %s。" % m["estimate"]["formula"],
          "- 基线来自 Jira 或禅道导入（平台“导入工单”或 `tmh issue` 适配器），只统计在原系统已关闭、且没有在平台上再处理的工单。",
          "- 首次定位耗时：从工单创建到第一次“分析定位”或“修改方案”运行完成。",
          "- 验收退回率：本期有验收记录的工单中，至少被退回一次的比例。",
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
