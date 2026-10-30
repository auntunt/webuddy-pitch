"""Real tenant gateway/worker checks; all identities and records are synthetic."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from tests import test_tenant_gateway as gateway_fixture
from tmh.platform import delivery
from tmh.platform.store import Store


@unittest.skipUnless(os.name == "posix", "tenant gateway requires POSIX Unix sockets")
class CoordinationHTTPTests(unittest.TestCase):
    setUp = gateway_fixture.TenantGatewayTest.setUp
    change = gateway_fixture.TenantGatewayTest.change
    request = gateway_fixture.TenantGatewayTest.request
    token = gateway_fixture.TenantGatewayTest.token

    def call(self, path, body=None, user="alice", tenant=None, headers=None):
        tenant = tenant or self.a
        return self.request("POST" if body is not None else "GET", "/t/" + tenant + path,
                            user, body, token=self.token(user, tenant),
                            headers={"X-TMH": "1", **(headers or {})})

    def ok(self, path, body=None, **kw):
        status, _, value = self.call(path, body, **kw)
        self.assertEqual(status, 200, value)
        return value

    def meeting(self, **kw):
        return self.ok("/api/projects/SAME/meetings", {
            "title": "发布评审合成记录", "body": "背景保持完整。\n待办：核对异常恢复步骤\n完整原话\n" * 3,
            "occurred_on": "2026-10-23", "request_id": "meeting-new", **kw})

    def add_action(self, record):
        return self.ok("/api/projects/SAME/meetings/" + str(record["id"]), {
            "action": "add_action", "revision": record["revision"], "request_id": "action-new",
            "title": "核对恢复说明", "owner": "alice", "due_date": "2026-10-29",
            "deliverable": "完整恢复说明和实际检查记录", "criteria": "包含启动失败与数据保持两种情况",
            "source_start": 2, "source_end": 2, "note": "合成行动"})

    def store_for(self, tenant=None):
        row = self.reg.one("SELECT path FROM tenants WHERE id=?", (tenant or self.a,))
        st = Store(Path(row["path"]) / "platform.db")
        self.addCleanup(st.db.close)
        return st

    def test_meeting_to_ticket_is_complete_idempotent_and_never_runs(self):
        source = "讨论原文：<script>不是命令</script>\n" + "完整材料\n" * 700
        record = self.meeting(body=source)
        self.assertEqual(record["body"], source)
        saved = self.add_action(record)
        action = next(x for x in saved["actions"] if x["title"] == "核对恢复说明")
        body = {"action": "publish_action", "revision": saved["revision"],
                "request_id": "publish-once", "action_id": action["id"]}
        path = "/api/projects/SAME/meetings/" + str(record["id"])
        published = self.ok(path, body)
        replay = self.ok(path, body)
        self.assertTrue(replay["receipt"]["replayed"])
        item = next(x for x in published["actions"] if x["id"] == action["id"])
        ticket = self.ok("/api/tickets/" + item["ticket"]["key"])["ticket"]
        self.assertEqual(ticket["status"], "new")
        self.assertEqual(ticket["assignee"], "alice")
        source_url = "/t/" + self.a + "/#/meetings/" + str(record["id"]) + "/SAME"
        self.assertEqual(ticket["links"]["coordination"]["url"], source_url)
        self.assertIn(source_url, ticket["body"])
        self.assertEqual(self.request("GET", source_url.split("#", 1)[0], "alice")[0], 200)
        self.assertIn("包含启动失败与数据保持两种情况", ticket["body"])
        self.assertIn("2026-10-29", ticket["body"])
        self.assertEqual(self.ok(path)["body"], source)
        workspace = self.ok("/api/workspace?project=SAME&view=mine")
        projected = next(x for x in workspace["items"] if x["key"] == ticket["key"])
        self.assertEqual(projected["meeting_action"]["meeting_id"], record["id"])
        self.assertEqual(projected["meeting_action"]["due_date"], "2026-10-29")
        st = self.store_for()
        self.assertEqual(st.one("SELECT COUNT(*) n FROM tickets")["n"], 2)
        self.assertEqual(st.q("SELECT * FROM runs"), [])
        self.assertEqual(st.q("SELECT * FROM events WHERE kind IN ('accept','close','candidate_decision')"), [])

    def test_project_tenant_and_personal_session_are_not_payload_choices(self):
        record = self.meeting()
        mid = str(record["id"])
        self.assertEqual(self.call("/api/projects/PRIVATE/meetings/" + mid)[0], 403)
        self.assertEqual(self.call("/api/projects/PRIVATE/meetings/" + mid, user="owner")[0], 404)
        self.assertEqual(self.call("/api/projects/SAME/meetings/" + mid, user="bob", tenant=self.b)[0], 404)
        body = {"title": "假作者", "body": "完整正文", "request_id": "forged", "by": "owner"}
        self.assertEqual(self.call("/api/projects/SAME/meetings", body)[0], 400)
        body.pop("by")
        self.assertEqual(self.call("/api/projects/SAME/meetings", body,
                                   headers={"X-Webuddy-Agent": "synthetic-agent"})[0], 403)
        self.assertEqual(self.request("POST", "/t/" + self.a + "/api/projects/SAME/meetings", body=body,
                                      headers={"X-TMH": "1", "X-TMH-Token": "legacy", "X-TMH-User": "owner"})[0], 401)

    def test_meeting_http_pagination_is_explicit_and_rejects_ambiguous_values(self):
        first = self.meeting(request_id="pagination-one")
        second = self.meeting(title="另一个会议", request_id="pagination-two")
        page = self.ok("/api/projects/SAME/meetings?offset=0&limit=1")
        self.assertEqual(page["total"], 2)
        self.assertEqual([x["id"] for x in page["items"]], [second["id"]])
        page = self.ok("/api/projects/SAME/meetings?offset=1&limit=1")
        self.assertEqual([x["id"] for x in page["items"]], [first["id"]])
        self.assertEqual(self.call("/api/projects/SAME/meetings?limit=1&limit=2")[0], 400)
        self.assertEqual(self.call("/api/projects/SAME/meetings?unknown=1")[0], 400)

    def test_brief_tracks_real_content_versions_without_confirming_ticket(self):
        path = "/api/tickets/SAME-1/brief"
        initial = self.ok(path)
        body = {"revision": initial["revision"], "source_token": initial["source_token"],
                "request_id": "brief-1", "summary": "简短结论\n第二行完整保留", "decisions": "需要负责人决定范围",
                "next_step": "补齐验收记录", "owner": "alice", "due_date": ""}
        saved = self.ok(path, body)
        self.assertFalse(saved["current"]["stale"])
        self.assertEqual(saved["current"]["summary"], body["summary"])
        self.ok("/api/tickets/SAME-1", {"body": "修改后的完整需求\n" * 500})
        changed = self.ok(path)
        self.assertTrue(changed["current"]["stale"])
        self.assertEqual(self.call(path, dict(body, request_id="brief-stale", revision=changed["revision"]))[0], 409)
        fresh = self.ok(path, dict(body, request_id="brief-2", revision=changed["revision"], source_token=changed["source_token"]))
        self.assertEqual(len(fresh["history"]), 2)
        self.assertFalse(fresh["current"]["stale"])
        self.assertEqual(self.ok("/api/tickets/SAME-1")["ticket"]["status"], "new")

    def test_revocation_blocks_receipt_replay_and_readonly_cannot_save(self):
        record = self.meeting()
        self.change("member_set", tenant=self.a, user="alice", role="viewer")
        self.assertFalse(self.ok("/api/projects/SAME/meetings/" + str(record["id"]))["can_edit"])
        body = {"title": "不应创建", "body": "完整记录", "request_id": "denied"}
        self.assertEqual(self.call("/api/projects/SAME/meetings", body)[0], 403)
        self.assertEqual(self.call("/api/tickets/SAME-1/brief", {"request_id": "denied-brief"})[0], 403)
        self.change("project_revoke", tenant=self.a, user="alice", project_id=1)
        self.assertEqual(self.call("/api/projects/SAME/meetings/" + str(record["id"]))[0], 403)
        self.assertEqual(self.call("/api/projects/SAME/meetings", body)[0], 403)

    def test_disabled_executor_tenant_can_create_delivery_and_version_materials(self):
        meta = self.ok("/api/meta")
        self.assertFalse(meta["access"]["capabilities"]["execution"])
        body = {"action": "create", "request_id": "manual-delivery", "revision": 0,
                "project": "SAME", "type": "docs", "title": "合成交付计划", "goal": "保留全部需求与核对来源",
                "stages": ["requirements", "release"]}
        created = self.ok("/api/delivery-content", body)
        repeated = self.ok("/api/delivery-content", body)
        self.assertTrue(repeated["receipt"]["replayed"])
        self.assertEqual(repeated["delivery"]["id"], created["delivery"]["id"])
        did = created["delivery"]["id"]
        path = "/api/deliveries/" + did + "/content"
        source = self.ok(path)
        text = "原始完整材料\n<script>仅作为正文</script>\n" * 700
        save = {"action": "save_artifact", "request_id": "manual-material", "revision": source["revision"],
                "source_token": source["source_token"], "stage": "requirements", "title": "需求说明", "body": text}
        saved = self.ok(path, save)
        self.assertEqual(saved["stages"][0]["artifact"]["body"], text)
        self.assertEqual(self.ok(path, save)["stages"][0]["version"], 1)
        coverage = "/api/deliveries/" + did + "/coverage"
        head = self.ok(coverage)
        row = self.ok(coverage, {"action": "add", "revision": head["revision"], "request_id": "content-coverage",
                               "title": "需求全覆盖", "requirement": "完整原文可追溯", "required": True,
                               "artifact_id": saved["stages"][0]["artifact"]["id"], "note": ""})
        item = row["items"][0]
        checked = self.ok(coverage, {"action": "verify", "revision": row["revision"], "request_id": "content-check",
                                    "item_id": item["id"], "source_token": item["source_token"], "note": "已阅读完整材料"})
        self.assertEqual(checked["items"][0]["status"], "checked")
        changed = self.ok(path, dict(save, request_id="manual-material-v2", revision=saved["revision"],
                                     source_token=saved["source_token"], body=text+"新增说明"))
        self.assertEqual(changed["stages"][0]["version"], 2)
        self.assertEqual(changed["stages"][0]["history"][0]["body"], text)
        self.assertEqual(self.ok(coverage)["items"][0]["status"], "stale")
        self.assertEqual(self.call(path, dict(save, request_id="stale-manual-material"))[0], 409)
        self.assertEqual(self.call("/api/deliveries/"+did, {"action": "start", "stage": "requirements"})[0], 403)
        self.assertEqual(self.call(path, dict(save, by="owner"))[0], 400)
        self.assertEqual(self.call(path, user="bob", tenant=self.b)[0], 404)
        st = self.store_for()
        self.assertEqual(st.q("SELECT * FROM runs"), [])
        self.assertEqual(st.q("SELECT * FROM delivery_reviews"), [])
        self.assertEqual(st.one("SELECT COUNT(*) n FROM delivery_items")["n"], 1)
        self.assertEqual(st.one("SELECT COUNT(*) n FROM tickets")["n"], 2)
        self.change("member_set", tenant=self.a, user="alice", role="viewer")
        self.assertFalse(self.ok(path)["can_edit"])
        self.assertEqual(self.call(path, save)[0], 403)
        self.assertEqual(self.call("/api/delivery-content", body)[0], 403)

    def test_coverage_binds_exact_material_and_cannot_cross_delivery(self):
        st = self.store_for()
        delivery._db(SimpleNamespace(store=st))
        did, other = "a" * 12, "b" * 12
        for ident in (did, other):
            st.x("INSERT INTO delivery_items(id,project_id,type,title,goal,stages,created,updated,author) VALUES(?,?,?,?,?,?,?,?,?)",
                 (ident, 1, "docs", "合成交付", "核对材料", '["requirements"]', "2026-10-23", "2026-10-23", "alice"))
        def material(ident, version):
            return st.x("INSERT INTO delivery_artifacts(delivery_id,stage,version,title,body,created,author,inputs) VALUES(?,?,?,?,?,?,?,?)",
                        (ident, "requirements", version, "验收说明", "完整要求\n" * 500, "2026-10-23", "alice", "{}"))
        aid = material(did, 1)
        wrong = material(other, 1)
        path = "/api/deliveries/" + did + "/coverage"
        first = self.ok(path)
        body = {"action": "add", "revision": first["revision"], "request_id": "coverage-add",
                "title": "需求与验收", "requirement": "包含所有验收条件", "required": True,
                "artifact_id": wrong, "note": "人工材料登记"}
        self.assertIn(self.call(path, body)[0], (400, 404))
        saved = self.ok(path, dict(body, artifact_id=aid))
        item = saved["items"][0]
        checked = self.ok(path, {"action": "verify", "revision": saved["revision"], "request_id": "coverage-check",
                                  "item_id": item["id"], "source_token": item["source_token"], "note": "已逐条阅读当前材料"})
        self.assertEqual(checked["items"][0]["status"], "checked")
        material(did, 2)
        changed = self.ok(path)
        self.assertEqual(changed["items"][0]["status"], "stale")
        self.assertEqual(st.q("SELECT * FROM delivery_reviews"), [])
        self.assertEqual(st.q("SELECT * FROM runs"), [])
        self.change("member_set", tenant=self.a, user="alice", role="viewer")
        self.assertEqual(self.call(path, {"action": "verify", "revision": changed["revision"], "request_id": "readonly-check",
                                         "item_id": item["id"], "source_token": item["source_token"], "note": "不可写"})[0], 403)
