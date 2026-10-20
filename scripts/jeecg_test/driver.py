"""JeecgBoot ticket test: 40 real, already-fixed GitHub issues go through the platform's automatic line.

Half are backend (Java) and half frontend (Vue) issues, the most recent ones counting back from 2026-09. Each ticket is
pinned to the commit just before its own fix (code_at), so the agent sees the bug as it was reported; the project itself,
and the business map built from it, sit at the commit before the earliest of these fixes, so no fix is in view.
15 tickets run the whole line (locate, plan, change the code on their own branch), 15 stop after the plan,
10 are only entered. The agent is Codex on this machine. At the end a report compares what the agent planned
or changed with the files the real fix touched.

    python3 driver.py --tmh <tob-maintenance-harness> [--work ~/tmh-jeecg-test] [--port 8791] [--parallel 3]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_URL = "https://github.com/jeecgboot/JeecgBoot.git"
KEY = "JB"
TIERS = (("full", "改到代码"), ("plan", "停在改代码前"), ("entry", "只录入"))


def sh(cmd, cwd=None, check=True):
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=cwd, check=check, text=True, capture_output=False)


def out(cmd, cwd=None):
    return subprocess.run([str(c) for c in cmd], cwd=cwd, text=True, capture_output=True).stdout.strip()


class Api:
    def __init__(self, port):
        self.base = "http://127.0.0.1:%d" % port
        self.open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # a system proxy must not see local calls

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json", "X-TMH": "1", "X-TMH-User": urllib.parse.quote("测试脚本")})
        with self.open(req, timeout=60) as r:
            return json.loads(r.read().decode() or "null")

    def up(self):
        try:
            self.call("GET", "/api/projects")
            return True
        except Exception:  # noqa: BLE001
            return False


def busy(api) -> int:
    return sum(1 for r in api.call("GET", "/api/runs?project=" + KEY) if r["status"] in ("queued", "running"))


def in_flight(api) -> int:
    """Tickets with a step queued or running."""
    return len({r["ticket_id"] for r in api.call("GET", "/api/runs?project=" + KEY) if r["status"] in ("queued", "running") and r.get("ticket_id")})


def settle(api, quiet=30, poll=5):
    """Wait until no run of the project has been queued or running for `quiet` seconds (a line's next step
    starts the moment the previous one ends, so a quiet spell means every ticket in flight has stopped)."""
    calm = 0
    while calm < quiet:
        time.sleep(poll)
        calm = calm + poll if busy(api) == 0 else 0


def stuck(api, keys) -> list:
    """Tickets whose automatic line stopped on a failed or cancelled step."""
    out = []
    for key in keys:
        t = api.call("GET", "/api/tickets/" + key)
        last = {}
        for r in sorted(t.get("runs") or [], key=lambda r: r["id"]):
            if r["mode"] in ("analyze", "plan", "fix"):
                last[r["mode"]] = r
        if t["ticket"]["status"] in ("new", "analyzing", "confirm", "doing") and t.get("auto_next") and \
                any(r["status"] in ("failed", "cancelled") for r in last.values()):
            out.append(key)
    return out


def changed(diff: str) -> list:
    return list(dict.fromkeys(m for m in re.findall(r"^\+\+\+ b/(\S+)", diff or "", re.M)))


def business_map(api, parallel):
    """Have the agent write the business map (domains and the system overview) before any ticket, the way a
    project starts on the platform: tickets are then analysed with the map, not just the parsed code graph."""
    print("\n== 用 Codex 写业务地图（业务域和系统总览）", flush=True)
    path = "/api/projects/%s/survey" % KEY
    sv = api.call("POST", path, {"agent": "codex", "scope": "top", "parallel": min(parallel, 3)})
    seen = set()
    while True:
        for ln in sv.get("log") or []:  # the last 40 lines, each stamped with its time
            if ln not in seen:
                seen.add(ln)
                print("  " + ln, flush=True)
        if sv["state"] not in ("starting", "building", "running", "stopping"):
            break
        time.sleep(10)
        sv = api.call("GET", path)
    print("业务地图：%s，写成 %d 页，失败 %d 页，还剩 %s 页" % (sv["state"], sv.get("ok", 0), sv.get("failed", 0), sv.get("pending")), flush=True)
    if sv["state"] != "done" or sv.get("pending"):
        print("  业务地图没有全部写完，工单照常处理；没写成的页可以之后在工作台“知识库 > 建设进度”里补", flush=True)


def originals(cases, work):
    """The issues' own words from GitHub (cached in the work folder). The copies in tickets.json were taken through
    a summarizing reader and some are paraphrased; this machine can reach GitHub, so ask for the real text."""
    cache_f = work / "issues.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "tmh-jeecg-test"}
    if os.environ.get("GITHUB_TOKEN"):
        hdr["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for c in cases:
        if c["issue"] not in cache:
            try:
                req = urllib.request.Request("https://api.github.com/repos/jeecgboot/JeecgBoot/issues/" + c["issue"], headers=hdr)
                with urllib.request.urlopen(req, timeout=20) as r:
                    d = json.loads(r.read().decode())
                if not d.get("pull_request"):
                    cache[c["issue"]] = {"title": d.get("title") or "", "body": d.get("body") or ""}
            except Exception as e:  # noqa: BLE001 - fall back to the copy in tickets.json
                print("  #%s 没取到 GitHub 原文（%s），用备份文本" % (c["issue"], e), flush=True)
        o = cache.get(c["issue"])
        if o and o["body"].strip():
            c["title"], c["body"] = o["title"] or c["title"], o["body"]  # a post with no title keeps the fix's wording
        if not c["title"].strip():
            c["title"] = next((ln.strip("#* ").strip() for ln in c["body"].splitlines() if ln.strip("#* ").strip()), "")[:60] or "（无标题）"
        c["title"] = re.sub(r"^[【\[]?issues/\d+[】\]]?\s*", "", c["title"]).strip(" -")
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmh", required=True)
    ap.add_argument("--work", default="~/tmh-jeecg-test")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--parallel", type=int, default=3, help="同时处理几张单")
    ap.add_argument("--check", default=None, help="改完代码后的构建测试命令；设置了测试机时默认在测试机上编译改到的模块，否则默认不跑")
    ap.add_argument("--report-only", action="store_true", help="不建单，只对已跑完的结果出报告")
    a = ap.parse_args(argv)
    tmh, work = Path(a.tmh).resolve(), Path(os.path.expanduser(a.work)).resolve()
    sys.path.insert(0, str(tmh))
    spec = json.loads((HERE / "tickets.json").read_text(encoding="utf-8"))
    code, data = work / "JeecgBoot", work / "data"
    work.mkdir(parents=True, exist_ok=True)
    data.mkdir(exist_ok=True)

    if not a.report_only and not shutil.which("codex"):
        sys.exit("找不到 codex 命令。请在装了 Codex 并已登录的终端里运行（which codex 能找到它）。")

    # 1. the code, before the earliest of the 40 fixes (each ticket is then pinned to the commit right before its own fix)
    if not (code / ".git").exists():
        sh(["git", "clone", REPO_URL, code])
    if out(["git", "rev-parse", "HEAD"], code) != spec["snapshot"]:
        sh(["git", "fetch", "-q", "origin"], code, check=False)
        sh(["git", "checkout", "-q", "-B", "tmh-test", spec["snapshot"]], code)
    env = dict(os.environ, PYTHONPATH=str(tmh) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    mark = work / "snapshot.txt"
    # +map: the agent writes the business map before any ticket; +flow3: a ticket's steps continue one agent
    # session, plans list only files that must change and are changed by one agent unless they are many
    want_map = spec["snapshot"] + "+map"
    want = want_map + "+flow3"
    old = mark.read_text().strip() if mark.exists() else ("earlier" if (work / "tickets-made.json").exists() else "")
    if old and old != want:  # an earlier ticket set or flow: keep its results aside, start the tickets clean
        tag = "-" + old[:8] + ("-nomap" if "+map" not in old else "-flow" + (old.split("+flow")[1] if "+flow" in old else "1"))
        keep_map = old.split("+flow")[0] == want_map  # the business map written for this snapshot stays in use
        for f in (data, work / "tickets-made.json", work / "report.md", work / "report.json") + (() if keep_map else (code / ".tmh" / "knowledge",)):
            if f.exists():
                f.rename(f.with_name(f.name + tag))
                print("  上一轮的 %s 改名为 %s 保留" % (f.name, f.name + tag), flush=True)
        if keep_map:
            print("  业务地图沿用上一轮写好的", flush=True)
        # the earlier run's branches keep their changes under another name, so the new runs' branches are free
        subprocess.run(["git", "worktree", "prune"], cwd=code, check=False)
        for b in out(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/tmh/"], code).split():
            subprocess.run(["git", "branch", "-m", b, "tmh-old" + tag + "/" + b[4:]], cwd=code, check=False)
        data.mkdir(exist_ok=True)
    mark.write_text(want + "\n")
    # the tmh tool the agents are told to use (flows, impact, context), as `tmh install` vendors it
    tool = code / ".tmh" / "tool"
    shutil.rmtree(tool / "tmh", ignore_errors=True)
    shutil.copytree(tmh / "tmh", tool / "tmh", ignore=shutil.ignore_patterns("__pycache__"))
    (tool / "tmh.py").write_text("import os, sys\nsys.dont_write_bytecode = True\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
                                 "from tmh.cli import main\nsys.exit(main())\n", encoding="utf-8")

    # 2. the data map (parsed from the code; the agent writes the business map on top of it below)
    if not (code / ".tmh" / "knowledge").exists():
        print("\n== 生成数据地图（业务域、业务流、表）", flush=True)
        subprocess.run([sys.executable, "-m", "tmh", "kb", "build", "--repo", str(code)], env=env, check=True)

    # 3. the platform, with the automatic line driven by Codex
    try:  # the test machine set on the platform's settings page stays
        box = json.loads((data / "autoflow.json").read_text(encoding="utf-8")).get("testbox")
    except (OSError, ValueError):
        box = None
    check = a.check if a.check is not None else ("" if box else "none")
    print("\n构建测试：%s" % ("在测试机 %s 上编译改到的模块" % box["host"] if box and not check else check if check != "none" else "不跑（平台设置页里设置了测试机就会跑）"), flush=True)
    (data / "autoflow.json").write_text(json.dumps(dict({"on": True, "agent": "codex", "plan": True, "fix": True, "commit": True,
                                                          "check": check, "max_agents": a.parallel}, **({"testbox": box} if box else {})),
                                                     ensure_ascii=False), encoding="utf-8")
    api = Api(a.port)
    srv = None
    if not api.up():
        srv = subprocess.Popen([sys.executable, "-m", "tmh", "serve", "--port", str(a.port), "--data", str(data)], env=env)
        for _ in range(60):
            if api.up():
                break
            time.sleep(1)
        else:
            sys.exit("平台没有起来，看上面的报错")
    print("\n工作台：%s/#/p/%s\n" % (api.base, KEY), flush=True)
    if not any(p["key"] == KEY for p in api.call("GET", "/api/projects")):
        api.call("POST", "/api/projects", {"key": KEY, "name": "JeecgBoot（工单测试）", "root": str(code),
                                           "description": "40 个已修复的真实 GitHub issue（前后端各半），每张单在它自己修复之前的代码上处理"})

    if not a.report_only:
        business_map(api, a.parallel)
        print("\n== 取 GitHub 上的工单原文", flush=True)
        originals(spec["cases"], work)
    state_f = work / "tickets-made.json"
    made = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
    try:
        if not a.report_only:
            for tier, label in TIERS:
                todo = [c for c in spec["cases"] if c["tier"] == tier and c["issue"] not in made]
                if tier == "entry" and not todo:
                    continue
                if not todo and not stuck(api, [made[c["issue"]] for c in spec["cases"] if c["tier"] == tier and c["issue"] in made]):
                    continue
                conf = json.loads((data / "autoflow.json").read_text(encoding="utf-8"))
                conf.update({"fix": tier == "full"})
                (data / "autoflow.json").write_text(json.dumps(conf, ensure_ascii=False), encoding="utf-8")
                print("\n== %s：%d 张" % (label, len(todo)), flush=True)
                for c in todo:  # keep `parallel` tickets going: the next one enters as soon as one stops
                    while tier != "entry" and in_flight(api) >= a.parallel:
                        time.sleep(10)
                    t = api.call("POST", "/api/tickets", {"project": KEY, "title": c["title"], "body": c["body"], "type": "bug",
                                                          "labels": ["GitHub #" + c["issue"], label, "后端" if c["kind"] == "java" else "前端"],
                                                          "auto": tier != "entry", "code_at": c["base"]})
                    made[c["issue"]] = t["key"]
                    state_f.write_text(json.dumps(made, ensure_ascii=False, indent=1), encoding="utf-8")
                    print("  %s  #%s %s" % (t["key"], c["issue"], c["title"][:50]), flush=True)
                    if tier != "entry":
                        time.sleep(5)  # its first step gets queued
                if tier != "entry":
                    settle(api)  # the line reads its settings when a ticket enters it: the next tier waits for this one
                    # a step that failed (the model service busy past its retries, say) is run once more
                    again = stuck(api, [made[c["issue"]] for c in spec["cases"] if c["tier"] == tier and c["issue"] in made])
                    for key in again:
                        while in_flight(api) >= a.parallel:
                            time.sleep(10)
                        api.call("POST", "/api/tickets/" + key, {"auto": "go"})
                        print("  %s  上一步失败，重跑" % key, flush=True)
                        time.sleep(5)
                    if again:
                        settle(api)
        report(api, spec, made, work, code)
    finally:
        if srv:
            print("\n平台还在运行：%s/#/p/%s 。看完按 Ctrl+C 关闭。" % (api.base, KEY), flush=True)
            try:
                srv.wait()
            except KeyboardInterrupt:
                srv.terminate()


def official(code: Path, base: str, gold: list) -> str:
    """The upstream commit that fixed the issue: a child of `base` on the upstream branches that touches its files."""
    refs = [r for r in out(["git", "for-each-ref", "--format=%(refname)", "refs/remotes/origin/"], code).split() if not r.endswith("/HEAD")]
    for line in out(["git", "log", "--format=%H %P", "--ancestry-path"] + ["^" + base] + refs, code).splitlines():
        h, *parents = line.split()
        if base in parents and set(gold) & set(out(["git", "diff", "--name-only", base, h], code).split()):
            return h
    return ""


def hunks(diff: str) -> dict:
    """{file: [(first old line, last old line)]} of a unified diff."""
    res, f = {}, None
    for line in (diff or "").splitlines():
        if line.startswith("+++ "):
            f = line[6:] if line.startswith("+++ b/") else None
        m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
        if m and f:
            a = int(m.group(1))
            res.setdefault(f, []).append((a, a + max(int(m.group(2) or 1), 1)))
    return res


def edits(diff: str) -> list:
    return [x for x in (diff or "").splitlines() if x[:1] in "+-" and x[:3] not in ("+++", "---") and x[1:].strip()]


def compare(code: Path, c: dict, ours: str, work: Path, key: str) -> dict:
    """How the agent's change sits against the upstream fix: which upstream hunks it touches (within 3 lines),
    how many changed lines each has and how many are the same, and the files it changed besides. Both diffs
    go to compare/<key>.md for a person to judge."""
    fix = official(code, c["base"], c["gold"])
    if not fix:
        return {}
    gd = out(["git", "diff", "-U3", c["base"], fix, "--", *c["gold"]], code)
    gh, mh = hunks(gd), hunks(ours)
    near = sum(1 for f in gh for a, b in gh[f] if any(x < b + 3 and a < y + 3 for x, y in mh.get(f, [])))
    same = len(set(edits(gd)) & set(edits(ours)))
    extra = [f for f in mh if f not in c["gold"]]
    d = work / "compare"
    d.mkdir(exist_ok=True)
    (d / (key + ".md")).write_text("# %s  GitHub #%s %s\n\n%s\n\n## 官方修复 %s\n\n```diff\n%s\n```\n\n## 智能体的改动\n\n```diff\n%s\n```\n" % (
        key, c["issue"], c["title"], c.get("url", ""), fix[:10], gd.strip(), (ours or "").strip()), encoding="utf-8")
    return {"official": fix, "hunks": sum(len(v) for v in gh.values()), "hunks_hit": near, "official_lines": len(edits(gd)),
            "our_lines": len(edits(ours)), "same_lines": same, "extra_files": extra}


def report(api, spec, made, work, code=None):
    rows = []
    for c in spec["cases"]:
        key = made.get(c["issue"])
        if not key:
            continue
        t = api.call("GET", "/api/tickets/" + key)
        tk = t["ticket"]
        runs = sorted(t.get("runs") or [], key=lambda r: r["id"])
        last = {r["mode"]: r for r in runs}
        plan_files, fix_files = [], []
        if "plan" in last:
            from tmh.platform.learn import predicted
            plan_files = predicted(api.call("GET", "/api/runs/%d" % last["plan"]["id"]).get("result") or "", [])
        cmp = {}
        if "fix" in last:
            ours = api.call("GET", "/api/runs/%d" % last["fix"]["id"]).get("diff") or ""
            fix_files = changed(ours)
            if code and ours:
                cmp = compare(code, c, ours, work, key)
        gold = c["gold"]
        same = lambda xs: [g for g in gold if any(x.endswith(g) or g.endswith(x) for x in xs)]  # noqa: E731
        ev = [e for e in (t.get("events") or []) if e.get("kind") not in ("status", "comment", "created", "run")]
        sec = lambda ts: time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))  # noqa: E731
        span = [(r["started"], r["ended"]) for r in runs if r.get("started") and r.get("ended")]
        minutes = round((sec(max(e for _, e in span)) - sec(min(b for b, _ in span))) / 60, 1) if span else None  # first step to last
        rows.append({"key": key, "issue": c["issue"], "tier": c["tier"], "title": c["title"], "status": tk.get("status"), "minutes": minutes,
                     "runs": {m: r["status"] for m, r in last.items()}, "last_step": ev[-1]["body"] if ev else "",
                     "gold": gold, "plan_files": plan_files[:20], "plan_hit": len(same(plan_files)),
                     "fix_files": fix_files, "fix_hit": len(same(fix_files)), "compare": cmp})
    (work / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# JeecgBoot 工单测试结果", "",
             "方案命中、改动命中：官方修复改的文件里，方案列到、改动改到了几个。改到官方改动处：官方修复的改动块里，智能体的改动落在附近（3 行内）的有几块。"
             "行数：智能体改了几行 / 官方改了几行，括号里是一字不差相同的行数。多改的文件多半是智能体补的测试。两边的完整 diff 在 compare/ 目录，改得对不对要人看。", "",
             "| 单号 | GitHub | 档位 | 状态 | 用时（分） | 方案命中 | 改动命中 | 改到官方改动处 | 行数（相同） | 多改的文件 | 最后一步 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    tl = dict(TIERS)
    for r in rows:
        n = len(r["gold"])
        m = r.get("compare") or {}
        lines.append("| %s | #%s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["key"], r["issue"], tl[r["tier"]], r["status"], "—" if r["minutes"] is None else r["minutes"], "%d/%d" % (r["plan_hit"], n) if r["plan_files"] else "—",
            "%d/%d" % (r["fix_hit"], n) if r["fix_files"] else "—",
            "%d/%d" % (m["hunks_hit"], m["hunks"]) if m else "—", "%d / %d（%d）" % (m["our_lines"], m["official_lines"], m["same_lines"]) if m else "—",
            "、".join(f.rsplit("/", 1)[-1] for f in m.get("extra_files", [])) or "—", r["last_step"].replace("|", "/")[:60]))
    (work / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n报告：%s\n" % (work / "report.md"), flush=True)


if __name__ == "__main__":
    main()
