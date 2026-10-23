"""Real SQLite transactions and synthetic people; no model, service or signoff."""
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import coordination as C, login
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.sqlite_snapshot import dump_store


class Context:
    tenant_id = "customer"

    def __init__(self):
        self.people = {
            "alice": {"role": "member", "project_grants": {"ORG": "manager"}},
            "bob": {"role": "member", "project_grants": {"ORG": "contributor"}},
            "reader": {"role": "viewer", "project_grants": {"ORG": "manager"}},
            "outsider": {"role": "member", "project_grants": {"OTHER": "manager"}},
            "agent:spoof": {"role": "admin", "project_grants": {}},
        }

    def current_actor(self, actor):
        value = self.people.get(actor)
        return dict(copy.deepcopy(value), authz_revision=1) if value else None

    def directory(self):
        return copy.deepcopy(self.people)


class CoordinationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-coordination-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.data = self.folder / "data"
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        C.schema(self.store)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.people = {name: {"pw": "synthetic-not-for-login"} for name in
                       ("alice", "bob", "reader", "outsider", "agent", "system", "agent:spoof")}
        login._save_users(self.data, self.people)
        (self.folder / "repo").mkdir()
        (self.folder / "other").mkdir()
        self.project = self.store.add_project("ORG", "合成项目", str(self.folder / "repo"))
        self.other = self.store.add_project("OTHER", "另一个项目", str(self.folder / "other"))
        self.ticket = self.store.create_ticket(self.project["id"], "已有需求", "alice", body="原始说明\n完整保留", assignee="alice")
        self.count = 0

    def rid(self):
        self.count += 1
        return "coordination-%s" % self.count

    def create(self, original="会议原文\nTODO: 修改导出格式\n讨论：不自动当作行动。", **kw):
        body = dict(title="交付会议", body=original, occurred_on="2026-10-23", request_id=self.rid())
        body.update(kw)
        return C.create_meeting(self.P, "ORG", body, "alice")

    def action_body(self, view, operation, **kw):
        body = {"action": operation, "revision": view["revision"], "request_id": self.rid()}
        if operation != "add_action":
            body["action_id"] = view["actions"][0]["id"]
        body.update(kw)
        return body

    def action(self, view, operation, **kw):
        return C.meeting_action(self.P, "ORG", view["id"], self.action_body(view, operation, **kw), "alice")

    def ready(self):
        view = self.create()
        return self.action(view, "edit_action", owner="bob", deliverable="可下载的完整导出文件", criteria="验证包含全部原始行和列，不丢数据", note="负责人已人工讨论")

    def brief_body(self, **kw):
        view = C.brief(self.P, self.ticket["key"], "alice")
        body = dict(source_token=view["source_token"], revision=view["revision"], request_id=self.rid(),
                    summary="完整工作简报", decisions="保留原始需求", next_step="准备测试资料", owner="bob", due_date="")
        body.update(kw)
        return body

    def assert_api(self, code, fn):
        before = dump_store(self.store)
        with self.assertRaises(ApiError) as err:
            fn()
        self.assertEqual(err.exception.code, code)
        self.assertEqual(dump_store(self.store), before)

    def second(self):
        store = Store(self.store.path)
        self.addCleanup(store.db.close)
        C.schema(store)
        return SimpleNamespace(store=store, data_dir=self.data, **({"tenant_context": self.P.tenant_context} if hasattr(self.P, "tenant_context") else {}))

    def race(self, fn):
        second = self.second()
        barrier = threading.Barrier(2)
        def run(P):
            barrier.wait(timeout=5)
            try:
                return ("ok", fn(P))
            except ApiError as exc:
                return ("error", exc.code)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, P) for P in (self.P, second)]
            return [future.result(timeout=10) for future in futures]

    def test_full_original_and_only_explicit_candidates_no_hidden_limit(self):
        original = "原始会议正文 \r\n\t讨论负责人日期都不猜。\r\n" + "完整长段落\t \r\n" * 3000
        original += "\r\n".join("TODO: 待核对事项 %s" % i for i in range(501))
        original += "\r\n[x] 已完成不提取\r\n- [ ] 明确未完成项\r\n待办：核对结果\r\n最后原文空格  "
        view = self.create(original)
        self.assertEqual(view["body"], original)
        self.assertEqual(view["meeting"]["body"], original)
        self.assertEqual(view["source_hash"], hashlib.sha256(original.encode()).hexdigest())
        self.assertEqual(view["meeting"]["extraction"]["count"], 503)
        self.assertEqual(len(view["actions"]), 503)
        for action in view["actions"]:
            self.assertEqual(action["status"], "draft")
            self.assertEqual((action["owner"], action["due_date"], action["criteria"], action["deliverable"]), ("", "", "", ""))
            self.assertIn(action["source_quote"], original)
        self.assertEqual(C.meeting(self.P, "ORG", view["id"], "alice")["body"], original)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM tickets")["n"], 1)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM runs")["n"], 0)

    def test_manual_actions_history_withdraw_and_immutable_original(self):
        view = self.create("讨论全文\n第二行完整\n")
        self.assertEqual(view["actions"], [])
        view = self.action(view, "add_action", title="手动遗漏项", source_start=1, source_end=2, note="原始说明\n" * 200)
        first = view["actions"][0]
        self.assertEqual(first["source_quote"], "讨论全文\n第二行完整\n")
        view = self.action(view, "edit_action", title="修订后标题", deliverable="完整交付物")
        self.assertEqual(view["actions"][0]["history"][0]["snapshot"]["title"], "手动遗漏项")
        view = self.action(view, "withdraw_action", note="重复事项，保留记录")
        self.assertEqual(view["actions"][0]["status"], "withdrawn")
        self.assertEqual(view["actions"][0]["withdraw_reason"], "重复事项，保留记录")
        self.assertEqual(len(view["actions"][0]["history"]), 3)
        self.assertEqual(view["body"], "讨论全文\n第二行完整\n")
        self.assert_api(409, lambda: self.action(view, "publish_action"))
        body = self.action_body(view, "add_action", body="覆盖会议原文")
        self.assert_api(400, lambda: C.meeting_action(self.P, "ORG", view["id"], body, "alice"))

    def test_source_ranges_validate_actual_text_and_cannot_forge_quote(self):
        view = self.create("甲\r\n乙\r\n")
        for values in ({"source_start": 0, "source_end": 1}, {"source_start": 1, "source_end": 3},
                       {"source_start": 2, "source_end": 1}, {"source_start": True, "source_end": 1},
                       {"source_start": 1}, {"source_quote": "伪造来源"}):
            with self.subTest(values=values):
                self.assert_api(400, lambda: self.action(view, "add_action", **values))
        result = self.action(view, "add_action", source_start=2, source_end=2)
        self.assertEqual(result["actions"][0]["source_quote"], "乙\r\n")

    def test_publication_creates_one_new_ticket_atomically_without_automation(self):
        view = self.ready()
        request = self.action_body(view, "publish_action")
        self.store.on_create.append(lambda *_: self.fail("must not launch on_create"))
        with patch.object(self.store, "create_ticket", side_effect=AssertionError("must not use implicit commits")), \
             patch.object(self.store, "x", side_effect=AssertionError("must not use implicit commits")), \
             patch.object(self.store, "create_run", side_effect=AssertionError("must not launch agents")):
            published = C.meeting_action(self.P, "ORG", view["id"], request, "alice")
        action = published["actions"][0]
        self.assertEqual(action["status"], "published")
        ticket = self.store.ticket(action["ticket"]["key"])
        self.assertEqual(ticket["status"], "new")
        self.assertEqual(ticket["assignee"], "bob")
        self.assertEqual(ticket["reporter"], "alice")
        self.assertIn(action["deliverable"], ticket["body"])
        self.assertIn(action["criteria"], ticket["body"])
        self.assertIn("期限：未约定", ticket["body"])
        self.assertIn("/api/projects/ORG/meetings/%s" % view["id"], ticket["body"])
        self.assertEqual(ticket["links"]["coordination"]["source_start"], 2)
        events = self.store.q("SELECT * FROM events WHERE ticket_id=?", (ticket["id"],))
        self.assertEqual([event["kind"] for event in events], ["created"])
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM runs")["n"], 0)
        replay = C.meeting_action(self.P, "ORG", view["id"], request, "alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(replay["actions"], published["actions"])
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM tickets")["n"], 2)
        for operation in ("edit_action", "withdraw_action", "publish_action"):
            self.assert_api(409, lambda: self.action(published, operation, **({"note": "仍不可撤回"} if operation == "withdraw_action" else {})))
        self.store.x("UPDATE tickets SET status='closed',assignee='alice' WHERE id=?", (ticket["id"],))
        fresh = C.meeting(self.P, "ORG", view["id"], "alice")
        self.assertEqual(fresh["actions"][0]["ticket"]["status"], "closed")
        self.assertEqual(fresh["actions"][0]["ticket"]["assignee"], "alice")
        projection = C.ticket_action(self.P, self.store.ticket(ticket["id"]))
        self.assertEqual(projection["meeting_id"], view["id"])
        self.assertEqual(projection["due_date"], "")
        self.assertNotIn("owner", projection)
        self.assertIsNone(C.ticket_action(self.P, dict(ticket, project_id=self.other["id"])))

    def test_publish_requires_complete_current_owner_and_development_project(self):
        view = self.create()
        self.assert_api(400, lambda: self.action(view, "publish_action"))
        view = self.action(view, "edit_action", owner="bob", deliverable="交付", criteria="验收")
        login._save_users(self.data, {name: value for name, value in self.people.items() if name != "bob"})
        self.assert_api(400, lambda: self.action(view, "publish_action"))
        login._save_users(self.data, self.people)
        self.store.x("UPDATE project_profiles SET workflow='reference' WHERE project_id=?", (self.project["id"],))
        self.assert_api(409, lambda: self.action(view, "publish_action"))
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM tickets")["n"], 1)

    def test_failure_rolls_back_published_ticket_event_link_revision_and_receipt(self):
        view = self.ready()
        before = dump_store(self.store)
        request = self.action_body(view, "publish_action")
        with patch.object(C, "_save_receipt", side_effect=RuntimeError("receipt disk failure")):
            with self.assertRaisesRegex(RuntimeError, "disk failure"):
                C.meeting_action(self.P, "ORG", view["id"], request, "alice")
        self.assertEqual(dump_store(self.store), before)
        self.assertFalse(self.store.db.in_transaction)
        result = C.meeting_action(self.P, "ORG", view["id"], request, "alice")
        self.assertEqual(result["actions"][0]["ticket"]["key"], "ORG-2")

    def test_create_replay_and_cross_resource_request_ids(self):
        body = dict(title="完整标题", body="TODO: 来源", request_id="fixed-create")
        first = C.create_meeting(self.P, "ORG", body, "alice")
        replay = C.create_meeting(self.P, "ORG", body, "alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(first["id"], replay["id"])
        self.assert_api(409, lambda: C.create_meeting(self.P, "ORG", dict(body, body="不同原文"), "alice"))
        self.assert_api(409, lambda: C.create_meeting(self.P, "OTHER", body, "alice"))
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM coordination_meetings")["n"], 1)

    def test_concurrent_publish_one_winner_and_single_ticket(self):
        view = self.ready()
        requests = {"a": self.action_body(view, "publish_action"), "b": self.action_body(view, "publish_action")}
        result = self.race(lambda P: C.meeting_action(P, "ORG", view["id"], requests["a" if P is self.P else "b"], "alice"))
        self.assertEqual(sorted(row[0] for row in result), ["error", "ok"])
        self.assertEqual(next(row[1] for row in result if row[0] == "error"), 409)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM tickets")["n"], 2)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM events WHERE kind='created'")["n"], 2)

    def test_concurrent_identical_publish_returns_original_receipt(self):
        view = self.ready()
        request = self.action_body(view, "publish_action")
        result = self.race(lambda P: C.meeting_action(P, "ORG", view["id"], request, "alice"))
        self.assertEqual([row[0] for row in result], ["ok", "ok"])
        self.assertEqual(sorted(row[1]["receipt"]["replayed"] for row in result), [False, True])
        self.assertEqual(result[0][1]["actions"], result[1][1]["actions"])
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM tickets")["n"], 2)

    def test_meeting_cas_covers_different_actions(self):
        view = self.create("TODO: 一\nTODO: 二")
        first = self.action_body(view, "edit_action", title="第一人改动")
        second = self.action_body(view, "edit_action", action_id=view["actions"][1]["id"], title="另一人改动")
        C.meeting_action(self.P, "ORG", view["id"], first, "alice")
        self.assert_api(409, lambda: C.meeting_action(self.P, "ORG", view["id"], second, "bob"))

    def test_personal_identity_and_payload_spoofing_fail_closed(self):
        view = self.create()
        for actor in ("", None, "missing", "agent", "system", "agent:spoof"):
            with self.subTest(actor=actor):
                self.assert_api(403, lambda: C.meeting(self.P, "ORG", view["id"], actor))
                self.assert_api(403, lambda: C.create_meeting(self.P, "ORG", {"title": "会议", "body": "全文", "request_id": self.rid()}, actor))
                self.assert_api(403, lambda: C.save_brief(self.P, self.ticket["key"], self.brief_body(), actor))
        self.assert_api(400, lambda: C.create_meeting(self.P, "ORG", {"title": "会议", "body": "全文", "request_id": self.rid(), "actor": "alice"}, "bob"))
        del self.people["alice"]
        login._save_users(self.data, self.people)
        self.assert_api(403, lambda: C.meeting(self.P, "ORG", view["id"], "alice"))

    def test_cross_project_meeting_and_action_ids_do_not_escape_scope(self):
        view = self.create()
        self.assert_api(404, lambda: C.meeting(self.P, "OTHER", view["id"], "alice"))
        self.assert_api(404, lambda: C.meeting_action(self.P, "OTHER", view["id"], self.action_body(view, "edit_action"), "alice"))
        another = self.create()
        self.assert_api(404, lambda: self.action(another, "edit_action", action_id=view["actions"][0]["id"], title="越界"))

    def test_tenant_project_permissions_directory_and_live_revocation(self):
        self.P.tenant_context = Context()
        view = self.create()
        read = C.meeting(self.P, "ORG", view["id"], "reader")
        self.assertFalse(read["can_edit"])
        self.assertEqual(read["members"], [{"id": name, "name": name} for name in ("alice", "bob")])
        self.assert_api(403, lambda: C.meeting(self.P, "ORG", view["id"], "outsider"))
        self.assert_api(403, lambda: C.meeting_action(self.P, "ORG", view["id"], self.action_body(view, "edit_action", title="越权"), "reader"))
        self.assert_api(400, lambda: self.action(view, "edit_action", owner="reader"))
        self.assert_api(400, lambda: self.action(view, "edit_action", owner="outsider"))
        request = self.action_body(view, "edit_action", title="个人变更")
        C.meeting_action(self.P, "ORG", view["id"], request, "alice")
        self.P.tenant_context.people["alice"]["project_grants"].clear()
        self.assert_api(403, lambda: C.meeting_action(self.P, "ORG", view["id"], request, "alice"))
        self.assert_api(403, lambda: C.brief(self.P, self.ticket["key"], "alice"))

    def test_brief_full_versions_do_not_change_task_or_acceptance(self):
        original = self.store.ticket(self.ticket["id"])
        first_body = self.brief_body(summary="完整简报\r\n" * 500, decisions="完整决定\n" * 300, next_step="保持原说明\n" * 200)
        first = C.save_brief(self.P, self.ticket["key"], first_body, "alice")
        self.assertFalse(first["current"]["stale"])
        self.assertEqual(first["current"]["summary"], first_body["summary"])
        self.assertEqual(first["current"]["decisions"], first_body["decisions"])
        second = C.save_brief(self.P, self.ticket["key"], self.brief_body(summary="第二版本"), "alice")
        self.assertEqual(second["revision"], 2)
        self.assertEqual(len(second["history"]), 2)
        self.assertEqual(second["history"][1]["summary"], first_body["summary"])
        self.assertEqual(second["source"]["ticket"]["body"], original["body"])
        self.assertEqual(self.store.ticket(self.ticket["id"]), original)
        self.assertEqual([row["kind"] for row in self.store.q("SELECT kind FROM events ORDER BY id")], ["created", "coordination_brief", "coordination_brief"])
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM runs")["n"], 0)

    def test_brief_source_changes_reject_old_draft_and_mark_history_stale(self):
        first = C.save_brief(self.P, self.ticket["key"], self.brief_body(), "alice")
        stale_body = self.brief_body(summary="基于旧来源的稿件")
        self.store.x("UPDATE tickets SET body=?,assignee=?,links=? WHERE id=?", ("新原文完整", "bob", json.dumps({"docs": "另一个文档"}), self.ticket["id"]))
        read = C.brief(self.P, self.ticket["key"], "alice")
        self.assertTrue(read["current"]["stale"])
        self.assertEqual(read["current"]["source"], first["source"])
        self.assertNotEqual(read["source_token"], first["source_token"])
        self.assert_api(409, lambda: C.save_brief(self.P, self.ticket["key"], stale_body, "alice"))
        fresh = C.save_brief(self.P, self.ticket["key"], self.brief_body(), "alice")
        self.assertFalse(fresh["current"]["stale"])
        self.assertTrue(fresh["history"][1]["stale"])

    def test_actual_handoff_receipt_stales_brief_and_preserves_old_source(self):
        from tmh.platform import handoffs
        initial = handoffs.read(self.P, self.ticket["key"], "alice")
        sent = handoffs.dispatch_action(self.P, {
            "ticket": self.ticket["key"], "action": "send", "revision": initial["revision"],
            "request_id": "handoff-send", "note": "真实协作事件的合成夹具", "receiver": "bob",
            "stage": "testing", "materials": "完整交接材料\n下一步准备测试",
            "source_token": initial["source_token"],
        }, "alice")
        first = C.save_brief(self.P, self.ticket["key"], self.brief_body(), "alice")
        self.assertEqual(first["source"]["handoff"]["current"]["status"], "waiting")
        self.assertEqual(first["source"]["handoff"]["current"]["materials"], "完整交接材料\n下一步准备测试")
        old_draft = self.brief_body(summary="仍以待接收状态为依据")
        handoffs.dispatch_action(self.P, {
            "ticket": self.ticket["key"], "action": "receive", "revision": sent["revision"],
            "request_id": "handoff-receive", "handoff_id": sent["current"]["id"], "note": "仅接收协作材料",
        }, "bob")
        current = C.brief(self.P, self.ticket["key"], "alice")
        self.assertTrue(current["current"]["stale"])
        self.assertEqual(current["source"]["handoff"]["current"]["status"], "received")
        self.assertEqual(current["current"]["source"]["handoff"]["current"]["status"], "waiting")
        self.assert_api(409, lambda: C.save_brief(self.P, self.ticket["key"], old_draft, "alice"))
        saved = C.save_brief(self.P, self.ticket["key"], self.brief_body(summary="按当前接收情况更新"), "alice")
        self.assertFalse(saved["current"]["stale"])
        self.assertTrue(saved["history"][1]["stale"])
        self.assertEqual(self.store.ticket(self.ticket["id"])["status"], "new")

    def test_brief_source_binds_assignment_discussion_project_and_meeting_relation(self):
        self.store.x("CREATE TABLE ticket_team(ticket_id INTEGER PRIMARY KEY,reviewer TEXT,revision INTEGER,updated TEXT,updated_by TEXT)")
        self.store.x("INSERT INTO ticket_team VALUES(?,?,?,?,?)", (self.ticket["id"], "bob", 0, "fixture", "alice"))
        old = C.brief(self.P, self.ticket["key"], "alice")["source_token"]
        for sql, args in (("UPDATE ticket_team SET reviewer='reader' WHERE ticket_id=?", (self.ticket["id"],)),
                          ("UPDATE projects SET root=? WHERE id=?", (str(self.folder / "moved"), self.project["id"])),
                          ("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)", (self.ticket["id"], "2026-10-23 12:00:00", "bob", "comment", "新要求", "{}")),
                          ("UPDATE tickets SET title='新标题' WHERE id=?", (self.ticket["id"],))):
            self.store.x(sql, args)
            fresh = C.brief(self.P, self.ticket["key"], "alice")["source_token"]
            self.assertNotEqual(fresh, old)
            old = fresh
        view = self.action(self.ready(), "publish_action")
        ticket = view["actions"][0]["ticket"]
        source = C.brief(self.P, ticket["key"], "alice")["source"]
        self.assertEqual(source["meeting_origin"]["meeting_id"], view["id"])
        self.assertEqual(source["meeting_origin"]["source_hash"], view["source_hash"])

    def test_brief_replay_is_payload_exact_and_does_not_need_new_source(self):
        body = self.brief_body()
        first = C.save_brief(self.P, self.ticket["key"], body, "alice")
        self.store.x("UPDATE tickets SET title='来源变化' WHERE id=?", (self.ticket["id"],))
        replay = C.save_brief(self.P, self.ticket["key"], body, "alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(replay["current"], first["current"])
        self.assert_api(409, lambda: C.save_brief(self.P, self.ticket["key"], dict(body, summary="改变内容"), "alice"))
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM coordination_briefs")["n"], 1)

    def test_brief_rollback_and_concurrent_cas(self):
        body = self.brief_body()
        before = dump_store(self.store)
        with patch.object(C, "_save_receipt", side_effect=RuntimeError("receipt failed")):
            with self.assertRaises(RuntimeError):
                C.save_brief(self.P, self.ticket["key"], body, "alice")
        self.assertEqual(dump_store(self.store), before)
        other = dict(body, request_id=self.rid(), summary="其他人简报")
        result = self.race(lambda P: C.save_brief(P, self.ticket["key"], body if P is self.P else other, "alice"))
        self.assertEqual(sorted(row[0] for row in result), ["error", "ok"])
        self.assertEqual(next(row[1] for row in result if row[0] == "error"), 409)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM coordination_briefs")["n"], 1)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM events WHERE kind='coordination_brief'")["n"], 1)

    def test_dates_and_revision_validation_without_silent_normalization(self):
        for date_value in ("20261023", "2026-02-30", "明天", None, 123):
            self.assert_api(400, lambda: self.create(occurred_on=date_value))
        view = self.create()
        for revision in (True, -1, "1", None):
            self.assert_api(400, lambda: self.action(view, "edit_action", revision=revision))
        for due in ("2026-10-32", "20261023", None):
            self.assert_api(400, lambda: self.action(view, "edit_action", due_date=due))
        view = self.action(view, "edit_action", due_date="2026-12-31")
        self.assertEqual(view["actions"][0]["due_date"], "2026-12-31")

    def test_list_pagination_is_explicit_and_project_scoped(self):
        ids = [self.create()["id"] for _ in range(3)]
        C.create_meeting(self.P, "OTHER", {"title": "另一项目", "body": "全文", "request_id": self.rid()}, "alice")
        page = C.meetings(self.P, "ORG", {"offset": "1", "limit": "1"}, "alice")
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["offset"], 1)
        self.assertEqual(page["limit"], 1)
        self.assertEqual([row["id"] for row in page["items"]], [ids[1]])
        self.assertEqual(page["items"][0]["action_counts"], {"draft": 1, "withdrawn": 0, "published": 0})
        self.assertNotIn("body", page["items"][0])
        self.assert_api(400, lambda: C.meetings(self.P, "ORG", {"limit": 101}, "alice"))
        self.assert_api(400, lambda: C.meetings(self.P, "ORG", {"offset": -1}, "alice"))

    def test_schema_atomic_failure_nested_guard_and_legacy_data_preservation(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        store = SimpleNamespace(db=db, lock=threading.RLock())
        db.execute("CREATE TABLE legacy(value TEXT)")
        db.execute("INSERT INTO legacy VALUES('完整历史')")
        db.commit()
        with patch.object(C, "DDL", C.DDL + ("THIS IS INVALID SQL",)):
            with self.assertRaises(sqlite3.Error):
                C.schema(store)
        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("legacy",)])
        self.assertEqual(db.execute("SELECT value FROM legacy").fetchall(), [("完整历史",)])
        db.execute("INSERT INTO legacy VALUES('未提交历史')")
        with self.assertRaisesRegex(RuntimeError, "cannot nest"):
            C.schema(store)
        self.assertTrue(db.in_transaction)
        db.rollback()
        C.schema(store)
        first = tuple(db.iterdump())
        C.schema(store)
        self.assertEqual(tuple(db.iterdump()), first)
        self.assertEqual(db.execute("SELECT value FROM legacy").fetchall(), [("完整历史",)])
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual({name for name in names if name.startswith("coordination_")},
                         {"coordination_meetings", "coordination_actions", "coordination_action_events", "coordination_briefs", "coordination_requests"})

    def test_create_failure_rolls_back_original_candidates_and_request(self):
        original = "待办：第一条\nTODO: 第二条\n完整未截断原文"
        before = dump_store(self.store)
        with patch.object(C, "_action_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.create(original)
        self.assertEqual(dump_store(self.store), before)
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual(self.create(original)["body"], original)

    def test_concurrent_identical_create_and_brief_are_idempotent(self):
        body = dict(title="唯一会议", body="TODO: 唯一事项", request_id=self.rid())
        results = self.race(lambda P: C.create_meeting(P, "ORG", body, "alice"))
        self.assertEqual([row[0] for row in results], ["ok", "ok"])
        self.assertEqual(sorted(row[1]["receipt"]["replayed"] for row in results), [False, True])
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM coordination_meetings")["n"], 1)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM coordination_actions")["n"], 1)
        body = self.brief_body()
        results = self.race(lambda P: C.save_brief(P, self.ticket["key"], body, "alice"))
        self.assertEqual([row[0] for row in results], ["ok", "ok"])
        self.assertEqual(sorted(row[1]["receipt"]["replayed"] for row in results), [False, True])
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM coordination_briefs")["n"], 1)

    def test_actor_and_owner_are_rechecked_after_entering_write_transaction(self):
        self.P.tenant_context = Context()
        view = self.ready()
        request = self.action_body(view, "publish_action")
        # Simulate authorization changing after the caller prepared its body.
        self.P.tenant_context.people["bob"]["project_grants"] = {"OTHER": "manager"}
        self.assert_api(400, lambda: C.meeting_action(self.P, "ORG", view["id"], request, "alice"))
        self.P.tenant_context.people["bob"]["project_grants"] = {"ORG": "contributor"}
        body = self.brief_body()
        self.P.tenant_context.people["alice"]["project_grants"] = {"OTHER": "manager"}
        self.assert_api(403, lambda: C.save_brief(self.P, self.ticket["key"], body, "alice"))
        self.P.tenant_context.people["alice"]["project_grants"] = {"ORG": "manager"}
        self.P.tenant_context.people["bob"]["project_grants"] = {"OTHER": "manager"}
        self.assert_api(400, lambda: C.save_brief(self.P, self.ticket["key"], body, "alice"))

    def test_disabled_legacy_account_and_brief_project_viewer_are_read_only(self):
        view = self.create()
        self.people["alice"]["disabled"] = True
        login._save_users(self.data, self.people)
        self.assert_api(403, lambda: C.meeting(self.P, "ORG", view["id"], "alice"))
        self.P.tenant_context = Context()
        read = C.brief(self.P, self.ticket["key"], "reader")
        self.assertFalse(read["can_edit"])
        body = dict(source_token=read["source_token"], revision=read["revision"], request_id=self.rid(), summary="只读账号写入")
        self.assert_api(403, lambda: C.save_brief(self.P, self.ticket["key"], body, "reader"))
        self.assert_api(403, lambda: C.brief(self.P, self.ticket["key"], "outsider"))

    def test_brief_source_is_read_only_database_snapshot_not_technical_verification(self):
        self.P.tenant_context = Context()
        from tmh.platform import agent_api, candidates
        before = dump_store(self.store)
        with patch.object(agent_api, "_requirement", side_effect=AssertionError("file-based requirements forbidden")), \
             patch.object(candidates, "view", side_effect=AssertionError("Git/preview inspection forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("no child process")):
            read = C.brief(self.P, self.ticket["key"], "alice")
        self.assertEqual(dump_store(self.store), before)
        self.assertEqual(read["source"]["ticket"]["body"], "原始说明\n完整保留")
        self.assertNotIn("verified", read)
        self.assertNotIn("accepted", read)

    def test_brief_on_closed_task_is_annotation_not_reopen_or_acceptance(self):
        self.store.x("UPDATE tickets SET status='closed' WHERE id=?", (self.ticket["id"],))
        original = self.store.ticket(self.ticket["id"])
        result = C.save_brief(self.P, self.ticket["key"], self.brief_body(summary="结束后的复盘说明"), "alice")
        self.assertEqual(result["ticket"]["status"], "closed")
        self.assertEqual(self.store.ticket(self.ticket["id"]), original)
        self.assertEqual(self.store.one("SELECT COUNT(*) n FROM events WHERE kind IN ('accept','confirm','close','status')")["n"], 0)

    def test_oversized_numeric_identifiers_fail_as_validation_not_server_error(self):
        view = self.create()
        for value in (2 ** 63, "9" * 5000, False, 0):
            self.assert_api(400, lambda: C.meeting(self.P, "ORG", value, "alice"))
            self.assert_api(400, lambda: self.action(view, "edit_action", action_id=value))
        for value in (2 ** 63, "9" * 5000):
            self.assert_api(400, lambda: C.meetings(self.P, "ORG", {"offset": value}, "alice"))
        self.assert_api(400, lambda: C.brief(self.P, 2 ** 63, "alice"))


if __name__ == "__main__":
    unittest.main()
