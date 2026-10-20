"""CLI for ops-tool integrations: tmh int / issue / ticket / build / change / quality / doc / notify / trace / mcp."""
from __future__ import annotations

import json
from pathlib import Path

from . import activity
from . import config as cfgmod
from . import integrations as I
from .integrations import link


def _root(a) -> Path:
    return Path(a.repo).resolve()


def _json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=lambda o: o.to_dict() if hasattr(o, "to_dict") else str(o)))


def _kv(pairs) -> dict:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise I.IntegrationError("参数要写成 key=value：%s" % p)
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def guarded(fn):
    def run(a):
        try:
            return fn(a) or 0
        except I.IntegrationError as e:
            print("错误：%s" % e)
            return 2
    run.__name__ = fn.__name__
    return run


def _write(a, inst: I.Integration, what: str, do):
    """Run a write. Without --confirm the HTTP client records instead of sending."""
    if a.confirm and inst.conf.get("readonly"):
        raise I.IntegrationError("%s 配置为只读（readonly: true），不能执行：%s" % (inst.name, what))
    res = do()
    if inst.http.planned:
        print("演练，没有发送。将要执行：%s" % what)
        for p in inst.http.planned:
            print("  %s %s" % (p["method"], p["url"]))
            if p.get("body"):
                print("  " + json.dumps(p["body"], ensure_ascii=False)[:800])
        print("确认无误后加 --confirm 再执行一次。")
        a.summary = "演练（未发送）：" + what
        return 0
    if isinstance(res, dict) and res.get("dry_run"):
        print("演练，没有发送：%s。加 --confirm 执行。" % what)
        return 0
    print("已执行：%s" % what)
    if getattr(a, "json", False):
        _json(res)
    activity.log(_root(a), "change", "%s：%s" % (inst.name, what), tool=inst.TYPE)
    a.summary = "%s：%s" % (inst.name, what)
    return 0


# ---------------------------------------------------------------- tmh int

