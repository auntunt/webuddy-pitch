"""Synthetic evidence only: no model, provider, credential or private holdout."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.rsi import codex_protocol as C
from tmh.platform import codex_learning_evidence as E
from tmh.platform import supervised_process as SP


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def events():
    return b"\n".join(encoded(x) for x in [
        {"type": "thread.started", "thread_id": "synthetic-thread"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "synthetic answer"}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 6, "output_tokens": 2}},
    ]) + b"\n"


class CodexEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="codex-proof-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.step = self.root / "attempts" / "S1"
        self.step.mkdir(parents=True)
        for path in (self.root, self.root / "attempts", self.step):
            path.chmod(0o700)
        self.owner = {"token": "synthetic-owner", "run_id": "synthetic-run", "data_dir": str(self.root)}
        self.contract = {"schema": C.CONTRACT, "root_id": "1" * 64, "tenant": "synthetic", "project_id": 1,
                         "application_commit": "a" * 40, "baseline_sha256": "2" * 64,
                         "candidate_sha256": "3" * 64,
                         "client": {"engine": "codex", "requested_model": "synthetic-model",
                                    "profile_sha256": "4" * 64, "executable_sha256": "5" * 64},
                         "limits": {"max_outer_starts": 1, "total_timeout_seconds": 10},
                         "accounting": {"unit": "cli_outer_start", "total_tokens_cap": None, "total_cost_cap": None}}
        identity = {"schema": 1, "owner": self.owner, "nonce": "synthetic-nonce", "folder": str(self.step)}
        self.planned = dict(identity, phase="running", supervisor_pid=31336, pid=31337, pgid=31337)
        self.result = dict(identity, phase="finished", supervisor_pid=31336, pid=31337, pgid=31337,
                           returncode=0, process_returncode=0, reason="exited", elapsed_seconds=.1, ended_at=100.,
                           cleanup={"trigger": None, "term_sent": False, "kill_sent": False, "signals": [], "errors": [],
                                    "remaining_group": False, "output_complete": True, "reaped": True, "complete": True})
        self.write("input.bin", b"complete synthetic input")
        self.set_output(events())

    def write(self, name, raw):
        path = self.step / name
        path.write_bytes(raw)
        path.chmod(0o600)

    def set_output(self, raw):
        self.write("output.bin", raw)
        self.result["output"] = {"file": "output.bin", "bytes": len(raw), "sha256": C.digest(raw)}

    def seal(self):
        self.write("supervisor.json", encoded(self.planned))
        self.write("supervisor-result.json", encoded(self.result))
        references = {}
        for key, name in (("input", "input.bin"), ("planned", "supervisor.json"),
                          ("result", "supervisor-result.json"), ("output", "output.bin")):
            raw = (self.step / name).read_bytes()
            references[key] = {"path": "attempts/S1/" + name, "bytes": len(raw), "sha256": C.digest(raw)}
        return {"schema": C.SCHEMA, "contract": copy.deepcopy(self.contract), "origin": "synthetic-fixture",
                "attempts": [{"request_id": "S1", "phase": "B", "state": "settled", "owner": copy.deepcopy(self.owner),
                              "original_folder": str(self.step), "files": references}]}

    def save(self, manifest):
        raw = encoded(manifest)
        path = self.root / "manifest.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        return C.digest(raw)

    def verify(self, manifest=None):
        manifest = self.seal() if manifest is None else manifest
        return E.verify(self.root, self.save(manifest))

    def test_consistent_counterfeit_bindings_never_authorize_adoption(self):
        result = self.verify()
        self.assertTrue(result["file_bindings_verified"])
        for key in ("adoptable", "execution_admitted", "official_client_provenance_verified", "isolation_verified",
                    "holdout_unseen_verified", "deadline_verified", "input_delivery_verified", "process_execution_verified"):
            self.assertIs(result[key], False)
        for key in ("http_request_count", "internal_retry_count", "actual_backend_model", "actual_outer_exec_count"):
            self.assertIsNone(result[key])
        self.assertEqual(result["observations"][0]["client_usage"],
                         {"input_tokens": 10, "cached_input_tokens": 6, "output_tokens": 2})
        self.assertEqual(result["outer_attempt_records"], 1)

    def test_official_label_does_not_establish_provenance(self):
        manifest = self.seal()
        manifest["origin"] = "official-cli-declared"
        self.assertIs(self.verify(manifest)["official_client_provenance_verified"], False)

    def test_real_supervisor_receipt_can_be_read_without_reexecuting(self):
        folder = self.root / "actual-supervisor"
        result = SP.run_supervised([sys.executable, "-c", "import sys;sys.stdout.write(" + repr(events().decode()) + ")"],
                                   folder=folder, owner=self.owner, timeout=5)
        self.assertEqual(result.returncode, 0)
        actual = SP.read_receipt(folder, self.owner)
        manifest = self.seal()
        for name in ("supervisor.json", "supervisor-result.json", "output.bin"):
            self.write(name, (folder / name).read_bytes())
        self.planned = json.loads((self.step / "supervisor.json").read_bytes())
        self.result = actual
        manifest = self.seal()
        manifest["attempts"][0]["original_folder"] = str(folder)
        self.assertTrue(self.verify(manifest)["file_bindings_verified"])
        self.assertIs(self.verify(manifest)["adoptable"], False)

    def test_draft_null_unknown_schema_and_stopped_root_rejected(self):
        for mutate in (
            lambda m: m.update(schema="draft"),
            lambda m: m.update(adoptable=True),
            lambda m: m["contract"].update(root_id=None),
            lambda m: m["contract"].update(root_id=C.STOPPED_ROOT),
            lambda m: m["contract"].update(schema="trial-finite-provider-v7"),
            lambda m: m["contract"].update(schema="codex-learning-prospective-design-v1"),
            lambda m: m["contract"].update(project_id=True),
            lambda m: m["contract"]["limits"].update(max_outer_starts=False),
            lambda m: m["contract"]["limits"].update(total_timeout_seconds=float("inf")),
            lambda m: m["contract"]["accounting"].update(total_tokens_cap=100000000),
            lambda m: m["contract"]["accounting"].update(unit="http_request"),
        ):
            with self.subTest(mutate=mutate):
                manifest = self.seal()
                mutate(manifest)
                with self.assertRaises(C.InvalidEvidence):
                    self.verify(manifest)

    def test_failed_unknown_incomplete_or_contradictory_receipts_rejected(self):
        original = copy.deepcopy(self.result)
        changes = [{"returncode": 1}, {"process_returncode": 1}, {"returncode": False},
                   {"reason": "timed_out"}, {"phase": "unknown"}, {"pid": True}, {"pgid": 12},
                   {"elapsed_seconds": 11}, {"elapsed_seconds": -1}, {"error": "original error"}]
        for change in changes:
            with self.subTest(change=change):
                self.result = dict(original, **change)
                with self.assertRaises(C.InvalidEvidence):
                    self.verify()
        for key, value in (("complete", False), ("reaped", False), ("remaining_group", True),
                           ("output_complete", False), ("term_sent", True), ("errors", ["error"]),
                           ("trigger", "cancelled")):
            self.result = copy.deepcopy(original)
            self.result["cleanup"][key] = value
            with self.subTest(cleanup=key), self.assertRaises(C.InvalidEvidence):
                self.verify()
        self.result = original
        for state in ("failed", "unknown", "intent", "reserved"):
            manifest = self.seal()
            manifest["attempts"][0]["state"] = state
            with self.subTest(state=state), self.assertRaises(C.InvalidEvidence):
                self.verify(manifest)

    def test_cli_logs_fail_closed(self):
        good = events()
        bad = [b"plain log", good.rsplit(b"\n", 2)[0], good + b'{}\n', good.replace(b'"turn.completed"', b'"turn.failed"'),
               good.replace(b'"text":"synthetic answer"', b'"text":""'),
               good.replace(b'"input_tokens":10', b'"input_tokens":true'),
               good.replace(b'"cached_input_tokens":6', b'"cached_input_tokens":11'),
               good.replace(b'"output_tokens":2', b'"output_tokens":2,"output_tokens":3'),
               good + b"\xff\n", good.replace(b'"turn.started"', b'"unknown.event"')]
        for raw in bad:
            with self.subTest(raw=raw):
                self.set_output(raw)
                with self.assertRaises(C.InvalidEvidence):
                    self.verify()

    def test_external_anchor_and_raw_bytes_are_mandatory(self):
        manifest = self.seal()
        anchor = self.save(manifest)
        with self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, "0" * 64)
        self.write("output.bin", events() + b"tamper")
        with self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, anchor)
        (self.step / "output.bin").unlink()
        with self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, anchor)

    def test_symlink_hardlink_and_private_modes_rejected(self):
        manifest = self.seal()
        anchor = self.save(manifest)
        path = self.step / "input.bin"
        saved = path.read_bytes()
        original = self.root / "saved.bin"
        original.write_bytes(saved)
        original.chmod(0o600)
        path.unlink()
        for link in (os.symlink, os.link):
            link(original, path)
            with self.subTest(link=link), self.assertRaises(C.InvalidEvidence):
                E.verify(self.root, anchor)
            path.unlink()
        self.write("input.bin", saved)
        for path in (self.step / "input.bin", self.step):
            before = path.stat().st_mode & 0o777
            path.chmod(0o755 if path.is_dir() else 0o644)
            with self.subTest(path=path), self.assertRaises(C.InvalidEvidence):
                E.verify(self.root, anchor)
            path.chmod(before)

    def test_intermediate_symlink_and_traversal_rejected(self):
        manifest = self.seal()
        anchor = self.save(manifest)
        attempts = self.root / "attempts"
        moved = self.root / "moved"
        attempts.rename(moved)
        attempts.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, anchor)
        attempts.unlink()
        moved.rename(attempts)
        for name in ("../input.bin", "/tmp/input.bin", "attempts/S1/../input.bin", "attempts//S1/input.bin"):
            value = copy.deepcopy(manifest)
            value["attempts"][0]["files"]["input"]["path"] = name
            with self.subTest(name=name), self.assertRaises(C.InvalidEvidence):
                self.verify(value)

    def test_replacement_during_readback_and_readonly_behavior(self):
        manifest = self.seal()
        anchor = self.save(manifest)
        before = {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.root.rglob("*") if p.is_file()}
        E.verify(self.root, anchor)
        after = {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        original = E._Files.unchanged
        def replace(files):
            path = self.step / "input.bin"
            replacement = self.step / "replacement.bin"
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, path)
            return original(files)
        with patch.object(E._Files, "unchanged", replace), self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, anchor)

    def test_duplicate_attempt_and_missing_fields_rejected(self):
        manifest = self.seal()
        manifest["contract"]["limits"]["max_outer_starts"] = 2
        manifest["attempts"].append(copy.deepcopy(manifest["attempts"][0]))
        with self.assertRaises(C.InvalidEvidence):
            self.verify(manifest)
        for key in ("planned", "result", "output", "input"):
            manifest = self.seal()
            del manifest["attempts"][0]["files"][key]
            with self.subTest(key=key), self.assertRaises(C.InvalidEvidence):
                self.verify(manifest)

    def test_directory_replacement_preserving_file_inodes_rejected(self):
        anchor = self.save(self.seal())
        original = E._Files.unchanged
        def replace(files):
            previous = self.step.with_name("old-step")
            self.step.rename(previous)
            self.step.mkdir(mode=0o700)
            for path in previous.iterdir():
                path.rename(self.step / path.name)
            return original(files)
        with patch.object(E._Files, "unchanged", replace), self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, anchor)

    def test_missing_or_extra_receipt_fields_and_owner_substitution(self):
        original = copy.deepcopy(self.result)
        for key in original:
            self.result = copy.deepcopy(original)
            del self.result[key]
            with self.subTest(missing=key), self.assertRaises(C.InvalidEvidence):
                self.verify()
        self.result = dict(original, unknown=True)
        with self.assertRaises(C.InvalidEvidence):
            self.verify()
        self.result = copy.deepcopy(original)
        self.result["owner"]["token"] = "another-owner"
        with self.assertRaises(C.InvalidEvidence):
            self.verify()

    def test_duplicate_fields_nonfinite_numbers_and_unknown_usage(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(C.InvalidEvidence):
                C.strict(raw)
        self.set_output(events().replace(b'"output_tokens":2', b'"output_tokens":2,"actual_cost":0'))
        with self.assertRaises(C.InvalidEvidence):
            self.verify()

    def test_bool_and_float_cannot_alias_integer_receipt_fields(self):
        for receipt in (self.planned, self.result):
            for key in ("supervisor_pid", "pid", "pgid"):
                receipt[key] = 1
        planned, result = copy.deepcopy(self.planned), copy.deepcopy(self.result)
        for target in ("planned", "result"):
            for key in ("schema", "supervisor_pid", "pid", "pgid"):
                for value in (True, 1.0):
                    self.planned, self.result = copy.deepcopy(planned), copy.deepcopy(result)
                    getattr(self, target)[key] = value
                    with self.subTest(target=target, key=key, value=value), self.assertRaises(C.InvalidEvidence):
                        self.verify()
        self.planned, self.result = planned, result
        self.result["output"]["bytes"] = float(self.result["output"]["bytes"])
        with self.assertRaises(C.InvalidEvidence):
            self.verify()

    def test_missing_usage_stays_unknown_without_inventing_zero(self):
        self.set_output(events().replace(b'{"input_tokens":10,"cached_input_tokens":6,"output_tokens":2}', b'{}'))
        self.assertEqual(self.verify()["observations"][0]["client_usage"], {})

    def test_existing_provider_and_adoption_paths_reject_new_protocol(self):
        from scripts.rsi import trial_preparation as old
        from tmh.platform import learning_decisions as decisions, learning_runs
        from tmh.platform.errors import ApiError
        with self.assertRaises(ValueError):
            old.validate_contract(self.contract)
        with patch.object(learning_runs, "get", return_value={"kind": C.SCHEMA}):
            with self.assertRaises(ApiError):
                decisions._job(None, None, None, "not-a-published-job")

    def nested_bundle(self):
        anchor = self.save(self.seal())
        parent = self.root / "parent"
        parent.mkdir(mode=0o700)
        bundle = parent / "bundle"
        bundle.mkdir(mode=0o700)
        shutil.copytree(self.root / "attempts", bundle / "attempts")
        shutil.copy2(self.root / "manifest.json", bundle / "manifest.json")
        return bundle, anchor

    def replace_ancestor(self, bundle):
        parent = bundle.parent
        retained = parent.with_name("parent-retained")
        parent.rename(retained)
        parent.symlink_to(retained, target_is_directory=True)

    def test_ancestor_symlink_after_canonical_check_before_root_open_rejected(self):
        bundle, anchor = self.nested_bundle()
        original = Path.resolve
        changed = []
        def resolve(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path == bundle and not changed:
                self.replace_ancestor(bundle)
                changed.append(True)
            return value
        with patch.object(Path, "resolve", resolve), self.assertRaises(C.InvalidEvidence):
            E.verify(bundle, anchor)
        self.assertEqual(changed, [True])
        self.assertTrue(bundle.parent.is_symlink())

    def test_ancestor_symlink_before_final_chain_recheck_rejected(self):
        bundle, anchor = self.nested_bundle()
        original = E._Files.unchanged
        changed = []
        def unchanged(files):
            self.replace_ancestor(bundle)
            changed.append(True)
            return original(files)
        with patch.object(E._Files, "unchanged", unchanged), self.assertRaises(C.InvalidEvidence):
            E.verify(bundle, anchor)
        self.assertEqual(changed, [True])
        self.assertTrue(bundle.parent.is_symlink())

    def test_private_check_cannot_bind_a_later_unchecked_mode(self):
        anchor = self.save(self.seal())
        original = E._private
        inode = self.root.stat().st_ino
        changed = []
        def private(st, directory=False):
            original(st, directory)
            if directory and st.st_ino == inode and not changed:
                self.root.chmod(0o750)
                changed.append(True)
        with patch.object(E, "_private", private), self.assertRaises(C.InvalidEvidence):
            E.verify(self.root, anchor)
        self.assertEqual(changed, [True])
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o750)

    def test_system_ancestors_do_not_require_owner_only_permissions(self):
        bundle, anchor = self.nested_bundle()
        bundle.parent.chmod(0o755)
        result = E.verify(bundle, anchor)
        self.assertTrue(result["file_bindings_verified"])
        self.assertIs(result["adoptable"], False)
        self.assertIs(result["execution_admitted"], False)


if __name__ == "__main__":
    unittest.main()
