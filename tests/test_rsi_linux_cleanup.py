"""Execute the shipped finally AST, no sudo or namespaces or real chown.

Use real directory FDs, fchmod, links and path replacement inside retained
synthetic fixtures. This proves cleanup confinement, not production isolation.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/rsi/linux_holdout_probe.py'
spec = importlib.util.spec_from_file_location('cleanup_probe', SCRIPT)
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


def snapshot(path):
    st = path.stat()
    return {'uid': st.st_uid, 'gid': st.st_gid, 'mode': stat.S_IMODE(st.st_mode),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


@unittest.skipUnless(os.name == "posix", "Linux cleanup directory-descriptor contract requires POSIX")
class LinuxCleanupTests(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get('RSI_CLEANUP_EVIDENCE_DIR')
        if retained:
            self.base = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=retained))
        else:
            temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
            self.base = Path(temp.name)
        self.root = self.base / 'fixture'; self.root.mkdir(mode=0o755)
        self.work = self.root / 'work'; self.work.mkdir()
        (self.work / 'probe-write').write_bytes(b'FIXTURE-WRITE')
        supervised = self.root / 'supervised'; supervised.mkdir(mode=0o700)
        self.artifacts = {self.root / 'report.json': b'{"synthetic":true}',
                          supervised / 'output.bin': b'full-original\xff\x00',
                          supervised / 'supervisor-result.json': b'{"cleanup":"synthetic-only"}'}
        for path, raw in self.artifacts.items():path.write_bytes(raw)
        self.outside = self.base / 'outside'; self.outside.mkdir(mode=0o755)
        self.target = self.outside / 'probe-write'; self.target.write_bytes(b'SYNTHETIC OUTSIDE TARGET')
        self.target.chmod(0o640)
        self.before = {'directory': snapshot(self.outside), 'file': snapshot(self.target)}
        self.calls = []

    def execute_cleanup(self, *, swap_root=False, swap_on_walk=False):
        tree = ast.parse(M.ROOT_ENTRY)
        final = [node.finalbody for node in tree.body if isinstance(node, ast.Try) and node.finalbody]
        self.assertEqual(len(final), 1)
        code = ast.fix_missing_locations(ast.Module(body=final[0], type_ignores=[]))
        (self.base / 'executed-finally.txt').write_text(ast.unparse(code))
        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        pinned = os.fstat(root_fd)
        closed = []
        original_root = self.root
        if swap_root:
            original_root = self.base / 'pinned-original'
            self.root.rename(original_root);self.root.symlink_to(self.outside, target_is_directory=True)
        def record(path, uid, gid, **kwargs):
            target = Path(path).resolve()
            self.calls.append({'path': str(path), 'target': str(target), 'uid': uid, 'gid': gid,
                               'escaped': not target.is_relative_to(original_root.resolve()),
                               'follows': kwargs.get('follow_symlinks', True)})
        def walk(path):
            for parent, dirs, files in os.walk(path):
                if swap_on_walk and Path(parent) == self.work:
                    self.work.rename(self.root / 'original-work')
                    self.work.symlink_to(self.outside, target_is_directory=True)
                yield parent, dirs, files
        def close(fd):
            closed.append(fd);os.close(fd)
        proxy = types.SimpleNamespace(walk=walk, chown=record, fchmod=os.fchmod, close=close)
        try:
            exec(compile(code, '<exact ROOT_ENTRY finally>', 'exec'),
                 {'os': proxy, 'Path': Path, 'root': self.root, 'root_fd': root_fd,
                  'request': {'owner_uid': os.getuid(), 'owner_gid': os.getgid()}})
        finally:
            if root_fd not in closed:os.close(root_fd)
            after = {'directory': snapshot(self.outside), 'file': snapshot(self.target)}
            (self.base / 'observation.json').write_text(json.dumps({'before': self.before, 'after': after,
                       'chown_calls': self.calls, 'real_chown_calls': 0}, indent=2))
        self.assertEqual(after, self.before, 'outside content/UID/GID/mode changed')
        self.assertEqual([c for c in self.calls if c['escaped'] and c['follows']], [], 'outside chown requested')
        st = original_root.stat()
        self.assertEqual((st.st_dev, st.st_ino), (pinned.st_dev, pinned.st_ino))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o700)
        return original_root

    def test_normal_fixed_outputs_keep_all_bytes_and_ownership(self):
        before = {str(p.relative_to(self.root)): snapshot(p) for p in self.artifacts}
        self.execute_cleanup()
        for path, raw in self.artifacts.items():
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(snapshot(path), before[str(path.relative_to(self.root))])

    def test_worker_file_link_never_requests_outside_ownership_change(self):
        (self.work / 'injected-file').symlink_to(self.target)
        self.execute_cleanup()

    def test_worker_directory_link_does_not_touch_outside_tree(self):
        (self.work / 'injected-dir').symlink_to(self.outside, target_is_directory=True)
        self.execute_cleanup()

    def test_root_path_replacement_only_tightens_pinned_original(self):
        self.execute_cleanup(swap_root=True)

    def test_work_path_replacement_during_traversal_cannot_escape(self):
        self.execute_cleanup(swap_on_walk=True)

    def test_failed_privileged_launch_still_closes_fixture_and_stderr_permissions(self):
        root = self.base / 'webuddy-holdout-probe-synthetic'
        def make(**kwargs):root.mkdir();return str(root)
        def fail(*args, **kwargs):
            return types.SimpleNamespace(returncode=1, stdout=b'', stderr=b'SYNTHETIC PRELAUNCH FAILURE')
        import pwd
        with patch.object(M.platform, 'system', return_value='Linux'), patch.object(M.os, 'getuid', return_value=1000), \
             patch.object(M.os, 'getgid', return_value=1000), patch.object(pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=65534,pw_gid=65534)), \
             patch.object(M.tempfile, 'mkdtemp', side_effect=make), patch.object(M.subprocess, 'run', side_effect=fail):
            result = M.run(Path('/synthetic-invalid-release'))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((root / 'root-wrapper.stderr').stat().st_mode), 0o600)
        self.assertEqual((root / 'root-wrapper.stderr').read_bytes(), b'SYNTHETIC PRELAUNCH FAILURE')