@guarded
def cmd_int(a) -> int:
    root = _root(a)
    if a.action == "types":
        for t, c in sorted(I.registry(root).items()):
            caps = "、".join(I.CAP_CN.get(x, x) for x in c.CAPABILITIES) or "按配置"
            print("%-11s %s ［%s］" % (t, c.TITLE, caps))
            if a.verbose:
                for k, v in c.OPTIONS.items():
                    print("    %s：%s" % (k, v))
        print("\n加新工具：在 .tmh/integrations/ 放一个继承 tmh.integrations.Integration 的 .py 插件，或用 type=generic 写配置。详见 docs/integrations.md")
        return 0
    if a.action == "list":
        s = I.settings(root)
        ts = s.get("tools") or {}
        if not ts:
            print("还没有接入任何运维工具。tmh int types 看支持哪些，tmh int add 添加。")
            return 0
        import os
        rows = []
        for name, conf in ts.items():
            try:
                inst = I.make(root, name, conf)
                envs = inst.env_names()
                rows.append({"name": name, "type": inst.TYPE, "url": inst.url, "capabilities": list(inst.CAPABILITIES),
                             "env": {e: bool(os.environ.get(e)) for e in envs}, "readonly": bool(conf.get("readonly")), "disabled": bool(conf.get("disabled"))})
            except I.IntegrationError as e:
                rows.append({"name": name, "type": conf.get("type", ""), "error": str(e)})
        if a.json:
            _json({"tools": rows, "defaults": s.get("defaults") or {}, "agent_writes": bool(s.get("agent_writes"))})
            return 0
        for r in rows:
            if r.get("error"):
                print("✗ %s（%s）配置有误：%s" % (r["name"], r["type"], r["error"]))
                continue
            caps = "、".join(I.CAP_CN.get(c, c) for c in r["capabilities"])
            env = "，".join("%s%s" % (k, "" if v else "（未设置）") for k, v in r["env"].items()) or "无"
            flags = "".join(["［只读］" if r["readonly"] else "", "［停用］" if r["disabled"] else ""])
            print("%s %s（%s）%s %s\n    能力：%s；环境变量：%s" % ("✓" if all(r["env"].values()) else "!", r["name"], r["type"], r["url"], flags, caps, env))
        if s.get("defaults"):
            print("默认：" + "，".join("%s→%s" % (I.CAP_CN.get(k, k), v) for k, v in s["defaults"].items()))
        print("智能体写操作（MCP）：%s" % ("允许" if s.get("agent_writes") else "只演练（agent_writes=false）"))
        return 0
    if a.action == "add":
        if not a.name or not a.type:
            raise I.IntegrationError("用法：tmh int add <名字> --type <类型> --url <地址> [认证参数] [--set key=value]")
        reg = I.registry(root)
        if a.type not in reg:
            raise I.IntegrationError("不认识的类型 %s，可选：%s" % (a.type, "、".join(sorted(reg))))
        conf = {"type": a.type}
        if a.url:
            conf["url"] = a.url
        auth = {}
        if a.auth:
            auth["type"] = a.auth
        for k in ("user", "user_env", "token_env", "password_env", "account"):
            v = getattr(a, k)
            if v:
                auth[k] = v
        if a.header_name:
            auth["name"] = a.header_name
        if auth:
            auth.setdefault("type", "bearer" if "token_env" in auth else "basic")
            conf["auth"] = auth
        for k, v in _kv(a.set).items():
            conf[k] = json.loads(v) if v[:1] in "[{" or v in ("true", "false") else v
        inst = reg[a.type](a.name, conf)  # validates: rejects literal secrets
        cfg = cfgmod.load(root)
        ig = cfg.setdefault("integrations", {})
        ig.setdefault("tools", {})[a.name] = conf
        if a.default:
            for c in inst.CAPABILITIES:
                ig.setdefault("defaults", {})[c] = a.name
        cfgmod.save(root, cfg)
        from .install import refresh_mcp
        refresh_mcp(root)
        print("已添加 %s（%s），能力：%s" % (a.name, a.type, "、".join(I.CAP_CN.get(c, c) for c in inst.CAPABILITIES)))
        envs = inst.env_names()
        if envs:
            print("凭据从环境变量读取：%s。在启动 Codex / Claude Code 的终端里 export，不要写进文件。" % "、".join(envs))
        print("接着运行 tmh int test %s 检查连通性。" % a.name)
        a.summary = "接入运维工具 %s（%s）" % (a.name, a.type)
        return 0
    if a.action == "remove":
        cfg = cfgmod.load(root)
        ig = cfg.get("integrations") or {}
        if a.name not in (ig.get("tools") or {}):
            raise I.IntegrationError("没有名为 %s 的接入" % a.name)
        del ig["tools"][a.name]
        ig["defaults"] = {k: v for k, v in (ig.get("defaults") or {}).items() if v != a.name}
        cfgmod.save(root, cfg)
        from .install import refresh_mcp
        refresh_mcp(root)
        print("已移除 %s" % a.name)
        return 0
    if a.action == "test":
        names = [a.name] if a.name else list(I.tools(root))
        if not names:
            print("还没有接入任何运维工具")
            return 0
        bad = 0
        for n in names:
            try:
                msg = I.make(root, n).ping()
                print("✓ %s：%s" % (n, msg))
            except I.IntegrationError as e:
                bad += 1
                print("✗ %s：%s" % (n, e))
        a.summary = "检查运维工具连通性：%d/%d 正常" % (len(names) - bad, len(names))
        return 1 if bad else 0
    raise I.IntegrationError("未知操作 %s" % a.action)


# ---------------------------------------------------------------- issues

def _print_issue(i: I.Issue) -> None:
    print("%s %s" % (i.key, i.title))
    print("  " + "、".join("%s：%s" % (k, v) for k, v in (("类型", i.type), ("状态", i.status), ("优先级", i.priority), ("经办人", i.assignee)) if v))
    if i.url:
        print("  " + i.url)


