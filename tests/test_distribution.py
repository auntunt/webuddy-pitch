"""Distribution tests exercise portable commands, not checkout-only imports."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tmh import install, offline, resources


class DistributionTest(unittest.TestCase):
    def test_offline_archive_installs_and_refreshes_outside_checkout(self):
        with tempfile.TemporaryDirectory(prefix="tmh-distribution-") as folder:
            root = Path(folder)
            archive = root / "offline.zip"
            offline.build(archive)
            self.assertTrue(offline.verify(archive)["ok"])
            unpacked = root / "unpacked"
            with zipfile.ZipFile(archive) as package:
                for source, relative in resources.files(resources.root()):
                    self.assertEqual(package.read(relative), source.read_bytes(), relative)
                package.extractall(unpacked)
            project = root / "project"
            project.mkdir()
            original = "# User instructions\nKeep every line.\n"
            (project / "AGENTS.md").write_text(original, encoding="utf-8")
            commands = [
                [str(unpacked / "tmh.py"), "install", "--repo", str(project)],
                [str(project / ".tmh/tool/tmh.py"), "install", "--repo", str(project)],
                [str(project / ".tmh/tool/tmh.py"), "--version"],
            ]
            for args in commands:
                result = subprocess.run([sys.executable, "-I", *args], cwd=root,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        encoding="utf-8", timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue((project / "AGENTS.md").read_text(encoding="utf-8").startswith(original))
            self.assertEqual((project / ".tmh/docs/agent-commands.md").read_bytes(),
                             (resources.root() / "docs/agent-commands.md").read_bytes())

    def test_missing_distribution_resources_do_not_partially_modify_project(self):
        with tempfile.TemporaryDirectory(prefix="tmh-missing-resource-") as folder:
            root = Path(folder)
            project = root / "project"
            with patch.object(install, "HOME", root / "missing"):
                with self.assertRaises(FileNotFoundError):
                    install.install(project, ["codex"])
            self.assertFalse(project.exists())
