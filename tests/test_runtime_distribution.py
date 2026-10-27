"""Runtime dependency closure outside a checkout; no provider/model calls."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from tmh import install, offline, resources

HELPER = "scripts/rsi/provider_transport.py"


class RuntimeDistributionTest(unittest.TestCase):
    def test_offline_archive_and_vendored_tool_import_canonical_gateway_without_checkout(self):
        with tempfile.TemporaryDirectory(prefix="tmh-runtime-package-") as temp:
            root = Path(temp)
            archive = root / "offline.zip"
            offline.build(archive)
            self.assertTrue(offline.verify(archive)["ok"])
            source = resources.root() / HELPER
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(package.read(HELPER), source.read_bytes())
                package.extractall(root / "unpacked")
            script = '''import hashlib,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from tmh.platform import codex_gateway as gateway
from tmh import install
helper=pathlib.Path(gateway.validate_framing.__code__.co_filename)
assert hashlib.sha256(helper.read_bytes()).hexdigest()==sys.argv[2]
assert gateway.validate_framing([('Content-Length','3')],3)==('length',3)
try:gateway.validate_framing([('Content-Length','3'),('Content-Length','4')],3)
except ValueError:pass
else:raise AssertionError('ambiguous framing accepted')
if len(sys.argv)>3:install.install(pathlib.Path(sys.argv[3]),['codex'])
print(json.dumps({'helper':str(helper),'sha256':sys.argv[2]}))
'''
            project = root / "project"
            for path, extra in ((root / "unpacked", [str(project)]), (project / ".tmh/tool", [])):
                result = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(path), digest, *extra],
                                        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout.decode())
            bundled = project / ".tmh/tool/tmh/_resources" / HELPER
            self.assertEqual(bundled.read_bytes(), source.read_bytes())

    def test_missing_runtime_helper_refuses_install_before_creating_project(self):
        with tempfile.TemporaryDirectory(prefix="tmh-missing-runtime-") as temp:
            root = Path(temp)
            assets = root / "assets"
            for source, relative in resources.files(resources.root()):
                if relative == HELPER:
                    continue
                destination = assets / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            project = root / "project"
            with mock.patch.object(install, "HOME", assets):
                with self.assertRaisesRegex(FileNotFoundError, "provider_transport"):
                    install.install(project, ["codex"])
            self.assertFalse(project.exists())
