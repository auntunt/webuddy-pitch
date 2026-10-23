"""Real gateway SIGKILL checks; all accounts, listeners and stores are temporary."""
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from tmh.platform import filelock, login
from tmh.platform.store import Store
from tmh.platform.tenancy import Registry
from tmh.platform.tenant_runtime import Workers


_WORKER = '''
import json, os, sys
from pathlib import Path
from tmh.platform import tenant_runtime as r
from tmh.platform.store import Store
comment = Store.comment
def observed_comment(self, tid, author, body, request_id=None):
    if request_id != 'loss-comment':
        return comment(self, tid, author, body, request_id)
    def trace(sql):
        if sql == 'BEGIN IMMEDIATE':
            marker = self.path.parent / 'worker-begin.json'
            temporary = marker.with_suffix('.tmp')
            temporary.write_text(json.dumps({'pid': os.getpid(), 'request_id': request_id,
                'ticket_id': tid, 'author': author, 'sql': sql}))
            temporary.replace(marker)
    self.db.set_trace_callback(trace)
    try:
        return comment(self, tid, author, body, request_id)
    finally:
        self.db.set_trace_callback(None)
Store.comment = observed_comment
r.worker(*sys.argv[1:])
'''


_GATEWAY = '''
import contextlib, json, os, subprocess, sys, time
from pathlib import Path
from tmh.platform import tenant_gateway as g, tenant_runtime as r
from tmh.platform.tenancy import Registry
data = Path(sys.argv[1]); original = g.ThreadingHTTPServer; ensure = r.Workers.ensure
launch = subprocess.Popen; guard = Registry.authorization_guard
def observed_worker(args, *positional, **kwargs):
    if args[1:3] == ['-m', 'tmh.platform.tenant_runtime']:
        args = [args[0], '-c', sys.argv[2], *args[3:]]
    return launch(args, *positional, **kwargs)
@contextlib.contextmanager
def observed_guard(self):
    with guard(self):
        if (data / 'hold-admission').exists():
            marker = data / 'gateway-admission.json'
            temporary = marker.with_suffix('.tmp')
            temporary.write_text(json.dumps({'pid': os.getpid(), 'phase': 'before-forward'}))
            temporary.replace(marker)
            while not (data / 'release-admission').exists():
                time.sleep(.01)
        yield
def server(*args, **kwargs):
    value = original(*args, **kwargs)
    (data / 'port').write_text(str(value.server_address[1]))
    return value
def record(self, tenant):
    value = ensure(self, tenant)
    (data / 'worker.json').write_text(json.dumps({'pid': value['proc'].pid,
        'socket': str(value['socket']), 'keyfile': str(value['keyfile'])}))
    return value
g.ThreadingHTTPServer = server; r.Workers.ensure = record
subprocess.Popen = observed_worker; Registry.authorization_guard = observed_guard
g.serve(data, '127.0.0.1', 0)
'''


def _running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # An orphan zombie has exited and cannot write or own a lock. Linux PID 1
    # may reap it later than macOS; do not mistake that for a running worker.
    state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                           capture_output=True, text=True, check=False).stdout.strip()
    return bool(state) and not state.startswith('Z')


