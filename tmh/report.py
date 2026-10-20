"""Markdown renderers for the assessment report and the project map."""
from __future__ import annotations

import datetime as _dt

CATEGORY_CN = {
    "database": "数据库", "middleware": "中间件", "os": "操作系统", "arch": "CPU 架构", "jdk": "JDK",
    "crypto": "国密", "encoding": "字符集", "dotnet": ".NET 平台", "frontend": "前端/浏览器",
}
# Migration waves: platform first (it decides whether anything builds on the target),
# then data layer, then runtime environment, then security and UI.
WAVE = {"dotnet": 1, "jdk": 1, "database": 2, "middleware": 3, "os": 3, "arch": 3, "encoding": 3, "crypto": 4, "frontend": 4}
WAVE_CN = {1: "第 1 波：平台与构建（能在目标环境编译运行）", 2: "第 2 波：数据库适配", 3: "第 3 波：中间件 / 操作系统 / CPU 架构", 4: "第 4 波：国密与前端"}
SEV_CN = {"high": "高", "medium": "中", "low": "低", "info": "提示"}


def now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def assessment_md(disc: dict, scan: dict, cfg: dict, head: str | None) -> str:
    t = cfg["target"]
    s = cfg["source"]
    out = []
    out.append("# 信创改造评估报告\n")
    out.append("> 生成时间 %s · 提交 `%s` · 由 `tmh assess` 自动生成，结论均附 文件:行号 证据；工作量与风险需人工复核。\n" % (now(), (head or "未纳入 git")[:12]))
    out.append("## 改造目标\n")
    out.append("| 维度 | 现状 | 目标 |\n|---|---|---|")
    for k, cn in (("db", "数据库"), ("appserver", "应用服务器"), ("os", "操作系统"), ("arch", "CPU 架构")):
        out.append("| %s | %s | %s |" % (cn, s.get(k, "unknown"), t.get(k, "unknown")))
    out.append("| 国密 | - | %s |" % ("需要" if t.get("crypto") == "sm" else "不要求"))
    out.append("| JDK | - | %s |\n" % t.get("jdk", "unknown"))
    unknown = [k for k in ("db", "appserver", "arch") if t.get(k) == "unknown"]
    if unknown:
        out.append("> 目标 %s 尚未确定：相关规则按最严格方式运行。用 `tmh init --target-db dm8 ...` 设定后重新评估。\n" % "、".join(unknown))

    out.append("## 技术栈概况\n")
    out.append("- 技术栈：%s；文件 %d 个" % ("、".join(disc["stacks"]) or "未识别", disc["total_files"]))
    loc = disc.get("loc", {})
    if loc:
        out.append("- 代码行数：" + "，".join("%s %s" % (k, f"{v:,}") for k, v in list(loc.items())[:8]))
    j = disc["java"]
    if "java" in disc["stacks"]:
        out.append("- Java：构建 %s；模块 %d 个；Java 版本 %s；Spring Boot %s" % (j["build"] or "-", len(j["modules"]), j["java_version"] or "未声明", j["spring_boot"] or "-"))
        if j["frameworks"]:
            out.append("- Java 框架：" + "、".join(j["frameworks"]))
    d = disc["dotnet"]
    if "dotnet" in disc["stacks"]:
        tfs = sorted({tf for p in d["projects"] for tf in p["target_frameworks"]})
        legacy = sum(1 for p in d["projects"] if not p["sdk_style"])
        out.append("- .NET：解决方案 %d 个；项目 %d 个（旧式 csproj %d 个）；目标框架 %s" % (len(d["solutions"]), len(d["projects"]), legacy, "、".join(tfs) or "未声明"))
        if d["frameworks"]:
            out.append("- .NET 组件：" + "、".join(d["frameworks"]))
    out.append("")

    summ = scan["summary"]
    bs = summ["by_severity"]
    out.append("## 结论摘要\n")
    out.append("扫描 %d 个文件，命中 %d 处：高 %d / 中 %d / 低 %d / 提示 %d。\n" % (
        scan["files_scanned"], len(scan["findings"]), bs.get("high", 0), bs.get("medium", 0), bs.get("low", 0), bs.get("info", 0)))
    blockers = [r for r in summ["by_rule"] if r["severity"] == "high" and r["effort"] == "L"]
    if blockers:
        out.append("**可能的阻塞项（高风险且工作量大，建议先做技术验证）：**\n")
        for r in blockers:
            out.append("- `%s` %s（%d 处 / %d 个文件）" % (r["rule"], r["title"], r["hits"], r["files"]))
        out.append("")

    out.append("## 分波次改造清单\n")
    waves: dict[int, list] = {}
    for r in summ["by_rule"]:
        waves.setdefault(WAVE.get(r["category"], 3), []).append(r)
    for w in sorted(waves):
        out.append("### %s\n" % WAVE_CN[w])
        out.append("| 规则 | 类别 | 风险 | 工作量 | 命中 | 文件 | 问题 |\n|---|---|---|---|---|---|---|")
        for r in waves[w]:
            out.append("| `%s` | %s | %s | %s | %d | %d | %s |" % (r["rule"], CATEGORY_CN.get(r["category"], r["category"]), SEV_CN.get(r["severity"], r["severity"]), r["effort"], r["hits"], r["files"], r["title"]))
        out.append("")
        for r in waves[w]:
            out.append("- **%s**：%s（参考 `.tmh/kb/%s`）" % (r["rule"], r["advice"], r["kb"]))
        out.append("")

    out.append("## 证据明细（每条规则最多列 15 处）\n")
    shown: dict[str, int] = {}
    cur = None
    for f in scan["findings"]:
        n = shown.get(f["rule"], 0)
        if n >= 15:
            continue
        shown[f["rule"]] = n + 1
        if f["rule"] != cur:
            cur = f["rule"]
            out.append("\n**%s %s**\n" % (f["rule"], f["title"]))
        loc_s = "%s:%d" % (f["file"], f["line"]) if f["line"] else f["file"]
        out.append("- `%s` — `%s`" % (loc_s, f["snippet"].replace("`", "'")[:140]))
    out.append("\n## 本报告不能证明的事\n")
    out.append("- 规则扫描只看文本特征，动态拼接的 SQL、反射调用、配置中心下发的配置和第三方二进制内部实现看不到")
    out.append("- “兼容模式下可运行”需要在目标数据库实例上用真实 SQL 与样例数据验证")
    out.append("- 工作量等级（S/M/L）是经验估计，不含联调、数据迁移与测评时间\n")
    return "\n".join(out) + "\n"


