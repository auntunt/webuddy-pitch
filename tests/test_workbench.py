"""The workbench: clients and what came from them, versions with the main line's standing preview, and the today feed."""
import json
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
sys.path.insert(0, str(HERE))

from tmh import kb  # noqa: E402
from tmh.platform.server import Platform, make_handler  # noqa: E402
from test_platform import FAKE_TEAM, JAVA, PREVIEW_APP, git_repo  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class WorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = git_repo(JAVA)
        (cls.repo / "app.py").write_text(PREVIEW_APP, encoding="utf-8")
        kb.build(cls.repo)
        from tmh import config as cfgmod
        cfg = cfgmod.load(cls.repo)
        cfg["commands"]["test"] = "%s -c pass" % sys.executable
        cfgmod.save(cls.repo, cfg)
        for a in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "app"]):
            subprocess.run(["git", "-C", str(cls.repo)] + a, check=True)
        cls.data = Path(tempfile.mkdtemp(prefix="tmh-wb-"))
        bot = cls.data / "fake_team.py"
        bot.write_text(FAKE_TEAM, encoding="utf-8")
        (cls.data / "agents.json").write_text(json.dumps({"team": {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}}), encoding="utf-8")
        (cls.data / "autoflow.json").write_text('{"on": false, "merge": "auto"}', encoding="utf-8")
        from tmh.platform import release
        cls._merge, release.MERGE = release.MERGE, ""
        cls.P = Platform(cls.data, "tester")
        from tmh.platform import workbench
        workbench.DEBOUNCE = 0.3
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        code, p = cls.call(cls, "POST", "/api/projects", {"key": "WB", "name": "工作台", "root": str(cls.repo)})
        assert code == 200, p

    @classmethod
    def tearDownClass(cls):
        from tmh.platform import preview, release
        release.MERGE = cls._merge
        preview.stop(cls.P, "WB-main")
        cls.httpd.shutdown()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"X-TMH": "1", "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def raw(self, path, cookie=""):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            r = urllib.request.build_opener(NoRedirect).open(req, timeout=20)
            return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def wait_run(self, rid):
        for _ in range(300):
            _, r = self.call("GET", "/api/runs/%d" % rid)
            if r["status"] not in ("queued", "running"):
                return r
            time.sleep(0.05)
        self.fail("run %d did not finish" % rid)

    def fixed(self, title):
        _, t = self.call("POST", "/api/tickets", {"project": "WB", "title": title, "body": "## 原话\n\n%s\n" % title, "auto": False})
        for mode in ("plan", "fix"):
            _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "team", "mode": mode})
            r = self.wait_run(r["id"])
            self.assertEqual(r["status"], "done", r.get("result"))
        code, d = self.call("POST", "/api/runs/%d/decide" % r["id"], {"decision": "accept"})
        self.assertEqual(code, 200, d)
        return t

    def until(self, fn, what, n=200):
        for _ in range(n):
            v = fn()
            if v:
                return v
            time.sleep(0.1)
        self.fail(what)

    def test_1_clients_and_what_came_from_them(self):
        code, c = self.call("POST", "/api/clients", {"name": "王总（某某集团）", "contact": "138", "projects": "WB"})
        self.assertEqual(code, 200, c)
        self.assertEqual(c["projects"], ["WB"])
        self.assertEqual(self.call("POST", "/api/clients", {"name": "王总（某某集团）"})[0], 409)
        self.assertEqual(self.call("POST", "/api/clients", {"name": "  "})[0], 400)
        self.assertEqual(self.call("POST", "/api/clients", {"name": "x", "projects": ["NOPE"]})[0], 404)
        code, c2 = self.call("POST", "/api/clients/%d" % c["id"], {"action": "update", "notes": "每周三开会"})
        self.assertEqual(c2["notes"], "每周三开会")

        # pasted once: the requirement talk starts and records whose words they were; a new name makes a client
        code, s = self.call("POST", "/api/workbench/intake", {"project": "WB", "client_name": "李经理",
                                                              "text": "请假审批通过后，请假列表里状态还是草稿，所有人都这样，从上周开始"})
        self.assertEqual(code, 200, s)
        self.assertTrue(s["client"])
        _, cs = self.call("GET", "/api/clients")
        li = next(x for x in cs["clients"] if x["name"] == "李经理")
        self.assertEqual((li["projects"], li["links"]), (["WB"], 1))
        _, v = self.call("GET", "/api/clients/%d" % li["id"])
        self.assertEqual(v["asked"][0]["kind"], "talk")
        self.assertEqual(v["owed"][0]["state"], "talk")  # still being understood: owed, in plain words
        _, req = self.call("GET", "/api/requirements?project=WB")
        talk = [x for x in req["columns"][0]["items"] if x.get("id") == s["id"]]
        self.assertEqual(talk[0]["client_name"], "李经理")
        code, done = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        self.assertEqual(code, 200, done)
        key = done["tickets"][0]
        self.assertEqual(self.P.store.ticket(key)["links"]["client"], li["id"])  # handed on when the talk made it, not when someone looks
        self.assertTrue(any(e["kind"] == "client" and "李经理" in e["body"] for e in self.P.store.events(self.P.store.ticket(key)["id"])))
        _, v = self.call("GET", "/api/clients/%d" % li["id"])
        r = next(x for x in v["requirements"] if x["key"] == key)
        self.assertIn(r["label"], ("做着", "等客户确认", "等你看"))
        self.assertTrue(any(x.get("key") == key for x in v["owed"]))
        self.assertIn("请假", r["said"])

        # a ticket made by hand, and a group chat, are attached the same way
        _, t = self.call("POST", "/api/tickets", {"project": "WB", "title": "报销单导出金额格式不对", "auto": False})
        self.assertEqual(self.call("POST", "/api/clients/%d" % c["id"], {"action": "link", "kind": "ticket", "ref": t["key"]})[0], 200)
        self.assertEqual(self.P.store.ticket(t["key"])["links"]["client"], c["id"])
        _, t2 = self.call("POST", "/api/tickets", {"project": "WB", "title": "群里说的：考勤导出慢", "auto": False})
        (self.data / "chat").mkdir(exist_ok=True)
        (self.data / "chat" / "convs.json").write_text(json.dumps({"WB:feishu:oc_1": {"project": "WB", "channel": "feishu", "tickets": [t2["key"]],
                                                                                       "seen": "2026-10-17 09:00:00"}}), encoding="utf-8")
        _, chats = self.call("GET", "/api/chats")
        self.assertEqual(chats["chats"][0]["id"], "WB:feishu:oc_1")
        self.assertEqual(self.call("POST", "/api/clients/%d" % c["id"], {"action": "link", "kind": "chat", "ref": "nope"})[0], 404)
        self.call("POST", "/api/clients/%d" % c["id"], {"action": "link", "kind": "chat", "ref": "WB:feishu:oc_1"})
        self.assertEqual(self.P.store.ticket(t2["key"])["links"]["client"], c["id"])
        _, v = self.call("GET", "/api/clients/%d" % c["id"])
        self.assertEqual({x["key"] for x in v["requirements"]}, {t["key"], t2["key"]})
        self.assertEqual(self.call("POST", "/api/clients/%d" % c["id"], {"action": "link", "kind": "bogus", "ref": "x"})[0], 400)
        self.call("POST", "/api/clients/%d" % c["id"], {"action": "unlink", "kind": "ticket", "ref": t["key"]})
        self.assertNotIn("client", self.P.store.ticket(t["key"])["links"])

        # taking a ticket off a client by hand: only the client it is under can, and the talk it came from does not put it back
        self.assertEqual(self.call("POST", "/api/clients/%d" % c["id"], {"action": "unlink", "kind": "ticket", "ref": key})[0], 409)
        self.assertEqual(self.P.store.ticket(key)["links"]["client"], li["id"])
        self.assertEqual(self.call("POST", "/api/clients/%d" % c["id"], {"action": "unlink", "kind": "intake", "ref": s["id"]})[0], 409)
        self.assertEqual(self.call("POST", "/api/clients/%d" % li["id"], {"action": "unlink", "kind": "ticket", "ref": key})[0], 200)
        self.assertNotIn("client", self.P.store.ticket(key)["links"])
        self.assertTrue(any(e["kind"] == "client" and e["body"].startswith("不再记为") for e in self.P.store.events(self.P.store.ticket(key)["id"])))
        from tmh.platform import workbench
        workbench.sync(self.P)
        self.call("POST", "/api/clients/%d" % li["id"], {"action": "link", "kind": "intake", "ref": s["id"]})
        self.assertNotIn("client", self.P.store.ticket(key)["links"])  # stays off
        self.call("POST", "/api/clients/%d" % li["id"], {"action": "link", "kind": "ticket", "ref": key})
        self.assertEqual(self.P.store.ticket(key)["links"]["client"], li["id"])  # until put back by hand

        # a group conversation moved to another client takes the tickets made from it along
        self.call("POST", "/api/clients/%d" % li["id"], {"action": "link", "kind": "chat", "ref": "WB:feishu:oc_1"})
        self.assertEqual(self.P.store.ticket(t2["key"])["links"]["client"], li["id"])
        self.call("POST", "/api/clients/%d" % c["id"], {"action": "link", "kind": "chat", "ref": "WB:feishu:oc_1"})
        self.assertEqual(self.P.store.ticket(t2["key"])["links"]["client"], c["id"])

        # reading never writes: a ticket the chat made since is not handed a client by someone looking
        _, t3 = self.call("POST", "/api/tickets", {"project": "WB", "title": "群里又说：排班表打不开", "auto": False})
        (self.data / "chat" / "convs.json").write_text(json.dumps({"WB:feishu:oc_1": {"project": "WB", "channel": "feishu", "tickets": [t2["key"], t3["key"]],
                                                                                       "seen": "2026-10-17 09:00:00"}}), encoding="utf-8")
        snap = lambda: [(x["id"], x["updated"], json.dumps(x["links"], sort_keys=True)) for x in self.P.store.q("SELECT id, updated, links FROM tickets ORDER BY id")]
        before, nev = snap(), self.P.store.one("SELECT COUNT(*) n FROM events")["n"]
        for path in ("/api/clients?counts=1", "/api/clients/%d" % c["id"], "/api/clients/%d" % li["id"], "/api/requirements?project=WB",
                     "/api/today", "/api/today?since=2000-01-01T00:00", "/api/projects/WB/versions", "/api/chats"):
            self.assertEqual(self.call("GET", path)[0], 200, path)
        self.assertEqual(snap(), before)
        self.assertEqual(self.P.store.one("SELECT COUNT(*) n FROM events")["n"], nev)
        workbench.sync(self.P)  # what a write (a confirmed talk, a chat's new ticket) runs
        self.assertEqual(self.P.store.ticket(t3["key"])["links"]["client"], c["id"])

        # deleting a client takes its links with it, not its tickets
        _, tmp = self.call("POST", "/api/clients", {"name": "临时客户"})
        self.call("POST", "/api/clients/%d" % tmp["id"], {"action": "link", "kind": "ticket", "ref": t["key"]})
        self.assertEqual(self.call("POST", "/api/clients/%d" % tmp["id"], {"action": "delete"})[0], 200)
        self.assertNotIn("client", self.P.store.ticket(t["key"])["links"])
        self.assertEqual(self.call("GET", "/api/clients/%d" % tmp["id"])[0], 404)

    def test_2_versions_standing_preview_follows_merges_and_a_client_link_opens_it(self):
        from tmh.platform import preview
        _, v = self.call("GET", "/api/projects/WB/versions")
        self.assertFalse(v["standing"]["configured"])
        self.assertIn("预览命令", v["standing"]["fix"])  # no command yet: say so, with the fix
        self.assertEqual(self.call("POST", "/api/projects/WB/preview-conf", {"cmd": "%s app.py {port} {prefix}" % sys.executable})[0], 200)
        _, c = self.call("POST", "/api/clients", {"name": "赵总", "projects": ["WB"]})
        t = self.fixed("请假审批提交后状态不刷新")
        self.call("POST", "/api/clients/%d" % c["id"], {"action": "link", "kind": "ticket", "ref": t["key"]})
        # a client holds a link to the current version: so it follows each merge
        code, sh = self.call("POST", "/api/projects/WB/shares", {"client": c["id"], "days": 7})
        self.assertEqual(code, 200, sh)
        code, r = self.call("POST", "/api/tickets/%s/accept" % t["key"], {"result": "pass"})
        self.assertEqual(code, 200, r)
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short=10", "HEAD"], capture_output=True, text=True).stdout.strip()
        st = self.until(lambda: (preview.status(self.data, "WB-main").get("state") == "up") and preview.status(self.data, "WB-main"),
                        "the standing preview did not come up after the merge")
        self.assertEqual(st["commit"], head)  # the version just made, not the ticket's branch
        _, v = self.call("GET", "/api/projects/WB/versions")
        self.assertEqual(v["standing"]["url"], "/pv/WB-main/")
        self.assertFalse(v["standing"]["stale"])
        top = v["versions"][0]
        self.assertEqual((top["items"][0]["key"], top["items"][0]["client_name"]), (t["key"], "赵总"))
        self.assertIn("给赵总", top["note"])
        _, cv = self.call("GET", "/api/clients/%d" % c["id"])
        self.assertEqual(cv["versions"][0]["version"], top["version"])
        self.assertEqual(cv["requirements"][0]["label"], "已出版本")
        self.assertEqual(cv["owed"], [])

        # the client's link: a page with the version and what it holds for them, then into the preview, nothing else
        code, _, page = self.raw(sh["path"])
        self.assertEqual(code, 200)
        self.assertIn(top["version"], page)
        self.assertIn("请假审批提交后状态不刷新", page)
        self.assertNotIn("/api/", page)
        code, h, _ = self.raw(sh["path"] + "/open")
        self.assertEqual(code, 303)
        loc = h["Location"]
        self.assertIn("/pv/WB-main/__open?g=", loc)
        code, h, _ = self.raw(loc[loc.index("/pv/"):])
        self.assertEqual(code, 303)
        jar = h["Set-Cookie"].split(";")[0]
        code, h, body = self.raw("/pv/WB-main/", jar)
        self.assertEqual(code, 200, body)
        self.assertIn("preview ok", body)
        self.assertEqual(self.raw("/pv/WB-MAIN/", jar)[0], 308)  # one spelling
        self.assertEqual(self.raw("/v/" + "x" * 30)[0], 404)
        self.call("POST", "/api/projects/WB/shares/%s/revoke" % sh["id"], {})
        self.assertEqual(self.raw(sh["path"])[0], 410)
        self.assertNotEqual(self.raw("/pv/WB-main/", jar)[0], 200)  # a revoked link no longer opens it

        # the next version: the standing preview moves to it
        t2 = self.fixed("请假列表排序不对")
        self.call("POST", "/api/tickets/%s/accept" % t2["key"], {"result": "pass"})
        head2 = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short=10", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertNotEqual(head, head2)
        self.until(lambda: preview.status(self.data, "WB-main").get("commit") == head2 and preview.status(self.data, "WB-main").get("state") == "up",
                   "the standing preview did not move to the new version")
        self.assertIsNone(self.P.store.ticket("WB-main"))
        code, s2 = self.call("POST", "/api/projects/WB/standing", {"action": "stop"})
        self.assertEqual((code, s2["state"]), (200, ""))

        # a link for no one in particular says how much changed, not what other clients asked for
        code, any_ = self.call("POST", "/api/projects/WB/shares", {"days": 3})
        self.assertEqual((code, any_["client_name"]), (200, ""))
        page = self.raw(any_["path"])[2]
        self.assertIn("本版包含 2 项改进", page)
        self.assertNotIn("请假审批提交后状态不刷新", page)
        self.assertNotIn("请假列表排序不对", page)
        # the whole address is made by the platform, with a warning when a client could not reach it
        self.assertTrue(any_["url"].endswith(any_["path"]) and any_["url"].startswith("http"), any_)
        self.assertTrue(any_["private"])  # 127.0.0.1
        self.assertIn("TMH_PUBLIC_URL", any_["warn"])
        old, self.P.public_url = self.P.public_url, "https://wb.example.com"
        try:
            _, pub = self.call("POST", "/api/projects/WB/shares", {"client": c["id"]})
        finally:
            self.P.public_url = old
        self.assertEqual((pub["url"], pub["private"], pub["warn"]), ("https://wb.example.com" + pub["path"], False, ""))

        # today: what went out since the last look, and what the AI did
        _, td = self.call("GET", "/api/today?since=2000-01-01T00:00")
        self.assertTrue(any(x["version"] == top["version"] for x in td["versions"]))
        self.assertTrue(any(x["kind"] == "release" and x["key"] == t["key"] for x in td["did"]))
        self.assertEqual(next(x for x in td["did"] if x["key"] == t["key"])["client_name"], "赵总")
        _, td = self.call("GET", "/api/today?since=2999-01-01T00:00")
        self.assertEqual((td["versions"], td["did"]), ([], []))

    def test_3_today_shows_running_work_waiting_items_and_open_questions(self):
        _, s = self.call("POST", "/api/workbench/intake", {"project": "WB", "client_name": "孙总", "text": "希望请假单能导出"})
        _, t = self.call("POST", "/api/tickets", {"project": "WB", "title": "考勤月报对不上", "auto": False})
        _, r = self.call("POST", "/api/tickets/%s/runs" % t["key"], {"agent": "team", "mode": "analyze"})
        _, td = self.call("GET", "/api/today")
        self.assertEqual(sorted(td), sorted(["now", "mine", "others", "did", "versions", "talks", "open_ac", "auto", "agent", "since", "server_time", "handwork",
                                                  "standing_failed"]))
        talk = next(x for x in td["talks"] if x["id"] == s["id"])
        self.assertEqual(talk["client_name"], "孙总")
        if self.call("GET", "/api/runs/%d" % r["id"])[1]["status"] in ("queued", "running"):
            self.assertTrue(any(x["key"] == t["key"] for x in td["now"]))
        self.wait_run(r["id"])
        _, td = self.call("GET", "/api/today")
        self.assertFalse(any(x["key"] == t["key"] for x in td["now"]))
        self.assertEqual(self.call("GET", "/api/today?since=%3Cscript%3E")[1]["since"], "")

    def test_4_main_line_previews_are_capped_debounced_and_stopped_when_idle(self):
        from unittest import mock
        from tmh.platform import preview, release, workbench
        p = self.P.project("WB")
        live = {"AA-main": {"state": "up", "started": "2026-10-17 08:00:00"}, "BB-main": {"state": "up", "started": "2026-10-17 08:00:00"}}
        stopped, started = [], []
        workbench.touch(self.data, "AA-main", "started", at=time.time() - 3600)
        workbench.touch(self.data, "BB-main", "started", at=time.time() - 60)
        with mock.patch.object(preview, "_load", lambda d: dict(live)), \
                mock.patch.object(preview, "stop", lambda P, k, why="": stopped.append(k)), \
                mock.patch.object(preview, "start", lambda P, p, t, b, by: started.append(t["key"]) or {"state": "starting"}), \
                mock.patch.object(preview, "command", lambda d, p: ("x {port}", "/", True)), \
                mock.patch.object(release, "main_branch", lambda *a: "master"):
            self.assertEqual(workbench.MAX_STANDING, 2)
            workbench.start_standing(self.P, p, "tester")
            self.assertEqual((stopped, started), (["AA-main"], ["WB-main"]))  # two running already: the one used least lately makes room

            calls = []
            fn = workbench.on_release(self.P)
            common = (mock.patch.object(workbench, "start_standing", lambda P, p, by, person=True: calls.append(by)),
                      mock.patch.object(preview, "settings", lambda d: {"preview": "auto"}))
            with common[0], common[1], mock.patch.object(workbench, "shares", lambda P, k: []), \
                    mock.patch.object(workbench, "_last_used", lambda d, k: 0):
                fn(p, {"id": 1}, {"version": "v9"})  # nobody opened it lately and no client holds a link: it stays down
                time.sleep(0.6)
                self.assertEqual(calls, [])
            common = (mock.patch.object(workbench, "start_standing", lambda P, p, by, person=True: calls.append(by)),
                      mock.patch.object(preview, "settings", lambda d: {"preview": "auto"}))
            with common[0], common[1], mock.patch.object(workbench, "shares", lambda P, k: [{"id": "x"}]):
                for v in ("v1", "v2", "v3"):  # three merges in a row: one restart, for the last
                    fn(p, {"id": 1}, {"version": v})
                time.sleep(0.9)
                self.assertEqual(calls, ["新版本 v3"])

            stopped.clear()
            self.assertEqual(workbench.reap(self.P), [])  # used within the last IDLE_H hours
            self.assertEqual(sorted(workbench.reap(self.P, at=time.time() + 13 * 3600)), ["AA-main", "BB-main"])  # idle longer: stopped
            self.assertEqual(sorted(stopped), ["AA-main", "BB-main"])


if __name__ == "__main__":
    unittest.main()
