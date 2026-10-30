#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G2 RSI replay skeleton: deterministic "echo replay" of the 40 JB evaluation cases.

It reuses the platform's scoring definition (see tmh/platform/learn.py: a case's
gold set is the files the real fix touched; 找全率 = gold files the plan listed,
准确率 = listed files that are actually in gold) but replaces the model with a
deterministic stub so the whole replay loop can be exercised offline and in CI.

The stub deliberately does NOT pretend to be an agent: it "reads" the case title
and body, extracts every repository file path that appears there, and returns it
as the plan's file list. That is an echo of the ticket text, not a model result --
the point is to prove the replay pipeline, the scoring math, the artifacts and the
"score must not drop" gate, not to claim any model quality.

    python tools/rsi_replay.py [--cases audit/live/project_JB_learn.json]
                               [--out D:\\DSH_project\\rsi\\baseline-replay.json]
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CASES = REPO.parent / "audit" / "live" / "project_JB_learn.json"
DEFAULT_OUT = REPO.parent / "rsi" / "baseline-replay.json"

# File-path shapes seen in the JB cases: jeecg-boot/...java, jeecgboot-vue3/...ts,
# and the shorter "src/main/java/..." variants some bodies use.
PATH_RE = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.(?:java|ts|vue|xml|sql|yml|json|js|tsx|jsx)")
STOP = {"没有", "系统", "问题", "功能", "接口", "页面", "文件"}


def echo_plan(case: dict) -> dict:
    """The stub "agent": echo every repository path it can see in the ticket text.

    It never invents a file that is not written in the ticket, and it never calls a
    model. `cited` records where each path came from so a human can audit the echo.
    """
    text = "\n".join(str(x) for x in (case.get("title", ""), case.get("body", "")))
    seen: list[str] = []
    cited: dict[str, dict] = {}
    for m in PATH_RE.finditer(text):
        path = m.group(0).strip("./")
        if path in seen:
            continue
        if not any(part and part not in STOP for part in path.split("/")):
            continue
        seen.append(path)
        start = max(0, m.start() - 40)
        cited[path] = {"offset": m.start(), "context": re.sub(r"\s+", " ", text[start:m.end() + 40])[:160]}
    # de-duplicate parent/child paths: keep the longest (most specific) one
    keep = [p for p in seen if not any(q != p and q.endswith("/" + p) for q in seen)]
    return {"files": keep, "cited": cited, "engine": "echo-stub", "agent_calls": 0}


def score(case: dict, plan: dict) -> dict:
    """Same definitions as tmh/platform/learn.py: gold = files the real fix touched;
    找全率 (recall) = gold files the plan listed; 准确率 (precision) = listed files in gold."""
    gold = [g for g in (case.get("gold") or []) if g]
    listed = [p for p in (plan.get("files") or []) if p]
    gold_set = set(gold)
    listed_set = set(listed)
    hits = sorted(gold_set & listed_set)
    missing = sorted(gold_set - listed_set)
    extra = sorted(listed_set - gold_set)
    recall = (len(hits) / len(gold_set)) if gold_set else None
    precision = (len(hits) / len(listed_set)) if listed_set else None
    # diagnostic, not part of the score: does the ticket text itself even name the
    # fixed file? A low echo score is expected when it does not -- that is exactly
    # why a real replay needs a model + knowledge context, not a grep.
    text = "\n".join(str(x) for x in (case.get("title", ""), case.get("body", "")))
    named = [g for g in gold if Path(g).stem and Path(g).stem in text]
    return {
        "hits": hits, "missing": missing, "extra": extra,
        "gold_n": len(gold_set), "listed_n": len(listed_set),
        "find_all": round(recall, 4) if recall is not None else None,
        "accuracy": round(precision, 4) if precision is not None else None,
        "ok": bool(gold_set) and gold_set == listed_set,
        "text_names_gold": named,
    }


def summarize(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["find_all"] is not None]
    n = len(scored)
    def avg(k):
        vals = [r[k] for r in scored if r[k] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    return {
        "cases": len(rows),
        "scored_cases": n,
        "find_all_avg": avg("find_all"),
        "accuracy_avg": avg("accuracy"),
        "exact_match_cases": sum(1 for r in scored if r["ok"]),
        "cases_with_missing": sum(1 for r in scored if r["missing"]),
        "cases_with_extra": sum(1 for r in scored if r["extra"]),
        "total_gold_files": sum(r["gold_n"] for r in scored),
        "total_hits": sum(len(r["hits"]) for r in scored),
        "total_listed": sum(r["listed_n"] for r in scored),
        "definition": {
            "find_all": "gold 中被方案列出的比例（learn.py 的找全率）",
            "accuracy": "方案列出的文件中属于 gold 的比例（learn.py 的准确率）",
            "engine": "echo-stub：确定性回声，仅用于验证回放管线，不代表模型能力",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    src = Path(args.cases)
    if not src.exists():
        print("cases 文件不存在：" + str(src))
        return 2
    data = json.loads(src.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for case in cases:
        plan = echo_plan(case)
        s = score(case, plan)
        rows.append({
            "id": case.get("id"), "ticket": case.get("ticket"), "title": case.get("title", ""),
            "base": case.get("base", ""), "gold": case.get("gold") or [],
            "stub_listed": plan["files"], "cited": plan["cited"], "agent_calls": plan["agent_calls"],
            **s,
        })
    result = {
        "schema": 1, "generated": started, "engine": "echo-stub (deterministic, no model)",
        "source": str(src), "case_source": "audit/live/project_JB_learn.json（线上 JB 平台，2026-10-20 快照）",
        "summary": summarize(rows),
        "cases": rows,
        "how_to_run_for_real": {
            "endpoint": "POST /api/projects/JB/evals/run  {\"agent\": \"codex\", \"cases\": [\"c1\", ...]}",
            "cli": "python -m tmh.workbench evals-run JB --agent codex   # 平台需在运行且已登录",
            "note": "真跑时每个用例在 case.base 提交上建临时 worktree，让智能体只按工单起草修改方案；"
                    "打分函数复用 tmh/platform/learn.py 的 compare()（文件清单 vs gold）。",
        },
        "gate": {
            "rule": "同一批次、同一用例集下 find_all_avg 与 accuracy_avg 均不得低于已归档基线；任一显著下降不得上线",
            "baseline_file": str(Path(args.out)),
            "next": "以后每次换模型/改提示词/改知识库后跑一次真实回放，与本文件对比",
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
