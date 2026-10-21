"""G9 developer-habit API: read-only, redacted by default, MIN_SAMPLE discipline for team shares."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("TMH_UNDERSTAND", "rules")

from tmh.platform.habits import MIN_SAMPLE  # noqa: E402
from tmh.platform.server import Platform, make_handler  # noqa: E402

TOKEN = "audit-token"


def snapshot_tree(root: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in Path(root).rglob("*") if p.is_file()}


class HabitsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Path(tempfile.mkdtemp(prefix="habitsapi-"))
        cls.oa_root = cls.data / "projects" / "oa"
        cls.small_root = cls.data / "projects" / "small"
        for root in (cls.oa_root, cls.small_root):
            root.mkdir(parents=True)
            (root / "src").mkdir()
            (root / "src" / "App.java").write_text("class App {}\n", encoding="utf-8")
        cls.P = Platform(cls.data, "tester")
        cls.oa = cls.P.store.add_project("OA", "OA 标品", str(cls.oa_root), "示例")
        cls.small = cls.P.store.add_project("SM", "小项目", str(cls.small_root), "示例")
        st = cls.P.store
        # OA: enough runs/tickets/decisions for shares; two authors so the team view is per-project anonymous
        cls.oa_tickets = []
        for i in range(5):
            t = st.create_ticket(cls.oa["id"], "请假导出问题 %d" % i, "li", type="bug")
            cls.oa_tickets.append(t)
            r = st.create_run(cls.oa["id"], t["id"], "codex", "fix", "li", "修复导出第 %d 列" % i)
            st.update_run(r["id"], status="done")
            r2 = st.create_run(cls.oa["id"], t["id"], "codex", "analyze", "wang", "分析导出问题 %d" % i)
            st.update_run(r2["id"], status="failed" if i == 0 else "done")
            st.event(t["id"], "li", "reject" if i % 2 else "accept", "",
                     {"note": "方向不对" if i % 2 else "导出列已补齐"})
        # SMALL: below MIN_SAMPLE everywhere
        t = st.create_ticket(cls.small["id"], "小项目唯一工单", "li", type="bug")
        r = st.create_run(cls.small["id"], t["id"], "codex", "fix", "li", "改一处")
        st.update_run(r["id"], status="done")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P, TOKEN))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.data, ignore_errors=True)

    def call(self, path, headers=None, token=True):
        h = {"X-TMH": "1", "Content-Type": "application/json"}
        if token:
            h["X-TMH-Token"] = TOKEN
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, method="GET", headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def test_without_token_is_401(self):
        self.assertEqual(self.call("/api/projects/OA/habits?team=1", token=False)[0], 401)

    def test_unknown_project_is_404(self):
        code, body = self.call("/api/projects/NOPE/habits?team=1")
        self.assertEqual(code, 404, body)

    def test_personal_view_is_redacted_by_default_and_never_returns_raw_text(self):
        code, body = self.call("/api/projects/OA/habits?user=li")
        self.assertEqual(code, 200, body)
        self.assertEqual(body["view"], "personal")
        self.assertTrue(body["privacy"]["redact"])
        self.assertFalse(body["privacy"]["contains_raw_text"])
        self.assertNotIn("person", body)
        raw = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("修复导出第", raw)  # prompts are only fingerprinted, never returned
        self.assertNotIn("方向不对", raw)  # acceptance notes are only classified
        self.assertEqual(body["sample"]["runs"], 5)
        self.assertTrue(body["fair"])
        self.assertIsNotNone(body["modes_share"])

    def test_explicit_unredacted_view_names_the_person(self):
        code, body = self.call("/api/projects/OA/habits?user=li&redact=0")
        self.assertEqual(code, 200, body)
        self.assertFalse(body["privacy"]["redact"])
        self.assertEqual(body["person"], "li")

    def test_small_sample_withholds_shares(self):
        code, body = self.call("/api/projects/SM/habits?user=li")
        self.assertEqual(code, 200, body)
        self.assertFalse(body["fair"])
        self.assertIsNone(body["modes_share"])  # counts only, no dressed-up ratio
        self.assertLess(body["sample"]["runs"], MIN_SAMPLE)
        self.assertTrue(body["notes"])

    def test_team_view_is_anonymous_and_sample_disciplined(self):
        code, body = self.call("/api/projects/SM/habits?team=1")
        self.assertEqual(code, 200, body)
        self.assertEqual(body["view"], "team")
        self.assertFalse(body["privacy"]["per_person"])
        self.assertEqual(body["min_sample"], MIN_SAMPLE)
        self.assertFalse(body["fair"])
        self.assertIsNone(body["modes_share"])
        self.assertIsNone(body["rework_rate"])
        self.assertEqual(body["sample"]["tickets"], 1)
        # OA has 5 tickets and 5 decisions -> shares are allowed
        code, body = self.call("/api/projects/OA/habits?team=1")
        self.assertEqual(code, 200, body)
        self.assertTrue(body["fair"], body)
        self.assertIsNotNone(body["modes_share"])
        self.assertIsNotNone(body["rework_rate"])
        self.assertNotIn("li", json.dumps(body.get("projects", {}), ensure_ascii=False))  # no per-person rows

    def test_cross_project_aggregation_on_team_view(self):
        code, body = self.call("/api/projects/OA/habits?team=1")
        self.assertEqual(code, 200, body)
        self.assertEqual(body["projects"], {"OA": 10})
        self.assertEqual(body["sample"]["participants"], 2)  # count only, no names
        self.assertEqual(body["sample"]["runs"], 10)

    def test_default_user_is_the_requester(self):
        """No user= means "my own view": the requester identity is used, not an error."""
        code, body = self.call("/api/projects/OA/habits")
        self.assertEqual(code, 200, body)
        self.assertEqual(body["view"], "personal")
        self.assertTrue(body["privacy"]["redact"])
        self.assertNotIn("person", body)

    def test_readonly_snapshot_unchanged(self):
        db = self.data / "platform.db"
        before_db = (db.stat().st_size, db.stat().st_mtime_ns)
        before_data = snapshot_tree(self.data)
        before_oa = snapshot_tree(self.oa_root)
        for path in ("/api/projects/OA/habits?user=li", "/api/projects/OA/habits?user=wang&redact=0",
                     "/api/projects/OA/habits?team=1", "/api/projects/SM/habits?team=1"):
            self.assertEqual(self.call(path)[0], 200)
        self.assertEqual((db.stat().st_size, db.stat().st_mtime_ns), before_db)
        self.assertEqual(snapshot_tree(self.data), before_data)
        self.assertEqual(snapshot_tree(self.oa_root), before_oa)


if __name__ == "__main__":
    unittest.main()
