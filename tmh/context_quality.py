"""A ruler for "context supply": does a query return the knowledge an agent needs?

The knowledge base had no way to answer that. This module loads the golden set
(``tests/fixtures/context_golden.json``: real customer-style Chinese questions →
the pages/nodes a correct answer must contain), runs the real retrieval stack
(``tmh.context.search`` + ``tmh.context_pack.collect`` and ``assemble``) and
reports:

* ``recall@5`` / ``recall@10`` — of the ids the question needs, how many are in
  the top 5 / top 10 results;
* ``precision@5`` — how many of the top 5 results are needed ids;
* ``MRR`` — 1/rank of the first needed id;
* ``tokens`` — estimated size of the rendered pack (what the agent is charged),
  using a tokenizer-free estimate documented in ``estimate_tokens``;
* ``tokens_per_needed_file`` — pack tokens divided by the needed ids actually
  surfaced, i.e. how expensive one useful fact is;
* ``budget_omission_rate`` — share of needed ids that fell out of the pack
  because of the budget (should be small; an omission is reported, never silent).

Everything is computed from real outputs; no target numbers are stored here.
Run ``benchmarks/run_context_quality.py`` for the lexical-vs-PPR report.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import kb
from .context_pack import DEFAULT_RANKER, RANKERS, assemble, collect, rendered_text

SCHEMA = 1
GOLDEN_REL = Path("tests") / "fixtures" / "context_golden.json"
TOP_K = 5
TOKENS_AT = (5, 10)
CJK_CHAR = re.compile(r"[一-鿿豈-﫿]")  # CJK unified ideographs (incl. compatibility blocks)
ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


# ---- golden set -------------------------------------------------------------
def default_golden(root: Path | None = None) -> Path:
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    return root / GOLDEN_REL


def load_golden(path: Path | str | None = None, root: Path | None = None) -> dict:
    """Load and structurally validate the golden queries."""
    path = Path(path) if path else default_golden(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("queries"), list) or not data["queries"]:
        raise ValueError("golden 集缺少 queries：%s" % path)
    ids, queries = set(), set()
    for i, q in enumerate(data["queries"]):
        where = "queries[%d]" % i
        if not isinstance(q.get("query"), str) or not q["query"].strip():
            raise ValueError("%s.query 为空" % where)
        expect = q.get("expect")
        if not isinstance(expect, list) or not expect or not all(isinstance(x, str) and x for x in expect):
            raise ValueError("%s.expect 必须是非空的 id 字符串数组" % where)
        if q["query"] in queries:
            raise ValueError("%s.query 重复：%s" % (where, q["query"]))
        queries.add(q["query"])
        qid = q.get("id") or "q%02d" % (i + 1)
        if qid in ids:
            raise ValueError("%s.id 重复：%s" % (where, qid))
        ids.add(qid)
    return data


def known_ids(root: Path) -> set[str]:
    """Every id retrieval can return for this project: knowledge pages + graph nodes."""
    from .graph import Graph

    ids = set(kb.load_registry(root))
    g = Graph(root)
    try:
        ids |= {n["id"] for n in g.nodes()}
    finally:
        g.db.close()
    return ids


def validate_golden(golden: dict, root: Path) -> list[str]:
    """Ids that the knowledge base of ``root`` does not contain (should be empty)."""
    known = known_ids(root)
    bad = []
    for q in golden["queries"]:
        for eid in q["expect"]:
            if eid not in known:
                bad.append("%s: %s" % (q.get("id") or q["query"], eid))
    return bad


# ---- measurement primitives -------------------------------------------------
def estimate_tokens(text: str) -> int:
    """Tokenizer-free token estimate for mixed Chinese/code context.

    One token per CJK character plus one per ASCII word (matching the rough
    cl100k behaviour on Chinese and identifiers); whitespace and punctuation are
    ignored, which under-counts layout by a few percent. It is a consistent
    yardstick for comparing rankers, not a billing figure.
    """
    text = text or ""
    return len(CJK_CHAR.findall(text)) + len(ASCII_WORD.findall(text))


def ranked_ids(root: Path, query: str, ranker: str = DEFAULT_RANKER, limit: int = 40) -> list[str]:
    """The ranked ids the context pack would consider for a query."""
    return [item["id"] for item in collect(Path(root), query, limit=limit, ranker=ranker)]


def _ranks(ranked: list[str], expect: list[str]) -> dict[str, int | None]:
    pos = {}
    for i, nid in enumerate(ranked):
        pos.setdefault(nid, i + 1)
    return {eid: pos.get(eid) for eid in dict.fromkeys(expect)}


def retrieval_metrics(ranks: dict[str, int | None]) -> dict:
    """recall@5/@10, precision@5, MRR from one query's ranks."""
    hits = {k: 0 for k in TOKENS_AT}
    first = None
    for rank in ranks.values():
        if rank is None:
            continue
        first = rank if first is None else min(first, rank)
        for k in TOKENS_AT:
            if rank <= k:
                hits[k] += 1
    n = max(1, len(ranks))
    return {
        "recall@5": round(hits[5] / n, 4),
        "recall@10": round(hits[10] / n, 4),
        "precision@5": round(hits[5] / float(TOP_K), 4),
        "mrr": round(1.0 / first, 4) if first else 0.0,
    }