@unittest.skipUnless(os.name == 'posix', 'tenant workers require POSIX Unix sockets')
class TenantParentLossTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tmh-tenant-parent-loss-')
        self.temp = temp  # Full-suite failure capture preserves this synthetic store.
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name).resolve()
        login.set_user(self.data, 'owner', 'synthetic-owner-password')
        login.set_user(self.data, 'member', 'synthetic-member-password')
        self.registry = Registry(self.data, bootstrap_owner='owner')
        self.addCleanup(self.registry.close)
        self.store = Store(self.data / 'platform.db')
        self.addCleanup(self.store.db.close)
        repo = self.data / 'repositories' / 'repo'
        repo.mkdir(parents=True)
        project = self.store.add_project('LOSS', 'synthetic project', str(repo))
        self.ticket = self.store.create_ticket(project['id'], 'parent loss', 'owner')
        self.action('project_grant', user='member', project_id=str(project['id']), role='contributor')
        self.cookie = 'tmh_session=' + login.make_session(self.data, 'member')
        self.token = self.registry.context('member')['context_token']
        self.proc = subprocess.Popen([sys.executable, '-c', _GATEWAY, str(self.data), _WORKER],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.worker = None
        self.addCleanup(self.cleanup_processes)
        self.wait_for(lambda: (self.data / 'port').exists(), 'gateway did not open its listener')
        self.port = int((self.data / 'port').read_text())
        response = self.request('GET', '/api/meta')
        self.assertEqual(response[0], 200, response)
        self.worker = json.loads((self.data / 'worker.json').read_text())
        self.assertTrue(_running(self.worker['pid']))

    def action(self, action, **body):
        revision = self.registry.context('owner')['revision']
        return self.registry.dispatch('owner', dict(action=action, tenant='default',
            revision=revision, request_id='parent-loss-%s' % revision, **body))

    def wait_for(self, condition, message, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.01)
        self.fail(message)

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)
        try:
            raw = json.dumps(body).encode() if body is not None else None
            conn.request(method, '/t/default' + path, raw, {
                'Cookie': self.cookie, 'X-TMH': '1', 'X-Webuddy-Context': self.token,
                'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def kill_gateway(self):
        self.proc.kill()
        _, stderr = self.proc.communicate(timeout=3)
        self.assertEqual(self.proc.returncode, -signal.SIGKILL, stderr)

    def cleanup_processes(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.communicate(timeout=5)
        if self.worker:
            try:
                os.kill(self.worker['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
            # The crash deliberately bypasses parent cleanup. Remove only the
            # exact private paths reported by this synthetic gateway instance.
            Path(self.worker['socket']).unlink(missing_ok=True)
            Path(self.worker['keyfile']).unlink(missing_ok=True)
            try:
                Path(self.worker['socket']).parent.rmdir()
            except OSError:
                pass

    def assert_worker_exited(self):
        self.wait_for(lambda: not _running(self.worker['pid']), 'orphan tenant worker stayed alive')
        # A fresh gateway can recover ownership, but must not overlap a live
        # old worker. No second gateway is started until exit is observed.
        workers = Workers(self.registry)
        workers.close()

    def guard_held(self):
        lockpath = self.registry.path.parent / 'authorization.lock'
        with lockpath.open('a+b') as stream:
            try:
                filelock.try_lock(stream)
            except BlockingIOError:
                return True
            filelock.unlock(stream)
            return False

    def wait_worker_write(self):
        marker = self.data / 'worker-begin.json'
        self.wait_for(marker.exists, 'worker never reached the real SQLite write barrier')
        self.assertEqual(json.loads(marker.read_text()), {
            'pid': self.worker['pid'], 'request_id': 'loss-comment',
            'ticket_id': self.ticket['id'], 'author': 'member', 'sql': 'BEGIN IMMEDIATE'})
        self.assertTrue(self.guard_held(), 'worker reached SQLite without its authorization guard')

    def test_sigkill_idle_gateway_orphan_worker_exits(self):
        self.kill_gateway()
        self.assert_worker_exited()

    def test_sigkill_gateway_does_not_release_active_worker_authorization(self):
        self.store.db.execute('BEGIN IMMEDIATE')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            request = pool.submit(self.request, 'POST', '/api/tickets/LOSS-1/comments',
                                  {'body': 'parent loss barrier', 'request_id': 'loss-comment'})
            try:
                # The gateway also briefly owns this same kernel lock. Only the
                # actual worker's BEGIN trace establishes the intended barrier.
                self.wait_worker_write()
                self.kill_gateway()
                self.assertTrue(self.guard_held(), 'parent death released the active worker authorization guard')
                begun = threading.Event()
                def revoke():
                    begun.set()
                    self.action('account_disable', user='member')
                    return self.store.q("SELECT body FROM events WHERE ticket_id=? AND kind='comment'", (self.ticket['id'],))
                revocation = pool.submit(revoke)
                self.assertTrue(begun.wait(1))
                self.assertFalse(revocation.done(), 'revocation passed an in-flight authorized write')
            finally:
                self.store.db.rollback()
            # The TCP caller loses the response because its gateway died; that
            # does not establish whether the business transaction committed.
            with self.assertRaises((OSError, http.client.HTTPException)):
                request.result(timeout=5)
            at_revocation = revocation.result(timeout=5)
        self.assert_worker_exited()
        after_exit = self.store.q("SELECT body FROM events WHERE ticket_id=? AND kind='comment'", (self.ticket['id'],))
        self.assertEqual(after_exit, at_revocation, 'a business write committed after revocation')
        self.assertIn(after_exit, ([], [{'body': 'parent loss barrier'}]))
        self.assertFalse(self.registry.one('SELECT active FROM accounts WHERE name=?', ('member',))['active'])

    def test_gateway_admission_lock_is_not_worker_write_barrier(self):
        self.store.db.execute('BEGIN IMMEDIATE')
        (self.data / 'hold-admission').touch()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(self.request, 'POST', '/api/tickets/LOSS-1/comments',
                                  {'body': 'parent loss barrier', 'request_id': 'loss-comment'})
            try:
                marker = self.data / 'gateway-admission.json'
                self.wait_for(marker.exists, 'gateway did not enter its admission guard')
                self.assertEqual(json.loads(marker.read_text()), {
                    'pid': self.proc.pid, 'phase': 'before-forward'})
                self.assertTrue(self.guard_held())
                self.assertFalse((self.data / 'worker-begin.json').exists(),
                                 'gateway admission was mistaken for worker execution')
                self.assertFalse(request.done())
                (self.data / 'release-admission').touch()
                self.wait_worker_write()
                self.assertFalse(request.done(), 'worker bypassed the SQLite writer barrier')
            finally:
                (self.data / 'release-admission').touch()
                self.store.db.rollback()
            self.assertEqual(request.result(timeout=5)[0], 200)
        self.assertEqual(self.store.q("SELECT body FROM events WHERE ticket_id=? AND kind='comment'",
                                      (self.ticket['id'],)), [{'body': 'parent loss barrier'}])


if __name__ == '__main__':
    unittest.main()
