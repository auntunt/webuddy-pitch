"""Independent candidate-Git and method-reachability checks; never execute a model."""
import hashlib
import importlib
import subprocess
import tempfile
import unittest
from pathlib import Path


BASE = '''from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def make_server(address):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            return self.get()
        def get(self):
            return "HOME"
        def do_POST(self):
            return self.post()
        def post(self):
            return self.save()
        def save(self):
            return "SAVED_BASE"
        def unused(self):
            return "UNUSED_BASE"
    return ThreadingHTTPServer(address, Handler)
'''


class IndependentPythonPathMapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-python-path-independent-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {"id": 1, "key": "PYMAP", "root": str(self.root)}
        self.git("init", "-q")
        self.git("config", "user.name", "independent-fixture")
        self.git("config", "user.email", "fixture@localhost")
        self.pathmap = importlib.import_module("tmh.platform.pathmap")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True, stderr=subprocess.PIPE).strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, text):
        self.git("add", ".")
        self.git("commit", "-qm", text)
        return self.git("rev-parse", "HEAD")

    def fixture(self, before=BASE, after=None, extra_before=None, extra_after=None):
        self.write("app.py", before)
        for path, value in (extra_before or {}).items():
            self.write(path, value)
        self.base = self.commit("baseline")
        self.write("app.py", after if after is not None else before.replace("SAVED_BASE", "SAVED_CANDIDATE"))
        for path, value in (extra_after or {}).items():
            self.write(path, value)
        self.candidate = self.commit("candidate")
        diff = subprocess.check_output(["git", "-C", str(self.root), "diff", "--no-color", self.base, self.candidate], text=True)
        self.fix = {"id": 7, "mode": "fix", "status": "done", "decision": "accepted:fixture@" + self.candidate[:7],
                    "diff": diff, "workdir": str(self.root)}
        return self.pathmap.for_change(self.project, self.fix)

    def selected(self, mapping, method=None):
        return [f["id"] for f in mapping.get("flows", []) if method is None or f["handler"].endswith("." + method)]

    def result(self, mapping, method=None):
        return self.pathmap.path_result(mapping, self.selected(mapping, method))

    def test_registered_dispatcher_reaches_changed_method_with_complete_source_identity(self):
        mapping = self.fixture()
        self.assertEqual(mapping["status"], "mapped", mapping)
        self.assertEqual(mapping["source"]["commit"], self.candidate)
        self.assertEqual(mapping["source"]["diff_sha256"], hashlib.sha256(self.fix["diff"].encode()).hexdigest())
        self.assertTrue(mapping["digest"])
        self.assertTrue(self.selected(mapping, "do_POST"))
        result = self.result(mapping, "do_POST")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["basis"], "python-static-functions")
        self.assertTrue(any("save" in str(c.get("functions")) for c in mapping["changes"]))
        self.assertFalse(self.result(mapping, "do_GET")["ok"], "a different dispatcher cannot own this change")

    def test_same_file_unreachable_method_does_not_pass(self):
        mapping = self.fixture(after=BASE.replace("UNUSED_BASE", "UNUSED_CANDIDATE"))
        self.assertNotEqual(mapping["status"], "mapped")
        self.assertFalse(self.result(mapping)["ok"])
        self.assertTrue(any(c["status"] == "unknown" for c in mapping["changes"]))

    def test_outer_factory_span_cannot_cover_an_uninvoked_nested_function(self):
        before = BASE.replace("    class Handler", "    def hidden():\n        return 'HIDDEN_BASE'\n    class Handler")
        mapping = self.fixture(before=before, after=before.replace("HIDDEN_BASE", "HIDDEN_CANDIDATE"))
        self.assertFalse(self.result(mapping)["ok"])
        self.assertTrue(any("hidden" in str(c.get("functions")) for c in mapping["changes"]))
        self.assertFalse(any(c["status"] == "mapped" for c in mapping["changes"]))

    def test_only_reachable_half_of_product_changes_cannot_pass(self):
        after = BASE.replace("SAVED_BASE", "SAVED_CANDIDATE").replace("UNUSED_BASE", "UNUSED_CANDIDATE")
        mapping = self.fixture(after=after)
        self.assertFalse(self.result(mapping, "do_POST")["ok"])
        self.assertNotEqual(mapping["status"], "mapped")

    def test_dynamic_dispatch_stays_unknown_even_if_method_name_exists(self):
        before = BASE.replace("return self.post()", "return getattr(self, self.operation)()")
        mapping = self.fixture(before=before)
        self.assertFalse(self.result(mapping)["ok"])
        self.assertNotEqual(mapping["status"], "mapped")

    def test_unregistered_protocol_handler_is_not_a_verified_entry(self):
        before = BASE.replace("return ThreadingHTTPServer(address, Handler)", "return Handler")
        mapping = self.fixture(before=before)
        self.assertFalse(self.result(mapping)["ok"], "a declared Handler is not evidence of server registration")

    def test_tests_only_changes_do_not_count_as_product_reachability(self):
        mapping = self.fixture(after=BASE, extra_before={"tests/test_app.py": "def test_example():\n    assert 1 == 1\n"},
            extra_after={"tests/test_app.py": "def test_example():\n    assert 2 == 2\n"})
        self.assertFalse(self.result(mapping)["ok"])
        self.assertNotEqual(mapping["status"], "mapped")

    def test_dirty_checkout_does_not_replace_candidate_source(self):
        mapping = self.fixture()
        self.write("app.py", "raise AssertionError('dirty working tree must not be imported')\n")
        before = self.git("status", "--porcelain")
        again = self.pathmap.for_change(self.project, self.fix)
        self.assertEqual(again["source"]["commit"], self.candidate)
        self.assertEqual(again["digest"], mapping["digest"])
        self.assertTrue(self.result(again, "do_POST")["ok"])
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertFalse((self.root / ".tmh").exists(), "reading a candidate must not build mutable root graph/cache")

    def test_missing_commit_or_valid_but_wrong_candidate_cannot_verify_diff(self):
        self.fixture()
        for revision in ("f" * 40, self.base):
            with self.subTest(revision=revision):
                mapping = self.pathmap.for_change(self.project, self.fix, revision)
                self.assertFalse(self.result(mapping)["ok"])
                self.assertEqual(mapping["status"], "unknown")

    def test_full_hash_object_cannot_be_shadowed_by_a_named_branch(self):
        self.fixture()
        self.git("branch", self.candidate, self.base)
        mapping = self.pathmap.for_change(self.project, self.fix, self.candidate)
        self.assertEqual(mapping["source"]["commit"], self.candidate)
        self.assertTrue(self.result(mapping, "do_POST")["ok"], mapping)

    def test_no_selected_entry_cannot_be_silently_replaced_with_suggestions(self):
        mapping = self.fixture()
        self.assertTrue(mapping.get("suggested"))
        self.assertFalse(self.pathmap.path_result(mapping, [])["ok"])
        self.assertFalse(self.pathmap.path_result(mapping, ["flow:not-real"])["ok"])

    def test_method_reachability_does_not_claim_specific_url_or_correct_behavior(self):
        before = BASE.replace("return self.save()", "if self.path == '/items/edit':\n                return self.save()\n            return self.unused()")
        mapping = self.fixture(before=before, after=before.replace("SAVED_BASE", "WRONG_BUSINESS_RESULT"))
        result = self.result(mapping, "do_POST")
        self.assertTrue(result["ok"], "a reachable wrong implementation remains reachable; separate tests must reject behavior")
        self.assertIn("静态", result.get("why", ""))
        for flow in mapping["flows"]:
            self.assertNotIn("/items/edit", flow["trigger"], "method dispatch cannot claim route branch execution")
        self.assertTrue(mapping["limitations"])
        self.assertNotIn("修复通过", result.get("why", ""))

    def test_reachable_addition_cannot_hide_a_deletion_in_an_unreachable_function(self):
        before = BASE.replace('return "UNUSED_BASE"', 'unused_guard = "DELETE_ME"\n            return "UNUSED_BASE"')
        after = before.replace("SAVED_BASE", "SAVED_CANDIDATE").replace('            unused_guard = "DELETE_ME"\n', '')
        mapping = self.fixture(before=before, after=after)
        self.assertFalse(self.result(mapping, "do_POST")["ok"],
                         "a separate deleted location cannot be covered by this file's reachable replacement")

    def test_abbreviated_adoption_commit_is_an_object_identity_not_a_branch_name(self):
        self.fixture()
        self.write("unrelated.txt", "a later commit sharing the candidate app blob\n")
        shadow = self.commit("later unrelated commit")
        self.git("branch", self.candidate[:7], shadow)
        mapping = self.pathmap.for_change(self.project, self.fix)
        self.assertEqual(mapping["source"]["commit"], self.candidate,
                         "the accepted abbreviated object must not silently resolve to a same-named ref")

    def test_registered_class_method_replaced_before_server_is_unknown(self):
        before = BASE.replace("    return ThreadingHTTPServer(address, Handler)",
                              "    Handler.post = lambda self: 'REPLACED'\n    return ThreadingHTTPServer(address, Handler)")
        mapping = self.fixture(before=before)
        self.assertFalse(self.result(mapping)["ok"], "registration does not undo a known dynamic method replacement")

    def test_unknown_decorator_cannot_be_assumed_to_call_original_method(self):
        before = BASE.replace("def make_server(address):", "def replacement(fn):\n    return lambda self: 'REPLACED'\n\ndef make_server(address):")
        before = before.replace("        def post(self):", "        @replacement\n        def post(self):")
        mapping = self.fixture(before=before)
        self.assertFalse(self.result(mapping)["ok"], "the wrapper may never call the changed function")

    def test_parse_failure_elsewhere_in_product_is_visible_and_blocks_complete_mapping(self):
        mapping = self.fixture(extra_before={"broken.py": "def broken(:\n"}, extra_after={"broken.py": "def broken(:\n"})
        self.assertTrue(mapping["diagnostics"])
        self.assertTrue(any(d.get("file") == "broken.py" for d in mapping["diagnostics"]))
        self.assertFalse(self.result(mapping)["ok"])

    def test_replacing_recorded_selection_does_not_keep_an_unchecked_technical_entry(self):
        from types import SimpleNamespace
        from tmh.platform import signoff
        from tmh.platform.server import Platform, api_path_map_record
        mapping = self.fixture()
        data = self.root / "platform-data"
        data.mkdir()
        (data / "autoflow.json").write_text('{"on":false}')
        platform = Platform(data, "technical-fixture")
        self.addCleanup(platform.store.db.close)
        project = platform.store.add_project("PYAPI", "合成独立入口验证", str(self.root))
        ticket = platform.store.create_ticket(project["id"], "保存记录", "技术验证")
        run = platform.store.create_run(project["id"], ticket["id"], "synthetic", "fix", "technical-fixture", "")
        platform.store.update_run(run["id"], status="done", decision=self.fix["decision"], diff=self.fix["diff"])
        for method, expected in (("do_POST", True), ("do_GET", False)):
            request = SimpleNamespace(user="technical-fixture", body={"commit": mapping["source"]["commit"],
                "digest": mapping["digest"], "flows": self.selected(mapping, method)})
            api_path_map_record(platform, request, ticket["key"])
            current = platform.store.ticket(ticket["id"])
            self.assertEqual(signoff.snapshot(platform, current)["path"]["ok"], expected,
                             "the gate must use the recorded selection, not an unchecked prior technical entry")


if __name__ == "__main__":
    unittest.main()
