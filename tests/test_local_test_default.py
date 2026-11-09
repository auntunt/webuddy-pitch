"""Default host selection and check receipts use the actual persisted config."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tmh.platform import server, testbox


class LocalDefaultTests(unittest.TestCase):
    def test_default_local_check_and_explicit_remote_switch(self):
        with tempfile.TemporaryDirectory() as root:
            platform = SimpleNamespace(data_dir=Path(root))
            req = SimpleNamespace(body={})
            self.assertEqual(server.api_testbox(platform, req)['executor'], 'local')
            with patch.object(testbox.TestBox, 'check', side_effect=AssertionError('must not use SSH')):
                result = server.api_testbox_act(platform, req, 'check')
            self.assertEqual(result['executor'], 'local')
            self.assertIn('python', result['tools'])
            self.assertIn('实际执行回执', result['notice'])
            self.assertIsNotNone(server.api_testbox(platform, req)['last'])
            req.body = {'executor': 'testbox', 'host': 'build-alias'}
            result = server.api_testbox_save(platform, req)
            self.assertEqual(result['conf']['host'], 'build-alias')
            self.assertIsNone(result['last'])
            with patch.object(testbox.TestBox, 'check', return_value={'ok': False, 'error': 'unreachable'}):
                self.assertFalse(server.api_testbox_act(platform, req, 'check')['ok'])
            self.assertEqual(server.api_testbox(platform, req)['executor'], 'testbox')
            req.body = {'executor': 'local', 'host': 'build-alias'}
            result = server.api_testbox_save(platform, req)
            self.assertEqual(result['conf'], {})
            self.assertIsNone(result['last'])

    def test_invalid_remote_does_not_change_saved_config(self):
        with tempfile.TemporaryDirectory() as root:
            platform = SimpleNamespace(data_dir=Path(root))
            req = SimpleNamespace(body={'host': 'user@build'})
            original = server.api_testbox_save(platform, req)['conf']
            for body in ({'executor':'testbox'}, {'executor':'unknown'}, {'host':'-option'}, {'host':'build;whoami'}):
                req.body = body
                with self.assertRaises(server.ApiError):
                    server.api_testbox_save(platform, req)
                self.assertEqual(server.api_testbox(platform, req)['conf'], original)

    def test_detects_platform_specific_wrapper(self):
        from tmh import verify
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            for name in ('mvnw','mvnw.cmd','pom.xml'):
                (root/name).write_text('fixture')
            with patch.object(verify,'os',SimpleNamespace(name='nt')):
                self.assertEqual(verify.detect_commands(root)['test'],r'.\mvnw.cmd -q -B test')
            with patch.object(verify,'os',SimpleNamespace(name='posix')):
                self.assertEqual(verify.detect_commands(root)['test'],'./mvnw -q -B test')
