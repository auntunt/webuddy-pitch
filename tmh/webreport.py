"""Self-contained HTML report: business flows, state machines, table usage, analysis process.

One file, no network, no external libraries, so it opens on an intranet laptop
or gets mailed to a customer as is. Diagrams are inline SVG generated here.
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter
import time
from pathlib import Path

from . import activity
from . import config as cfgmod

LAYERS = [("entry", "入口"), ("service", "业务逻辑"), ("dao", "数据访问"), ("table", "数据表")]
OPS = {"C": ("新增", "op-c"), "R": ("查询", "op-r"), "U": ("修改", "op-u"), "D": ("删除", "op-d"), "P": ("过程", "op-p")}
NOTE_STATUS = re.compile(r"^\s*(?:状态|status)\s*[:：]\s*(\S+)", re.M | re.I)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _trunc(s: str, n: int) -> str:
    w, out = 0, ""
    for ch in s:
        w += 2 if ord(ch) > 0x2E80 else 1
        if w > n:
            return out + "…"
        out += ch
    return out


# ---------------------------------------------------------------- markdown
def md(text: str) -> str:
    """Small Markdown subset: headings, lists, tables, code fences, quotes, bold/inline code/links."""
    out, lines, i = [], text.splitlines(), 0

    def inline(s: str) -> str:
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
        s = s.replace("【推断】", '<span class="tag tag-guess">推断</span>').replace("【待确认】", '<span class="tag tag-ask">待确认</span>')
        return s

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            lang = ln.strip()[3:].strip()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append('<pre class="code" data-lang="%s">%s</pre>' % (esc(lang), esc("\n".join(buf))))
            i = j + 1
            continue
        hm = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if hm:
            lvl = min(len(hm.group(1)) + 2, 6)
            out.append("<h%d>%s</h%d>" % (lvl, inline(hm.group(2)), lvl))
            i += 1
            continue
        if ln.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], rows[2:]
            out.append("<table class='grid'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                "".join("<th>%s</th>" % inline(c) for c in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in body)))
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            tag = "ol" if re.match(r"^\s*\d+\.", ln) else "ul"
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue
        if ln.startswith(">"):
            out.append("<blockquote>%s</blockquote>" % inline(ln.lstrip("> ")))
            i += 1
            continue
        if ln.strip():
            buf = [ln]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|```|\||>|\s*([-*]|\d+\.)\s)", lines[i]):
                buf.append(lines[i])
                i += 1
            out.append("<p>%s</p>" % inline(" ".join(buf)))
            continue
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------- diagrams
SVG_MAX_NODES = 40     # big legacy flows: draw the first part, the rest is in `tmh flows`
CARD_MAX_ROWS = 60
MATRIX_MAX_CELLS = 150000
MATRIX_TOP_TABLES = 80


def _dedup(rows: list, key, limit: int) -> tuple[list, int]:
    seen, out = set(), []
    for r in rows:
        k = key(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out[:limit], max(0, len(out) - limit)


def flow_svg(f: dict) -> str:
    """Lane diagram: one row per call in depth-first order, one column per layer."""
    nodes = {n["id"]: n for n in f["nodes"]}
    children: dict = {}
    for e in f["edges"]:
        children.setdefault(e["from"], []).append(e)
    order, depth_in_col, edges = [], {}, []

    def walk(nid, depth, seen):
        if len(order) >= SVG_MAX_NODES and nid not in depth_in_col:
            return
        if nid not in depth_in_col:
            order.append(nid)
            depth_in_col[nid] = depth
        if nid in seen:
            return
        seen = seen | {nid}
        for e in children.get(nid, []):
            edges.append(e)
            if e["to"] not in depth_in_col or nodes[e["to"]]["layer"] != "table":
                walk(e["to"], depth + 1, seen)

    if f.get("root"):
        walk(f["root"], 0, set())
    edges = [e for e in edges if e["from"] in depth_in_col and e["to"] in depth_in_col]
    col_x = {k: 20 + i * 250 for i, (k, _) in enumerate(LAYERS)}
    box_w, row_h, top = 212, 46, 44
    pos = {}
    indent: dict = {}
    for r, nid in enumerate(order):
        n = nodes[nid]
        lay = n["layer"]
        lvl = 0
        # indent repeated visits within the same lane so nesting stays readable
        for e in edges:
            if e["to"] == nid and nodes[e["from"]]["layer"] == lay:
                lvl = indent.get(e["from"], 0) + 1
                break
        indent[nid] = min(lvl, 3)
        x = col_x[lay] + indent[nid] * 10
        pos[nid] = (x, top + r * row_h)
    width = col_x["table"] + box_w + 30
    height = top + len(order) * row_h + 16
    parts = ['<svg class="flow" viewBox="0 0 %d %d" width="%d" role="img" aria-label="%s">' % (width, height, width, esc(f["trigger"]))]
    for k, label in LAYERS:
        parts.append('<rect class="lane" x="%d" y="0" width="236" height="%d" rx="8"/>' % (col_x[k] - 10, height))
        parts.append('<text class="lane-title" x="%d" y="24">%s</text>' % (col_x[k], label))
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos:
            continue
        (x1, y1), (x2, y2) = pos[e["from"]], pos[e["to"]]
        sx, sy = x1 + 14, y1 + 34
        back = y2 < y1
        cls = "edge back" if back else "edge"
        if back:
            path = "M%d %d H%d V%d H%d" % (x1 + box_w, y1 + 17, x2 - 8, y2 + 17, x2)
        else:
            path = "M%d %d V%d H%d" % (sx, sy, y2 + 17, x2)
        parts.append('<path class="%s" d="%s" marker-end="url(#arr)"/>' % (cls, path))
        if e.get("op"):
            label, c = OPS.get(e["op"], ("", "op-r"))
            parts.append('<g class="%s"><rect x="%d" y="%d" width="34" height="18" rx="9"/><text x="%d" y="%d">%s</text></g>' % (c, x2 - 46, y2 + 8, x2 - 29, y2 + 21, label))
    for nid in order:
        n = nodes[nid]
        x, y = pos[nid]
        title = n["label"] + (" — %s:%d" % (n["file"], n["line"]) if n["file"] else "")
        sub = n.get("comment") or (n["file"].rsplit("/", 1)[-1] + (":%d" % n["line"] if n["line"] else "") if n["file"] else "")
        parts.append('<g class="node %s"><title>%s</title><rect x="%d" y="%d" width="%d" height="36" rx="6"/>'
                     '<text class="n1" x="%d" y="%d">%s</text><text class="n2" x="%d" y="%d">%s</text></g>' % (
                         n["layer"], esc(title), x, y, box_w, x + 10, y + 15, esc(_trunc(n["label"], 30)), x + 10, y + 29, esc(_trunc(sub, 32))))
    parts.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="arrowhead"/></marker></defs></svg>')
    return "".join(parts)


def state_svg(sm: dict) -> str:
    states = sm["states"]
    incoming = {s: [] for s in states}
    for t in sm["transitions"]:
        if t["to"] in incoming and t["from"] != "*":
            incoming[t["to"]].append(t["from"])
    level = {}
    roots = [s for s in states if not incoming[s] or s == "(新建)"] or states[:1]
    frontier = list(roots)
    for s in roots:
        level[s] = 0
    while frontier:
        nxt = []
        for s in frontier:
            for t in sm["transitions"]:
                if t["from"] == s and t["to"] not in level:
                    level[t["to"]] = level[s] + 1
                    nxt.append(t["to"])
        frontier = nxt
    for s in states:
        level.setdefault(s, max(level.values() or [0]) + 1)
    cols: dict = {}
    for s in states:
        cols.setdefault(level[s], []).append(s)
    bw, bh, gx, gy = 150, 40, 170, 30
    maxrows = max(len(v) for v in cols.values())
    pos = {}
    for lv, ss in cols.items():
        off = (maxrows - len(ss)) * (bh + gy) / 2
        for r, s in enumerate(ss):
            pos[s] = (20 + lv * (bw + gx), 40 + off + r * (bh + gy))
    width = 40 + (max(cols) + 1) * (bw + gx) - gx
    height = 60 + maxrows * (bh + gy)
    parts = ['<svg class="sm" viewBox="0 0 %d %d" width="%d" role="img" aria-label="%s 状态流转">' % (width, height, width, esc(sm["table"] + "." + sm["column"]))]
    pair_count: dict = {}
    for t in sm["transitions"]:
        frs = states if t["from"] == "*" else [t["from"]]
        for fr in frs:
            if fr not in pos or t["to"] not in pos or fr == t["to"]:
                continue
            (x1, y1), (x2, y2) = pos[fr], pos[t["to"]]
            k = (fr, t["to"])
            pair_count[k] = pair_count.get(k, 0) + 1
            bend = (pair_count[k] - 1) * 22
            if x2 > x1:
                sx, sy, ex, ey = x1 + bw, y1 + bh / 2, x2, y2 + bh / 2
            else:
                sx, sy, ex, ey = x1 + bw / 2, y1 + bh, x2 + bw / 2, y2 + bh
                bend += 50
            mx, my = (sx + ex) / 2, (sy + ey) / 2 - bend
            parts.append('<path class="edge" d="M%.0f %.0f Q%.0f %.0f %.0f %.0f" marker-end="url(#sarr)"><title>%s (%s:%d)</title></path>' % (sx, sy, mx, my, ex, ey, esc(t["flow_name"]), esc(t["file"]), t["line"]))
            lx, ly = sx + (ex - sx) * 0.62, sy + (ey - sy) * 0.62 - bend * 0.47
            parts.append('<text class="elabel" x="%.0f" y="%.0f">%s</text>' % (lx, ly - 6, esc(_trunc(t["flow_name"], 18))))
    for s, (x, y) in pos.items():
        cls = "state init" if s == "(新建)" else "state"
        parts.append('<g class="%s"><rect x="%.0f" y="%.0f" width="%d" height="%d" rx="20"/><text x="%.0f" y="%.0f">%s</text></g>' % (cls, x, y, bw, bh, x + bw / 2, y + bh / 2 + 5, esc(_trunc(s, 18))))
    parts.append('<defs><marker id="sarr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="arrowhead"/></marker></defs></svg>')
    return "".join(parts)


# ---------------------------------------------------------------- data
UNFILLED = "（这个功能为谁、解决什么问题）"


def _notes(root: Path) -> dict:
    from . import kb
    d = cfgmod.tmh_dir(root) / "knowledge" / "flows"
    out = {}
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            t = p.read_text(encoding="utf-8")
            if UNFILLED in t:  # template nobody has written yet
                continue
            pg = kb.parse_page(t)
            st = pg["meta"].get("status") or "待确认"
            if st == kb.STATUS_NEW:
                continue
            out[p.stem] = {"text": pg["body"], "status": st, "title": pg["meta"].get("title", ""), "file": p.relative_to(root).as_posix(),
                           "summary": pg["meta"].get("summary", "")}
    return out


def _kb_pages(root: Path) -> list[dict]:
    """Knowledge pages for the wiki tab, in reading order."""
    from . import kb
    reg = kb.load_registry(root)
    k = kb.kdir(root)
    if not reg:
        return []
    pages = []
    for pid, r in reg.items():
        if r.get("orphan"):
            continue
        p = kb.page_path(root, pid)
        if not p.exists():
            continue
        pg = kb.parse_page(p.read_text(encoding="utf-8"))
        written = r.get("status") != kb.STATUS_NEW or bool(r.get("stale"))
        pages.append({"id": pid, "kind": kb.page_kind(pid), "path": p.relative_to(k).as_posix(), "title": pg["meta"].get("title") or pid,
                      "summary": r.get("summary", ""), "status": "过期" if r.get("stale") else r.get("status", kb.STATUS_NEW),
                      "scope": r.get("scope", ""), "facts": pg["facts"], "body": pg["body"] if written else "", "domain": "", "stale": r.get("stale", [])})
    for name in ("glossary.md", "decisions.md", "pitfalls.md", "open-questions.md"):
        p = k / name
        if p.exists():
            t = p.read_text(encoding="utf-8")
            title = next((l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("#")), name)
            pages.append({"id": name, "kind": "free", "path": name, "title": title, "summary": "", "status": "", "scope": "",
                          "facts": "", "body": re.sub(r"^#\s+.*\n", "", t, count=1), "stale": []})
    return pages


def _kb_links(text: str, page_path: str) -> str:
    """Relative .md links inside a page → in-report navigation."""
    import posixpath
    base = posixpath.dirname(page_path)

    def fix(m):
        target = posixpath.normpath(posixpath.join(base, m.group(2)))
        return "[%s](#kb:%s)" % (m.group(1), target)
    return re.sub(r"\[([^\]]+)\]\(((?!https?:|#)[^)\s]+\.md)\)", fix, text)


def domain_svg(root: Path) -> str:
    """Business domains and how they share data, for the overview page."""
    try:
        from .graph import Graph
        g = Graph(root)
    except FileNotFoundError:
        return ""
    doms = g.nodes("dom")
    if not doms:
        return ""
    from collections import Counter
    rel = Counter()
    size = {}
    for d in doms:
        size[d["id"]] = sum(1 for e in g.inn(d["id"], "in") if e["src"].startswith("flow:"))
    for t in g.nodes("tbl"):
        owner = "dom:" + t["domain"] if t["domain"] else None
        if not owner:
            continue
        for e in g.inn(t["id"], "uses"):
            f = g.node(e["src"])
            if f and f["domain"] and "dom:" + f["domain"] != owner:
                rel[("dom:" + f["domain"], owner)] += 1
    doms = sorted(doms, key=lambda d: -size[d["id"]])[:24]
    ids = {d["id"] for d in doms}
    cols = min(4, len(doms))
    W, H, GX, GY = 190, 64, 70, 60
    pos = {}
    for i, d in enumerate(doms):
        r, c = divmod(i, cols)
        pos[d["id"]] = (20 + c * (W + GX), 20 + r * (H + GY))
    rows = (len(doms) + cols - 1) // cols
    vw, vh = 40 + cols * W + (cols - 1) * GX, 40 + rows * H + (rows - 1) * GY
    out = ['<svg viewBox="0 0 %d %d" width="%d" style="max-width:100%%;height:auto" role="img" aria-label="业务域关系">' % (vw, vh, vw),
           '<defs><marker id="dah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="arrowhead" d="M0,0L10,5L0,10z"/></marker></defs>']
    for (a, b), n in rel.items():
        if a not in ids or b not in ids:
            continue
        x1, y1 = pos[a][0] + W / 2, pos[a][1] + H / 2
        x2, y2 = pos[b][0] + W / 2, pos[b][1] + H / 2
        # clip to box edges
        dx, dy = x2 - x1, y2 - y1
        k = min(abs((W / 2) / dx) if dx else 9e9, abs((H / 2) / dy) if dy else 9e9)
        sx, sy, ex, ey = x1 + dx * k, y1 + dy * k, x2 - dx * k, y2 - dy * k
        out.append('<path class="edge" d="M%.0f,%.0f L%.0f,%.0f" marker-end="url(#dah)"/>' % (sx, sy, ex, ey))
        out.append('<text class="elabel" x="%.0f" y="%.0f">用 %d 处</text>' % ((sx + ex) / 2, (sy + ey) / 2 - 4, n))
    for d in doms:
        x, y = pos[d["id"]]
        out.append('<g class="node service" data-kb="%s" style="cursor:pointer"><rect x="%d" y="%d" width="%d" height="%d" rx="8"/>'
                   '<text x="%d" y="%d" style="font-weight:600">%s</text><text class="n2" x="%d" y="%d">%d 条业务流</text></g>' % (
                       esc("domains/%s.md" % d["id"][4:]), x, y, W, H, x + 12, y + 26, esc(_trunc(d["name"], 22)), x + 12, y + 46, size[d["id"]]))
    out.append("</svg>")
    return "".join(out)


def _kb_section(root: Path) -> tuple[str, dict]:
    pages = _kb_pages(root)
    if not pages:
        return ('<section class="tab" id="kb"><div class="card empty">还没有知识库。运行 <code>tmh kb build</code> 生成知识图谱和 Wiki 骨架，'
                '再让智能体按 <code>kb-build</code> 技能完成全项目分析。</div></section>', {})
    from collections import Counter
    st = Counter(p["status"] for p in pages if p["kind"] != "free")
    groups = [("index", "总览"), ("dom", "业务域"), ("flow", "业务流"), ("tbl", "业务对象"), ("mod", "代码模块"), ("free", "术语、决定与问题")]
    cls = {"已确认": "tag-ok", "待确认": "tag-guess", "过期": "tag-ask"}
    nav, body = [], []
    for kind, label in groups:
        ps = [p for p in pages if p["kind"] == kind]
        if not ps:
            continue
        nav.append('<div class="grp">%s <span class="m">%d</span></div>' % (label, len(ps)))
        for p in sorted(ps, key=lambda x: (x["status"] == "未分析", x["title"])):
            nav.append('<div class="item kbi" data-kb="%s"><div class="t">%s%s</div>%s</div>' % (
                esc(p["path"]), esc(_trunc(p["title"], 34)), ' <span class="tag %s">%s</span>' % (cls.get(p["status"], ""), esc(p["status"])) if p["status"] else "",
                '<div class="m">%s</div>' % esc(_trunc(p["summary"], 60)) if p["summary"] else ""))
    for p in pages:
        h = ['<div class="card kbpage" id="kb-%s" style="display:none">' % esc(p["path"]),
             '<h2>%s%s</h2>' % (esc(p["title"]), ' <span class="tag %s">%s</span>' % (cls.get(p["status"], ""), esc(p["status"])) if p["status"] else "")]
        if p["summary"]:
            h.append('<div class="sub">%s</div>' % esc(p["summary"]))
        h.append('<div class="loc">.tmh/knowledge/%s</div>' % esc(p["path"]))
        if p["stale"]:
            h.append('<p class="warn">代码在这些地方有变化，说明可能已不准确：%s</p>' % esc("、".join(x.split(":", 1)[-1] for x in p["stale"][:8])))
        if p["id"] == "index":
            h.append(domain_svg(root))
        if p["facts"]:
            facts = p["facts"].split("\n", 1)[1].rsplit("<!-- tmh:facts:end -->", 1)[0]
            h.append('<div class="factbox"><div class="fb-h">工具抽取的事实</div>%s</div>' % md(_kb_links(facts, p["path"])))
        if p["body"]:
            h.append('<div class="und"><div class="fb-h">业务理解%s</div>%s</div>' % (
                "" if p["kind"] == "free" else "（智能体撰写，%s）" % ("已由人确认" if p["status"] == "已确认" else "待人确认"), md(_kb_links(p["body"], p["path"]))))
        elif p["kind"] != "free":
            h.append('<p class="empty">%s</p>' % ("在全项目分析范围内，还没写。" if p["scope"] else "不在全项目分析范围内（只读查询等），需要时 <code>tmh kb next --page %s</code>。" % esc(p["id"])))
        h.append("</div>")
        body.append("".join(h))
    total = sum(st.values())
    head = '<div class="card"><h2>项目知识库</h2><div class="sub">知识图谱自动抽取事实，智能体自底向上撰写业务理解（业务流 → 业务对象 → 模块 → 业务域 → 总览），人工确认后入库；代码变化时只有受影响的页面会被标为过期。</div><div class="stats">%s</div></div>' % "".join(
        '<div class="stat"><b>%d</b><span>%s</span></div>' % (v, k) for k, v in [("知识页", total)] + sorted(st.items(), key=lambda kv: ["已确认", "待确认", "过期", "未分析"].index(kv[0]) if kv[0] in ["已确认", "待确认", "过期", "未分析"] else 9))
    html_ = '<section class="tab on" id="kb">%s<div class="split"><div class="list"><input id="kq" placeholder="搜索知识页">%s</div><div>%s</div></div></section>' % (head, "".join(nav), "".join(body))
    html_ = re.sub(r'<a href="#kb:([^"]+)">', r'<a href="#" data-kb="\1">', html_)
    return html_, dict(st)


def affected_flows(flows: list[dict], files: list[str], lines: dict | None = None) -> list[dict]:
    """Flows touched by a change. With line ranges, only methods/statements that overlap a hunk count."""
    fs = set(files or [])
    out = []
    for f in flows:
        spans = [(n["file"], n["line"], n.get("end", n["line"])) for n in f["nodes"] if n["file"]]
        spans += [(o["file"], o["line"], o["line"] + max(3, o["sql"].count(" ") // 12)) for o in f["data_ops"]]
        hit = False
        for file, a, b in spans:
            if file not in fs:
                continue
            if lines is None or file not in lines:
                hit = True
            elif any(x <= b and y >= a for x, y in lines[file]):
                hit = True
            if hit:
                break
        if hit:
            out.append(f)
    return out


def _timeline(root: Path, flows: list[dict]) -> list[dict]:
    ev = []
    group = None
    for a in activity.read(root):
        if a["kind"] == "tool":
            if group is None:
                group = {"ts": a["ts"], "kind": "tool", "steps": []}
                ev.append(group)
            group["steps"].append("%s %s" % (a["ts"][11:], a["text"]))
            continue
        group = None
        ev.append({"ts": a["ts"], "kind": a["kind"], "title": a["text"], "body": a.get("detail", ""), "meta": a.get("cmd", "")})
    for g in ev:
        if g["kind"] == "tool":
            g["title"] = "智能体操作 %d 步：%s" % (len(g["steps"]), _trunc("；".join(s[9:] for s in g["steps"][:3]), 80))
            g["body"] = "<ol class='steps'>%s</ol>" % "".join("<li><code>%s</code></li>" % esc(s) for s in g["steps"])
            g["html"] = True
    x = cfgmod.tmh_dir(root)
    for p in sorted((x / "tasks").glob("T*.md")) if (x / "tasks").is_dir() else []:
        t = p.read_text(encoding="utf-8")
        st = re.search(r"状态[:：]\s*(\S+)", t)
        ev.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime)), "kind": "task",
                   "title": "变更契约 %s（%s）" % (t.splitlines()[0].lstrip("# "), st.group(1) if st else "?"), "body": md(t), "html": True})
    rep = x / "reports"
    for p in sorted(rep.glob("verify-2*.json")) if rep.is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        aff = affected_flows(flows, r.get("changed_files") or [], r.get("changed_lines"))
        lines = ["- 结果：**%s**" % ("通过" if r.get("passed") else "未通过"),
                 "- 改动文件：%s" % ("、".join("`%s`" % c for c in (r.get("changed_files") or [])) or "无"),
                 "- 影响的业务流：%s" % ("、".join(f["name"] or f["trigger"] for f in aff) or "无")]
        for c in r.get("commands", []):
            lines.append("- `%s` → 退出码 %s（%ss）" % (c["command"], c["exit_code"], c["seconds"]))
        for v in r.get("protected_violations", []):
            lines.append("- 受保护文件：`%s` %s" % (v["file"], v["problem"]))
        for nf in r.get("new_findings", []):
            lines.append("- 新引入问题：%s `%s:%s`" % (nf.get("title", nf.get("rule")), nf.get("file"), nf.get("line")))
        ts = (r.get("time") or "").replace(" ", "T")
        ts = ts if len(ts) >= 19 else time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))
        ev.append({"ts": ts[:19], "kind": "verify", "title": "独立验证%s" % ("通过" if r.get("passed") else "未通过"), "body": md("\n".join(lines)), "html": True})
    ev.sort(key=lambda e: e["ts"])
    return ev


# ---------------------------------------------------------------- page
CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--ink:#1d2129;--muted:#6b7280;--line:#e3e6ea;--lane:#f1f3f6;--accent:#2f6fde;
--entry:#e8f0fe;--entry-b:#2f6fde;--service:#eef7ee;--service-b:#2e8b57;--dao:#fff4e5;--dao-b:#d9822b;--table:#f3eefc;--table-b:#7b52c7;
--c:#2e8b57;--r:#2f6fde;--u:#d9822b;--d:#d64545;--p:#7b52c7;--edge:#9aa3ae}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14161a;--panel:#1c1f24;--ink:#e6e8eb;--muted:#9aa3ae;--line:#2c3138;--lane:#20242a;
--entry:#1d2a40;--service:#1c2e24;--dao:#33281a;--table:#2a2238;--edge:#5d6672}}
:root[data-theme=dark]{--bg:#14161a;--panel:#1c1f24;--ink:#e6e8eb;--muted:#9aa3ae;--line:#2c3138;--lane:#20242a;--entry:#1d2a40;--service:#1c2e24;--dao:#33281a;--table:#2a2238;--edge:#5d6672}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif}
header{padding:20px 24px 8px;max-width:1400px;margin:auto}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--muted)}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;min-width:110px}
.stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}
nav{max-width:1400px;margin:auto;padding:0 24px;display:flex;gap:4px;border-bottom:1px solid var(--line);overflow-x:auto}
nav button{background:none;border:0;padding:10px 14px;color:var(--muted);font:inherit;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
nav button.on{color:var(--ink);border-color:var(--accent);font-weight:600}
main{max-width:1400px;margin:auto;padding:18px 24px 60px}section.tab{display:none}section.tab.on{display:block}
.split{display:grid;grid-template-columns:300px 1fr;gap:16px}@media(max-width:860px){.split{grid-template-columns:1fr}}
.list{background:var(--panel);border:1px solid var(--line);border-radius:10px;max-height:78vh;overflow:auto}
.list input{width:100%;border:0;border-bottom:1px solid var(--line);padding:10px 12px;background:transparent;color:var(--ink);font:inherit}
.item{padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer}.item:hover,.item.on{background:var(--lane)}
.item .t{font-weight:600}.item .m{color:var(--muted);font-size:12px;word-break:break-all}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:14px;overflow:auto}
.card h2{font-size:18px;margin:0 0 4px}.card h3{font-size:15px;margin:16px 0 6px}
.tag{display:inline-block;font-size:11px;border-radius:9px;padding:0 8px;margin-left:6px;border:1px solid var(--line);color:var(--muted);vertical-align:middle}
.tag-ok{color:var(--c);border-color:var(--c)}.tag-guess{color:var(--u);border-color:var(--u)}.tag-ask{color:var(--d);border-color:var(--d)}
.grid{border-collapse:collapse;width:100%;font-size:13px}.grid th,.grid td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
.grid th{background:var(--lane)}code,.code{font-family:SFMono-Regular,Consolas,"Liberation Mono",monospace;font-size:12px}
.code{background:var(--lane);padding:10px;border-radius:6px;white-space:pre-wrap;word-break:break-all}
.loc{color:var(--muted);font-size:12px;font-family:monospace;word-break:break-all}.facts{display:grid;grid-template-columns:3fr 2fr;gap:18px}.grid td:first-child{white-space:nowrap}a{color:var(--accent)}@media(max-width:1100px){.facts{grid-template-columns:1fr}}
svg text{fill:var(--ink);font-size:12px}.lane{fill:var(--lane)}.lane-title{font-weight:600;fill:var(--muted)!important}
.node rect{stroke-width:1.4}.node .n2{fill:var(--muted);font-size:11px}
.node.entry rect{fill:var(--entry);stroke:var(--entry-b)}.node.service rect{fill:var(--service);stroke:var(--service-b)}
.node.dao rect{fill:var(--dao);stroke:var(--dao-b)}.node.table rect{fill:var(--table);stroke:var(--table-b)}
.edge{fill:none;stroke:var(--edge);stroke-width:1.4}.edge.back{stroke-dasharray:4 3}.arrowhead{fill:var(--edge)}
.op-c rect{fill:var(--c)}.op-r rect{fill:var(--r)}.op-u rect{fill:var(--u)}.op-d rect{fill:var(--d)}.op-p rect{fill:var(--p)}
g[class^=op-] text{fill:#fff;font-size:11px;text-anchor:middle}
.state rect{fill:var(--service);stroke:var(--service-b);stroke-width:1.4}.state.init rect{fill:var(--lane);stroke:var(--edge);stroke-dasharray:4 3}
.state text{text-anchor:middle;font-weight:600}.elabel{font-size:11px;fill:var(--muted)!important;text-anchor:middle;paint-order:stroke;stroke:var(--panel);stroke-width:4px}
.cell{text-align:center;font-weight:700}.cell span{display:inline-block;width:18px;border-radius:4px;color:#fff;margin:0 1px}
.cC{background:var(--c)}.cR{background:var(--r)}.cU{background:var(--u)}.cD{background:var(--d)}.cP{background:var(--p)}
.tl{border-left:2px solid var(--line);margin-left:8px;padding-left:18px}.ev{position:relative;margin-bottom:14px}
.ev:before{content:"";position:absolute;left:-25px;top:6px;width:10px;height:10px;border-radius:50%;background:var(--edge)}
.ev.k-finding:before{background:var(--r)}.ev.k-decision:before{background:var(--c)}.ev.k-question:before{background:var(--d)}.ev.k-verify:before{background:var(--u)}.ev.k-task:before{background:var(--p)}
.ev .h{font-weight:600}.steps{font-size:12px;margin:4px 0;padding-left:22px}.ev.k-tool:before{background:transparent;border:2px solid var(--edge)}.ev .ts{color:var(--muted);font-size:12px;margin-right:8px}details summary{cursor:pointer;color:var(--accent)}
.empty{color:var(--muted);padding:20px}.legend span{margin-right:12px;font-size:12px;color:var(--muted)}
.grp{padding:8px 12px 4px;font-size:12px;font-weight:700;color:var(--muted);background:var(--lane);border-bottom:1px solid var(--line)}.grp .m{font-weight:400}
.factbox,.und{border:1px solid var(--line);border-radius:8px;padding:4px 14px 10px;margin-top:12px}.factbox{background:var(--lane)}.fb-h{font-size:12px;color:var(--muted);margin:8px 0 2px;font-weight:600}
.warn{color:var(--d)}.kbpage blockquote{margin:6px 0;color:var(--muted)}
.theme{float:right;background:var(--panel);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:4px 10px;cursor:pointer}
"""

