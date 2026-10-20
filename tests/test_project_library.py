"""Real local Git, SQLite and supervised-worker project-library behavior.

Every build runs the shipped worker in its supervised child process. The
20-second test deadline detects a hung synthetic fixture; it does not change
the product's build budget. All repositories and platform storage are temporary.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest

from tmh.platform import project_library as library
from tmh.platform.errors import ApiError
from tmh.platform.store import SCHEMA as PLATFORM_SCHEMA, Store
from tmh.platform.supervised_process import read_receipt


@unittest.skipUnless(os.name == "posix" and shutil.which("git"),
                     "real project builds require POSIX supervision and local Git")
class ProjectLibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-library-test-")
        self.root = Path(self.temp.name).resolve()
        self.empty_template = self.root / "empty-template"
        self.empty_template.mkdir()
        self.store = Store(self.root / "platform" / "platform.db")
        self.platform = SimpleNamespace(store=self.store)
        library.schema(self.store)

    def tearDown(self):
        # Request normal supervised cancellation before closing SQLite or
        # removing its ownership/receipt files, even after an assertion fails.
        for row in self.store.q("SELECT * FROM knowledge_revisions WHERE status IN ('queued','building')"):
            project, rid = self.store.project(row["project_id"]), row["id"]
            if row:
                library.cancel(self.store, project, rid)
                self.wait_terminal(project, rid)
        self.store.db.close()
        self.temp.cleanup()

    def git(self, root, *args, raw=False):
        env = dict(os.environ, GIT_AUTHOR_NAME="Synthetic library test",
                   GIT_AUTHOR_EMAIL="library-test@localhost",
                   GIT_COMMITTER_NAME="Synthetic library test",
                   GIT_COMMITTER_EMAIL="library-test@localhost",
                   GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
        result = subprocess.run(
            ["git", "-C", str(root), "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=" + str(self.empty_template), *args],
            env=env, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        return result.stdout if raw else result.stdout.decode("utf-8").strip()

    def project(self, key, files=None):
        root = self.root / key
        root.mkdir()
        self.git(root, "init", "--template=" + str(self.empty_template))
        for name, content in (files or {
            "modules/approval.py": "def Approval():\n    return 'baseline approval'\n",
            "docs/guide.md": "# Approval\n固定来源的审批规则。\n",
        }).items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", "Synthetic baseline")
        return self.store.add_project(key, key + " 项目", str(root))

    def commit(self, project, message="Synthetic update"):
        self.git(project["root"], "add", "--all")
        self.git(project["root"], "commit", "-m", message)
        return self.git(project["root"], "rev-parse", "HEAD")

    def snapshot(self, project):
        root = Path(project["root"])
        return {
            "head": self.git(root, "rev-parse", "HEAD"),
            "status": self.git(root, "status", "--porcelain=v1", "--untracked-files=all", raw=True),
            "files": {p.relative_to(root).as_posix(): p.read_bytes()
                      for p in root.rglob("*")
                      if p.is_file() and ".git" not in p.relative_to(root).parts},
            "index": (root / ".git" / "index").read_bytes(),
            "config": (root / ".git" / "config").read_bytes(),
        }

    def start(self, project, commit="HEAD"):
        return library.start(self.store, project, commit, "synthetic operator")

    def wait_terminal(self, project, rid, expected=None):
        deadline = time.monotonic() + 20
        result = None
        while time.monotonic() < deadline:
            view = library.view(self.store, self.store.project(project["id"]))
            result = next(r for r in view["revisions"] if r["id"] == rid)
            if result["status"] not in ("queued", "building"):
                break
            time.sleep(.025)
        else:
            self.fail("real knowledge worker did not finish within 20s: %r; scene=%s" % (result, self.root))
        if expected is not None:
            self.assertEqual(result["status"], expected, result)
        row = self.store.one("SELECT * FROM knowledge_revisions WHERE id=?", (rid,))
        attempt = self.root / "platform/project-library/revisions" / rid / "attempts" / row["attempt"]
        owner = json.loads((attempt / "owner.json").read_text())
        receipt = read_receipt(attempt, owner)
        self.assertIsNotNone(receipt, "a database terminal label cannot substitute for a real supervisor receipt")
        self.assertTrue(receipt["cleanup"]["complete"], receipt)
        self.assertFalse(receipt["cleanup"]["remaining_group"], receipt)
        self.assertTrue(receipt["cleanup"]["output_complete"], receipt)
        self.assertTrue((attempt / "supervisor.json").is_file())
        return result

    def build(self, project, commit="HEAD", expected="ready"):
        result = self.start(project, commit)
        return self.wait_terminal(project, result["id"], expected)

    def assert_api_error(self, code, call, *args):
        with self.assertRaises(ApiError) as raised:
            call(*args)
        self.assertEqual(raised.exception.code, code)

    def test_fixed_commit_survives_head_advance_and_dirty_source_is_untouched(self):
        source = self.project("STD")
        original = self.git(source["root"], "rev-parse", "HEAD")
        build = self.start(source)
        path = Path(source["root"]) / "modules/approval.py"
        path.write_text("def Approval():\n    return 'new committed behavior'\n")
        newer = self.commit(source)
        self.assertNotEqual(newer, original)
        path.write_text("def Approval():\n    return 'uncommitted customer draft'\n")
        (Path(source["root"]) / "local-note.txt").write_text("untracked local note")
        before = self.snapshot(source)
        result = self.wait_terminal(source, build["id"], "ready")
        self.assertEqual(result["commit"], original)
        full = library.read(self.store, source, result["id"], "modules/approval.py")
        self.assertEqual(full["commit"], original)
        self.assertEqual(full["content"], "def Approval():\n    return 'baseline approval'\n")
        self.assertEqual(self.snapshot(source), before)
        self.assertFalse((Path(source["root"]) / ".tmh").exists())

    def test_two_same_named_sources_require_scopes_and_revocation_blocks_new_reads(self):
        files = {
            "modules/approval.py": "def Approval():\n    return 'Approval workflow'\n",
            "private/approval.py": "def Approval():\n    return 'Approval internal policy'\n",
            "modules-extra/approval.py": "def Approval():\n    return 'Approval prefix sibling'\n",
        }
        first = self.project("STD", files)
        second = self.project("REF", files)
        customer = self.project("CLIENT")
        one, two = self.build(first), self.build(second)
        for revision in (one, two):
            self.assert_api_error(403, library.reference, self.store, customer, revision["id"], ["modules"], "业务参考", "operator")
            self.assert_api_error(403, library.read, self.store, customer, revision["id"], "modules/approval.py")
        self.assertEqual(library.search(self.store, customer, "Approval")["items"], [])
        for source, revision in ((first, one), (second, two)):
            library.grant(self.store, source, customer["key"], ["modules"], "operator")
            self.assert_api_error(403, library.read, self.store, customer, revision["id"], "modules/approval.py")
            self.assert_api_error(403, library.reference, self.store, customer, revision["id"], [], "扩大到全库", "operator")
            self.assert_api_error(403, library.reference, self.store, customer, revision["id"], ["private"], "越出授权模块", "operator")
            library.reference(self.store, customer, revision["id"], ["modules"], "业务参考", "operator")
        result = library.search(self.store, customer, "Approval", limit=100)
        self.assertEqual({r["source_project"] for r in result["items"]}, {"STD", "REF"})
        self.assertEqual({r["revision_id"] for r in result["items"]}, {one["id"], two["id"]})
        self.assertEqual(len({r["id"] for r in result["items"]}), len(result["items"]))
        self.assertTrue(all(r["path"].startswith("modules/") for r in result["items"]))
        self.assertTrue(all(r["relation"] == "reference" for r in result["items"]))
        self.assertTrue(all("待核对" in r["applicability"] for r in result["items"]))
        for revision in (one, two):
            self.assert_api_error(403, library.read, self.store, customer, revision["id"], "private/approval.py")
            self.assert_api_error(403, library.read, self.store, customer, revision["id"], "modules-extra/approval.py")
        pages = [library.search(self.store, customer, "Approval", limit=1, offset=index)
                 for index in range(result["total"])]
        self.assertEqual([page["items"][0]["id"] for page in pages], [item["id"] for item in result["items"]])
        self.assertTrue(all(page["references_hash"] == result["references_hash"] for page in pages))
        old_hash = result["references_hash"]
        library.act(self.platform, first, {"action": "revoke", "project": "CLIENT"}, "operator")
        self.assert_api_error(403, library.read, self.store, customer, one["id"], "modules/approval.py")
        after = library.search(self.store, customer, "Approval", limit=100)
        self.assertEqual({r["source_project"] for r in after["items"]}, {"REF"})
        self.assertEqual(after["unavailable"][0]["revision_id"], one["id"])
        self.assertNotEqual(after["references_hash"], old_hash)
        with self.assertRaisesRegex(ValueError, "参考知识不可用"):
            library.context(self.store, customer, "Approval")
        binding = next(r for r in library.reference_state(self.store, customer) if r["revision_id"] == two["id"])
        library.unlink(self.store, customer, binding["id"])
        self.assert_api_error(403, library.read, self.store, customer, two["id"], "modules/approval.py")

    def test_full_text_and_original_binary_remain_available_beyond_search_excerpt(self):
        text = "# Approval 原始资料\n" + "审批条件与完整原始说明。" * 250 + "\n最后一段不可丢失。\n"
        raw = bytes(range(256)) * 32
        source = self.project("STD", {"docs/approval.md": text, "assets/example.bin": raw})
        revision = self.build(source)
        hit = next(r for r in library.search(self.store, source, "Approval", limit=100)["items"]
                   if r["path"] == "docs/approval.md")
        self.assertTrue(hit["excerpt_truncated"])
        self.assertLess(len(hit["excerpt"]), len(text))
        full = library.read(self.store, source, revision["id"], hit["path"])
        self.assertEqual(full["encoding"], "utf-8")
        self.assertEqual(full["content"], text)
        self.assertEqual(full["sha256"], hashlib.sha256(text.encode()).hexdigest())
        binary = library.read(self.store, source, revision["id"], "assets/example.bin")
        self.assertEqual(binary["encoding"], "base64")
        self.assertEqual(base64.b64decode(binary["content"], validate=True), raw)
        self.assertEqual(binary["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(any(r["path"] == "assets/example.bin" for r in revision["summary"]["unindexed"]))

    def test_existing_project_defaults_and_role_changes_preserve_identity(self):
        project = self.project("LEGACY")
        self.assertEqual(library.profile(self.store, project), {"roles": [], "workflow": "development"})
        before = self.snapshot(project)
        configured = library.configure(self.store, project, ["product", "reference"], "reference")
        self.assertEqual(configured, {"roles": ["product", "reference"], "workflow": "reference"})
        self.assertEqual(self.store.project("LEGACY"), project)
        self.assertEqual(self.snapshot(project), before)
        with self.assertRaisesRegex(ValueError, "仅供知识查阅"):
            library.require_development(self.store, project)
        self.assert_api_error(409, library.configure, self.store, project, ["product"], "development")
        for roles in (["product", "product"], ["admin"], "reference"):
            self.assert_api_error(400, library.configure, self.store, project, roles, "reference")

    def test_legacy_store_without_library_tables_is_migrated_without_replacing_project(self):
        source = self.project("STD")
        path = self.root / "legacy-platform.db"
        database = sqlite3.connect(path)
        try:
            database.executescript(PLATFORM_SCHEMA)
            database.execute("INSERT INTO projects(id,key,name,root,description,created) VALUES(?,?,?,?,?,?)",
                             (37, "OLD", "已有老项目", source["root"], "保留原说明", "2025-01-02 03:04:05"))
            database.commit()
            self.assertIsNone(database.execute("SELECT name FROM sqlite_master WHERE name='project_profiles'").fetchone())
        finally:
            database.close()
        legacy = Store(path)
        try:
            project = legacy.project("OLD")
            self.assertEqual(project, {"id": 37, "key": "OLD", "name": "已有老项目", "root": source["root"],
                                       "description": "保留原说明", "created": "2025-01-02 03:04:05"})
            self.assertEqual(library.profile(legacy, project), {"roles": [], "workflow": "development"})
            before = self.snapshot(project)
            view = library.view(legacy, project)
            self.assertEqual(view["project"], project)
            self.assertEqual(legacy.project("OLD"), project)
            self.assertEqual(view["profile"], {"roles": [], "workflow": "development"})
            self.assertEqual(view["revisions"], [])
            self.assertEqual(view["references"], [])
            self.assertEqual(len(view["sources"]), 1)
            self.assertEqual(view["sources"][0]["root"], source["root"])
            # Explicit registration remains idempotent after the old root
            # has been mapped by the additive Store migration.
            mapped = library.source(legacy, project)
            self.assertEqual(mapped["root"], source["root"])
            self.assertEqual(mapped["project_id"], project["id"])
            self.assertEqual(library.source(legacy, project)["id"], mapped["id"])
            self.assertEqual([s["id"] for s in library.view(legacy, project)["sources"]], [mapped["id"]])
            self.assertEqual(self.snapshot(project), before)
        finally:
            legacy.db.close()

    def test_derivation_imports_exact_baseline_into_independent_customer_workspaces(self):
        source = self.project("STD")
        library.configure(self.store, source, ["product", "reference"], "reference")
        revision = self.build(source)
        before = self.snapshot(source)
        outputs = [library.derive(self.store, source, revision["id"], key, key + " 客户", "operator")
                   for key in ("CLIENTA", "CLIENTB")]
        self.assertEqual(len({r["project"]["id"] for r in outputs}), 2)
        for result in outputs:
            project = result["project"]
            self.assertNotEqual(project["id"], source["id"])
            self.assertNotEqual(project["root"], source["root"])
            self.assertFalse(result["human_accepted"])
            self.assertEqual(result["source_commit"], revision["commit"])
            self.assertEqual(self.git(project["root"], "rev-parse", "HEAD"), result["commit"])
            self.assertEqual(self.git(project["root"], "rev-parse", "HEAD^{tree}"),
                             self.git(source["root"], "rev-parse", revision["commit"] + "^{tree}"))
            self.assertEqual(self.git(project["root"], "remote"), "")
            refs = library.reference_state(self.store, project)
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["revision_id"], revision["id"])
            self.assertTrue(refs[0]["available"])
            original = Path(source["root"]) / "modules/approval.py"
            copied = Path(project["root"]) / "modules/approval.py"
            self.assertEqual(copied.read_bytes(), original.read_bytes())
            self.assertNotEqual(copied.stat().st_ino, original.stat().st_ino)
        first, second = (r["project"] for r in outputs)
        untouched = self.snapshot(second)
        (Path(first["root"]) / "modules/approval.py").write_text("def Approval():\n    return 'customer exception'\n")
        self.commit(first)
        compared = library.compare(self.store, first, revision["id"])
        self.assertEqual(compared["base_commit"], revision["commit"])
        self.assertEqual(compared["changed"], [{"path": "modules/approval.py", "status": "changed"}])
        self.assertEqual(self.snapshot(source), before)
        self.assertEqual(self.snapshot(second), untouched)

    def test_maintenance_retains_project_id_history_and_fixed_references(self):
        source, customer = self.project("STD"), self.project("CLIENT")
        library.configure(self.store, source, ["product", "reference"], "reference")
        revision = self.build(source)
        library.grant(self.store, source, "CLIENT", [], "operator")
        library.reference(self.store, customer, revision["id"], [], "固定旧版", "operator")
        before = self.snapshot(source)
        result = library.derive(self.store, source, revision["id"], None, None, "operator", maintain=True)
        maintained = result["project"]
        self.assertEqual((maintained["id"], maintained["key"], maintained["created"]),
                         (source["id"], source["key"], source["created"]))
        self.assertNotEqual(maintained["root"], source["root"])
        self.assertEqual(library.profile(self.store, maintained),
                         {"roles": ["product", "reference"], "workflow": "development"})
        library.require_development(self.store, maintained)
        self.assertEqual(library.read(self.store, customer, revision["id"], "modules/approval.py")["commit"], revision["commit"])
        self.assertEqual(library.view(self.store, maintained)["revisions"][0]["id"], revision["id"])
        self.assertTrue(any(s["root"] == source["root"] for s in library.view(self.store, maintained)["sources"]))
        self.assertEqual(self.snapshot(source), before)
        self.assert_api_error(409, library.derive, self.store, maintained, revision["id"], None, None, "operator", True)

    def test_failed_real_worker_keeps_previous_ready_revision_readable(self):
        source = self.project("STD")
        ready = self.build(source)
        # A committed path rejected by the snapshot boundary makes the real
        # worker fail during export, without mocking its child or supervision.
        (Path(source["root"]) / "invalid:path.txt").write_text("unusable source path")
        self.commit(source)
        before = self.snapshot(source)
        failed = self.build(source, expected="failed")
        self.assertNotEqual(failed["id"], ready["id"])
        self.assertIn("路径", failed["error"])
        versions = library.view(self.store, source)["revisions"]
        self.assertEqual({r["id"]: r["status"] for r in versions},
                         {ready["id"]: "ready", failed["id"]: "failed"})
        self.assertEqual({r["revision_id"] for r in library.search(self.store, source, "Approval")["items"]}, {ready["id"]})
        full = library.read(self.store, source, ready["id"], "modules/approval.py")
        self.assertEqual(full["content"], "def Approval():\n    return 'baseline approval'\n")
        self.assert_api_error(409, library.read, self.store, source, failed["id"], "modules/approval.py")
        self.assertEqual(self.snapshot(source), before)
        self.assert_api_error(409, library.resume, self.store, source, ready["id"])

    def test_compare_reports_add_delete_change_and_never_updates_the_reference(self):
        source = self.project("STD")
        revision = self.build(source)
        baseline = library.compare(self.store, source, revision["id"])
        self.assertEqual(baseline["changed"], [])
        root = Path(source["root"])
        (root / "modules/approval.py").write_text("def Approval():\n    return 'changed'\n")
        (root / "docs/guide.md").unlink()
        (root / "docs/new.md").write_text("# Newly added rule\n")
        newer = self.commit(source)
        compared = library.compare(self.store, source, revision["id"])
        self.assertEqual(compared["base_commit"], revision["commit"])
        self.assertEqual(compared["current_commit"], newer)
        self.assertEqual(compared["changed"], [
            {"path": "docs/guide.md", "status": "deleted"},
            {"path": "docs/new.md", "status": "added"},
            {"path": "modules/approval.py", "status": "changed"},
        ])
        self.assertEqual(library.read(self.store, source, revision["id"], "docs/guide.md")["content"],
                         "# Approval\n固定来源的审批规则。\n")
        self.assertEqual(library.view(self.store, source)["revisions"][0]["commit"], revision["commit"])

    def test_scope_only_reference_cannot_be_used_as_a_complete_derived_baseline(self):
        source, customer = self.project("STD"), self.project("CLIENT")
        revision = self.build(source)
        library.grant(self.store, source, "CLIENT", ["modules"], "operator")
        library.reference(self.store, customer, revision["id"], ["modules"], "模块参考", "operator")
        before = self.snapshot(source)
        self.assert_api_error(409, library.derive, self.store, customer, revision["id"], "COPY", "不完整派生", "operator")
        self.assertIsNone(self.store.project("COPY"))
        self.assertEqual(self.snapshot(source), before)

    def test_resume_runs_a_new_supervised_attempt_without_rewriting_fixed_input(self):
        source = self.project("STD", {"invalid:path.txt": "unsupported path"})
        first = self.build(source, expected="failed")
        old_row = self.store.one("SELECT * FROM knowledge_revisions WHERE id=?", (first["id"],))
        folder = self.root / "platform/project-library/revisions" / first["id"]
        fixed_request = (folder / "request.json").read_bytes()
        # Repairing HEAD cannot make a failed fixed revision silently mean
        # another commit. A resumed attempt must still fail on its old input.
        (Path(source["root"]) / "invalid:path.txt").rename(Path(source["root"]) / "valid-path.txt")
        self.commit(source)
        resumed = library.resume(self.store, source, first["id"])
        self.assertEqual(resumed["id"], first["id"])
        second = self.wait_terminal(source, first["id"], "failed")
        new_row = self.store.one("SELECT * FROM knowledge_revisions WHERE id=?", (first["id"],))
        self.assertNotEqual(new_row["attempt"], old_row["attempt"])
        self.assertEqual(second["commit"], first["commit"])
        self.assertEqual((folder / "request.json").read_bytes(), fixed_request)
        self.assertEqual(len(list((folder / "attempts").iterdir())), 2)
        fresh = self.build(source)
        self.assertNotEqual(fresh["id"], first["id"])
        self.assertEqual(library.read(self.store, source, fresh["id"], "valid-path.txt")["content"], "unsupported path")


if __name__ == "__main__":
    unittest.main()
