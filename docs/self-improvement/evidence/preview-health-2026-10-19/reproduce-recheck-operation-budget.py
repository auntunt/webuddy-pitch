"""Run one real operation fixture with explicit preparation delay or bad reset.

Usage: python script.py TEST_FILE delay|reset EVIDENCE_DIRECTORY
Only this separate test process is patched. Product files are never edited.
"""
import base64
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
target = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
if mode not in ("delay", "reset"):
    raise ValueError("mode must be delay or reset")
evidence = Path(sys.argv[3]).resolve()
evidence.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location("operation_budget_fixture", target)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
case = module.RecheckOperationsTest
original_setup, original_command = case.setUp, case.command
results = []


def setup(self):
    original_setup(self)
    self._budget_repro_calls = 0

    def capture():
        (evidence / "operations.json").write_text(json.dumps(
            self.store.q("SELECT * FROM verification_operations"),
            ensure_ascii=False, indent=2) + "\n")
        runtime = self.data / "verification-operations"
        if runtime.exists():
            shutil.copytree(runtime, evidence / "verification-operations")
    # Runs before the original cleanup closes the store/releases ownership.
    self.addCleanup(capture)


def command(self, opid, code="import os;os.write(1,b'operation-output\\x00\\xff')", **kwargs):
    self._budget_repro_calls += 1
    number = self._budget_repro_calls
    if mode == "delay" and number == 1:
        code = "import time;time.sleep(.8)\n" + code
    if mode == "reset" and number == 2:
        # Deliberate defect, confined to this disposable fixture process.
        self.operations.runner.controls[opid]["start"] = time.monotonic()
    result, folder = original_command(self, opid, code, **kwargs)
    record = asdict(result)
    record["output_base64"] = base64.b64encode(record.pop("output_bytes")).decode("ascii")
    record.update(command_number=number, evidence=str(folder))
    results.append(record)
    (evidence / ("command-%d.bin" % number)).write_bytes(result.output_bytes)
    return result, folder


case.setUp, case.command = setup, command
suite = unittest.TestSuite([case("test_total_operation_budget_covers_multiple_commands")])
outcome = unittest.TextTestRunner(verbosity=2).run(suite)
summary = {"mode": mode, "test_file": str(target),
           "test_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
           "tests_run": outcome.testsRun, "failures": len(outcome.failures),
           "errors": len(outcome.errors), "successful": outcome.wasSuccessful(),
           "commands": results}
(evidence / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "commands"}, ensure_ascii=False, indent=2))
sys.exit(0 if outcome.wasSuccessful() else 1)
