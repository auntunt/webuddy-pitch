"""Task code can be taken back out read-only: patch, changed files, full archive."""
import io
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tmh.platform import code_return
from tmh.platform.errors import ApiError


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


class CodeReturnTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-return-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "app"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        (self.root / "keep.txt").write_text("base\n")
        (self.root / "gone.txt").write_text("bye\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-q", "-b", "tmh/TSK-1-r7")
        (self.root / "keep.txt").write_text("changed\n")
        (self.root / "new.txt").write_text("new\n")
        (self.root / "gone.txt").unlink()
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "task")
        git(self.root, "checkout", "-q", "main")

    def test_patch_contains_the_committed_change(self):
        text = code_return.patch(self.root, "TSK-1").decode()
        self.assertIn("+changed", text)
        self.assertIn("+new", text)

    def test_changed_files_zip_has_only_changed_files_and_deletions(self):
        names = zipfile.ZipFile(io.BytesIO(code_return.changed_files_zip(self.root, "TSK-1"))).namelist()
        self.assertEqual(sorted(names), ["DELETED_FILES.txt", "keep.txt", "new.txt"])

    def test_full_archive_is_the_task_branch_tree(self):
        names = zipfile.ZipFile(io.BytesIO(code_return.full_archive(self.root, "TSK-1"))).namelist()
        self.assertIn("keep.txt", names)
        self.assertNotIn("gone.txt", names)

    def test_reads_do_not_change_the_project_folder(self):
        before = git(self.root, "status", "--porcelain"), git(self.root, "rev-parse", "HEAD")
        code_return.patch(self.root, "TSK-1")
        code_return.changed_files_zip(self.root, "TSK-1")
        code_return.full_archive(self.root, "TSK-1")
        self.assertEqual(before, (git(self.root, "status", "--porcelain"), git(self.root, "rev-parse", "HEAD")))
        self.assertEqual(git(self.root, "branch", "--show-current").strip(), "main")

    def test_missing_branch_is_a_plain_not_found(self):
        with self.assertRaises(ApiError) as caught:
            code_return.patch(self.root, "NOPE-9")
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