def pack_metrics(root: Path, query: str, expect: list[str], ranker: str = DEFAULT_RANKER,
                 budget: int = 8000, label: str = "oa") -> dict:
    """What the assembled pack actually contains and costs for one query."""
    root = Path(root)
    res = assemble([{"root": str(root), "label": label, "current": True}], query,
                   budget=budget, json_mode=True, log=False, ranker=ranker)
    prefix = (res["sources"][0]["id"] if res["sources"] else label) + ":"
    item_ids = [i["id"][len(prefix):] if i["id"].startswith(prefix) else i["id"] for i in res["items"]]
    omitted_ids = [o["id"][len(prefix):] if o["id"].startswith(prefix) else o["id"]
                   for o in res.get("omissions") or []]
    want = list(dict.fromkeys(expect))
    covered = [eid for eid in want if eid in item_ids]
    omitted = [eid for eid in want if eid in omitted_ids and eid not in item_ids]
    missing = [eid for eid in want if eid not in item_ids and eid not in omitted_ids]
    tokens = estimate_tokens(rendered_text(res))
    return {
        "budget": budget,
        "used": res["used"],
        "tokens": tokens,
        "items": len(item_ids),
        "covered": covered,
        "omitted": omitted,
        "missing": missing,
        "coverage": round(len(covered) / float(len(want)), 4),
        "tokens_per_needed_file": round(tokens / float(len(covered)), 4) if covered else None,
        "budget_omission_rate": round(len(omitted) / float(len(want)), 4),
        "complete": bool(res["complete"]),
    }


def _mean(values: list[float]) -> float:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else 0.0


def evaluate(root: Path, golden: dict | None = None, rankers=("lexical", "ppr"),
             budgets=(4000, 8000), limit: int = 40) -> dict:
    """Run the whole golden set through every ranker and budget; return the report body.

    Deterministic: no timestamps or absolute paths that vary between machines.
    """
    root = Path(root)
    golden = golden or load_golden(root=Path(__file__).resolve().parent.parent)
    unknown = [r for r in rankers if r not in RANKERS]
    if unknown:
        raise ValueError("未知 ranker：%s" % "、".join(unknown))
    report = {
        "schema": SCHEMA,
        "project": golden.get("project") or root.name,
        "queries": len(golden["queries"]),
        "rankers": {},
        "budgets": [int(b) for b in budgets],
        "per_query": [],
    }
    for ranker in rankers:
        report["rankers"][ranker] = {"retrieval": {}, "packs": {str(b): {} for b in budgets}}
    rows = []
    for q in golden["queries"]:
        expect = list(dict.fromkeys(q["expect"]))
        row = {"id": q.get("id") or "q%02d" % (len(rows) + 1), "query": q["query"],
               "expect": expect, "notes": q.get("notes", ""), "budget_hint": q.get("budget", 8000),
               "rankers": {}}
        for ranker in rankers:
            ranked = ranked_ids(root, q["query"], ranker=ranker, limit=limit)
            ranks = _ranks(ranked, expect)
            row["rankers"][ranker] = {"ranks": ranks, "retrieval": retrieval_metrics(ranks), "packs": {}}
            for budget in budgets:
                row["rankers"][ranker]["packs"][str(budget)] = pack_metrics(
                    root, q["query"], expect, ranker=ranker, budget=budget)
        rows.append(row)
    report["per_query"] = rows

    for ranker in rankers:
        ret = [row["rankers"][ranker]["retrieval"] for row in rows]
        report["rankers"][ranker]["retrieval"] = {
            "recall@5": _mean([r["recall@5"] for r in ret]),
            "recall@10": _mean([r["recall@10"] for r in ret]),
            "precision@5": _mean([r["precision@5"] for r in ret]),
            "mrr": _mean([r["mrr"] for r in ret]),
            "perfect@5": _mean([1.0 if r["recall@5"] >= 1.0 else 0.0 for r in ret]),
        }
        for budget in budgets:
            packs = [row["rankers"][ranker]["packs"][str(budget)] for row in rows]
            covered = sum(len(p["covered"]) for p in packs)
            expected = sum(len(p["covered"]) + len(p["omitted"]) + len(p["missing"]) for p in packs)
            tokens = sum(p["tokens"] for p in packs)
            report["rankers"][ranker]["packs"][str(budget)] = {
                "tokens_mean": round(tokens / float(len(packs)), 2),
                "tokens_total": tokens,
                "coverage": round(covered / float(expected), 4) if expected else 0.0,
                "tokens_per_needed_file": round(tokens / float(covered), 2) if covered else None,
                "budget_omission_rate": round(sum(len(p["omitted"]) for p in packs) / float(expected), 4) if expected else 0.0,
                "missing_rate": round(sum(len(p["missing"]) for p in packs) / float(expected), 4) if expected else 0.0,
                "complete_rate": _mean([1.0 if p["complete"] else 0.0 for p in packs]),
                "items_mean": round(sum(p["items"] for p in packs) / float(len(packs)), 2),
                "used_mean": round(sum(p["used"] for p in packs) / float(len(packs)), 1),
            }
    return report