JS = """
const tabs=[...document.querySelectorAll('nav button')];
function show(id){tabs.forEach(b=>b.classList.toggle('on',b.dataset.t===id));document.querySelectorAll('section.tab').forEach(s=>s.classList.toggle('on',s.id===id));try{localStorage.setItem('tmh-tab',id)}catch(e){}}
tabs.forEach(b=>b.onclick=()=>show(b.dataset.t));
try{const t=localStorage.getItem('tmh-tab');if(t&&document.getElementById(t))show(t)}catch(e){}
const items=[...document.querySelectorAll('.item')];
function pick(id){items.forEach(i=>i.classList.toggle('on',i.dataset.f===id));document.querySelectorAll('.flowcard').forEach(c=>c.style.display=c.id==='f-'+id?'block':'none');location.hash=id}
items.forEach(i=>i.onclick=()=>pick(i.dataset.f));
const q=document.getElementById('q');if(q)q.oninput=()=>{const v=q.value.toLowerCase();items.forEach(i=>i.style.display=i.textContent.toLowerCase().includes(v)?'':'none')};
if(items.length){const h=location.hash.slice(1);pick(items.some(i=>i.dataset.f===h)?h:items[0].dataset.f)}
document.querySelectorAll('[data-goto]').forEach(a=>a.onclick=e=>{e.preventDefault();show('flows');pick(a.dataset.goto)});
const kbi=[...document.querySelectorAll('.kbi')];
function kb(path,quiet){if(!document.getElementById('kb-'+path))return;if(!quiet)show('kb');kbi.forEach(i=>i.classList.toggle('on',i.dataset.kb===path));document.querySelectorAll('.kbpage').forEach(c=>c.style.display=c.id==='kb-'+path?'block':'none');const it=kbi.find(i=>i.dataset.kb===path);if(it)it.scrollIntoView({block:'nearest'})}
kbi.forEach(i=>i.onclick=()=>kb(i.dataset.kb));
document.addEventListener('click',e=>{const a=e.target.closest('[data-kb]');if(a&&!a.classList.contains('kbi')){e.preventDefault();kb(a.dataset.kb)}});
const kq=document.getElementById('kq');if(kq)kq.oninput=()=>{const v=kq.value.toLowerCase();kbi.forEach(i=>i.style.display=i.textContent.toLowerCase().includes(v)?'':'none')};
if(kbi.length)kb(kbi[0].dataset.kb,true);
document.querySelector('.theme').onclick=()=>{const r=document.documentElement;r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'};
"""


