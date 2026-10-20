"""RealWorld rewrite test: the reform service rewrites a standard .NET app in Java + DM8, and the result is held
against a Java version that already exists.

The source is the official ASP.NET Core RealWorld (Conduit) backend; RealWorld is one API spec with many
implementations, so the official Spring Boot one is a ready reference, and the spec's own Hurl tests are the
acceptance bar for both. The run mirrors a real reform:

1. full-project analysis (every knowledge page, `--parallel` agents at once);
2. piece 0, the skeleton: the Maven project under java/, the DM8 schema, entities, JWT, error format, so the
   business pieces can run side by side without touching the same files; it is merged into the project branch;
3. a reform plan (框架迁移) split by business domain, every piece released at once and run `--parallel` at a time;
4. every piece's change applied onto one branch (tmh-java-all), conflicts noted;
5. a report: per piece status, time, files, build; which spec endpoints the Java code has, next to the
   reference; optionally the spec's Hurl tests against running servers (--verify).

    python3 driver.py --tmh <tob-maintenance-harness> [--work ~/tmh-realworld-test] [--port 8792] [--parallel 5]
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
KEY = "RW"
SRC = ("https://github.com/gothinkster/aspnetcore-realworld-example-app.git", "a51468ca042605d22f7c78082e5d6129c1b995c6")
REF = ("https://github.com/gothinkster/spring-boot-realworld-example-app.git", "ee17e31aafe733d98c4853c8b9a74d7f2f6c924a")
LOCAL = Path("~/Desktop/workspace/运维智能体/实测项目/重构对照").expanduser()  # copies put there when GitHub is out of reach
BRANCH, ALL = "tmh-test", "tmh-java-all"
ME = {"GIT_AUTHOR_NAME": "tmh-test", "GIT_AUTHOR_EMAIL": "tmh-test@localhost", "GIT_COMMITTER_NAME": "tmh-test",
      "GIT_COMMITTER_EMAIL": "tmh-test@localhost"}

TITLE = "RealWorld 后端改写为 Java + 达梦"
GOAL = """把 .NET 版 RealWorld 后端（src/Conduit，ASP.NET Core + EF Core）改写成 Java 版，放在仓库的 java/ 目录下：
JDK 17、Spring Boot 3、MyBatis、达梦 DM8（JDBC 驱动 com.dameng:DmJdbcDriver18），测试用 H2。

骨架已经在 java/ 里（第 0 部分做的）：Maven 工程、启动类、配置（dm 和 h2 两个 profile）、全部表的建表脚本、
实体类、MyBatis 配置、JWT 鉴权和每个接口的登录要求、统一错误格式、取当前用户。直接用，不要重做。

每个业务域只新增自己的包 com.conduit.<业务域>（controller、service、mapper 接口和 resources/mapper 下的 XML、请求和返回对象）。
尽量不改公共文件；非改不可时只追加，不改动已有内容，并在说明里写清楚改了什么。
接口规范在 spec/api/openapi.yml，spec/api/hurl 下和本域有关的测试就是验收标准。"""
KEEP = """对外接口与 .NET 版、spec/api/openapi.yml 完全一致：路径、方法、状态码、JSON 字段名和外层包装（如 {"user": {...}}、{"articles": [...], "articlesCount": n}）、错误格式。
.NET 代码只读，不改。SQL 用达梦能执行的标准写法，不用 SQLite、MySQL 方言。
不要参照或照抄任何现成的 Java 版 RealWorld。"""
SKELETON = """跨语言重写「%s」的第 0 部分：骨架。后面每个业务域都在这个骨架上并行开发，所以公共的东西这一次全部做好，业务接口一个都不写。

## 改造目标
%s

