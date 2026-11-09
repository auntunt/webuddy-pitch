"""Read-only steps on Windows: the platform, not the sandbox, enforces read-only, and reports any change without reverting it."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import readonly_guard, agents


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class ReadOnlyGuardTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-readonly-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "app"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        (self.root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")

    def test_unchanged_worktree_passes(self):
        before = readonly_guard.snapshot(self.root)
        self.assertEqual(readonly_guard.changed(before, readonly_guard.snapshot(self.root)), [])

    def test_edit_and_new_file_are_reported_with_names_and_not_reverted(self):
        before = readonly_guard.snapshot(self.root)
        (self.root / "pom.xml").write_text("<project>changed</project>\n", encoding="utf-8")
        (self.root / "new.txt").write_text("x\n", encoding="utf-8")
        touched = readonly_guard.changed(before, readonly_guard.snapshot(self.root))
        self.assertEqual(touched, ["new.txt", "pom.xml"])
        self.assertIn("changed", (self.root / "pom.xml").read_text(encoding="utf-8"))

    def test_windows_codex_runs_with_full_access_and_others_unchanged(self):
        conf = {"codex": {"title": "Codex", "bin": "codex", "models": [], "defaults": {}}}
        args = (conf, "codex", "analyze", "p", Path("/tmp/p.txt"), Path("/tmp"), Path("/tmp/l.txt"))
        with patch.object(agents, "sys") as fake_sys:
            fake_sys.platform = "win32"
            cmd = agents.command(*args)
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "danger-full-access")
        with patch.object(agents, "sys") as fake_sys:
            fake_sys.platform = "linux"
            cmd = agents.command(*args)
        self.assertEqual(cmd[cmd.index("--sandbox") + 1], "read-only")

if __name__ == "__main__":
    unittest.main()
