"""Non-Git manifests need no process; Git roots retain actual commit checks."""
from pathlib import Path
import os
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import learning as L
from tmh.platform.store import Store
from tmh.platform.errors import ApiError


class LearningBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='learning-binding-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.store = Store(self.home / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.home)

    def project(self, root):
        return self.store.add_project('SOURCE', 'Source', str(root))

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT,
                                       env=L.pk.git_env(), timeout=10).decode().strip()

    def repository(self):
        root = self.home / 'repository'; root.mkdir()
        self.git(root, 'init', '-q')
        (root / 'file.txt').write_text('synthetic source\n')
        self.git(root, 'add', 'file.txt')
        self.git(root, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 'commit', '-qm', 'fixture')
        return root

    def test_non_git_manifest_never_starts_a_process(self):
        root = self.home / 'plain'; root.mkdir()
        p = self.project(root)
        with patch.object(L.pk, 'git', wraps=L.pk.git) as probe:
            binding = L.binding(self.P, p)
        self.assertEqual(binding['commit'], '')
        self.assertEqual(binding['root'], str(root))
        self.assertEqual(binding['references'], [])
        probe.assert_not_called()

    def test_nested_git_directory_binds_real_head(self):
        root = self.repository(); child = root / 'nested'; child.mkdir()
        p = self.project(child)
        expected = self.git(root, 'rev-parse', 'HEAD')
        self.assertEqual(L.binding(self.P, p)['commit'], expected)
        (root / 'file.txt').write_text('new source\n')
        self.git(root, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 'commit', '-qam', 'second')
        self.assertNotEqual(L.binding(self.P, p)['commit'], expected)

    def test_bare_git_repository_still_binds_actual_head(self):
        root = self.repository(); bare = self.home / 'bare.git'
        subprocess.check_output(['git', 'clone', '--bare', '--no-hardlinks', str(root), str(bare)],
                                stderr=subprocess.STDOUT, timeout=10,
                                env=dict(L.pk.git_env(), GIT_ALLOW_PROTOCOL='file'))
        project = self.project(bare)
        for location in (bare, bare / 'objects'):
            with self.subTest(location=location.name):
                self.store.x('UPDATE projects SET root=? WHERE id=?', (str(location), project['id']))
                self.assertEqual(L.binding(self.P, project)['commit'], self.git(root, 'rev-parse', 'HEAD'))

    def test_git_metadata_subdirectory_is_not_treated_as_plain_manifest(self):
        root = self.repository()
        p = self.project(root / '.git' / 'objects')
        self.assertEqual(L.binding(self.P, p)['commit'], self.git(root, 'rev-parse', 'HEAD'))

    def test_nested_git_without_head_cannot_be_downgraded_to_plain_manifest(self):
        root = self.home / 'unborn'; root.mkdir(); self.git(root, 'init', '-q')
        child = root / 'nested'; child.mkdir()
        with self.assertRaises(ApiError) as error:
            L.binding(self.P, self.project(child))
        self.assertEqual(error.exception.code, 409)

    def test_broken_ancestor_marker_cannot_be_downgraded_to_plain_manifest(self):
        root = self.home / 'ancestor'; root.mkdir()
        (root / '.git').write_text('gitdir: missing-git-directory\n')
        child = root / 'nested'; child.mkdir()
        with self.assertRaises(ApiError) as error:
            L.binding(self.P, self.project(child))
        self.assertEqual(error.exception.code, 409)

    def test_broken_git_marker_never_becomes_plain_manifest(self):
        root = self.home / 'broken'; root.mkdir()
        (root / '.git').write_text('gitdir: missing-git-directory\n')
        with self.assertRaises(ApiError) as error:
            L.binding(self.P, self.project(root))
        self.assertEqual(error.exception.code, 409)

    @unittest.skipUnless(os.name == 'posix', 'fixture requires unprivileged POSIX symlink creation')
    def test_dangling_git_marker_never_becomes_plain_manifest(self):
        root = self.home / 'dangling'; root.mkdir()
        (root / '.git').symlink_to(root / 'missing-git-directory')
        with self.assertRaises(ApiError) as error:
            L.binding(self.P, self.project(root))
        self.assertEqual(error.exception.code, 409)

    def test_unreadable_ancestor_metadata_cannot_be_assumed_absent(self):
        root = self.home / 'plain'; root.mkdir()
        p = self.project(root)
        original = Path.lstat
        def denied(path, *args, **kwargs):
            if path == self.home / '.git':
                raise PermissionError('synthetic unreadable parent metadata')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', denied), patch.object(L.pk, 'git') as process:
            with self.assertRaises(ApiError) as error:
                L.binding(self.P, p)
        self.assertEqual(error.exception.code, 409)
        process.assert_not_called()