@guarded
def cmd_issue(a) -> int:
    root = _root(a)
    inst = I.pick(root, "issues", a.via, dry_run=not a.confirm)
    if a.action == "get":
        i = inst.get_issue(a.target)
        if a.json:
            _json(i)
        else:
            _print_issue(i)
            if i.description:
                print("\n" + i.description.strip()[:3000])
            for c in i.comments:
                print("\n— %s %s\n%s" % (c["author"], c["created"][:16], c["body"].strip()[:800]))
        a.summary = "查看工单 %s" % a.target
        return 0
    if a.action == "search":
        rows = inst.search_issues(" ".join([a.target or ""] + (a.text or [])).strip(), a.limit)
        if a.json:
            _json(rows)
        else:
            for i in rows:
                print("%-12s %-8s %s" % (i.key, i.status, i.title))
            print("共 %d 条（%s）" % (len(rows), inst.name))
        a.summary = "搜索工单：%s" % a.target
        return 0
    if a.action == "comment":
        body = " ".join(a.text or [])
        if not body:
            raise I.IntegrationError("用法：tmh issue comment <工单号> \"评论内容\" [--confirm]")
        return _write(a, inst, "在 %s 评论 %s" % (a.target, body[:40]), lambda: inst.add_comment(a.target, body))
    if a.action == "transition":
        to = " ".join(a.text or [])
        return _write(a, inst, "把 %s 流转到 %s" % (a.target, to), lambda: inst.transition(a.target, to))
    raise I.IntegrationError("未知操作 %s" % a.action)


@guarded
def cmd_ticket(a) -> int:
    root = _root(a)
    inst = I.pick(root, "issues", a.via)
    issue = inst.get_issue(a.key)
    if a.task:
        p = link.ticket_task(root, issue)
        print("已从工单生成任务契约：%s" % p.relative_to(root).as_posix())
        print("先补全第 2–4 节（要改变/保持不变/验收标准），确认后再改代码。")
        a.summary = "从工单 %s 生成任务契约" % a.key
        return 0
    print(link.ticket_brief(root, issue, a.budget))
    a.summary = "读取工单 %s 并取相关项目知识" % a.key
    return 0


# ---------------------------------------------------------------- builds

@guarded
def cmd_build(a) -> int:
    root = _root(a)
    inst = I.pick(root, "builds", a.via, dry_run=not a.confirm)
    job = a.job or ""
    if a.action == "status":
        rows = inst.list_builds(job, a.limit)
        if a.json:
            _json(rows)
        else:
            mark = {"success": "✓", "failed": "✗", "running": "…", "unstable": "!", "aborted": "-"}
            for b in rows:
                print("%s #%-6s %-9s %s %5.0fs %s %s" % (mark.get(b.status, "?"), b.number, b.status, b.started, b.duration_s, (b.commit or "")[:8], b.cause))
        a.summary = "查看构建 %s" % (job or inst.opt("job", inst.name))
        return 0
    if a.action == "log":
        print(inst.build_log(job, a.number, a.tail))
        a.summary = "查看构建日志 %s #%s" % (job or inst.name, a.number)
        return 0
    if a.action == "failure":
        number = a.number if a.number != "last" else "lastFailed"
        b = inst.get_build(job, number)
        log = inst.build_log(job, b.number or number, max(a.tail, 400))
        r = link.failure_report(root, b, log)
        if a.json:
            _json(r)
        else:
            print(link.format_failure(r))
        a.summary = "分析构建失败 %s #%s：定位到 %d 条业务流" % (b.job, b.number, len(r["flows"]))
        return 0
    if a.action == "trigger":
        params = _kv(a.param)
        return _write(a, inst, "触发构建 %s %s" % (job or inst.opt("job", ""), params or ""), lambda: inst.trigger_build(job, params))
    raise I.IntegrationError("未知操作 %s" % a.action)


# ---------------------------------------------------------------- changes / quality / docs / notify / trace

