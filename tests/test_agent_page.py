"""Executor page data: a recorded connection test, usage from run records, and no invented tokens."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tmh.platform import agent_page
from tmh.platform.store import Store


class AgentPageTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-agent-page-")
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        (self.data / "app").mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("AGP", "agent page", str(self.data / "app"))

    def add_run(self, agent, status, exit_code, started, ended):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.store.db.execute("INSERT INTO runs(project_id,agent,mode,status,created,started,ended,exit_code) VALUES(?,?,?,?,?,?,?,?)",
                              (self.project["id"], agent, "fix", status, now, started, ended, exit_code))
        self.store.db.commit()

    def test_last_connection_test_is_recorded_with_reason(self):
        agent_page.record_test(self.data, "codex", {"ok": False, "reason": "未登录"})
        recorded = json.loads((self.data / "agent-tests.json").read_text(encoding="utf-8"))["codex"]
        self.assertFalse(recorded["ok"])
        self.assertEqual(recorded["reason"], "未登录")
        self.assertTrue(recorded["at"])

    def test_usage_counts_success_rate_last_used_and_duration(self):
        self.add_run("codex", "done", 0, "2026-11-09 10:00:00", "2026-11-09 10:01:00")
        self.add_run("codex", "failed", 1, "2026-11-09 11:00:00", "2026-11-09 11:00:30")
        usage = agent_page.usage(self.store)["by_executor"]["codex"]
        self.assertEqual(usage["runs"], 2)
        self.assertEqual(usage["success"], 1)
        self.assertEqual(usage["success_rate"], 0.5)
        self.assertEqual(usage["total_seconds"], 90)
        self.assertTrue(usage["last_used"])
        self.assertNotIn("tokens", usage)

    def test_no_runs_means_no_usage(self):
        self.assertEqual(agent_page.usage(self.store)["by_executor"], {})


if __name__ == "__main__":
    unittest.main()


class DefaultExecutorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-default-exec-")
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)

    def test_last_passing_test_wins_and_untested_means_none(self):
        self.assertEqual(agent_page.default_executor(self.data, ["claude", "codex"]), "")
        agent_page.record_test(self.data, "codex", {"ok": True})
        self.assertEqual(agent_page.default_executor(self.data, ["claude", "codex"]), "codex")
        agent_page.record_test(self.data, "claude", {"ok": False, "reason": "403 封禁"})
        self.assertEqual(agent_page.default_executor(self.data, ["claude", "codex"]), "codex")

    def test_a_passing_executor_that_is_not_available_is_not_chosen(self):
        agent_page.record_test(self.data, "codex", {"ok": True})
        self.assertEqual(agent_page.default_executor(self.data, ["claude"]), "")
