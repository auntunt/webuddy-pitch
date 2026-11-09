"""Build output never trips the code-change guard; a real source change still does."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from tmh.platform import agents


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


class BuildOutputExcludeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-exclude-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "app"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        (self.root / "Main.java").write_text("class Main {}\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        agents._exclude_build_output(self.root)

    def test_build_output_is_not_untracked(self):
        (self.root / "target" / "classes").mkdir(parents=True)
        (self.root / "target" / "classes" / "Main.class").write_text("x", encoding="utf-8")
        (self.root / "Other.class").write_text("x", encoding="utf-8")
        status = git(self.root, "status", "--porcelain=v1", "--untracked-files=all")
        self.assertEqual(status, "")

    def test_the_project_gitignore_is_untouched(self):
        self.assertFalse((self.root / ".gitignore").exists())

    def test_a_real_source_change_still_appears(self):
        (self.root / "target").mkdir()
        (self.root / "target" / "Main.class").write_text("x", encoding="utf-8")
        (self.root / "Main.java").write_text("class Main { int x; }\n", encoding="utf-8")
        (self.root / "New.java").write_text("class New {}\n", encoding="utf-8")
        status = git(self.root, "status", "--porcelain=v1", "--untracked-files=all")
        self.assertIn("Main.java", status)
        self.assertIn("New.java", status)
        self.assertNotIn("target", status)

    def test_writing_the_exclude_twice_adds_each_pattern_once(self):
        agents._exclude_build_output(self.root)
        text = (self.root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(text.count("target/"), 1)


if __name__ == "__main__":
    unittest.main()
