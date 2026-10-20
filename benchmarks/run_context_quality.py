"""Run the context-quality comparison experiment and write the report files.

    python benchmarks/run_context_quality.py

It copies ``examples/legacy-java-oa`` into a temporary git repository, builds the
knowledge base once, then evaluates every golden query with both rankers
(``lexical`` default and optional ``ppr``) at two budgets (4000 / 8000 characters)
through the real ``tmh.context_pack.assemble`` path. Output:

    benchmarks/context-quality-report.json
    benchmarks/context-quality-report.md

Numbers come from that run; the report also records the environment and the
golden-set fingerprint so a later run can be compared. The decision on whether
to switch the default ranker is computed from the measured deltas, never hardcoded.
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tmh import kb  # noqa: E402
from tmh.context_quality import (  # noqa: E402
    evaluate, load_golden, render_markdown, validate_golden,
)

JAVA = ROOT / "examples" / "legacy-java-oa"
GOLDEN = ROOT / "tests" / "fixtures" / "context_golden.json"
BUDGETS = (4000, 8000)
# Decision rule, stated up front so it cannot be fitted after seeing the result:
# PPR becomes a candidate for default only if it lifts recall@5 by >= 0.02 and
# does not hurt needed-id coverage; token inflation may not exceed 25%.
MIN_RECALL_GAIN = 0.02
MAX_TOKEN_INFLATION = 0.25


def copy_repo(src: Path, prefix: str = "tmh-quality-") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    dst = d / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=dst, check=True)
    return dst


def git_head(root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""


def compare(report: dict) -> dict:
    """Per-query win/tie/loss counts and the final enable/disable decision."""
    lex = report["rankers"]["lexical"]
    ppr = report["rankers"]["ppr"]
    wins = ties = losses = 0
    for row in report["per_query"]:
        a = row["rankers"]["lexical"]["retrieval"]["recall@5"]
        b = row["rankers"]["ppr"]["retrieval"]["recall@5"]
        wins += b > a
        ties += b == a
        losses += b < a
    gain_r5 = round(ppr["retrieval"]["recall@5"] - lex["retrieval"]["recall@5"], 4)
    gain_r10 = round(ppr["retrieval"]["recall@10"] - lex["retrieval"]["recall@10"], 4)
    gain_mrr = round(ppr["retrieval"]["mrr"] - lex["retrieval"]["mrr"], 4)
    per_budget = {}
    for budget in report["budgets"]:
        b = str(budget)
        lp, pp = lex["packs"][b], ppr["packs"][b]
        token_change = (pp["tokens_mean"] - lp["tokens_mean"]) / lp["tokens_mean"] if lp["tokens_mean"] else 0.0
        per_budget[b] = {
            "coverage_delta": round(pp["coverage"] - lp["coverage"], 4),
            "tokens_change": round(token_change, 4),
            "tokens_per_needed_file_change": (
                round((pp["tokens_per_needed_file"] - lp["tokens_per_needed_file"]) / lp["tokens_per_needed_file"], 4)
                if lp["tokens_per_needed_file"] and pp["tokens_per_needed_file"] else None),
        }
    coverage_ok = all(v["coverage_delta"] >= -0.02 for v in per_budget.values())
    tokens_ok = all(abs(v["tokens_change"]) <= MAX_TOKEN_INFLATION for v in per_budget.values())
    enabled = bool(gain_r5 >= MIN_RECALL_GAIN and coverage_ok and tokens_ok)
    reasons = []
    if gain_r5 < MIN_RECALL_GAIN:
        reasons.append("recall@5 增益 %.4f < 门槛 %.2f" % (gain_r5, MIN_RECALL_GAIN))
    if not coverage_ok:
        reasons.append("needed id 覆盖率下降超过 0.02")
    if not tokens_ok:
        reasons.append("token 变化超过 ±%.0f%%" % (MAX_TOKEN_INFLATION * 100))
    return {
        "wins": wins, "ties": ties, "losses": losses,
        "recall@5_delta": gain_r5, "recall@10_delta": gain_r10, "mrr_delta": gain_mrr,
        "per_budget": per_budget,
        "decision": {
            "ppr_default_enabled": enabled,
            "rule": "recall@5 gain >= %.2f 且 needed-id 覆盖率不降 >0.02 且 token 变化 <= %.0f%%" % (
                MIN_RECALL_GAIN, MAX_TOKEN_INFLATION * 100),
            "reasons": reasons or ["满足启用门槛，但默认 ranker 的切换需要人工评审后单独提交"],
        },
    }


def conclusion_md(report: dict, comp: dict) -> list[str]:
    lex = report["rankers"]["lexical"]
    ppr = report["rankers"]["ppr"]
    lines = ["## 结论（由上面真实数字直接判定）", ""]
    lines.append("- lexical recall@5 = %.4f，PPR recall@5 = %.4f，差值 %+.4f；逐题对比 %d 胜 / %d 平 / %d 负。" % (
        lex["retrieval"]["recall@5"], ppr["retrieval"]["recall@5"], comp["recall@5_delta"],
        comp["wins"], comp["ties"], comp["losses"]))
    lines.append("- recall@10 差值 %+.4f，MRR 差值 %+.4f。" % (comp["recall@10_delta"], comp["mrr_delta"]))
    for budget, v in comp["per_budget"].items():
        tpf = "n/a" if v["tokens_per_needed_file_change"] is None else "%+.1f%%" % (v["tokens_per_needed_file_change"] * 100)
        lines.append("- 预算 %s：tokens/包变化 %+.1f%%，needed-id 覆盖率变化 %+.4f，tokens/needed file 变化 %s。" % (
            budget, v["tokens_change"] * 100, v["coverage_delta"], tpf))
    d = comp["decision"]
    if d["ppr_default_enabled"]:
        lines.append("- 判定：**满足启用门槛**（进入人工评审，本次仍保持默认 lexical，不改默认值）。")
    else:
        lines.append("- 判定：**不启用 PPR 作为默认 ranker**，默认保持 `lexical`。原因：%s。" % "；".join(d["reasons"]))
    lines.append("")
    return lines


def main() -> int:
    t0 = time.time()
    golden = load_golden(GOLDEN)
    repo = copy_repo(JAVA)
    build = kb.build(repo)
    bad = validate_golden(golden, repo)
    if bad:
        print("golden 集引用了知识库里不存在的 id：\n  " + "\n  ".join(bad))
        return 2
    report = evaluate(repo, golden, rankers=("lexical", "ppr"), budgets=BUDGETS)
    comp = compare(report)
    report["golden"] = {
        "path": "tests/fixtures/context_golden.json",
        "schema": golden.get("schema"),
        "sha256": hashlib.sha256(GOLDEN.read_bytes()).hexdigest()[:16],
        "queries": len(golden["queries"]),
    }
    report["environment"] = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "machine": platform.platform(),
        "python": platform.python_version(),
        "repo_head": git_head(ROOT),
        "graph": build.get("graph", {}),
        "kb_coverage": build.get("coverage", {}),
        "seconds": round(time.time() - t0, 1),
        "ranker_params": {
            "ppr_damping": 0.85, "ppr_tol": 1e-9, "ppr_max_iter": 100,
            "ppr_seed_hits": 10, "ppr_lexical_mix": 0.5, "ppr_min_rel": 0.005,
            "edge_weights": "step 1.0, handles/calls 0.9, entry/uses 0.8, writes/in 0.7, reads 0.6, contains/has_state 0.5, extends/transition 0.4, depends/effect 0.3; symmetric walk",
            "token_estimate": "1 per CJK char + 1 per ASCII word (tmh.context_quality.estimate_tokens)",
        },
    }
    report["comparison"] = comp
    out_json = HERE / "context-quality-report.json"
    out_md = HERE / "context-quality-report.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = render_markdown(report, extra={
        "golden": "%s（sha256:%s）" % (report["golden"]["path"], report["golden"]["sha256"]),
        "generated_at": report["environment"]["generated_at"],
        "machine": report["environment"]["machine"],
        "python": report["environment"]["python"],
    })
    md += "\n".join(conclusion_md(report, comp)) + "\n"
    md += "## 复跑方式\n\n```\npython benchmarks/run_context_quality.py\n```\n\n"
    md += "报告里所有数字由本次真实运行产生（临时仓库 + `kb.build` + 真实 `assemble`），环境与 golden 指纹见 JSON 的 `environment`/`golden` 字段。\n"
    out_md.write_text(md, encoding="utf-8")
    print("queries=%d" % report["queries"])
    for ranker in report["rankers"]:
        r = report["rankers"][ranker]["retrieval"]
        print("%-8s recall@5=%.4f recall@10=%.4f precision@5=%.4f mrr=%.4f" % (
            ranker, r["recall@5"], r["recall@10"], r["precision@5"], r["mrr"]))
        for budget, p in report["rankers"][ranker]["packs"].items():
            print("  budget=%-5s tokens_mean=%.1f coverage=%.4f tpf=%s omission=%.4f" % (
                budget, p["tokens_mean"], p["coverage"],
                "-" if p["tokens_per_needed_file"] is None else "%.2f" % p["tokens_per_needed_file"],
                p["budget_omission_rate"]))
    print("decision: ppr_default_enabled=%s reasons=%s" % (
        comp["decision"]["ppr_default_enabled"], "；".join(comp["decision"]["reasons"])))
    print("written: %s" % out_json)
    print("written: %s" % out_md)
    print("elapsed: %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
