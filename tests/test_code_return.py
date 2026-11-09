"""Task code can be taken back out read-only, committed or not, and says which in every download."""
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
        self.wt = Path(temp.name) / "wt"
        git(self.root, "worktree", "add", "-q", "-b", "tmh/TSK-1-r7", str(self.wt), "main")

    def edit(self):
        (self.wt / "keep.txt").write_text("changed\n")
        (self.wt / "new.txt").write_text("new\n")
        (self.wt / "gone.txt").unlink()

    def commit(self):
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "task")

    def names(self, data):
        return zipfile.ZipFile(io.BytesIO(data)).namelist()

    def test_uncommitted_state_includes_worktree_edits_and_is_labelled(self):
        self.edit()
        body, ctype, name = code_return.download(self.root, "TSK-1", "patch")
        self.assertIn("未提交".encode(), body[:200])
        self.assertIn("+changed", body.decode("utf-8", "replace"))
        self.assertIn("+new", body.decode("utf-8", "replace"))
        self.assertIn("-bye", body.decode("utf-8", "replace"))
        self.assertIn("uncommitted", name)
        files, _, fname = code_return.download(self.root, "TSK-1", "files")
        self.assertIn("uncommitted", fname)
        self.assertEqual(sorted(self.names(files)), ["DELETED_FILES.txt", "STATUS.txt", "keep.txt", "new.txt"])
        self.assertIn("未提交".encode(), zipfile.ZipFile(io.BytesIO(files)).read("STATUS.txt"))
        archive, _, aname = code_return.download(self.root, "TSK-1", "archive")
        self.assertIn("uncommitted", aname)
        self.assertIn("new.txt", self.names(archive))
        self.assertNotIn("gone.txt", self.names(archive))

    def test_committed_state_is_labelled_with_the_commit(self):
        self.edit()
        self.commit()
        body, _, name = code_return.download(self.root, "TSK-1", "patch")
        sha = git(self.root, "rev-parse", "--short=12", "tmh/TSK-1-r7").strip()
        self.assertIn(("已提交 " + sha).encode(), body[:200])
        self.assertIn("committed", name)
        files, _, fname = code_return.download(self.root, "TSK-1", "files")
        self.assertIn("committed", fname)
        self.assertIn("STATUS.txt", self.names(files))

    def test_reads_do_not_change_index_refs_or_project_folder(self):
        self.edit()
        before = (git(self.root, "status", "--porcelain"), git(self.root, "rev-parse", "HEAD"),
                  git(self.root, "rev-parse", "tmh/TSK-1-r7"), git(self.wt, "status", "--porcelain"))
        code_return.download(self.root, "TSK-1", "patch")
        code_return.download(self.root, "TSK-1", "files")
        code_return.download(self.root, "TSK-1", "archive")
        after = (git(self.root, "status", "--porcelain"), git(self.root, "rev-parse", "HEAD"),
                 git(self.root, "rev-parse", "tmh/TSK-1-r7"), git(self.wt, "status", "--porcelain"))
        self.assertEqual(before, after)

    def test_missing_branch_is_not_found(self):
        with self.assertRaises(ApiError) as caught:
            code_return.download(self.root, "NOPE-9", "patch")
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
