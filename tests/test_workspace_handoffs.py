"""Organization workspace uses actual rows and explicit handoff events."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import handoffs, login, team, workspace
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class WorkspaceHandoffsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-workspace-handoffs-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.data = self.root / "data"
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        login._save_users(self.data, {n: {"pw": "synthetic-not-login"} for n in ("alice", "bob", "charlie")})
        self.project = self.store.add_project("FLOW", "Synthetic project", str(self.repo))
        team.schema(self.P)
        self.seq = 0

    def ticket(self, title="真实工单", assignee="alice", **kw):
        return self.store.create_ticket(self.project["id"], title, "alice", assignee=assignee, **kw)

    def action(self, t, action="send", user="alice", stage="testing", **kw):
        view = handoffs.read(self.P, t["key"], user)
        self.seq += 1
        body = {"action": action, "ticket": t["key"], "revision": view["revision"], "request_id": "workspace-%s" % self.seq, "note": "合成协作记录"}
        if action == "send":
            body.update(receiver="bob", stage=stage, materials="完整测试材料", source_token=view["source_token"])
        else:
            body["handoff_id"] = view["current"]["id"]
        body.update(kw)
        return handoffs.dispatch_action(self.P, body, user)

    def read(self, user="alice", **query):
        return workspace.read(self.P, query, user)

    def test_over_500_tickets_are_counted_before_pagination_and_stage_filter(self):
        rows = [self.ticket("工单 %s" % i) for i in range(503)]
        for t, stage in zip(rows, handoffs.STAGES):
            self.action(t, stage=stage)
        first = self.read(view="team", limit="2")
        self.assertEqual(first["total"], 503)
        self.assertEqual(len(first["items"]), 2)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["counts"]["team"], 503)
        self.assertEqual(first["stage_counts"], {**dict.fromkeys(handoffs.STAGES, 1), "unrecorded": 498})
        selected = self.read(view="team", stage="testing", limit="2")
        self.assertEqual(selected["total"], 1)
        self.assertEqual(selected["items"][0]["key"], rows[2]["key"])
        self.assertEqual(selected["stage_counts"], first["stage_counts"])
        last = self.read(view="team", offset="502", limit="2")
        self.assertEqual(last["total"], 503)
        self.assertEqual(len(last["items"]), 1)
        self.assertEqual(last["items"][0]["key"], rows[0]["key"])
        self.assertFalse(last["has_more"])

    def test_incoming_distinguishes_blocked_waiting_from_blocked_received(self):
        waiting, blocked_waiting, blocked_received = [self.ticket(str(i)) for i in range(3)]
        self.action(waiting)
        self.action(blocked_waiting)
        self.action(blocked_waiting, "block", "bob", note="还未接收，缺少环境")
        self.action(blocked_received)
        self.action(blocked_received, "receive", "bob")
        self.action(blocked_received, "block", "bob", note="已接手，外部依赖阻塞")
        incoming = self.read("bob", view="incoming")
        self.assertEqual(incoming["incoming_count"], 2)
        self.assertEqual(incoming["total"], 2)
        self.assertEqual({t["key"] for t in incoming["items"]}, {waiting["key"], blocked_waiting["key"]})
        mine = self.read("bob", view="mine")
        self.assertEqual(mine["total"], 3)
        self.assertEqual(mine["counts"], {"mine": 3, "review": 0, "unassigned": 0, "team": 3})
        self.assertTrue(all(t["next_actor"] == "bob" and t["assignee"] == "alice" for t in mine["items"]))
        self.assertEqual(self.read("charlie", view="incoming")["total"], 0)

    def test_historical_tasks_keep_unknown_stage_and_wait(self):
        t = self.ticket(body="原始需求全文")
        self.store.x("UPDATE tickets SET created='2020-01-01 00:00:00',updated='2020-01-02 00:00:00' WHERE id=?", (t["id"],))
        item = self.read(view="team")["items"][0]
        self.assertEqual(item["stage"], "unrecorded")
        self.assertEqual(item["stage_source"], "unrecorded")
        self.assertIsNone(item["waiting_seconds"])
        self.assertIsNone(item["handoff"])
        self.assertEqual(self.read(view="team")["stage_counts"]["unrecorded"], 1)

    def test_only_visible_page_gets_expensive_team_projection_without_review_candidates(self):
        for i in range(43):
            self.ticket("工单 %s" % i)
        with patch.object(team, "item", wraps=team.item) as observed:
            result = self.read(view="team", offset="10", limit="5")
        self.assertEqual(result["total"], 43)
        self.assertEqual(observed.call_count, 5)
        self.assertEqual({args.args[1]["key"] for args in observed.call_args_list}, {t["key"] for t in result["items"]})

    def test_actual_failed_run_is_visible_without_mutating_ticket_status(self):
        t = self.ticket()
        run = self.store.create_run(self.project["id"], t["id"], "external:fixture", "fix", "alice", "合成执行记录")
        self.store.x("UPDATE runs SET status='failed',result='synthetic failure' WHERE id=?", (run["id"],))
        item = self.read(view="team")["items"][0]
        self.assertEqual(item["work"]["state"], "blocked")
        self.assertEqual(item["work"]["label"], "执行中断，待处理")
        self.assertEqual(item["status"], "new")
        self.assertEqual(item["action_href"], "#/t/" + t["key"])
        self.assertIsNone(item["waiting_seconds"])
        self.assertEqual(item["next_actor"], "alice")

    def test_stage_counts_follow_view_query_and_state_but_not_selected_stage(self):
        self.action(self.ticket("支付待交接"), stage="testing")
        self.action(self.ticket("支付待上线"), stage="delivery")
        self.action(self.ticket("其它任务"), stage="operations")
        result = self.read("bob", view="incoming", q="支付", stage="testing", handoff_state="waiting")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["stage_counts"]["testing"], 1)
        self.assertEqual(result["stage_counts"]["delivery"], 1)
        self.assertEqual(result["stage_counts"]["operations"], 0)
        self.assertEqual(result["incoming_count"], 3)

    def test_closed_tasks_leave_active_queues_but_project_totals_keep_history(self):
        t = self.ticket()
        self.action(t)
        self.store.x("UPDATE tickets SET status='closed' WHERE id=?", (t["id"],))
        data = self.read("bob", view="incoming")
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["incoming_count"], 0)
        self.assertEqual(data["counts"]["team"], 0)
        self.assertEqual(data["projects"][0]["total"], 1)
        self.assertEqual(data["projects"][0]["open"], 0)

    def test_invalid_stage_state_view_and_page_are_400(self):
        for query in ({"stage": "invented"}, {"handoff_state": "accepted"}, {"view": "secret"}, {"offset": "NaN"}, {"limit": "bad"}):
            with self.subTest(query=query):
                with self.assertRaises(ApiError) as error:
                    self.read(**query)
                self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
