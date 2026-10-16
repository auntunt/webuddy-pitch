"""The platform (`tmh serve`): tickets over the HTTP API, knowledge links, and agent runs with a stand-in agent."""
from unittest import mock
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tmh import kb  # noqa: E402
from tmh.platform.server import Platform, make_handler  # noqa: E402
from tmh.platform.store import Store  # noqa: E402
from tmh.platform.ui import page  # noqa: E402

JAVA = HERE.parent / "examples" / "legacy-java-oa"

FAKE_AGENT = r'''
import pathlib, sys
mode, pf = sys.argv[1], sys.argv[2]
p = open(pf, encoding="utf-8").read()
print("读到提示词", len(p), "字")
print("带知识库" if "知识库" in p else "没有知识库")
if mode == "fix":
    f = sorted(pathlib.Path(".").rglob("*.java"))[0]
    f.write_text(f.read_text(encoding="utf-8") + "\n// fixed by fake agent\n", encoding="utf-8")
    print("改了", f.as_posix())
if mode == "plan":
    print('```tmh-plan\n{"files": [], "ac": [{"id": "A1", "text": "审批后状态正确", "layer": "L2", "check": "跑请假测试"}]}\n```')
print("结论：问题在请假审批流程【推断】")
'''

SVC = "src/main/java/com/acme/oa/service/LeaveService.java"
UNSURE_WORD = "不清楚"
CTL = "src/main/java/com/acme/oa/controller/LeaveController.java"
# A planner that hands out files, per-file editors that message each other, and a diagnosis that reads the build.
FAKE_TEAM = r'''
import json, pathlib, re, sys
mode, pf = sys.argv[1], sys.argv[2]
p = open(pf, encoding="utf-8").read()
S, C = %r, %r
U = "src/main/java/com/acme/oa/controller/UserController.java"
if mode == "plan":
    print("方案：提交时更新状态")
    print("```tmh-plan\n" + json.dumps({"files": [{"path": S, "goal": "提交时更新状态"}],
                                        "ac": [{"id": "A1", "text": "提交后状态更新", "layer": "L2", "check": "跑请假测试"}]}) + "\n```")
elif mode == "edit":
    t = re.search(r"目标文件：`([^`]+)`", p).group(1)
    f = pathlib.Path(t)
    txt = f.read_text(encoding="utf-8")
    if t == S:
        if "去掉 BROKEN" in p:
            txt = txt.replace("// BROKEN\n", "") + "// repaired\n"
        else:
            txt += "// BROKEN\n"
            pathlib.Path(U).write_text(pathlib.Path(U).read_text(encoding="utf-8") + "// stray\n", encoding="utf-8")
        f.write_text(txt, encoding="utf-8")
        print("改了状态更新")
        print("```tmh-msg\n" + json.dumps([{"to": C, "need": "调用 submit 后刷新状态"}]) + "\n```")
    else:
        f.write_text(txt + ("// got-msg\n" if "调用 submit 后刷新状态" in p else "// no-msg\n"), encoding="utf-8")
        print("配合改了\n```tmh-msg\n[]\n```")
elif mode == "fix":  # a plan this small is done by one agent
    pathlib.Path(S).write_text(pathlib.Path(S).read_text(encoding="utf-8") + "// whole\n", encoding="utf-8")
    if "也看看用户页" in p:  # strays beyond the plan
        pathlib.Path(U).write_text(pathlib.Path(U).read_text(encoding="utf-8") + "// extra\n", encoding="utf-8")
    print("一次改完状态更新")
elif mode == "diagnose":
    bad = "BROKEN" in pathlib.Path(S).read_text(encoding="utf-8")
    d = {"verdict": "fail" if bad else "pass", "match": "wrong" if bad else "equivalent", "cause": "LeaveService 里留了 BROKEN" if bad else "",
         "files": [{"path": S, "goal": "去掉 BROKEN 标记"}] if bad else []}
    print("诊断完毕\n```tmh-diag\n" + json.dumps(d, ensure_ascii=False) + "\n```")
else:
    print("结论：LeaveService.java:12 提交时没有更新状态【核实】")
''' % (SVC, CTL)

# Writes the knowledge page it is given the way a real agent would, then submits it with `tmh kb done`.
FAKE_WRITER = r'''
import pathlib, re, sys
sys.path.insert(0, sys.argv[3])
from tmh import kb
p = open(sys.argv[2], encoding="utf-8").read()
if sys.argv[1] != "kb":  # analysing a ticket: name the flows the knowledge base pointed at
    print("结论：涉及 " + "、".join(sorted(set(re.findall(r"flow:[a-z0-9-]+", p)))[:2]))
    sys.exit(0)
pids = re.findall(r"^- (\S+:\S+|index)$", p, re.M) or [re.search(r"kb next --page ([^\s`]+)", p).group(1)]
root = pathlib.Path(".").resolve()
bad = 0
for pid in pids:
    kb.next_jobs(root, who="agent", only=pid)
    path = kb.page_path(root, pid)
    pg = kb.parse_page(path.read_text(encoding="utf-8"))
    f = sorted(root.rglob("*.java"))[0].relative_to(root).as_posix()
    body = "\n".join("## %s\n\n测试内容，见 %s:1【推断】\n" % (s, f) for s in kb.SECTIONS[kb.page_kind(pid)])
    path.write_text(kb.render_page(pid, dict(pg["meta"], title="测试页 " + pid, summary="测试摘要"), pg["facts"], body), encoding="utf-8")
    ok, errs = kb.done(root, pid, "fake")
    print("入库" if ok else "未通过：%s" % errs)
    bad += not ok
sys.exit(1 if bad else 0)
'''


def git_repo(src: Path) -> Path:
    dst = Path(tempfile.mkdtemp(prefix="tmh-plat-")) / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git"] + cmd, cwd=dst, check=True)
    return dst


class StoreTest(unittest.TestCase):
    def test_ticket_lifecycle_and_labels(self):
        d = Path(tempfile.mkdtemp())
        s = Store(d / "p.db")
        p = s.add_project("tog", "together", str(d))
        self.assertEqual(p["key"], "TOG")
        with self.assertRaises(ValueError):
            s.add_project("1x", "bad", str(d))
        t1 = s.create_ticket(p["id"], "请假审批不通过", "李", type="缺陷", priority="高")
        t2 = s.create_ticket(p["id"], "加导出", "李", type="feature")
        self.assertEqual((t1["key"], t2["key"]), ("TOG-1", "TOG-2"))
        self.assertEqual((t1["type"], t1["priority"]), ("bug", "high"))
        s.update_ticket(t1["id"], "王", status="处理中", assignee="王")
        t = s.ticket("tog-1")
        self.assertEqual(t["status"], "doing")
        kinds = [e["kind"] for e in s.events(t["id"])]
        self.assertEqual(kinds, ["created", "status", "assign"])
        with self.assertRaises(ValueError):
            s.update_ticket(t1["id"], "王", status="不存在的状态")
        st = s.stats(p["id"])
        self.assertEqual(st["by_status"], {"doing": 1, "new": 1})
        self.assertEqual(st["open_by_priority"], {"high": 1, "normal": 1})


class PlatformApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = git_repo(JAVA)
        kb.build(cls.repo)
        from tmh import config as cfgmod
        cfg = cfgmod.load(cls.repo)
        cfg["commands"]["test"] = "%s -c pass" % sys.executable  # builds and tests of a change: instant, always green
        cfgmod.save(cls.repo, cfg)
        cls.data = Path(tempfile.mkdtemp(prefix="tmh-data-"))
        script = cls.data / "fake_agent.py"
        script.write_text(FAKE_AGENT, encoding="utf-8")
        writer = cls.data / "fake_writer.py"
        writer.write_text(FAKE_WRITER, encoding="utf-8")
        (cls.data / "agents.json").write_text(json.dumps({"fake": {"title": "测试智能体", "cmd": [sys.executable, str(script), "{mode}", "{prompt_file}"]},
                                                          "writer": {"cmd": [sys.executable, str(writer), "{mode}", "{prompt_file}", str(HERE.parent)]}}),
                                              encoding="utf-8")
        (cls.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")  # tests drive runs by hand unless they turn it on
        cls.P = Platform(cls.data, "tester")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, method, path, body=None, headers=None):
        h = {"X-TMH": "1", "Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def wait_run(self, rid):
        for _ in range(200):
            _, r = self.call("GET", "/api/runs/%d" % rid)
            if r["status"] not in ("queued", "running"):
                return r
            time.sleep(0.05)
        self.fail("run %d did not finish" % rid)

    def project(self):
        code, ps = self.call("GET", "/api/projects")
        if not any(x["key"] == "OA" for x in ps):
            code, p = self.call("POST", "/api/projects", {"key": "OA", "name": "示例 OA", "root": str(self.repo)})
            self.assertEqual(code, 200, p)
        return "OA"

    def test_inbox_lists_what_waits_for_a_person(self):
        self.project()
        st = self.P.store
        made = {}
        for title, status, pri in [("验收这单", "verify", "high"), ("确认这单", "confirm", "normal"), ("跑挂了", "doing", "urgent"),
                                   ("等审阅", "doing", "normal"), ("还在跑", "analyzing", "high"), ("没人管", "new", "low")]:
            _, t = self.call("POST", "/api/tickets", {"project": "OA", "title": "收件箱 " + title, "priority": pri})
            st.update_ticket(t["id"], "tester", status=status)
            made[title] = t
        p = st.project(made["跑挂了"]["project_id"])
        fail = st.create_run(p["id"], made["跑挂了"]["id"], "fake", "analyze", "tester", "")["id"]
        st.update_run(fail, status="failed")
        rev = st.create_run(p["id"], made["等审阅"]["id"], "fake", "fix", "tester", "")["id"]
        st.update_run(rev, status="done", diff="diff --git a/x b/x\n+1\n")
        busy = st.create_run(p["id"], made["还在跑"]["id"], "fake", "analyze", "tester", "")["id"]
        st.update_run(busy, status="running")
        code, d = self.call("GET", "/api/projects/OA/inbox")
        self.assertEqual(code, 200, d)
        got = {x["key"]: x for x in d["mine"] if x["title"].startswith("收件箱")}
        reasons = {x["title"][4:]: x["reason"] for x in got.values()}
        want = {"验收这单": "verify", "确认这单": "confirm", "跑挂了": "failed", "等审阅": "review"}
        if not (d["auto"] and d["agent"]):  # nothing will start 没人管 by itself here, so it waits for a person too
            want["没人管"] = "stalled"
        self.assertEqual(reasons, want, d["mine"])
        self.assertGreaterEqual(d["running"], 1)
        keys = [x["key"] for x in d["mine"]]
        self.assertLess(keys.index(made["跑挂了"]["key"]), keys.index(made["等审阅"]["key"]))  # urgent first
        self.assertEqual(self.call("GET", "/api/projects/*/inbox")[0], 200)
        # with the automatic line off, a new ticket nobody started is the person's to pick up, and says why
        f = self.P.data_dir / "autoflow.json"
        old = f.read_text(encoding="utf-8") if f.exists() else None
        f.write_text(json.dumps({"on": False}), encoding="utf-8")
        try:
            _, d = self.call("GET", "/api/projects/OA/inbox")
            row = next((x for x in d["mine"] if x["key"] == made["没人管"]["key"]), None)
            if not [r for r in st.runs(ticket_id=made["没人管"]["id"]) if r["mode"] != "ask"]:
                self.assertEqual((row or {}).get("reason"), "stalled", d["mine"])
                self.assertIn("自动处理关着", row["label"])
            self.assertFalse(d["auto"])
        finally:
            f.write_text(old, encoding="utf-8") if old is not None else f.unlink()
        st.update_run(busy, status="done")
        for t in made.values():
            st.update_ticket(t["id"], "tester", status="closed")

    def test_page_and_guards(self):
        with urllib.request.urlopen(self.base + "/") as r:
            html = r.read().decode("utf-8")
        self.assertIn('id="brandName"', html)
        self.assertNotIn("tmh 运维平台", html)  # the internal name stays off the screen
        self.assertIn("<script>", page())
        code, _ = self.call("POST", "/api/projects", {"key": "X"}, headers={"X-TMH": ""})
        self.assertEqual(code, 403)  # writes need the custom header
        req = urllib.request.Request(self.base + "/api/meta", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)  # DNS-rebinding guard
        self.project()
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/p/OA/report/..%2F..%2Fpom.xml")
        # a crash tells the person the step did not finish and gives a reference to quote; the exception text stays out of the message
        from tmh.platform import server as srv
        boom = lambda P, req: (_ for _ in ()).throw(KeyError("secret_column"))  # noqa: E731
        srv.ROUTES.insert(0, ("GET", __import__("re").compile("^/api/boom$"), boom))
        try:
            code, e = self.call("GET", "/api/boom")
        finally:
            srv.ROUTES.pop(0)
        self.assertEqual(code, 500)
        self.assertIn("没有完成", e["error"])
        self.assertIn(e["ref"], e["error"])
        self.assertNotIn("secret_column", e["error"])
        self.assertIn("KeyError", e["detail"])

    def test_lead_reads_response_resolution_first_fix_and_backlog(self):
        key = self.project()
        pid = self.P.project(key)["id"]
        t = self.P.store.create_ticket(pid, "月底报销单提交不了", "客户甲")
        self.call("POST", "/api/tickets/%s/comments" % t["key"], {"body": "已收到，在查"})
        self.call("POST", "/api/tickets/%s/accept" % t["key"], {"result": "pass", "note": "现场确认可以提交"})
        code, d = self.call("GET", "/api/lead?days=30")
        self.assertEqual(code, 200, d)
        core = {c["key"]: c for c in d["core"]}
        self.assertEqual(sorted(core), ["backlog", "ftf", "res", "resp"])
        self.assertIsNotNone(core["resp"]["value"])
        self.assertIsNotNone(core["ftf"]["value"])
        self.assertIn(t["key"], [x["key"] for x in d["done"]])
        self.assertTrue(all("value" in x for x in d["ai"]))
        self.assertTrue(all("rejected" in p and "avg_h" in p for p in d["people"]))

    def test_new_ticket_flows_to_doing_by_itself(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        loc = self.data / "fake_locator.py"
        loc.write_text("import sys\nprint('结论：LeaveService.java:12 提交时没有更新状态【核实】' if sys.argv[1] == 'analyze' else '方案：补上状态更新')\n",
                       encoding="utf-8")
        conf["locator"] = {"cmd": [sys.executable, str(loc), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        (self.data / "autoflow.json").write_text('{"on": true, "agent": "locator", "fix": false}', encoding="utf-8")
        try:
            code, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假申请提交后审批状态不对", "body": "提交请假后状态没变"})
            self.assertEqual(code, 200, t)
            for _ in range(200):
                _, d = self.call("GET", "/api/tickets/" + t["key"])
                if d["ticket"]["status"] == "doing" and any(r["mode"] == "plan" and r["status"] == "done" for r in d["runs"]):
                    break
                time.sleep(0.05)
            self.assertEqual(d["ticket"]["status"], "doing")
            kinds = [e["kind"] for e in d["events"]]
            self.assertIn("intake", kinds)
            self.assertIn("flow", kinds)
            self.assertTrue(d["ticket"]["links"].get("flows"), "intake links the business the ticket touches")
            self.assertEqual(sorted(r["mode"] for r in d["runs"]), ["analyze", "plan"])
            self.assertGreaterEqual(d["evidence"]["flows"], 1)
            # what the machine linked stays a suggestion until a person confirms it
            self.assertFalse(d["ticket"]["links"].get("flows_ok"))
            _, t3 = self.call("POST", "/api/tickets/" + t["key"], {"confirm_flows": "*"})
            self.assertEqual(t3["links"]["flows_ok"], t3["links"]["flows"])
            # with the agent gone the ticket still reaches 处理中, with a note why
            (self.data / "autoflow.json").write_text('{"on": true, "agent": "ghost-x"}', encoding="utf-8")
            conf.pop("locator")
            (self.data / "agents.json").write_text(json.dumps({k: v for k, v in conf.items() if k == "nobody"}), encoding="utf-8")
            t2 = self.P.store.create_ticket(self.P.project(key)["id"], "导出报表很慢", "tester")
            orig = __import__("tmh.platform.agents", fromlist=["available"]).available
            import tmh.platform.agents as ag
            ag.available = lambda d: []
            try:
                self.P.flow.submit(self.P.project(key), t2, wait=True)
            finally:
                ag.available = orig
            self.assertEqual(self.P.store.ticket(t2["id"])["status"], "doing")
        finally:
            conf.pop("locator", None)
            (self.data / "agents.json").write_text(json.dumps(json.loads(json.dumps(conf))), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def test_a_change_is_built_again_without_being_redone(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_fixer.py"
        bot.write_text(FAKE_AGENT.replace('print("结论：问题在请假审批流程【推断】")',
                                          'print("结论：LeaveService.java:12 提交时没有更新状态【核实】")'), encoding="utf-8")
        conf["fixer"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        ok = "%s -c \"import sys; sys.exit(0)\"" % sys.executable
        try:
            # first time round nothing was built (the build was off), so the change waits for a person
            (self.data / "autoflow.json").write_text(json.dumps({"on": True, "agent": "fixer", "check": "none", "commit": False}), encoding="utf-8")
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态没变", "body": "提交请假后审批状态不对"})
            for _ in range(300):
                _, d = self.call("GET", "/api/tickets/" + t["key"])
                if any("留给人审阅" in e["body"] for e in d["events"]):
                    break
                time.sleep(0.05)
            fx = [r for r in d["runs"] if r["mode"] == "fix"][0]
            self.assertEqual(fx["verify"]["check"], "skip")
            self.assertFalse(fx["decision"])
            n_runs = len(d["runs"])
            # the build works now: built again, not redone, and committed as if its own run had passed
            (self.data / "autoflow.json").write_text(json.dumps({"on": True, "agent": "fixer", "check": ok}), encoding="utf-8")
            code, v = self.call("POST", "/api/runs/%d/recheck" % fx["id"], {"wait": True})
            self.assertEqual(code, 200, v)
            self.assertEqual(v["check"], "pass", v)
            self.assertTrue(v["rechecked"])
            _, d = self.call("GET", "/api/tickets/" + t["key"])
            self.assertEqual(len(d["runs"]), n_runs, "no agent ran again")
            fx = [r for r in d["runs"] if r["mode"] == "fix"][0]
            self.assertTrue(fx["decision"].startswith("accepted:"), [e["body"] for e in d["events"]])
            self.assertEqual(d["ticket"]["status"], "verify")
            self.assertTrue(any("重新验证了运行" in e["body"] and "构建通过" in e["body"] for e in d["events"]))
            # an adopted change is built from its commit, in a worktree that is gone afterwards
            code, v = self.call("POST", "/api/runs/%d/recheck" % fx["id"], {"wait": True})
            self.assertEqual(v["check"], "pass", v)
            self.assertFalse((self.data / "worktrees" / ("recheck-%d" % fx["id"])).exists())
            _, s = self.call("GET", "/api/runs/%d/recheck" % fx["id"])
            self.assertFalse(s["running"])
            self.assertEqual(s["verify"]["check"], "pass")
            code, e = self.call("POST", "/api/runs/%d/recheck" % [r for r in d["runs"] if r["mode"] == "plan"][0]["id"], {})
            self.assertEqual(code, 400)
        finally:
            conf.pop("fixer", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def test_a_rebuilt_change_the_diagnosis_judged_unsolved_still_waits_for_a_person(self):
        # a missing endpoint compiles fine: a build that passes later does not overrule what the diagnosis found
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_fixer.py"
        bot.write_text(FAKE_AGENT.replace('print("结论：问题在请假审批流程【推断】")',
                                          'print("结论：LeaveService.java:12 提交时没有更新状态【核实】")'), encoding="utf-8")
        conf["fixer"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        ok = "%s -c \"import sys; sys.exit(0)\"" % sys.executable
        try:
            (self.data / "autoflow.json").write_text(json.dumps({"on": True, "agent": "fixer", "check": "none", "commit": False}), encoding="utf-8")
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "资料查询没有接口", "body": "查用户资料返回 404"})
            for _ in range(300):
                _, d = self.call("GET", "/api/tickets/" + t["key"])
                if any("留给人审阅" in e["body"] for e in d["events"]):
                    break
                time.sleep(0.05)
            fx = [r for r in d["runs"] if r["mode"] == "fix"][0]
            vf = self.data / "runs" / str(fx["id"]) / "verify.json"
            v = json.loads(vf.read_text(encoding="utf-8"))
            v.update({"verdict": "fail", "diagnosis": {"cause": "遗漏方案中的 HTTP Controller；验证环境不可用"}})
            vf.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
            (self.data / "autoflow.json").write_text(json.dumps({"on": True, "agent": "fixer", "check": ok}), encoding="utf-8")
            code, v = self.call("POST", "/api/runs/%d/recheck" % fx["id"], {"wait": True})
            self.assertEqual((code, v["check"], v["verdict"]), (200, "pass", "fail"), v)
            _, d = self.call("GET", "/api/tickets/" + t["key"])
            fx = [r for r in d["runs"] if r["mode"] == "fix"][0]
            self.assertFalse(fx["decision"], "not committed")
            self.assertTrue(any("诊断认为还没解决" in e["body"] and "Controller" in e["body"] for e in d["events"]), [e["body"] for e in d["events"]])
        finally:
            conf.pop("fixer", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def test_ticket_runs_on_its_own_to_a_committed_branch(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_fixer.py"
        bot.write_text(FAKE_AGENT.replace('print("结论：问题在请假审批流程【推断】")',
                                          'print("结论：LeaveService.java:12 提交时没有更新状态【核实】")'), encoding="utf-8")
        conf["fixer"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")

        def wait(k, ok):
            for _ in range(300):
                _, d = self.call("GET", "/api/tickets/" + k)
                if ok(d) and not any(r["status"] in ("queued", "running") for r in d["runs"]):
                    return d
                time.sleep(0.05)
            return d
        try:
            # nobody presses a button: analysis, plan and the change, committed on the ticket's own branch
            (self.data / "autoflow.json").write_text('{"on": true, "agent": "fixer"}', encoding="utf-8")
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态没变", "body": "提交请假后审批状态不对"})
            d = wait(t["key"], lambda d: d["ticket"]["status"] == "verify")
            self.assertEqual(d["ticket"]["status"], "verify", [e["body"] for e in d["events"]])
            self.assertEqual(sorted(r["mode"] for r in d["runs"]), ["analyze", "fix", "plan"])
            fx = [r for r in d["runs"] if r["mode"] == "fix"][0]
            self.assertTrue(fx["decision"].startswith("accepted:tmh/%s-r" % t["key"]), fx["decision"])
            # the commit says who wrote it and where it came from, in trailers git itself can read back
            sha = fx["decision"].rsplit("@", 1)[1]
            tr = subprocess.run(["git", "log", "-1", "--format=%(trailers:only,unfold)", sha], cwd=self.repo, capture_output=True, text=True).stdout
            self.assertIn("Assisted-by: %s" % fx["agent"], tr)
            self.assertIn("Ticket: %s" % t["key"], tr)
            self.assertIn("Webuddy-Run: %d" % fx["id"], tr)
            self.assertNotIn("Reviewed-by", tr)  # committed by the line, nobody reviewed it yet
            adopt = [e for e in d["events"] if e["kind"] == "adopt"]
            self.assertEqual(adopt[0]["author"], "自动流转")
            self.assertNotIn("accept", [e["kind"] for e in d["events"]], "committing a change is not passing acceptance")
            self.assertEqual(subprocess.run(["git", "diff", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout.strip(), "",
                             "the person's working copy stays untouched")
            # a change bigger than the limit waits for a person, and handing it back after a take-over commits it
            (self.data / "autoflow.json").write_text('{"on": true, "agent": "fixer", "max_lines": 0}', encoding="utf-8")
            _, t2 = self.call("POST", "/api/tickets", {"project": key, "title": "请假审批后状态未更新", "body": "审批后状态不对"})
            d = wait(t2["key"], lambda d: any("留给人审阅" in e["body"] for e in d["events"]))
            self.assertEqual(d["ticket"]["status"], "doing")
            self.assertTrue(any("超过自动提交上限" in e["body"] for e in d["events"]), [e["body"] for e in d["events"]])
            self.assertFalse([r for r in d["runs"] if r["mode"] == "fix"][0]["decision"])
            _, t3 = self.call("POST", "/api/tickets/" + t2["key"], {"hold": True})
            self.assertTrue(t3["links"]["hold"])
            (self.data / "autoflow.json").write_text('{"on": true, "agent": "fixer"}', encoding="utf-8")
            _, t3 = self.call("POST", "/api/tickets/" + t2["key"], {"hold": False})
            self.assertNotIn("hold", t3["links"])
            self.assertEqual(t3["status"], "verify")
            # tickets that were there before (no intake ran) show up as waiting and can be handed over in one go
            old = self.P.store.create_ticket(self.P.project(key)["id"], "请假审批提交后状态没回写", "tester", body="提交后状态不对")
            _, lp = self.call("GET", "/api/projects/%s/loop" % key)
            self.assertGreaterEqual(lp["waiting"], 1)
            _, dd = self.call("GET", "/api/tickets/" + old["key"])
            self.assertEqual(dd["auto_next"], "analyze")
            _, q = self.call("POST", "/api/projects/%s/catchup" % key, {})
            self.assertGreaterEqual(q["queued"], 1)
            d = wait(old["key"], lambda d: d["ticket"]["status"] == "verify")
            self.assertEqual(d["ticket"]["status"], "verify", [e["body"] for e in d["events"]])
            self.assertEqual(d["auto_next"], "")
            # taken over before it starts: the analysis finishes and nothing else runs on its own
            (self.data / "autoflow.json").write_text('{"on": true, "agent": "fixer"}', encoding="utf-8")
            t4 = self.P.store.create_ticket(self.P.project(key)["id"], "请假单状态显示错误", "tester", body="提交请假后状态错")
            self.P.flow.take_over(t4, True, "李")
            self.P.flow.submit(self.P.project(key), self.P.store.ticket(t4["id"]), wait=True)
            d = wait(t4["key"], lambda d: any(r["mode"] == "analyze" and r["status"] == "done" for r in d["runs"]))
            time.sleep(0.3)
            _, d = self.call("GET", "/api/tickets/" + t4["key"])
            self.assertEqual([r["mode"] for r in d["runs"]], ["analyze"])
        finally:
            conf.pop("fixer", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def test_timing_counts_the_time_lost_reconnecting(self):
        from tmh.platform import agents
        t = agents.Timing()
        clock = iter([1.0, 1.0, 2.0, 3.0, 5.0, 5.5, 6.0])
        with mock.patch.object(agents.time, "time", lambda: next(clock)):
            t.t0 = t.last = next(clock)
            for line in ["user", "ERROR: Reconnecting... 2/5", "ERROR: Reconnecting... 3/5", "Falling back from WebSockets to HTTPS", "codex", "ok"]:
                t.feed(line)
        d = t.done()
        self.assertEqual((d["reconnects"], d["reconnect_seconds"]), (2, 4.0), d)
        self.assertIn("重连 2 次共 4 秒", agents.timing_text(d))

    def test_a_busy_model_is_waited_out_and_the_session_picked_up(self):
        from tmh.platform import agents
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_busy.py"
        flag = self.data / "busy-once"
        flag.write_text("1", encoding="utf-8")
        bot.write_text(r'''
import pathlib, sys
pf, sid, flag = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
print("session id: " + (sid or "s-busy"))
if flag.exists():
    flag.unlink()
    print("exec")
    print(" succeeded in 5ms:")
    print("ERROR: Selected model is at capacity. Please try a different model.")
    sys.exit(1)
print("结论：%s" % ("续" if sid else "新"))
''', encoding="utf-8")
        conf["busy"] = {"cmd": [sys.executable, str(bot), "{prompt_file}", "{resume}", str(flag)]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        try:
            with mock.patch.object(agents, "BUSY_WAITS", (0, 0)):
                _, t = self.call("POST", "/api/tickets", {"project": key, "title": "导出报表超时", "body": "导出时一直转圈"})
                _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "busy", "mode": "analyze"})
                r = self.wait_run(r["id"])
            self.assertEqual(r["status"], "done", r.get("output"))
            self.assertIn("模型服务繁忙", r["output"])
            self.assertIn("续", r["result"], "the retry continues the session that was cut off")
            again = (self.data / "runs" / str(r["id"]) / "prompt.md").read_text(encoding="utf-8")
            self.assertEqual(again, agents.BUSY_AGAIN)
        finally:
            conf.pop("busy", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")

    def test_a_ticket_s_steps_continue_one_agent_session(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_session.py"
        bot.write_text(r'''
import pathlib, sys, uuid
mode, pf, sid = sys.argv[1], sys.argv[2], sys.argv[3]
p = open(pf, encoding="utf-8").read()
if sid == "gone":  # a session the agent no longer has
    sys.exit(1)
print("session id: " + (sid or "s-" + mode + "-" + uuid.uuid4().hex[:6]))
print("hook: PreToolUse")
print("hook: PreToolUse Completed")
print("exec")
print("/bin/zsh -lc ls")
print(" succeeded in 120ms:")
if mode == "fix":
    f = pathlib.Path("NOTE.md")
    f.write_text("fixed\\n", encoding="utf-8")
print("tokens used")
print("1,234")
print("结论：%s %s %d" % (mode, "续" if sid else "新", len(p)))
''', encoding="utf-8")
        conf["sess"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}", "{resume}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        try:
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态没变", "body": "提交后状态不对"})
            res = {}
            for mode in ("analyze", "plan", "fix"):
                _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "sess", "mode": mode})
                r = self.wait_run(r["id"])
                self.assertEqual(r["status"], "done", r.get("output"))
                res[mode] = r
            a_sid = (self.data / "runs" / str(res["analyze"]["id"]) / "session.txt").read_text(encoding="utf-8")
            self.assertIn("analyze 新", res["analyze"]["result"])
            self.assertIn("plan 续", res["plan"]["result"], "the plan continues the analysis session")
            self.assertEqual((self.data / "runs" / str(res["plan"]["id"]) / "session.txt").read_text(encoding="utf-8"), a_sid)
            plan_prompt = (self.data / "runs" / str(res["plan"]["id"]) / "prompt.md").read_text(encoding="utf-8")
            self.assertTrue(plan_prompt.startswith("# 接着做下一步"), plan_prompt[:80])
            self.assertNotIn("## 描述", plan_prompt, "a continued step is not given the ticket all over again")
            self.assertIn("fix 续", res["fix"]["output"], "the change continues the session that planned it")
            self.assertIn("NOTE.md", res["fix"]["diff"])
            tm = json.loads((self.data / "runs" / str(res["plan"]["id"]) / "timing.json").read_text(encoding="utf-8"))
            self.assertEqual((tm["commands"], tm["command_seconds"], tm["tokens"], tm["resumed"]), (1, 0.1, 1234, True), tm)
            self.assertIn("用时", res["plan"]["output"])
            # a session the agent lost: the step starts over with the whole prompt
            (self.data / "runs" / str(res["plan"]["id"]) / "session.txt").write_text("gone", encoding="utf-8")
            _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "sess", "mode": "fix"})
            r = self.wait_run(r["id"])
            self.assertIn("改为新开一个会话", r["output"])
            self.assertIn("fix 新", r["output"])
        finally:
            conf.pop("sess", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")

    def test_agent_runs_wait_for_a_free_slot_ticket_steps_first(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_slow.py"
        bot.write_text("import time\ntime.sleep(0.4)\nprint('结论：好了')\n", encoding="utf-8")
        conf["slow"] = {"cmd": [sys.executable, str(bot)]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        (self.data / "autoflow.json").write_text('{"on": false, "max_agents": 1}', encoding="utf-8")
        try:
            p = self.P.project(key)
            first = self.P.runner.start(p, None, "slow", "analyze", "t")
            time.sleep(0.1)
            page = self.P.runner.start(p, None, "slow", "kb", "t", "dom:x")
            step = self.P.runner.start(p, None, "slow", "analyze", "t")
            time.sleep(0.15)
            self.assertEqual([self.P.store.run(r["id"])["status"] for r in (first, page, step)], ["running", "queued", "queued"])
            for r in (first, page, step):
                self.wait_run(r["id"])
            a, b = self.P.store.run(step["id"]), self.P.store.run(page["id"])
            self.assertLessEqual(a["started"], b["started"], "a ticket step goes before a knowledge page that waited longer")
            self.assertGreaterEqual(b["started"], a["ended"], "only one agent at a time")
        finally:
            conf.pop("slow", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def test_ticket_pinned_to_an_old_commit_runs_on_that_code(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_pinned.py"
        bot.write_text(FAKE_AGENT.replace('print("结论：问题在请假审批流程【推断】")',
                                          'print("结论：LeaveService.java:12【核实】 " + ("新代码" if pathlib.Path("NEWER.md").exists() else "旧代码"))'),
                       encoding="utf-8")
        conf["pinbot"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(a), cwd=self.repo,  # noqa: E731
                                      check=True, capture_output=True, text=True).stdout.strip()
        old = g("rev-parse", "HEAD")
        (self.repo / "NEWER.md").write_text("added after the ticket was reported\n", encoding="utf-8")
        g("add", "NEWER.md")
        g("commit", "-qm", "newer")
        try:
            st, err = self.call("POST", "/api/tickets", {"project": key, "title": "x", "code_at": "deadbeef"})
            self.assertEqual(st, 400, err)
            (self.data / "autoflow.json").write_text('{"on": true, "agent": "pinbot"}', encoding="utf-8")
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态没变", "body": "提交后状态不对", "code_at": old})
            self.assertEqual(t["links"]["code_at"], old)
            for _ in range(300):
                _, d = self.call("GET", "/api/tickets/" + t["key"])
                if d["ticket"]["status"] == "verify" and not any(r["status"] in ("queued", "running") for r in d["runs"]):
                    break
                time.sleep(0.05)
            self.assertEqual(d["ticket"]["status"], "verify", [e["body"] for e in d["events"]])
            for r in d["runs"]:
                _, full = self.call("GET", "/api/runs/%d" % r["id"])
                self.assertIn("旧代码", full["result"], (r["mode"], full["result"]))
            fx = [r for r in d["runs"] if r["mode"] == "fix"][0]
            branch = fx["decision"].split(":", 1)[1].split("@")[0]
            self.assertEqual(g("merge-base", branch, old), old)
            self.assertNotIn("NEWER.md", g("ls-tree", "-r", "--name-only", branch))
            self.assertFalse([w for w in (self.data / "worktrees").glob("view-r*")], "the read-only views are cleaned up")
        finally:
            conf.pop("pinbot", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")
            g("rm", "-q", "NEWER.md")
            g("commit", "-qm", "drop newer")

    def test_change_is_split_by_file_built_and_diagnosed(self):
        key = self.project()
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot, check = self.data / "fake_team.py", self.data / "check.py"
        bot.write_text(FAKE_TEAM, encoding="utf-8")
        check.write_text("import pathlib, sys\nsys.exit(1 if 'BROKEN' in pathlib.Path(%r).read_text() else 0)\n" % SVC, encoding="utf-8")
        conf["team"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")

        def run(k, mode):
            code, r = self.call("POST", "/api/tickets/%s/runs" % k, {"agent": "team", "mode": mode})
            self.assertEqual(code, 200, r)
            return self.wait_run(r["id"])
        try:
            (self.data / "autoflow.json").write_text(json.dumps({"on": False, "split_from": 1, "check": "%s %s" % (sys.executable, check)}), encoding="utf-8")
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态不更新", "body": "提交后状态没变"})
            run(t["key"], "plan")
            r = run(t["key"], "fix")
            self.assertEqual(r["status"], "done", r["result"])
            v = json.loads((self.data / "runs" / str(r["id"]) / "verify.json").read_text(encoding="utf-8"))
            # round 1 breaks the build, the diagnosis names the file, round 2 repairs it
            self.assertEqual((v["check"], v["verdict"], v["rounds"], v["split"]), ("pass", "pass", 2, True), v)
            self.assertTrue(r["result"].startswith("验证：构建测试通过"), r["result"])
            self.assertIn("// repaired", r["diff"])
            self.assertNotIn("BROKEN", r["diff"])
            # the service's agent asked the controller for something: the controller came in and got the message
            self.assertIn(CTL, v["files"])
            self.assertIn("// got-msg", r["diff"])
            # an agent's edit outside its own file is put back
            self.assertNotIn("UserController", r["diff"])
            self.assertIn("已撤回", r["output"])
            self.assertEqual(self.P.flow.fix_gate({"root": str(self.repo)}, r["diff"], {"max_lines": 400}, r["id"]), "")
            # no more rounds allowed: the broken build stays, and the automatic flow will not commit it
            (self.data / "autoflow.json").write_text(json.dumps({"on": False, "split_from": 1, "rounds": 0, "check": "%s %s" % (sys.executable, check)}), encoding="utf-8")
            _, t2 = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态仍不对", "body": "提交后状态没变"})
            run(t2["key"], "plan")
            r2 = run(t2["key"], "fix")
            self.assertTrue(r2["result"].startswith("验证：构建测试没通过"), r2["result"])
            self.assertIn("构建测试仍没通过", self.P.flow.fix_gate({"root": str(self.repo)}, r2["diff"], {"max_lines": 400}, r2["id"]))
        finally:
            conf.pop("team", None)
            (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
            (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def team(self):
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        bot = self.data / "fake_team.py"
        bot.write_text(FAKE_TEAM, encoding="utf-8")
        conf["team"] = {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")

    def untrain(self):
        conf = json.loads((self.data / "agents.json").read_text(encoding="utf-8"))
        conf.pop("team", None)
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")

    def fixed(self, title):
        """A ticket with an automatic change committed on its branch, waiting for acceptance."""
        _, t = self.call("POST", "/api/tickets", {"project": self.project(), "title": title, "body": "提交后状态没变"})
        for mode in ("plan", "fix"):
            code, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "team", "mode": mode})
            r = self.wait_run(r["id"])
            self.assertEqual(r["status"], "done", r["result"])
        v = json.loads((self.data / "runs" / str(r["id"]) / "verify.json").read_text(encoding="utf-8"))
        self.assertFalse(v["split"], "a one-file plan is changed by one agent, not split by file")
        code, d = self.call("POST", "/api/runs/%d/decide" % r["id"], {"decision": "accept"})
        self.assertEqual(code, 200, d)
        return t, d["decision"].split(":", 1)[1].split("@")[0]

    def test_a_change_beyond_the_plan_is_flagged_and_left_to_a_person(self):
        self.team()
        try:
            _, t = self.call("POST", "/api/tickets", {"project": self.project(), "title": "请假提交状态不对", "body": "也看看用户页"})
            for mode in ("plan", "fix"):
                _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "team", "mode": mode})
                r = self.wait_run(r["id"])
            v = json.loads((self.data / "runs" / str(r["id"]) / "verify.json").read_text(encoding="utf-8"))
            self.assertEqual(v["beyond_plan"], ["src/main/java/com/acme/oa/controller/UserController.java"])
            self.assertIn("超出方案", r["result"])
            self.assertIn("方案没列", self.P.flow.fix_gate({"root": str(self.repo)}, r["diff"], {"max_lines": 400}, r["id"]))
        finally:
            self.untrain()

    def test_acceptance_teaches_and_grows_the_eval_set(self):
        from tmh.platform import learn
        from tmh.platform.agents import build_prompt
        self.team()
        try:
            # passed, but a person had to add a commit on top of the automatic one: a lesson, and an eval case
            t, branch = self.fixed("请假审批提交后状态不刷新")
            wt = self.data / "human-wt"
            subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q", str(wt), branch], check=True)
            readme = wt / "src" / "main" / "resources" / "leave-note.txt"
            readme.parent.mkdir(parents=True, exist_ok=True)
            readme.write_text("状态刷新要在提交事务之后\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(wt), "-c", "user.name=li", "-c", "user.email=li@x", "commit", "-q", "-m", "补充事务说明"], check=True)
            subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(wt)], check=True)
            code, _ = self.call("POST", "/api/tickets/%s/accept" % t["key"], {"result": "pass", "note": "合并后验证通过"})
            self.assertEqual(code, 200)
            ls = learn.lessons(self.data, "OA")
            self.assertEqual((ls[0]["kind"], ls[0]["ticket"]), ("human-fix", t["key"]), ls[0])
            self.assertIn("补充事务说明", ls[0]["note"])
            self.assertIn("src/main/resources/leave-note.txt", ls[0]["files"])
            case = [c for c in learn.cases(self.data, "OA") if c["ticket"] == t["key"]][0]
            self.assertIn(SVC, case["gold"])
            self.assertIn("src/main/resources/leave-note.txt", case["gold"])  # the human fix counts as part of the right answer
            # a related ticket's prompt carries the lesson; the ticket itself does not get its own lesson twice
            _, t2 = self.call("POST", "/api/tickets", {"project": "OA", "title": "请假审批提交后状态还是不刷新", "body": "LeaveService 提交"})
            p = self.P.store.project(t2["project_id"])
            self.assertIn("以往的经验", build_prompt(self.P.store, p, self.P.store.ticket(t2["id"]), "plan"))
            self.assertIn("补充事务说明", build_prompt(self.P.store, p, self.P.store.ticket(t2["id"]), "fix"))
            self.assertNotIn("以往的经验", build_prompt(self.P.store, p, self.P.store.ticket(t["id"]), "plan"))
            lid = ls[0]["id"]
            self.assertEqual(learn.lesson(self.data, lid)["stats"]["used"], 1)  # two prompts before a verdict count once
            # people look after the cards: a reason is needed to take one out, and then it stays out of prompts
            code, r = self.call("POST", "/api/projects/OA/lessons/%s" % lid, {"action": "retire"})
            self.assertEqual(code, 400, r)
            code, r = self.call("POST", "/api/projects/OA/lessons/%s" % lid, {"action": "retire", "why": "事务问题已统一修掉"})
            self.assertEqual((code, r["status"]), (200, "retired"), r)
            self.assertNotIn("以往的经验", build_prompt(self.P.store, p, self.P.store.ticket(t2["id"]), "plan"))
            code, r = self.call("POST", "/api/projects/OA/lessons/%s" % lid, {"action": "restore", "fields": {"cause": "刷新在事务提交前执行"}})
            self.assertEqual((code, r["status"], r["cause"]), (200, "active", "刷新在事务提交前执行"), r)
            self.assertIn("根因：刷新在事务提交前执行", build_prompt(self.P.store, p, self.P.store.ticket(t2["id"]), "plan"))
            self.assertEqual(self.call("POST", "/api/projects/OA/lessons/L999", {"action": "confirm"})[0], 404)
            _, d = self.call("GET", "/api/projects/OA/learn")
            self.assertEqual(d["lesson_summary"]["active"], len([x for x in d["lessons"] if x["status"] == "active"]))

            # failed acceptance of an automatic change: a lesson, and the change is redone on top of the rejected branch
            t3, branch3 = self.fixed("请假提交后列表状态不对")
            (self.data / "autoflow.json").write_text(json.dumps({"on": True, "agent": "team", "refix": 1}), encoding="utf-8")
            code, _ = self.call("POST", "/api/tickets/%s/accept" % t3["key"], {"result": "fail", "note": "列表页还是显示待提交"})
            self.assertEqual(code, 200)
            self.assertEqual(learn.lessons(self.data, "OA")[0]["kind"], "reject")
            for _ in range(400):
                cur = self.P.store.ticket(t3["id"])
                if cur["status"] == "verify":
                    break
                time.sleep(0.05)
            self.assertEqual(cur["status"], "verify")  # redone, checked and committed again by the automatic flow
            redo = self.P.store.run(self.P.store.runs(ticket_id=t3["id"])[0]["id"])
            self.assertIn("列表页还是显示待提交", redo["prompt"])
            self.assertIn("接着被退回的分支 " + branch3, redo["output"])
            # the second rejection is past the limit: a person takes over
            code, _ = self.call("POST", "/api/tickets/%s/accept" % t3["key"], {"result": "fail", "note": "还是不对"})
            self.assertIn("不再自动重改", self.P.store.events(t3["id"])[-1]["body"])
            # passing later: the case starts before the first automatic change, not from the rejected one
            self.P.store.update_ticket(t3["id"], "tester", status="verify")
            self.call("POST", "/api/tickets/%s/accept" % t3["key"], {"result": "pass"})
            c3 = [c for c in learn.cases(self.data, "OA") if c["ticket"] == t3["key"]][0]
            first = [e["data"]["commit"] for e in self.P.store.events(t3["id"]) if e["kind"] == "adopt"][0]
            self.assertEqual(c3["base"], learn._resolve(self.repo, first + "^"))
            # signed over failed gates: no draft of "what worked" (a person's call is not a pattern to copy); cards carry their package
            ls = learn.lessons(self.data, "OA")
            self.assertNotIn("pass", [l["kind"] for l in ls])
            self.assertEqual(ls[0]["provenance"]["status"], "rejected")
            self.assertEqual(len(ls[0]["provenance"]["package_hash"]), 64)
        finally:
            self.untrain()

    def test_eval_set_replays_and_scores(self):
        from tmh.platform import learn
        self.team()
        try:
            key = self.project()
            head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            code, c = self.call("POST", "/api/projects/OA/evals/cases", {"title": "请假提交后状态不更新", "gold": SVC + ", " + CTL, "base": head})
            self.assertEqual(code, 200, c)
            code, bad = self.call("POST", "/api/projects/OA/evals/cases", {"title": "没写文件"})
            self.assertEqual(code, 400)
            r = learn.run_evals(self.P.flow, self.P.store.project(key), "team", None, "tester", [c["id"]], wait=True)
            b = learn.batches(self.data, "OA")[0]
            self.assertEqual(b["batch"], r["batch"])
            row = b["rows"][0]
            self.assertEqual((row["recall"], row["precision"], row["missed"]), (0.5, 1.0, [CTL]), row)
            run = self.P.store.run(row["run"])
            self.assertIn("evals/wt/OA-" + c["id"], run["prompt"])  # the agent was pointed at the code as it was
            self.assertFalse((self.data / "evals" / "wt" / ("OA-" + c["id"])).exists())
            code, d = self.call("GET", "/api/projects/OA/learn")
            self.assertEqual(d["batches"][0]["recall"], 0.5)
            self.call("POST", "/api/projects/OA/evals/cases", {"remove": c["id"]})
            self.assertFalse([x for x in learn.cases(self.data, "OA") if x["id"] == c["id"]])
        finally:
            self.untrain()

    def test_history_tickets_become_cases_by_their_fix_commits(self):
        from tmh.platform import learn
        repo = git_repo(JAVA)
        if not any(x["key"] == "HIS" for x in self.call("GET", "/api/projects")[1]):
            self.assertEqual(self.call("POST", "/api/projects", {"key": "HIS", "name": "历史", "root": str(repo)})[0], 200)
        p = self.P.store.project("HIS")

        def commit(msg, edits):
            for path, text in edits.items():
                fp = repo / path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(text, encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg], cwd=repo, check=True)
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        svc = (repo / SVC).read_text(encoding="utf-8")
        commit("fix TOG-12: 审批后状态没变", {SVC: svc + "\n// fixed\n", "package-lock.json": "{}", "target/x.class": "x"})
        commit("TOG-12 补控制层", {CTL: (repo / CTL).read_text(encoding="utf-8") + "\n// also\n"})
        commit("修复 bug#7 导出", {"sql/patch.sql": "select 1;"})
        commit("整理 TOG-120 无关", {"README.md": "x"})
        closed = {"system": "jira", "key": "TOG-12", "status": "Done", "resolved": "2026-05-02T10:00:00"}
        t1 = self.P.store.create_ticket(p["id"], "审批通过后请假单状态没变", "imp", body="当时的描述", external=closed)
        self.P.store.event(t1["id"], "dev", "comment", "后来的评论：改 LeaveService 就行", {"external": True})
        self.P.store.create_ticket(p["id"], "导出报错", "imp", external={"system": "zentao", "key": "bug-7", "status": "closed", "resolved": "2026-05-03"})
        self.P.store.create_ticket(p["id"], "没人提交过", "imp", external={"system": "jira", "key": "TOG-99", "resolved": "2026-05-04"})
        self.P.store.create_ticket(p["id"], "还开着", "imp", external={"system": "jira", "key": "TOG-120", "status": "Open"})
        code, r = self.call("POST", "/api/projects/HIS/evals/history", {})
        self.assertEqual(code, 200, r)
        self.assertEqual((r["tickets"], r["unmatched"], len(r["matched"]), len(r["flagged"])), (3, 1, 1, 1), r)
        m = r["matched"][0]
        self.assertEqual((m["external"], m["base"], sorted(m["gold"])), ("TOG-12", before, sorted([SVC, CTL])))  # lock and build output dropped
        self.assertEqual(r["flagged"][0]["why"], "只改配置或 SQL")
        self.assertEqual(self.call("POST", "/api/projects/HIS/evals/history", {"since": "2026-05-03"})[1]["tickets"], 2)
        code, r = self.call("POST", "/api/projects/HIS/evals/history", {"apply": True})
        self.assertEqual(len(r["added"]), 1)
        c = learn.cases(self.data, "HIS")[0]
        self.assertEqual((c["source"], c["ticket"], c["body"]), ("history", t1["key"], "当时的描述"))  # no later comments leak in
        self.assertEqual(self.call("POST", "/api/projects/HIS/evals/history", {"apply": True})[1]["existing"], 1)

    def test_github_issues_named_by_commits_and_merged_prs_are_imported_for_replay(self):
        from http.server import BaseHTTPRequestHandler
        from tmh import config as cfgmod
        from tmh.platform import learn
        repo = git_repo(JAVA)
        self.assertEqual(self.call("POST", "/api/projects", {"key": "GH", "name": "GitHub 历史", "root": str(repo)})[0], 200)
        p = self.P.store.project("GH")
        run = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(a), cwd=repo, check=True,  # noqa: E731
                                        capture_output=True, text=True).stdout.strip()

        def edit(path, msg):
            (repo / path).write_text((repo / path).read_text(encoding="utf-8") + "\n// %s\n" % msg, encoding="utf-8")
            run("commit", "-qam", msg)
        main = run("rev-parse", "--abbrev-ref", "HEAD")
        b12 = run("rev-parse", "HEAD")
        edit(SVC, "fix: 审批后状态没变 (close #12)")
        run("checkout", "-qb", "fix/ctl")
        edit(CTL, "补控制层校验")
        run("checkout", "-q", main)
        b20 = run("rev-parse", "HEAD")
        run("merge", "--no-ff", "-qm", "Merge pull request #20 from x/fix-ctl", "fix/ctl")
        edit("pom.xml", "docs (#30)")
        edit("pom.xml", "wip #40")
        GH = {12: {"number": 12, "title": "审批通过后状态没变", "body": "当时的描述", "state": "closed", "closed_at": "2026-05-02T10:00:00Z",
                   "labels": [{"name": "bug"}], "comments": 0},
              20: {"number": 20, "title": "控制层校验", "body": "Fixes #21", "pull_request": {"merged_at": "2026-05-03T00:00:00Z"}},
              21: {"number": 21, "title": "请假接口不校验", "body": "原话", "state": "closed", "closed_at": "2026-05-03T00:00:00Z", "comments": 0},
              30: {"number": 30, "title": "docs", "body": "Closes #12", "pull_request": {"merged_at": None}},
              40: {"number": 40, "title": "还开着", "state": "open", "comments": 0}}
        calls = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                calls.append(self.path)
                n = int(self.path.rstrip("/").rsplit("/", 1)[-1]) if self.path.startswith("/repos/o/r/issues/") else 0
                data = json.dumps(GH.get(n, {"message": "Not Found"})).encode()
                self.send_response(200 if n in GH else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        cfg = cfgmod.load(repo)
        cfg.setdefault("integrations", {}).setdefault("tools", {})["gh"] = {"type": "github", "url": "http://127.0.0.1:%d" % srv.server_address[1], "repo": "o/r"}
        cfgmod.save(repo, cfg)
        self.assertEqual(learn.ref_log(repo)[0], "#12")  # after a closing word: asked first
        self.assertEqual(learn.refs("解决【issues/9840】字典 https://github.com/a/b/issues/9880"), {"#9840", "#9880"})
        code, r = self.call("POST", "/api/projects/GH/evals/history/import", {})
        self.assertEqual(code, 200, r)
        self.assertEqual((r["refs"], r["checked"], len(r["imported"]), r["open"], r["left"]), (4, 4, 2, 1, 0), r)
        ts = {t["external"]["key"]: t for t in self.P.store.tickets(project_id=p["id"]) if t.get("external")}
        self.assertEqual(sorted(ts), ["#12", "#21"])
        self.assertEqual((ts["#21"]["external"]["prs"], ts["#21"]["body"]), (["#20"], "原话"))
        self.assertEqual(self.call("POST", "/api/projects/GH/evals/history/import", {})[1]["refs"], 0)  # PR #30 and open #40 are remembered
        r = self.call("POST", "/api/projects/GH/evals/history", {})[1]
        got = {m["external"]: (m["base"], m["gold"]) for m in r["matched"]}
        self.assertEqual(got, {"#12": (b12, [SVC]), "#21": (b20, [CTL])})  # the merge stands for the whole pull request

    def test_alerts_open_deduplicated_tickets_pointing_at_code(self):
        import os
        key = self.project()
        stack = ("java.lang.NullPointerException: null\n\tat org.springframework.web.Servlet.service(Servlet.java:99)\n"
                 "\tat com.acme.oa.service.LeaveService.submit(LeaveService.java:12)\n")
        am = {"status": "firing", "alerts": [{"status": "firing", "labels": {"alertname": "LeaveSubmitError", "severity": "critical", "service": "oa"},
                                              "annotations": {"summary": "请假提交报错 37 次", "description": stack}, "fingerprint": "abc123"}]}
        code, _ = self.call("POST", "/hook/alert/OA", am)
        self.assertEqual(code, 404)  # not configured
        (self.data / "alerts.json").write_text(json.dumps({"OA": {"key_env": "TMH_TEST_ALERT", "per_hour": 2}}), encoding="utf-8")
        os.environ["TMH_TEST_ALERT"] = "s3cret"
        try:
            code, _ = self.call("POST", "/hook/alert/OA", am, headers={"Authorization": "Bearer nope"})
            self.assertEqual(code, 401)
            auth = {"Authorization": "Bearer s3cret"}
            code, r = self.call("POST", "/hook/alert/OA", am, headers=auth)
            self.assertEqual(code, 200, r)
            t = self.P.store.ticket(r["opened"][0])
            self.assertEqual((t["priority"], t["type"], t["reporter"]), ("urgent", "bug", "告警"))
            self.assertIn("## 堆栈里的项目代码", t["body"])
            self.assertIn(SVC + ":12", t["body"])
            self.assertNotIn("Servlet.java", t["body"].split("## 堆栈里的项目代码")[1])  # framework frames are not the project's code
            code, r = self.call("POST", "/hook/alert/OA", am, headers=auth)
            self.assertEqual(r["updated"], [t["key"]])
            self.assertEqual(self.P.store.ticket(t["id"])["links"]["alert"]["count"], 2)
            am["alerts"][0]["status"] = "resolved"
            code, r = self.call("POST", "/hook/alert/OA", am, headers=auth)
            self.assertEqual(r["resolved"], [t["key"]])
            # a pasted Python log with no fingerprint; then the hourly cap holds back the third new alert
            code, r = self.call("POST", "/api/projects/OA/alerts", {"text": 'Traceback (most recent call last):\n  File "/srv/app/x.py", line 3, in run\nValueError: 坏了'})
            self.assertEqual(len(r["opened"]), 1, r)
            code, r = self.call("POST", "/hook/alert/OA", {"title": "磁盘满了", "severity": "warning"}, headers=auth)
            self.assertEqual((r["opened"], r["skipped"]), ([], 1), r)
            code, d = self.call("GET", "/api/projects/OA/learn")
            self.assertTrue(d["alerts"]["ready"])
            self.assertIn(t["key"], [x["key"] for x in d["alerts"]["tickets"]])
        finally:
            os.environ.pop("TMH_TEST_ALERT", None)
            (self.data / "alerts.json").unlink()

    def test_reform_plan_splits_by_domain_and_releases_in_waves(self):
        key = self.project()
        code, d = self.call("GET", "/api/projects/OA/reforms")
        self.assertEqual(code, 200, d)
        self.assertTrue(d["built"] and d["domains"])
        self.assertIn("upgrade", d["kinds"])
        code, pv = self.call("POST", "/api/projects/OA/reforms", {"preview": True})
        self.assertEqual([i["order"] for i in pv["items"]], list(range(1, len(pv["items"]) + 1)))
        self.assertEqual(pv["items"], sorted(pv["items"], key=lambda i: (i["score"], i["title"])))  # least entangled first
        code, bad = self.call("POST", "/api/projects/OA/reforms", {"title": "x"})
        self.assertEqual(code, 400)
        code, p = self.call("POST", "/api/projects/OA/reforms", {"kind": "upgrade", "title": "Spring 升级", "goal": "Spring 4 升到 5",
                                                                 "keep": "对外接口不变", "wave": 1})
        self.assertEqual(code, 200, p)
        self.assertEqual(p["counts"]["released"], 0)  # nothing opens until someone releases the first wave
        code, r = self.call("POST", "/api/projects/OA/reforms/%s" % p["id"], {"action": "release"})
        self.assertEqual(code, 200, r)
        self.assertEqual(len(r["opened"]), 1)
        t = self.P.store.ticket(r["opened"][0])
        self.assertEqual((t["type"], t["links"]["reform"]["plan"]), ("change", p["id"]))
        self.assertIn("对外接口不变", t["body"])
        self.assertIn(r["items"][0]["title"], t["title"])
        self.assertEqual(r["items"][0]["status"], t["status"])
        code, deps = self.call("GET", "/api/projects/OA/reforms/deps")
        self.assertTrue(any(x["system"] == "Maven" for x in deps["deps"]), deps)
        self.call("POST", "/api/projects/OA/reforms/%s" % p["id"], {"action": "remove"})
        code, d = self.call("GET", "/api/projects/OA/reforms")
        self.assertFalse([x for x in d["plans"] if x["id"] == p["id"]])
        self.assertTrue(self.P.store.ticket(t["id"]))  # its tickets stay

    def test_reform_plan_advances_on_acceptance_like_a_fix_is_redone_on_rejection(self):
        self.project()
        self.untrain()  # pieces wait for people; only the plan-level loop is under test
        u = "/api/projects/OA/reforms"
        code, p = self.call("POST", u, {"kind": "restructure", "title": "分层整理", "goal": "理清分层", "wave": 1})
        self.assertEqual(code, 200, p)
        self.assertTrue(p["auto"])
        if len(p["items"]) < 3:
            self.skipTest("the sample project needs three business domains")
        code, r = self.call("POST", u + "/" + p["id"], {"action": "release"})
        k1 = r["opened"][0]
        code, a = self.call("POST", "/api/tickets/%s/accept" % k1, {"result": "pass", "note": "审批页的按钮顺序别动"})
        self.assertEqual(code, 200, a)
        code, d = self.call("GET", u)
        v = next(x for x in d["plans"] if x["id"] == p["id"])
        self.assertEqual(v["counts"]["released"], 2, "a passed wave releases the next one by itself")
        k2 = v["items"][1]["ticket"]
        self.assertIn("审批页的按钮顺序别动", self.P.store.ticket(k2)["body"], "what acceptance said carries to later pieces")
        self.call("POST", "/api/tickets/%s/accept" % k2, {"result": "fail", "note": "导出的报表少了一列"})
        code, d = self.call("GET", u)
        v = next(x for x in d["plans"] if x["id"] == p["id"])
        self.assertIn("导出的报表少了一列", v.get("paused", ""), "a piece nobody will redo automatically pauses the plan")
        self.call("POST", "/api/tickets/%s/accept" % k2, {"result": "pass"})
        code, d = self.call("GET", u)
        self.assertEqual(next(x for x in d["plans"] if x["id"] == p["id"])["counts"]["released"], 2, "paused: no new wave")
        code, v = self.call("POST", u + "/" + p["id"], {"action": "resume"})
        self.assertNotIn("paused", v)
        code, v = self.call("POST", u + "/" + p["id"], {"action": "release"})
        self.assertIn("导出的报表少了一列", self.P.store.ticket(v["opened"][0])["body"])
        code, v = self.call("POST", u + "/" + p["id"], {"action": "auto", "on": False})
        self.assertFalse(v["auto"])
        self.assertTrue(any("关闭" in x["text"] for x in v["log"]))
        # two services: reform pieces have their own list and stay off the 运维 board and its numbers
        code, rt = self.call("GET", "/api/tickets?svc=reform&project=OA")
        self.assertIn(k1, [t["key"] for t in rt])
        code, ot = self.call("GET", "/api/tickets?svc=ops&project=OA")
        self.assertFalse({k1, k2} & {t["key"] for t in ot})
        code, allt = self.call("GET", "/api/tickets?project=OA")
        code, loop = self.call("GET", "/api/projects/OA/loop")
        self.assertEqual(loop["open"] + loop["closed"], len(ot))
        self.assertIn("kb_built", loop)  # the first-run card on an empty board ticks this step off
        self.assertGreater(len(allt), len(ot))

    def test_reform_lead_goes_first_and_later_pieces_start_from_its_commit(self):
        self.project()
        self.untrain()
        u = "/api/projects/OA/reforms"
        code, bad = self.call("POST", u, {"kind": "rewrite", "title": "Java 重写", "goal": "用 Java 重写"})
        self.assertEqual(code, 400, "a rewrite needs a target folder")
        code, p = self.call("POST", u, {"kind": "rewrite", "title": "Java 重写", "goal": "用 Spring Boot 重写全部接口", "target": "java/", "wave": 5,
                                        "lead": {"title": "工程骨架", "body": "建 Maven 工程、配置、实体和登录鉴权"}})
        self.assertEqual(code, 200, p)
        self.assertEqual((p["target"], p["items"][0]["order"], p["items"][0]["lead"]), ("java", 0, True))
        code, r = self.call("POST", u + "/" + p["id"], {"action": "release"})
        self.assertEqual(len(r["opened"]), 1, "only the lead goes out first")
        lead = self.P.store.ticket(r["opened"][0])
        self.assertEqual(lead["links"]["reform"]["order"], 0)
        self.assertIn("先导", lead["title"])
        self.assertIn("java/", lead["body"])
        code, e = self.call("POST", u + "/" + p["id"], {"action": "release"})
        self.assertEqual(code, 400, "the rest waits for the lead")
        code, rt = self.call("GET", "/api/tickets?svc=reform&project=OA")
        self.assertIn(lead["key"], [t["key"] for t in rt], "the lead is a reform ticket from the start")
        # the lead's automatic change, committed on its own branch
        root = self.repo
        br = "tmh/%s-lead" % lead["key"]
        subprocess.run(["git", "branch", br, "HEAD"], cwd=root, check=True)
        wt = Path(tempfile.mkdtemp()) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", str(wt), br], cwd=root, check=True)
        (wt / "java").mkdir()
        (wt / "java" / "pom.xml").write_text("<project/>", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "skeleton"], cwd=wt, check=True)
        tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True).stdout.strip()
        self.P.store.event(lead["id"], "tmh", "adopt", "采纳", {"commit": tip, "branch": br, "run": None})
        code, a = self.call("POST", "/api/tickets/%s/accept" % lead["key"], {"result": "pass"})
        self.assertEqual(code, 200, a)
        code, d = self.call("GET", u)
        v = next(x for x in d["plans"] if x["id"] == p["id"])
        self.assertEqual(v["base"], tip)
        self.assertGreater(v["counts"]["released"], 1, "a passed lead releases the domains by itself")
        nxt = [self.P.store.ticket(i["ticket"]) for i in v["items"] if i.get("ticket") and not i.get("lead")]
        self.assertTrue(all(t["links"]["base"] == tip for t in nxt))
        self.assertIn(tip[:10], nxt[0]["body"])
        self.assertIn("接口规范测试", nxt[0]["body"])
        # the coding line starts those changes from the lead's commit
        seen = {}
        orig = self.P.flow.runner.start
        self.P.flow.runner.start = lambda *a, **k: seen.update(base=k.get("base")) or {"id": 0}
        try:
            self.P.flow._flow_fix(self.P.project("OA"), nxt[0]["id"], {}, "fake")
        finally:
            self.P.flow.runner.start = orig
        self.assertEqual(seen["base"], tip)

    def test_three_layers_only_meet_at_their_interfaces(self):
        """Knowledge knows nothing above it; the coding line knows no app; apps use only the line's public calls."""
        import ast
        base = Path(__file__).resolve().parent.parent / "tmh" / "platform"

        def imports(name):
            tree = ast.parse((base / name).read_text(encoding="utf-8"))
            out = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom) and n.level == 1:
                    out |= {n.module} if n.module else {a.name for a in n.names}
            return out
        above = {"server", "orchestra", "apps", "reform", "alerts", "learn", "ui"}
        self.assertFalse(imports("knowledge.py") & above)
        self.assertFalse(imports("orchestra.py") & {"server", "apps", "reform", "alerts", "ui"})
        for app in ("reform.py", "alerts.py", "apps.py"):
            src = (base / app).read_text(encoding="utf-8")
            self.assertNotRegex(src, r"\b(flow|kb)\._", app)
            self.assertFalse(imports(app) & {"server", "orchestra"}, app)
        self.assertIsInstance(self.P.flow.listeners, list)
        self.assertTrue(any(getattr(f, "app", "") == "改造计划" for f in self.P.flow.listeners))

    def test_fix_gate_keeps_test_edits_and_deletions_for_people(self):
        p = {"root": str(self.repo)}
        new_test = "diff --git a/src/test/FooTest.java b/src/test/FooTest.java\nnew file mode 100644\n+++ b/src/test/FooTest.java\n+x\n"
        old_test = "diff --git a/src/test/FooTest.java b/src/test/FooTest.java\n--- a/src/test/FooTest.java\n+++ b/src/test/FooTest.java\n-x\n+y\n"
        gone = "diff --git a/A.java b/A.java\ndeleted file mode 100644\n--- a/A.java\n-x\n"
        conf = {"max_lines": 400}
        self.assertEqual(self.P.flow.fix_gate(p, new_test, conf), "")
        self.assertIn("测试", self.P.flow.fix_gate(p, old_test, conf))
        self.assertIn("删除", self.P.flow.fix_gate(p, gone, conf))
        self.assertIn("上限", self.P.flow.fix_gate(p, old_test, {"max_lines": 1}))

    def test_each_project_can_have_its_own_size_limit(self):
        big = "diff --git a/A.java b/A.java\n--- a/A.java\n+++ b/A.java\n" + "+x\n" * 50
        conf = {"max_lines": {"RW": 20000, "*": 10}}
        self.assertEqual(self.P.flow.fix_gate({"root": str(self.repo), "key": "RW"}, big, conf), "")
        self.assertIn("上限 10 行", self.P.flow.fix_gate({"root": str(self.repo), "key": "JB"}, big, conf))
        self.assertIn("上限 400 行", self.P.flow.fix_gate({"root": str(self.repo), "key": "JB"}, big * 9, {"max_lines": {"RW": 1}}))

    def test_ticket_flow_with_agent(self):
        key = self.project()
        code, meta = self.call("GET", "/api/meta")
        self.assertIn("fake", [a["name"] for a in meta["agents"]])
        code, ov = self.call("GET", "/api/projects/OA")
        self.assertTrue(ov["kb"]["built"])
        self.assertGreater(ov["kb"]["flows"], 0)

        code, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假申请提交后审批状态不对", "body": "提交请假后状态没变", "type": "缺陷"})
        self.assertEqual(code, 200, t)
        k = t["key"]
        code, rel = self.call("GET", "/api/tickets/%s/related" % k)
        self.assertTrue(rel["flows"], "a leave ticket should find the leave flows")
        fid = rel["flows"][0]["id"]
        code, t2 = self.call("POST", "/api/tickets/" + k, {"link_flow": fid})
        self.assertEqual(t2["links"]["flows"], [fid])
        code, fd = self.call("GET", "/api/projects/OA/flows/" + fid)
        self.assertIn(k, [x["key"] for x in fd["tickets"]])
        self.call("POST", "/api/tickets/%s/comments" % k, {"body": "业务说是部门经理审批这一步"})

        code, run = self.call("POST", "/api/tickets/%s/runs" % k, {"agent": "fake", "mode": "analyze"})
        self.assertEqual(code, 200, run)
        r = self.wait_run(run["id"])
        self.assertEqual(r["status"], "done", r["result"])
        self.assertIn("带知识库", r["output"])
        self.assertIn("结论", r["result"])
        code, rp = self.call("GET", "/api/runs/%d?prompt=1" % run["id"])
        self.assertIn("部门经理", rp["prompt"])  # discussion goes into the prompt
        self.assertIn(fid, rp["prompt"])
        code, d = self.call("GET", "/api/tickets/" + k)
        self.assertEqual(d["ticket"]["status"], "confirm")

        code, run = self.call("POST", "/api/tickets/%s/runs" % k, {"agent": "fake", "mode": "fix"})
        r = self.wait_run(run["id"])
        self.assertEqual(r["status"], "done", r["output"])
        self.assertIn("fixed by fake agent", r["diff"])
        self.assertNotIn("fixed by fake agent", subprocess.run(["git", "diff"], cwd=self.repo, capture_output=True, text=True).stdout,
                         "fix runs must not touch the user's working copy")
        code, _ = self.call("POST", "/api/tickets/%s/runs" % k, {"agent": "fake", "mode": "nope"})
        self.assertEqual(code, 400)
        code, r = self.call("POST", "/api/runs/%d/decide" % run["id"], {"decision": "accept"})
        self.assertEqual(code, 200, r)
        branch = r["decision"].split(":", 1)[1].split("@")[0]
        log = subprocess.run(["git", "log", "-1", "--format=%s", branch], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn(k, log)
        code, d = self.call("GET", "/api/tickets/" + k)
        self.assertEqual(d["ticket"]["status"], "verify")
        self.assertIn("adopt", [e["kind"] for e in d["events"]])
        code, again = self.call("POST", "/api/runs/%d/decide" % run["id"], {"decision": "discard"})
        self.assertEqual(code, 400)

        code, lst = self.call("GET", "/api/tickets?project=OA&q=" + urllib.request.quote("请假"))
        self.assertIn(k, [x["key"] for x in lst])
        code, runs = self.call("GET", "/api/runs?project=OA")
        self.assertGreaterEqual(len(runs), 2)

    def test_missing_agent_fails_cleanly(self):
        self.project()
        code, t = self.call("POST", "/api/tickets", {"project": "OA", "title": "随便看看"})
        (self.data / "agents.json").write_text(json.dumps({"ghost": {"cmd": ["/nonexistent/agent-bin", "{prompt_file}"]},
                                                           "fake": json.loads((self.data / "agents.json").read_text())["fake"]}), encoding="utf-8")
        code, run = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "ghost", "mode": "analyze"})
        r = self.wait_run(run["id"])
        self.assertEqual(r["status"], "failed")
        self.assertIn("启动", r["result"])

    def test_full_project_analysis(self):
        key = self.project()
        code, v = self.call("GET", "/api/projects/%s/survey" % key)
        self.assertIn(v["state"], ("idle", "done"))
        before = len(kb.pending(self.repo, kb.load_registry(self.repo)))
        code, v = self.call("POST", "/api/projects/%s/survey" % key, {"agent": "writer", "parallel": 2, "limit": 3})
        self.assertEqual(code, 200, v)
        code, again = self.call("POST", "/api/projects/%s/survey" % key, {"agent": "writer"})
        self.assertEqual(code, 409)
        for _ in range(600):
            _, v = self.call("GET", "/api/projects/%s/survey" % key)
            if v["state"] in ("done", "stopped", "failed"):
                break
            time.sleep(0.1)
        self.assertEqual(v["state"], "done", v["log"])
        self.assertEqual((v["ok"], v["failed"]), (3, 0), v["log"])
        self.assertEqual(v["pending"], before - 3)
        self.assertTrue(all(kb.load_registry(self.repo)[f["page"]]["status"] == "待确认" for f in v["finished"]))
        self.assertEqual(len({f["page"] for f in v["finished"]}), 3)
        _, runs = self.call("GET", "/api/runs?project=" + key)
        mine = {f["run"] for f in v["finished"]}
        self.assertEqual(sum(len(r["target"].split()) for r in runs if r["id"] in mine and r["status"] == "done" and r["mode"] == "kb"), 3)
        self.assertLess(len(mine), 3)  # flows of one controller went to one run together
        code, e = self.call("POST", "/api/projects/%s/survey/stop" % key)
        self.assertEqual(code, 400)

    def test_survey_resumes_after_a_restart(self):
        key = self.project()
        pid = self.P.project(key)["id"]
        conf = json.loads((self.data / "agents.json").read_text())  # another test may have swapped the agents out
        conf["writer"] = {"cmd": [sys.executable, str(self.data / "fake_writer.py"), "{mode}", "{prompt_file}", str(HERE.parent)]}
        (self.data / "agents.json").write_text(json.dumps(conf), encoding="utf-8")
        self.assertFalse((self.data / "surveys.json").exists() and str(pid) in json.loads((self.data / "surveys.json").read_text()))
        # what the last process left behind: a survey with 2 pages of its limit to go, and a page one of its workers had taken
        (self.data / "surveys.json").write_text(json.dumps({str(pid): {"agent": "writer", "parallel": 2, "scope": "all", "author": "li", "limit": 2}}))
        first = kb.pending(self.repo, kb.load_registry(self.repo))[0]
        cp = kb._claims_path(self.repo)
        cp.write_text(json.dumps({first: {"by": "tmh-w9", "at": time.time()}}))
        from tmh.platform.survey import Survey
        Survey.resume_all(self.P)  # what Platform() does on start
        v = self.wait_survey(key)
        self.assertTrue(v["resumed"])
        self.assertEqual((v["state"], v["ok"]), ("done", 2), v["log"])
        self.assertTrue(v["hit_limit"])
        self.assertIn(first, [f["page"] for f in v["finished"]])  # the old claim did not block it
        self.assertIn("不是全部写完", "\n".join(v["log"]))
        self.assertNotIn(str(pid), json.loads((self.data / "surveys.json").read_text()))

    def wait_survey(self, key):
        for _ in range(600):
            _, v = self.call("GET", "/api/projects/%s/survey" % key)
            if v["state"] in ("done", "stopped", "failed"):
                return v
            time.sleep(0.1)
        self.fail("survey did not finish")

    def test_business_map_writes_domains_then_overview(self):
        key = self.project()
        code, v = self.call("POST", "/api/projects/%s/survey" % key, {"agent": "writer", "parallel": 2, "scope": "top"})
        self.assertEqual(code, 200, v)
        v = self.wait_survey(key)
        self.assertEqual(v["state"], "done", v["log"])
        pages = [f["page"] for f in v["finished"]][::-1]
        self.assertTrue(all(p.startswith("dom:") for p in pages[:-1]), pages)
        self.assertEqual(pages[-1], "index")
        self.assertEqual(v["failed"], 0, v["log"])
        self.assertEqual(v["pending"], 0)
        reg = kb.load_registry(self.repo)
        self.assertTrue(all(reg[p]["status"] == "待确认" for p in pages))
        self.assertIn("仅工具事实", kb.pack(self.repo, "dom:expense") + kb.pack(self.repo, "dom:leave"))

    def test_analysis_writes_the_flow_pages_it_touched(self):
        key = self.project()
        code, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假审批通过后状态不对", "body": "审批通过以后请假单状态没变"})
        self.assertEqual(code, 200, t)
        code, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "writer", "mode": "analyze", "kb_after": 2})
        self.assertEqual(code, 200, r)
        self.wait_run(r["id"])
        for _ in range(300):
            _, d = self.call("GET", "/api/tickets/" + t["key"])
            done = [e for e in d["events"] if e["kind"] == "kb" and e["data"].get("page")]
            if len(done) == 2:
                break
            time.sleep(0.1)
        plan = [e for e in d["events"] if e["kind"] == "kb" and e["data"].get("pages")]
        self.assertEqual(len(plan), 1, d["events"])
        self.assertEqual(len(done), 2, d["events"])
        reg = kb.load_registry(self.repo)
        for pid in plan[0]["data"]["pages"]:
            self.assertTrue(pid.startswith("flow:"))
            self.assertEqual(reg[pid]["status"], "待确认")
        self.assertTrue(all("写成" in e["body"] for e in done))

    def test_loop_points_assistant_and_acceptance(self):
        key = self.project()
        _, meta = self.call("GET", "/api/meta")
        self.assertTrue(meta["brand"])
        code, t = self.call("POST", "/api/tickets", {"project": key, "title": "报销单财务审核后状态没变", "body": "财务审核通过以后报销单还是待审核"})
        _, L = self.call("GET", "/api/projects/%s/loop" % key)
        self.assertGreaterEqual(L["total"], 1)
        self.assertEqual(len(L["metrics"]), 4)
        self.assertIn("在流转", L["insight"])
        _, pts = self.call("GET", "/api/projects/%s/points" % key)
        before = pts["balance"]
        # evidence mode: knowledge base only, no model, no points
        code, r = self.call("POST", "/api/assist", {"project": key, "ticket": t["key"], "question": "涉及哪些业务流和表", "mode": "evidence"})
        self.assertEqual(code, 200, r)
        ans = r["messages"][-1]
        self.assertEqual(ans["role"], "assistant")
        self.assertTrue(ans["data"]["cards"], ans)
        self.assertEqual(ans["data"]["points"], 0)
        self.assertEqual(r["balance"], before)
        # draft mode: a local agent answers; its flow ids become evidence cards, and the answer costs points
        code, r = self.call("POST", "/api/assist", {"project": key, "ticket": t["key"], "question": "这单为什么失败", "mode": "draft", "agent": "writer"})
        self.assertEqual(code, 200, r)
        for _ in range(200):
            _, r = self.call("GET", "/api/assist?project=%s&ticket=%s" % (key, t["key"]))
            if r["messages"][-1]["data"].get("state") != "running":
                break
            time.sleep(0.05)
        ans = r["messages"][-1]
        self.assertEqual(ans["data"]["state"], "done", ans)
        self.assertTrue(any(c["kind"] == "flow" for c in ans["data"]["cards"]), ans)
        price = self.P.pricing["prices"]["ask"]
        self.assertEqual(ans["data"]["points"], price)
        self.assertEqual(r["balance"], before - price)
        _, d = self.call("GET", "/api/tickets/" + t["key"])
        self.assertEqual(d["ticket"]["status"], "new")  # asking does not move the ticket
        self.assertFalse([e for e in d["events"] if e["kind"].startswith("run")])
        # closing is acceptance, not a status edit
        code, e = self.call("POST", "/api/tickets/" + t["key"], {"status": "closed"})
        self.assertEqual(code, 400)
        # only a person accepts; failing needs a reason
        code, e = self.call("POST", "/api/tickets/%s/accept" % t["key"], {"result": "fail"})
        self.assertEqual(code, 400)
        code, x = self.call("POST", "/api/tickets/%s/accept" % t["key"], {"result": "fail", "note": "状态仍未变"})
        self.assertEqual(x["status"], "doing")
        code, x = self.call("POST", "/api/tickets/%s/accept" % t["key"], {"result": "pass"})
        self.assertEqual(x["status"], "closed")
        _, d = self.call("GET", "/api/tickets/" + t["key"])
        self.assertIn("evidence", d)
        code, b = self.call("POST", "/api/projects/%s/points" % key, {"delta": 100})
        self.assertEqual(b["balance"], before - price + 100)

    def test_the_panel_reads_the_question_before_searching(self):
        """Platform questions are answered from the platform's records, not from the nearest code flow."""
        key = self.project()
        li = {"X-TMH-User": "li"}
        st = self.P.store
        p = st.project(key)
        made = [self.call("POST", "/api/tickets", {"project": key, "title": "单据%d 保存报错" % i, "auto": False})[1] for i in range(3)]
        busy = "ERROR: Selected model is at capacity. Please try a different model."
        for t, res in ((made[0], busy), (made[1], busy), (made[2], "ok")):
            r = st.create_run(p["id"], t["id"], "codex", "analyze", "li", "")
            st.update_run(r["id"], status="failed" if res == busy else "done", result=res, ended="2026-10-13 10:00:00")
        _, s = self.call("POST", "/api/projects/%s/sessions" % key, {"kind": "consult", "title": "项目咨询"}, li)
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "为什么那么多失败的", "mode": "evidence"}, li)
        a = r["messages"][-1]
        self.assertEqual(a["data"]["source"], "平台记录", a)
        busy_line = next(x for x in a["body"].splitlines() if "模型满载" in x)
        self.assertIn(made[0]["key"], busy_line)
        self.assertIn(made[1]["key"], busy_line)
        self.assertNotIn(made[2]["key"], a["body"])
        self.assertNotIn("业务流", a["body"])
        self.assertTrue({made[0]["key"], made[1]["key"]} <= set(a["data"]["actions"][0]["keys"]))
        self.assertTrue(a["data"]["follow"])
        # a platform question in deep mode still costs nothing and starts no agent
        before = len(st.runs(project_id=p["id"]))
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "现在在跑什么", "mode": "draft", "agent": "writer"}, li)
        self.assertEqual(r["messages"][-1]["data"]["points"], 0)
        self.assertEqual(len(st.runs(project_id=p["id"])), before)
        # "都重试" is read against the failures listed before; nothing runs until the person confirms on the page
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "为什么失败", "mode": "evidence"}, li)
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "都重试", "mode": "evidence"}, li)
        a = r["messages"][-1]
        self.assertEqual(a["data"]["intent"], "retry")
        self.assertTrue({made[0]["key"], made[1]["key"]} <= set(a["data"]["actions"][0]["keys"]))
        self.assertEqual(len(st.runs(project_id=p["id"])), before)
        # a ticket named by key: its last step, why it failed, and the retry
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "%s 怎么了" % made[0]["key"], "mode": "evidence"}, li)
        a = r["messages"][-1]
        self.assertIn("分析定位」失败", a["body"])
        self.assertEqual(a["data"]["actions"][0]["keys"], [made[0]["key"]])
        # help, and a business question that matches nothing says so instead of naming the nearest flow
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "你能做什么", "mode": "evidence"}, li)
        self.assertIn("看平台状态", r["messages"][-1]["body"])
        _, r = self.call("POST", "/api/sessions/%d/messages" % s["id"], {"question": "量子纠缠的蝴蝶效应", "mode": "evidence"}, li)
        a = r["messages"][-1]
        self.assertTrue(a["data"]["deep"])
        self.assertTrue(a["data"]["weak"] or a["data"]["no_evidence"], a)
        self.assertNotIn("最相关的是", a["body"])

    def test_assistant_sessions(self):
        key = self.project()
        li, wang = {"X-TMH-User": "li"}, {"X-TMH-User": "wang"}
        code, a = self.call("POST", "/api/projects/%s/sessions" % key, {"kind": "matter", "matter_title": "审批通过后单据未生效"}, li)
        self.assertEqual(code, 200, a)
        _, b = self.call("POST", "/api/projects/%s/sessions" % key, {"kind": "consult", "title": "系统主要业务"}, li)
        self.assertEqual(a["kind"], "matter")
        # each session keeps its own messages; an idem key makes a resend a no-op
        for _ in range(2):
            code, r = self.call("POST", "/api/sessions/%d/messages" % a["id"], {"question": "审批在哪里实现", "mode": "evidence", "idem": "k1"}, li)
            self.assertEqual(code, 200, r)
        self.assertEqual(len(r["messages"]), 2)
        ans = r["messages"][-1]
        self.assertIn("结论与边界", ans["body"])
        _, rb = self.call("GET", "/api/sessions/%d" % b["id"], headers=li)
        self.assertEqual(rb["messages"], [])
        # sessions are personal
        code, _ = self.call("GET", "/api/sessions/%d" % a["id"], headers=wang)
        self.assertEqual(code, 404)
        _, lst = self.call("GET", "/api/projects/%s/sessions" % key, headers=wang)
        self.assertNotIn(a["id"], [s["id"] for s in lst["sessions"]])
        _, lst = self.call("GET", "/api/projects/%s/sessions" % key, headers=li)
        self.assertIn("审批通过后单据未生效", [m["title"] for m in lst["matters"]])
        # rename, archive (sending refused, messages kept), restore
        _, s = self.call("POST", "/api/sessions/%d" % a["id"], {"title": "问题排查"}, li)
        self.assertEqual(s["title"], "问题排查")
        self.call("POST", "/api/sessions/%d" % a["id"], {"archived": True}, li)
        code, _ = self.call("POST", "/api/sessions/%d/messages" % a["id"], {"question": "还在吗", "mode": "evidence"}, li)
        self.assertEqual(code, 400)
        _, s = self.call("POST", "/api/sessions/%d" % a["id"], {"archived": False}, li)
        self.assertFalse(s["archived_at"])
        _, r = self.call("GET", "/api/sessions/%d" % a["id"], headers=li)
        self.assertEqual(len(r["messages"]), 2)
        # a draft creates nothing; submitting twice with one key creates one ticket, bound to the session and matter
        _, before = self.call("GET", "/api/tickets?project=" + key)
        code, d = self.call("POST", "/api/sessions/%d/ticket-draft" % a["id"], {}, li)
        self.assertEqual(code, 200, d)
        self.assertIn("待确认", d["body"])
        self.assertEqual(d["assignee"], "")
        _, after = self.call("GET", "/api/tickets?project=" + key)
        self.assertEqual(len(after), len(before))
        sub = {"idem": "t1", "target": "new", "title": d["title"], "body": d["body"], "flows": d["flows"]}
        _, t1 = self.call("POST", "/api/sessions/%d/ticket" % a["id"], sub, li)
        _, t2 = self.call("POST", "/api/sessions/%d/ticket" % a["id"], sub, li)
        self.assertTrue(t1["created"])
        self.assertEqual(t1["key"], t2["key"])
        _, after = self.call("GET", "/api/tickets?project=" + key)
        self.assertEqual(len(after), len(before) + 1)
        _, r = self.call("GET", "/api/sessions/%d" % a["id"], headers=li)
        self.assertEqual(r["session"]["ticket"]["key"], t1["key"])
        # once bound, "existing" adds a note to that ticket instead of a new one
        _, t3 = self.call("POST", "/api/sessions/%d/ticket" % a["id"], {"idem": "t2", "target": "existing", "body": "补充：只有财务审批有这个问题"}, li)
        self.assertEqual((t3["key"], t3["created"]), (t1["key"], False))
        _, tk = self.call("GET", "/api/tickets/" + t1["key"])
        self.assertTrue(any("只有财务审批" in e["body"] for e in tk["events"]))
        # a ticket's working session is found again, not duplicated
        _, s1 = self.call("POST", "/api/projects/%s/sessions" % key, {"kind": "ticket", "ticket": t1["key"]}, wang)
        _, s2 = self.call("POST", "/api/projects/%s/sessions" % key, {"kind": "ticket", "ticket": t1["key"]}, wang)
        self.assertEqual(s1["id"], s2["id"])

    def test_old_chats_move_into_sessions(self):
        d = Path(tempfile.mkdtemp(prefix="tmh-mig-"))
        st = Store(d / "tmh.db")
        p = st.add_project("OA", "示例", str(self.repo))
        t = st.create_ticket(p["id"], "旧工单", "li")
        st.db.execute("INSERT INTO chats(project_id,ticket_id,ts,role,author,body,data) VALUES(?,?,?,?,?,?,?)",
                      (p["id"], t["id"], "2026-01-01 00:00:00", "user", "li", "旧问题", "{}"))
        st.db.execute("UPDATE chats SET session_id=NULL")
        st.db.commit()
        st._migrate_chats()
        ss = st.sessions(p["id"], "anyone")
        self.assertEqual([s["kind"] for s in ss], ["ticket"])
        self.assertEqual(len(st.session_chats(ss[0]["id"], 50)), 1)

    def test_kb_tree_and_architecture(self):
        key = self.project()
        code, tr = self.call("GET", "/api/projects/%s/kb/tree" % key)
        self.assertEqual(code, 200, tr)
        self.assertTrue(tr["domains"])
        code, a = self.call("GET", "/api/projects/%s/arch" % key)
        self.assertEqual(code, 200, a)
        self.assertTrue(a["domains"] and a["tables"])
        did = a["domains"][0]["id"]
        code, dd = self.call("GET", "/api/projects/%s/arch/%s" % (key, urllib.request.quote(did)))
        self.assertEqual(code, 200, dd)
        self.assertTrue(all(f.get("file") for f in dd["flows"]))

    def test_project_atlas(self):
        key = self.project()
        code, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假申请提交后审批状态不对", "body": "提交请假后状态没变", "type": "缺陷"})
        code, rel = self.call("GET", "/api/tickets/%s/related" % t["key"])
        fid = rel["flows"][0]["id"]
        self.call("POST", "/api/tickets/" + t["key"], {"link_flow": fid})
        code, at = self.call("GET", "/api/projects/%s/atlas" % key)
        self.assertEqual(code, 200, at)
        self.assertTrue(at["built"] and at["domains"] and at["tables"])
        self.assertEqual(at["stats"]["flows"], len(at["flows"]))
        f = next(x for x in at["flows"] if x["id"] == fid)
        self.assertIn(t["key"], [x["key"] for x in f["tickets"]])
        self.assertTrue(all(x["domain"] in {d["id"] for d in at["domains"]} for x in at["flows"]))
        code, fl = self.call("GET", "/api/projects/%s/atlas/flow/%s" % (key, urllib.request.quote(fid)))
        self.assertEqual(code, 200, fl)
        self.assertTrue(fl["steps"])
        self.assertTrue(all(s["layer"] in ("入口", "业务", "数据", "其他") for s in fl["steps"]))
        self.assertIn(t["key"], [x["key"] for x in fl["tickets"]])
        code, _ = self.call("GET", "/api/projects/%s/atlas/flow/nope" % key)
        self.assertEqual(code, 404)

    def test_question_words_do_not_steer_search(self):
        from tmh.context import query_terms, search
        self.assertEqual(query_terms("审批是在哪里实现的"), ["审批"])
        self.assertIn("个人", "".join(query_terms("个人报销怎么提交")))
        hits = search(self.repo, "审批是在哪里实现的", limit=5)
        self.assertTrue(hits)
        top = json.dumps(hits[0][1], ensure_ascii=False)
        self.assertTrue("审批" in top or "approv" in top.lower(), top)

    def test_port_in_use_is_reported_not_crashed(self):
        import contextlib
        import io
        import socket
        from tmh.platform.server import serve
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen(1)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = serve(Path(tempfile.mkdtemp(prefix="tmh-port-")), "127.0.0.1", busy.getsockname()[1], "tester", None, "", False, "")
        self.assertEqual(rc, 1)
        self.assertIn("已被占用", out.getvalue())

    def test_efficiency_metrics_baseline_and_report(self):
        import os
        from unittest import mock
        from tmh import integrations as im, mcp, usage
        from tmh.integrations.base import Issue
        from tmh.platform.metrics import report_md, ts_norm
        self.assertEqual(ts_norm("0000-00-00 00:00:00"), "")
        self.assertEqual(ts_norm("2026-03-01 09:00:00"), "2026-03-01 09:00:00")
        self.assertRegex(ts_norm("2026-03-01T09:00:00.000+0800"), r"^2026-03-0\d \d\d:00:00$")
        root = Path(tempfile.mkdtemp(prefix="tmh-eff-"))
        (root / ".tmh").mkdir()
        st, P = self.P.store, self.P
        p = st.add_project("EF", "提效", str(root))

        # baseline: closed Jira history, imported with its own dates
        class FakeJira:
            name, TYPE = "jira", "jira"

            def search_issues(self, q, limit=50):
                return [Issue(key="J-1", title="旧缺陷一", type="Bug", status="Done", assignee="王", created="2026-03-01T09:00:00.000+0800",
                              resolved="2026-03-05T09:00:00.000+0800"),
                        Issue(key="J-2", title="旧缺陷二", type="Bug", status="Done", assignee="王", created="2026-03-02 09:00:00",
                              resolved="2026-03-04 09:00:00"),
                        Issue(key="J-3", title="还开着", type="Bug", status="In Progress", created="2026-03-03 09:00:00")]
        with mock.patch.object(im, "pick", lambda *a, **k: FakeJira()):
            made = P.import_issues(p, "", [], "x", "李")
        self.assertEqual(len(made), 3)
        ext = st.ticket(made[0])["external"]
        self.assertEqual((ext["created"][:10], ext["resolved"][:10]), ("2026-03-01", "2026-03-05"))

        # pilot: one analysed, rejected once then accepted; one untouched; one only touched from the IDE
        a = st.create_ticket(p["id"], "审批卡住", "李", type="bug")
        b = st.create_ticket(p["id"], "加字段", "李", type="feature")
        c = st.create_ticket(p["id"], "导出慢", "李", type="bug")
        for t in (a, b, c):
            st.x("UPDATE tickets SET created=? WHERE id=?", ("2026-09-01 09:00:00", t["id"]))
        r = st.create_run(p["id"], a["id"], "fake", "analyze", "李", "x")
        st.update_run(r["id"], status="done", ended="2026-09-01 11:00:00")
        st.add_points(p["id"], -10, "分析定位", "李", r["id"], a["id"])
        st.x("UPDATE points SET ts=? WHERE run_id=?", ("2026-09-01 11:00:00", r["id"]))
        for kind, ts in (("reject", "2026-09-02 09:00:00"), ("accept", "2026-09-03 09:00:00")):
            e = st.event(a["id"], "李", kind, kind)
            st.x("UPDATE events SET ts=? WHERE id=?", (ts, e))
        mcp.handle(root, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "Cursor", "version": "1.7"}}})
        mcp.handle(root, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "context", "arguments": {"query": c["key"] + " 导出"}}})
        with mock.patch.dict(os.environ, {"TMH_RUN": "99", "TMH_TICKET": b["key"]}):  # the platform's own run: not IDE usage
            mcp.handle(root, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "flows", "arguments": {"query": "审批"}}})
        rows = usage.read(root)
        self.assertEqual([(x["client"], x["ticket"], x.get("run")) for x in rows], [("Cursor 1.7", c["key"], None), ("Cursor 1.7", b["key"], "99")])

        # no sealed baseline: measured numbers only, no comparison, no saving
        code, m = self.call("GET", "/api/projects/EF/metrics")
        self.assertEqual(code, 200, m)
        self.assertFalse(m["gate"]["sealed"])
        self.assertEqual((m["compare"][0]["baseline"], m["compare"][0]["change"]), ("未封存", None))
        self.assertNotIn("estimate", m)  # no "person-days saved", ever
        self.assertIn("还没有封存基线", report_md(m))
        code, cand = self.call("GET", "/api/projects/EF/baseline?from=2026-03-01&to=2026-03-31")
        self.assertEqual((cand["sealed"], cand["candidate"]["n"]), (None, 2))
        self.assertIn("样本只有 2 张", cand["candidate"]["warning"])
        self.assertEqual(self.call("POST", "/api/projects/EF/baseline/seal", {"from": "2026-04-01", "to": "2026-04-30"})[0], 409)  # empty window
        code, sealed = self.call("POST", "/api/projects/EF/baseline/seal", {"from": "2026-03-01", "to": "2026-03-31", "note": "试点前三月"})
        self.assertEqual(code, 200, sealed)
        self.assertEqual((sealed["stats"]["n"], len(sealed["sample"]), sealed["sealed_by"]), (2, 2, "tester"))
        self.assertEqual(self.call("POST", "/api/projects/EF/baseline/seal", {"from": "2026-03-01", "to": "2026-03-02"})[0], 409)  # sealed once

        code, m = self.call("GET", "/api/projects/EF/metrics")
        self.assertEqual(code, 200, m)
        self.assertTrue(m["gate"]["sealed"])
        bl, pl = m["baseline"], m["pilot"]
        self.assertEqual((bl["n"], bl["cycle"]["median_h"], bl["systems"]), (2, 72.0, ["jira"]))
        self.assertEqual(pl["n"], 4)  # three platform tickets + the open imported one
        self.assertEqual((pl["cycle"]["n"], pl["cycle"]["median_h"]), (1, 48.0))
        self.assertEqual(pl["locate"]["median_h"], 2.0)
        self.assertEqual((pl["reject"]["reviewed"], pl["reject"]["rejected"], pl["reject"]["rate"]), (1, 1, 100.0))
        self.assertEqual(pl["cycle"]["p90_h"], 48.0)
        self.assertEqual((pl["reopen"]["matured"], pl["reopen"]["reopened"]), (1, 0))  # its rejection came before the acceptance
        from tmh.platform.metrics import _reopened
        acc = "2026-09-01 10:00:00"
        self.assertTrue(_reopened([{"ts": "2026-09-05 10:00:00", "kind": "status", "data": '{"from": "closed", "to": "doing"}'}], acc))
        self.assertTrue(_reopened([{"ts": "2026-09-03 10:00:00", "kind": "reject", "data": "{}"}], acc))
        self.assertFalse(_reopened([{"ts": "2026-09-20 10:00:00", "kind": "reject", "data": "{}"}], acc))  # past the 14 days
        self.assertIn("P90", report_md(m))
        src = {x["key"]: x["n"] for x in pl["ai"]["by_source"]}
        self.assertEqual((pl["ai"]["tickets"], src["run"], src["mcp"]), (2, 1, 1))
        self.assertEqual((pl["cost"]["per_ticket"], pl["ide"]["calls"]), (10, 1))
        self.assertEqual(m["compare"][0]["change"], -33.3)
        code, sep = self.call("GET", "/api/projects/EF/metrics?month=2026-09")
        self.assertEqual((sep["pilot"]["closed"], sep["period"]), (1, "2026 年 9 月"))
        self.assertEqual(self.call("GET", "/api/projects/EF/metrics?month=9")[0], 400)

        md = report_md(m)
        for w in ("# AI 提效报告", "实测", "估算", "Cursor 1.7 1 次", "工单周期（中位数） | 3.0 天 | 2.0 天 | -33.3%", "封存窗口 2026-03-01 至 2026-03-31",
                  "## 账本（每单）", "标价折人民币 | 10.00 元", "实付 | 未录入"):
            self.assertIn(w, md)
        # the ledger: one row per ticket handled, points priced, people's actions counted
        row = {x["key"]: x for x in m["ledger"]["rows"]}[a["key"]]
        self.assertEqual((row["reworks"], row["ai_runs"], row["points"], row["list_yuan"], row["paid_yuan"], row["human_actions"]), (1, 1, 10, 10.0, None, 2))
        # a sealed baseline edited afterwards no longer counts
        f = self.data / "baselines" / "EF.json"
        f.chmod(0o644)
        f.write_text(f.read_text(encoding="utf-8").replace('"n": 2', '"n": 20', 1), encoding="utf-8")
        code, m2 = self.call("GET", "/api/projects/EF/metrics")
        self.assertFalse(m2["gate"]["sealed"])
        self.assertIn("被改过", m2["gate"]["reason"])
        self.assertIsNone(m2["compare"][0]["change"])
        code, rep = self.call("GET", "/api/projects/EF/report?month=2026-09")
        self.assertEqual(rep["filename"], "AI提效报告-EF-2026-09.md")
        with urllib.request.urlopen(self.base + "/p/EF/efficiency?month=2026-09") as resp:
            page_html = resp.read().decode("utf-8")
        self.assertIn("<table>", page_html)
        self.assertIn("2026 年 9 月", page_html)

    def test_ticket_prompt_tab(self):
        key = self.project()
        claude_md = self.repo / "CLAUDE.md"
        claude_md.write_text("# 原有说明\n\n别动我。\n", encoding="utf-8")
        _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假审批表加一个“代理人”字段", "body": "审批时要能指定代理人", "type": "feature"})
        code, pr = self.call("GET", "/api/tickets/%s/prompt?scene=field" % t["key"])
        self.assertEqual(code, 200, pr)
        self.assertEqual((pr["scene"], pr["label"]), ("field", "新增字段"))
        for w in (t["key"], "## 要做的事", "回滚脚本", "context"):
            self.assertIn(w, pr["text"])
        self.assertTrue(pr["sources"])  # the knowledge base contributed flows/tables/code
        self.assertEqual(len(pr["scenes"]), 5)

        code, r = self.call("POST", "/api/tickets/%s/prompt" % t["key"], {"scene": "field", "action": "claude"})
        self.assertEqual((code, r["files"]), (200, ["CLAUDE.md"]))
        self.call("POST", "/api/tickets/%s/prompt" % t["key"], {"scene": "bugfix", "action": "claude"})
        text = claude_md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 原有说明\n\n别动我。\n"))
        self.assertEqual(text.count("tmh:ticket:start"), 1)  # replaced, not stacked
        self.assertIn("修复缺陷", text)
        _, r = self.call("POST", "/api/tickets/%s/prompt" % t["key"], {"scene": "test", "action": "cursor"})
        mdc = self.repo / ".cursor" / "rules" / "tmh-ticket.mdc"
        self.assertIn("alwaysApply: true", mdc.read_text(encoding="utf-8"))
        self.assertEqual(r["written"], {"ticket": t["key"], "cursor": True, "claude": True})
        self.call("POST", "/api/tickets/%s/prompt" % t["key"], {"scene": "test", "action": "copy"})
        _, d = self.call("GET", "/api/tickets/" + t["key"])
        self.assertEqual(sum(1 for e in d["events"] if e["kind"] == "prompt"), 4)

        _, r = self.call("POST", "/api/tickets/%s/prompt" % t["key"], {"action": "clear"})
        self.assertEqual(r["written"], {"ticket": "", "cursor": False, "claude": False})
        self.assertEqual(claude_md.read_text(encoding="utf-8"), "# 原有说明\n\n别动我。\n")
        self.assertFalse(mdc.exists())
        self.assertEqual(self.call("POST", "/api/tickets/%s/prompt" % t["key"], {"action": "rm"})[0], 400)
        claude_md.unlink()

    def test_model_is_picked_per_run(self):
        from tmh.platform.agents import BUILTIN, command, pick_model
        claude, codex = BUILTIN["claude"], dict(BUILTIN["codex"], args=["-m", "o3", "--foo"])
        self.assertEqual((pick_model(claude, "fix", None), pick_model(claude, "kb", "auto"), pick_model(claude, "ask", "")), ("opus", "sonnet", ""))
        with self.assertRaises(ValueError):
            pick_model(claude, "fix", "opus; rm -rf /")
        f = Path("p.md")
        cmd = command({"claude": claude}, "claude", "fix", "x", f, f, f, "", "opus")
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertNotIn("--model", command({"claude": claude}, "claude", "analyze", "x", f, f, f, "", ""))
        cmd = command({"codex": codex}, "codex", "plan", "x", f, f, f, "", "gpt-5")
        self.assertEqual((cmd.count("-m"), cmd[cmd.index("-m") + 1], "--foo" in cmd), (1, "gpt-5", True))  # the pick replaces the configured one

        key = self.project()
        _, t = self.call("POST", "/api/tickets", {"project": key, "title": "选模型"})
        code, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "fake", "mode": "analyze", "model": "sonnet"})
        self.assertEqual((code, r["model"]), (200, "sonnet"))
        self.assertEqual(self.wait_run(r["id"])["model"], "sonnet")
        _, d = self.call("GET", "/api/tickets/" + t["key"])
        self.assertIn("（sonnet）", [e for e in d["events"] if e["kind"] == "run"][-1]["body"])
        self.assertEqual(self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "fake", "mode": "analyze", "model": "a b"})[0], 400)
        _, meta = self.call("GET", "/api/meta")
        cl = next(a for a in meta["agents"] if a["name"] == "claude")
        self.assertEqual(([m[0] for m in cl["models"]], cl["defaults"]["plan"]), (["opus", "sonnet", "haiku"], "opus"))

    def test_kb_views(self):
        self.project()
        code, d = self.call("GET", "/api/projects/OA/kb")
        self.assertTrue(d["pages"])
        pid = d["pages"][0]["id"]
        code, pg = self.call("GET", "/api/projects/OA/kb/page?id=" + urllib.request.quote(pid))
        self.assertEqual(code, 200)
        self.assertTrue(pg["text"])

    def test_kb_questions_answers_and_triage(self):
        self.project()
        code, r = self.call("POST", "/api/projects/OA/kb/ask", {"question": "驳回后预算怎么处理？", "pages": ["dom:expense"], "to": "财务"})
        self.assertEqual(code, 200)
        code, q = self.call("GET", "/api/projects/OA/kb/questions")
        self.assertEqual(q["stats"]["questions_open"], 1)
        self.assertNotIn("key_env", q["router"])
        code, e = self.call("POST", "/api/projects/OA/kb/answer", {"n": r["n"], "text": ""})
        self.assertEqual(code, 400)
        code, a = self.call("POST", "/api/projects/OA/kb/answer", {"n": r["n"], "text": "全额释放"}, headers={"X-TMH-User": "wang"})
        self.assertEqual((code, a["pages"]), (200, ["dom:expense"]))
        code, t = self.call("POST", "/api/projects/OA/kb/triage", {"request": "报销审核驳回释放预算", "model": False})
        self.assertEqual((code, t["verdict"]), (200, "需要人判断"))


    def test_command_plan_is_kept_in_the_session(self):
        self.project()
        code, t = self.call("POST", "/api/tickets", {"project": "OA", "title": "审批后单据未生效"})
        code, s = self.call("POST", "/api/projects/OA/sessions", {"kind": "consult"})
        code, r = self.call("POST", "/api/projects/OA/command", {"text": "给 %s 写评论：需要现场日志" % t["key"], "page": {"route": "#/"}, "session": s["id"]})
        self.assertEqual(code, 200, r)
        self.assertEqual([x["op"] for x in r["plan"]["steps"]], ["nav", "fill", "click"])
        code, q = self.call("POST", "/api/projects/OA/command", {"text": "审批在哪里实现？", "session": s["id"]})
        self.assertEqual(q["plan"]["kind"], "question")
        self.assertNotIn("message", q)
        code, u = self.call("POST", "/api/sessions/%s/command/%s" % (s["id"], r["message"]), {"state": "done", "done": 3})
        self.assertEqual((code, u["data"]["state"], u["data"]["done"]), (200, "done", 3))
        code, v = self.call("GET", "/api/sessions/%s" % s["id"])
        self.assertEqual([m["data"].get("kind") for m in v["messages"]], ["cmd", "cmd"])
        code, d = self.call("POST", "/api/sessions/%s/ticket-draft" % s["id"])
        self.assertNotIn("需要现场日志", d["body"])  # page operations are not the problem description
        code, _ = self.call("POST", "/api/sessions/%s/command/999" % s["id"], {"state": "done"})
        self.assertEqual(code, 404)

    def test_similar_metrics_overrule_and_bot_api(self):
        import os
        from unittest import mock
        from tmh import config as cfgmod
        self.project()
        code, a = self.call("POST", "/api/tickets", {"project": "OA", "title": "请假列表按部门筛选为空", "body": "选了部门以后列表没有数据"})
        self.assertEqual(code, 200, a)
        code, b = self.call("POST", "/api/tickets", {"project": "OA", "title": "请假列表部门筛选不出数据", "body": "部门筛选后列表为空"})
        code, r = self.call("GET", "/api/tickets/%s/similar" % b["key"])
        self.assertEqual(r["similar"][0]["key"], a["key"])
        code, r = self.call("POST", "/api/projects/OA/similar", {"title": "部门筛选 请假列表 空白"})
        self.assertIn(a["key"], [x["key"] for x in r["similar"]])
        code, t = self.call("POST", "/api/projects/OA/kb/triage", {"request": "请假列表加一个导出", "model": False})
        code, m = self.call("GET", "/api/projects/OA/kb/metrics")
        self.assertEqual(m["recent"][0]["id"], t["id"])
        self.assertEqual(m["recent"][0]["channel"], "web")
        code, o = self.call("POST", "/api/projects/OA/kb/overrule", {"id": t["id"], "reason": "导出已有"}, headers={"X-TMH-User": "wang"})
        self.assertEqual((code, o["by"]), (200, "wang"))
        code, _ = self.call("POST", "/api/projects/OA/kb/overrule", {"id": "00000000", "reason": "x"})
        self.assertEqual(code, 404)
        code, rep = self.call("GET", "/api/projects/OA/report")
        self.assertIn("少找人", rep["markdown"])
        c = cfgmod.load(self.repo)
        c["bots"] = {"api": {"key_env": "TMH_TEST_BOT_KEY"}}
        cfgmod.save(self.repo, c)
        with mock.patch.dict(os.environ, {"TMH_TEST_BOT_KEY": "k-9"}):
            code, st = self.call("GET", "/api/projects/OA/bots")
            self.assertEqual((st["bots"]["api"]["ready"], st["paths"]["api"]), (True, "/bot/api/OA"))
            # callbacks come from outside: no platform token or X-TMH header, any Host; the key is what counts
            code, r = self.call("POST", "/bot/api/OA", {"text": "请假列表加一个导出", "model": False}, headers={"X-TMH": "", "Host": "bot.example.com", "Authorization": "Bearer k-9"})
            self.assertEqual((code, r["kind"]), (200, "triage"))
            code, r = self.call("POST", "/bot/api/OA", {"text": "x"}, headers={"Host": "bot.example.com", "Authorization": "Bearer nope"})
            self.assertEqual(code, 401)
            code, r = self.call("POST", "/bot/dingtalk/OA", {}, headers={"Host": "bot.example.com"})
            self.assertEqual(code, 404)  # not configured for this project
            code, r = self.call("POST", "/bot/api/NOPE", {"text": "x"}, headers={"Authorization": "Bearer k-9"})
            self.assertEqual(code, 404)

    def test_requirement_conversation_turns_vague_words_into_tickets_with_criteria(self):
        """One message with two asks and a question: split, ask only what is missing, EARS criteria, tickets on confirm."""
        from tmh.platform import signoff
        key = self.project()
        msg = "请假审批通过后状态还是草稿，不对。另外希望请假列表能导出 Excel。还有，年假是怎么计算的？"
        code, s = self.call("POST", "/api/projects/%s/intake" % key, {"text": msg, "model": False})
        self.assertEqual(code, 200, s)
        self.assertEqual([it["kind"] for it in s["items"]], ["bug", "feature", "question"])
        bug, feat, q = s["items"]
        self.assertEqual(s["state"], "asking")
        self.assertTrue(q["answer"])  # a question is answered, never ticketed
        self.assertEqual(q["questions"], [])
        self.assertTrue(all(len(it["questions"]) <= 3 for it in s["items"]))
        self.assertEqual(bug["slots"]["trigger"]["from"], "原话")  # "审批通过后" was said: not asked again
        self.assertNotIn("trigger", [x["slot"] for x in bug["questions"]])
        self.assertIn("待确认", bug["ac"][0]["text"] + bug["ac"][0]["check"])  # nothing guessed
        self.assertTrue(any(a["text"].startswith("必须保持") for a in bug["ac"]))
        ans = {"0": {"expected": "状态变成已通过", "who": "所有人", "since": "这周", "example": "张三提交 3 天年假，经理审批通过后列表显示已通过"},
               "1": {"trigger": "在请假列表页点导出", "expected": "下载当前筛选结果的 Excel", "example": UNSURE_WORD}}
        if bug["questions"] and bug["questions"][0]["slot"] == "flow":
            ans["0"]["flow"] = bug["questions"][0]["options"][0]
        code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "answer", "answers": ans})
        self.assertEqual(code, 200, s)
        bug, feat = s["items"][0], s["items"][1]
        self.assertTrue(bug["ac"][0]["text"].startswith("当") and "系统应当状态变成已通过" in bug["ac"][0]["text"], bug["ac"])
        self.assertFalse(bug["ac"][0]["open"])
        self.assertTrue(feat["ac"][0]["open"])  # "不清楚" stays 待确认
        self.assertEqual(self.call("POST", "/api/intake/%s" % s["id"], {"action": "answer", "answers": {"9": {"trigger": "x"}}})[0], 400)
        code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        self.assertEqual((code, len(s["tickets"]), s["state"]), (200, 2, "confirmed"), s)
        _, t = self.call("GET", "/api/tickets/%s" % s["tickets"][0])
        self.assertEqual(t["ticket"]["type"], "bug")
        self.assertIn("验收标准", t["ticket"]["body"])
        self.assertIn("张三提交 3 天年假", t["ticket"]["body"])
        recs = signoff.records(self.data, s["tickets"][0])
        self.assertEqual((recs[0]["kind"], recs[0]["data"]["confirmed_by"]), ("intake", "tester"))
        self.assertEqual(self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})[0], 409)
        self.assertEqual(self.call("GET", "/api/intake/nope")[0], 404)

    def test_box_on_the_page_finds_the_backend_and_starts_a_ticket(self):
        """The client's bookmarklet posts a box; the requests in it lead to the flow; the location rides into the ticket."""
        key = self.project()
        code, tk = self.call("POST", "/api/projects/%s/capture-token" % key, {"base": "https://webuddy.example"})
        self.assertEqual(code, 200, tk)
        tok = tk["bookmarklet"].split("/capture/")[1].split("'")[0]
        cap = {"url": "http://oa.local/leave/list", "title": "请假", "texts": ["提交"], "note": "点提交以后状态还是草稿",
               "elements": [{"tag": "button", "text": "提交"}], "requests": ["http://oa.local/leave/submit"]}
        post = lambda t, body: urllib.request.Request(self.base + "/capture/" + t, method="POST", data=body, headers={"Content-Type": "text/plain"})
        with urllib.request.urlopen(post(tok, json.dumps(cap).encode())) as r:  # no account, no X-TMH: the token is all it has
            self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), "*")
            got = json.loads(r.read())
        self.assertIn("后端入口", got["message"])
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(post("x" * 24, json.dumps(cap).encode()))
        self.assertEqual(e.exception.code, 401)
        _, ps = self.call("GET", "/api/projects/%s/pins" % key)
        pin = ps["pins"][0]
        self.assertTrue(ps["has_token"])
        self.assertEqual((pin["id"], pin["via"]), (got["id"], "bookmarklet"))
        self.assertIn("/leave/submit", pin["found"]["layer3"][0]["entry"])
        self.assertTrue(pin["found"]["layer3"][0]["flows"])
        self.assertIn("后端：", pin["summary"])
        code, s = self.call("POST", "/api/pins/%s/intake" % pin["id"], {"model": False})
        self.assertEqual(code, 200, s)
        self.assertEqual((s["text"], s["pin"]["id"]), ("点提交以后状态还是草稿", pin["id"]))
        code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        self.assertEqual(code, 200, s)
        _, t = self.call("GET", "/api/tickets/%s" % s["tickets"][0])
        self.assertIn("## 位置", t["ticket"]["body"])
        self.assertIn("/leave/submit", t["ticket"]["body"])
        self.assertEqual(self.call("GET", "/api/pins/000000000000")[0], 404)
        code, x = self.call("POST", "/api/projects/%s/pins" % key, {"texts": []})
        self.assertEqual(code, 400, x)

    def test_evidence_package_sign_off_and_ledger(self):
        """AI gathers the evidence, a person signs on a page without code, the ledger picks it up."""
        import re as _re
        from tmh import evidence
        from tmh.graph import Graph
        from tmh.platform import signoff
        self.team()
        try:
            key = self.project()
            g = Graph(self.repo)
            fid = next(f["id"] for f in g.nodes("flow") if any((g.node(e["dst"]) or {}).get("file") == SVC for e in g.out(f["id"], "step")))
            _, t = self.call("POST", "/api/tickets", {"project": key, "title": "请假提交后状态不更新", "body": "员工提交请假后，列表里状态还是草稿"})
            self.call("POST", "/api/tickets/%s" % t["key"], {"link_flow": fid})
            self.assertEqual(self.call("GET", "/api/tickets/%s/evidence" % t["key"])[1]["status"], "none")
            for mode in ("plan", "fix"):
                _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "team", "mode": mode})
                r = self.wait_run(r["id"])
            code, d = self.call("POST", "/api/runs/%d/decide" % r["id"], {"decision": "accept"})
            self.assertEqual(code, 200, d)

            # handed over for acceptance → packed, complete: AC, change, build, scope, flow, reviewer (the person who adopted it)
            code, s = self.call("GET", "/api/tickets/%s/evidence" % t["key"])
            self.assertEqual((s["status"], s["missing"], s["intact"]), ("ready", [], True), s)
            # not signed yet: no decision at all (an empty list here once broke the ticket page, [] being truthy in the browser)
            self.assertIsNone(s["decision"])
            self.assertIsNone(self.call("GET", "/api/tickets/%s" % t["key"])[1]["package"]["decision"])
            snap = s["snapshot"]
            self.assertEqual(snap["ac"][0]["id"], "A1")
            self.assertEqual((snap["check"]["result"], snap["path"]["ok"], snap["change"]["files"]), ("pass", True, [SVC]))
            self.assertEqual(s["review"]["by"], "tester")
            self.assertIn("evidence", [e["kind"] for e in self.call("GET", "/api/tickets/%s" % t["key"])[1]["events"]])
            # every verification gate passed, each with its reason; letting one through takes a gate that exists and a reason
            self.assertEqual((s["gate_state"], [g["id"] for g in s["gates"] if g["state"] != "pass"]), ("pass", []), s["gates"])
            self.assertIn("等价", next(g for g in s["gates"] if g["id"] == "match")["why"])
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "review", "waive": {"nope": "随便写写理由"}})[0], 400)
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "review", "waive": {"scope": "短"}})[0], 400)

            # a screenshot for A1; only images, only small ones
            png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "attach", "ac": "A1", "image": "data:text/html;base64,PGI+"})[0], 400)
            code, a = self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "attach", "ac": "A1", "note": "提交后列表显示“审批中”", "image": png})
            self.assertEqual(code, 200, a)
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "nope"})[0], 400)

            # a one-time link for the named signer
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "link"})[0], 400)
            # exported as an in-toto Statement that checks out offline, and stops checking out once a record is touched
            with urllib.request.urlopen(self.base + "/e/%s.intoto.json" % t["key"]) as r:
                stmt = json.loads(r.read())
            from tmh import evidence as ev
            self.assertEqual((stmt["_type"], stmt["predicateType"]), (ev.STATEMENT, ev.PREDICATE))
            self.assertTrue(ev.verify_statement(stmt, self.call("GET", "/api/tickets/%s/evidence" % t["key"])[1]["hash"][:10])[0])
            self.assertFalse(ev.verify_statement(stmt, "deadbeef")[0])
            stmt["predicate"]["records"][0]["by"] = "别人"
            self.assertFalse(ev.verify_statement(stmt)[0])
            code, ln = self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "link", "signer": "周敏", "role": "人事业务负责人"})
            self.assertEqual(code, 200, ln)
            with urllib.request.urlopen(self.base + ln["path"]) as resp:
                page_html = resp.read().decode("utf-8")
            for w in ("请假提交后状态不更新", "提交后状态更新", "签收", "退回", "证据包完整", "提交后列表显示", "验证门：9 道，通过 9 道"):
                self.assertIn(w, page_html)
            for code_word in (".java", "LeaveService", "diff", "src/main"):  # no code on the client's page
                self.assertNotIn(code_word, page_html)
            img = _re.search(r"src='(/sign/[^']+)'", page_html).group(1)
            with urllib.request.urlopen(self.base + img) as resp:
                self.assertEqual(resp.headers["Content-Type"], "image/png")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(self.base + "/sign/" + "x" * 32)
            self.assertEqual(cm.exception.code, 404)

            def post(form):
                data = "&".join("%s=%s" % (k, urllib.request.quote(v)) for k, v in form.items()).encode()
                req = urllib.request.Request(self.base + ln["path"], data=data, method="POST",
                                             headers={"Content-Type": "application/x-www-form-urlencoded"})
                try:
                    with urllib.request.urlopen(req) as resp:
                        return resp.status, resp.read().decode("utf-8")
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode("utf-8")
            code, body = post({"action": "sign", "name": "别人", "ac_A1": "pass"})
            self.assertEqual(code, 400)
            self.assertIn("周敏", body)
            self.assertEqual(post({"action": "sign", "name": "周敏"})[0], 400)  # every criterion has to be confirmed
            self.assertEqual(post({"action": "reject", "name": "周敏"})[0], 400)  # a rejection needs a reason
            code, body = post({"action": "sign", "name": "周敏", "ac_A1": "pass", "note": "已在测试环境操作确认"})
            self.assertEqual(code, 200, body)
            self.assertIn("已签收", body)
            self.assertEqual(post({"action": "sign", "name": "周敏", "ac_A1": "pass"})[0], 410)  # one time only

            t2 = self.call("GET", "/api/tickets/%s" % t["key"])[1]
            self.assertEqual(t2["ticket"]["status"], "closed")
            acc = [e for e in t2["events"] if e["kind"] == "accept"][-1]
            self.assertEqual(acc["author"], "周敏（甲方人事业务负责人）")
            self.assertEqual(t2["package"]["status"], "signed")
            recs = signoff.records(self.data, t["key"])
            self.assertEqual([x["kind"] for x in recs], ["pack", "attach", "link", "sign"])
            self.assertEqual(recs[-1]["data"]["package_hash"], recs[-2]["hash"])  # the signature names the package it signed
            with urllib.request.urlopen(self.base + "/e/%s" % t["key"]) as resp:
                full = resp.read().decode("utf-8")
            self.assertIn(SVC, full)  # the provider's copy keeps the code facts
            self.assertIn("甲方签收", full)
            self.assertIn("没有削弱测试", full)  # the gates, each with its reason

            # the ledger shows it signed through the client's link
            row = {x["key"]: x for x in self.call("GET", "/api/projects/%s/ledger" % key)[1]["ledger"]["rows"]}[t["key"]]
            self.assertEqual((row["evidence_status"], row["signer"], row["signed_via"]), ("signed", "周敏", "签收链接"))

            # tampering breaks the seal, and nothing more can be added or signed
            f = signoff.epath(self.data, t["key"])
            f.write_text(f.read_text(encoding="utf-8").replace("已在测试环境操作确认", "随便"), encoding="utf-8")
            ok, why = evidence.check(evidence.read(f))
            self.assertFalse(ok)
            self.assertIn("第 4 条", why)
            code, s = self.call("GET", "/api/tickets/%s/evidence" % t["key"])
            self.assertFalse(s["intact"])
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t["key"], {"kind": "attach", "note": "再补"})[0], 409)

            # a ticket handed over with nothing behind it: everything missing, a link only with a written reason
            _, t3 = self.call("POST", "/api/tickets", {"project": key, "title": "导出按钮没反应"})
            self.call("POST", "/api/tickets/%s" % t3["key"], {"status": "verify"})
            s3 = self.call("GET", "/api/tickets/%s/evidence" % t3["key"])[1]
            self.assertEqual(s3["status"], "incomplete")
            self.assertIn("验收标准（AC）", s3["missing"])
            code, e3 = self.call("POST", "/api/tickets/%s/evidence" % t3["key"], {"kind": "link", "signer": "周敏"})
            self.assertEqual(code, 409)
            self.assertIn("证据还缺", e3["error"])
            self.assertEqual(self.call("POST", "/api/tickets/%s/evidence" % t3["key"], {"kind": "link", "signer": "周敏", "note": "甲方要求先看现场"})[0], 200)
            # the platform's own 验收 button also lands on the chain
            self.assertEqual(self.call("POST", "/api/tickets/%s/accept" % t3["key"], {"result": "fail", "note": "还是没反应"})[0], 200)
            self.assertEqual(signoff.records(self.data, t3["key"])[-1]["kind"], "reject")
        finally:
            self.untrain()

    def test_external_pull_request_is_drafted_approved_and_tracked_to_merge(self):
        """A change proposed upstream: a person approves the exact draft, GitHub's verdict lands in the evidence package."""
        from unittest import mock
        from tmh.platform import signoff, upstream
        key = self.project()
        _, t = self.call("POST", "/api/tickets", {"project": key, "title": "订单服务缺少权限检查"})
        k = t["key"]
        self.assertEqual(self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "link", "repo": "not a repo"})[0], 400)
        code, u = self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "link", "repo": "apache/ofbiz-framework", "issue": "OFBIZ-1"})
        self.assertEqual((code, u["upstream"]["repo"], u["label"]), (200, "apache/ofbiz-framework", "未开始"))
        self.assertEqual(self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "submit"})[0], 409)  # nothing approved
        draft = {"action": "draft", "title": "Fixed: missing permission check in OrderServices", "body": "AI-assisted, reviewed by a person.",
                 "head": "auntunt:fix-order-perm", "base": "trunk"}
        self.assertEqual(self.call("POST", "/api/tickets/%s/upstream" % k, draft)[0], 200)
        self.assertEqual(self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "approve"}, {"X-TMH-User": "agent"})[0], 403)
        # no evidence package with gates behind this ticket: approving takes a written reason
        self.assertEqual(self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "approve", "note": "看过了"})[0], 409)
        code, u = self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "approve", "note": "改动在测试机上验证过，三处页面都看过"})
        self.assertEqual((u["state"], u["approved"]["by"]), ("approved", "tester"))
        # the draft changed after approval: approve again
        self.call("POST", "/api/tickets/%s/upstream" % k, dict(draft, body="changed"))
        self.assertEqual(self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "submit"})[0], 409)
        self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "approve", "note": "改动在测试机上验证过，三处页面都看过"})

        class FakeHub:
            sent = []

            def __init__(self, dry):
                self.dry = dry

            def open_pr(self, head, base, title, body, draft=False):
                if self.dry:
                    return {"dry_run": True}
                FakeHub.sent.append((head, base, title))
                return {"number": 2300, "url": "https://github.com/apache/ofbiz-framework/pull/2300"}
        with mock.patch.object(upstream, "client", lambda repo, dry_run=True: FakeHub(dry_run)):
            code, r = self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "submit"})
            self.assertEqual((code, r["dry_run"], FakeHub.sent), (200, True, []))  # without confirm nothing goes out
            with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "x"}):
                code, u = self.call("POST", "/api/tickets/%s/upstream" % k, {"action": "submit", "confirm": True})
        self.assertEqual((code, u["upstream"]["pr"], u["state"]), (200, "2300", "open"), u)
        self.assertEqual(FakeHub.sent, [("auntunt:fix-order-perm", "trunk", draft["title"])])

        def status(state, reviews, commits, merged=""):
            return {"number": 2300, "url": "https://github.com/apache/ofbiz-framework/pull/2300", "title": draft["title"], "author": "auntunt",
                    "state": state, "draft": False, "created": "2026-10-16T02:00:00Z", "updated": "", "closed": merged, "merged": merged,
                    "merged_by": "jacopoc" if merged else "", "merge_commit": "", "head": "abc", "head_ref": "fix-order-perm", "base": "trunk",
                    "additions": 6, "deletions": 1, "changed_files": 1, "ci": {"state": "success", "checks": []}, "reviews": reviews,
                    "review_comments": [], "comments": [], "commits": commits}
        ask = {"by": "jacopoc", "state": "CHANGES_REQUESTED", "at": "2026-10-16T05:00:00Z", "body": "Please use hasEntityPermission"}
        c1 = {"sha": "a1", "author": "auntunt", "at": "2026-10-16T02:00:00Z", "message": "Fixed"}
        u = upstream.sync(self.P, self.P.store.ticket(k), status=status("open", [ask], [c1]))
        self.assertEqual((u["state"], u["summary"]["rounds"]), ("changes", 1))
        c2 = {"sha": "a2", "author": "auntunt", "at": "2026-10-16T06:00:00Z", "message": "Use hasEntityPermission"}
        ok = {"by": "jacopoc", "state": "APPROVED", "at": "2026-10-16T07:00:00Z", "body": ""}
        c3 = {"sha": "a3", "author": "jacopoc", "at": "2026-10-16T07:30:00Z", "message": "Tidy"}
        u = upstream.sync(self.P, self.P.store.ticket(k), status=status("merged", [ask, ok], [c1, c2, c3], "2026-10-16T08:00:00Z"))
        self.assertEqual((u["state"], u["summary"]["maintainer_commits"], u["summary"]["hours_to_merge"]), ("merged", 1, 6.0))
        t2 = self.call("GET", "/api/tickets/%s" % k)[1]
        self.assertEqual(t2["ticket"]["status"], "closed")
        self.assertEqual(t2["package"]["status"], "upstream_merged")
        kinds = [r["kind"] for r in signoff.records(self.data, k)]
        self.assertEqual(kinds[:4], ["upstream_draft", "upstream_approve", "upstream_draft", "upstream_approve"])
        self.assertIn("upstream_review", kinds)
        self.assertEqual(kinds[-1], "upstream_outcome")
        m = self.call("GET", "/api/projects/%s/upstream" % key)[1]
        self.assertEqual((m["submitted"], m["merged"], m["merge_rate"], m["rounds_avg"], m["maintainer_edited"]), (1, 1, 100.0, 1.0, 1))
        from tmh.platform.metrics import report_md
        self.assertIn("## 外部 PR（第三方验收）", report_md(self.P.metrics(self.P.store.project(key))))


if __name__ == "__main__":
    unittest.main()
