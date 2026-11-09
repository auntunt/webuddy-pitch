"""Pushing a task branch: the default branch is refused, only tmh/<task> is pushed, git errors are reported."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from tmh.platform import git_push
from tmh.platform.errors import ApiError


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


class GitPushTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-push-")
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.bare = base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.bare)], check=True)
        self.root = base / "app"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        (self.root / "a.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "remote", "add", "origin", str(self.bare))
        git(self.root, "push", "-q", "origin", "main")
        git(self.root, "checkout", "-q", "-b", "tmh/SHOP-8-r12")
        (self.root / "a.txt").write_text("changed\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "task")
        git(self.root, "checkout", "-q", "main")

    def test_task_branch_is_pushed_under_its_own_name(self):
        result = git_push.push_task_branch(self.root, "SHOP-8", 12)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["remote_branch"], "tmh/SHOP-8-r12")
        remote = subprocess.run(["git", "--git-dir", str(self.bare), "branch", "--list"], capture_output=True, text=True).stdout
        self.assertIn("tmh/SHOP-8-r12", remote)

    def test_default_branch_is_refused_and_nothing_is_pushed(self):
        with self.assertRaises(ApiError):
            git_push.push_task_branch(self.root, "main", 0)

    def test_missing_task_branch_is_not_found(self):
        with self.assertRaises(ApiError) as caught:
            git_push.push_task_branch(self.root, "NOPE-1", 1)
        self.assertEqual(caught.exception.code, 404)

    def test_remote_rejection_is_reported_as_git_error_not_success(self):
        git(self.root, "remote", "set-url", "origin", str(Path(self.bare).parent / "missing.git"))
        result = git_push.push_task_branch(self.root, "SHOP-8", 12)
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