def _flow_card(f: dict, note: dict | None) -> str:
    badge = ""
    if note:
        badge = '<span class="tag %s">业务说明：%s</span>' % ("tag-ok" if note["status"] in ("已确认", "confirmed") else "tag-ask", esc(note["status"]))
    name = (note and note["title"]) or f["name"] or f["trigger"]
    src = "人工/智能体整理" if note and note["title"] else (f["name_source"] or "无业务名，显示触发方式")
    h = ['<div class="card flowcard" id="f-%s" style="display:none">' % esc(f["id"]),
         '<h2>%s %s</h2>' % (esc(name), badge),
         '<div class="sub">%s · %s · 名称来源：%s · <span class="loc">%s:%d</span></div>' % (esc(f["kind"]), esc(f["trigger"]), esc(src), esc(f["file"]), f["line"]),
         '<h3>调用链 <span class="legend"><span>悬停方框可看文件与行号；虚线表示回到已出现的节点</span></span></h3>']
    if len(f["nodes"]) <= SVG_MAX_NODES:
        h.append(flow_svg(f))
    else:  # long legacy chains read better (and weigh far less) as an indented outline
        from .flow import flow_text
        outline = flow_text(f, max_lines=150).split("\n调用链：\n", 1)[-1].split("\n状态变化：", 1)[0].split("\n业务规则", 1)[0]
        h.append("<pre class='code'>%s</pre><p class='loc'>调用链共 %d 个节点，以缩进文本显示；完整内容：<code>tmh flows %s</code></p>" % (
            esc(outline), len(f["nodes"]), esc(f["id"])))
    ops, more_ops = _dedup(f["data_ops"], lambda o: (o["op"], o["table"], o["via"]), CARD_MAX_ROWS)
    states, more_st = _dedup(f["states"], lambda x: (x["table"], x["column"], tuple(x["from"]), x["to"], x["file"], x["line"]), CARD_MAX_ROWS)
    rules, more_ru = _dedup(f["rules"], lambda r: (r["condition"], r["message"], r["file"], r["line"]), CARD_MAX_ROWS)
    more = lambda n: "<p class='loc'>另有 %d 条未列出，见 <code>tmh flows %s</code></p>" % (n, esc(f["id"])) if n else ""
    h.append('<div class="facts"><div>')
    if ops:
        h.append("<h3>数据操作</h3><table class='grid'><tr><th>操作</th><th>表</th><th>经由</th><th>位置</th></tr>")
        for o in ops:
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td class='loc'>%s:%d</td></tr>" % (OPS[o["op"]][0], esc(o["table"]), esc(o["via"]), esc(o["file"]), o["line"]))
        h.append("</table>" + more(more_ops))
    if states:
        h.append("<h3>状态变化</h3><table class='grid'><tr><th>字段</th><th>从</th><th>到</th><th>位置</th></tr>")
        for s in states:
            h.append("<tr><td>%s.%s</td><td>%s</td><td><b>%s</b></td><td class='loc'>%s:%d</td></tr>" % (esc(s["table"]), esc(s["column"]), esc(" / ".join(s["from"])), esc(s["to"]), esc(s["file"]), s["line"]))
        h.append("</table>" + more(more_st))
    if rules:
        h.append("<h3>代码中的业务规则</h3><table class='grid'><tr><th>条件</th><th>提示 / 异常</th><th>位置</th></tr>")
        for r in rules:
            h.append("<tr><td><code>%s</code></td><td>%s</td><td class='loc'>%s:%d</td></tr>" % (esc(r["condition"]), esc(r["message"] or r["exception"]), esc(r["file"]), r["line"]))
        h.append("</table>" + more(more_ru))
    extra = []
    for t in f["transactions"]:
        extra.append("- 事务：`%s`" % t["method"])
    for s in f["side_effects"]:
        extra.append("- %s：`%s`（%s:%d）" % (s["kind"], s["code"], s["file"], s["line"]))
    for u in _dedup(f["unresolved"], lambda u: u["call"], 20)[0]:
        extra.append("- 未能解析：`%s`，%s" % (u["call"], u["why"]))
    if extra:
        h.append("<h3>事务、外部影响与盲区</h3>" + md("\n".join(extra)))
    sqls = _dedup([o for o in f["data_ops"] if o["sql"]], lambda o: o["sql"], 30)[0]
    if sqls:
        h.append("<details><summary>查看涉及的 SQL</summary>%s</details>" % "".join(
            "<p class='loc'>%s</p><pre class='code'>%s</pre>" % (esc(o["via"]), esc(o["sql"])) for o in sqls))
    h.append("</div><div>")
    h.append("<h3>业务理解 <span class='tag'>人工 / 智能体整理，需人工确认</span></h3>")
    if note:
        body = NOTE_STATUS.sub("", note["text"], count=1)
        body = re.sub(r"^#\s+.*\n", "", body, count=1)
        h.append(md(body) + "<p class='loc'>%s</p>" % esc(note["file"]))
    else:
        h.append("<p class='empty'>还没有整理。让智能体运行 business-flow 技能，或在 <code>.tmh/knowledge/flows/%s.md</code> 中补充业务目的、角色、规则与例外。</p>" % esc(f["id"]))
    h.append("</div></div></div>")
    return "".join(h)


