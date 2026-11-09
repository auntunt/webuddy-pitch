"""/next/ task list and creation: a task is an ordinary ticket and creation enters the existing flow."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tmh.platform.api import tasks
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform


class TaskApiTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-tasks-")
        self.addCleanup(temp.cleanup)
        self.P = Platform(Path(temp.name), "tester")
        root = Path(temp.name) / "app"
        root.mkdir()
        self.P.store.add_project("TSK", "task sample", str(root))

    def req(self, body=None, user="alice"):
        return SimpleNamespace(body=body or {}, user=user, arg=lambda k: "")

    def test_create_requires_name_content_and_known_goal(self):
        for body in ({}, {"title": "t"}, {"title": "t", "body": "b", "goal": "发布"}):
            with self.subTest(body=body), self.assertRaises(ApiError) as caught:
                tasks.api_new_task(self.P, self.req(body), "TSK")
            self.assertEqual(caught.exception.code, 400)

    def test_plan_only_creates_ticket_without_submitting_and_lists_first_line(self):
        created = tasks.api_new_task(self.P, self.req({"title": "切换数据库", "body": "当前项目使用 MySQL\n第二行细节", "goal": "出方案"}), "TSK")
        self.assertEqual(created["goal"], "出方案")
        listed = tasks.api_tasks(self.P, self.req(), "TSK")["items"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["title"], "切换数据库")
        self.assertEqual(listed[0]["first_line"], "当前项目使用 MySQL")
        self.assertEqual(listed[0]["key"], created["key"])


if __name__ == "__main__":
    unittest.main()
