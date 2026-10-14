"""The test machine, with a stand-in `ssh` that runs the remote side locally (a POSIX machine)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tmh.platform import testbox  # noqa: E402

FAKE_SSH = """#!/bin/sh
# ssh -p PORT -o .. -o .. -o .. -o .. HOST COMMAND: run COMMAND here
while [ $# -gt 1 ]; do shift; done
exec sh -c "$1"
"""
FAKE_SCP = """#!/bin/sh
# scp -q -P PORT -o .. LOCAL HOST:NAME: put LOCAL at $HOME/NAME here; nothing ever comes through stdin
src=""; for a in "$@"; do src="$dst"; dst="$a"; done
cp "$src" "$HOME/${dst#*:}"
"""


class TestBoxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "ssh").write_text(FAKE_SSH)
        (bin_ / "ssh").chmod(0o755)
        (bin_ / "scp").write_text(FAKE_SCP)
        (bin_ / "scp").chmod(0o755)
        self.old, self.home = os.environ["PATH"], os.environ.get("HOME")
        os.environ["PATH"] = str(bin_) + os.pathsep + self.old
        os.environ["HOME"] = str(self.tmp / "home")
        (self.tmp / "home").mkdir()
        self.repo = self.tmp / "repo"
        g = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        mod = self.repo / "app" / "core"
        mod.mkdir(parents=True)
        (self.repo / "app" / "pom.xml").write_text("<project/>")
        (mod / "pom.xml").write_text("<project/>")
        (mod / "A.java").write_text("class A {}\n")
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "base"], check=True)
        self.base = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def tearDown(self):
        os.environ["PATH"] = self.old
        if self.home is not None:
            os.environ["HOME"] = self.home

    def test_an_ssh_config_alias_keeps_its_own_port(self):
        seen = self.tmp / "args"
        (self.tmp / "bin" / "ssh").write_text('#!/bin/sh\necho "$@" > %s\n' % seen)
        testbox.TestBox({"host": "laptop", "port": 0, "dir": "", "timeout": 30}, self.tmp)._ssh("echo hi")
        self.assertNotIn("-p", seen.read_text().split())
        testbox.TestBox({"host": "u@h", "port": 12022, "dir": "", "timeout": 30}, self.tmp)._ssh("echo hi")
        self.assertIn("-p 12022", seen.read_text())

    def test_commands_compile_the_maven_modules_the_change_touches(self):
        seq, why = testbox.build_commands(self.repo, ["app/core/A.java"])
        self.assertEqual(seq, [("build", "cd app && mvn -B -q compile -DskipTests -pl core -am")], why)
        self.assertEqual(testbox.build_commands(self.repo, ["README.md"])[0], [])

    def test_a_maven_project_the_plan_creates_is_compiled_but_not_before_it_exists(self):
        seq, why = testbox.build_commands(self.repo, ["java/pom.xml", "java/src/main/java/c/App.java"])
        self.assertEqual(seq, [("build", "cd java && mvn -B -q compile -DskipTests")], why)
        self.assertFalse(testbox.runs_on(self.repo, seq[0][1]))
        self.assertTrue(testbox.runs_on(self.repo, "cd app && mvn -B -q compile -DskipTests -pl core -am"))

    def test_a_failed_hand_over_is_not_remembered_as_the_code_failing(self):
        from types import SimpleNamespace
        from tmh.platform.fixloop import FixLoop
        calls = []

        def execute(seq, untouched=False):
            calls.append(seq)
            if len(calls) == 1:
                return [{"kind": "setup", "command": "准备测试机", "exit_code": -2, "seconds": 0, "tail": "Remove-Item: 文件被占用"}]
            return [{"kind": k, "command": c, "exit_code": 0, "seconds": 1, "tail": ""} for k, c in seq]
        fl = SimpleNamespace(wt=self.repo, r=SimpleNamespace(data_dir=self.tmp / "data"), p={"key": "JB"}, say=lambda s: None, execute=execute)
        seq = [("build", "cd app && mvn -B -q compile -DskipTests -pl core -am")]
        why = FixLoop.baseline(fl, seq)
        self.assertIn("测试机没准备好", why)
        self.assertFalse(list((self.tmp / "data" / "checks").glob("*.json")) if (self.tmp / "data" / "checks").exists() else [])
        self.assertEqual(FixLoop.baseline(fl, seq), "")  # the next ticket tries again instead of reusing the failure
        self.assertEqual(len(calls), 2)
        self.assertEqual(FixLoop.baseline(fl, seq), "")  # a real result is kept
        self.assertEqual(len(calls), 2)
        self.assertEqual(FixLoop.baseline(fl, [("build", "cd java && mvn -B -q compile -DskipTests")]), "")  # nothing to build yet
        self.assertEqual(len(calls), 2)

    def test_the_untouched_code_is_built_even_when_the_change_is_already_there(self):
        # building a finished change again: its worktree already holds the change, which must not count as the
        # commit's own result (else a broken change reads as "the original code fails" for every later ticket)
        from tmh.platform.fixloop import FixLoop
        (self.repo / "app" / "core" / "A.java").write_text("class A { broken }\n")
        (self.repo / "java").mkdir()
        (self.repo / "java" / "pom.xml").write_text("<project/>")  # a module the change creates
        base_ok = [("build", "grep -q 'class A {}' app/core/A.java")]
        for box in (testbox.TestBox({"host": "u@h", "port": 22, "dir": str(self.tmp / "remote"), "timeout": 60}, self.tmp), None):
            fl = FixLoop.__new__(FixLoop)
            fl.wt, fl.r, fl.p, fl.rid, fl.box, fl.base, fl.set = self.repo, SimpleNamespace(data_dir=self.tmp / ("data%d" % bool(box))), \
                {"key": "JB", "root": str(self.repo)}, 7, box, self.base, {"check_timeout": 60}
            fl.say = lambda s: None
            self.assertEqual(fl.baseline(base_ok + [("build", "cd java && mvn -B -q compile -DskipTests")]), "", "box" if box else "local")
            self.assertEqual(fl.execute(base_ok)[0]["exit_code"], 1)  # the change itself is what the build then sees
        self.assertEqual((self.repo / "app" / "core" / "A.java").read_text(), "class A { broken }\n")

    def test_the_change_is_sent_applied_on_its_commit_and_built_there(self):
        box = testbox.TestBox({"host": "u@h", "port": 22, "dir": str(self.tmp / "remote"), "timeout": 120}, self.tmp)
        self.assertEqual(box.check()["os"], "posix")
        patch = b"diff --git a/app/core/A.java b/app/core/A.java\n--- a/app/core/A.java\n+++ b/app/core/A.java\n@@ -1 +1 @@\n-class A {}\n+class A { int x; }\n"
        res = box.run("JB", self.repo, self.base, patch, [("build", "grep -q 'int x' app/core/A.java"), ("test", "false")], 60)
        self.assertEqual([(r["command"], r["exit_code"]) for r in res], [("grep -q 'int x' app/core/A.java", 0), ("false", 1)], res)
        # the next run starts from the clean commit again: the earlier change is gone
        res = box.run("JB", self.repo, self.base, b"", [("build", "grep -q 'class A {}' app/core/A.java")], 60)
        self.assertEqual(res[0]["exit_code"], 0, res)
        self.assertEqual(list((self.tmp / "home").iterdir()), [])  # the copied bundle and patch are removed after use

    def test_code_reaches_the_machine_even_when_its_stdin_never_ends(self):
        # Windows OpenSSH may not pass on the end of stdin: a remote side that reads stdin to the end then hangs
        (self.tmp / "bin" / "ssh").write_text(FAKE_SSH.replace('exec sh -c "$1"', 'exec sh -c "$1" < /dev/zero'))
        box = testbox.TestBox({"host": "u@h", "port": 22, "dir": str(self.tmp / "remote"), "timeout": 20}, self.tmp)
        patch = b"diff --git a/app/core/A.java b/app/core/A.java\n--- a/app/core/A.java\n+++ b/app/core/A.java\n@@ -1 +1 @@\n-class A {}\n+class A { int x; }\n"
        res = box.run("JB", self.repo, self.base, patch, [("build", "grep -q 'int x' app/core/A.java")], 20)
        self.assertEqual([(r["command"], r["exit_code"]) for r in res], [("grep -q 'int x' app/core/A.java", 0)], res)

    def test_an_unreachable_machine_says_so(self):
        os.environ["PATH"] = self.old
        if not shutil.which("ssh"):
            self.skipTest("no ssh here")
        box = testbox.TestBox({"host": "u@127.0.0.1", "port": 1, "dir": "", "timeout": 30}, self.tmp)
        r = box.check()
        self.assertFalse(r["ok"])
        self.assertIn("连不上测试机", r["error"])


if __name__ == "__main__":
    unittest.main()
