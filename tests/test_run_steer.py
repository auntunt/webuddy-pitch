"""执行中插话：人对正在跑的 AI 说一句，写进运行的 notes 文件（AI 每步读），也进日志和工单时间线；运行结束后不能再插话。"""
import json
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

from tmh.platform import agents  # noqa: E402
from tmh.platform.server import Platform, make_handler  # noqa: E402
from test_platform import JAVA, git_repo  # noqa: E402


class RunSteerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = git_repo(JAVA)
        cls.data = Path(tempfile.mkdtemp(prefix="tmh-steer-"))
        cls.P = Platform(cls.data, "tester")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        assert cls.call(cls, "POST", "/api/projects", {"key": "ST", "name": "插话", "root": str(cls.repo)})[0] == 200
        code, t = cls.call(cls, "POST", "/api/tickets", {"project": "ST", "title": "评标报告按万元汇总", "type": "feature"})
        assert code == 200, t
        cls.ticket = cls.P.store.ticket(t["key"])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"X-TMH": "1", "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def _run(self, status):
        return self.P.store.x("INSERT INTO runs(ticket_id,project_id,agent,mode,status,created) VALUES(?,?,?,?,?,datetime('now'))",
                              (self.ticket["id"], self.ticket["project_id"], "codex", "fix", status))

    def test_hint_only_for_working_modes(self):
        self.assertIn("TMH_NOTES", agents.steer_hint("fix"))
        self.assertEqual(agents.steer_hint("ask"), "")

    def test_say_reaches_notes_log_and_ticket(self):
        rid = self._run("running")
        code, r = self.call("POST", "/api/runs/%d/say" % rid, {"text": "金额保留两位小数"})
        self.assertEqual(code, 200, r)
        self.call("POST", "/api/runs/%d/say" % rid, {"text": "合计行放最后"})
        notes = agents.notes_file(self.data, rid).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(notes), 2)
        self.assertIn("金额保留两位小数", notes[0])
        self.assertIn("插话：合计行放最后", self.P.store.run(rid)["output"])
        self.assertIn("steer", [e["kind"] for e in self.P.store.events(self.ticket["id"])])
        self.assertEqual(self.call("POST", "/api/runs/%d/say" % rid, {"text": " "})[0], 400)

    def test_a_word_said_after_the_last_look_is_flagged_unread(self):
        bot = self.data / "late_bot.py"
        bot.write_text(
            "import json, os\n"
            "import time\n"
            "print(json.dumps({'type': 'item.started', 'item': {'type': 'command_execution', 'command': 'cat \"$TMH_NOTES\"'}}), flush=True)\n"
            "time.sleep(0.5)\n"
            "n = os.environ['TMH_NOTES']\n"
            "if not os.path.exists(n):\n"
            "    open(n, 'a', encoding='utf-8').write('[12:00:00 li] 错误提示用中文\\n')\n"
            "print('结论：生日校验在 PetController')\n", encoding="utf-8")
        (self.data / "agents.json").write_text(json.dumps({"late": {"cmd": [sys.executable, str(bot), "{mode}", "{prompt_file}"]}}),
                                               encoding="utf-8")
        code, r = self.call("POST", "/api/tickets/%s/runs" % self.ticket["key"], {"mode": "analyze", "agent": "late"})
        self.assertEqual(code, 200, r)
        for _ in range(200):
            run = self.P.store.run(r["id"])
            if run["status"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        self.assertIn("插话没被读到", run["output"])
        flows = [e for e in self.P.store.events(self.ticket["id"]) if e["kind"] == "flow" and "插话没被读到" in e["body"] and e["data"].get("run") == r["id"]]
        self.assertEqual(len(flows), 1)
        self.assertIn("错误提示用中文", flows[0]["body"])

    def test_timing_counts_only_what_came_after_the_last_look(self):
        f = self.data / "notes-timing.md"
        f.write_text("[10:00:00 li] 先看新增\n", encoding="utf-8")
        t = agents.Timing(notes=f)
        self.assertIn("先看新增", t.unread_notes()[0])  # never looked: all of it is unread
        t.feed(json.dumps({"type": "item.started", "item": {"type": "command_execution", "command": 'cat "$TMH_NOTES"; ls'}}) + "\n")
        self.assertEqual(t.unread_notes()[0], "")
        with f.open("a", encoding="utf-8") as fh:
            fh.write("[10:01:00 li] 编辑也要校验\n")
        text, size = t.unread_notes()
        self.assertEqual(text, "[10:01:00 li] 编辑也要校验")
        self.assertEqual(t.unread_notes(size)[0], "")  # already said once
        self.assertEqual(agents.Timing(notes=self.data / "missing.md").unread_notes()[0], "")

    def test_finished_run_refuses(self):
        rid = self._run("done")
        self.assertEqual(self.call("POST", "/api/runs/%d/say" % rid, {"text": "晚了"})[0], 409)


if __name__ == "__main__":
    unittest.main()
