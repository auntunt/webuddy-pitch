"""Saved-answer recovery over real HTTP, sessions, evidence and local executors.

The reader below is deterministic synthetic code, never a model. The server is
owned by this test on an ephemeral loopback port and is always closed afterward.
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests.sqlite_snapshot import dump_store
from tmh.platform import intake, signoff, workbench
from tmh.platform.server import Platform, make_handler


ANSWER = "马上显示 <保留客户原文>"
READER = r'''
import json, pathlib, sys, time
root = pathlib.Path(__file__).parent
mode = (root / "reader-mode").read_text()
prompt = pathlib.Path(sys.argv[1]).read_text()
if mode == "fail":
    print("SYNTHETIC interpretation failed; saved answers must survive", flush=True)
    raise SystemExit(7)
if mode == "wait":
    (root / "reader-ready").write_text("ready")
    while not (root / "reader-release").exists():
        time.sleep(.02)
answered = mode != "initial"
if answered:
    assert "马上显示 <保留客户原文>" in prompt, "retry must receive the exact saved answer"
item = {"title":"保存后列表可见", "quote":"保存后列表看不到记录", "kind":"缺陷",
 "restated":"我理解的是：保存后列表应出现记录", "flow":"新模块",
 "questions":[] if answered else [{"q":"保存后应该多久可见？", "blocks":["A1"]}],
 "ac":[{"id":"A1", "text":"保存后应当%s看到记录" % ("马上" if answered else "【待确认：多久】"),
         "check":"保存一条记录并检查列表"},
        {"id":"A2", "text":"旧记录内容保持不变", "check":"核对旧记录原文"}],
 "keep":["权限范围保持不变"]}
print("```tmh-intake\n" + json.dumps({"title":"保存后可见", "items":[item]}, ensure_ascii=False) + "\n```", flush=True)
'''


class IntakeRecoveryApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="webuddy-intake-api-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.script = self.data / "synthetic-reader.py"
        self.script.write_text(READER)
        self.mode("initial")
        (self.data / "agents.json").write_text(json.dumps({"reader": {
            "cmd": [sys.executable, str(self.script), "{prompt_file}"], "run_timeout": 5}}))
        self.configure()
        self.P = Platform(self.data, "fixture-user")
        self.addCleanup(self.P.store.db.close)
        self.project = self.P.store.add_project("RECAPI", "恢复 HTTP 技术夹具", str(self.data))
        self.client = workbench.create_client(self.P, {"name": "合成客户王总"}, "fixture-user")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.P))
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.close_server)
        self.addCleanup(self.finish_owned_reader)
        self.base = "http://127.0.0.1:%s" % self.httpd.server_address[1]
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def close_server(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.server_thread.join(2)

    def finish_owned_reader(self):
        (self.data / "reader-release").write_text("release")
        end = time.monotonic() + 6
        while time.monotonic() < end:
            active = [c for c in self.P.runner.controls.values() if not c.get("finished")]
            if not active:
                with intake._LOCK:
                    pass
                return
            time.sleep(.02)
        self.fail("the test's reader did not finish its bounded run")

    def configure(self, understand="agent"):
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "preview": "off",
            "understand": understand, "understand_agent": "reader", "understand_timeout": 10}))

    def mode(self, value):
        (self.data / "reader-mode").write_text(value)

    def call(self, method, path, body=None, *, write_header=True, user="恢复操作员"):
        headers = {"Content-Type": "application/json", "X-TMH-User": urllib.parse.quote(user)}
        if write_header:
            headers["X-TMH"] = "1"
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
        try:
            with self.opener.open(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def failed_answer(self):
        s = intake.start(self.P, self.project, "保存后列表看不到记录", "工程师", wait=True)
        self.assertEqual(s["understood"]["by"], "智能体", s)
        s = intake.confirm(self.P, s["id"], "工程师")
        self.sid, self.key = s["id"], s["tickets"][0]
        workbench.link(self.P, self.client["id"], "intake", self.sid, "工程师")
        link = intake.ask_client(self.P, self.sid, "工程师", tell=False)
        self.mode("fail")
        intake.client_answer(self.P, link["token"], {"0": {"q1": ANSWER}}, name="王总", wait=True)
        state = intake.recovery_state(self.P, self.key)
        self.assertEqual(state["status"], "failed", state)
        self.assertTrue(state["can_retry"], state)
        self.assertEqual(self.P.store.run(state["run"])["exit_code"], 7)
        return state

    def snapshot(self):
        with self.P.store.lock:
            database = dump_store(self.P.store)
        files = {str(p.relative_to(self.data)): p.read_bytes() for p in self.data.rglob("*")
                 if p.is_file() and not p.name.startswith("platform.db")}
        return database, files

    def same_everywhere(self, expected, includes):
        ticket = self.P.store.ticket(self.key)
        state = workbench.states(self.P, [ticket])[self.key]
        self.assertEqual(state["state"], expected, state)
        self.assertIn(includes, state["why"])
        code, detail = self.call("GET", "/api/tickets/" + self.key)
        self.assertEqual(code, 200, detail)
        self.assertEqual(detail["plain_state"], state)
        code, requirements = self.call("GET", "/api/requirements?project=RECAPI")
        self.assertEqual(code, 200, requirements)
        col, row = next((c, t) for c in requirements["columns"] for t in c["items"] if t.get("key") == self.key)
        self.assertEqual((col["key"], row["why"], row["version"]), (expected, state["why"], state["version"]))
        code, client = self.call("GET", "/api/clients/%s" % self.client["id"])
        self.assertEqual(code, 200, client)
        row = next(t for t in client["requirements"] if t["key"] == self.key)
        self.assertEqual({k: row[k] for k in state}, state)
        return detail

    def wait_reader(self):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            if (self.data / "reader-ready").exists():
                return
            time.sleep(.01)
        self.fail("owned reader did not reach the waiting phase")

    def wait_recovery(self):
        end = time.monotonic() + 6
        while time.monotonic() < end:
            state = intake.recovery_state(self.P, self.key)
            if state["status"] != "running":
                return state
            time.sleep(.01)
        self.fail("recovery did not finish: " + json.dumps(state, ensure_ascii=False))

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_failed_saved_answer_is_read_only_and_has_the_same_owner_on_all_pages(self):
        failed = self.failed_answer()
        before = self.snapshot()
        detail = self.same_everywhere("you", "客户答复已保存")
        recovery = detail["intake_recovery"]
        self.assertEqual((recovery["session"], recovery["run"]), (self.sid, failed["run"]))
        self.assertEqual(recovery["items"][0]["answers"][0]["value"], ANSWER)
        self.assertEqual(recovery["items"][0]["answers"][0]["from"], "王总（客户）")
        self.assertEqual(self.snapshot(), before, "ticket/client/requirements GETs cannot repair or rewrite stored state")

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_real_http_retry_has_running_state_and_blocks_duplicate_until_complete(self):
        failed = self.failed_answer()
        self.mode("wait")
        code, started = self.call("POST", "/api/tickets/%s/intake-retry" % self.key, {})
        self.assertEqual(code, 200, started)
        self.assertEqual(started["status"], "running")
        self.wait_reader()
        before = self.snapshot()
        self.assertEqual(self.same_everywhere("doing", "已保存答复")["intake_recovery"]["status"], "running")
        self.assertEqual(self.snapshot(), before)
        code, duplicate = self.call("POST", "/api/tickets/%s/intake-retry" % self.key, {})
        self.assertEqual(code, 409, duplicate)
        self.assertEqual(self.snapshot(), before, "a duplicate retry must not append a new job or evidence")
        (self.data / "reader-release").write_text("release")
        self.assertEqual(self.wait_recovery()["status"], "resolved")
        self.assertNotIn("open_ac", self.P.store.ticket(self.key)["links"])
        runs = [r for r in self.P.store.runs(project_id=self.project["id"]) if r["mode"] == "understand"]
        self.assertEqual(len(runs), 3, "initial read + failed answer + exactly one recovery")
        self.assertEqual(self.P.store.run(failed["run"])["status"], "failed")

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_retry_delegates_canonical_key_actor_and_wait_without_replacing_customer_words(self):
        self.failed_answer()
        self.mode("success")
        before = json.loads((intake.idir(self.data) / (self.sid + ".json")).read_text())
        contract = signoff.client_ac(self.data, self.key)
        with mock.patch.object(intake, "retry_understanding", wraps=intake.retry_understanding) as retry:
            code, result = self.call("POST", "/api/tickets/%s/intake-retry" % self.key.lower(),
                                    {"wait": True, "answers": {"0": {"q1": "must not overwrite"}}})
        self.assertEqual(code, 200, result)
        retry.assert_called_once_with(self.P, self.key, "恢复操作员", wait=True)
        self.assertEqual(result["status"], "resolved", result)
        after = json.loads((intake.idir(self.data) / (self.sid + ".json")).read_text())
        self.assertEqual(after["items"][0]["slots"]["q1"], before["items"][0]["slots"]["q1"])
        self.assertEqual(signoff.client_ac(self.data, self.key)[1:], contract[1:])

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_closed_ticket_stays_closed_everywhere_and_rejects_retry_without_writes(self):
        self.failed_answer()
        self.P.store.update_ticket(self.P.store.ticket(self.key)["id"], "工程师", status="closed")
        before = self.snapshot()
        detail = self.same_everywhere("done", "已关闭")
        self.assertFalse(detail["intake_recovery"]["can_retry"])
        code, result = self.call("POST", "/api/tickets/%s/intake-retry" % self.key, {})
        self.assertEqual(code, 409, result)
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_missing_executor_blocks_retry_with_a_409_and_keeps_saved_answers(self):
        self.failed_answer()
        self.configure(understand="rules")
        before = self.snapshot()
        detail = self.same_everywhere("you", "客户答复已保存")
        self.assertFalse(detail["intake_recovery"]["can_retry"])
        self.assertTrue(detail["intake_recovery"]["blocked"])
        code, result = self.call("POST", "/api/tickets/%s/intake-retry" % self.key, {})
        self.assertEqual(code, 409, result)
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_http_retry_requires_write_header_and_missing_ticket_does_not_delegate(self):
        self.failed_answer()
        before = self.snapshot()
        with mock.patch.object(intake, "retry_understanding", wraps=intake.retry_understanding) as retry:
            code, result = self.call("POST", "/api/tickets/%s/intake-retry" % self.key, {}, write_header=False)
            self.assertEqual(code, 403, result)
            code, result = self.call("POST", "/api/tickets/RECAPI-999/intake-retry", {})
            self.assertEqual(code, 404, result)
            retry.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_expired_recovery_reads_do_not_sweep_or_land_customer_answers(self):
        self.failed_answer()
        # Model a retained job after a server restart, with no live process.
        # Views must report it without turning a GET into answer application.
        with mock.patch.object(intake, "_spawn"):
            intake.retry_understanding(self.P, self.key, "fixture-operator")
        path = intake.idir(self.data) / (self.sid + ".json")
        session = json.loads(path.read_text())
        session["understanding_job"]["t0"] = 0
        path.write_text(json.dumps(session, ensure_ascii=False))
        before = self.snapshot()
        self.same_everywhere("doing", "已保存答复")
        self.assertEqual(self.snapshot(), before, "expired GETs must not invoke the mutating intake sweep")

    @unittest.skipUnless(os.name == 'posix', 'supervised execution requires POSIX')
    def test_uncertain_process_cleanup_blocks_http_retry_without_changing_evidence(self):
        failed = self.failed_answer()
        path = self.data / "runs" / str(failed["run"]) / "lifecycle.json"
        life = json.loads(path.read_text())
        self.assertIsNotNone(life["attempts"][0]["pid"], "fixture must have executed a real reader process")
        life["attempts"][0]["cleanup"]["complete"] = False
        path.write_text(json.dumps(life, ensure_ascii=False))
        before = self.snapshot()
        detail = self.same_everywhere("you", "客户答复已保存")
        self.assertFalse(detail["intake_recovery"]["can_retry"])
        self.assertIn("回收", "；".join(detail["intake_recovery"]["blocked"]))
        code, result = self.call("POST", "/api/tickets/%s/intake-retry" % self.key, {})
        self.assertEqual(code, 409, result)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
