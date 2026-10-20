import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tmh.platform.store import Store

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("merge_data", ROOT / "scripts" / "deploy" / "merge_data.py")
merge_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge_data)


class MergeDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ops, self.reform = self.tmp / "ops", self.tmp / "reform"

    def fill(self, d: Path, key: str, runs: int, max_lines: int):
        d.mkdir()
        st = Store(d / "platform.db")
        p = st.add_project(key, key + " 项目", str(self.tmp))
        t = st.create_ticket(p["id"], "工单 " + key)
        last = None
        for _ in range(runs):
            last = st.create_run(p["id"], t["id"], "codex", "fix", "张工", "prompt")
            st.event(t["id"], "自动流转", "agent", "跑完了", {"run": last["id"]})
            st.add_points(p["id"], -50, "运行", run_id=last["id"], ticket_id=t["id"])
            (d / "runs" / str(last["id"])).mkdir(parents=True)
            (d / "runs" / str(last["id"]) / "verify.json").write_text('{"check": "pass"}', encoding="utf-8")
        (d / "evals").mkdir()
        (d / "evals" / (key + ".json")).write_text("[]", encoding="utf-8")
        (d / "autoflow.json").write_text(json.dumps({"on": True, "max_lines": max_lines, "max_agents": 3}), encoding="utf-8")
        (d / "lessons.jsonl").write_text(json.dumps({"kind": "reject", "run": last["id"]}) + "\n", encoding="utf-8")
        st.db.close()
        return t

    def test_both_projects_end_up_in_one_platform_with_their_records_intact(self):
        self.fill(self.ops, "JB", 3, 400)
        self.fill(self.reform, "RW", 2, 20000)
        (self.reform / "reforms").mkdir()
        (self.reform / "reforms" / "RW.json").write_text("[]", encoding="utf-8")
        merge_data.merge(self.ops, self.reform)

        st = Store(self.ops / "platform.db")
        rw = st.project("RW")
        self.assertEqual([p["key"] for p in st.q("SELECT key FROM projects ORDER BY id")], ["JB", "RW"])
        t = st.tickets(project_id=rw["id"])[0]
        self.assertEqual(t["title"], "工单 RW")
        runs = st.q("SELECT id, ticket_id FROM runs WHERE project_id=? ORDER BY id", (rw["id"],))
        self.assertEqual([r["id"] for r in runs], [4, 5])
        self.assertTrue(all(r["ticket_id"] == t["id"] for r in runs))
        self.assertEqual([e["data"]["run"] for e in st.events(t["id"]) if "run" in e["data"]], [4, 5])
        pts = st.q("SELECT run_id, ticket_id FROM points WHERE project_id=?", (rw["id"],))
        self.assertEqual(sorted(p["run_id"] for p in pts), [4, 5])
        for r in (1, 2, 3, 4, 5):
            self.assertTrue((self.ops / "runs" / str(r) / "verify.json").exists())
        self.assertTrue((self.ops / "reforms" / "RW.json").exists())
        self.assertTrue((self.ops / "evals" / "RW.json").exists() and (self.ops / "evals" / "JB.json").exists())
        lessons = [json.loads(x) for x in (self.ops / "lessons.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["run"] for x in lessons], [3, 5])
        flow = json.loads((self.ops / "autoflow.json").read_text(encoding="utf-8"))
        self.assertEqual(flow["max_lines"], {"JB": 400, "RW": 20000, "*": 400})

    def test_a_project_already_there_is_not_merged_twice(self):
        self.fill(self.ops, "JB", 1, 400)
        self.fill(self.reform, "JB", 1, 400)
        with self.assertRaises(SystemExit):
            merge_data.merge(self.ops, self.reform)
        c = sqlite3.connect(str(self.ops / "platform.db"))
        self.assertEqual(c.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