@guarded
def cmd_change(a) -> int:
    root = _root(a)
    inst = I.pick(root, "changes", a.via)
    if a.action == "list":
        rows = inst.list_changes(a.state, a.limit)
        if a.json:
            _json(rows)
        else:
            for c in rows:
                print("%-6s %-7s %s → %s  %s（%s）" % (c.id, c.state, c.source_branch, c.target_branch, c.title, c.author))
        return 0
    if a.action == "get":
        c = inst.get_change(a.id)
        files = []
        try:
            files = inst.change_files(a.id)
        except I.NotSupported:
            pass
        flows = {}
        if files and link.has_kb(root):
            L = link.Locator(root)
            for f in files:
                for fl in L.flows_for_file(f):
                    flows[fl] = L.flow_label(fl)
        if a.json:
            _json({"change": c, "files": files, "flows": flows})
            return 0
        print("%s %s（%s，%s → %s）\n%s" % (c.id, c.title, c.state, c.source_branch, c.target_branch, c.url))
        if c.description:
            print("\n" + c.description.strip()[:2000])
        if files:
            print("\n改动文件 %d 个：" % len(files))
            print("\n".join("  " + f for f in files[:50]))
        if flows:
            print("\n涉及业务流：")
            print("\n".join("  `%s` %s" % (k, v) for k, v in flows.items()))
        a.summary = "查看合并请求 %s" % a.id
        return 0
    raise I.IntegrationError("未知操作 %s" % a.action)


@guarded
def cmd_quality(a) -> int:
    root = _root(a)
    inst = I.pick(root, "quality", a.via)
    if a.gate:
        g = inst.quality_gate()
        if a.json:
            _json(g)
        else:
            print("质量门禁：%s" % g["status"])
            for c in g["failed"]:
                print("  ✗ %s：%s（阈值 %s）" % (c["metric"], c["actual"], c["threshold"]))
        return 0
    rows = inst.quality_issues(a.path or "", a.severity or "", a.limit)
    groups = link.quality_by_flow(root, rows)
    if a.json:
        _json(groups)
        return 0
    print("未解决的质量问题 %d 条，按业务流分组：" % len(rows))
    for g, items in groups.items():
        print("\n## %s（%d）" % (g, len(items)))
        for i in items[:8]:
            print("  [%s] %s:%s %s（%s）" % (i["severity"], i.get("repo_file") or i["file"], i["line"], i["message"][:80], i["rule"]))
    a.summary = "按业务流查看质量问题 %d 条" % len(rows)
    return 0


@guarded
def cmd_doc(a) -> int:
    root = _root(a)
    inst = I.pick(root, "docs", a.via)
    if a.action == "search":
        rows = inst.search_docs(" ".join(a.query), a.limit)
        if a.json:
            _json(rows)
        else:
            for d in rows:
                print("%s  %s\n    %s\n    %s" % (d.id, d.title, d.url, d.excerpt[:120]))
        return 0
    d = inst.get_doc(a.query[0])
    if a.json:
        _json(d)
    else:
        print("# %s\n%s\n\n%s" % (d.title, d.url, d.body[:a.budget]))
    return 0


@guarded
def cmd_notify(a) -> int:
    root = _root(a)
    inst = I.pick(root, "notify", a.via, dry_run=not a.confirm)
    return _write(a, inst, "发送通知“%s”" % a.title, lambda: inst.send(a.title, a.text))


@guarded
def cmd_trace(a) -> int:
    root = _root(a)
    r = link.trace(root, a.key, a.limit)
    if a.json:
        _json(r)
        return 0
    if not r["commits"]:
        print("git 历史里没有提到 %s 的提交" % a.key)
        return 0
    print("提到 %s 的提交 %d 个：" % (a.key, len(r["commits"])))
    for c in r["commits"]:
        print("  %s %s %s %s" % (c["commit"][:10], c["date"], c["author"], c["subject"][:80]))
    print("\n改动过的文件 %d 个：" % len(r["files"]))
    print("\n".join("  " + f for f in r["files"][:40]))
    if r["flows"]:
        print("\n涉及业务流：")
        print("\n".join("  `%s` %s" % (f["id"], f["label"]) for f in r["flows"]))
    a.summary = "追溯工单 %s：%d 个提交，%d 条业务流" % (a.key, len(r["commits"]), len(r["flows"]))
    return 0


def cmd_mcp(a) -> int:
    from .mcp import serve
    return serve(_root(a))


# ---------------------------------------------------------------- parser

