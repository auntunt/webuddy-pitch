"""Daily queues must preserve identity, scope and pagination beyond 500 tasks."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock

from tmh.platform import team, workspace
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class WorkspaceTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.a = self.store.add_project("A", "项目甲", str(self.data))
        self.b = self.store.add_project("B", "项目乙", str(self.data))
        self.users = mock.patch("tmh.platform.login.load_users", return_value={"lin": {}, "chen": {}})
        self.users.start()

    def tearDown(self):
        self.users.stop()
        self.store.db.close()
        self.tmp.cleanup()

    def ticket(self, p=None, assignee="lin", title="处理审批问题"):
        return self.store.create_ticket((p or self.a)["id"], title, "reporter", assignee=assignee)

    def test_personal_queues_use_verified_identity_and_preserve_scope(self):
        t = self.ticket()
        self.ticket(self.b)
        self.ticket(assignee="chen")
        self.ticket(assignee="")
        result = workspace.read(self.P, {"view": ["mine"], "project": ["A"]}, "lin")
        self.assertEqual([x["key"] for x in result["items"]], [t["key"]])
        self.assertEqual(result["counts"], {"mine": 1, "review": 0, "unassigned": 1, "team": 3})
        self.assertEqual(workspace.read(self.P, {"view": "mine"}, "")['total'], 0)
        self.assertEqual(workspace.read(self.P, {"view": "team"}, "")['total'], 4)

    def test_review_queue_does_not_count_work_assigned_to_someone_else(self):
        t = self.ticket(assignee="chen")
        team.schema(self.P)
        self.store.update_ticket(t['id'], 'tester', status='verify')
        self.store.x("INSERT INTO ticket_team VALUES(?,?,?,?,?)", (t['id'], 'lin', 1, t['updated'], 'chen'))
        self.assertEqual(workspace.read(self.P, {"view": "review"}, "lin")['total'], 1)
        self.assertEqual(workspace.read(self.P, {"view": "review"}, "chen")['total'], 0)

    def test_large_queue_is_paginated_without_losing_tasks_or_inflating_search_count(self):
        for i in range(503):
            self.ticket(title="审批 %d" % i)
        result = workspace.read(self.P, {"view": "mine", "offset": "500", "limit": "30"}, "lin")
        self.assertEqual((result['total'], len(result['items']), result['has_more']), (503, 3, False))
        result = workspace.read(self.P, {"q": "审批 502"}, "lin")
        self.assertEqual((result['total'], result['counts']['mine']), (1, 503))

    def test_invalid_scope_and_pagination_fail_actionably(self):
        for query in ({"project": "UNKNOWN"}, {"offset": "oops"}, {"view": "unknown"}):
            with self.assertRaises(ApiError):
                workspace.read(self.P, query, "lin")
