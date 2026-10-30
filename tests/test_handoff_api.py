"""Real loopback HTTP and signed synthetic accounts; no business approvals."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from http.server import ThreadingHTTPServer

from tmh import bots
from tmh.platform import handoffs, login, team
from tmh.platform.server import Platform, make_handler


class HandoffHTTPTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, bots, "INTAKE", bots.INTAKE)
        temp = tempfile.TemporaryDirectory(prefix="handoff-http-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.P = Platform(self.home / "runtime", "untrusted-display")
        self.addCleanup(self.P.store.db.close)
        self.store = self.P.store
        self.root = self.home / "repo"
        self.root.mkdir()
        self.project = self.store.add_project("ORG", "Synthetic delivery", str(self.root))
        self.store.add_project("OTHER", "Other scope", str(self.root))
        login._save_users(self.P.data_dir, {name: {"pw": "unusable-synthetic-hash"} for name in ("alice", "bob", "charlie")})
        self.cookies = {name: "tmh_session=" + login.make_session(self.P.data_dir, name) for name in ("alice", "bob", "charlie")}
        self.ticket = self.store.create_ticket(self.project["id"], "研发交给测试再交付", "reporter", assignee="alice", body="完整要求\n" * 800)
        team.schema(self.P)
        self.store.x("INSERT INTO ticket_team VALUES(?,?,?,?,?)", (self.ticket["id"], "charlie", 1, self.ticket["updated"], "alice"))
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.P, "synthetic-token"))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = "http://127.0.0.1:%d" % self.http.server_address[1]
        self.opener = build_opener(ProxyHandler({}))
        self.serial = 0

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def call(self, path="/api/handoffs", body=None, user="alice", headers=None, token=False):
        hdr = {"X-TMH": "1", "Content-Type": "application/json"}
        if user:
            hdr["Cookie"] = self.cookies[user]
        if token:
            hdr["X-TMH-Token"] = "synthetic-token"
        hdr.update(headers or {})
        req = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=hdr)
        try:
            with self.opener.open(req, timeout=10) as res:
                return res.status, json.loads(res.read())
        except HTTPError as res:
            with res:
                return res.code, json.loads(res.read())

    def read(self, user="alice"):
        code, data = self.call("/api/handoffs?ticket=" + self.ticket["key"], user=user)
        self.assertEqual(code, 200, data)
        return data

    def body(self, action, user="alice", **kw):
        data = self.read(user)
        self.serial += 1
        body = {"ticket": self.ticket["key"], "action": action, "revision": data["revision"], "request_id": "http-%d" % self.serial, "note": "完整交接说明"}
        if action == "send":
            body.update(receiver="bob", stage="testing", materials="逐项材料\n" * 600, source_token=data["source_token"])
        else:
            body["handoff_id"] = data["current"]["id"]
        body.update(kw)
        return body

    def action(self, action, user="alice", **kw):
        code, result = self.call(body=self.body(action, user, **kw), user=user)
        self.assertEqual(code, 200, result)
        return result

    def test_personal_cookie_required_and_display_or_agent_cannot_act(self):
        body = self.body("send")
        self.assertEqual(self.call(body=body, user="")[0], 401)
        self.assertEqual(self.call(body=body, user="", token=True, headers={"X-TMH-User": "alice"})[0], 403)
        self.assertEqual(self.call(body=body, headers={"X-Webuddy-Agent": "external:fixture"})[0], 403)
        self.assertEqual(self.call(body=body, user="charlie")[0], 403)
        self.assertEqual(self.store.q("SELECT * FROM ticket_handoffs"), [])
        code, result = self.call(body=body, headers={"X-TMH-User": "bob"})
        self.assertEqual(code, 200, result)
        self.assertEqual(result["current"]["sender"], "alice")

    def test_complete_testing_delivery_path_never_changes_acceptance_or_assignment(self):
        original = self.store.ticket(self.ticket["id"])
        assignment = team.assignment(self.P, original)
        first = self.action("send")
        self.assertEqual(first["current"]["materials"], "逐项材料\n" * 600)
        self.assertEqual(first["source"]["ticket"]["body"], original["body"])
        self.assertEqual(self.call(body=self.body("receive", "charlie"), user="charlie")[0], 403)
        self.action("block", "bob", note="等待隔离测试环境")
        code, queue = self.call("/api/workspace?view=incoming", user="bob")
        self.assertEqual(code, 200, queue)
        self.assertEqual(queue["incoming_count"], 1)
        self.action("resume", "bob")
        self.action("receive", "bob")
        self.action("send", "bob", receiver="charlie", stage="delivery")
        self.action("return", "charlie", note="补充回滚步骤")
        self.action("send", "bob", receiver="charlie", stage="delivery")
        result = self.action("receive", "charlie")
        self.assertEqual(result["current"]["stage"], "delivery")
        self.assertEqual(len(result["history"]), 3)
        self.assertEqual(self.store.ticket(self.ticket["id"]), original)
        self.assertEqual(team.assignment(self.P, original), assignment)
        self.assertEqual(self.store.q("SELECT * FROM events WHERE kind IN ('accept','reject','close','candidate_decision')"), [])
        self.assertEqual(result["work"]["human"], "not_requested")

    def test_source_change_blocks_receive_but_sender_can_withdraw(self):
        self.action("send")
        self.store.comment(self.ticket["id"], "alice", "需求增加异常恢复")
        self.assertTrue(self.read("bob")["current"]["stale"])
        code, body = self.call(body=self.body("receive", "bob"), user="bob")
        self.assertEqual(code, 409, body)
        self.assertEqual(self.action("withdraw", note="需求已变化，补齐材料后重发")["current"]["status"], "withdrawn")

    def test_missing_and_cross_scope_reads_are_rejected(self):
        self.assertEqual(self.call("/api/handoffs")[0], 400)
        self.assertEqual(self.call("/api/handoffs?ticket=ORG-999")[0], 404)
        self.assertEqual(self.call("/api/handoffs?ticket=" + self.ticket["key"] + "&project=OTHER")[0], 404)

    def test_committed_receipt_survives_projection_error_and_replays_once(self):
        body = self.body("send")
        with patch.object(team, "item", side_effect=RuntimeError("合成附加读失败")), patch("tmh.platform.server.traceback.print_exc") as logged:
            code, result = self.call(body=body)
        logged.assert_called_once()
        self.assertEqual(code, 200, result)
        self.assertIsNone(result["work"])
        self.assertIn("交接已登记", result["work_error"])
        self.store.comment(self.ticket["id"], "alice", "来源随后改变")
        with patch.object(handoffs, "_source", side_effect=AssertionError("replay must not inspect new source")):
            code, replay = self.call(body=body)
        self.assertEqual(code, 200, replay)
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(self.store.one("SELECT COUNT(*) AS n FROM ticket_handoffs")["n"], 1)
        self.assertEqual(self.store.one("SELECT COUNT(*) AS n FROM ticket_handoff_events")["n"], 1)

    def test_deleted_user_cannot_use_old_signed_cookie_or_receive(self):
        self.action("send")
        login.del_user(self.P.data_dir, "bob")
        self.assertEqual(self.call("/api/handoffs?ticket=" + self.ticket["key"], user="bob")[0], 401)
        self.assertEqual(self.call("/api/workspace?view=incoming", user="", token=True, headers={"X-TMH-User": "bob"})[1]["total"], 0)
        self.assertEqual(self.action("withdraw", note="接收账号已停用")["next_actor"], "alice")
