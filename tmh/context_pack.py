"""Context Pack v2: the bounded, provenance-carrying slice of project knowledge for one task.

Why this module exists
----------------------
`tmh/context.py::build_context` renders one flat text block for one project and,
when the budget runs out, cuts the string. That violates the project-library
design (`docs/design/project-knowledge-library-2026-10-20.md`, §6.6): a short
budget may only limit how much is *expanded*, never silently drop evidence, and
every result must carry its source, version and a way to read the full text.

This module keeps the existing lexical search + graph expansion, but assembles
a structured pack instead:

* one item per fact, each carrying `source` / `source_version` /
  `knowledge_revision` / `path:line` / a `full_text` handle;
* a budget that allocates per section (pages / flows / tables / code) and never
  splits an item — items that do not fit are listed under `omissions` with a
  reason and a full-text handle;
* multiple sources (current project + pinned reference projects), kept apart,
  never merged by symbol name, current project first on ties;
* an explicit `complete` flag and a machine-readable JSON form;
* one `activity.jsonl` record per assembly, so later work (RSI / habit mining /
  knowledge-gap analysis) can see which pack was actually used.

It is deliberately a narrow interface (`assemble`) so the storage backend can
change later without touching callers.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from . import activity, kb
from .context import PPR_LEXICAL_MIX, PPR_MIN_REL, PPR_SEED_HITS, personalized_pagerank, search
from .graph import Graph, graph_path
from .platform.errors import ApiError

SCHEMA = 2
NOTICE = "有来源的检索结果：来源事实不等于当前项目行为验证，也不替代人工验收。"
RANKERS = ("lexical", "ppr")
DEFAULT_RANKER = "lexical"
SECTION_ORDER = ("pages", "flows", "tables", "code")
SECTION_TITLE = {"pages": "知识页", "flows": "相关业务流", "tables": "相关表", "code": "相关代码位置"}
SECTION_WEIGHT = {"pages": 0.42, "flows": 0.20, "tables": 0.14, "code": 0.16}
META_RESERVE = 0.08  # headers, source lines, omission notices, advice
PAGE_SECTIONS = {"index", "dom", "flow", "tbl", "mod"}


def _git_head(root: Path) -> str:
    try:
        from .platform.project_git import read
        scoped = read(root, ('rev-parse', '--verify', 'HEAD^{commit}'))
        if scoped is not None:
            return scoped.stdout.decode('utf-8', 'replace').strip() if scoped.returncode == 0 else ''
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError, ValueError, ApiError):
        return ""
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""


def _knowledge_revision(root: Path) -> str:
    """A cheap, reproducible fingerprint of the knowledge the pack was built from."""
    h = hashlib.sha256()
    for p in (graph_path(root), kb._reg_path(root), kb.kdir(root) / "glossary.md"):
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"-")
    return h.hexdigest()[:12]


def _source(spec, index: int) -> dict:
    if isinstance(spec, (str, Path)):
        spec = {"root": spec}
    root = Path(spec.get("root", ".")).resolve()
    label = spec.get("label") or (root.name or "source-%d" % index)
    out = {"id": spec.get("id") or label, "label": label, "root": str(root),
           "current": bool(spec.get("current", index == 0)), "available": False,
           "revision": "", "knowledge_revision": "", "error": ""}
    if not root.is_dir():
        out["error"] = "目录不存在或不可访问"
        return out
    if not graph_path(root).exists():
        out["error"] = "还没有知识库（先运行 tmh kb build）"
        return out
    out["available"] = True
    out["revision"] = _git_head(root)
    out["knowledge_revision"] = _knowledge_revision(root)
    return out


def _excerpt_page(text: str, record: dict) -> str:
    summary = (record.get("summary") or "").strip()
    if summary:
        return summary[:180]
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("（") or line.startswith(">"):
            continue
        return line[:180]
    return "（还没写说明，只有工具抽取的事实）"


def _page_item(root: Path, reg: dict, pid: str, score: float) -> dict | None:
    record = reg.get(pid) or {}
    path = kb.page_path(root, pid)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    page = kb.parse_page(text)
    title = record.get("title") or page["meta"].get("title") or pid
    rel = path.relative_to(root).as_posix()
    return {
        "id": pid, "section": "pages", "kind": "page:" + kb.page_kind(pid), "title": title,
        "domain": "", "score": round(score, 4), "status": record.get("status") or kb.STATUS_NEW,
        "stale": bool(record.get("stale")), "path": rel, "line": 1, "end_line": 0,
        "excerpt": _excerpt_page(page["body"], record), "full_text": "tmh kb read %s" % pid,
    }


def _node_item(g: Graph, nid: str, score: float) -> dict | None:
    node = g.node(nid)
    if not node:
        return None
    data = node.get("data") or {}
    if node["kind"] == "flow":
        tables = sorted((data.get("crud") or {}).items(),
                        key=lambda kv: (not (set(kv[1]) & set("CUD")) if isinstance(kv[1], (set, list, str)) else True, kv[0]))
        shown = "、".join("%s(%s)" % (t, "".join(data["crud"][t]) if isinstance(data["crud"][t], (list, tuple)) else data["crud"][t])
                         for t in [t for t, _ in tables[:8]])
        return {
            "id": nid, "section": "flows", "kind": "flow", "title": node.get("label") or node["name"],
            "domain": node.get("domain") or "", "score": round(score, 4), "status": "", "stale": False,
            "path": node.get("file") or "", "line": int(node.get("line") or 0),
            "end_line": int(node.get("end_line") or 0),
            "excerpt": "入口 %s → %s%s" % (data.get("trigger", ""), data.get("handler", ""),
                                           "；表：" + shown if shown else ""),
            "full_text": "tmh flows %s" % nid[5:],
        }
    if node["kind"] == "tbl":
        return {
            "id": nid, "section": "tables", "kind": "table", "title": node["name"],
            "domain": node.get("domain") or "", "score": round(score, 4), "status": "", "stale": False,
            "path": node.get("file") or "", "line": int(node.get("line") or 0), "end_line": 0,
            "excerpt": "业务对象 %s" % data["entity"] if data.get("entity") else "被业务流读写的表",
            "full_text": "tmh kb show %s" % nid,
        }
    if node["kind"] in ("fn", "cls"):
        extra = []
        if data.get("fan_in"):
            extra.append("被 %d 处调用" % data["fan_in"])
        if data.get("comment"):
            extra.append(str(data["comment"])[:60])
        return {
            "id": nid, "section": "code", "kind": node["kind"], "title": node.get("label") or node["name"],
            "domain": node.get("domain") or "", "score": round(score, 4), "status": "", "stale": False,
            "path": node.get("file") or "", "line": int(node.get("line") or 0),
            "end_line": int(node.get("end_line") or 0), "excerpt": "；".join(extra),
            "full_text": "%s:%s-%s" % (node.get("file") or "", node.get("line") or 0, node.get("end_line") or 0),
        }
    return None


def _ppr_scores(root: Path, hits: list[tuple[float, dict]], g: Graph) -> dict[str, float]:
    """Blend lexical hit scores with personalized PageRank over the graph.

    The lexical top hits become the personalization vector; PPR then spreads that
    relevance to nodes the hits imply. Both score sets are min-max scaled so the
    mix weight is meaningful, and nodes only one ranker knows keep a partial score:
    graph nodes get lexical + ppr, knowledge-only pages (e.g. `index`) get lexical.

    PPR mass is defined over the whole graph, so its tail is cut: nodes the walk
    barely reaches (below `PPR_MIN_REL` of the top PPR score) are dropped. Without
    that cut the ranker would hand the pack the entire graph and inflate the token
    bill with facts no hit implies.
    """
    lex = {d["id"]: float(s) for s, d in hits}
    seeds = [(d["id"], float(s)) for s, d in hits[:PPR_SEED_HITS] if nid_is_graph_node(d["id"])]
    ppr = personalized_pagerank(root, seeds, graph=g)
    if not ppr:
        return lex
    lmax = max(lex.values()) or 1.0
    pmax = max(ppr.values()) or 1.0
    floor = pmax * PPR_MIN_REL
    keep = {nid for nid, s in ppr.items() if s >= floor}
    ids = set(lex) | keep
    return {nid: PPR_LEXICAL_MIX * (lex.get(nid, 0.0) / lmax) + (1.0 - PPR_LEXICAL_MIX) * (ppr.get(nid, 0.0) / pmax)
            for nid in ids}


def nid_is_graph_node(nid: str) -> bool:
    return nid.split(":", 1)[0] in ("flow", "tbl", "fn", "cls", "dom", "mod", "ep", "sm")


def collect(root: Path, query: str, limit: int = 40, ranker: str = DEFAULT_RANKER,
            params: dict | None = None) -> list[dict]:
    """Structured hits for one source: lexical search, then one step of graph expansion.

    `ranker="ppr"` replaces that one-step expansion with a personalized PageRank
    pass seeded by the lexical hits (see `tmh.context.personalized_pagerank`).
    The default stays lexical, so existing callers see byte-identical output.
    `params` is passed through to `tmh.context.search` for tuning experiments only.
    """
    if ranker not in RANKERS:
        raise ValueError("未知 ranker：%r（可选 %s）" % (ranker, "、".join(RANKERS)))
    reg = kb.load_registry(root)
    hits = search(root, query, limit=limit, params=params)
    g = Graph(root)
    try:
        if ranker == "ppr":
            score = _ppr_scores(root, hits, g)
        else:
            score = {}
            for s, d in hits:
                score[d["id"]] = score.get(d["id"], 0.0) + s
            # One propagation step: a hit on a method surfaces the flows that run it,
            # a flow surfaces its tables, a class surfaces its methods. This is the
            # same judgement the old build_context encoded, kept explicit here.
            for s, d in hits[:15]:
                nid = d["id"]
                if nid.startswith("fn:"):
                    for e in g.inn(nid, "step"):
                        score[e["src"]] = score.get(e["src"], 0.0) + s * 0.5
                elif nid.startswith("flow:"):
                    for e in g.out(nid, "uses"):
                        score[e["dst"]] = score.get(e["dst"], 0.0) + s * 0.3
                    for e in g.out(nid, "in"):
                        score[e["dst"]] = score.get(e["dst"], 0.0) + s * 0.2
                elif nid.startswith("tbl:"):
                    for e in g.inn(nid, "uses"):
                        score[e["src"]] = score.get(e["src"], 0.0) + s * 0.25
                elif nid.startswith("cls:"):
                    for e in g.out(nid, "contains"):
                        score[e["dst"]] = score.get(e["dst"], 0.0) + s * 0.2

        items = []
        for nid, s in sorted(score.items(), key=lambda kv: (-kv[1], kv[0])):
            if nid in reg:
                item = _page_item(root, reg, nid, s)
            else:
                item = _node_item(g, nid, s)
            if item:
                items.append(item)
        return items
    finally:
        g.db.close()


def _render_item(item: dict) -> str:
    head = "- "
    where = ""
    if item["path"]:
        where = " `%s%s`" % (item["path"], ":%d" % item["line"] if item["line"] else "")
    meta = []
    if item["section"] == "pages":
        meta.append("[%s]" % ("过期" if item["stale"] else item["status"]))
    if item["domain"]:
        meta.append("域：" + item["domain"])
    tail = ("（%s）" % "，".join(meta)) if meta else ""
    body = (" " + item["excerpt"]) if item["excerpt"] else ""
    # Keep the canonical id visible in the rendered text: downstream tools
    # (kb follow-up, orchestra, server) extract `flow:`/`tbl:` ids from the
    # agent's reading and result text. A namespaced id still contains the plain
    # `flow:<name>` substring, so legacy regexes keep working.
    ident = (" `%s`" % item["id"]) if item.get("id") else ""
    return head + item["title"] + tail + ident + where + body


def pack(items: list[dict], budget: int = 8000) -> dict:
    """Allocate the budget per section, fit whole items only, report what was left out."""
    budget = max(200, int(budget))
    usable = max(120, int(budget * (1 - META_RESERVE)))
    alloc = {k: max(40, int(usable * w)) for k, w in SECTION_WEIGHT.items()}
    chosen: list[dict] = []
    omitted: list[dict] = []
    per_section: dict[str, dict] = {k: {"count": 0, "bytes": 0} for k in SECTION_ORDER}

    grouped = {k: [i for i in items if i["section"] == k] for k in SECTION_ORDER}
    for section in SECTION_ORDER:
        for item in grouped[section]:
            cost = len(_render_item(item)) + 1
            if per_section[section]["bytes"] + cost > alloc[section]:
                continue  # kept for the spill-over pass below
            item = dict(item, render=_render_item(item))
            chosen.append(item)
            per_section[section]["count"] += 1
            per_section[section]["bytes"] += cost

    # Unused section capacity may still help lower-priority hits of other sections.
    picked = {i["id"] for i in chosen}
    leftover = sorted((i for i in items if i["id"] not in picked), key=lambda i: (-i["score"], i["id"]))
    used = sum(len(i["render"]) + 1 for i in chosen)
    for item in leftover:
        cost = len(_render_item(item)) + 1
        if used + cost > usable:
            omitted.append(_omission(item, "budget"))
            continue
        item = dict(item, render=_render_item(item))
        chosen.append(item)
        used += cost
        per_section[item["section"]]["count"] += 1
        per_section[item["section"]]["bytes"] += cost
    chosen.sort(key=lambda i: (SECTION_ORDER.index(i["section"]), -i["score"], i["id"]))
    return {"items": chosen, "omissions": omitted, "sections": per_section, "usable": usable}


def _omission(item: dict, reason: str) -> dict:
    return {"id": item["id"], "section": item["section"], "title": item["title"],
            "reason": reason, "full_text": item["full_text"], "source": item.get("source", "")}


def _render_text(result: dict) -> str:
    lines = ["# 与“%s”相关的项目知识（context pack v%d）" % (result["query"], SCHEMA), ""]
    flag = "完整" if result["complete"] else "部分"
    # %06d keeps the header width stable while the exact used-count is still being fitted.
    lines.append("> 预算 %d 字符，已用 %06d；%s。%s" % (result["budget"], result["used"], flag, NOTICE))
    lines.append("")
    lines.append("## 来源")
    for src in result["sources"]:
        if src["available"]:
            lines.append("- %s @ %s · 知识修订 %s%s" % (
                src["label"], (src["revision"] or "-")[:12], src["knowledge_revision"],
                "（当前项目）" if src["current"] else "（参考来源）"))
        else:
            lines.append("- %s：不可用（%s）" % (src["label"], src["error"]))
    lines.append("")
    for section in SECTION_ORDER:
        items = [i for i in result["items"] if i["section"] == section]
        if not items:
            continue
        lines.append("## %s（%d）" % (SECTION_TITLE[section], len(items)))
        for item in items:
            lines.append(item["render"])
        lines.append("")
    if result["omissions"] or result.get("omissions_capped"):
        lines.append("## 未展开（预算不足，仍可读全文）")
        for o in result["omissions"]:
            lines.append("- `%s`（%s，原因：%s）→ %s" % (o["id"], o["title"], o["reason"], o["full_text"]))
        if result.get("omissions_capped"):
            lines.append("- …另有 %d 条未列出（`--json` 查看完整清单；它们同样可读全文）" % result["omissions_capped"])
        lines.append("")
    lines.append("## 怎么用")
    lines.append("- 需要某条全文：按上面的 full-text 命令读取；预算只影响本包展开范围，需求原文和原始证据不受影响。")
    lines.append("- 机器可读：`tmh context --json`；增加参考来源：`tmh context --source <项目目录>`。")
    return "\n".join(lines)


def rendered_text(result: dict) -> str:
    """The text a caller would receive for an assembled JSON pack.

    `assemble(json_mode=True)` drops the per-item `render` strings; a quality
    measurement still has to know what the agent actually pays in tokens, so this
    re-renders exactly the same view (same item order, same omission listing).
    """
    items = [dict(i, render=_render_item(i)) for i in result["items"]]
    omissions = list(result.get("omissions") or [])
    visible = omissions[:3]
    return _render_text({**result, "items": items, "omissions": visible,
                         "omissions_capped": len(omissions) - len(visible)})


def assemble(sources, query: str, budget: int = 8000, json_mode: bool = False,
             require_all: bool = False, log: bool = True, ranker: str = DEFAULT_RANKER,
             params: dict | None = None) -> dict | str:
    """Build one context pack across the given sources.

    `sources` may be paths or dicts: {"root", "label", "current"}. The current
    project goes first; reference sources are kept as separate namespaces and
    are never merged with it by symbol name.

    `ranker` selects how hits are ordered: "lexical" (default, unchanged) or
    "ppr" (optional personalized-PageRank re-ranking, see `collect`). `params`
    overrides lexical scoring constants for tuning experiments only.
    """
    if ranker not in RANKERS:
        raise ValueError("未知 ranker：%r（可选 %s）" % (ranker, "、".join(RANKERS)))
    query = (query or "").strip()
    specs = [_source(s, i) for i, s in enumerate(sources or [])]
    # Two projects may share a directory name (e.g. two checkouts of the same
    # product). Labels and ids are namespaced so their facts can never collide.
    seen_ids: dict[str, int] = {}
    seen_labels: dict[str, int] = {}
    for i, spec in enumerate(specs):
        n = seen_ids.get(spec["id"], 0)
        seen_ids[spec["id"]] = n + 1
        if n:
            spec["id"] = "%s#%d" % (spec["id"], i)
        m = seen_labels.get(spec["label"], 0)
        seen_labels[spec["label"]] = m + 1
        if m:
            spec["label"] = "%s#%d" % (spec["label"], i)
    if not specs:
        raise ValueError("至少需要一个知识来源")
    unavailable = [s for s in specs if not s["available"]]
    if require_all and unavailable:
        raise ValueError("来源不可用，不能静默降级：" + "；".join("%s：%s" % (s["label"], s["error"]) for s in unavailable))

    merged: list[dict] = []
    for spec in specs:
        if not spec["available"]:
            continue
        try:
            found = collect(Path(spec["root"]), query, ranker=ranker, params=params)
        except (OSError, ValueError, FileNotFoundError) as exc:
            spec["available"] = False
            spec["error"] = "检索失败：%s" % exc
            continue
        for item in found:
            item = dict(item, source=spec["label"], source_version=spec["revision"],
                        knowledge_revision=spec["knowledge_revision"], current=spec["current"])
            item["id"] = "%s:%s" % (spec["id"], item["id"])  # never merge two projects' ids
            merged.append(item)
    merged.sort(key=lambda i: (not i["current"], -i["score"], i["id"]))

    packed = pack(merged, budget)
    all_sources_available = all(s["available"] for s in specs)
    shown_items = list(packed["items"])
    visible_omissions = list(packed["omissions"][:3])
    hidden_count = max(0, len(packed["omissions"]) - len(visible_omissions))
    dropped_omissions: list[dict] = []
    static = {"schema": SCHEMA, "query": query, "budget": budget, "sources": specs, "notice": NOTICE}

    def rendered():
        return _render_text({**static, "items": shown_items, "omissions": visible_omissions,
                             "omissions_capped": hidden_count,
                             "complete": not visible_omissions and not hidden_count and all_sources_available,
                             "used": 999999})

    text = rendered()
    # Fit the text without ever splitting an item. Order of sacrifice is
    # explicit: shrink the omission listing to one line first (the count stays
    # reported), then drop the lowest-scored item, then finally the last line.
    while len(text) > budget:
        if len(visible_omissions) > 1:
            visible_omissions.pop()
            hidden_count += 1
        elif shown_items:
            dropped = shown_items.pop()
            omitted = _omission(dropped, "total-budget")
            dropped_omissions.append(omitted)
            if not visible_omissions:
                visible_omissions.append(omitted)
            else:
                hidden_count += 1
        elif visible_omissions:
            visible_omissions.pop()
            hidden_count += 1
        else:
            break
        text = rendered()
    used = len(text)
    text = text.replace("已用 999999", "已用 %06d" % used)
    sections = {k: {"count": sum(1 for i in shown_items if i["section"] == k),
                    "bytes": sum(len(i["render"]) + 1 for i in shown_items if i["section"] == k)}
                for k in SECTION_ORDER}
    base = {
        **static,
        "used": used,
        # The JSON keeps every omission (section-packed and fit-dropped); the
        # text view may show fewer lines but always reports the hidden count.
        "omissions": packed["omissions"] + dropped_omissions,
        "omissions_capped": hidden_count,
        "complete": not packed["omissions"] and not dropped_omissions and all_sources_available,
        "sections": sections,
        "items": [{k: v for k, v in i.items() if k != "render"} for i in shown_items],
    }

    if log:
        log_root = Path(specs[0]["root"])
        activity.log(log_root, "context", query, budget=budget, used=used,
                     sources=[{"label": s["label"], "revision": s["revision"], "available": s["available"]}
                              for s in specs],
                     items=len(base["items"]), omitted=len(base["omissions"]), complete=base["complete"])
    if json_mode:
        return base
    return text

