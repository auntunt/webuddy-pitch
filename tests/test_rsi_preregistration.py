"""Preflight declarations cannot substitute for verified trial evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/rsi/check_preregistration.py"
spec = importlib.util.spec_from_file_location("rsi_preregistration", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def declared():
    # Explicitly fictitious structural positive control: no person/evidence is verified.
    v = json.loads((ROOT / "scripts/rsi/preregistration.template.json").read_text())
    h = lambda x: hashlib.sha256(x.encode()).hexdigest()
    v["application"] = {"project_key": "fixture-project", "commit": "a" * 40}
    v["strategy"] = {"baseline_revision": "fixture-base", "candidate_revision": "fixture-candidate", "training_source_family": "fixture-A"}
    v["evaluation"] = {"task_families": ["fixture-B", "fixture-C"], "holdout_cases": [
        {"id": str(i), "source_family": f, "input_sha256": h(str(i))}
        for i, f in enumerate(["fixture-B", "fixture-B", "fixture-C"])],
        "followup_source_family": "fixture-D", "custodian": "fixture-custodian", "optimizer": "fixture-optimizer"}
    for k in v["model"]:
        v["model"][k] = h(k) if k.endswith("_sha256") else "fixture-" + k
    v["pilot"] = {"participants": [
        {"user_id": "fixture-person-1", "roles": ["requirement", "development"], "consent_evidence_sha256": h("p1")},
        {"user_id": "fixture-person-2", "roles": ["testing", "delivery", "operations"], "consent_evidence_sha256": h("p2")}],
        "cycles": [{"starts_at": "2026-11-01T09:00:00+08:00", "ends_at": "2026-11-07T18:00:00+08:00"},
                   {"starts_at": "2026-11-08T09:00:00+08:00", "ends_at": "2026-11-14T18:00:00+08:00"}],
        "task_manifest_sha256": h("tasks"), "baseline_manifest_sha256": h("baseline"), "quality_targets": "fixture threshold"}
    for k in v["protocol"]:
        v["protocol"][k] = h(k)
    return v


class PreregistrationTests(unittest.TestCase):
    def test_template_blocks_without_fabricating_people_or_authority(self):
        v = json.loads((ROOT / "scripts/rsi/preregistration.template.json").read_text())
        result = M.check(v)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("participants" in row for row in result["blockers"]))
        self.assertIs(result["execution_authorized"], False)
        self.assertIsNone(result["score"])

    def test_complete_declarations_still_never_verify_or_authorize(self):
        v = declared()
        original = copy.deepcopy(v)
        result = M.check(v)
        self.assertEqual(result["status"], "declared_complete")
        self.assertEqual(v, original)
        self.assertIs(result["execution_authorized"], False)
        self.assertIs(result["evidence_verified"], False)
        self.assertIsNone(result["score"])

    def test_exact_duplicate_inputs_cannot_be_independent_cases(self):
        v = declared()
        v["evaluation"]["holdout_cases"][1]["input_sha256"] = v["evaluation"]["holdout_cases"][0]["input_sha256"]
        self.assertEqual(M.check(v)["status"], "invalid")

    def test_training_holdout_and_followup_disjoint(self):
        for target in ("training", "followup", "training-followup"):
            with self.subTest(target=target):
                v = declared()
                if target == "training":
                    v["strategy"]["training_source_family"] = "fixture-B"
                else:
                    v["evaluation"]["followup_source_family"] = "fixture-B" if target == "followup" else "fixture-A"
                self.assertEqual(M.check(v)["status"], "invalid")

    def test_whitespace_cannot_disguise_training_overlap(self):
        v = declared()
        v["strategy"]["training_source_family"] = " fixture-B "
        self.assertEqual(M.check(v)["status"], "invalid")

    def test_custodian_cannot_be_optimizer(self):
        v = declared()
        v["evaluation"]["custodian"] = v["evaluation"]["optimizer"]
        self.assertEqual(M.check(v)["status"], "invalid")

    def test_preserves_three_holdout_minimum_and_both_families(self):
        v = declared()
        v["evaluation"]["holdout_cases"].pop()
        result = M.check(v)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("has no case" in row for row in result["blockers"]))

    def test_no_bool_float_negative_or_zero_budget(self):
        for field in declared()["budget"]:
            for bad in (True, False, 1.5, 0, -1, "10", {}, []):
                with self.subTest(field=field, bad=bad):
                    v = declared()
                    v["budget"][field] = bad
                    self.assertEqual(M.check(v)["status"], "invalid")
        v = declared()
        v["budget"]["max_calls"] = 6
        self.assertEqual(M.check(v)["status"], "invalid")

    def test_unknown_identity_price_cap_or_review_stays_blocked(self):
        for section, field in (("model", "response_model"), ("model", "price_upper_bound_evidence_sha256"),
                               ("model", "provider_cap_evidence_sha256"), ("protocol", "review_evidence_sha256"),
                               ("protocol", "isolation_evidence_sha256")):
            with self.subTest(field=field):
                v = declared()
                v[section][field] = None
                self.assertEqual(M.check(v)["status"], "blocked")

    def test_real_roles_and_time_periods_must_be_declared(self):
        for kind in ("duplicate-user", "missing-role", "naive-time", "overlap", "reversed"):
            with self.subTest(kind=kind):
                v = declared()
                if kind == "duplicate-user":
                    v["pilot"]["participants"][1]["user_id"] = v["pilot"]["participants"][0]["user_id"]
                elif kind == "missing-role":
                    v["pilot"]["participants"][1]["roles"].remove("operations")
                elif kind == "naive-time":
                    v["pilot"]["cycles"][0]["starts_at"] = "2026-11-01T09:00:00"
                else:
                    v["pilot"]["cycles"][1]["starts_at"] = "2026-11-01T09:00:00+08:00" if kind == "overlap" else "2026-12-01T09:00:00+08:00"
                self.assertNotEqual(M.check(v)["status"], "declared_complete")

    def test_forbids_inline_answers_keys_unknown_fields_and_bad_shapes(self):
        for section in ("root", "application", "strategy", "evaluation", "model", "budget", "pilot", "protocol"):
            for shape in (None, [], False, "text", 1):
                with self.subTest(section=section, shape=shape):
                    v = declared()
                    if section == "root":
                        v = shape
                    else:
                        v[section] = shape
                    self.assertEqual(M.check(v)["status"], "invalid")
        v = declared()
        v["evaluation"]["expected_answer"] = "must not enter optimizer-visible declarations"
        self.assertEqual(M.check(v)["status"], "invalid")

    def test_strict_json_duplicate_keys_and_nan(self):
        for raw in ('{"schema":1,"schema":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                M.loads(raw)

    def test_cli_missing_file_returns_invalid_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, str(SCRIPT), str(Path(folder) / "missing.json")], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            out = json.loads(result.stdout)
            self.assertEqual(out["status"], "invalid")
            self.assertIsNone(out["document_sha256"])
            self.assertIs(out["execution_authorized"], False)
            self.assertEqual(result.stderr, b"")

    def test_cli_exit_codes_and_original_byte_hash_without_echo(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "protocol.json"
            for raw, code, status in ((json.dumps(declared()).encode(), 0, "declared_complete"),
                                      ((ROOT / "scripts/rsi/preregistration.template.json").read_bytes(), 1, "blocked"),
                                      (b'{"private":"DO-NOT-ECHO","private":false}', 2, "invalid")):
                p.write_bytes(raw)
                result = subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, code, result.stderr)
                out = json.loads(result.stdout)
                self.assertEqual(out["status"], status)
                self.assertEqual(out["document_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertNotIn(b"DO-NOT-ECHO", result.stdout + result.stderr)
                self.assertIs(out["execution_authorized"], False)
                self.assertEqual(p.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
