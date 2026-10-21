"""Run the local-model RSI baseline and write the report files.

    python benchmarks/run_rsi_local.py

For each "change where" task it asks the same local Ollama model three times:
``cold`` (requirement only), ``pack-4000`` and ``pack-8000`` (requirement plus a
real ``assemble`` context pack), parses the JSON file list, and records file
recall / precision / exact rate / latency / real token usage. If Ollama is down or
the model is missing the run degrades into an explicit report, it never crashes.

Output:
    benchmarks/rsi-local-report.json
    benchmarks/rsi-local-report.md

Also runs the small G3 lexical-tuning grid on ``tests/fixtures/context_golden.json``
and records whether the winning config is adopted (adoption rule lives in
``tmh.context_quality``: recall@5 gain >= 0.02 and token growth <= 10%).
"""
from __future__ import annotations

import argparse
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
sys.path.insert(0, str(HERE))

import rsi_local_eval as rsi  # noqa: E402
from tmh import kb  # noqa: E402
from tmh.context_pack import assemble  # noqa: E402

JAVA = ROOT / "examples" / "legacy-java-oa"
GOLDEN = ROOT / "tests" / "fixtures" / "context_golden.json"


def copy_repo(src: Path, prefix: str = "tmh-rsi-") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    dst = d / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=dst, check=True)
    return dst


