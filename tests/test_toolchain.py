"""Build environment: detect project needs, reuse installed tools, verify pinned downloads, and report failures."""
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tmh.platform.errors import ApiError
from tmh.platform import toolchain


class ToolchainTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-toolchain-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "toolchains"
        self.root = Path(temp.name) / "app"
        self.root.mkdir()

    def test_detection_by_project_type(self):
        (self.root / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.assertEqual(toolchain.needs(self.root), {"jdk", "maven"})
        (self.root / "pom.xml").unlink()
        (self.root / "package.json").write_text("{}", encoding="utf-8")
        self.assertEqual(toolchain.needs(self.root), {"node"})

    def test_installed_tools_are_reused_without_download(self):
        (self.root / "pom.xml").write_text("<project/>", encoding="utf-8")
        with patch.object(toolchain.shutil, "which", side_effect=lambda n: "C:/tools/" + n), \
                patch.object(toolchain, "_fetch") as fetch:
            result = toolchain.prepare(self.root, self.home)
        fetch.assert_not_called()
        self.assertEqual(result["env"], {})
        self.assertEqual(len(result["notes"]), 2)

    def test_download_with_bad_hash_is_refused_and_removed(self):
        pin = dict(toolchain.MAVEN, url="https://example.invalid/m.zip", folder="fake-maven")
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("fake-maven/bin/mvn", "x")
        data = payload.getvalue()
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with patch.object(toolchain.urllib.request, "urlopen", return_value=Resp(data)):
            with self.assertRaises(ApiError) as caught:
                toolchain._fetch(pin, self.home)
        self.assertEqual(caught.exception.code, 409)
        self.assertFalse((self.home / "fake-maven.zip").exists())

    def test_network_failure_is_reported_not_passed(self):
        pin = dict(toolchain.JDK, folder="jdk-x")
        with patch.object(toolchain.urllib.request, "urlopen", side_effect=OSError("offline")):
            with self.assertRaises(ApiError) as caught:
                toolchain._fetch(pin, self.home)
        self.assertIn("下载", str(caught.exception))

    def test_pins_are_present_and_well_formed(self):
        self.assertEqual(len(toolchain.JDK["digest"]), 64)
        self.assertEqual(len(toolchain.MAVEN["digest"]), 128)
        self.assertTrue(toolchain.JDK["url"].startswith("https://"))
        self.assertTrue(toolchain.MAVEN["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
