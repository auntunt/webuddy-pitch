"""A long report of the JeecgBoot ticket test: for every ticket, what the agents found and changed, set against the
upstream commit that really fixed the issue, with both diffs side by side. Test-only, like the scoring in driver.py.

It reads the platform's database and the JeecgBoot clone directly, so the platform need not be running, and it
writes one self-contained HTML page next to them; no code leaves this machine.

    python3 longreport.py <work dir, e.g. ~/tmh-jeecg-test> [--notes notes.json] [--out 报告.html]

notes.json is optional: {"JB-1": {"verdict": "与官方一致", "text": "…"}} — a person's (or reviewer's) judgment per ticket,
shown above that ticket's code.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from tmh.platform.learn import predicted  # noqa: E402 - the same reading of a plan's files as driver.py
TIERS = {"full": "第一批：一开始就跑到改代码", "plan": "第二批：先停在方案，后来补跑改代码", "entry": "第三批：先只录入，后来补跑全流程"}
MODE = {"analyze": "分析定位", "plan": "修改方案", "fix": "修改代码", "kb": "知识页", "ask": "问答"}
STATUS = {"new": "新建", "analyzing": "分析中", "confirm": "待确认", "doing": "处理中", "verify": "待验收", "closed": "已关闭"}
RUN_ST = {"done": "完成", "failed": "失败", "cancelled": "已停止", "running": "运行中", "queued": "排队"}
BUSY = re.compile(r"at capacity|overloaded|rate.?limit|too many requests|\b(429|503|529)\b|stream disconnected", re.I)
MAX_LINES = 400  # per side per ticket; the rest stays in compare/<key>.md


def git(args, cwd) -> str:
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def official(code: Path, base: str, gold: list) -> str:
    refs = [r for r in git(["for-each-ref", "--format=%(refname)", "refs/remotes/origin/"], code).split() if not r.endswith("/HEAD")]
    for line in git(["log", "--format=%H %P", "--ancestry-path", "^" + base] + refs, code).splitlines():
        h, *parents = line.split()
        if base in parents and set(gold) & set(git(["diff", "--name-only", base, h], code).split()):
            return h
    return ""


def split_files(diff: str) -> dict:
    """{path: [lines of that file's diff, from the first @@]}"""
    out, f = {}, None
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            f = None
            continue
        if line.startswith("+++ "):
            f = line[6:] if line.startswith("+++ b/") else f
            continue
        if line.startswith("--- "):
            if line != "--- /dev/null":
                f = line[6:] if line.startswith("--- a/") else f
            continue
        if f and (line.startswith("@@") or (out.get(f) is not None and line[:1] in " +-\\")):
            out.setdefault(f, []).append(line)
    return out


def hunks(lines: list) -> list:
    res = []
    for line in lines:
        m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
        if m:
            a = int(m.group(1))
            res.append((a, a + max(int(m.group(2) or 1), 1)))
    return res


def edits(lines: list) -> list:
    return [x for x in lines if x[:1] in "+-" and x[1:].strip()]


def section(text: str, names) -> str:
    """The body of the first '## name' section of an agent's answer."""
    for n in names:
        m = re.search(r"^#{1,4}\s*[0-9.、]*\s*%s[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)" % re.escape(n), text or "", re.M | re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def secs(a, b):
    try:
        return time.mktime(time.strptime(b, "%Y-%m-%d %H:%M:%S")) - time.mktime(time.strptime(a, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return None


def collect(work: Path, spec: dict) -> list:
    code = work / "JeecgBoot"
    data = work / "data"
    made = json.loads((work / "tickets-made.json").read_text(encoding="utf-8"))
    issues = json.loads((work / "issues.json").read_text(encoding="utf-8")) if (work / "issues.json").exists() else {}
    db = sqlite3.connect("file:%s?mode=ro" % (data / "platform.db"), uri=True)
    db.row_factory = sqlite3.Row
    rows = []
    for c in spec["cases"]:
        key = made.get(c["issue"])
        if not key:
            continue
        pkey, num = key.rsplit("-", 1)
        t = db.execute("SELECT t.* FROM tickets t JOIN projects p ON p.id=t.project_id WHERE p.key=? AND t.num=?", (pkey, int(num))).fetchone()
        if not t:
            continue
        runs = [dict(r) for r in db.execute("SELECT id,mode,status,agent,model,created,started,ended,result,diff,decision FROM runs "
                                             "WHERE ticket_id=? AND mode!='ask' ORDER BY id", (t["id"],))]
        events = [dict(e) for e in db.execute("SELECT ts,author,kind,body FROM events WHERE ticket_id=? ORDER BY id", (t["id"],))]
        last = {}
        for r in runs:
            if r["status"] == "done":
                last[r["mode"]] = r
        an, pl, fx = last.get("analyze"), last.get("plan"), last.get("fix")
        verify = {}
        if fx and (data / "runs" / str(fx["id"]) / "verify.json").exists():
            try:
                verify = json.loads((data / "runs" / str(fx["id"]) / "verify.json").read_text(encoding="utf-8"))
            except ValueError:
                pass
        fix = official(code, c["base"], c["gold"]) if code.exists() else ""
        gd = git(["diff", "-U3", c["base"], fix, "--", *c["gold"]], code) if fix else ""
        meta = git(["show", "-s", "--format=%ad%x09%an%x09%s", "--date=short", fix], code).strip().split("\t") if fix else []
        ours = (fx or {}).get("diff") or ""
        g, o = split_files(gd), split_files(ours)
        near = sum(1 for f in g for a, b in hunks(g[f]) if any(x < b + 3 and a < y + 3 for x, y in hunks(o.get(f, []))))
        ge, oe = [e for f in g for e in edits(g[f])], [e for f in o for e in edits(o[f])]
        span = [(r["started"], r["ended"]) for r in runs if r["started"] and r["ended"]]
        busy = sum(1 for r in runs if r["status"] == "failed" and BUSY.search((r["result"] or "")[-3000:]))
        iss = issues.get(c["issue"]) or {}
        plan_files = predicted((pl or {}).get("result") or "", []) if pl else []
        hit = lambda xs: [f for f in c["gold"] if any(x.endswith(f) or f.endswith(x) for x in xs)]  # noqa: E731
        rows.append({
            "key": key, "issue": c["issue"], "tier": c["tier"], "kind": c.get("kind", ""), "url": c.get("url", ""),
            "title": re.sub(r"^[【\[]?issues/\d+[】\]]?\s*", "", iss.get("title") or c["title"]).strip(" -") or c["title"],
            "body": (iss.get("body") or c.get("body") or "").strip(),
            "status": t["status"], "gold": c["gold"], "official": fix, "official_meta": meta, "official_diff": g,
            "ours": o, "fix_run": (fx or {}).get("id"), "decision": (fx or {}).get("decision") or "",
            "analysis": (an or {}).get("result") or "", "analysis_run": (an or {}).get("id"), "plan": (pl or {}).get("result") or "",
            "plan_run": (pl or {}).get("id"), "plan_files": plan_files, "plan_hit": hit(plan_files), "fix_hit": hit(list(o)),
            "hunks": sum(len(hunks(v)) for v in g.values()), "hunks_hit": near, "official_lines": len(ge), "our_lines": len(oe),
            "same_lines": len(set(ge) & set(oe)), "extra_files": [f for f in o if f not in c["gold"]],
            "verify": verify, "runs": [{k: r[k] for k in ("id", "mode", "status", "agent", "model", "created", "started", "ended", "decision")}
                                       | {"err": (r["result"] or "").strip().splitlines()[-1][:160] if r["status"] == "failed" and (r["result"] or "").strip() else ""}
                                       for r in runs],
            "busy_failures": busy, "minutes": round((max(secs(min(b for b, _ in span), e) or 0 for _, e in span)) / 60, 1) if span else None,
            "agent_minutes": round(sum(secs(b, e) or 0 for b, e in span) / 60, 1) if span else None,
            "events": [e for e in events if e["kind"] not in ("comment",)][-12:],
        })
    return rows


# ---- rendering ------------------------------------------------------------------------------------
CSS = """
:root{--bg:#f7f6f2;--card:#fff;--fg:#1f2328;--mut:#656d76;--line:#d8dee4;--acc:#0b6bcb;--add:#e6ffec;--addt:#116329;--del:#ffebe9;--delt:#82071e;
 --hunk:#ddf4ff;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e;--chip:#eef1f4;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--card:#171a21;--fg:#e6edf3;--mut:#9198a1;--line:#2d333b;--acc:#58a6ff;
 --add:#12261a;--addt:#7ee2a8;--del:#2d1418;--delt:#ffa198;--hunk:#14233a;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--chip:#222831;color-scheme:dark}}
:root[data-theme=dark]{--bg:#0f1115;--card:#171a21;--fg:#e6edf3;--mut:#9198a1;--line:#2d333b;--acc:#58a6ff;--add:#12261a;--addt:#7ee2a8;--del:#2d1418;
 --delt:#ffa198;--hunk:#14233a;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--chip:#222831;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:28px 20px 80px}h1{font-size:28px;margin:0 0 6px}h2{font-size:21px;margin:40px 0 12px;text-wrap:balance}
h3{font-size:17px;margin:22px 0 8px}.mut{color:var(--mut)}a{color:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;white-space:nowrap}.tw{overflow-x:auto}
.chip{display:inline-block;background:var(--chip);border-radius:10px;padding:1px 8px;font-size:12px;margin:0 4px 2px 0;white-space:nowrap}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--mut);font-size:13px}
.verdict{font-weight:700;padding:2px 10px;border-radius:12px;background:var(--chip)}
.sbs{display:grid;grid-template-columns:1fr 1fr;gap:10px}.sbs>div{min-width:0}@media(max-width:900px){.sbs{grid-template-columns:1fr}}
.col h4{margin:0 0 6px;font-size:13px;color:var(--mut)}
pre.d{margin:0;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow-x:auto;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;padding:6px 0}
pre.d span{display:block;padding:0 10px;white-space:pre}pre.d .a{background:var(--add);color:var(--addt)}pre.d .r{background:var(--del);color:var(--delt)}pre.d .h{background:var(--hunk);color:var(--mut)}
.file{margin:14px 0 4px;font:600 13px ui-monospace,Menlo,monospace;word-break:break-all}
details>summary{cursor:pointer;color:var(--acc)}.prose{white-space:pre-wrap;font-size:14px;background:var(--bg);border-radius:8px;padding:10px 12px;max-height:520px;overflow:auto}
nav.toc{columns:3 260px;font-size:13.5px}nav.toc a{display:block;text-decoration:none}
.empty{color:var(--mut);font-style:italic;padding:8px 0}
"""


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def pre(lines: list, cap: int = MAX_LINES) -> str:
    if not lines:
        return '<div class="empty">没有改动</div>'
    out = []
    for x in lines[:cap]:
        cls = "h" if x.startswith("@@") else "a" if x.startswith("+") else "r" if x.startswith("-") else ""
        out.append('<span class="%s">%s</span>' % (cls, e(x) or " "))
    more = '<div class="mut" style="font-size:12px;margin-top:4px">还有 %d 行没显示，完整内容在 compare/ 目录。</div>' % (len(lines) - cap) if len(lines) > cap else ""
    return '<pre class="d">%s</pre>%s' % ("".join(out), more)


def pct(a, b):
    return "%d%%" % round(a * 100 / b) if b else "—"


def render(rows: list, notes: dict, spec: dict) -> str:
    fixed = [r for r in rows if r["ours"]]
    planned = [r for r in rows if r["plan"]]
    analyzed = [r for r in rows if r["analysis"]]
    gold_n = lambda rs: sum(len(r["gold"]) for r in rs)  # noqa: E731
    k_plan = sum(len(r["plan_hit"]) for r in planned)
    k_fix = sum(len(r["fix_hit"]) for r in fixed)
    k_h = sum(r["hunks_hit"] for r in fixed)
    k_hn = sum(r["hunks"] for r in fixed)
    busy = sum(r["busy_failures"] for r in rows)
    verdicts = Counter((notes.get(r["key"]) or {}).get("verdict") for r in fixed if isinstance(notes.get(r["key"]), dict) and notes[r["key"]].get("verdict"))
    p = ['<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         "<title>JeecgBoot 工单测试报告</title><style>%s</style></head><body><div class=wrap>" % CSS]
    p.append("<h1>JeecgBoot 工单测试报告</h1><div class=mut>%d 张真实工单，智能体的结论和改动逐张对照官方修复提交。生成于 %s。本页只在本机生成，代码没有离开这台电脑。</div>"
             % (len(rows), time.strftime("%Y-%m-%d %H:%M")))
    # summary
    p.append("<h2>一、总体结果</h2><div class=kpis>")
    for v, label in ((len(analyzed), "张有分析结论"), (len(planned), "张有修改方案"), (len(fixed), "张生成了代码改动"),
                     (pct(k_plan, gold_n(planned)), "方案列到官方改的文件"), (pct(k_fix, gold_n(fixed)), "改动改到官方改的文件"),
                     (pct(k_h, k_hn), "官方改动块被改到（3 行内）"), (busy, "次运行因模型满载失败")):
        p.append("<div class=kpi><b>%s</b><span>%s</span></div>" % (e(v), e(label)))
    p.append("</div>")
    if notes.get("_summary"):
        p.append('<div class=card><b>主要结论</b><div style="margin-top:6px;white-space:pre-wrap">%s</div></div>' % e(notes["_summary"]))
    if verdicts:
        p.append('<div class=card><b>逐单评审（人工看代码后的判断）</b><div style="margin-top:6px">%s</div></div>'
                 % "".join('<span class=chip>%s %d 张</span>' % (e(k), n) for k, n in verdicts.most_common()))
    p.append("""<div class=card><b>怎么读</b><ul>
<li><b>方案命中 / 改动命中</b>：官方修复改了哪些文件，智能体的方案列到了几个、改动改到了几个。只看文件，不看改得对不对。</li>
<li><b>改到官方改动处</b>：官方修复的每个改动块，智能体的改动落在它前后 3 行内就算改到。两边起点不一定是同一个提交，行号可能有少量偏移。</li>
<li><b>行数（相同）</b>：智能体改了几行、官方改了几行，括号里是一字不差相同的行数。写法不同但意思一样的不算相同，所以这个数偏低是正常的。</li>
<li><b>多改的文件</b>：官方没改、智能体改了的文件，多数是补的测试，也可能是改大了，下面每张单里都列出来了。</li>
<li><b>评审</b>：每张生成了改动的单，下面都有一段对照代码写的判断。这是看代码得出的意见，没有编译运行过；最终对不对，以合并后实际验收为准。</li></ul></div>""")
    # per-tier table
    for tier, label in TIERS.items():
        rs = [r for r in rows if r["tier"] == tier]
        if not rs:
            continue
        p.append("<h3>%s（%d 张）</h3><div class=tw><table><tr><th>单号</th><th>问题</th><th>状态</th><th>评审</th><th>方案命中</th><th>改动命中</th>"
                 "<th>改到官方改动处</th><th>行数（相同）</th><th>多改的文件</th><th>总用时</th><th>满载失败</th></tr>" % (e(label), len(rs)))
        for r in rs:
            n = len(r["gold"])
            v = (notes.get(r["key"]) or {}).get("verdict", "")
            p.append("<tr><td><a href='#%s'>%s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                e(r["key"]), e(r["key"]), e(r["title"][:46]), e(STATUS.get(r["status"], r["status"])), e(v) or "—",
                "%d/%d" % (len(r["plan_hit"]), n) if r["plan"] else "—", "%d/%d" % (len(r["fix_hit"]), n) if r["ours"] else "—",
                "%d/%d" % (r["hunks_hit"], r["hunks"]) if r["ours"] and r["official"] else "—",
                "%d / %d（%d）" % (r["our_lines"], r["official_lines"], r["same_lines"]) if r["ours"] else "—",
                e("、".join(f.rsplit("/", 1)[-1] for f in r["extra_files"])) or "—",
                "%s 分" % r["minutes"] if r["minutes"] is not None else "—", r["busy_failures"] or ""))
        p.append("</table></div>")
    # toc
    p.append("<h2>二、逐单详情</h2><nav class=toc>%s</nav>" % "".join(
        "<a href='#%s'>%s　%s</a>" % (e(r["key"]), e(r["key"]), e(r["title"][:30])) for r in rows))
    for r in rows:
        p.append(ticket(r, notes.get(r["key"]) if isinstance(notes.get(r["key"]), dict) else {}))
    p.append("<h2>三、说明</h2><div class=card>每张单都钉在它自己的官方修复之前的那个提交上，智能体看到的是问题刚报出来时的代码。官方修复是上游仓库里、以这个提交为父提交并且改了相关文件的那次提交。"
             "评审意见只看代码，没有编译运行；“与官方一致”指改法和官方本质相同；“思路一致”指改的位置和原因对、写法不同；“方向对但改太多”指找到了对的地方，但顺带改了很多官方不需要的代码；“改法不同需验证”指和官方不是一个改法，但看起来也可能解决；“方向不对”指改的地方或原因和官方不同。"
             "智能体补的测试文件没有算进行数对比。</div>")
    p.append("</div></body></html>")
    return "\n".join(p)


def ticket(r: dict, note: dict) -> str:
    q = ['<section id="%s"><h2>%s　%s</h2>' % (e(r["key"]), e(r["key"]), e(r["title"]))]
    q.append('<div class=mut><a href="%s">GitHub #%s</a>　%s · %s · 当前%s · 总用时 %s 分（智能体实际运行 %s 分）</div>' % (
        e(r["url"]), e(r["issue"]), e(TIERS.get(r["tier"], r["tier"])), "前端" if r["kind"] in ("vue", "ts", "front") else "后端" if r["kind"] == "java" else e(r["kind"]),
        e(STATUS.get(r["status"], r["status"])), r["minutes"] if r["minutes"] is not None else "—", r["agent_minutes"] if r["agent_minutes"] is not None else "—"))
    if note:
        q.append('<div class=card><span class=verdict>%s</span><div style="margin-top:8px;white-space:pre-wrap">%s</div></div>' % (e(note.get("verdict", "")), e(note.get("text", ""))))
    q.append('<details><summary>问题原文</summary><div class=prose>%s</div></details>' % e(r["body"][:4000] or "（无）"))
    concl = section(r["analysis"], ("结论", "结论与边界", "原因分析", "原因", "根因"))
    q.append("<h3>智能体的分析</h3>")
    if r["analysis"]:
        q.append('<div class=prose>%s</div><details><summary>完整分析（运行 #%s）</summary><div class=prose>%s</div></details>' % (
            e((concl or r["analysis"])[:1800]), r["analysis_run"], e(r["analysis"])))
    else:
        q.append('<div class=empty>没有完成的分析</div>')
    if r["plan"]:
        q.append('<h3>修改方案</h3><div>方案列出的文件：%s</div><div class=mut>官方改的文件：%s</div><details><summary>完整方案（运行 #%s）</summary><div class=prose>%s</div></details>' % (
            "".join("<span class=chip>%s</span>" % e(f.rsplit("/", 1)[-1]) for f in r["plan_files"][:20]) or "—",
            "".join("<span class=chip>%s</span>" % e(f.rsplit("/", 1)[-1]) for f in r["gold"]), r["plan_run"], e(r["plan"])))
    q.append("<h3>代码对比：官方修复 ↔ 智能体改动</h3>")
    if r["official"]:
        m = r["official_meta"] + ["", "", ""]
        q.append('<div class=mut>官方提交 <code>%s</code> · %s · %s · %s</div>' % (e(r["official"][:10]), e(m[0]), e(m[1]), e(m[2][:120])))
    if not r["ours"]:
        q.append('<div class=empty>%s</div>' % ("这张单按测试设计停在改代码之前。" if r["tier"] != "full" else "这张单还没有生成代码改动。"))
    files = list(dict.fromkeys(list(r["official_diff"]) + [f for f in r["ours"] if f in r["official_diff"]]))
    budget = MAX_LINES
    for f in files:
        q.append('<div class=file>%s</div><div class=sbs><div class=col><h4>官方修复</h4>%s</div><div class=col><h4>智能体</h4>%s</div></div>' % (
            e(f), pre(r["official_diff"].get(f, []), budget), pre(r["ours"].get(f, []), budget) if r["ours"] else '<div class=empty>—</div>'))
    for f in r["extra_files"]:
        q.append('<div class=file>%s <span class=chip>官方没改</span></div>%s' % (e(f), pre(r["ours"][f], 160)))
    v = r["verify"]
    if v:
        bits = []
        if v.get("skip"):
            bits.append("构建和测试：没跑（%s）" % e(v["skip"]))
        for c in v.get("commands") or []:
            if isinstance(c, dict):
                bits.append("%s：%s" % (e(c.get("name") or c.get("cmd") or ""), "<span class=ok>通过</span>" if c.get("ok") else "<span class=bad>没过</span>"))
        if v.get("rounds"):
            bits.append("改了 %s 轮%s" % (v["rounds"], "，中途拆成小步" if v.get("split") else ""))
        if v.get("beyond_plan"):
            bits.append("<span class=warn>超出方案的文件：%s</span>" % e("、".join(f.rsplit("/", 1)[-1] for f in v["beyond_plan"])))
        d = v.get("diagnosis")
        if isinstance(d, dict):
            bits.append("诊断：%s" % ("<span class=ok>认为已解决</span>" if d.get("verdict") == "pass" else "<span class=bad>认为还没解决</span>"))
            for k, label in (("cause", "原因"), ("evidence", "依据"), ("guide", "建议")):
                if d.get(k):
                    bits.append("%s：%s" % (label, e(str(d[k])[:600])))
        elif d:
            bits.append("诊断：%s" % e(str(d)[:600]))
        if bits:
            q.append("<h3>平台核对</h3><div>%s</div>" % "<br>".join(bits))
    q.append('<details><summary>运行记录（%d 次）</summary><div class=tw><table><tr><th>#</th><th>步骤</th><th>结果</th><th>开始</th><th>用时</th><th>模型</th><th>备注</th></tr>%s</table></div></details>' % (
        len(r["runs"]), "".join("<tr><td>%s</td><td>%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            x["id"], e(MODE.get(x["mode"], x["mode"])), "bad" if x["status"] == "failed" else "", e(RUN_ST.get(x["status"], x["status"])),
            e((x["started"] or x["created"] or "")[5:16]), "%d 分" % round(secs(x["started"], x["ended"]) / 60) if secs(x["started"], x["ended"]) else "—",
            e(x["model"] or x["agent"]), e(x["err"] or (x["decision"] or ""))) for x in r["runs"])))
    q.append("</section>")
    return "\n".join(q)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--notes")
    ap.add_argument("--out")
    ap.add_argument("--spec", default=str(HERE / "tickets.json"))
    a = ap.parse_args(argv)
    work = Path(a.work).expanduser()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    rows = collect(work, spec)
    (work / "report-data.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    notes = json.loads(Path(a.notes).read_text(encoding="utf-8")) if a.notes and Path(a.notes).exists() else {}
    out = Path(a.out) if a.out else work / "JeecgBoot工单测试报告.html"
    out.write_text(render(rows, notes, spec), encoding="utf-8")
    print("报告：%s（%d 张单，%d 张有代码改动）" % (out, len(rows), sum(1 for r in rows if r["ours"])))


if __name__ == "__main__":
    main()