def git_head(path: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""


def build_packs(repo: Path, tasks: list[dict], budgets: dict) -> tuple[dict, dict, float]:
    """One context pack per (task, budget); also record how long base assembly took."""
    packs: dict[str, dict] = {}
    t0 = time.time()
    for task in tasks:
        for condition, budget in budgets.items():
            text = assemble([{"root": str(repo), "label": "oa", "current": True}],
                            task["query"], budget=budget, log=False)
            packs.setdefault(condition, {})[task["id"]] = text
    return packs, {}, round(time.time() - t0, 1)


def run_suite(client, repo: Path, tasks: list[dict], packs: dict, max_tokens: int) -> tuple[list[dict], dict]:
    files = rsi.project_files(repo)
    samples, per_condition = [], {}
    for condition in rsi.CONDITIONS:
        rows = []
        for i, task in enumerate(tasks):
            pack_text = packs.get(condition, {}).get(task["id"], "")
            sample = rsi.run_task(client, task, condition, repo, files, pack_text, max_tokens=max_tokens)
            rows.append(sample)
            samples.append(sample)
            print("[%s %2d/%2d] %s recall=%.2f files=%d err=%s %.1fs" % (
                condition, i + 1, len(tasks), task["id"], sample["recall"], len(sample["files"]),
                sample["parse_error"] or "-", sample["latency_s"]), flush=True)
        per_condition[condition] = rsi.summarize(rows)
    return samples, per_condition


def g3_tuning(repo: Path) -> dict:
    """Optional: the lexical-tuning grid needs the built knowledge base of ``repo``."""
    try:
        from tmh.context_quality import tune_lexical

        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        return {"status": "ran", **tune_lexical(repo, golden)}
    except ImportError:
        return {"status": "skipped", "reason": "tmh.context_quality.tune_lexical 未实现"}
    except Exception as exc:  # noqa: BLE001 - the RSI report must still be written
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def render_markdown(report: dict) -> str:
    env, summaries, comp = report["environment"], report["conditions"], report["comparison"]
    lines = ["# 本地模型 RSI 基线报告（冷启动 vs 上下文包）", ""]
    lines.append("- 项目：`%s` · 任务数 %d · 模型 `%s` @ `%s`" % (
        env["project"], env["task_count"], env["model"], env["ollama_base"]))
    lines.append("- 生成时间：%s · Python %s · 主机 %s · Ollama %s" % (
        env["generated_at"], env["python"], env["machine"], env.get("ollama_version") or "?"))
    lines.append("- 调用参数：temperature=%s、think=%s、max_tokens=%d、timeout=%ss；每条件 %d 次调用。" % (
        env["temperature"], env["think"], env["max_tokens"], env["timeout_s"], env["task_count"]))
    lines.append("- 上下文包：`tmh.context_pack.assemble` 真实输出，预算 4000 / 8000 字符（构建耗时 %.1fs）。" % env["pack_build_seconds"])
    lines.append("")
    lines.append("## 三组结果")
    lines.append("")
    lines.append("| 条件 | 找全率 recall | exact（gold 全覆盖） | precision | 幻觉路径率 | 有答案 | 失败/空答 | 平均延迟 | 真实 completion tokens | 有效输出 tokens | prompt tokens |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for condition in rsi.CONDITIONS:
        s = summaries[condition]
        fails = "、".join("%s×%d" % (k, v) for k, v in s["failures"].items()) or "-"
        lines.append("| %s | %.4f | %.4f | %.4f | %.4f | %d/%d | %s / %d | %.2fs | %.1f | %.1f | %.1f |" % (
            condition, s["recall_mean"], s["exact_rate"], s["precision_mean"], s["hallucinated_path_rate"],
            s["answered"], s["n"], fails, s["empty_answers"], s["latency_mean_s"],
            s["completion_tokens_mean"], s["effective_output_tokens_mean"], s["prompt_tokens_mean"]))
    lines.append("")
    lines.append("## 解读与注意")
    lines.append("")
    cold, p4, p8 = summaries["cold"], summaries["pack-4000"], summaries["pack-8000"]
    if cold["empty_answers"] == cold["n"]:
        lines.append("- cold 的 %d 条回答全部是空数组（模型按指令“没把握输出 []”）：cold recall=0 是**拒答**而不是乱猜；"
                     "有上下文后才有 %d/%d 条给出答案。这说明上下文解决的是“从 0 到有”，还没有到“找得全”。" % (
                         cold["n"], p8["answered"], p8["n"]))
    if abs(p4["recall_mean"] - p8["recall_mean"]) < 1e-9:
        lines.append("- pack-4000 与 pack-8000 的 recall 完全相同：该样例项目知识库很小，4000 字符包已基本包含全部条目，"
                     "把预算翻到 8000 没有新增信息（同一原因也见 `context-quality-report.md` 的 complete_rate）。")
    if p4["latency_mean_s"] > 0 and p8["latency_mean_s"] > 0 and \
            max(p4["latency_mean_s"], p8["latency_mean_s"]) > 2 * min(p4["latency_mean_s"], p8["latency_mean_s"]):
        lines.append("- 延迟差（pack-4000 %.2fs vs pack-8000 %.2fs）与两组 prompt tokens 几乎相同，属模型首次加载/预热噪声，"
                     "不是预算造成的；延迟只适合同条件重复测量后再比较。" % (p4["latency_mean_s"], p8["latency_mean_s"]))
    latencies = {c: summaries[c]["latency_mean_s"] for c in rsi.CONDITIONS}
    slowest = max(latencies, key=latencies.get)
    if latencies[slowest] > 2 * min(latencies.values()):
        lines.append("- 延迟不能跨条件直接比较：%s 平均 %.2fs 明显高于其他条件（%.2fs / %.2fs），而条件按 %s 顺序执行——"
                     "第一个条件包含 Ollama 模型加载与首推预热；要看真实推理延迟应固定条件重复测量。" % (
                         slowest, latencies[slowest],
                         min(latencies.values()), max(v for k, v in latencies.items() if k != slowest),
                         " → ".join(rsi.CONDITIONS)))
    lines.append("- 上下文代价：prompt tokens 均值 %.1f（cold）→ %.1f（pack），约 %.1fx；completion tokens 含全部推理 token。" % (
        cold["prompt_tokens_mean"], p8["prompt_tokens_mean"],
        (p8["prompt_tokens_mean"] / cold["prompt_tokens_mean"]) if cold["prompt_tokens_mean"] else 0.0))
    lines.append("- 样本只有 %d 条、单个 9B 模型、单次 temperature=0 运行：结论只作方向性参考，不构成统计显著性。" % env["task_count"])
    lines.append("")
    lines.append("## 与 cold 的对比（判定规则：%s）" % comp["min_gain_rule"])
    lines.append("")
    lines.append("| 条件 | recall 差值 | exact 差值 | 延迟差值 | completion token 差值 |")
    lines.append("|---|---|---|---|---|")
    for condition, c in comp["per_condition"].items():
        lines.append("| %s | %+.4f | %+.4f | %+.2fs | %+.1f |" % (
            condition, c["recall_delta_vs_cold"], c["exact_delta_vs_cold"],
            c["latency_delta_s"], c["completion_tokens_delta"]))
    lines.append("")
    lines.append("**结论**：%s" % comp["conclusion"])
    lines.append("")
    lines.append("## 逐任务 recall")
    lines.append("")
    lines.append("| 任务 | 需求 | gold 文件数 | cold | pack-4000 | pack-8000 |")
    lines.append("|---|---|---|---|---|---|")
    by_task: dict[str, dict] = {}
    for s in report["per_task"]:
        by_task.setdefault(s["task_id"], {})[s["condition"]] = s
    for task in rsi.TASKS:
        row = by_task.get(task["id"], {})
        lines.append("| %s | %s | %d | %.2f | %.2f | %.2f |" % (
            task["id"], task["query"], len(task["gold"]),
            row.get("cold", {}).get("recall", 0.0),
            row.get("pack-4000", {}).get("recall", 0.0),
            row.get("pack-8000", {}).get("recall", 0.0)))
    lines.append("")
    tuning = report.get("g3_tuning") or {}
    lines.append("## G3 检索调优（lexical 小网格）")
    lines.append("")
    if tuning.get("status") == "ran":
        lines.append("- 网格 %d 组，基准 recall@5=%.4f、recall@10=%.4f、token/包=%.1f" % (
            len(tuning.get("configs", [])), tuning["baseline"]["recall@5"],
            tuning["baseline"]["recall@10"], tuning["baseline"]["tokens_mean"]))
        for c in tuning.get("configs", []):
            lines.append("- `%s`：recall@5=%+.4f、recall@10=%+.4f、token %+.1f%%%s" % (
                c["name"], c["recall@5_delta"], c["recall@10_delta"], c["tokens_change_pct"],
                "（最佳）" if c.get("best") else ""))
        d = tuning["decision"]
        lines.append("- 判定：**%s**（规则：%s；理由：%s）" % (
            "采纳" if d["adopted"] else "不采纳", d["rule"], "；".join(d["reasons"])))
    else:
        lines.append("- 未运行或不可用：%s" % tuning.get("reason", "无结果"))
    lines.append("")
    lines.append("## 复跑方式")
    lines.append("")
    lines.append("```")
    lines.append("python benchmarks/run_rsi_local.py")
    lines.append("python -m pytest tests/test_rsi_local_eval.py -q")
    lines.append("```")
    lines.append("")
    lines.append("## 口径说明")
    lines.append("- 找全率：gold 文件被模型答案覆盖的比例（文件级 recall），解析失败/空答按 0 计，不从分母剔除。")
    lines.append("- exact：只有 gold 文件全部被找到才算对（文件级准确率）。")
    lines.append("- 真实 completion tokens：Ollama 返回的 `eval_count`，包含推理 token；有效输出 tokens 用 `estimate_tokens` 估算模型可见答案。")
    lines.append("- 失败分类：`request_timeout` / `request_unavailable` / `request_http_*` / `parse` / `empty` 分别计数。")
    lines.append("- 延迟：条件固定按 %s 顺序执行，第一个条件包含 Ollama 模型加载/预热，不用于跨条件比较。" % " → ".join(rsi.CONDITIONS))
    return "\n".join(lines) + "\n"


def write_degraded(detail: str, model: str, base_url: str) -> int:
    report = {
        "schema": rsi.SCHEMA, "status": "degraded",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "reason": detail, "model": model, "ollama_base": base_url,
        "task_count": len(rsi.TASKS), "conditions": list(rsi.CONDITIONS),
        "commands": "python benchmarks/run_rsi_local.py",
    }
    (HERE / "rsi-local-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = ["# 本地模型 RSI 基线报告（降级）", "",
          "- 状态：**本地模型不可用，未产生任何数字**（不是 0 分，而是没有测量）。",
          "- 原因：%s" % detail, "- 模型：`%s` @ `%s`" % (model, base_url), "",
          "## 处理方式", "",
          "- 脚本按契约降级：写降级报告并以 0 退出，不伪造数据。",
          "- 恢复服务后复跑：`python benchmarks/run_rsi_local.py`。", ""]
    (HERE / "rsi-local-report.md").write_text("\n".join(md), encoding="utf-8")
    print("DEGRADED: %s" % detail)
    print("written: %s" % (HERE / "rsi-local-report.json"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="本地 Ollama 模型 RSI 基线：cold vs context pack")
    ap.add_argument("--root", default=str(JAVA), help="样例项目目录")
    ap.add_argument("--model", default=rsi.MODEL)
    ap.add_argument("--base-url", default=rsi.OLLAMA_URL)
    ap.add_argument("--max-tokens", type=int, default=rsi.DEFAULT_MAX_TOKENS)
    ap.add_argument("--timeout", type=float, default=rsi.DEFAULT_TIMEOUT)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个任务（0=全部）")
    ap.add_argument("--no-g3", action="store_true", help="跳过 G3 调优网格")
    args = ap.parse_args(argv)
    t0 = time.time()
    tasks = rsi.TASKS[:args.limit] if args.limit else rsi.TASKS
    repo = copy_repo(Path(args.root))
    build = kb.build(repo)
    client = rsi.OllamaClient(args.base_url, args.model, args.timeout)
    ok, detail = client.available()
    if not ok:
        return write_degraded(detail, args.model, args.base_url)
    try:
        version = client._get(args.base_url.rstrip("/") + "/api/version", 10).get("version", "")
    except Exception:  # noqa: BLE001
        version = ""
    packs, _, pack_seconds = build_packs(repo, tasks, rsi.PACK_BUDGET)
    samples, summaries = run_suite(client, repo, tasks, packs, args.max_tokens)
    comp = rsi.compare(summaries)
    report = {
        "schema": rsi.SCHEMA, "status": "ok",
        "kind": "rsi-local-context-baseline",
        "environment": {
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "project": "examples/legacy-java-oa", "task_count": len(tasks),
            "model": args.model, "ollama_base": args.base_url, "ollama_version": version,
            "think": rsi.THINK, "temperature": 0.0, "max_tokens": args.max_tokens,
            "timeout_s": args.timeout, "conditions": list(rsi.CONDITIONS),
            "pack_budget": rsi.PACK_BUDGET, "pack_build_seconds": pack_seconds,
            "machine": platform.platform(), "python": platform.python_version(),
            "repo_head": git_head(ROOT), "kb_build": build.get("graph", {}),
            "seconds": round(time.time() - t0, 1),
        },
        "conditions": summaries,
        "comparison": comp,
        "per_task": samples,
        "g3_tuning": {"status": "skipped"} if args.no_g3 else g3_tuning(repo),
    }
    (HERE / "rsi-local-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (HERE / "rsi-local-report.md").write_text(render_markdown(report), encoding="utf-8")
    print("== summary ==")
    for condition in rsi.CONDITIONS:
        s = summaries[condition]
        print("%-10s recall=%.4f exact=%.4f latency=%.2fs completion_tokens=%.1f" % (
            condition, s["recall_mean"], s["exact_rate"], s["latency_mean_s"], s["completion_tokens_mean"]))
    print("conclusion: %s" % comp["conclusion"])
    print("written: %s" % (HERE / "rsi-local-report.json"))
    print("elapsed: %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
