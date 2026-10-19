"""tmh — 传统 toB 软件项目维护 harness 命令行。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__
from . import config as cfgmod
from .fsutil import remove_file

TARGET_KEYS = ["db", "appserver", "os", "arch", "crypto", "mq", "cache", "browser", "jdk"]


def _root(a) -> Path:
    return Path(getattr(a, "repo", ".") or ".").resolve()


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def guess_source_db(root: Path) -> str:
    from .fsutil import iter_files, read_text
    votes = {"oracle": 0, "mysql": 0, "sqlserver": 0, "postgresql": 0}
    pats = {"oracle": r"oracle\.jdbc|jdbc:oracle|ojdbc|Oracle\.ManagedDataAccess|OracleClient",
            "mysql": r"com\.mysql|jdbc:mysql|mysql-connector|MySql\.Data|MySqlConnector",
            "sqlserver": r"sqlserver|SqlClient|mssql",
            "postgresql": r"org\.postgresql|jdbc:postgresql|Npgsql"}
    for p in iter_files(root):
        if p.name in ("pom.xml", "packages.config") or p.suffix.lower() in (".gradle", ".csproj", ".properties", ".yml", ".yaml", ".config"):
            t = read_text(p) or ""
            for k, rx in pats.items():
                votes[k] += len(re.findall(rx, t, re.I))
    best = max(votes, key=votes.get)
    return best if votes[best] else "unknown"


def cmd_init(a) -> int:
    root = _root(a)
    cfg = cfgmod.load(root)
    for k in TARGET_KEYS:
        v = getattr(a, "target_" + k, None)
        if v:
            if v not in cfgmod.CHOICES[k]:
                print("target.%s 可选值：%s" % (k, ", ".join(cfgmod.CHOICES[k])), file=sys.stderr)
                return 2
            cfg["target"][k] = v
    if a.source_db:
        cfg["source"]["db"] = a.source_db
    elif cfg["source"]["db"] == "unknown":
        cfg["source"]["db"] = guess_source_db(root)
    if a.name:
        cfg["project"]["name"] = a.name
    p = cfgmod.save(root, cfg)
    print("已写入 %s" % p)
    print("源数据库（自动识别）：%s；目标：%s" % (cfg["source"]["db"], ", ".join("%s=%s" % (k, cfg["target"][k]) for k in TARGET_KEYS)))
    return 0


def cmd_install(a) -> int:
    from .install import install
    engines = [e.strip() for e in a.engines.split(",") if e.strip()]
    for line in install(_root(a), engines, a.git_hook):
        print("✓", line)
    print("\n下一步：python3 .tmh/tool/tmh.py init --target-db dm8 ...；然后 assess / map / baseline。")
    return 0


def cmd_assess(a) -> int:
    from . import discover, ledger, report, scanner
    from .fsutil import git_head
    root = _root(a)
    cfg = cfgmod.load(root)
    disc = discover.discover(root)
    scan = scanner.scan_repo(root, cfg)
    x = cfgmod.tmh_dir(root)
    x.mkdir(parents=True, exist_ok=True)
    (x / "stack.json").write_text(json.dumps(disc, ensure_ascii=False, indent=1), encoding="utf-8")
    (x / "scan.json").write_text(json.dumps(scan, ensure_ascii=False, indent=1), encoding="utf-8")
    md = report.assessment_md(disc, scan, cfg, git_head(root))
    (x / "ASSESSMENT.md").write_text(md, encoding="utf-8")
    items = ledger.refresh(root, scan)
    bs = scan["summary"]["by_severity"]
    print("评估完成：扫描 %d 个文件，命中 %d 处（高 %d / 中 %d / 低 %d），工作项 %d 个。" % (
        scan["files_scanned"], len(scan["findings"]), bs.get("high", 0), bs.get("medium", 0), bs.get("low", 0), len(items)))
    print("报告：.tmh/ASSESSMENT.md  工作项：.tmh/workitems.json  技术栈：.tmh/stack.json")
    a.summary = "改造评估：命中 %d 处（高 %d / 中 %d），工作项 %d 个" % (len(scan["findings"]), bs.get("high", 0), bs.get("medium", 0), len(items))
    return 0


def cmd_map(a) -> int:
    from . import discover, mapper, report
    from .fsutil import git_head
    root = _root(a)
    x = cfgmod.tmh_dir(root)
    x.mkdir(parents=True, exist_ok=True)
    disc = discover.discover(root)
    m = mapper.build_map(root)
    (x / "map.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    (x / "stack.json").write_text(json.dumps(disc, ensure_ascii=False, indent=1), encoding="utf-8")
    (x / "PROJECT_MAP.md").write_text(report.map_md(disc, m, git_head(root)), encoding="utf-8")
    stale = x / "stale-files.txt"
    if stale.exists():
        remove_file(stale)
    print("项目地图：入口 %d，后台任务 %d，消息监听 %d，数据访问 %d，表 %d，类型 %d。" % (
        len(m["endpoints"]), len(m["jobs"]), len(m["listeners"]), len(m["data_access"]), len(m["tables"]), len(m["symbols"])))
    print("已写入 .tmh/PROJECT_MAP.md 与 .tmh/map.json")
    a.summary = "项目地图：入口 %d、后台任务 %d、表 %d" % (len(m["endpoints"]), len(m["jobs"]), len(m["tables"]))
    return 0


def cmd_scan(a) -> int:
    from . import scanner
    root = _root(a)
    res = scanner.scan_repo(root, only_files=a.files or None)
    if a.json:
        _out(res)
        return 0
    for f in res["findings"][: a.limit]:
        print("[%s] %s:%d %s %s\n    %s" % (f["severity"], f["file"], f["line"], f["rule"], f["title"], f["snippet"][:120]))
    print("共 %d 处（显示前 %d）" % (len(res["findings"]), a.limit))
    return 0


def cmd_where(a) -> int:
    from .query import where
    res = where(_root(a), a.keywords, a.limit)
    if a.json:
        _out(res)
        return 0
    for r in res:
        print("%5.1f  %s" % (r["score"], r["file"]))
        for w in r["why"]:
            print("       - " + w)
    if not res:
        print("没有命中。试试同义词、英文名、表名或 URL 片段。")
    a.summary = "定位“%s”：%s" % (" ".join(a.keywords), "、".join(r["file"].rsplit("/", 1)[-1] for r in res[:3]) or "无命中")
    return 0


def cmd_impact(a) -> int:
    from .query import impact
    res = impact(_root(a), a.target, depth=a.depth)
    if a.json:
        _out(res)
        return 0
    print("目标：%s" % res["target"])
    print("定义位置：%s" % (", ".join(res["defined_in"]) or "未找到"))
    if res.get("tables_used"):
        print("该文件访问的表：%s" % ", ".join(res["tables_used"]))
    if res["table_users"]:
        print("访问该表的文件（%d）：" % len(res["table_users"]))
        for f in res["table_users"]:
            print("  - " + f)
    print("引用方（%d）：" % len(res["referenced_by"]))
    for r in res["referenced_by"]:
        print("  - [第%d层 经 %s] %s 行 %s" % (r["level"], ",".join(r["via"]), r["file"], ",".join(map(str, r["lines"]))))
    if res["entrypoints_in_referrers"]:
        print("受影响的入口：")
        for e in res["entrypoints_in_referrers"]:
            print("  - %s %s → %s (%s:%s)" % (e["method"], e["path"], e["handler"], e["file"], e.get("line", 0)))
    if res.get("jobs_in_referrers"):
        print("受影响的后台任务：")
        for j in res["jobs_in_referrers"]:
            print("  - %s %s (%s)" % (j["kind"], j["class"], j["file"]))
    a.summary = "影响分析 %s：引用方 %d 个，受影响入口 %d 个" % (a.target, len(res["referenced_by"]), len(res["entrypoints_in_referrers"]))
    return 0


def cmd_items(a) -> int:
    from . import ledger
    root = _root(a)
    if a.set:
        i = ledger.set_status(root, a.set, a.status or "doing", a.note or "", by=a.by)
        print("%s → %s" % (i["id"], i["status"]))
        return 0
    items = ledger.load(root)
    if not items:
        print("还没有工作项，先运行 assess。")
        return 0
    for i in items:
        if a.status and i["status"] != a.status:
            continue
        print("[%s] W%d %-12s %-6s %-2s 命中%4d  %s" % (i["status"], i["wave"], i["id"], i["severity"], i["effort"], i["hits"], i["title"]))
        if a.verbose:
            for f in i["files"][:30]:
                print("        %s (%d)" % (f["file"], f["hits"]))
            for n in i["notes"][-3:]:
                print("        * %s %s: %s" % (n["at"], n["by"], n["text"]))
    return 0


def cmd_task(a) -> int:
    from . import task
    root = _root(a)
    if a.action == "new":
        p = task.new_task(root, a.title or "未命名任务", a.kind, a.request or "")
        print("已创建任务契约：%s" % p.relative_to(root))
        a.summary = "创建变更契约：%s" % (a.title or "未命名任务")
    else:
        for t in task.list_tasks(root):
            print("%-50s %-14s %s" % (t["title"][:50], t["status"][:14], t["acceptance"]))
    return 0


def cmd_accept(a) -> int:
    from . import acceptance as acc
    root = _root(a)

    def print_size_warnings():
        contract = acc.find_contract(root, a.task)
        peers = [p.read_text(encoding="utf-8") for p in sorted(contract.parent.glob("T*.md")) if p != contract]
        for warning in acc.size_warnings(contract.read_text(encoding="utf-8"), peers):
            print("提示：" + warning)

    try:
        if a.action == "path-check":
            from .path import path_check, path_text
            r = path_check(root, a.task or "", a.entry or None)
            print(path_text(r))
            a.summary = "入口路径检查 %s：%s" % (a.task or "", "通过" if r["ok"] else "未通过")
            return 0 if r["ok"] else 1
        if a.action == "check":
            text = acc.find_contract(root, a.task).read_text(encoding="utf-8")
            probs = acc.ac_problems(text)
            rows = acc.ac_rows(text)
            for r in rows:
                print("%-4s %-3s %-40s %s" % (r["id"], r["layer"] or "?", r["clause"][:40], r["result"][:30]))
            print("入口：%s" % ("、".join(acc.entries(text)) or "未写"))
            print("\n".join(["❌ " + x for x in probs]) or "✅ 验收标准完整，可以进入实现")
            print_size_warnings()
            a.summary = "检查验收标准 %s：%s" % (a.task, "完整" if not probs else "缺 %d 项" % len(probs))
            return 1 if probs else 0
        if a.action in ("advance", "confirm", "close", "reject"):
            to = {"confirm": "user_confirmed_fix", "close": "closed", "reject": "implementing"}.get(a.action, a.to)
            if not to:
                print("要推进到哪个状态：--to " + "|".join(acc.LABEL))
                return 2
            r = acc.advance(root, a.task, to, who=a.who or "", note=a.note or "", ref=a.ref or "", build=a.build or "")
            print("%s → %s（%s）" % (r["task"], r["state"], acc.LABEL[r["state"]]))
            if to == "implementing":
                print_size_warnings()
            for b in r["blockers"]:
                print("  阻塞：" + b)
            a.summary = "验收状态 %s → %s" % (r["task"], acc.LABEL[r["state"]])
            return 0
        if a.action == "evidence":
            from . import evidence as ev
            path = acc.evidence_path(root, acc.load(root, a.task)["task"])
            recs = ev.read(path)
            ok, why = ev.check(recs)
            for r in recs:
                print("%2d %s %-6s %-12s %s" % (r.get("seq", 0), r.get("ts", ""), r.get("kind", ""), r.get("by", ""), (r.get("hash") or "")[:16]))
            print(("✅ 证据包完整，%d 条记录，哈希 %s" % (len(recs), ev.head(recs))) if ok and recs else ("还没有证据包（进入待人工验收或自动证据齐全时生成）" if ok else "❌ " + why))
            a.summary = "证据包 %s：%s" % (a.task, "完整" if ok else "被改动")
            return 0 if ok else 1
        if a.action == "correct":
            r = acc.correct(root, a.task, a.kind or "other", a.note or "", a.who or "")
            print("已记录纠错 %s（%s 类第 %d 次）" % (r["task"], r["kind"], r["count"]))
            if r["due"]:
                print("达到阈值 %d：请提一个评审 PR 更新 skills/acceptance-l2 的反模式检查项，不要只改会话记忆。" % r["threshold"])
            return 0
        rows = acc.by_build(root, a.build) if a.build else ([acc.load(root, a.task)] if a.task else acc.records(root))
        if a.build:
            print("构建 %s 可验收的任务 %d 个：" % (a.build, len(rows)))
        for r in rows:
            print("%-6s %-26s 构建 %-10s %s%s" % (r["task"], "%s（%s）" % (r["state"], acc.LABEL[r["state"]]), r.get("build_id") or "-",
                                             r["file"], "  阻塞：" + "；".join(r["blockers"]) if r["blockers"] else ""))
        return 0
    except acc.Refused as e:
        print("拒绝：%s" % e)
        a.summary = "验收操作被拒绝：%s" % str(e).splitlines()[0]
        return 1


def cmd_baseline(a) -> int:
    from .verify import take_baseline
    b = take_baseline(_root(a), run_tests=a.with_tests)
    print("基线：提交 %s，受保护文件 %d 个，已知不兼容点 %d 处。" % ((b["head"] or "无 git")[:12], len(b["protected"]), b["finding_count"]))
    if b["tests"]:
        for c in b["tests"]:
            print("  %s 退出码 %s" % (c["command"], c["exit_code"]))
    a.summary = "记录基线：受保护文件 %d 个" % len(b["protected"])
    return 0


def cmd_evidence_verify(a) -> int:
    """Check an exported evidence package (<KEY>.intoto.json) without webuddy, against the hash you kept when signing."""
    from . import evidence as ev
    try:
        st = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("读不了这个文件：%s" % e)
        return 2
    if a.hash and len(a.hash.strip()) < ev.MIN_ANCHOR:
        print("--hash 太短：请填签收页上显示的完整哈希（至少前 %d 位）。太短的前缀，改过记录的人可以凑出来。" % ev.MIN_ANCHOR)
        return 2
    verdict, notes = ev.verify_statement(st, a.hash or "", a.key or "", marked=True)
    for mark, n in notes:
        print(mark + " " + n)
    if a.payload:  # for checking with plain OpenSSH: the exact signed bytes and the signature, side by side
        Path(a.payload).write_bytes(ev.payload(st))
        if isinstance(st.get("signature"), dict) and st["signature"].get("sig"):
            Path(a.payload + ".sig").write_text(st["signature"]["sig"] + "\n", encoding="utf-8")
            print("  已写出 %s 和 %s.sig，可用 ssh-keygen -Y check-novalidate -n webuddy-evidence@v1 -s %s.sig < %s 自行验签"
                  % (a.payload, a.payload, a.payload, a.payload))
    summ = (st.get("predicate") or {}).get("summary") or {}
    if summ:
        print("  %s %s · %s" % (summ.get("ticket", ""), summ.get("title", ""), summ.get("label", "")))
    print("结论：%s" % {"anchored": "可信：你签收时记下的那条及之前的记录都没被改过",
                       "consistent": "未核实：加上 --hash 签收页上的完整哈希 再核对一次",
                       "bad": "不可信"}[verdict])
    return {"anchored": 0, "consistent": 3, "bad": 1}[verdict]


def cmd_verify(a) -> int:
    from .verify import verify, verify_md
    r = verify(_root(a), run_tests=not a.no_tests, timeout=a.timeout, task=a.task or "")
    print(verify_md(r))
    a.summary = "独立验证：%s" % ("通过" if r["passed"] else "未通过")
    return 0 if r["passed"] else 1


def cmd_hook(a) -> int:
    from . import guard
    fn = {"pre-edit": guard.pre_edit, "post-edit": guard.post_edit, "pre-bash": guard.pre_bash,
          "stop": guard.stop, "pre-commit": guard.pre_commit, "agent-pre": guard.agent_pre, "agent-post": guard.agent_post}[a.event]
    try:
        return fn()
    except SystemExit:
        raise
    except Exception as e:  # a broken hook must never wedge the agent session
        sys.stderr.write("[tmh] 钩子内部错误（已放行）：%r\n" % (e,))
        return 0


def cmd_agent_config(a) -> int:
    from . import agentcfg
    if a.engine == "claude":
        print(agentcfg.claude_config(a.provider, a.model, a.fast_model or ""))
    else:
        print(agentcfg.codex_config(a.provider, a.model, a.fast_model or ""))
    print("# 冒烟测试提示（启动智能体后粘贴）：\n# " + agentcfg.SMOKE_PROMPT.replace("\n", "\n# "))
    return 0


def cmd_status(a) -> int:
    from . import ledger, task
    from .verify import load_baseline
    root = _root(a)
    x = cfgmod.tmh_dir(root)
    cfg = cfgmod.load(root)
    print("tmh %s · 仓库 %s" % (__version__, root))
    print("目标：" + ", ".join("%s=%s" % (k, cfg["target"][k]) for k in TARGET_KEYS) + "；源库=%s" % cfg["source"]["db"])
    b = load_baseline(root)
    print("基线：%s" % ("提交 %s，%s" % ((b["head"] or "-")[:12], b["created"]) if b else "未建立（运行 baseline）"))
    print("项目地图：%s" % ("已生成" if (x / "PROJECT_MAP.md").exists() else "未生成（运行 map）"))
    stale = x / "stale-files.txt"
    if stale.exists():
        n = len(set(stale.read_text(encoding="utf-8").split()))
        if n:
            print("  地图后已改动 %d 个文件，结束前运行 map 刷新，并更新 .tmh/knowledge/ 中相关说明" % n)
    items = ledger.load(root)
    if items:
        from collections import Counter
        c = Counter(i["status"] for i in items)
        print("工作项：" + "，".join("%s %d" % kv for kv in c.items()))
    ts = task.list_tasks(root)
    if ts:
        print("任务契约：%d 个，最新：%s（%s）" % (len(ts), ts[-1]["title"], ts[-1]["status"]))
    lv = x / "reports" / "verify-latest.json"
    if lv.exists():
        r = json.loads(lv.read_text(encoding="utf-8"))
        print("最近验证：%s %s" % (r["time"], "通过" if r["passed"] else "未通过"))
    kn = x / "knowledge"
    if kn.is_dir():
        notes = [p.name for p in kn.glob("*.md") if p.name != "README.md"]
        print("项目知识笔记：%s" % (", ".join(sorted(notes)) or "尚无（接管项目时用 legacy-onboard 技能编写）"))
    return 0


def _load_flows(root: Path) -> dict:
    from . import flow
    data = flow.build_flows(root)
    x = cfgmod.tmh_dir(root)
    x.mkdir(parents=True, exist_ok=True)
    (x / "flows.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data




def cmd_flows(a) -> int:
    from . import activity, flow, webreport
    root = _root(a)
    data = _load_flows(root)
    flows = data["flows"]
    if a.changed:
        from .fsutil import git_changed_files, git_changed_lines
        from .verify import load_baseline, source_changes
        b = load_baseline(root)
        files = source_changes(git_changed_files(root, b.get("head") if b else None) or [])
        flows = webreport.affected_flows(flows, files, git_changed_lines(root, b.get("head") if b else None))
        print("相对基线改动源文件 %d 个，按改动行定位到业务流 %d 条：" % (len(files), len(flows)))
        a.summary = "改动影响的业务流：%s" % ("、".join(f["name"] or f["trigger"] for f in flows) or "无")
    if a.query:
        q = " ".join(a.query).lower()
        hit = [f for f in flows if f["id"] == q] or [f for f in flows if q in json.dumps([f["id"], f["trigger"], f["name"], f["handler"], list(f["crud"])], ensure_ascii=False).lower()]
        if a.json:
            _out(hit)
        else:
            print("\n\n".join(flow.flow_text(f) for f in hit) or "没有匹配的业务流。")
        a.summary = "查看业务流“%s”：%s" % (" ".join(a.query), "、".join(f["name"] or f["id"] for f in hit[:3]) or "无匹配")
        return 0
    if a.notes:
        from . import kb
        made = 0
        for f in flows:
            if not (cfgmod.tmh_dir(root) / "knowledge" / "flows" / ("%s.md" % f["id"])).exists():
                made += 1
        kb.build(root)
        kb.add_pages(root, ["flow:" + f["id"] for f in flows])  # also flows outside the full-analysis scope
        kb.build(root)
        print("已在 .tmh/knowledge/flows/ 生成 %d 个待补充的业务说明（知识库页面，含自动抽取的事实；用 tmh kb next 领取撰写）" % made)
    if a.json:
        _out(data)
        return 0
    for f in flows:
        crud = " ".join("%s:%s" % kv for kv in f["crud"].items())
        print("%-28s %-34s %s  %s" % (f["id"][:28], (f["name"] or "-")[:20], f["trigger"][:40], crud))
    sms = data["state_machines"]
    print("\n共 %d 条业务流，%d 个状态机（%s）。详情：tmh flows <id或关键词>；可视化：tmh report" % (
        len(data["flows"]), len(sms), "、".join("%s.%s" % (s["table"], s["column"]) for s in sms) or "无"))
    if not getattr(a, "summary", ""):
        a.summary = "识别 %d 条业务流、%d 个状态机" % (len(data["flows"]), len(sms))
    return 0


def cmd_report(a) -> int:
    from . import webreport
    root = _root(a)
    data = _load_flows(root)
    if a.classic:
        p = webreport.write(root, data)
        target = p.with_name("classic.html")
        from .fsutil import replace_file
        replace_file(p, target)
        p = target
        print("已生成 %s（单文件，可离线打开或发给同事）" % p.relative_to(root))
    else:
        from . import explorer
        p = explorer.write(root, data)
        print("已生成 %s（连同 data/ 文件夹一起离线打开；发给同事时把整个 report 文件夹打包）" % p.relative_to(root))
    if a.open:
        import webbrowser
        webbrowser.open(p.resolve().as_uri())
    a.summary = "生成分析报告：%d 条业务流" % len(data["flows"])
    return 0


def cmd_note(a) -> int:
    from . import activity
    root = _root(a)
    if not cfgmod.tmh_dir(root).is_dir():
        print("没有 .tmh 目录，先运行 install", file=sys.stderr)
        return 2
    activity.log(root, a.kind, a.text, detail=a.detail or "", flow=a.flow or "")
    print("已记录")
    return 0


def cmd_kb(a) -> int:
    from . import kb
    root = _root(a)
    cfgmod.tmh_dir(root).mkdir(parents=True, exist_ok=True)
    act = a.action
    if act == "build":
        r = kb.build(root, use_cache=not a.no_cache)
        from . import discover, report
        from .fsutil import git_head
        x = cfgmod.tmh_dir(root)
        m = json.loads((x / "map.json").read_text(encoding="utf-8"))
        (x / "PROJECT_MAP.md").write_text(report.map_md(discover.discover(root), m, git_head(root)), encoding="utf-8")
        if (x / "stale-files.txt").exists():
            remove_file(x / "stale-files.txt")
        gr = r["graph"]
        print("知识图谱：节点 %d，边 %d（%s）" % (gr["nodes"], gr["edges"], "，".join("%s %d" % kv for kv in sorted(gr["kinds"].items()))))
        print("解析：%s 个文件重新解析，%d 个来自缓存；用时 %.1f 秒" % (gr["parsed"], gr["cached"], r["seconds"]))
        _print_cov(r["coverage"])
        if r["stale"]:
            print("代码变化导致 %d 个知识页过期：%s" % (len(r["stale"]), "、".join(r["stale"][:12]) + (" 等" if len(r["stale"]) > 12 else "")))
            print("  → 用 tmh kb next 逐个修订（只需按变化改，不必重写）")
        if r["orphans"]:
            print("对应代码已不存在的页面：%s（确认后可删除文件）" % "、".join(r["orphans"][:12]))
        a.summary = "构建知识库：%d 个节点，%d 个业务域，%d 页过期" % (gr["nodes"], gr["domains"], len(r["stale"]))
        return 0
    if act == "status":
        reg = kb.load_registry(root)
        if not reg:
            print("还没有知识库，先运行 tmh kb build")
            return 1
        _print_cov(kb.coverage(reg))
        pend = kb.pending(root, reg)
        print("待处理任务 %d 个%s" % (len(pend), "：" + "、".join(pend[:10]) + (" 等" if len(pend) > 10 else "") if pend else ""))
        from . import kbqa
        q = kbqa.stats(root)
        print("业务方问题：未答复 %d 个，已答复 %d 个；需求预判 %d 次，其中可直接答复 %d 次" % (q["questions_open"], q["questions_answered"], q["triage"], q["triage_auto"]))
        if q["triage"]:
            print(kbqa.metrics_text(kbqa.metrics(root)).splitlines()[0])
        return 0
    if act == "next":
        r = kb.next_jobs(root, n=a.n, who=a.who, only=a.page)
        if not r["jobs"]:
            if r["remaining"]:
                print("还有 %d 个任务，但都在等下层页面或被其他代理领走（%d 个）。稍后再试。" % (r["remaining"], r["claimed_by_others"]))
            else:
                print("知识库已全部完成，没有待处理任务。")
            return 0
        for pid in r["jobs"]:
            print(kb.instructions(root, pid))
            print("\n## 上下文\n")
            print(kb.pack(root, pid, a.budget))
            print("\n" + "=" * 60 + "\n")
        print("（剩余任务 %d 个）" % (r["remaining"] - len(r["jobs"])))
        a.summary = "领取知识库任务：" + "、".join(r["jobs"])
        return 0
    if act == "pack":
        print(kb.pack(root, a.target, a.budget))
        return 0
    if act == "done":
        ok, errs = kb.done(root, a.target, a.who)
        if not ok:
            print("还不能入库，请修正：")
            for e in errs:
                print("  - " + e)
            return 1
        reg = kb.load_registry(root)
        print("已入库：%s（待确认）。剩余任务 %d 个。" % (a.target, len(kb.pending(root, reg))))
        a.summary = "知识页入库：" + a.target
        return 0
    if act == "confirm":
        kb.confirm(root, a.target, a.who)
        print("已确认：" + a.target)
        return 0
    if act == "show":
        print(kb.show(root, a.target))
        return 0
    return _kb_qa(a, root, act)


def _kb_qa(a, root: Path, act: str) -> int:
    """Read the knowledge base as written, and the human question/answer loop (tmh/kbqa.py)."""
    from . import kbqa
    words = [x for x in [a.target] + list(a.rest or []) if x]
    if act == "read":
        if not words:
            print("用法：tmh kb read <页面 id>…（如 index、dom:bank、flow:post-approva-action、glossary.md）")
            return 2
        print(kbqa.read(root, words, a.budget or 30000))
        return 0
    if act == "chain":
        print(kbqa.chain_text(root, kbqa.chain(root, " ".join(words), a.budget or 30000)))
        a.summary = "读取业务链路：" + " ".join(words)[:60]
        return 0
    if act == "questions":
        qs = [q for q in kbqa.questions(root) if a.all or q["open"]]
        for q in qs:
            print("#%d %s\n    涉及：%s；问：%s；%s" % (q["n"], q["question"], q["pages_text"], q["who"], q["answer"]))
        s = kbqa.stats(root)
        print("未答复 %d 个，已答复 %d 个；人工已确认 %d 页，答复后待修订 %d 页" % (s["questions_open"], s["questions_answered"], s["confirmed"], s["revise"]))
        return 0
    if act == "ask":
        if not words:
            print("用法：tmh kb ask \"<问题>\" --pages dom:x,flow:y --to <要问谁>")
            return 2
        n = kbqa.ask(root, " ".join(words), [x for x in (a.pages or "").split(",") if x], a.to or "", a.who)
        print("已记入待确认问题 #%d（%s）" % (n, kbqa.QFILE))
        return 0
    if act == "answer":
        if len(words) < 2 or not words[0].lstrip("#").isdigit():
            print("用法：tmh kb answer <问题编号> \"<答复原文>\" --who <答复人>")
            return 2
        try:
            r = kbqa.answer(root, int(words[0].lstrip("#")), " ".join(words[1:]), a.who)
        except (KeyError, ValueError) as e:
            print(e.args[0])
            return 1
        print("已记录问题 #%d 的答复%s" % (r["n"], "，写入并排队修订：" + "、".join(r["pages"]) if r["pages"] else "（问题没有关联知识页）"))
        print("下一步：tmh kb next 修订这些页面，修订后由人 tmh kb confirm 确认。")
        a.summary = "记录业务方答复 #%d" % r["n"]
        return 0
    if act == "triage":
        req = " ".join(words)
        if not req:
            print("用法：tmh kb triage \"<需求或问题原文>\" [--record] [--no-model] [--json]")
            return 2
        res = kbqa.triage(root, req, use_model=not a.no_model)
        if a.record:
            res["recorded"] = kbqa.record(root, res, a.who)
        print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else kbqa.triage_text(res))
        if not a.json:
            print("\n预判编号 %s（结论不对时：tmh kb overrule %s --who <姓名> --reason \"…\"）" % (res["id"], res["id"]))
        if a.record and not a.json:
            rec = res["recorded"]
            print("\n已记入待确认问题：%s；已排队补写：%s" % ("、".join("#%d" % n for n in rec["questions"]) or "无", "、".join(rec["queued"]) or "无"))
        a.summary = "需求预判（%s）：%s" % (res["verdict"], req[:50])
        return 0
    if act == "overrule":
        if not words:
            print("用法：tmh kb overrule <预判编号> --who <姓名> --reason \"<为什么不对>\" [--verdict 可以做|不能做|需要人判断]")
            return 2
        try:
            kbqa.overrule(root, words[0], a.who, a.reason or " ".join(words[1:]), a.verdict or "")
        except (KeyError, ValueError) as e:
            print(e.args[0])
            return 1
        print("已记录改判：%s（计入少找人统计的采纳率）" % words[0])
        a.summary = "改判需求预判 %s" % words[0]
        return 0
    if act == "metrics":
        m = kbqa.metrics(root, a.days or 0)
        if a.json:
            print(json.dumps(m, ensure_ascii=False, indent=1))
            return 0
        print(kbqa.metrics_text(m))
        rows = kbqa.triages(root, 10)
        if rows:
            print("\n最近的预判：")
            for r in rows:
                print("  %s %s [%s/%s%s] %s%s" % (r.get("id", "—"), r.get("at", ""), r.get("verdict"), r.get("confidence"),
                                                "，%s" % r["channel"] if r.get("channel") and r["channel"] != "cli" else "", r.get("request", "")[:50],
                                                "（%s 改判）" % r["overruled"]["by"] if r.get("overruled") else ""))
        return 0
    return 1


def _print_cov(c: dict) -> None:
    names = {"flow": "业务流", "tbl": "业务对象", "mod": "模块", "dom": "业务域", "index": "总览"}
    order = ["已确认", "待确认", "过期", "未分析", "仅事实"]
    print("知识页：" + "，".join("%s %d" % (k, c["total"][k]) for k in order if c["total"].get(k)))
    for k in ("index", "dom", "flow", "tbl", "mod"):
        v = c["by_kind"].get(k)
        if v:
            print("  %s：%s" % (names[k], "，".join("%s %d" % (s, v[s]) for s in order if v.get(s))))
    if c.get("context_chars"):
        print("累计投入上下文约 %d 万字符（≈ %d k tokens）" % (c["context_chars"] // 10000, c["context_chars"] // 3000))


def cmd_context(a) -> int:
    from .context import build_context
    from .graph import graph_path
    root = _root(a)
    if not graph_path(root).exists():
        print("还没有知识库，先运行 tmh kb build")
        return 1
    print(build_context(root, " ".join(a.query), a.budget))
    a.summary = "查询项目知识：" + " ".join(a.query)[:60]
    return 0


def cmd_offline_pack(a) -> int:
    from . import offline
    if a.verify:
        r = offline.verify(Path(a.verify))
        print("校验%s：%d 个文件%s" % ("通过" if r["ok"] else "不通过", r["files"],
                                  "".join("\n  %s：%s" % (k, "、".join(r[k][:20])) for k, l in (("bad", "内容不符"), ("missing", "缺失"), ("extra", "多出")) if r[k])))
        return 0 if r["ok"] else 1
    out = Path(a.out or "tmh-offline-%s.zip" % __version__).resolve()
    r = offline.build(out)
    print("已生成 %s：%d 个文件，%.1f MB（压缩后 %.1f MB）\nsha256 %s" % (r["out"], r["files"], r["bytes"] / 1e6, r["zip_bytes"] / 1e6, r["sha256"]))
    print("拷到内网后：python3 tmh.py offline-pack --verify <压缩包> 校验，再按包里的 README-offline.md 安装。")
    return 0


def cmd_serve(a) -> int:
    import getpass
    from .platform.server import serve
    project = None
    if a.project or (_root(a) / ".tmh").is_dir():
        project = Path(a.project or a.repo).resolve()
    return serve(Path(a.data).expanduser(), a.host, a.port, a.user or getpass.getuser(), project, a.key, a.open, a.brand or "",
                 getattr(a, "preview_port", 0) or 0)


def cmd_user(a) -> int:
    import getpass
    import sys
    from .platform import login
    data = Path(a.data).expanduser()
    if a.action == "list":
        for name, u in sorted(login.load_users(data).items()):
            print("%s\t（%s 设置密码）" % (name, u.get("updated", "")))
        return 0
    if not a.name:
        print("要写用户名：tmh user %s <名字>" % a.action)
        return 2
    if a.action == "del":
        ok = login.del_user(data, a.name)
        print("已删除 %s" % a.name if ok else "没有这个用户：%s" % a.name)
        return 0 if ok else 1
    if a.password_stdin:
        pw = sys.stdin.readline().rstrip("\n")
    else:
        pw = getpass.getpass("给 %s 设密码（至少 8 位）：" % a.name)
        if pw != getpass.getpass("再输一遍："):
            print("两次输入不一样")
            return 1
    try:
        login.set_user(data, a.name, pw)
    except ValueError as e:
        print(e)
        return 1
    print("已设置 %s 的密码。网页登录页：/login" % a.name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tmh", description="传统 toB 软件项目维护 harness：业务流理解、新需求、改造（含信创）")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--repo", default=".", help="目标仓库根目录（默认当前目录）")
        p.set_defaults(fn=fn)
        return p

    p = add("init", cmd_init, "设定改造目标（写入 .tmh/config.json）")
    for k in TARGET_KEYS:
        p.add_argument("--target-" + k, dest="target_" + k, help="可选：" + "/".join(cfgmod.CHOICES[k]))
    p.add_argument("--source-db", choices=cfgmod.CHOICES["db"])
    p.add_argument("--name")
    p = add("install", cmd_install, "把 harness 安装进目标仓库（技能/子代理/钩子/AGENTS.md）")
    p.add_argument("--engines", default="claude,codex")
    p.add_argument("--git-hook", action="store_true", help="同时安装 git pre-commit 保护")
    add("assess", cmd_assess, "信创评估：技术栈 + 规则扫描 + 分波次报告 + 工作项")
    add("map", cmd_map, "生成项目地图（入口、任务、数据访问、表→代码）")
    p = add("scan", cmd_scan, "只跑规则扫描")
    p.add_argument("files", nargs="*")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=60)
    p = add("where", cmd_where, "按关键词定位代码（支持中文业务词）")
    p.add_argument("keywords", nargs="+")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p = add("impact", cmd_impact, "影响分析：类名 / 表名 / 文件路径")
    p.add_argument("target")
    p.add_argument("--depth", type=int, default=3, help="反向引用追溯层数")
    p.add_argument("--json", action="store_true")
    p = add("items", cmd_items, "查看/更新改造工作项")
    p.add_argument("--status", help="过滤或设置状态：todo/doing/done/blocked/wontfix")
    p.add_argument("--set", metavar="ID", help="要更新的工作项 ID")
    p.add_argument("--note")
    p.add_argument("--by", default="agent")
    p.add_argument("-v", "--verbose", action="store_true")
    p = add("task", cmd_task, "需求/变更契约")
    p.add_argument("action", choices=["new", "list"])
    p.add_argument("title", nargs="?")
    p.add_argument("--kind", default="feature", choices=["feature", "migration", "bugfix", "refactor", "upgrade"])
    p.add_argument("--request", help="需求原文")
    p = add("accept", cmd_accept, "验收状态机：检查 AC、入口路径检查、推进状态；关单只认用户确认（docs/acceptance.md）")
    p.add_argument("action", choices=["status", "check", "path-check", "advance", "reject", "confirm", "close", "correct", "evidence"],
                   help="status 看状态（--build 按构建列）；check 检查 AC；path-check 改动是否接上契约入口；advance --to 推进；"
                        "reject 退回实现；confirm/close 由人确认、关单；correct 记一次纠错；evidence 看证据包和哈希链")
    p.add_argument("task", nargs="?", help="任务号，如 T001")
    p.add_argument("--to", help="advance 的目标状态")
    p.add_argument("--who", help="谁做的（confirm/close 必填姓名）")
    p.add_argument("--note", help="说明；退回实现时写原因")
    p.add_argument("--ref", help="合并：提交号或合并请求")
    p.add_argument("--build", help="部署：可测构建号/版本；status 时按构建列出")
    p.add_argument("--entry", action="append", help="path-check：不读契约，直接给入口（可多次）")
    p.add_argument("--kind", help="correct：too-big / wrong-direction / misroute / other")
    p = add("baseline", cmd_baseline, "记录基线（受保护文件、已知不兼容点，可选跑测试）")
    p.add_argument("--with-tests", action="store_true")
    p = add("verify", cmd_verify, "独立验证闸门")
    p.add_argument("--no-tests", action="store_true")
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--task", help="同时检查改动是否接上这个任务契约的入口（tmh accept path-check）")
    p = add("hook", cmd_hook, "智能体钩子入口（由 .claude/settings.json 调用）")
    p.add_argument("event", choices=["pre-edit", "post-edit", "pre-bash", "stop", "pre-commit", "agent-pre", "agent-post"])
    p = add("agent-config", cmd_agent_config, "生成 Claude Code / Codex 接第三方模型的配置")
    p.add_argument("engine", choices=["claude", "codex"])
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--model", required=True)
    p.add_argument("--fast-model")
    add("status", cmd_status, "当前改造/维护状态总览")
    p = add("flows", cmd_flows, "业务流：入口 → 逻辑 → 数据访问 → 表，含状态变化与代码中的规则")
    p.add_argument("query", nargs="*", help="业务流 id 或关键词（URL、类名、表名、中文业务名）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--notes", action="store_true", help="为尚无说明的业务流生成 .tmh/knowledge/flows/<id>.md 模板")
    p.add_argument("--changed", action="store_true", help="只看当前改动影响到的业务流")
    p = add("report", cmd_report, "生成业务全景报告 .tmh/report/index.html（业务域 → 业务流 → 代码，项目构建分析；核实与推断分开标注）")
    p.add_argument("--open", action="store_true", help="生成后用浏览器打开")
    p.add_argument("--classic", action="store_true", help="生成旧版单文件报告 .tmh/report/classic.html（含分析过程时间线，适合小项目）")
    p = add("note", cmd_note, "把分析中的发现/决定/疑问记入分析过程（显示在报告里）")
    p.add_argument("kind", choices=["finding", "decision", "question", "change"])
    p.add_argument("text")
    p.add_argument("--detail", help="补充说明（Markdown）")
    p.add_argument("--flow", help="关联的业务流 id")
    p = add("kb", cmd_kb, "项目知识库：知识图谱 + Wiki（全项目分析、增量维护、过期检测）")
    p.add_argument("action", choices=["build", "status", "next", "done", "confirm", "show", "pack", "read", "chain", "questions", "ask", "answer", "triage", "overrule", "metrics"],
                   help="build 构建/增量更新；status 覆盖情况；next 领取分析任务；done 校验入库；confirm 人工确认；show 查图谱节点；pack 只看上下文；"
                        "read 按 id 读知识页原文；chain 按需求读业务链路原文；questions 待答问题；ask 记一个要问业务方的问题；answer 记录业务方答复；triage 需求预判；overrule 改判一次预判；metrics 少找人统计")
    p.add_argument("target", nargs="?", help="页面 id（如 flow:post-leave-submit、tbl:OA_LEAVE、dom:leave、index）或 show 的查询词")
    p.add_argument("rest", nargs="*", help="read 的更多页面 id；chain/ask/triage 的其余文字；answer 的答复原文")
    p.add_argument("--pages", help="ask：涉及的知识页 id，逗号分隔")
    p.add_argument("--to", help="ask：要问谁")
    p.add_argument("--all", action="store_true", help="questions：连已答复的一起列")
    p.add_argument("--record", action="store_true", help="triage：把要问的问题记入 open-questions.md，并把没写的业务流排进撰写队列")
    p.add_argument("--no-model", action="store_true", help="triage：不调用转发模型，只按规则判断")
    p.add_argument("--json", action="store_true", help="triage/metrics：输出 JSON")
    p.add_argument("--reason", help="overrule：为什么预判不对")
    p.add_argument("--verdict", help="overrule：正确的结论")
    p.add_argument("--days", type=int, help="metrics：只统计最近几天")
    p.add_argument("-n", type=int, default=1, help="next 一次领取几个任务")
    p.add_argument("--page", help="next 指定页面（按需分析范围外的页面）")
    p.add_argument("--who", default="agent", help="领取/提交者（并行时区分子代理；confirm 时写确认人）")
    p.add_argument("--budget", type=int, help="上下文包字符上限")
    p.add_argument("--no-cache", action="store_true", help="忽略解析缓存，全部重新解析")
    p = add("context", cmd_context, "按需求/关键词取出相关的知识页、业务流、表和代码位置（任务开始时先用它）")
    p.add_argument("query", nargs="+")
    p.add_argument("--budget", type=int, default=8000)
    p = add("serve", cmd_serve, "启动 tmh 运维平台（网页）：工单、看板、业务全景、知识库，内置 Claude Code / Codex")
    p.add_argument("--port", type=int, default=8790)
    p.add_argument("--host", default="127.0.0.1", help="对局域网开放用 0.0.0.0，需先设置 TMH_TOKEN")
    p.add_argument("--data", default="~/.tmh/platform", help="平台数据目录（工单库、运行记录、工作树）")
    p.add_argument("--project", help="启动时登记这个项目目录（默认：当前目录有 .tmh/ 时登记当前目录）")
    p.add_argument("--key", default="", help="登记项目时用的代号，例如 TOG")
    p.add_argument("--user", default="", help="默认用户名（网页里可改）")
    p.add_argument("--open", action="store_true", help="启动后打开浏览器")
    p.add_argument("--brand", help="界面上显示的产品名，例如 \"OA 闭环监控\"（默认“webuddy”，也可用环境变量 TMH_BRAND）")
    p.add_argument("--preview-port", type=int, default=0, help="预览版本用的独立端口（另一个源，和平台完全隔开）；"
                   "有反向代理给它起了名字时再设 TMH_PREVIEW_BASE=https://pv.example.com")
    p = add("user", cmd_user, "管理平台登录账号：add（新建或改密码）/ del / list；有账号后网页改为账号密码登录")
    p.add_argument("action", choices=["add", "del", "list"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--data", default="~/.tmh/platform", help="平台数据目录（与 tmh serve --data 相同）")
    p.add_argument("--password-stdin", action="store_true", help="从标准输入读一行作为密码（脚本用）")
    p = add("evidence-verify", cmd_evidence_verify, "离线核对导出的证据包（<工单>.intoto.json）：哈希链、摘要、你记下的哈希")
    p.add_argument("file")
    p.add_argument("--hash", help="签收页上显示的记录哈希（至少前 32 位，最好整串）")
    p.add_argument("--key", help="乙方公布的证据签名公钥指纹（SHA256:...），给了就要求签名出自这把钥匙")
    p.add_argument("--payload", help="另存签名覆盖的原始字节到这个文件（及 .sig），方便只用 ssh-keygen 验签")
    p = add("offline-pack", cmd_offline_pack, "打内网离线安装包（工具、模板、技能、子代理、信创知识库，带 sha256 清单）")
    p.add_argument("--out", help="输出的 zip 路径（默认 tmh-offline-<版本>.zip）")
    p.add_argument("--verify", help="校验一个离线包，不打包")
    from .opscli import register
    register(add)
    add("workbench", lambda a: 0, "Webuddy CLI / MCP：连接正在运行的交付工作台（workbench --help）")
    return ap


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "workbench":
        from .workbench import main as workbench_main
        return workbench_main(raw[1:])
    a = build_parser().parse_args(argv)
    rc = a.fn(a) or 0
    quiet = a.cmd == "kb" and a.action in ("status", "show", "pack", "done", "read", "questions", "ask", "answer", "overrule", "metrics")  # done logs its own entry
    quiet = quiet or a.cmd == "mcp" or (a.cmd == "int" and a.action in ("list", "types"))
    if a.cmd not in ("hook", "note", "status", "agent-config", "install", "verify", "serve", "offline-pack", "evidence-verify") and not quiet:  # verify writes its own report
        from . import activity
        argv_s = " ".join(sys.argv[1:] if argv is None else argv)
        argv_s = re.sub(r"--repo\s+\S+\s*", "", argv_s).strip()
        activity.log(_root(a), "command", getattr(a, "summary", "") or "运行 tmh %s" % a.cmd, cmd="tmh " + argv_s, rc=rc)
    return rc
