"""Fixed learning revisions, old authority and additive migration contracts."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import learning as L, learn
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.root = self.data / "repo"
        self.root.mkdir()
        self.p = self.store.add_project("APP", "APP", str(self.root))
        other = self.data / "other"
        other.mkdir()
        self.other = self.store.add_project("OTHER", "OTHER", str(other))
        self.page = self.root / ".tmh/knowledge/flows/demo.md"
        self.page.parent.mkdir(parents=True)
        self.body = "---\nid: flow:demo\ntitle: 示例\nstatus: 已确认\n---\n# 示例\n\n返回真实值 `a.py:1`。\n" + "完整正文。" * 1000
        self.page.write_text(self.body)
        (self.root / "a.py").write_text("def answer(): return 42\n")

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def capture(self, key="fact:flow:demo"):
        item = next(x for x in L.catalog(self.P, self.p)["items"] if x["key"] == key)
        return L.capture(self.P, self.p, key, item["fingerprint"], "writer")

    def test_read_is_pure_and_old_confirmation_is_not_machine_pass(self):
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.data.rglob("*") if p.is_file()}
        result = L.catalog(self.P, self.p)
        item = result["items"][0]
        self.assertEqual(item["content"], self.body)
        self.assertEqual(item["human"]["status"], "已确认")
        self.assertEqual(item["machine"]["status"], "unreviewed")
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.data.rglob("*") if p.is_file()})
        self.assertEqual(L.catalog(self.P, self.other)["items"], [])

    def test_capture_is_complete_idempotent_and_project_scoped(self):
        r = self.capture()
        self.assertEqual(self.capture()["id"], r["id"])
        self.assertEqual(r["content"], self.body)
        self.assertEqual(r["source"]["evidence"][0]["content"], "def answer(): return 42\n")
        self.assertEqual(r["source"]["snapshot_kind"], "working-copy-manifest")
        self.assertTrue(L.revision_current(self.P, self.p, r))
        self.assertFalse(L.revision_current(self.P, self.other, r))
        with self.assertRaises(ApiError):
            L.revision(self.P, self.other, r["id"])

    def test_proposal_never_mutates_page_or_inherits_confirmation(self):
        r = self.capture()
        content = self.body + "\n修订正文"
        proposal = L.propose(self.P, self.p, r["id"], content, "agent:review")
        self.assertEqual(proposal["parent_id"], r["id"])
        self.assertEqual(proposal["id"], L.propose(self.P, self.p, r["id"], content, "retry")["id"])
        self.assertEqual(self.page.read_text(), self.body)
        self.assertEqual(L.revision(self.P, self.p, r["id"])["content"], self.body)
        detail = L.detail(self.P, self.p, proposal["id"])
        self.assertIsNone(detail["active_revision_id"])
        self.assertEqual(len(detail["history"]), 2)
        self.assertEqual(detail["jobs"], [])
        with self.assertRaises(ApiError):
            L.propose(self.P, self.p, r["id"], self.body.replace("status: 已确认", "status: 自动确认"), "agent:review")

    def test_source_content_workspace_and_reference_changes_invalidate(self):
        r = self.capture()
        (self.root / "a.py").write_text("def answer(): return 0\n")
        self.assertFalse(L.revision_current(self.P, self.p, r))
        (self.root / "a.py").write_text("def answer(): return 42\n")
        self.page.write_text(self.body + "changed")
        self.assertFalse(L.revision_current(self.P, self.p, r))
        self.page.write_text(self.body)
        self.store.x("UPDATE projects SET root=? WHERE id=?", (self.other["root"], self.p["id"]))
        self.assertFalse(L.revision_current(self.P, self.p, r))
        self.store.x("UPDATE projects SET root=? WHERE id=?", (str(self.root), self.p["id"]))
        with patch.object(L.library, "bindings", return_value=[{"revision": "changed"}]):
            self.assertFalse(L.revision_current(self.P, self.p, r))

    def test_evidence_missing_or_symlink_or_secret_is_not_silently_ignored(self):
        for ref in ("missing.py:1", "secret.pem:1", "../outside.py:1", "link.py:1"):
            self.page.write_text(self.body.replace("a.py:1", ref))
            (self.root / "link.py").unlink(missing_ok=True)
            (self.root / "link.py").symlink_to(self.root / "a.py")
            with self.subTest(ref=ref), self.assertRaises(ApiError):
                self.capture()
        self.assertEqual(self.store.q("SELECT * FROM learning_revisions"), [])

    def test_lesson_full_text_and_status_remain_ledger_owned(self):
        card = learn.add_lesson(self.data, {"project": "APP", "title": "原因", "symptom": "重复事件", "fix": "全字" * 2000, "status": "candidate"})
        r = self.capture("lesson:" + card["id"])
        self.assertEqual(json.loads(r["content"])["fix"], "全字" * 2000)
        learn.set_status(self.data, card["id"], "active", "human")
        self.assertTrue(L.revision_current(self.P, self.p, r))
        learn.edit_lesson(self.data, card["id"], {"fix": "changed"}, "human")
        self.assertFalse(L.revision_current(self.P, self.p, r))

    def test_partial_lesson_proposal_is_a_complete_parent_based_revision(self):
        fields = {"title": "完整经验", "symptom": "重复事件", "cause": "完整根因。" * 3000,
                  "fix": "原改法", "verify": "完整验证。" * 3000, "anti": "不要忽略独立事件",
                  "applicability": "重复回调", "non_applicability": "新业务事件"}
        card = learn.add_lesson(self.data, dict(fields, project="APP", status="candidate"))
        r = self.capture("lesson:" + card["id"])
        proposal = L.propose(self.P, self.p, r["id"], L.encoded({"fix": "修订后的完整改法"}), "writer")
        expected = dict(fields, fix="修订后的完整改法")
        self.assertEqual(json.loads(proposal["content"]), expected)
        self.assertEqual(set(json.loads(proposal["content"])), set(L.LESSON_FIELDS))
        self.assertEqual(proposal["parent_id"], r["id"])
        self.assertEqual(json.loads(L.revision(self.P, self.p, r["id"])["content"]), fields)
        self.assertEqual(learn.lesson(self.data, card["id"])["fix"], "原改法")
        # Explicit invalid edits are not repaired by silently falling back.
        for value in ({"fix": ""}, {"title": " "}, {"verify": 1}, {"status": "active"}):
            with self.subTest(value=value), self.assertRaises(ApiError) as caught:
                L.propose(self.P, self.p, r["id"], L.encoded(value), "writer")
            self.assertEqual(caught.exception.code, 400)

    def test_policy_allowlist_rejects_boolean_unknown_and_out_of_range(self):
        for params in ({"guard": False}, {"context_budget": True}, {"context_budget": 12001}, {}):
            with self.subTest(params=params), self.assertRaises(ApiError):
                L.policy_create(self.P, self.p, "safe", "预算", params, "代码咨询", "writer")
        r = L.policy_create(self.P, self.p, "safe", "预算", {"context_budget": 8000}, "代码咨询", "writer")
        self.assertEqual(r["kind"], "policy")
        self.assertEqual(L.catalog(self.P, self.p, "policy")["items"][0]["human"]["status"], "draft")

    def test_migration_is_repeatable_and_ddl_failure_rolls_back(self):
        r = self.capture()
        L.schema(self.store)
        self.assertEqual(L.revision(self.P, self.p, r["id"])["content"], self.body)
        with patch.object(L, "DDL", ("CREATE TABLE learning_test (id INTEGER)", "INVALID SQL")):
            with self.assertRaises(sqlite3.Error):
                L.schema(self.store)
        self.assertFalse(self.store.db.in_transaction)
        self.assertIsNone(self.store.one("SELECT name FROM sqlite_master WHERE name='learning_test'"))

    def test_registration_failure_does_not_leak_partial_revision(self):
        real = L._save
        def fail(*args):
            real(*args)
            raise RuntimeError("after insert")
        with patch.object(L, "_save", side_effect=fail), self.assertRaises(RuntimeError):
            self.capture()
        self.assertEqual(self.store.q("SELECT * FROM learning_revisions"), [])
        self.assertFalse(self.store.db.in_transaction)


if __name__ == "__main__":
    unittest.main()
