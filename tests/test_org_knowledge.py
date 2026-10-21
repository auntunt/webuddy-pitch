"""Organization knowledge v0 (`tmh/platform/org_knowledge.py`): read-only roll-up tests."""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("TMH_UNDERSTAND", "rules")

from tmh.platform import org_knowledge as org  # noqa: E402
from tmh.platform.store import Store  # noqa: E402

PAGE = """---
id: {pid}
title: {title}
status: {status}
---
# {title}

{summary}
"""


def write_page(root: Path, rel: str, pid: str, title: str, summary: str, status: str = "已确认") -> Path:
    p = root / ".tmh" / "knowledge" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(PAGE.format(pid=pid, title=title, status=status, summary=summary), encoding="utf-8")
    return p


def write_glossary(root: Path, rows: list[tuple[str, str, str]]) -> None:
    lines = ["# 术语表", "", "| 业务词 | 代码 / 表 | 说明 |", "|---|---|---|"]
    lines += ["| %s | %s | %s |" % r for r in rows]
    p = root / ".tmh" / "knowledge" / "glossary.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_lessons(data: Path, cards: list[dict]) -> None:
    p = data / "lessons.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cards) + "\n", encoding="utf-8")


class OrgKnowledgeTest:
    """Not a TestCase mixin: helpers only (subclasses below add tests)."""

    def make_store(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orgkb-"))
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.store = Store(self.data / "platform.db")
        self.oa = self.tmp / "oa"
        self.crm = self.tmp / "crm"
        for root in (self.oa, self.crm):
            root.mkdir()
            (root / "src").mkdir()
            (root / "src" / "App.java").write_text("class App {}\n", encoding="utf-8")
        self.store.add_project("OA", "OA 标品", str(self.oa), "示例")
        self.store.add_project("CRM", "CRM 项目", str(self.crm), "示例")

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


import unittest  # noqa: E402


class OrgKnowledgeTests(OrgKnowledgeTest, unittest.TestCase):
    def test_aggregates_multiple_projects(self):
        self.make_store()
        write_page(self.oa, "flows/approve.md", "flow:approve", "请假审批通过", "审批通过时记录审批人和时间。")
        write_page(self.crm, "flows/approve.md", "flow:approve", "合同审批通过", "合同审批通过后归档。")
        result = org.build(self.store)
        self.assertEqual(len(result["projects_read"]), 2)
        self.assertEqual(result["readonly"], True)
        self.assertGreaterEqual(result["stats"]["projects_contributing"], 2)
        self.assertEqual([p["key"] for p in result["projects_read"]], ["OA", "CRM"])

    def test_duplicate_content_is_deduped_across_projects_with_both_provenance(self):
        self.make_store()
        # identical glossary rows in both projects: one organization term, two provenance entries
        write_glossary(self.oa, [("审批", "approve", "状态从待审批变为已审批")])
        write_glossary(self.crm, [("审批", "approve", "状态从待审批变为已审批")])
        result = org.build(self.store)
        terms = [i for i in result["items"] if i["type"] == "term"]
        self.assertEqual(len(terms), 1, terms)
        projects = {p["project"] for p in terms[0]["provenance"]}
        self.assertEqual(projects, {"OA", "CRM"})
        self.assertEqual(result["stats"]["cross_project_items"], 1)

    def test_same_name_different_content_is_not_merged(self):
        """Two projects may both have a page titled 审批通过; the content differs -> two items."""
        self.make_store()
        write_page(self.oa, "flows/approve.md", "flow:approve", "审批通过", "OA：审批通过后写入审批日志并通知申请人。")
        write_page(self.crm, "flows/approve.md", "flow:approve", "审批通过", "CRM：审批通过后生成合同版本。")
        result = org.build(self.store)
        same_title = [i for i in result["items"] if i["title"] == "审批通过"]
        self.assertEqual(len(same_title), 2, same_title)
        self.assertNotEqual(same_title[0]["dedup_key"], same_title[1]["dedup_key"])
        # and provenance never claims both projects on one item
        for item in same_title:
            self.assertEqual(len({p["project"] for p in item["provenance"]}), 1)

    def test_empty_projects_return_empty_without_error(self):
        self.make_store()
        result = org.build(self.store)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["stats"]["items"], 0)
        self.assertEqual(result["stats"]["by_type"], {"term": 0, "pattern": 0, "component": 0, "rule": 0})
        self.assertEqual(org.search(self.store, "anything"), [])

    def test_read_only_never_writes_store_or_project(self):
        self.make_store()
        write_page(self.oa, "flows/approve.md", "flow:approve", "请假审批", "审批通过后通知。")
        write_glossary(self.oa, [("审批", "approve", "状态流转")])
        db = self.data / "platform.db"
        before_db = (db.stat().st_size, db.stat().st_mtime_ns)
        before_files = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.oa.rglob("*") if p.is_file()}
        before_all = sorted(str(p) for p in self.tmp.rglob("*"))
        org.build(self.store)
        org.search(self.store, "审批")
        self.assertEqual((db.stat().st_size, db.stat().st_mtime_ns), before_db)
        after_files = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.oa.rglob("*") if p.is_file()}
        self.assertEqual(after_files, before_files)
        self.assertEqual(sorted(str(p) for p in self.tmp.rglob("*")), before_all)

    def test_search_returns_traceable_provenance(self):
        self.make_store()
        write_page(self.oa, "flows/approve.md", "flow:approve", "请假审批通过", "审批通过时记录审批人和时间。")
        hits = org.search(self.store, "审批")
        self.assertTrue(hits)
        item = hits[0]
        self.assertEqual(item["type"], "pattern")
        self.assertEqual(item["title"], "请假审批通过")
        prov = item["provenance"][0]
        self.assertEqual(prov["project"], "OA")
        self.assertEqual(prov["kind"], "page")
        self.assertEqual(prov["ref"], "flows/approve.md")
        self.assertEqual(prov["id"], "flow:approve")
        self.assertTrue(prov["confirmed"])

    def test_lessons_become_patterns_and_rules_and_cover_four_types(self):
        self.make_store()
        write_page(self.oa, "flows/approve.md", "flow:approve", "请假审批", "审批通过后通知。")
        write_page(self.oa, "modules/leave.md", "mod:leave", "请假服务模块", "请假相关服务。")
        write_glossary(self.oa, [("审批", "approve", "状态流转")])
        write_lessons(self.data, [
            {"id": "L1", "project": "OA", "symptom": "导出少一列", "fix": "在导出模板补第 8 列并加测试",
             "anti": "不要顺手改公共导出工具", "status": "active"},
            {"id": "L2", "project": "CRM", "symptom": "导出少一列", "fix": "在导出模板补第 8 列并加测试",
             "status": "active"},
        ])
        result = org.build(self.store)
        for kind in ("term", "pattern", "component", "rule"):
            self.assertGreaterEqual(result["stats"]["by_type"][kind], 1, result["stats"])
        patterns = [i for i in result["items"] if i["type"] == "pattern"]
        merged = [i for i in patterns if len(i["provenance"]) >= 2]
        self.assertTrue(merged, "same lesson fix in two projects should dedupe with both provenance")


if __name__ == "__main__":
    unittest.main()
