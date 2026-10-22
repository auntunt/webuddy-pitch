"""G8 organization knowledge over the HTTP API: read-only, authenticated, provenance-carrying."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("TMH_UNDERSTAND", "rules")

from tmh.platform.server import Platform, make_handler  # noqa: E402

TOKEN = "audit-token"
PAGE = """---
id: {pid}
title: {title}
status: 已确认
---
# {title}

{summary}
"""
GLOSSARY = "# 术语表\n\n| 业务词 | 代码 / 表 | 说明 |\n|---|---|---|\n| 审批 | approve | {note} |\n"


def kb_page(root: Path, rel: str, pid: str, title: str, summary: str) -> None:
    p = root / ".tmh" / "knowledge" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(PAGE.format(pid=pid, title=title, summary=summary), encoding="utf-8")


def glossary(root: Path, note: str) -> None:
    p = root / ".tmh" / "knowledge" / "glossary.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(GLOSSARY.format(note=note), encoding="utf-8")


def snapshot_tree(root: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in Path(root).rglob("*") if p.is_file()}


class OrgKnowledgeApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tmh import bots
        # Platform wires a process-global callback; restore its previous owner.
        cls.addClassCleanup(setattr, bots, "INTAKE", bots.INTAKE)
        cls.data = Path(tempfile.mkdtemp(prefix="orgapi-"))
        cls.oa = cls.data / "projects" / "oa"
        cls.crm = cls.data / "projects" / "crm"
        for root in (cls.oa, cls.crm):
            root.mkdir(parents=True)
            (root / "src").mkdir()
            (root / "src" / "App.java").write_text("class App {}\n", encoding="utf-8")
        kb_page(cls.oa, "flows/approve.md", "flow:approve", "请假审批通过", "OA：审批通过后写审批日志。")
        kb_page(cls.crm, "flows/approve.md", "flow:approve", "合同审批通过", "CRM：审批通过后生成合同版本。")
        glossary(cls.oa, "状态从待审批变为已审批")
        glossary(cls.crm, "状态从待审批变为已审批")
        cls.P = Platform(cls.data, "tester")
        cls.P.store.add_project("OA", "OA 标品", str(cls.oa), "示例")
        cls.P.store.add_project("CRM", "CRM 项目", str(cls.crm), "示例")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P, TOKEN))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls.P.store.db.close()
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

    # ---- auth ----
    def test_without_token_is_401(self):
        code, body = self.call("/api/org/knowledge", token=False)
        self.assertEqual(code, 401, body)

    def test_preview_origin_referer_is_403(self):
        code, body = self.call("/api/org/knowledge", headers={"Referer": "http://127.0.0.1:9/pv/OA-1/"})
        self.assertEqual(code, 403, body)

    # ---- shape ----
    def test_summary_shape_and_type_counts(self):
        code, body = self.call("/api/org/knowledge")
        self.assertEqual(code, 200, body)
        self.assertTrue(body["readonly"])
        self.assertEqual(body["query"], "")
        for t in ("term", "pattern", "component", "rule"):
            self.assertIn(t, body["summary"]["by_type"])
        self.assertEqual({p["key"] for p in body["projects"]}, {"OA", "CRM"})
        self.assertGreaterEqual(body["summary"]["projects_contributing"], 2)
        self.assertIsInstance(body["items"], list)

    def test_search_returns_cross_project_provenance(self):
        code, body = self.call("/api/org/knowledge?q=%E5%AE%A1%E6%89%B9&limit=20")
        self.assertEqual(code, 200, body)
        self.assertEqual(body["query"], "审批")
        self.assertTrue(body["items"], body)
        terms = [i for i in body["items"] if i["type"] == "term"]
        self.assertTrue(terms, body)
        projects = {p["project"] for p in terms[0]["provenance"]}
        self.assertEqual(projects, {"OA", "CRM"})  # identical content deduped, provenance kept apart
        for prov in terms[0]["provenance"]:
            self.assertEqual(prov["kind"], "glossary")
            self.assertEqual(prov["ref"], "glossary.md")
            self.assertTrue(prov["confirmed"])

    def test_type_filter_and_bad_type(self):
        code, body = self.call("/api/org/knowledge?q=%E5%AE%A1%E6%89%B9&type=term")
        self.assertEqual(code, 200, body)
        self.assertTrue(all(i["type"] == "term" for i in body["items"]))
        code, body = self.call("/api/org/knowledge?type=nope")
        self.assertEqual(code, 400, body)
        self.assertIn("nope", body["error"])

    def test_bad_limit_is_400(self):
        self.assertEqual(self.call("/api/org/knowledge?limit=abc")[0], 400)
        self.assertEqual(self.call("/api/org/knowledge?limit=0")[0], 400)
        self.assertEqual(self.call("/api/org/knowledge?limit=999")[0], 400)

    def test_readonly_snapshot_unchanged(self):
        db = self.data / "platform.db"
        before_db = (db.stat().st_size, db.stat().st_mtime_ns)
        before_data = snapshot_tree(self.data)
        before_oa, before_crm = snapshot_tree(self.oa), snapshot_tree(self.crm)
        for path in ("/api/org/knowledge", "/api/org/knowledge?q=%E5%AE%A1%E6%89%B9",
                     "/api/org/knowledge?type=rule&limit=5"):
            self.assertEqual(self.call(path)[0], 200)
        self.assertEqual((db.stat().st_size, db.stat().st_mtime_ns), before_db)
        self.assertEqual(snapshot_tree(self.data), before_data)
        self.assertEqual(snapshot_tree(self.oa), before_oa)
        self.assertEqual(snapshot_tree(self.crm), before_crm)


class DraftKnowledgeReaderApiTest(unittest.TestCase):
    def test_memory_source_opens_complete_draft_without_confirming_it(self):
        from tmh import bots, kb
        self.addCleanup(setattr, bots, "INTAKE", bots.INTAKE)
        with tempfile.TemporaryDirectory(prefix="draft-knowledge-http-") as folder:
            data = Path(folder)
            root = data / "project"
            root.mkdir()
            (root / "App.java").write_text("class App {}\n")
            kb.build(root)
            path = kb.page_path(root, "index")
            old = kb.parse_page(path.read_text())
            body = "\n\n".join("## " + title + "\n待确认的项目说明，代码来源 App.java:1。" for title in kb.SECTIONS["index"])
            path.write_text(kb.render_page("index", {"id": "index", "title": "项目总览草稿", "summary": "项目知识导入说明"}, old["facts"], body))
            self.assertEqual(kb.done(root, "index", "agent:test-import"), (True, []))
            platform = Platform(data / "platform", "test-reader")
            platform.store.add_project("DRAFT", "草稿测试项目", str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(platform, TOKEN))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base = "http://127.0.0.1:%d" % server.server_address[1]
            def read(endpoint):
                request = urllib.request.Request(base + endpoint, headers={"X-TMH-Token": TOKEN})
                with opener.open(request, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    return json.loads(response.read())
            try:
                before = snapshot_tree(root)
                self.assertEqual(read("/api/org/knowledge")["items"], [])
                result = read("/api/memory?project=DRAFT&section=knowledge")
                self.assertEqual(len(result["knowledge"]), 1)
                source = result["knowledge"][0]["provenance"][0]
                self.assertFalse(source["confirmed"])
                self.assertTrue(read("/api/projects/DRAFT/kb/tree")["built"])
                page = read("/api/projects/DRAFT/kb/page?id=" + urllib.parse.quote(source["id"], safe=""))
                self.assertEqual(page["text"], path.read_text())
                self.assertEqual(page["status"], "待确认")
                self.assertEqual(page["confirmed_by"], "")
                self.assertEqual(snapshot_tree(root), before)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                platform.store.db.close()


class KnowledgeFixtureIsolationTest(unittest.TestCase):
    def test_http_fixtures_restore_the_previous_bot_intake(self):
        from tmh import bots

        previous = mock.Mock(side_effect=AssertionError("unrelated intake must not run"))
        with mock.patch.object(bots, "INTAKE", previous):
            for case in (OrgKnowledgeApiTest("test_summary_shape_and_type_counts"),
                         DraftKnowledgeReaderApiTest("test_memory_source_opens_complete_draft_without_confirming_it")):
                with self.subTest(fixture=type(case).__name__):
                    result = unittest.TestResult()
                    unittest.TestSuite([case]).run(result)
                    self.assertEqual(result.errors, [])
                    self.assertEqual(result.failures, [])
                    self.assertEqual(result.testsRun, 1)
                    self.assertIs(bots.INTAKE, previous)
            previous.assert_not_called()


if __name__ == "__main__":
    unittest.main()