# ---- rendering ---------------------------------------------------------------
def render_markdown(report: dict, extra: dict | None = None) -> str:
    """Human-readable comparison report (same numbers as the JSON body)."""
    lines = ["# 上下文质量对比报告：lexical vs PPR", ""]
    lines.append("- 项目：`%s` · golden 查询 %d 条" % (report.get("project", "?"), report["queries"]))
    lines.append("- rankers：%s；预算档：%s 字符" % ("、".join(report["rankers"]), "、".join(str(b) for b in report["budgets"])))
    if extra:
        for key in ("golden", "generated_at", "machine", "python"):
            if extra.get(key):
                lines.append("- %s：%s" % (key, extra[key]))
    lines.append("")
    lines.append("## 检索质量（top-40 候选池，无需组装）")
    lines.append("")
    lines.append("| ranker | recall@5 | recall@10 | precision@5 | MRR | perfect@5 |")
    lines.append("|---|---|---|---|---|---|")
    for ranker, data in report["rankers"].items():
        r = data["retrieval"]
        lines.append("| %s | %.4f | %.4f | %.4f | %.4f | %.4f |" % (
            ranker, r["recall@5"], r["recall@10"], r["precision@5"], r["mrr"], r["perfect@5"]))
    lines.append("")
    lines.append("## 打包质量与 token 成本（assemble 真实输出）")
    lines.append("")
    lines.append("| ranker | 预算 | tokens/包(均值) | 覆盖 needed id | tokens/needed file | 预算遗漏率 | 未检索到 | 完整包比例 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for ranker, data in report["rankers"].items():
        for budget, p in data["packs"].items():
            tpf = "-" if p["tokens_per_needed_file"] is None else "%.2f" % p["tokens_per_needed_file"]
            lines.append("| %s | %s | %.1f | %.4f | %s | %.4f | %.4f | %.4f |" % (
                ranker, budget, p["tokens_mean"], p["coverage"], tpf,
                p["budget_omission_rate"], p["missing_rate"], p["complete_rate"]))
    lines.append("")
    lines.append("## 指标定义")
    lines.append("- recall@k：每条查询需要 id 中出现在前 k 的比例，再对全部查询取均值。")
    lines.append("- precision@5：前 5 条里命中需要 id 的数量 / 5。")
    lines.append("- MRR：第一个正确 id 排名的倒数（无命中记 0），再取均值。")
    lines.append("- tokens：用 `tmh.context_quality.estimate_tokens` 估算的实际渲染包大小（1 个汉字 / 1 个 ASCII 词 ≈ 1 token）。")
    lines.append("- tokens/needed file：所有查询包 tokens 总和 / 实际被包覆盖的 needed id 总数。")
    lines.append("- 预算遗漏率：因预算被列进 `omissions` 的 needed id / needed id 总数。")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="上下文质量度量（需先建好知识库：tmh kb build）")
    ap.add_argument("--root", default="examples/legacy-java-oa", help="已有知识库的项目目录")
    ap.add_argument("--golden", default="", help="golden 集路径（默认仓库内 tests/fixtures/context_golden.json）")
    ap.add_argument("--rankers", default="lexical,ppr")
    ap.add_argument("--budgets", default="4000,8000")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--md-out", default="")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    golden = load_golden(args.golden or None)
    report = evaluate(root, golden, rankers=tuple(args.rankers.split(",")),
                      budgets=tuple(int(b) for b in args.budgets.split(",") if b))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(render_markdown(report), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
