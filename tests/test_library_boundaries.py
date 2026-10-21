"""Reference/workflow boundaries with real temporary Git and SQLite inputs.

Knowledge snapshots use the real supervised worker and its cleanup receipts.
Preview execution is forbidden at the Git/Popen seams; the delayed caller uses
an Event, not a timing sleep. Runner prompt generation and reference reads stay
real, while its final thread scheduling is intercepted so no model can run even
if a regression admits an invalid task. No HTTP or daily service is started.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import sqlite_compat
from tests import test_project_library as library_fixtures
from tmh.platform import agents, preview, project_library as library
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


@unittest.skipUnless(os.name == "posix" and shutil.which("git"),
                     "boundary snapshots require POSIX supervision and local Git")
class LibraryBoundariesTest(unittest.TestCase):
    # Reuse helpers only; subclassing the fixture TestCase would discover its
    # backend tests again in this module.
    setUp = library_fixtures.ProjectLibraryTest.setUp
    tearDown = library_fixtures.ProjectLibraryTest.tearDown
    git = library_fixtures.ProjectLibraryTest.git
    project = library_fixtures.ProjectLibraryTest.project
    commit = library_fixtures.ProjectLibraryTest.commit
    snapshot = library_fixtures.ProjectLibraryTest.snapshot
    start = library_fixtures.ProjectLibraryTest.start
    wait_terminal = library_fixtures.ProjectLibraryTest.wait_terminal
    build = library_fixtures.ProjectLibraryTest.build

    def reference(self, source, customer, revision, scopes=None, purpose="Approval reference"):
        library.grant(self.store, source, customer["key"], [], "fixture operator")
        return library.reference(self.store, customer, revision["id"], scopes or [], purpose, "fixture operator")

    def runner(self):
        (self.store.path.parent / "agents.json").write_text(json.dumps({"synthetic": {
            "cmd": [sys.executable, "-c", "raise AssertionError('must not invoke a model')"]}}))
        return agents.Runner(self.store, self.store.path.parent)

    def scoped_pair(self):
        source = self.project("STD", {
            "docs/a/rules.txt": "Approval ONLY_BINDING_A original business rules\n",
            "docs/b/rules.txt": "Approval ONLY_BINDING_B different business rules\n",
        })
        customer = self.project("CLIENT")
        revision = self.build(source)
        self.reference(source, customer, revision, ["docs/a"], "binding A")

        def use_binding(label):
            return library.reference(self.store, customer, revision["id"],
                                     ["docs/" + label.lower()], "binding " + label, "fixture operator")

        return source, customer, revision, use_binding

    def test_delayed_preview_rechecks_workflow_before_git_or_process_start(self):
        project = self.project("REF")
        data = self.store.path.parent
        platform = SimpleNamespace(store=self.store, data_dir=data)
        preview.set_conf(data, project["key"], "must-not-run-preview", by="fixture operator")
        before = self.snapshot(project)
        queued, release, finished = threading.Event(), threading.Event(), threading.Event()
        errors, results = [], []

        def delayed_callback():
            queued.set()
            try:
                if not release.wait(3):
                    raise AssertionError("fixture callback was never released")
                # Deliberately retain the project dict captured before configure.
                results.append(preview.start(platform, project, {"key": "REF-main"}, "HEAD", "delayed release"))
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        thread = threading.Thread(target=delayed_callback, daemon=True)
        with patch.object(preview, "git", side_effect=AssertionError("reference preview must not invoke Git")) as git_call, \
                patch.object(preview.subprocess, "Popen", side_effect=AssertionError("reference preview must not spawn")) as spawn:
            thread.start()
            try:
                self.assertTrue(queued.wait(2), "callback must be queued before workflow transition")
                library.configure(self.store, project, ["reference"], "reference")
                release.set()
                self.assertTrue(finished.wait(2), "a rejected preview must finish without background work")
            finally:
                release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results, [])
            self.assertEqual(len(errors), 1, errors)
            self.assertIsInstance(errors[0], ValueError)
            self.assertIn("仅供知识查阅", str(errors[0]))
            git_call.assert_not_called()
            spawn.assert_not_called()
        self.assertEqual(preview._load(data), {})
        self.assertEqual(self.snapshot(project), before)

    def test_workflow_switch_refuses_starting_and_up_previews_of_same_project(self):
        project = self.project("REF")
        data = self.store.path.parent
        for state in ("starting", "up"):
            with self.subTest(state=state):
                record = {"REF-main": {"project": project["key"], "state": state, "pid": 0}}
                preview._save(data, record)
                with self.assertRaises(ApiError) as raised:
                    library.configure(self.store, project, ["reference"], "reference")
                self.assertEqual(raised.exception.code, 409)
                self.assertIn("预览", str(raised.exception))
                self.assertEqual(library.profile(self.store, project)["workflow"], "development")
                self.assertEqual(preview._load(data), record)
        # No synthetic PID is started or signalled. Stopped records and another
        # project's live record must not prevent this project's transition.
        preview._save(data, {"REF-main": {"project": "REF", "state": "stopped", "pid": 0},
                             "OTHER-main": {"project": "OTHER", "state": "up", "pid": 0}})
        configured = library.configure(self.store, project, ["reference"], "reference")
        self.assertEqual(configured["workflow"], "reference")

    def test_workflow_can_change_during_prompt_but_cannot_register_that_run(self):
        project = self.project("REF")
        other = Store(self.store.path)
        runner = self.runner()
        real_prompt = agents.build_prompt
        prepared = []

        def change_after_prompt(*args, **kwargs):
            prompt = real_prompt(*args, **kwargs)
            prepared.append(prompt)
            # This independent connection must be able to change workflow while
            # the caller is still preparing. Registration must recheck it.
            library.configure(other, project, ["reference"], "reference")
            return prompt

        try:
            with patch.object(agents, "build_prompt", side_effect=change_after_prompt), \
                    patch.object(agents.threading, "Thread") as launch:
                with self.assertRaisesRegex(ValueError, "仅供知识查阅"):
                    runner.start(project, None, "synthetic", "ask", "fixture operator", question="Approval")
                launch.assert_not_called()
            self.assertEqual(len(prepared), 1)
            self.assertEqual(library.profile(other, project)["workflow"], "reference")
            self.assertEqual(self.store.runs(project_id=project["id"]), [])
            self.assertEqual(self.store.q("SELECT * FROM knowledge_run_inputs"), [])
            self.assertEqual(runner.owners, {})
            self.assertFalse(self.store.db.in_transaction)
        finally:
            for rid in list(runner.owners):
                runner._release(rid)
            other.db.close()

    def test_workflow_and_run_registration_hold_writer_across_check_and_publication(self):
        for first in ("run", "workflow"):
            with self.subTest(first=first):
                project = self.project("RUN" if first == "run" else "FLOW")
                other = Store(self.store.path)
                checked, release = threading.Event(), threading.Event()
                values, errors = [], []
                real_profile = library.profile

                def pause_after_read(store, current):
                    value = real_profile(store, current)
                    if store is self.store and current['id'] == project['id'] and not checked.is_set():
                        checked.set()
                        if not release.wait(3):
                            raise AssertionError("workflow read was never released")
                    return value

                def first_operation():
                    try:
                        if first == "run":
                            values.append(self.store.create_run(project['id'], None, "synthetic", "ask", "fixture", "prompt"))
                        else:
                            values.append(library.configure(self.store, project, ["reference"], "reference"))
                    except BaseException as exc:
                        errors.append(exc)

                thread = threading.Thread(target=first_operation, daemon=True)
                try:
                    with patch.object(library, "profile", side_effect=pause_after_read):
                        thread.start()
                        try:
                            self.assertTrue(checked.wait(2), "first operation must reach its real workflow read")
                            # A zero-wait lock probe on a separate connection
                            # checks actual SQLite ownership, without timing a
                            # sleep or extending the production busy timeout.
                            other.db.execute("PRAGMA busy_timeout=0")
                            with self.assertRaises(sqlite3.OperationalError) as locked:
                                other.db.execute("BEGIN IMMEDIATE")
                            self.assertTrue(sqlite_compat.is_busy(locked.exception), locked.exception)
                            self.assertFalse(other.db.in_transaction)
                        finally:
                            release.set()
                            thread.join(2)
                        self.assertFalse(thread.is_alive())
                    self.assertEqual(errors, [])
                    self.assertEqual(len(values), 1)
                    self.assertFalse(self.store.db.in_transaction)
                    if first == "run":
                        with self.assertRaisesRegex(ApiError, "项目仍有运行"):
                            library.configure(other, project, ["reference"], "reference")
                        self.assertEqual(library.profile(other, project)["workflow"], "development")
                        self.assertEqual(other.run(values[0]['id'])["status"], "queued")
                    else:
                        with self.assertRaisesRegex(ValueError, "仅供知识查阅"):
                            other.create_run(project['id'], None, "synthetic", "ask", "fixture", "prompt")
                        self.assertEqual(other.runs(project_id=project['id']), [])
                    self.assertFalse(other.db.in_transaction)
                    # Rejections must release their writer transaction too.
                    other.db.execute("BEGIN IMMEDIATE")
                    other.db.rollback()
                finally:
                    release.set()
                    other.db.rollback()
                    thread.join(2)
                    other.db.close()

    def test_prompt_for_old_workspace_cannot_launch_after_reference_then_maintain(self):
        project = self.project("STD")
        revision = self.build(project)
        other = Store(self.store.path)
        runner = self.runner()
        real_prompt = agents.build_prompt
        workspaces = []

        def change_after_prompt(*args, **kwargs):
            prompt = real_prompt(*args, **kwargs)
            library.configure(other, project, ["product"], "reference")
            workspaces.append(library.derive(other, project, revision['id'], "", "", "fixture operator", maintain=True))
            return prompt

        try:
            with patch.object(agents, "build_prompt", side_effect=change_after_prompt), \
                    patch.object(agents.threading, "Thread") as launch:
                with self.assertRaisesRegex(ValueError, "项目工作区已变化"):
                    runner.start(project, None, "synthetic", "ask", "fixture operator", question="Approval")
                launch.assert_not_called()
            self.assertEqual(len(workspaces), 1)
            self.assertNotEqual(other.project(project['id'])['root'], project['root'])
            self.assertEqual(library.profile(other, project)["workflow"], "development")
            self.assertEqual(self.store.runs(project_id=project['id']), [])
            self.assertEqual(self.store.q("SELECT * FROM knowledge_run_inputs"), [])
            self.assertEqual(runner.owners, {})
            self.assertFalse(self.store.db.in_transaction)
        finally:
            for rid in list(runner.owners):
                runner._release(rid)
            other.db.close()

    def test_new_unrelated_plan_cannot_validate_stale_pinned_delivery_plan(self):
        source, customer = self.project("STD"), self.project("CLIENT")
        revision_a = self.build(source)
        binding_a = self.reference(source, customer, revision_a)
        ticket = self.store.create_ticket(customer["id"], "Approval delivery", "fixture operator")

        def completed_plan(label):
            run = self.store.create_run(customer["id"], ticket["id"], "synthetic", "plan", "fixture operator", label)
            library.bind_run(self.store, customer, run["id"], library.bindings(self.store, customer))
            self.store.update_run(run["id"], status="done", exit_code=0, result=label)
            return self.store.run(run["id"])

        plan_a = completed_plan("Pinned reviewed plan A")
        ticket = self.store.update_ticket(ticket["id"], "fixture operator", links={"delivery_plan_run": plan_a["id"]})
        self.assertEqual(agents.reviewed_delivery_plan(self.store, ticket)["id"], plan_a["id"])
        (Path(source["root"]) / "modules/approval.py").write_text("def Approval():\n    return 'new source revision B'\n")
        self.commit(source)
        revision_b = self.build(source)
        self.assertNotEqual(revision_a["id"], revision_b["id"])
        library.unlink(self.store, customer, binding_a["id"])
        self.reference(source, customer, revision_b)
        plan_b = completed_plan("Newer unrelated plan B")
        self.assertEqual(self.store.runs(ticket_id=ticket["id"])[0]["id"], plan_b["id"])
        self.assertFalse(library.run_current(self.store, customer, plan_a["id"]))
        self.assertTrue(library.run_current(self.store, customer, plan_b["id"]))
        with self.assertRaisesRegex(ValueError, "知识版本、范围或授权已变化"):
            agents.reviewed_delivery_plan(self.store, self.store.ticket(ticket["id"]))
        self.assertEqual(self.store.ticket(ticket["id"])["links"]["delivery_plan_run"], plan_a["id"])
        explicit_b = dict(ticket, links={"delivery_plan_run": plan_b["id"]})
        self.assertEqual(agents.reviewed_delivery_plan(self.store, explicit_b)["id"], plan_b["id"])

    def test_runner_rejects_completed_search_for_b_after_binding_is_restored_to_a(self):
        _, customer, _, use_binding = self.scoped_pair()
        original_a = library.bindings(self.store, customer)
        real_search = library.search
        completed_searches = []

        def search_b_then_restore_a(*args, **kwargs):
            use_binding("B")
            try:
                result = real_search(*args, **kwargs)
                # The original method must finish under B before restoring A.
                self.assertFalse(result["partial"], result)
                self.assertTrue(result["items"])
                self.assertTrue(all(hit["path"].startswith("docs/b/") for hit in result["items"]))
                self.assertIn("ONLY_BINDING_B", result["items"][0]["excerpt"])
                self.assertNotEqual(result["references_hash"], library.digest(original_a))
                completed_searches.append(result)
                return result
            finally:
                use_binding("A")

        runner = self.runner()
        previous = self.store.runs(project_id=customer["id"])
        try:
            with patch.object(library, "search", side_effect=search_b_then_restore_a) as search_call, \
                    patch.object(agents.threading, "Thread") as worker_thread:
                with self.assertRaisesRegex(ValueError, "参考版本与运行输入不同"):
                    runner.start(customer, None, "synthetic", "ask", "fixture operator", question="Approval")
                self.assertEqual(search_call.call_count, 1)
                worker_thread.assert_not_called()
            self.assertEqual(len(completed_searches), 1)
            self.assertEqual(library.bindings(self.store, customer), original_a)
            self.assertEqual(self.store.runs(project_id=customer["id"]), previous)
            self.assertEqual(self.store.q("SELECT * FROM knowledge_run_inputs"), [])
            self.assertEqual(runner.owners, {})
        finally:
            # A broken implementation may register a run before reaching the
            # scheduling seam. Release its fixture-only ownership on failure.
            for rid in list(runner.owners):
                runner._release(rid)

    def test_search_does_not_label_b_snapshot_with_restored_a_hash(self):
        _, customer, _, use_binding = self.scoped_pair()
        binding_a = library.bindings(self.store, customer)
        use_binding("B")
        binding_b = library.bindings(self.store, customer)
        real_read_scope = library._read_scope
        reads = []

        def restore_after_scope_read(*args, **kwargs):
            value = real_read_scope(*args, **kwargs)
            self.assertEqual(value[2], ["docs/b"])
            reads.append(value[0]["id"])
            use_binding("A")
            return value

        with patch.object(library, "_read_scope", side_effect=restore_after_scope_read):
            result = library.search(self.store, customer, "Approval", references_only=True)
        self.assertEqual(len(reads), 1)
        self.assertEqual(library.bindings(self.store, customer), binding_a)
        self.assertEqual(result["references_hash"], library.digest(binding_b))
        self.assertNotEqual(result["references_hash"], library.digest(binding_a))
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertTrue(result["partial"])
        self.assertTrue(any("检索期间已变化" in item["reason"] for item in result["unavailable"]), result)

    def test_tied_results_cross_twenty_item_pages_without_duplicates_or_omissions(self):
        files = {"docs/doc-%02d.txt" % index: "uniformtoken identical score\n" for index in range(35)}
        first, second, customer = self.project("STD", files), self.project("REF", files), self.project("CLIENT")
        revisions = [(first, self.build(first)), (second, self.build(second))]
        for source, revision in revisions:
            self.reference(source, customer, revision, ["docs"])
        all_results = library.search(self.store, customer, "uniformtoken", limit=100)
        self.assertFalse(all_results["partial"], all_results)
        self.assertEqual(all_results["total"], 70)
        self.assertEqual(len(all_results["items"]), 70)
        self.assertEqual({hit["score"] for hit in all_results["items"]}, {1})
        self.assertEqual({(hit["source_project"], hit["path"]) for hit in all_results["items"]},
                         {(source["key"], name) for source, _ in revisions for name in files})
        page_items = []
        for offset in range(0, 80, 20):
            page = library.search(self.store, customer, "uniformtoken", limit=20, offset=offset)
            self.assertFalse(page["partial"], page)
            self.assertEqual(page["total"], 70)
            self.assertEqual(page["references_hash"], all_results["references_hash"])
            self.assertEqual(len(page["items"]), min(20, 70 - offset))
            page_items.extend(page["items"])
        ids = [hit["id"] for hit in page_items]
        self.assertEqual(ids, [hit["id"] for hit in all_results["items"]])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(library.search(self.store, customer, "uniformtoken", limit=20, offset=70)["items"], [])

    def test_reserved_knowledge_root_file_cannot_publish_a_revision(self):
        for index, filename in enumerate(("@knowledge", "@Knowledge")):
            with self.subTest(filename=filename):
                source = self.project("BAD" + str(index), {filename: "Approval reserved-root collision\n",
                                                         "docs/allowed.txt": "Approval ordinary documentation\n"})
                before = self.snapshot(source)
                revision = self.build(source, expected="failed")
                self.assertIn("保留命名空间 @knowledge", revision["error"])
                folder = library._folder(self.store, revision["id"])
                self.assertFalse((folder / "result.json").exists())
                self.assertFalse((folder / "index.db").exists())
                row = library._row(self.store, revision["id"])
                self.assertEqual(row["digest"], "")
                with self.assertRaises(ApiError) as raised:
                    library.read(self.store, source, revision["id"], filename)
                self.assertEqual(raised.exception.code, 409)
                self.assertEqual(library.search(self.store, source, "Approval")["items"], [])
                self.assertEqual(self.snapshot(source), before)


if __name__ == "__main__":
    unittest.main()
