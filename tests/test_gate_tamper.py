"""G1: test/gate-file tampering on an external candidate cannot self-pass.
G4: the control-point boundary is reported honestly."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tmh.platform import agent_api, candidates
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, Req


class GateTamperTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="webuddy-gate-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@localhost")
        (self.repo / "app.py").write_text("VALUE = 1\n")
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_app.py").write_text(
            "import unittest\nfrom app import VALUE\nclass Test(unittest.TestCase):\n"
            " def test_value(self): self.assertIn(VALUE, (1, 2))\n")
        (self.repo / ".tmh").mkdir()
        (self.repo / ".tmh/config.json").write_text(json.dumps({"commands": {
            "build": sys.executable + " -m py_compile app.py",
            "test": sys.executable + " -m unittest discover -s tests -v"}}))
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "app.py").write_text("VALUE = 2\n")
        self.git("commit", "-am", "candidate")
        self.sha = self.git("rev-parse", "HEAD")
        self.P = Platform(self.root / "data", user="fixture-human")
        self.addCleanup(self.P.store.db.close)
        self.p = self.P.store.add_project("EXT", "Fixture", str(self.repo))
        self.ticket = self.call("ticket_create", {"project": "EXT", "title": "Use value 2",
                                                  "body": "Use value 2 and preserve the test.",
                                                  "request_id": "create"})["ticket"]
        self.criteria = [{"id": "A1", "text": "Value 2 is returned",
                          "check": "Read the app and run its test"}]

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def call(self, op, args, actor="writer", operator=False):
        headers = {"X-Webuddy-Execution": "1"}
        headers.update({"X-Webuddy-Operator": "1"} if operator else {"X-Webuddy-Agent": actor})
        if operator:
            from tmh.platform.operator_access import read_key
            headers["X-Webuddy-Operator-Token"] = read_key(self.P.operator_key_path)
        return agent_api.dispatch(self.P, Req(SimpleNamespace(headers=headers), {}, args, "fixture-human"), op)

    def submit(self, commit=None, **kw):
        packet = self.call("ticket_get", {"ticket": self.ticket["key"]})
        args = {"ticket": self.ticket["key"], "base_commit": self.base,
                "commit": commit or self.sha, "requirement_hash": packet["requirement_hash"],
                "criteria": self.criteria, "summary": "External fixture implementation",
                "request_id": "submit"}
        args.update(kw)
        return self.call("candidate_submit", args)

    def view(self, cid):
        return candidates.view(self.P, cid)

    def test_added_test_does_not_block(self):
        (self.repo / "tests/test_extra.py").write_text("import unittest\nclass T(unittest.TestCase):\n def t(self): self.assertTrue(True)\n")
        self.git("add", ".")
        self.git("commit", "-m", "adds a test")
        a = self.submit(commit=self.git("rev-parse", "HEAD"))
        gate = self.view(a["candidate_id"])["gate_findings"]
        self.assertEqual(gate["tests_added"], ["tests/test_extra.py"])
        self.assertFalse(gate["blocking"])
        self.assertFalse(any("门禁" in x for x in self.view(a["candidate_id"])["missing"]))

    def test_removed_assertion_blocks_and_needs_operator_ack(self):
        test = self.repo / "tests/test_app.py"
        test.write_text("import unittest\nclass Test(unittest.TestCase):\n def test_value(self): pass\n")
        self.git("commit", "-am", "weakens the assertion")
        a = self.submit(commit=self.git("rev-parse", "HEAD"))
        v = self.view(a["candidate_id"])
        self.assertTrue(v["gate_findings"]["blocking"])
        self.assertIn("tests/test_app.py", v["gate_findings"]["tests_changed"])
        self.assertTrue(v["gate_findings"]["weakening"])
        self.assertFalse(v["ready_for_human"])
        self.assertFalse(v["human_accepted"])
        self.assertTrue(any("门禁" in x for x in v["missing"]))
        # implementer and agent-side calls are rejected before reaching the op
        for actor in ("writer", "agent:cursor"):
            with self.assertRaises(ApiError):
                self.call("candidate_gate_ack", {"candidate_id": a["candidate_id"],
                          "reason": "self", "request_id": "bad-" + actor}, actor=actor)
        # an operator ack on the exact classification unblocks that gate item
        out = self.call("candidate_gate_ack", {"candidate_id": a["candidate_id"],
                        "reason": "assertion removal was a fixture; checked", "request_id": "ack"},
                        actor="fixture-human", operator=True)
        self.assertEqual(out["gate_ack"]["reason"], "assertion removal was a fixture; checked")
        self.assertFalse(any("门禁" in x for x in self.view(a["candidate_id"])["missing"]))

    def test_disable_marker_and_ci_change_block(self):
        test = self.repo / "tests/test_app.py"
        test.write_text("import unittest\nfrom app import VALUE\n"
                        "class Test(unittest.TestCase):\n @unittest.skip('skip')\n"
                        " def test_value(self): self.assertIn(VALUE, (1, 2))\n")
        (self.repo / ".github").mkdir()
        (self.repo / ".github/workflows").mkdir(parents=True, exist_ok=True)
        (self.repo / ".github/workflows/ci.yml").write_text("on: push\n")
        self.git("add", ".")
        self.git("commit", "-m", "disables the test and edits CI")
        a = self.submit(commit=self.git("rev-parse", "HEAD"))
        gate = self.view(a["candidate_id"])["gate_findings"]
        self.assertTrue(gate["blocking"])
        self.assertIn(".github/workflows/ci.yml", gate["gate_files"])
        self.assertTrue(any("跳过" in x or "skip" in x.lower() for x in gate["weakening"]))

    def test_deleted_test_file_blocks(self):
        self.git("rm", "-q", "tests/test_app.py")
        self.git("commit", "-m", "removes the test")
        a = self.submit(commit=self.git("rev-parse", "HEAD"))
        gate = self.view(a["candidate_id"])["gate_findings"]
        self.assertTrue(gate["blocking"])
        self.assertIn("tests/test_app.py", gate["tests_deleted"])

    def test_ack_on_wrong_classification_hash_does_not_count(self):
        test = self.repo / "tests/test_app.py"
        test.write_text("import unittest\nclass Test(unittest.TestCase):\n def test_value(self): pass\n")
        self.git("commit", "-am", "weakens")
        a = self.submit(commit=self.git("rev-parse", "HEAD"))
        self.P.store.db.execute("INSERT INTO candidate_gate_acks(candidate_id,author,classification_hash,reason,created) "
                                "VALUES(?,?,?,?,?)", (a["candidate_id"], "fixture-human", "stale-hash", "old", "t"))
        self.P.store.db.commit()
        v = self.view(a["candidate_id"])
        self.assertIsNone(v["gate_ack"])
        self.assertTrue(any("门禁" in x for x in v["missing"]))

    def test_control_points_are_honest(self):
        a = self.submit()
        cps = {x["name"]: x["state"] for x in self.view(a["candidate_id"])["control_points"]}
        self.assertEqual(cps["Webuddy 内部就绪"], "enforced")
        self.assertEqual(cps["Webuddy 执行的合并"], "enforced")
        self.assertEqual(cps["客户仓库必需检查"], "not_connected")
        self.assertEqual(cps["部署许可"], "not_connected")


class GateClassificationTest(unittest.TestCase):
    def diff(self, path, removed, added, new=False, deleted=False):
        lines = "diff --git a/%s b/%s\n" % (path, path)
        if deleted:
            lines += "deleted file mode 100644\n"
        if new:
            lines += "new file mode 100644\n"
        lines += "".join("-" + x + "\n" for x in removed) + "".join("+" + x + "\n" for x in added)
        return lines

    def test_unit_classifier(self):
        c = candidates.gate_classification(self.diff("tests/test_app.py",
            [" self.assertIn(VALUE, (1, 2))"], [" pass"]))
        self.assertTrue(c["blocking"])
        self.assertIn("tests/test_app.py", c["tests_changed"])
        c = candidates.gate_classification(self.diff("src/main/app.py", [], ["x = 1"], new=False))
        self.assertFalse(c["blocking"])
        c = candidates.gate_classification(self.diff("Jenkinsfile", ["old"], ["new"]))
        self.assertTrue(c["blocking"])
        self.assertIn("Jenkinsfile", c["gate_files"])
        c = candidates.gate_classification(self.diff("tests/test_app.py",
            [], ["import unittest\n"], new=True))
        self.assertFalse(c["blocking"])  # pure test addition
        self.assertIn("tests/test_app.py", c["tests_added"])


if __name__ == "__main__":
    unittest.main()
