"""Context Pack v2 acceptance tests.

They use the checked-in example projects (the same fixtures the rest of the
suite uses), build a real knowledge base once per class, and then assert the
contract that `docs/design/project-knowledge-library-2026-10-20.md` §6.6 asks
for: budget limits expansion, never evidence; every result is traceable to a
source, a version and a full-text handle; multiple sources stay separated.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tmh import activity, kb  # noqa: E402
from tmh.context import build_context  # noqa: E402
from tmh.context_pack import SCHEMA, assemble, pack  # noqa: E402

JAVA = ROOT / "examples" / "legacy-java-oa"
QUERY = "报销单财务审核驳回后预算"


def copy_repo(src: Path, prefix: str = "tmh-ctx-") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    dst = d / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=dst, check=True)
    return dst


class ContextPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = copy_repo(JAVA)
        kb.build(cls.repo)
        cls.reference = copy_repo(JAVA, "tmh-ctx-ref-")
        kb.build(cls.reference)

    def one(self, **kwargs):
        options = {"json_mode": True, "log": False}
        options.update(kwargs)
        return assemble([{"root": str(self.repo), "label": "oa", "current": True}], QUERY, **options)

    # --- provenance -------------------------------------------------------
    def test_pack_carries_source_version_and_full_text_handle(self):
        res = self.one()
        self.assertEqual(res["schema"], SCHEMA)
        self.assertIn("不替代人工验收", res["notice"])
        src = res["sources"][0]
        self.assertTrue(src["available"])
        self.assertTrue(src["revision"], "source version must pin a git commit")
        self.assertTrue(src["knowledge_revision"], "knowledge revision fingerprint missing")
        self.assertLessEqual(res["used"], res["budget"])
        self.assertTrue(res["items"])
        for item in res["items"]:
            self.assertTrue(item["id"].startswith("oa:"), "ids must be namespaced by source")
            self.assertEqual(item["source"], "oa")
            self.assertEqual(item["source_version"], src["revision"])
            self.assertEqual(item["knowledge_revision"], src["knowledge_revision"])
            self.assertTrue(item["full_text"], "every item must tell how to read its full text")
            self.assertTrue(item["path"])

    def test_page_and_code_items_expose_the_right_full_text_commands(self):
        res = self.one(budget=60000)
        pages = [i for i in res["items"] if i["section"] == "pages"]
        code = [i for i in res["items"] if i["section"] == "code"]
        self.assertTrue(pages, "expected knowledge pages in the pack")
        self.assertTrue(code, "expected code locations in the pack")
        for item in pages:
            self.assertTrue(item["full_text"].startswith("tmh kb read "))
            self.assertTrue(item["path"].startswith(".tmh/knowledge/"))
        for item in code:
            self.assertIn(":", item["full_text"])
            self.assertTrue(item["end_line"] >= item["line"] >= 1)

    def test_relevant_flow_survives_render(self):
        text = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                        QUERY, budget=8000, log=False)
        self.assertIn("post-expense-audit", text)
        self.assertIn("OA_BUDGET", text)

    # --- budget contract --------------------------------------------------
    def test_budget_limits_expansion_not_evidence(self):
        res = self.one(budget=600)
        self.assertLessEqual(res["used"], 600)
        self.assertFalse(res["complete"], "a 600-char pack cannot be complete")
        self.assertTrue(res["omissions"], "omitted items must be reported, never silently dropped")
        for omission in res["omissions"]:
            self.assertTrue(omission["full_text"], "an omitted item must still be readable in full")
            self.assertIn(omission["reason"], ("budget", "section-budget", "total-budget"))
        text = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                        QUERY, budget=600, log=False)
        self.assertIn("未展开", text)
        self.assertLessEqual(len(text), 600)

    def test_generous_budget_is_complete(self):
        res = self.one(budget=60000)
        self.assertTrue(res["complete"])
        self.assertEqual(res["omissions"], [])
        self.assertGreater(len(res["items"]), 2)

    def test_sections_account_for_what_is_rendered(self):
        res = self.one(budget=8000)
        for name in ("pages", "flows", "tables", "code"):
            self.assertIn(name, res["sections"])
        self.assertEqual(res["sections"]["pages"]["count"],
                         sum(1 for i in res["items"] if i["section"] == "pages"))
        self.assertGreaterEqual(res["used"], sum(s["bytes"] for s in res["sections"].values()))

    def test_pack_never_splits_an_item(self):
        items = [{"id": "x:1", "section": "pages", "kind": "page:flow", "title": "a" * 120,
                  "domain": "", "score": 1.0, "status": "待确认", "stale": False,
                  "path": ".tmh/knowledge/p.md", "line": 1, "end_line": 0, "excerpt": "b" * 120,
                  "full_text": "tmh kb read x"}]
        packed = pack(items, budget=250)
        self.assertEqual(packed["items"], [])
        self.assertEqual(len(packed["omissions"]), 1)
        self.assertLessEqual(sum(len(i["render"]) for i in packed["items"]), 250)

    # --- multi source -----------------------------------------------------
    def test_reference_source_is_separate_and_current_comes_first(self):
        res = assemble([
            {"root": str(self.repo), "label": "oa", "current": True},
            {"root": str(self.reference), "label": "ref", "current": False},
        ], QUERY, budget=60000, json_mode=True, log=False)
        self.assertEqual(len(res["sources"]), 2)
        ids = [i["id"] for i in res["items"]]
        self.assertEqual(len(ids), len(set(ids)), "two projects' ids must never collide")
        labels = {i["source"] for i in res["items"]}
        self.assertEqual(labels, {"oa", "ref"})
        self.assertEqual(res["items"][0]["source"], "oa", "current project should rank first on equal scores")
        self.assertTrue(all(i["source_version"] for i in res["items"]))

    def test_unavailable_source_is_explicit_and_can_fail_closed(self):
        missing = Path(tempfile.mkdtemp(prefix="tmh-ctx-missing-")) / "nope"
        res = assemble([
            {"root": str(self.repo), "label": "oa", "current": True},
            {"root": str(missing), "label": "ghost", "current": False},
        ], QUERY, budget=4000, json_mode=True, log=False)
        ghost = next(s for s in res["sources"] if s["label"] == "ghost")
        self.assertFalse(ghost["available"])
        self.assertTrue(ghost["error"])
        self.assertFalse(res["complete"])
        with self.assertRaises(ValueError):
            assemble([{"root": str(missing), "label": "ghost"}], QUERY, require_all=True, log=False)
        with self.assertRaises(ValueError):
            assemble([], QUERY, log=False)

    # --- determinism and activity ----------------------------------------
    def test_output_is_deterministic(self):
        first = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                         QUERY, budget=4000, json_mode=True, log=False)
        second = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                          QUERY, budget=4000, json_mode=True, log=False)
        self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True),
                         json.dumps(second, ensure_ascii=False, sort_keys=True))

    def test_assembly_is_recorded_for_later_experience_mining(self):
        before = len(activity.read(self.repo))
        assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                 QUERY, budget=4000, json_mode=True, log=True)
        records = activity.read(self.repo)
        self.assertGreater(len(records), before)
        last = records[-1]
        self.assertEqual(last["kind"], "context")
        self.assertEqual(last["budget"], 4000)
        self.assertIn("items", last)
        self.assertIn("omitted", last)
        self.assertIn("sources", last)

    # --- legacy path ------------------------------------------------------
    def test_legacy_build_context_reports_truncation_instead_of_hiding_it(self):
        out = build_context(self.repo, QUERY, 300)
        self.assertLessEqual(len(out), 300)
        self.assertIn("省略", out)
        self.assertIn("tmh kb read", out)


if __name__ == "__main__":
    unittest.main()
