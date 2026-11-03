import base64
import io
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from tmh.platform import project_import as imp
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


def make_zip(entries, links=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
        for name in links:
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


class ProjectImportTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-import-")
        self.addCleanup(temp.cleanup)
        data = Path(temp.name) / "data"
        self.store = Store(data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=data)

    def upload(self, raw, key="OA", by="li", chunk=None):
        st = imp.start(self.P, {"key": key, "name": "OA 系统", "source": "zip", "size": len(raw), "filename": "oa.zip"}, by)
        size = chunk or imp.CHUNK
        for seq, off in enumerate(range(0, len(raw), size)):
            imp.chunk(self.P, st["job"], {"seq": seq, "data": base64.b64encode(raw[off:off + size]).decode()}, by)
        imp.finish(self.P, st["job"], by)
        for _ in range(200):
            st = imp.status(self.P, st["job"])
            if st["status"] in ("done", "failed"):
                return st
            time.sleep(0.05)
        self.fail("import did not finish")

    def test_zip_becomes_registered_git_project_without_uploaded_git_or_links(self):
        raw = make_zip({"oa/pom.xml": "<project/>", "oa/src/A.java": "class A {}", "oa/.git/config": "[core]\nfsmonitor = touch /tmp/pwn\n",
                        "oa/__MACOSX/._A": "x", "oa/.tmh/tool/tmh.py": "print('uploaded')"}, links=["oa/link"])
        st = self.upload(raw, chunk=7)
        self.assertEqual(st["status"], "done", st.get("error"))
        root = Path(st["root"])
        self.assertEqual(root, self.P.data_dir / "repositories" / "OA")
        self.assertTrue((root / "pom.xml").is_file() and (root / "src" / "A.java").is_file())
        self.assertFalse((root / "link").exists() or (root / "__MACOSX").exists())
        self.assertNotIn("fsmonitor", (root / ".git" / "config").read_text())
        self.assertEqual(st["files"], 2)
        tool = (root / ".tmh" / "tool" / "tmh.py").read_text()
        self.assertIn("from tmh.cli import main", tool)
        self.assertTrue((root / ".tmh" / "tool" / "tmh" / "cli.py").is_file())
        clean = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True).stdout
        self.assertEqual(clean, "")
        p = self.store.project("OA")
        self.assertEqual((p["name"], p["root"]), ("OA 系统", str(root)))
        self.assertFalse((self.P.data_dir / "project-imports" / st["job"] / "upload.zip").exists())

    def test_traversal_fails_and_leaves_nothing(self):
        st = self.upload(make_zip({"a.txt": "ok", "../evil.txt": "x"}))
        self.assertEqual(st["status"], "failed")
        self.assertIn("越界", st["error"])
        self.assertIsNone(self.store.project("OA"))
        self.assertFalse((self.P.data_dir / "repositories" / "OA").exists())
        self.assertFalse((self.P.data_dir.parent / "evil.txt").exists())
        self.assertEqual([p.name for p in (self.P.data_dir / "repositories").iterdir()], [])

    def test_upload_order_owner_and_existing_key_are_enforced(self):
        raw = make_zip({"a.txt": "ok"})
        st = imp.start(self.P, {"key": "oa", "source": "zip", "size": len(raw)}, "li")
        with self.assertRaises(ApiError):
            imp.chunk(self.P, st["job"], {"seq": 1, "data": base64.b64encode(raw).decode()}, "li")
        with self.assertRaises(ApiError):
            imp.chunk(self.P, st["job"], {"seq": 0, "data": base64.b64encode(raw).decode()}, "mallory")
        with self.assertRaises(ApiError):
            imp.finish(self.P, st["job"], "li")
        with self.assertRaises(ApiError):
            imp.start(self.P, {"key": "OA", "source": "zip", "size": 10}, "li")
        with self.assertRaises(ApiError):
            imp.status(self.P, "../../etc")

    def test_git_addresses(self):
        for bad in ("/srv/repo", "file:///srv/repo", "ext::sh -c id", "--upload-pack=id", "https://host", "http://x/y.git"):
            with self.assertRaises(ApiError, msg=bad):
                imp.check_url(bad)
        for good in ("https://github.com/o/r.git", "git@github.com:o/r.git", "ssh://git@host:2222/o/r.git"):
            self.assertEqual(imp.check_url(good), good)
        self.assertEqual(imp.clean_url("https://user:tok@github.com/o/r.git"), "https://github.com/o/r.git")
        self.assertEqual(imp.clean_url("ssh://git@host:2222/o/r.git"), "ssh://git@host:2222/o/r.git")
        with self.assertRaises(ApiError):
            imp.start(self.P, {"key": "OA", "source": "git", "url": "https://github.com/o/r.git", "branch": "-x"}, "li")


if __name__ == "__main__":
    unittest.main()