## 要做的（都在 java/ 下，.NET 代码只读）
- Maven 单模块工程：java/pom.xml，groupId com.conduit，JDK 17，Spring Boot 3，mybatis-spring-boot-starter，达梦 JDBC 驱动 com.dameng:DmJdbcDriver18，H2（test 范围），JWT 库。
- 启动类 com.conduit.ConduitApplication；application.yml 分 dm（默认）和 h2 两个 profile，端口和 .NET 版一样可配。
- 建表：照 src/Conduit/Infrastructure/ConduitContext.cs 和 Migrations 里的表、列、索引、外键，写 src/main/resources/db/schema-dm8.sql（达梦写法：IDENTITY 自增、VARCHAR/CLOB/TIMESTAMP 类型）和 schema-h2.sql，启动时按 profile 初始化。
- 实体：照 src/Conduit/Domain 写 com.conduit.domain 下的实体类，字段和表一一对应。
- MyBatis：mapper 扫描 com.conduit.**.mapper，XML 放 resources/mapper/**，下划线转驼峰按表结构配好。
- 鉴权：照 src/Conduit/Infrastructure/Security 用 JWT，请求头 `Authorization: Token <jwt>`；按 spec/api/openapi.yml 每个接口的 security 要求，把 19 个接口哪些可匿名、哪些要登录一次配好；提供取当前登录用户的组件。
- 错误格式：照 src/Conduit/Infrastructure/Errors，校验失败 422 返回 {"errors": {"字段": ["原因"]}}，未登录 401，无权限 403，找不到 404，和 .NET 版一致。
- 一个启动测试：h2 profile 下应用能起来。

## 不能变的东西
%s

## 验收条件
- `cd java && mvn -B -q compile` 通过（有测试机时在测试机上编译）。
- 没有任何业务接口代码；公共部分齐全，后面的业务域只需要加自己的包。"""


def sh(cmd, cwd=None, check=True, env=None):
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=cwd, check=check, text=True, env=env)


def out(cmd, cwd=None):
    return subprocess.run([str(c) for c in cmd], cwd=cwd, text=True, capture_output=True).stdout.strip()


class Api:
    def __init__(self, port):
        self.base = "http://127.0.0.1:%d" % port
        self.open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Content-Type": "application/json", "X-TMH": "1", "X-TMH-User": urllib.parse.quote("测试脚本")})
        try:
            with self.open(req, timeout=60) as r:
                return json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            raise RuntimeError("%s %s → %s %s" % (method, path, e.code, e.read().decode("utf-8", "replace")[:300])) from None

    def up(self):
        try:
            self.call("GET", "/api/projects")
            return True
        except Exception:  # noqa: BLE001
            return False


def busy(api) -> int:
    return sum(1 for r in api.call("GET", "/api/runs?project=" + KEY) if r["status"] in ("queued", "running"))


def settle(api, quiet=30, poll=5, label=""):
    """Wait until nothing of the project has been queued or running for `quiet` seconds."""
    calm, last = 0, 0.0
    while calm < quiet:
        time.sleep(poll)
        n = busy(api)
        calm = calm + poll if n == 0 else 0
        if n and time.time() - last > 60:
            print("  %s还有 %d 个步骤在跑或排队" % (label, n), flush=True)
            last = time.time()


def last_runs(t: dict) -> dict:
    last = {}
    for r in sorted(t.get("runs") or [], key=lambda r: r["id"]):
        last[r["mode"]] = r
    return last


def stuck(api, keys) -> list:
    """Tickets whose automatic line stopped on a failed or cancelled step."""
    res = []
    for key in keys:
        t = api.call("GET", "/api/tickets/" + key)
        last = {m: r for m, r in last_runs(t).items() if m in ("analyze", "plan", "fix")}
        if t["ticket"]["status"] in ("new", "analyzing", "confirm", "doing") and t.get("auto_next") and \
                any(r["status"] in ("failed", "cancelled") for r in last.values()):
            res.append(key)
    return res


def retry(api, keys, parallel, label):
    again = stuck(api, keys)
    for key in again:
        api.call("POST", "/api/tickets/" + key, {"auto": "go"})
        print("  %s  上一步失败，重跑" % key, flush=True)
        time.sleep(3)
    if again:
        settle(api, label=label)


def fix_diff(api, key) -> str:
    t = api.call("GET", "/api/tickets/" + key)
    fx = last_runs(t).get("fix")
    return (api.call("GET", "/api/runs/%d" % fx["id"]).get("diff") or "") if fx else ""


def testbox(api):
    try:
        return json.loads((Path(api.data) / "autoflow.json").read_text(encoding="utf-8")).get("testbox")
    except (OSError, ValueError):
        return None


def verify_of(api, key) -> tuple:
    """(last fix run, its verify.json) of a ticket."""
    fx = last_runs(api.call("GET", "/api/tickets/" + key)).get("fix")
    vf = Path(api.data) / "runs" / str(fx["id"]) / "verify.json" if fx else None
    return fx, (json.loads(vf.read_text(encoding="utf-8")) if vf and vf.exists() else {})


def recheck(api, keys, label) -> dict:
    """Build again, on the test machine, the finished changes that never compiled there (no redo); {key: check}."""
    todo = {}
    for key in keys:
        fx, v = verify_of(api, key)
        if fx and fx["status"] == "done" and v.get("check") != "pass":
            try:
                api.call("POST", "/api/runs/%d/recheck" % fx["id"], {})
            except RuntimeError as e:
                print("  %s  没法重新验证：%s" % (key, e), flush=True)
                continue
            todo[key] = fx["id"]
            print("  %s  改动还没在测试机上编译过（%s），重新验证" % (key, v.get("skip") or v.get("check") or "没有结果"), flush=True)
    last = time.time()
    while todo and any(api.call("GET", "/api/runs/%d/recheck" % rid).get("running") for rid in todo.values()):
        time.sleep(10)
        if time.time() - last > 120:
            print("  %s重新验证还在跑" % label, flush=True)
            last = time.time()
    res = {k: (verify_of(api, k)[1].get("check") or "—") for k in todo}
    for k, c in res.items():
        print("  %s  重新验证：%s" % (k, {"pass": "编译通过", "fail": "编译失败"}.get(c, c)), flush=True)
    return res


def checkout(url_sha, dest: Path, local: Path, branch: str):
    url, sha = url_sha
    if not (dest / ".git").exists():
        r = subprocess.run(["git", "clone", url, str(dest)])
        if r.returncode != 0 and (local / ".git").exists():
            print("  GitHub 连不上，改用本机副本 %s" % local, flush=True)
            shutil.rmtree(dest, ignore_errors=True)
            sh(["git", "clone", local, dest])
        elif r.returncode != 0:
            sys.exit("拉不到 %s，本机也没有副本 %s" % (url, local))
    if out(["git", "rev-parse", "-q", "--verify", sha + "^{commit}"], dest) != sha:
        sh(["git", "fetch", "-q", "origin"], dest, check=False)
    if not out(["git", "rev-parse", "-q", "--verify", "refs/heads/" + branch], dest):
        sh(["git", "checkout", "-q", "-B", branch, sha], dest)
    elif out(["git", "branch", "--show-current"], dest) != branch:
        sh(["git", "checkout", "-q", branch], dest)


def commit_all(code: Path, msg: str):
    sh(["git", "add", "-A"], code)
    if out(["git", "status", "--porcelain"], code):
        sh(["git", "commit", "-q", "-m", msg], code, env=dict(os.environ, **ME))


def analyse(api, parallel, scope):
    print("\n== 全项目分析（%s，%d 个并行）" % ("全部知识页" if scope == "all" else "业务域和总览", parallel), flush=True)
    path = "/api/projects/%s/survey" % KEY
    sv = api.call("POST", path, {"agent": "codex", "scope": scope, "parallel": parallel})
    seen = set()
    while True:
        for ln in sv.get("log") or []:
            if ln not in seen:
                seen.add(ln)
                print("  " + ln, flush=True)
        if sv["state"] not in ("starting", "building", "running", "stopping"):
            break
        time.sleep(10)
        sv = api.call("GET", path)
    print("全项目分析：%s，写成 %d 页，失败 %d 页，还剩 %s 页" % (sv["state"], sv.get("ok", 0), sv.get("failed", 0), sv.get("pending")), flush=True)


SNAP = Path("~/Desktop/workspace/运维智能体/实测项目/_截图数据/RW").expanduser()  # platform data for screenshots, no source


def snapshot(data: Path, code: Path, dest: Path = SNAP) -> None:
    """Copy the platform's records (tickets, runs, reform plans, knowledge pages, the code-structure map) where the
    screenshot session can read them. Worktrees and the source tree stay out; the database is copied with sqlite's
    backup so a half-written file is never taken."""
    import sqlite3
    try:
        dest.mkdir(parents=True, exist_ok=True)
        skip = shutil.ignore_patterns("worktrees", "*.db", "*.db-journal", "*.db-wal", "*.db-shm", "__pycache__")
        shutil.copytree(data, dest / "data", ignore=skip, dirs_exist_ok=True)
        db = data / "platform.db"
        if db.exists():
            tmp = dest / "data" / "platform.db.tmp"
            src, dst = sqlite3.connect(str(db)), sqlite3.connect(str(tmp))
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            os.replace(tmp, dest / "data" / "platform.db")
        t, d = code / ".tmh", dest / "tmh"
        for name in ("knowledge", "report"):
            if (t / name).is_dir():
                shutil.copytree(t / name, d / name, dirs_exist_ok=True)
        for name in ("flows.json", "map.json", "PROJECT_MAP.md", "activity.jsonl", "cache/graph.db"):
            if (t / name).is_file():
                (d / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(t / name, d / name)
        (dest / "快照时间.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n", encoding="utf-8")
    except Exception as e:  # a screenshot copy must never stop the test
        print("  （截图数据快照没复制成功：%s）" % e, flush=True)


def keep_snapshot(data: Path, code: Path, every: int = 180) -> None:
    import threading

    def loop():
        while True:
            snapshot(data, code)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmh", required=True)
    ap.add_argument("--work", default="~/tmh-realworld-test")
    ap.add_argument("--port", type=int, default=8792)
    ap.add_argument("--parallel", type=int, default=5, help="同时跑几个智能体（分析和改造都用这个数）")
    ap.add_argument("--agent", default="codex")
    ap.add_argument("--scope", default="all", choices=("all", "top"), help="all：全量分析；top：只写业务域和总览")
    ap.add_argument("--check", default=None, help="构建命令；默认有测试机就在测试机上编译，没有就看本机有没有 mvn")
    ap.add_argument("--testbox-from", default="~/tmh-jeecg-test/data/autoflow.json", help="沿用这里设置的测试机")
    ap.add_argument("--verify", default="", help="用规范的 Hurl 测试打已经跑起来的后端，逗号分隔，如 java=http://localhost:8080,net=http://localhost:5050")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args(argv)
    tmh, work = Path(a.tmh).resolve(), Path(os.path.expanduser(a.work)).resolve()
    sys.path.insert(0, str(tmh))
    code, ref, data = work / "realworld-net", work / "reference-java", work / "data"
    work.mkdir(parents=True, exist_ok=True)
    state_f = work / "state.json"
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}
    api = Api(a.port)
    api.data = str(data)
    if "skeleton" in state:  # an earlier version ran the skeleton as a loose ticket on the ops board: set that run aside
        if api.up():
            sys.exit("上一版测试的平台还开着（%s）。请先关掉那个窗口（Ctrl+C），再双击运行。" % api.base)
        old = work / ("data-旧版-" + time.strftime("%Y%m%d%H%M%S"))
        if data.exists():
            data.rename(old)
        if state.get("skeleton_commit") and (code / ".git").exists() and \
                out(["git", "rev-parse", "-q", "--verify", "refs/heads/" + BRANCH], code) == state["skeleton_commit"]:
            sh(["git", "checkout", "-q", "-B", BRANCH, state["skeleton_commit"] + "^"], code)  # take the old skeleton off tmh-test
        state = {k: v for k, v in state.items() if k == "analysed"}
        state_f.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print("上一版的运行数据已移到 %s，这次重新建单。" % old.name, flush=True)
    data.mkdir(exist_ok=True)

    def save():
        state_f.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    if not a.report_only and not shutil.which(a.agent):
        sys.exit("找不到 %s 命令。请在装好并已登录的终端里运行。" % a.agent)

    # 1. the .NET source on its own branch, with the API spec next to it; the Java reference beside, outside the project
    checkout(SRC, code, LOCAL / "realworld-net", BRANCH)
    checkout(REF, ref, LOCAL / "realworld-java", "reference")
    if not (code / "spec" / "api" / "openapi.yml").exists():
        shutil.copytree(HERE / "spec", code / "spec" / "api", dirs_exist_ok=True)
        commit_all(code, "测试准备：加入 RealWorld 接口规范（spec/api）")
    env = dict(os.environ, PYTHONPATH=str(tmh) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    tool = code / ".tmh" / "tool"
    shutil.rmtree(tool / "tmh", ignore_errors=True)
    shutil.copytree(tmh / "tmh", tool / "tmh", ignore=shutil.ignore_patterns("__pycache__"))
    (tool / "tmh.py").write_text("import os, sys\nsys.dont_write_bytecode = True\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
                                 "from tmh.cli import main\nsys.exit(main())\n", encoding="utf-8")
    info = code / ".git" / "info" / "exclude"
    if ".tmh/" not in (info.read_text() if info.exists() else ""):
        with info.open("a") as f:
            f.write("\n.tmh/\n")

    # 2. the data map
    if not (code / ".tmh" / "knowledge" / "domains.json").exists():
        print("\n== 生成数据地图（业务域、业务流、表）", flush=True)
        subprocess.run([sys.executable, "-m", "tmh", "kb", "build", "--repo", str(code)], env=env, check=True)

    # 3. the platform; builds on the test machine set up for the JeecgBoot test, if there is one
    try:
        box = json.loads((data / "autoflow.json").read_text(encoding="utf-8")).get("testbox")
    except (OSError, ValueError):
        box = None
    if not box:
        try:
            box = json.loads(Path(os.path.expanduser(a.testbox_from)).read_text(encoding="utf-8")).get("testbox")
        except (OSError, ValueError):
            box = None
    check = a.check if a.check is not None else ("" if box else ("" if shutil.which("mvn") else "none"))
    print("\n构建：%s" % ("在测试机 %s 上编译改到的模块" % box["host"] if box and not check else
                       "本机 mvn" if check == "" else check if check != "none" else
                       "不跑（%s）" % ("按 --check none" if a.check == "none" else "本机没有 mvn，也没有测试机")), flush=True)
    (data / "autoflow.json").write_text(json.dumps(dict({"on": True, "agent": a.agent, "plan": True, "fix": True, "commit": True,
                                                          "check": check, "max_agents": a.parallel, "max_lines": 20000}, **({"testbox": box} if box else {})),
                                                     ensure_ascii=False), encoding="utf-8")
    srv = None
    if api.up() and not a.report_only:
        sys.exit("平台已经开着（%s），可能是上一次运行留下的。请先关掉那个窗口（Ctrl+C），再双击运行，这样会用上最新的平台代码。" % api.base)
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
        api.call("POST", "/api/projects", {"key": KEY, "name": "RealWorld（.NET 转 Java 测试）", "root": str(code),
                                           "description": "官方 ASP.NET Core 版 RealWorld 改写为 Java + 达梦；对照官方 Spring Boot 版和规范自带的接口测试"})
    keep_snapshot(data, code)
    print("截图数据每 3 分钟复制一份到 %s（不含源码）" % SNAP, flush=True)
    try:
        if not a.report_only:
            run(api, a, code, state, save)
        report(api, state, work, code, ref, a.verify)
    except SystemExit as e:  # say why now, not after the platform is closed
        if e.code and not isinstance(e.code, int):
            print("\n停下了：%s" % e.code, flush=True)
            e.code = 1
        raise
    finally:
        snapshot(data, code)
        if srv:
            print("\n平台还在运行：%s/#/p/%s 。看完按 Ctrl+C 关闭。" % (api.base, KEY), flush=True)
            try:
                srv.wait()
            except KeyboardInterrupt:
                srv.terminate()


def plan_view(api, pid) -> dict:
    return next(x for x in api.call("GET", "/api/projects/%s/reforms" % KEY)["plans"] if x["id"] == pid)


def run(api, a, code: Path, state: dict, save):
    if not state.get("analysed"):
        analyse(api, a.parallel, a.scope)
        state["analysed"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save()

    # one rewrite plan: the skeleton as its lead piece (第 0 部分), then every domain at once, `parallel` agents at a time
    if not state.get("plan"):
        info = api.call("GET", "/api/projects/%s/reforms" % KEY)
        doms = [d["id"] for d in info.get("domains") or []]
        p = api.call("POST", "/api/projects/%s/reforms" % KEY, {
            "kind": "rewrite", "target": "java", "title": TITLE, "goal": GOAL, "keep": KEEP, "domains": doms, "wave": 20, "auto": True,
            "lead": {"title": "骨架", "body": SKELETON % (TITLE, GOAL, KEEP)}})
        state["plan"] = p["id"]
        save()
        print("\n== 改造计划 %s：先导「骨架」+ %d 个业务域（%s）" % (p["id"], len(p["items"]) - 1,
              "、".join(i["title"] for i in p["items"] if not i.get("lead"))), flush=True)
    plan = plan_view(api, state["plan"])
    lead = next(i for i in plan["items"] if i.get("lead"))
    if not lead.get("ticket"):
        r = api.call("POST", "/api/projects/%s/reforms/%s" % (KEY, state["plan"]), {"action": "release"})
        print("\n== 第 0 部分：骨架 %s" % "、".join(r.get("opened") or []), flush=True)
        time.sleep(5)
        lead = next(i for i in plan_view(api, state["plan"])["items"] if i.get("lead"))
    key = lead["ticket"]

    # the lead passes when it built a Maven project that compiles (or no build is set up); the script stands in for the person
    if not plan_view(api, state["plan"]).get("lead_passed"):
        settle(api, label="骨架：")
        retry(api, [key], 1, "骨架：")
        fx, v = verify_of(api, key)
        diff = fix_diff(api, key)
        if not fx or "java/pom.xml" not in diff:
            sys.exit("骨架 %s 没有改出 java/pom.xml，后面的业务域没法开始。到工作台看这张单，处理好后再双击运行会接着跑。" % key)
        box = testbox(api)
        if box and v.get("check") != "pass":
            recheck(api, [key], "骨架：")
            fx, v = verify_of(api, key)
        if v.get("check") == "fail":
            sys.exit("骨架 %s 编译没通过，后面的业务域没法开始。到工作台看这张单，处理好后再双击运行会接着跑。" % key)
        if box and v.get("check") != "pass":  # with a test machine the skeleton must really compile before anything builds on it
            sys.exit("骨架 %s 没在测试机上编译通过（%s），后面的业务域没法开始。到工作台看这张单，处理好后再双击运行会接着跑。" % (
                key, v.get("skip") or v.get("check") or "没有验证结果"))
        if not (api.call("GET", "/api/runs/%d" % fx["id"]).get("decision") or ""):  # not committed automatically: commit it on its branch
            api.call("POST", "/api/runs/%d/decide" % fx["id"], {"decision": "accept"})
            print("  骨架的改动提交到它自己的分支", flush=True)
        api.call("POST", "/api/tickets/%s/accept" % key, {"result": "pass", "note": "测试脚本验收：改出了 java/pom.xml，%s" % (
            "编译通过" if v.get("check") == "pass" else "没有跑编译（%s）" % (v.get("skip") or "未设置构建"))})
        time.sleep(3)
        pv = plan_view(api, state["plan"])
        print("  骨架验收通过，后面各部分从 %s 开始" % ((pv.get("base") or "")[:10] or "项目当前代码"), flush=True)
    elif testbox(api) and verify_of(api, key)[1].get("check") != "pass":  # accepted by an earlier run without compiling
        if recheck(api, [key], "骨架：").get(key) != "pass":
            sys.exit("骨架 %s 在测试机上编译没通过，业务域的验证先不跑。到工作台看这张单的“重新验证”结果。" % key)

    # the domains: released by the plan itself once the lead passed (auto); release here if that did not happen
    if any(not i.get("ticket") for i in plan_view(api, state["plan"])["items"]):
        try:
            r = api.call("POST", "/api/projects/%s/reforms/%s" % (KEY, state["plan"]), {"action": "release"})
            print("  放出：%s" % "、".join(r.get("opened") or []), flush=True)
        except RuntimeError as e:
            print("  放出失败：%s" % e, flush=True)
        time.sleep(5)
    keys = [i["ticket"] for i in plan_view(api, state["plan"])["items"] if i.get("ticket") and not i.get("lead")]
    print("\n== 业务域：%s（%d 个并行）" % ("、".join(keys), a.parallel), flush=True)
    time.sleep(5)
    settle(api, label="业务域：")
    retry(api, keys, a.parallel, "业务域：")
    if testbox(api) and recheck(api, keys, "业务域："):
        settle(api, label="业务域：")  # the ones that now compile go on to the automatic commit
    state["pieces_done"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save()


def integrate(api, code: Path, keys: list) -> dict:
    """Every piece's change, the lead (skeleton) first, applied onto tmh-java-all from tmh-test, one commit each; conflicts noted."""
    res = {}
    cur = out(["git", "branch", "--show-current"], code)
    sh(["git", "checkout", "-q", "-B", ALL, BRANCH], code)
    try:
        for key in keys:
            diff = fix_diff(api, key)
            if not diff.strip():
                res[key] = "没有改动"
                continue
            p = subprocess.run(["git", "apply", "--3way", "--index", "--whitespace=nowarn", "-"], cwd=code, input=diff, text=True, capture_output=True)
            if p.returncode != 0:
                bad = sorted(set(re.findall(r"(?:conflict|patch failed|error): (\S+?)(?::|\s|$)", p.stderr)))
                subprocess.run(["git", "reset", "-q", "--hard"], cwd=code)
                res[key] = "冲突：" + ("、".join(bad[:5]) or p.stderr.strip()[:200])
                continue
            subprocess.run(["git", "commit", "-q", "-m", "合入 %s" % key], cwd=code, env=dict(os.environ, **ME))
            res[key] = "已合入"
    finally:
        subprocess.run(["git", "checkout", "-q", cur or BRANCH], cwd=code)
    return res


SPRING = re.compile(r"@(Request|Get|Post|Put|Delete|Patch)Mapping\s*(?:\(([^)]*)\))?")


def spec_ops(code: Path) -> list:
    """[(METHOD, /path)] from spec/api/openapi.yml, without a YAML library."""
    ops, path = [], None
    for line in (code / "spec" / "api" / "openapi.yml").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^  (/\S*):\s*$", line)
        if m:
            path = m.group(1)
            continue
        m = re.match(r"^    (get|post|put|delete|patch):\s*$", line)
        if m and path:
            ops.append((m.group(1).upper(), path))
        elif re.match(r"^\S", line):
            path = None
    return ops


def java_ops(root: Path) -> dict:
    """{(METHOD, /path with {x}): file} from Spring annotations under root."""
    found = {}
    for f in root.rglob("*.java"):
        if "/test/" in f.as_posix():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        prefix = ""
        for m in SPRING.finditer(text):
            kind, args = m.group(1), m.group(2) or ""
            paths = re.findall(r"\"([^\"]*)\"", args) or [""]
            if kind == "Request" and text.rfind("class ", 0, m.start()) == -1:  # on the class: a prefix
                prefix = paths[0]
                continue
            verbs = [kind.upper()] if kind != "Request" else (re.findall(r"(?:RequestMethod\.|method\s*=\s*\{?\s*)([A-Z]+)\b", args) or ["ANY"])
            for v in verbs:
                for p in paths:
                    full = "/" + "/".join(x.strip("/") for x in (prefix, p) if x.strip("/"))
                    full = re.sub(r"\{(\w+)(:[^}]*)?\}", r"{\1}", full)
                    found[(v, full)] = f.relative_to(root).as_posix()
    return found


def norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip("/") or "/")


def hurl(hosts: str, code: Path) -> dict:
    """{name: {file: "通过"|"失败"}} running the spec's Hurl tests against each running server."""
    if not shutil.which("hurl"):
        print("  本机没有 hurl（brew install hurl），跳过接口测试", flush=True)
        return {}
    res = {}
    for pair in [x for x in hosts.split(",") if x.strip()]:
        name, _, host = pair.partition("=")
        res[name] = {}
        for f in sorted((code / "spec" / "api" / "hurl").glob("*.hurl")):
            p = subprocess.run(["hurl", "--test", "--jobs", "1", "--variable", "host=" + host.strip().rstrip("/"),
                                "--variable", "uid=%d" % (time.time() * 1000), str(f)], capture_output=True, text=True)
            res[name][f.stem] = "通过" if p.returncode == 0 else "失败"
    return res


def report(api, state, work: Path, code: Path, ref: Path, verify: str):
    plan = None
    if state.get("plan"):
        plan = next((x for x in api.call("GET", "/api/projects/%s/reforms" % KEY)["plans"] if x["id"] == state["plan"]), None)
    items = sorted((i for i in (plan or {}).get("items") or [] if i.get("ticket")), key=lambda i: (not i.get("lead"), i["order"]))
    pieces = [{"key": i["ticket"], "title": i["title"], "order": i["order"], "lead": bool(i.get("lead"))} for i in items]
    # with a test machine only what compiled there goes onto the merged branch, so the branch itself can build
    box = testbox(api)
    checks = {p["key"]: verify_of(api, p["key"])[1].get("check") for p in pieces}
    ok = [p["key"] for p in pieces if not box or checks[p["key"]] == "pass"]
    merged = integrate(api, code, ok) if ok else {}
    for p in pieces:
        if p["key"] not in ok:
            merged[p["key"]] = "未合入：%s" % ("测试机上编译没通过" if checks[p["key"]] == "fail" else "没在测试机上编译过")
    sec = lambda ts: time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))  # noqa: E731
    rows = []
    for p in pieces:
        t = api.call("GET", "/api/tickets/" + p["key"])
        runs = sorted(t.get("runs") or [], key=lambda r: r["id"])
        span = [(r["started"], r["ended"]) for r in runs if r.get("started") and r.get("ended")]
        last = last_runs(t)
        v = {}
        if "fix" in last:
            vf = work / "data" / "runs" / str(last["fix"]["id"]) / "verify.json"
            v = json.loads(vf.read_text(encoding="utf-8")) if vf.exists() else {}
        diff = fix_diff(api, p["key"])
        files = list(dict.fromkeys(re.findall(r"^\+\+\+ b/(\S+)", diff, re.M)))
        rows.append(dict(p, status=t["ticket"]["status"], steps={m: r["status"] for m, r in last.items()},
                         minutes=round((sec(max(e for _, e in span)) - sec(min(b for b, _ in span))) / 60, 1) if span else None,
                         java=sum(1 for f in files if f.endswith(".java")), xml=sum(1 for f in files if f.endswith(".xml")),
                         outside=[f for f in files if not f.startswith("java/")], build=v.get("check", "—"), verdict=v.get("verdict", "—"),
                         merged=merged.get(p["key"], "—")))
        d = work / "compare"
        d.mkdir(exist_ok=True)
        kw = p["title"].lower().rstrip("s")
        refs = sorted(f.relative_to(ref).as_posix() for f in ref.rglob("*") if f.is_file() and kw in f.name.lower()) if not p["lead"] else []
        (d / (p["key"] + ".md")).write_text("# %s %s\n\n## 参考版本里名字含“%s”的文件\n\n%s\n\n## 智能体的改动\n\n```diff\n%s\n```\n" % (
            p["key"], p["title"], kw, "\n".join("- " + f for f in refs) or "（按名字没找到，参考版本按分层组织，请到 reference-java 里看）", diff.strip()), encoding="utf-8")

    # endpoint coverage on the merged branch, next to the reference
    ops = spec_ops(code)
    ours = {}
    if out(["git", "rev-parse", "-q", "--verify", "refs/heads/" + ALL], code):
        tmp = work / "_all"
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=code)
        subprocess.run(["git", "worktree", "add", "-f", "--detach", str(tmp), ALL], cwd=code, capture_output=True)
        ours = {(m, norm(p)): f for (m, p), f in java_ops(tmp / "java").items()} if (tmp / "java").exists() else {}
        subprocess.run(["git", "worktree", "remove", "--force", str(tmp)], cwd=code, capture_output=True)
    theirs = {(m, norm(p)): f for (m, p), f in java_ops(ref / "src").items()} if ref.exists() else {}
    cover = [{"op": "%s /api%s" % (m, p), "ours": ours.get((m, norm("/api" + p))) or ours.get((m, norm(p))) or "",
              "ref": theirs.get((m, norm(p))) or theirs.get((m, norm("/api" + p))) or ""} for m, p in ops]
    tests = hurl(verify, code) if verify else {}

    (work / "report.json").write_text(json.dumps({"pieces": rows, "coverage": cover, "hurl": tests}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# RealWorld .NET 转 Java + 达梦：测试结果", "",
         "源：官方 ASP.NET Core 版 %s；对照：官方 Spring Boot 版 %s。合并后的 Java 代码在 realworld-net 仓库的 %s 分支。" % (SRC[1][:10], REF[1][:10], ALL), "",
         "## 每一部分", "",
         "| 部分 | 单号 | 状态 | 用时（分） | 新增 Java / XML | 改到 java/ 以外 | 构建 | 诊断 | 合并 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %d %s | %s | %s | %s | %d / %d | %s | %s | %s | %s |" % (
            r["order"], r["title"], r["key"], r["status"], "—" if r["minutes"] is None else r["minutes"], r["java"], r["xml"],
            "、".join(r["outside"][:3]) or "—", r["build"], r["verdict"], r["merged"]))
    n_ours, n_ref = sum(1 for c in cover if c["ours"]), sum(1 for c in cover if c["ref"])
    L += ["", "## 接口覆盖（规范 %d 个接口；改出来的 %d 个，参考版本 %d 个）" % (len(cover), n_ours, n_ref), "",
          "| 接口 | 改出来的 | 参考版本 |", "|---|---|---|"]
    L += ["| %s | %s | %s |" % (c["op"], c["ours"].rsplit("/", 1)[-1] or "**缺**", c["ref"].rsplit("/", 1)[-1] or "—") for c in cover]
    if tests:
        names = list(tests)
        L += ["", "## 规范自带的接口测试（Hurl）", "", "| 测试 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for f in sorted({f for v in tests.values() for f in v}):
            L.append("| %s | %s |" % (f, " | ".join(tests[n].get(f, "—") for n in names)))
    if box:
        L += ["", "只有在测试机上编译通过的部分合进了 %s；没合入的部分，改动仍在各自的单里。诊断一栏是 fail 的，说明智能体自己认为还没做完，要人看。" % ALL]
    L += ["", "每一部分的改动和参考版本对应文件的清单在 compare/ 目录。"]
    (work / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n报告：%s\n" % (work / "report.md"), flush=True)


if __name__ == "__main__":
    main()
