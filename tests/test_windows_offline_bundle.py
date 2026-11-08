import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    with patch.object(sys, 'path', [str(ROOT / 'scripts/deploy'), *sys.path]):
        spec.loader.exec_module(result)
    return result


launcher = module('windows_launcher', 'scripts/deploy/windows-offline/launcher.py')
builder = module('windows_builder', 'scripts/deploy/build-windows-offline.py')


class WindowsOfflineBundleTest(unittest.TestCase):
    def test_corrupt_cache_is_rejected_without_download_or_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'payload').write_bytes(b'bad')
            lock = {'python': dict(filename='payload', sha256=hashlib.sha256(b'good').hexdigest())}
            with patch.object(builder.urllib.request, 'urlopen', side_effect=AssertionError('offline')):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    builder.payloads(lock, root, True)
                (root / 'payload').unlink()
                with self.assertRaisesRegex(ValueError, 'Missing cached'):
                    builder.payloads(lock, root, True)
            self.assertFalse((root / 'payload').exists())

    def test_windows_markers_require_pywin32_even_on_mac_or_linux(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sdk = root / 'sdk.whl'
            native = root / 'pywin32.whl'
            with zipfile.ZipFile(sdk, 'w') as z:
                z.writestr('sdk.dist-info/METADATA', 'Name: sdk\nVersion: 1\nRequires-Dist: pywin32>=311; sys_platform == "win32" and python_version >= "3.14"\n')
            with self.assertRaisesRegex(ValueError, 'pywin32'):
                builder.check_windows_dependencies([sdk])
            with zipfile.ZipFile(native, 'w') as z:
                z.writestr('pywin32.dist-info/METADATA', 'Name: pywin32\nVersion: 312\n')
            builder.check_windows_dependencies([sdk, native])

    def test_pywin32_scripts_are_relocated_without_running_postinstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wheel = root / 'native.whl'
            content = b'raise AssertionError("postinstall must never run")\n'
            with zipfile.ZipFile(wheel, 'w') as z:
                z.writestr('native.data/scripts/install.py', content)
                z.writestr('native.dist-info/RECORD', 'native.data/scripts/install.py,,\nnative.dist-info/RECORD,,\n')
                z.writestr('native.pth', b'win32\n')
            builder.install_wheel(wheel, root / 'Lib/site-packages', root / 'Scripts')
            self.assertEqual((root / 'Scripts/install.py').read_bytes(), content)
            self.assertIn('../../Scripts/install.py', (root / 'Lib/site-packages/native.dist-info/RECORD').read_text())
            self.assertEqual((root / 'Lib/site-packages/native.pth').read_bytes(), b'win32\n')

    def test_manifest_rejects_missing_corrupt_and_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / 'MANIFEST.json'
            (root / 'file').write_bytes(b'complete')
            manifest.write_text(json.dumps({'file': hashlib.sha256(b'complete').hexdigest()}))
            self.assertEqual(launcher.verify(root), 1)
            (root / 'file').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                launcher.verify(root)
            (root / 'file').unlink()
            with self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
                launcher.verify(root)
            manifest.write_text(json.dumps({'../outside': 'bad'}))
            with self.assertRaisesRegex(ValueError, 'Missing or unsafe'):
                launcher.verify(root)

    def test_external_config_is_read_without_copying_or_creating_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / '用户 配置.json'
            data = root / '业务 数据'
            original = json.dumps(dict(data_dir=str(data), environment={'TMH_TOKEN_FILE': 'private-token-file'}))
            path.write_text(original, encoding='utf-8-sig')
            config, env, selected, host, port = launcher.configuration(root, path)
            self.assertEqual(selected, data.resolve())
            self.assertEqual((host, port), ('127.0.0.1', 8790))
            self.assertEqual(env['TMH_TOKEN_FILE'], 'private-token-file')
            self.assertFalse(data.exists())
            self.assertEqual(path.read_text(encoding='utf-8-sig'), original)

    def test_reuse_and_fallback_are_per_tool_and_broken_local_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tools = {name: name + '.exe' for name in ('node', 'git', 'codex', 'claude')}
            for name in tools.values():
                (root / name).touch()
            (root / 'release.json').write_text(json.dumps(dict(tools=tools)))
            local = root / 'existing claude.cmd'
            local.touch()
            probe = subprocess.CompletedProcess([], 0, stdout='official version\n', stderr='')
            environment = {'PATH': 'original'}
            with patch.object(launcher.shutil, 'which', side_effect=lambda name, **kw: str(local) if name == 'claude' else None), patch.object(launcher.subprocess, 'run', return_value=probe) as run:
                selected, env = launcher.resolve_tools(root, {}, environment)
                self.assertEqual(selected['claude']['source'], 'local')
                self.assertEqual(selected['codex']['source'], 'bundled')
                self.assertEqual(run.call_args_list[-1].args[0], [str(local), '--version'])
                self.assertEqual(environment, {'PATH': 'original'})
                self.assertTrue(env['PATH'].endswith('original'))
                run.return_value = subprocess.CompletedProcess([], 1, stdout='', stderr='private')
                with self.assertRaisesRegex(ValueError, 'failed') as raised:
                    launcher.resolve_tools(root, {}, environment)
                self.assertNotIn('private', str(raised.exception))

    def test_cursor_agent_is_optional_detected_and_explicit_config_reaches_runner(self):
        from tmh.platform import agents
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tools = {name: name+'.exe' for name in ('node', 'git', 'codex', 'claude')}
            for name in tools.values():
                (root/name).touch()
            (root/'release.json').write_text(json.dumps(dict(tools=tools)))
            cli = root/'agent.cmd'
            cli.touch()
            probe = subprocess.CompletedProcess([], 0, stdout='fixture version', stderr='')
            with patch.object(launcher.shutil, 'which', return_value=None), patch.object(launcher.subprocess, 'run', return_value=probe):
                selected, env = launcher.resolve_tools(root, {}, {'PATH':''})
                self.assertFalse(selected['cursor']['available'])
                selected, env = launcher.resolve_tools(root, {'cursor':str(cli)}, {'PATH':''})
                self.assertEqual(selected['cursor']['source'], 'configured')
                with patch.dict(os.environ, env):
                    self.assertEqual(agents.executable('cursor', {'bin':'cursor-agent'}), str(cli))
                with self.assertRaisesRegex(ValueError, 'absolute'):
                    launcher.resolve_tools(root, {'cursor':'relative.cmd'}, {'PATH':''})
            with patch.object(launcher.shutil, 'which', side_effect=lambda name, **kw: str(cli) if name=='agent' else None), patch.object(launcher.subprocess, 'run', return_value=probe):
                selected, env = launcher.resolve_tools(root, {}, {'PATH':''})
                self.assertTrue(selected['cursor']['available'])
                self.assertEqual(selected['cursor']['path'], str(cli))


if __name__ == '__main__':
    unittest.main()
