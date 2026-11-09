"""Toolchain sources: pinned archives, fallbacks tried in order, pre-placed verified archives, and reported source."""
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tmh.platform import toolchain
from tmh.platform.errors import ApiError


def _zip(folder):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr(folder + "/bin/tool", "x")
    return payload.getvalue()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ToolchainSourcesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-sources-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "toolchains"

    def pin_for(self, data, folder="fake-tool"):
        digest = hashlib.sha256(data).hexdigest()
        return dict(name=folder + ".zip", folder=folder, algo="sha256", digest=digest,
                    sources=["https://primary.example/a.zip", "https://mirror.example/a.zip"])

    def test_first_source_that_answers_is_used_and_named(self):
        data = _zip("fake-tool")
        pin = self.pin_for(data)
        with patch.object(toolchain.urllib.request, "urlopen", return_value=_Resp(data)) as opened:
            folder, source = toolchain._fetch(pin, self.home)
        self.assertEqual(opened.call_args[0][0], "https://primary.example/a.zip")
        self.assertEqual(source, "primary.example")
        self.assertTrue((folder / "bin" / "tool").is_file())

    def test_falls_back_to_the_next_mirror_when_the_first_fails(self):
        data = _zip("fake-tool")
        pin = self.pin_for(data)
        calls = []

        def fake_open(url, timeout):
            calls.append(url)
            if "primary" in url:
                raise OSError("blocked")
            return _Resp(data)

        with patch.object(toolchain.urllib.request, "urlopen", side_effect=fake_open):
            folder, source = toolchain._fetch(pin, self.home)
        self.assertEqual(calls, pin["sources"])
        self.assertEqual(source, "mirror.example")

    def test_all_sources_failing_reports_every_attempt(self):
        pin = self.pin_for(_zip("fake-tool"))
        with patch.object(toolchain.urllib.request, "urlopen", side_effect=OSError("offline")):
            with self.assertRaises(ApiError) as caught:
                toolchain._fetch(pin, self.home)
        self.assertIn("primary.example", str(caught.exception))
        self.assertIn("mirror.example", str(caught.exception))

    def test_pre_placed_verified_archive_is_used_without_network(self):
        data = _zip("fake-tool")
        pin = self.pin_for(data)
        placed = self.home / "downloads"
        placed.mkdir(parents=True)
        (placed / pin["name"]).write_bytes(data)
        with patch.object(toolchain.urllib.request, "urlopen", side_effect=AssertionError("no network")):
            folder, source = toolchain._fetch(pin, self.home)
        self.assertEqual(source, "本地预置包")
        self.assertTrue((folder / "bin" / "tool").is_file())

    def test_pre_placed_archive_with_wrong_hash_is_refused(self):
        pin = self.pin_for(_zip("fake-tool"))
        placed = self.home / "downloads"
        placed.mkdir(parents=True)
        (placed / pin["name"]).write_bytes(b"tampered")
        with self.assertRaises(ApiError):
            toolchain._fetch(pin, self.home)
        self.assertFalse((placed / pin["name"]).exists())

    def test_pins_use_the_maven_version_that_the_mirrors_carry(self):
        self.assertEqual(toolchain.MAVEN["version"], "3.9.16")
        self.assertEqual(len(toolchain.MAVEN["digest"]), 128)
        self.assertEqual(toolchain.JDK["digest"], "98518ecf554465057ee5509462631deeee374bc368c12a411d225cd29381f84b")
        for pin in (toolchain.JDK, toolchain.MAVEN):
            self.assertEqual(len(pin["sources"]), 3)
            self.assertTrue(all(u.startswith("https://") for u in pin["sources"]))


if __name__ == "__main__":
    unittest.main()


class MavenMirrorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-mirror-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "app"
        self.root.mkdir()
        (self.root / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.task = Path(temp.name) / "task"

    def test_no_mirror_means_no_settings_file(self):
        self.assertIsNone(toolchain.maven_settings(self.task, ""))

    def test_mirror_writes_task_local_settings_and_points_the_environment_at_it(self):
        with patch.object(toolchain, "_fetch", return_value=(self.task, "已有")), \
                patch.object(toolchain.shutil, "which", return_value=None):
            result = toolchain.prepare(self.root, Path(self.task) / "tools", "https://maven.aliyun.com/repository/public", self.task)
        settings = Path(result["env"]["TMH_MAVEN_SETTINGS"])
        self.assertTrue(settings.is_file())
        text = settings.read_text(encoding="utf-8")
        self.assertIn("<mirrorOf>central</mirrorOf>", text)
        self.assertIn("https://maven.aliyun.com/repository/public", text)

    def test_non_http_mirror_is_refused(self):
        with self.assertRaises(ApiError):
            toolchain.maven_settings(self.task, "file:///etc/passwd")


class MavenSettingsFlagTest(unittest.TestCase):
    def test_mvn_check_gets_the_settings_flag_only_when_a_mirror_is_set(self):
        import re
        pattern = r"^(cd \S+ && )?(\./|\.\\)?mvnw?(\.cmd)?\b"
        self.assertTrue(re.match(pattern, "mvn -q -B test"))
        self.assertTrue(re.match(pattern, "cd sub && ./mvnw -q test"))
        self.assertFalse(re.match(pattern, "npm test"))
        cmd = "mvn -q -B test".replace("mvn", 'mvn -s "$TMH_MAVEN_SETTINGS"', 1)
        self.assertEqual(cmd, 'mvn -s "$TMH_MAVEN_SETTINGS" -q -B test')