def register(add) -> None:
    def common(p, write=False):
        p.add_argument("--via", default="", help="指定用哪个接入（tmh int list 里的名字）")
        p.add_argument("--json", action="store_true")
        if write:
            p.add_argument("--confirm", action="store_true", help="真正执行写操作（默认只演练）")

    p = add("int", cmd_int, "运维工具接入：list 已接入 / types 支持的类型 / add 添加 / test 连通性 / remove 移除")
    p.add_argument("action", choices=["list", "types", "add", "test", "remove"])
    p.add_argument("name", nargs="?")
    p.add_argument("--type")
    p.add_argument("--url")
    p.add_argument("--auth", choices=["none", "basic", "bearer", "header", "query", "zentao"])
    p.add_argument("--user", help="用户名（不是密码，可直接写）")
    p.add_argument("--user-env", dest="user_env")
    p.add_argument("--token-env", dest="token_env", help="存放 token 的环境变量名")
    p.add_argument("--password-env", dest="password_env", help="存放密码/API token 的环境变量名")
    p.add_argument("--account", help="禅道账号")
    p.add_argument("--header-name", dest="header_name", help="header 认证的头名，如 PRIVATE-TOKEN")
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="其它配置项，如 project=OA、job=oa/master")
    p.add_argument("--default", action="store_true", help="设为它所提供能力的默认接入")
    p.add_argument("--json", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")

    p = add("issue", cmd_issue, "工单（Jira/禅道/GitLab…）：get 查看 / search 搜索 / comment 评论 / transition 流转")
    p.add_argument("action", choices=["get", "search", "comment", "transition"])
    p.add_argument("target", nargs="?", default="", help="工单号或搜索词")
    p.add_argument("text", nargs="*", help="评论内容 / 目标状态")
    p.add_argument("--limit", type=int, default=20)
    common(p, write=True)

    p = add("ticket", cmd_ticket, "按工单开工：工单内容 + 知识库里相关的业务流/表/代码；--task 直接生成任务契约")
    p.add_argument("key")
    p.add_argument("--task", action="store_true")
    p.add_argument("--budget", type=int, default=6000)
    common(p)

    p = add("build", cmd_build, "构建（Jenkins/GitLab CI…）：status 最近构建 / log 日志 / failure 失败定位到业务流 / trigger 触发")
    p.add_argument("action", choices=["status", "log", "failure", "trigger"])
    p.add_argument("job", nargs="?", default="", help="job 名（Jenkins 多级目录用 /）；GitLab 为分支，可空")
    p.add_argument("--number", default="last", help="构建号，或 last / lastFailed / lastSuccessful")
    p.add_argument("--tail", type=int, default=200)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--param", action="append", metavar="KEY=VALUE")
    common(p, write=True)

    p = add("change", cmd_change, "合并请求（GitLab…）：list / get（含改动文件涉及的业务流）")
    p.add_argument("action", choices=["list", "get"])
    p.add_argument("id", nargs="?", default="")
    p.add_argument("--state", default="open")
    p.add_argument("--limit", type=int, default=20)
    common(p)

    p = add("quality", cmd_quality, "代码质量（SonarQube…）：未解决问题按业务流分组；--gate 看质量门禁")
    p.add_argument("--path", help="只看这个目录下的")
    p.add_argument("--severity", help="最低严重级别，如 MAJOR")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--gate", action="store_true")
    common(p)

    p = add("doc", cmd_doc, "文档（Confluence…）：search 搜索 / get 读取")
    p.add_argument("action", choices=["search", "get"])
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--budget", type=int, default=8000)
    common(p)

    p = add("notify", cmd_notify, "发群通知（钉钉/飞书/企业微信/webhook），默认只演练")
    p.add_argument("title")
    p.add_argument("text")
    common(p, write=True)

    p = add("trace", cmd_trace, "按工单号追溯：哪些提交、改了哪些文件、涉及哪些业务流")
    p.add_argument("key")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    add("mcp", cmd_mcp, "以 MCP 服务方式运行（stdio），供 Codex / Claude Code 直接调用 tmh 的知识库和运维工具")