def render(root: Path, data: dict) -> str:
    cfg = cfgmod.load(root)
    flows, sms, matrix = data["flows"], data["state_machines"], data["matrix"]
    notes = _notes(root)
    kb_html, kb_st = _kb_section(root)
    if not kb_st and "tmh kb build" in kb_html and not (cfgmod.tmh_dir(root) / "cache" / "graph.db").exists():
        kb_st = None
    name = cfg.get("project", {}).get("name") or root.name
    tables = matrix["tables"]
    n_rules = sum(len(f["rules"]) for f in flows)
    n_unres = sum(len(f["unresolved"]) for f in flows)
    confirmed = sum(1 for f in flows if notes.get(f["id"], {}).get("status") in ("已确认", "confirmed"))
    stats = [(len(flows), "业务流（入口）"), (len(tables), "涉及的表"), (len(sms), "状态机"), (n_rules, "代码中的规则"),
             ("%d / %d" % (sum(1 for f in flows if f["id"] in notes), confirmed), "已整理 / 已确认说明"), (n_unres, "未能解析的调用")]
    out = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>%s 项目知识与业务流</title><style>%s</style></head><body>" % (esc(name), CSS),
           '<header><button class="theme" type="button">切换明暗</button><h1>%s · 项目知识与业务流</h1><div class="sub">生成于 %s · 由 tmh 从代码静态抽取，事实带文件与行号；“业务理解”栏为人工或智能体整理，以确认状态为准</div><div class="stats">%s</div></header>' % (
               esc(name), time.strftime("%Y-%m-%d %H:%M"), "".join('<div class="stat"><b>%s</b><span>%s</span></div>' % (esc(v), esc(k)) for v, k in stats)),
           '<nav>%s<button data-t="flows"%s>业务流</button><button data-t="states">状态流转</button><button data-t="matrix">表与业务</button><button data-t="process">分析过程</button></nav><main>' % ('<button data-t="kb" class="on">知识库</button>' if kb_st is not None else "", "" if kb_st is not None else ' class="on"')]
    if kb_st is not None:
        out.append(kb_html)
    # flows
    out.append('<section class="tab%s" id="flows">' % ("" if kb_st is not None else " on") + '<div class="split"><div class="list"><input id="q" placeholder="搜索业务名、URL、类名、表名">')
    for f in flows:
        nm = notes.get(f["id"], {}).get("title") or f["name"] or f["trigger"]
        out.append('<div class="item" data-f="%s"><div class="t">%s</div><div class="m">%s · %s</div><div class="m">%s</div></div>' % (
            esc(f["id"]), esc(nm), esc(f["kind"]), esc(f["trigger"]), esc(" ".join("%s:%s" % (t, c) for t, c in f["crud"].items()))))
    if not flows:
        out.append('<div class="empty">没有识别到入口。</div>')
    out.append("</div><div>")
    for f in flows:
        out.append(_flow_card(f, notes.get(f["id"])))
    out.append("</div></div></section>")
    # state machines
    out.append('<section class="tab" id="states">')
    if not sms:
        out.append('<div class="card empty">没有在 SQL 或代码中发现对状态字段（STATUS/STATE/FLAG）的赋值。</div>')
    for sm in sms:
        rows = "".join("<tr><td>%s</td><td><b>%s</b></td><td><a href='#' data-goto='%s'>%s</a></td><td class='loc'>%s:%d</td></tr>" % (
            esc(t["from"]), esc(t["to"]), esc(t["flow"]), esc(t["flow_name"]), esc(t["file"]), t["line"]) for t in sm["transitions"][:200])
        if len(sm["transitions"]) > 200:
            rows += "<tr><td colspan='4' class='loc'>共 %d 条转换，只列前 200 条</td></tr>" % len(sm["transitions"])
        out.append('<div class="card"><h2>%s.%s</h2><div class="sub">从 UPDATE … SET %s = … WHERE %s = … 与 INSERT 推出；“*”表示代码里没有限定原状态</div>%s'
                   "<h3>转换明细</h3><table class='grid'><tr><th>从</th><th>到</th><th>触发的业务</th><th>位置</th></tr>%s</table></div>" % (
                       esc(sm["table"]), esc(sm["column"]), esc(sm["column"]), esc(sm["column"]), state_svg(sm), rows))
    out.append("</section>")
    # matrix
    out.append('<section class="tab" id="matrix"><div class="card"><h2>业务 × 表</h2><div class="sub legend"><span>C 新增</span><span>R 查询</span><span>U 修改</span><span>D 删除</span><span>P 调用存储过程</span>；改一张表之前先看哪些业务在写它</div>')
    mrows = matrix["rows"]
    if len(mrows) * len(tables) > MATRIX_MAX_CELLS:  # large systems: the most-used tables, flows that touch them
        use = Counter(t for r in mrows for t, c in r["cells"].items() if c)
        tables = [t for t, _ in use.most_common(MATRIX_TOP_TABLES)]
        mrows = [r for r in mrows if any(r["cells"].get(t) for t in tables)]
        out.append("<p class='loc'>表太多（%d 张），这里只列被业务流用得最多的 %d 张；某张表的全部用法见知识库里它的页面或 <code>tmh impact 表名</code>。</p>" % (len(matrix["tables"]), len(tables)))
    if mrows:
        out.append("<table class='grid'><tr><th>业务</th>%s</tr>" % "".join("<th>%s</th>" % esc(t) for t in tables))
        for r in mrows:
            nm = notes.get(r["flow"], {}).get("title") or r["label"]
            out.append("<tr><td><a href='#' data-goto='%s'>%s</a></td>%s</tr>" % (esc(r["flow"]), esc(nm), "".join(
                "<td class='cell'>%s</td>" % "".join('<span class="c%s">%s</span>' % (c, c) for c in r["cells"][t]) for t in tables)))
        out.append("</table>")
    else:
        out.append('<p class="empty">没有识别到数据操作。</p>')
    out.append("</div></section>")
    # process
    tl = _timeline(root, flows)
    out.append('<section class="tab" id="process"><div class="card"><h2>分析过程</h2><div class="sub">tmh 命令、智能体用 <code>tmh note</code> 记下的发现与决定、变更契约和独立验证，按时间排列</div><div class="tl">')
    if not tl:
        out.append('<p class="empty">还没有记录。</p>')
    for e in tl:
        body = e.get("body") or ""
        if body and not e.get("html"):
            body = md(body)
        label = {"tool": "操作", "command": "命令", "finding": "发现", "decision": "决定", "question": "待确认", "change": "改动", "verify": "验证", "task": "契约"}.get(e["kind"], e["kind"])
        out.append('<div class="ev k-%s"><div class="h"><span class="ts">%s</span><span class="tag">%s</span> %s</div>%s</div>' % (
            esc(e["kind"]), esc(e["ts"].replace("T", " ")), label, esc(e["title"]) + (' <span class="loc">%s</span>' % esc(e["meta"]) if e.get("meta") else ""),
            ("<details><summary>详情</summary>%s</details>" % body) if body else ""))
    out.append("</div></div></section></main><script>%s</script></body></html>" % JS)
    return "".join(out)


def write(root: Path, data: dict) -> Path:
    d = cfgmod.tmh_dir(root) / "report"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.html"
    p.write_text(render(root, data), encoding="utf-8")
    return p