def map_md(disc: dict, m: dict, head: str | None) -> str:
    out = ["# 项目地图（自动生成的事实层）\n",
           "> 生成时间 %s · 提交 `%s` · 由 `tmh map` 从源码语法提取，只陈述“在哪里”，不解释业务含义。"
           "业务理解写在 `.tmh/knowledge/`，并标注 [事实]/[推断]/[待确认]。代码改变后运行 `tmh map` 刷新。\n" % (now(), (head or "未纳入 git")[:12])]
    out.append("## 模块\n")
    j, d = disc["java"], disc["dotnet"]
    for mod in j["modules"]:
        if mod.get("artifact"):
            out.append("- `%s` (%s) — %s" % (mod["artifact"], mod.get("packaging", ""), mod["path"]))
    if any(j.get("module_graph", {}).values()):
        out.append("\nMaven 模块依赖：")
        for k, v in j["module_graph"].items():
            if v:
                out.append("- %s → %s" % (k, ", ".join(v)))
    for p in d["projects"]:
        out.append("- `%s` — %s %s%s" % (p["path"], ",".join(p["target_frameworks"]) or "?", p["output_type"], " (Web)" if p["is_web"] else ""))
    if any(d["project_graph"].values()):
        out.append("\n.NET 项目引用：")
        for k, v in d["project_graph"].items():
            if v:
                out.append("- %s → %s" % (k, ", ".join(v)))
    out.append("")

    def table(title, rows, cols, keys, limit=400):
        out.append("## %s（%d）\n" % (title, len(rows)))
        if not rows:
            out.append("_未发现_\n")
            return
        out.append("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
        for r in rows[:limit]:
            vals = []
            for k in keys:
                v = r.get(k, "")
                if k == "file":
                    v = "%s:%s" % (r["file"], r.get("line", 0)) if r.get("line") else r["file"]
                vals.append(str(v).replace("|", "\\|"))
            out.append("| " + " | ".join(vals) + " |")
        if len(rows) > limit:
            out.append("\n_仅列前 %d 条，完整数据见 .tmh/map.json_" % limit)
        out.append("")

    table("对外入口（URL / 接口）", sorted(m["endpoints"], key=lambda e: e["path"]), ["方法", "路径", "处理者", "位置"], ["method", "path", "handler", "file"])
    table("其他入口（Servlet/Filter/WCF 契约等）", m["entrypoints"], ["类型", "类", "位置"], ["kind", "class", "file"])
    table("后台任务", m["jobs"], ["类型", "处理者", "调度", "位置"], ["kind", "class", "schedule", "file"])
    table("消息监听", m["listeners"], ["类型", "处理者", "目标", "位置"], ["kind", "class", "target", "file"])
    da = [{"kind": x["kind"], "namespace": x["namespace"], "n": len(x["statements"]), "file": x["file"]} for x in m["data_access"]]
    table("数据访问层", da, ["类型", "名称", "语句数", "位置"], ["kind", "namespace", "n", "file"])
    table("实体与表", m["entities"], ["类", "表", "位置"], ["class", "table", "file"])
    table("数据库对象（SQL 脚本）", m["db_objects"], ["类型", "名称", "位置"], ["kind", "name", "file"])
    out.append("## 表 → 引用代码（%d 张表）\n" % len(m["tables"]))
    out.append("改需求或迁数据库时，用这张表找“动这张表会影响哪些代码”。\n")
    for t, files in list(m["tables"].items())[:600]:
        shown = ", ".join("`%s`" % f for f in files[:8])
        more = " 等 %d 个文件" % len(files) if len(files) > 8 else ""
        out.append("- **%s**：%s%s" % (t, shown, more))
    out.append("\n## 配置文件\n")
    for c in m["configs"][:200]:
        out.append("- `%s`" % c)
    return "\n".join(out) + "\n"
