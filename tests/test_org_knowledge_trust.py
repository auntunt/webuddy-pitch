"""Plain project notes remain discoverable without inventing human confirmation."""
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh import cli
from tmh.platform import memory, org_knowledge as org
from tmh.platform.store import Store


class OrgKnowledgeTrustTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="org-knowledge-trust-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name).resolve()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.root = self.data / "repo"
        self.kdir = self.root / ".tmh" / "knowledge"
        self.kdir.mkdir(parents=True)
        self.project = self.store.add_project("APP", "合成项目", str(self.root))
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)

    def write_notes(self):
        files = {
            "glossary.md": "# 术语表\r\n\r\n| 业务词 | 代码 / 表 | 说明 |\r\n|---|---|---|\r\n| 审批 | approve | 尚未经人工确认的解释 |\r\n\r\n完整补充原文。\r\n",
            "decisions.md": "# 决策\n\n- 审批规则：尚未经人工确认的决定。\n\n非列表原文保留。\n",
            "pitfalls.md": "# 经验\n\n- 审批风险：尚未经人工确认的经验。\n\n原始补充说明保留。\n",
        }
        for name, text in files.items():
            (self.kdir / name).write_bytes(text.encode("utf-8"))
        return {name: text.encode("utf-8") for name, text in files.items()}

    def assert_pending(self, items):
        self.assertEqual(len(items), 3)
        for item in items:
            self.assertEqual(item["status"], "待确认", item)
            self.assertIs(item["reviewed"], False, item)
            for source in item["provenance"]:
                self.assertEqual(source["status"], "待确认")
                self.assertIs(source["confirmed"], False)

    def test_actual_file_parsers_keep_all_three_sources_unconfirmed_and_readonly(self):
        originals = self.write_notes()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.kdir.iterdir()}
        built = org.build(self.store)
        self.assert_pending(built["items"])
        self.assertEqual({p["ref"] for i in built["items"] for p in i["provenance"]}, set(originals))
        self.assert_pending(org.search(self.store, "审批"))
        for item in built["items"]:
            source = item["provenance"][0]
            self.assertEqual(source["content_sha256"], hashlib.sha256(originals[source["ref"]]).hexdigest())
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.kdir.iterdir()})

    def test_status_claims_in_plain_files_or_page_registry_cannot_confirm_notes(self):
        self.write_notes()
        # These files have no human-confirmation route. Self-reported names,
        # copied learning state and page metadata must not supply one.
        registry = {}
        for name in ("glossary.md", "decisions.md", "pitfalls.md"):
            path = self.kdir / name
            path.write_bytes(("---\nid: " + name + "\nstatus: 已确认\nconfirmed_by: reviewer\n---\n").encode() + path.read_bytes())
            registry[name] = {"status": "已确认", "confirmed_by": "reviewer", "learning": {
                "confirmed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "pending": ""}}
        (self.kdir / ".pages.json").write_text(json.dumps(registry), encoding="utf-8")
        self.assert_pending(org.build(self.store)["items"])

    def test_matching_page_and_lesson_cannot_lend_confirmation_to_plain_note(self):
        page = "---\nid: index\ntitle: 审批\nstatus: 已确认\n---\n需要人工核验之后发布。"
        (self.kdir / "index.md").write_text(page, encoding="utf-8")
        (self.kdir / ".pages.json").write_text(json.dumps({"index": {
            "status": "已确认", "confirmed_by": "human-reviewer", "learning": {
                "confirmed_sha256": hashlib.sha256(page.encode()).hexdigest(), "pending": ""}}}), encoding="utf-8")
        (self.data / "lessons.jsonl").write_text(json.dumps({"id": "L1", "project": "APP", "status": "active",
            "symptom": "审批", "anti": "需要人工核验之后发布。", "by": "human-reviewer"}, ensure_ascii=False) + "\n", encoding="utf-8")
        (self.kdir / "decisions.md").write_text("- 审批 需要人工核验之后发布。\n", encoding="utf-8")
        result = org.build(self.store)["items"]
        self.assertEqual(len(result), 2, result)
        confirmed, pending = sorted(result, key=lambda item: not item["reviewed"])
        self.assertEqual(confirmed["status"], "已确认")
        self.assertEqual({p["kind"] for p in confirmed["provenance"]}, {"page", "lesson"})
        self.assertTrue(all(p["confirmed"] for p in confirmed["provenance"]))
        self.assertEqual(pending["status"], "待确认")
        self.assertFalse(pending["reviewed"])
        self.assertEqual([p["kind"] for p in pending["provenance"]], ["doc"])
        self.assertNotEqual(confirmed["dedup_key"], pending["dedup_key"])
        # Exact-content confirmation on the page still invalidates on change.
        (self.kdir / "index.md").write_text(page + "\n后来修改。", encoding="utf-8")
        self.assertEqual(next(p for p in org._pages(self.kdir) if p["id"] == "index")["status"], "需更新")
        remaining = org.build(self.store)["items"]
        self.assertEqual(len(remaining), 2)
        self.assertEqual([p["kind"] for i in remaining if i["reviewed"] for p in i["provenance"]], ["lesson"])

    def test_note_edit_changes_exact_content_identity_without_inheriting_confirmation(self):
        originals = self.write_notes()
        before = org.build(self.store)["items"]
        for name, data in originals.items():
            (self.kdir / name).write_bytes(data + "\n更新完整说明；尚待确认。\n".encode())
        after = org.build(self.store)["items"]
        self.assert_pending(after)
        before_hashes = {p["ref"]: p["content_sha256"] for i in before for p in i["provenance"]}
        for item in after:
            source = item["provenance"][0]
            self.assertNotEqual(source["content_sha256"], before_hashes[source["ref"]])
            self.assertEqual(source["content_sha256"], hashlib.sha256((self.kdir / source["ref"]).read_bytes()).hexdigest())

    def test_merge_missing_or_conflicting_status_never_defaults_to_confirmed(self):
        for extra in ({}, {"status": "已确认"}):
            with self.subTest(extra=extra):
                item = org._merge([{"type": "rule", "title": "待核验规则", "summary": "尚未核验", "dedup_text": "尚未核验",
                    "provenance": {"project": "APP", "confirmed": False}, **extra}])[0]
                self.assertEqual(item["status"], "待确认")
                self.assertFalse(item["reviewed"])
                self.assertIs(item["provenance"][0]["confirmed"], False)

    def test_memory_and_cli_json_preserve_unconfirmed_source_status(self):
        self.write_notes()
        for scope in ({}, {"project": "APP"}):
            self.assert_pending(memory.dispatch_read(self.P, {"section": "knowledge", **scope}, "reader")["knowledge"])
        output = io.StringIO()
        args = SimpleNamespace(type=None, limit=20, q="审批", json=True)
        with patch.object(cli, "_platform_store", return_value=self.store), contextlib.redirect_stdout(output):
            self.assertEqual(cli.cmd_platform_org_knowledge(args), 0)
        self.assert_pending(json.loads(output.getvalue())["items"])

    def test_real_cli_readback_reports_pending_notes_without_rewriting_sources(self):
        originals = self.write_notes()
        result = subprocess.run([sys.executable, "-m", "tmh", "platform", "--data", str(self.data),
                                 "org-knowledge", "--q", "审批", "--json"],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_pending(json.loads(result.stdout)["items"])
        self.assertEqual(originals, {name: (self.kdir / name).read_bytes() for name in originals})


if __name__ == "__main__":
    unittest.main()
