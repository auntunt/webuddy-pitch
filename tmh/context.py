"""`tmh context`: the small, relevant slice of project knowledge for one task.

Instead of reading the repository, an agent starts every task with
`tmh context "<需求原文或关键词>"`. The query is matched (Chinese bigrams,
identifier parts, glossary synonyms) against knowledge pages and graph nodes,
then expanded along the graph (flow → tables → their pages, method → flows that
run through it). The answer is a bounded pack: which pages to read, which flows
and tables are involved, which code locations to open, and what is stale.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import kb
from .graph import Graph

ASCII = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
CJK = re.compile(r"[一-鿿]+")
STOP = {"的", "了", "和", "与", "在", "要", "能", "把", "被", "让", "给", "对", "是", "我", "你", "他", "这个", "那个", "需要", "可以", "功能", "支持",
        "get", "set", "the", "and", "for", "to", "of", "in", "a", "an", "is", "id", "impl", "service", "controller", "mapper", "dao"}


# Question words carry no business meaning; left in, "审批是在哪里实现的" matches every page that says 实现 or 哪里.
QUESTION = re.compile(r"(在哪里|在哪儿|在哪|哪里|哪儿|哪些|哪个|怎么样|怎么|怎样|如何|什么|为什么|为何|是否|有没有|能不能|是不是|实现的?|处理的?|做的|"
                      r"告诉我|请问|帮我|一下|主要|相关|有关|的|了|吗|呢|吧|是)")


# How people describe a fault ("一直转圈", "提交不了") says nothing about which business it is in; left in, these words
# and the bigrams they glue together (单提, 交不) match pages at random.
SYMPTOM = re.compile(r"(一直|总是|老是|经常|突然|今天|好多人|很多人|大家|所有人|月底|急急?|在吗|转圈圈?|卡住了?|卡死|很慢|变慢|好慢|报错了?|出错了?|"
                     r"失败了?|打不开|进不去|没反应|没有反应|白屏|超时|不了|不能|无法|不行|不对|异常|错误|问题|点了?|一下)")

# Business words → what the code and the knowledge base usually call them. A query keeps its own words at full weight;
# these are added at a lower weight so "报销单提交" can find the 单据 domain and its submit/save handlers.
SYNONYMS = {
    "报销": "费用 reimburse expense bx", "借款": "loan borrow jk", "付款": "pay payment fk", "收款": "receipt receive",
    "预算": "budget ys", "合同": "contract ht", "发票": "invoice fp", "凭证": "voucher pz", "资金": "fund funding",
    "审批": "approve approval audit workflow 流程", "审核": "audit check 审批", "流程": "flow workflow process 审批",
    "提交": "submit save commit 保存 审批", "保存": "save 提交", "撤回": "revoke withdraw recall", "退回": "reject back return",
    "作废": "cancel invalid void", "删除": "delete remove", "导出": "export", "导入": "import", "打印": "print",
    "附件": "attach attachment upload file", "上传": "upload", "下载": "download", "登录": "login", "权限": "permission auth role",
    "用户": "user", "部门": "dept department org", "人员": "staff person emp", "档案": "archive", "归档": "archive",
    "查询": "query search list", "列表": "list page", "统计": "stat report", "报表": "report", "消息": "message notice msg",
    "待办": "todo task", "单据": "bill form 表单", "表单": "form bill 单据", "编码": "code rule", "规则": "rule",
}
_SUFFIX_DAN = re.compile(r"([一-鿿]{1,4})单(?!据)")


def query_terms(query: str) -> list[str]:
    """Terms of a question: question and symptom words are cut out first, so they neither match nor glue bigrams together."""
    text = SYMPTOM.sub(" ", QUESTION.sub(" ", query or ""))
    q = [t for t in terms(text) if not _straddles(t, text)]
    return list(dict.fromkeys(q or terms(query)))


def _straddles(t: str, text: str) -> bool:
    """A bigram cut across two known words (销单 in 报销单, 单提 in 单提交) is noise."""
    if len(t) != 2 or not CJK.fullmatch(t) or t in SYNONYMS:
        return False
    for i in [m.start() for m in re.finditer(t, text)]:
        for w in SYNONYMS:
            for m in re.finditer(w, text):
                a, b = m.start(), m.end()
                if a < i + 2 and i < b and not (a <= i and i + 2 <= b):
                    return True
    return False


def expand(query: str, q: list[str]) -> list[str]:
    """Lower-weight terms a query implies: synonyms of its business words, and 单据 for any “XX单”."""
    extra = []
    for word, more in SYNONYMS.items():
        if word in query:
            extra += terms(more)
    if _SUFFIX_DAN.search(query):
        extra += ["单据", "bill", "form"]
    return [t for t in dict.fromkeys(extra) if t not in q]


def terms(text: str) -> list[str]:
    out = []
    for w in ASCII.findall(text or ""):
        parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", w) or [w]
        for p in parts + ([w] if len(parts) > 1 else []):
            p = p.lower()
            if len(p) > 1 and p not in STOP:
                out.append(p)
        if "_" in w:
            out += [x.lower() for x in w.split("_") if len(x) > 1 and x.lower() not in STOP]
    for seg in CJK.findall(text or ""):
        if len(seg) <= 4 and seg not in STOP:
            out.append(seg)
        out += [seg[i:i + 2] for i in range(len(seg) - 1) if seg[i:i + 2] not in STOP]
    return out


def glossary(root: Path) -> list[tuple[str, str]]:
    p = kb.kdir(root) / "glossary.md"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and not set(cells[0]) <= set("-: ") and cells[0] != "业务词":
            rows.append((cells[0], cells[1]))
    return rows


def _docs(root: Path, g: Graph, reg: dict) -> list[dict]:
    docs = []
    for pid, r in reg.items():
        if r.get("orphan"):
            continue
        p = kb.page_path(root, pid)
        if not p.exists():
            continue
        pg = kb.parse_page(p.read_text(encoding="utf-8"))
        # only what a person wrote counts: skeleton headings and （提示） placeholders would match every page
        body = "\n".join(l for l in pg["body"].splitlines() if not re.match(r"\s*(#|（.*）\s*$)", l))
        text = " ".join([pg["meta"].get("title", ""), pg["meta"].get("summary", "")] * 3 + [body, pid])
        docs.append({"id": pid, "type": "page", "text": text, "title": (pg["meta"].get("title", "") + " " + pid).lower()})
    for n in g.nodes():
        if n["kind"] in ("file", "mod", "ext"):
            continue
        d = n["data"]
        text = " ".join(str(x) for x in (n["name"], n["label"], n["id"], d.get("comment", ""), d.get("trigger", ""), d.get("handler", ""),
                                         d.get("entity", ""), " ".join(d.get("crud", {}).keys()),
                                         " ".join(r.get("msg", "") for r in d["rules"] if isinstance(r, dict)) if isinstance(d.get("rules"), list) else "",
                                         " ".join(d.get("texts") or [])))
        docs.append({"id": n["id"], "type": n["kind"], "text": text, "title": ("%s %s" % (n["name"], n["label"] or "")).lower()})
    return docs


# The index (terms of every page and node) takes seconds to build on a large project, and every question,
# ticket and agent run searches it: build it once per knowledge-base version, in memory and in .tmh/cache.
_INDEX: dict = {}


def _stamp(root: Path) -> tuple:
    from .graph import graph_path
    st = []
    for p in (graph_path(root), kb._reg_path(root), kb.kdir(root) / "glossary.md"):
        try:
            st.append(int(p.stat().st_mtime))
        except OSError:
            st.append(0)
    newest, n = 0, 0
    for p in kb.kdir(root).rglob("*.md") if kb.kdir(root).is_dir() else []:
        n += 1
        newest = max(newest, int(p.stat().st_mtime))
    return tuple(st + [newest, n, 3])  # last item: index format


def _build(root: Path, g: Graph, reg: dict) -> dict:
    docs = _docs(root, g, reg)
    dom = {n["id"]: n["domain"] for n in g.nodes() if n.get("domain")}
    meta, post = [], defaultdict(list)
    for i, d in enumerate(docs):
        nid = d["id"]
        dm = nid[4:] if nid.startswith("dom:") else dom.get(nid, "")
        tc = Counter(terms(d["text"]))
        meta.append([nid, d["type"], d["title"], dm, sum(tc.values())])
        for t, c in tc.items():
            post[t].append((i, c))
    return {"docs": meta, "post": dict(post)}


def index(root: Path, g: Graph | None = None, reg: dict | None = None) -> dict:
    import marshal
    from .config import tmh_dir
    key, stamp = str(Path(root).resolve()), _stamp(root)
    hit = _INDEX.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    f = tmh_dir(root) / "cache" / "search.idx"
    ix = None
    try:
        with open(f, "rb") as fh:
            saved = marshal.load(fh)
        if saved.get("stamp") == list(stamp):
            ix = saved["ix"]
    except (OSError, ValueError, EOFError, TypeError, AttributeError):
        ix = None
    if ix is None:
        ix = _build(root, g or Graph(root), reg if reg is not None else kb.load_registry(root))
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                marshal.dump({"stamp": list(stamp), "ix": ix}, fh)
            tmp.replace(f)
        except OSError:
            pass  # a read-only checkout still searches, just without the disk cache
    _INDEX.clear()  # one project's index at a time is plenty for memory
    _INDEX[key] = (stamp, ix)
    return ix


def search(root: Path, query: str, limit: int = 30) -> list[tuple[float, dict]]:
    """Ranked pages and nodes for a request. Two stages: plain term scoring, then the business domains that the
    best hits agree on lift their own flows, tables and code and push down look-alikes from unrelated domains."""
    q = query_terms(query)
    for word, code in glossary(root):
        if word in query or any(t in word for t in q if len(t) >= 2 and re.match(r"[一-鿿]", t)):
            q += terms(code) + [word]
    qw = defaultdict(float)
    for t in q:
        qw[t] = 1.0
    for t in expand(query, q):
        qw.setdefault(t, 0.5)
    ix = index(root)
    docs, post = ix["docs"], ix["post"]
    N = len(docs) or 1
    avg = (sum(d[4] for d in docs) / N) or 1
    acc = defaultdict(float)
    for t, w in qw.items():
        pl = post.get(t)
        if not pl:
            continue
        idf = math.log(1 + N / len(pl)) * (1.5 if len(t) > 3 else 1.0) * w
        for i, c in pl:
            acc[i] += (1 + math.log(c)) * idf
    weight = {"page": 1.6, "flow": 1.4, "tbl": 1.3, "dom": 1.2, "ep": 1.0, "cls": 0.9, "fn": 0.8, "sm": 0.8}
    scored = []
    for i, s in acc.items():
        nid, typ, title, dm, ln = docs[i]
        s /= max(1.0, ln / avg) ** 0.5  # a very long page mentions everything once; don't let length win
        hit = sum(1 for t in qw if len(t) >= 2 and t in title)
        scored.append((s * weight.get(typ, 1.0) * (1 + 0.6 * min(hit, 2)), i))
    scored.sort(key=lambda x: -x[0])
    # stage 2: which domains do the best hits agree on? Domain pages and nodes vote double.
    votes = defaultdict(float)
    for s, i in scored[:80]:
        nid, typ, _, dm, _ = docs[i]
        if dm:
            votes[dm] += s * (2 if nid.startswith("dom:") else 1)
    top = sorted(votes.items(), key=lambda x: -x[1])
    keep = {d for d, v in top[:3] if top and v >= top[0][1] * 0.5}
    if keep and len(top) > len(keep):
        scored = [(s * (1.5 if docs[i][3] in keep else (0.6 if docs[i][3] else 1.0)), i) for s, i in scored]
        scored.sort(key=lambda x: -x[0])
    return [(s, {"id": docs[i][0], "type": docs[i][1], "title": docs[i][2], "domain": docs[i][3]}) for s, i in scored[:limit]]


# ---- optional graph ranker: personalized PageRank over the knowledge graph -----
# Lexical search answers "which page/node mentions these words"; it cannot tell
# that hitting `fn:LeaveService.approve` also makes `flow:post-leave-approve` and
# `tbl:OA_APPROVAL_LOG` relevant. PPR spreads the seed mass along the graph, so a
# node that many high-scoring hits point at (directly or via one hop) rises.
# Every number below is deliberately explicit: the comparison report quotes them.
#
# Edge weights per graph edge kind. `step`/`handles`/`calls` carry the most signal
# (this code runs that code), table read/write edges less (many flows touch a table),
# module dependency edges least (architecture, not behaviour).
PPR_EDGE_WEIGHT = {
    "step": 1.0, "handles": 0.9, "entry": 0.8, "calls": 0.9, "uses": 0.8,
    "reads": 0.6, "writes": 0.7, "in": 0.7, "contains": 0.5,
    "depends": 0.3, "extends": 0.4, "has_state": 0.5, "transition": 0.4, "effect": 0.3,
}
PPR_DAMPING = 0.85       # walker follows the graph 85% of the time, restarts from the seeds
PPR_TOL = 1e-9           # L1 change below which the power iteration has converged
PPR_MAX_ITER = 100       # hard cap; the example graph converges in ~20 iterations
PPR_SEED_HITS = 10       # lexical top-k that form the personalization vector
PPR_LEXICAL_MIX = 0.5    # final score = MIX * lexical + (1-MIX) * ppr (both min-max scaled)
PPR_MIN_REL = 0.005      # drop graph nodes whose PPR mass is below 0.5% of the top node


def personalized_pagerank(root: Path, seeds, graph: Graph | None = None, damping: float = PPR_DAMPING,
                          tol: float = PPR_TOL, max_iter: int = PPR_MAX_ITER,
                          edge_weights: dict | None = None) -> dict[str, float]:
    """Personalized PageRank over graph.db, seeded by lexical hits.

    `seeds` is a mapping or an iterable of (node_id, score) pairs. Returns
    {node_id: score} summing to 1, or {} when no seed exists in the graph.

    The random walk is symmetric: for every edge `src --kind--> dst` the walker
    may move both ways with `PPR_EDGE_WEIGHT[kind]`, because relevance is not
    directional here (a flow implies its handler, a handler implies its flow).
    Parallel edges between the same pair add up. Iteration is the usual
    r <- damping * A^T r + (1 - damping) * p; dangling mass is redistributed by p.
    """
    g = graph or Graph(root)
    close = graph is None
    try:
        try:
            node_ids = {r[0] for r in g.db.execute("SELECT id FROM nodes")}
            rows = list(g.db.execute("SELECT src, dst, kind FROM edges"))
        except Exception as exc:  # a missing/half-written graph must degrade, not crash a pack
            raise ValueError("知识图谱不可读取：%s" % exc)
    finally:
        if close:
            g.db.close()
    weights = PPR_EDGE_WEIGHT if edge_weights is None else edge_weights
    pairs: dict[str, dict[str, float]] = defaultdict(dict)
    for src, dst, kind in rows:
        if src not in node_ids or dst not in node_ids or src == dst:
            continue
        w = float(weights.get(kind, 0.0) or 0.0)
        if w <= 0:
            continue
        pairs[src][dst] = pairs[src].get(dst, 0.0) + w
        pairs[dst][src] = pairs[dst].get(src, 0.0) + w

    raw = dict(seeds) if isinstance(seeds, dict) else dict(seeds or [])
    p = {nid: float(s) for nid, s in raw.items() if nid in node_ids and float(s or 0.0) > 0}
    total = sum(p.values())
    if total <= 0:
        return {}
    p = {nid: s / total for nid, s in p.items()}
    adj = {nid: pairs.get(nid, {}) for nid in node_ids}
    row_sum = {nid: sum(row.values()) for nid, row in adj.items()}
    r = dict(p)
    for _ in range(max(1, int(max_iter))):
        new = {nid: (1.0 - damping) * p.get(nid, 0.0) for nid in node_ids}
        dangling = 0.0
        for nid in sorted(node_ids):
            mass = r.get(nid, 0.0)
            if mass <= 0:
                continue
            row = adj[nid]
            if not row:
                dangling += mass
                continue
            share = damping * mass / row_sum[nid]
            for dst in sorted(row):
                new[dst] += share * row[dst]
        if dangling:
            for nid in sorted(p):
                new[nid] += damping * dangling * p[nid]
        delta = sum(abs(new[nid] - r.get(nid, 0.0)) for nid in node_ids)
        r = new
        if delta < tol:
            break
    return r


def domains_for(root: Path, query: str, n: int = 3) -> list[str]:
    """The business domains a request most likely belongs to, best first."""
    out = []
    for _, d in search(root, query, limit=40):
        if d["domain"] and d["domain"] not in out:
            out.append(d["domain"])
    return out[:n]


def build_context(root: Path, query: str, budget: int = 8000) -> str:
    g = Graph(root)
    reg = kb.load_registry(root)
    hits = search(root, query, limit=40)
    if not hits:
        return "知识库里没有找到和“%s”相关的内容。换个说法（业务词、URL、类名、表名）再试，或者用 tmh where 按关键词搜代码。" % query
    score = defaultdict(float)
    for s, d in hits:
        score[d["id"]] += s
    # spread along the graph so a hit on a method surfaces its flows, a flow its tables, a page its node
    for s, d in hits[:15]:
        nid = d["id"]
        if nid.startswith("fn:"):
            for e in g.inn(nid, "step"):
                score[e["src"]] += s * 0.5
        if nid.startswith("flow:"):
            for e in g.out(nid, "uses"):
                score[e["dst"]] += s * 0.3
            for e in g.out(nid, "in"):
                score[e["dst"]] += s * 0.2
        if nid.startswith("tbl:"):
            for e in g.inn(nid, "uses"):
                score[e["src"]] += s * 0.25
        if nid.startswith("cls:"):
            for e in g.out(nid, "contains"):
                score[e["dst"]] += s * 0.2
    ranked = sorted(score.items(), key=lambda x: -x[1])
    by = defaultdict(list)
    for nid, s in ranked:
        k = kb.page_kind(nid) if (nid == "index" or nid.split(":")[0] in ("flow", "tbl", "dom", "mod")) else nid.split(":")[0]
        by[k].append(nid)
    out = ["# 与“%s”相关的项目知识" % query, ""]
    pages = [p for p in dict.fromkeys(by.get("flow", []) + by.get("dom", []) + by.get("tbl", []) + [n for n, _ in ranked if n in reg]) if p in reg][:7]
    stale = []
    if pages:
        out.append("## 先读这些知识页")
        for pid in pages:
            r = reg[pid]
            st = "过期" if r.get("stale") else r.get("status", kb.STATUS_NEW)
            if r.get("stale"):
                stale.append(pid)
            rel = kb.page_path(root, pid).relative_to(root).as_posix()
            n = g.node(pid)
            title = r.get("title") or (n["name"] if n else "") or pid
            out.append("- [%s] %s `%s`：%s" % (st, title, rel, r.get("summary") or "（还没写说明，只有工具抽取的事实）"))
        out.append("")
    flows, seen = [], set()
    for fid in by.get("flow", []):
        f = g.node(fid)
        if not f:
            continue
        sig = (f["data"].get("trigger"), f["data"].get("handler"), f["file"], f["line"])
        if sig in seen:  # the same entry reached by two ids (e.g. GET and POST mappings) would print twice
            continue
        seen.add(sig)
        flows.append(f)
        if len(flows) == 6:
            break
    if flows:
        out.append("## 相关业务流")
        for f in flows:
            d = f["data"]
            items = sorted(d.get("crud", {}).items(), key=lambda x: (not set(x[1]) & set("CUD"), x[0]))  # writes first
            crud = "、".join("%s(%s)" % (t, o) for t, o in items[:10]) + ("等 %d 张" % len(items) if len(items) > 10 else "")
            name = f["name"] if f["name"] != d.get("trigger") else ""
            out.append("- `%s` %s → `%s` (%s:%d)%s%s" % (d.get("trigger", ""), name, d.get("handler", ""), f["file"], f["line"],
                                                    "；表：" + crud if crud else "", "；域：" + f["domain"] if f["domain"] else ""))
        out.append("")
    tabs = [g.node(t) for t in by.get("tbl", [])[:6]]
    tabs = [t for t in tabs if t]
    if tabs:
        out.append("## 相关表")
        for t in tabs:
            users = g.inn(t["id"], "uses")
            w = sorted({e["src"][5:] for e in users if set(e["op"]) & set("CUD")})
            out.append("- %s%s：被 %d 条业务流使用%s" % (t["name"], "（%s）" % t["data"]["entity"] if t["data"].get("entity") else "", len(users),
                                               "，写入方：" + "、".join(w[:6]) if w else ""))
        out.append("")
    code = [g.node(c) for c in (by.get("fn", []) + by.get("cls", []))[:10]]
    code = [c for c in code if c and c["file"] and not (c["kind"] == "fn" and c["name"] == c["label"].split(".")[0])]
    if code:
        out.append("## 相关代码位置")
        for c in code:
            d = c["data"]
            extra = []
            if d.get("fan_in"):
                extra.append("被 %d 处调用" % d["fan_in"])
            if d.get("comment"):
                extra.append(d["comment"][:40])
            out.append("- `%s` %s:%d-%d%s" % (c["label"], c["file"], c["line"], c["end_line"], "（%s）" % "，".join(extra) if extra else ""))
        out.append("")
    out.append("## 建议")
    out.append("- 先读上面的知识页和业务流说明，再按“相关代码位置”打开文件，不要通读仓库。")
    if flows:
        out.append("- 改动前用 `tmh flows %s` 看完整调用链，用 `tmh impact <类名或表名>` 看影响面。" % flows[0]["id"][5:])
    if stale:
        out.append("- 这些页面已过期，结论可能不准，以代码为准，任务完成后顺手修订：" + "、".join(stale))
    unwritten = [p for p in pages if reg[p].get("status", kb.STATUS_NEW) == kb.STATUS_NEW and not reg[p].get("stale")]
    if unwritten:
        out.append("- 这些页面还没写说明，任务里弄清楚后用 `tmh kb next --page <id>` 补上：" + "、".join(unwritten[:5]))
    text = "\n".join(out)
    if len(text) > budget:
        # Never cut silently: the caller must be able to tell that evidence was
        # left out and where to read it. The notice is counted against the
        # budget, so the returned pack still honours its own limit.
        dropped_chars = len(text) - budget
        marker = ("\n\n…（预算 %d 字符已满：省略 %d 字符未展开；加大 --budget、用 `tmh context --json` "
                  "查看结构化清单，或按页面 id 用 `tmh kb read <id>` 读全文。需求原文与原始证据不受影响。）"
                  % (budget, dropped_chars))
        keep = max(0, budget - len(marker))
        cut = text[:keep]
        if "\n" in cut:
            cut = cut[: cut.rfind("\n")]
        text = cut + marker
    return text
