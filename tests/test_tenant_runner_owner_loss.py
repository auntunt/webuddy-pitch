"""A real tenant worker's Runner loses its pipe and reclaims a live process tree."""
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from tmh.platform import login, supervised_process
from tmh.platform.store import Store
from tmh.platform.tenancy import Registry
from tests.test_run_lifecycle import FIXTURE
from tests.test_tenant_parent_loss import _GATEWAY, _running


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'fork'), 'requires POSIX process trees')
class TenantRunnerOwnerLossTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tmh-tenant-runner-loss-')
        self.temp = temporary  # Preserve the full synthetic fixture on suite failures.
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name).resolve()
        login.set_user(self.data, 'owner', 'synthetic-owner-password')
        self.registry = Registry(self.data, bootstrap_owner='owner')
        self.addCleanup(self.registry.close)
        self.store = Store(self.data / 'platform.db')
        self.addCleanup(self.store.db.close)
        root = self.data / 'repositories' / 'synthetic'
        root.mkdir(parents=True)
        project = self.store.add_project('TREE', 'synthetic tree', str(root))
        self.store.create_ticket(project['id'], 'owner loss', 'owner', auto=False)
        self.script = self.data / 'owned-tree.py'
        self.script.write_text(FIXTURE)
        self.pidfile = self.data / 'owned-tree-pids'
        self.token = self.data.name
        (self.data / 'agents.json').write_text(json.dumps({'fixture': {'timeout': 30,
            'cmd': [sys.executable, str(self.script), 'tree', self.token, str(self.pidfile),
                    '{mode}', '{prompt_file}', '{workdir}']}}))
        self.cookie = 'tmh_session=' + login.make_session(self.data, 'owner')
        self.context_token = self.registry.context('owner')['context_token']
        self.gateway = subprocess.Popen([sys.executable, '-c', _GATEWAY, str(self.data)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.worker = None
        self.attempt = None
        self.guard = None
        self.addCleanup(self.cleanup_processes)
        self.wait_for(lambda: (self.data / 'port').exists(), 'gateway listener')
        self.port = int((self.data / 'port').read_text())
        self.assertEqual(self.request('GET', '/api/meta')[0], 200)
        self.worker = json.loads((self.data / 'worker.json').read_text())

    def wait_for(self, predicate, description, seconds=6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(.01)
        diagnostics = self.store.runs() if hasattr(self, 'store') else []
        self.fail('%s did not reach its real barrier; runs=%r' % (description, diagnostics))

    def request(self, method, path, value=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)
        try:
            raw = json.dumps(value).encode() if value is not None else None
            connection.request(method, '/t/default' + path, raw, {
                'Cookie': self.cookie, 'X-Webuddy-Context': self.context_token,
                'X-TMH': '1', 'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def start_tree(self):
        status, run = self.request('POST', '/api/tickets/TREE-1/runs', {'agent': 'fixture', 'mode': 'analyze'})
        self.assertEqual(status, 200, run)
        self.rid = run['id']
        self.attempt = self.data / 'runs' / str(self.rid) / 'attempts' / '0001'
        markers = [Path(str(self.pidfile) + '.' + name + '.ready') for name in ('tree', 'child', 'leaf')]
        self.wait_for(lambda: all(path.exists() for path in markers), 'three independently published readiness markers')
        pids = [int(path.read_text()) for path in markers]
        self.assertEqual(len(set(pids)), 3)
        self.assertEqual(set(map(int, self.pidfile.read_text().splitlines())), set(pids))
        for pid in pids:
            self.assertTrue(_running(pid), 'ready PID is not alive: %s' % pid)
        for child, parent in zip(pids[1:], pids):
            actual = subprocess.run(['ps', '-o', 'ppid=', '-p', str(child)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(int(actual.stdout.strip()), parent, 'fixture is not a real three-generation tree')
        self.owner = json.loads((self.data / 'runs' / str(self.rid) / 'owner.json').read_text())
        planned = json.loads((self.attempt / 'supervisor.json').read_text())
        self.assertEqual(planned['owner'], self.owner)
        self.assertEqual(planned['pid'], pids[0])
        self.supervisor_pid = planned['supervisor_pid']
        self.assertTrue(_running(self.supervisor_pid))
        raw = self.attempt / 'output.bin'
        expected = [b'fixture-start:' + name.encode() + b':analyze\n' for name in ('tree', 'child', 'leaf')]
        self.wait_for(lambda: raw.exists() and all(text in raw.read_bytes() for text in expected),
                      'durable original output from each generation')
        self.original_output = raw.read_bytes()
        self.assertIsNone(supervised_process.read_receipt(self.attempt, self.owner))
        self.pids = pids
        # A separate process group must survive the cleanup of the owned tree.
        guard_ready = self.data / 'unrelated-ready'
        code = 'from pathlib import Path;import threading;Path(%r).touch();threading.Event().wait()' % str(guard_ready)
        self.guard = subprocess.Popen([sys.executable, '-c', code], start_new_session=True,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wait_for(guard_ready.exists, 'unrelated guard process')

    def assert_owner_lost_tree_cleaned(self):
        receipt = self.wait_for(lambda: supervised_process.read_receipt(self.attempt, self.owner),
                                'supervisor owner-loss receipt')
        self.assertEqual(receipt['reason'], 'owner_lost', receipt)
        self.assertEqual(receipt['returncode'], 125, receipt)
        self.assertEqual(receipt['cleanup']['trigger'], 'owner_lost', receipt)
        for field in ('term_sent', 'kill_sent', 'reaped', 'output_complete', 'complete'):
            self.assertTrue(receipt['cleanup'][field], receipt)
        self.assertFalse(receipt['cleanup']['remaining_group'], receipt)
        self.assertEqual((self.attempt / 'output.bin').read_bytes(), self.original_output)
        self.wait_for(lambda: not _running(self.worker['pid']), 'tenant worker exit')
        self.wait_for(lambda: not _running(self.supervisor_pid), 'independent supervisor exit')
        for pid in self.pids:
            self.assertFalse(_running(pid), 'owned descendant survived: %s' % pid)
        with self.assertRaises(ProcessLookupError):
            os.killpg(receipt['pgid'], 0)
        self.assertIsNone(self.guard.poll(), 'cleanup signalled an unrelated process group')

    def test_worker_sigkill_closes_runner_control_pipe_and_reclaims_three_generations(self):
        self.start_tree()
        os.kill(self.worker['pid'], signal.SIGKILL)
        self.assert_owner_lost_tree_cleaned()
        self.assertIsNone(self.gateway.poll(), 'worker kill also killed its gateway')

    def test_gateway_sigkill_exits_worker_and_reclaims_runner_three_generations(self):
        self.start_tree()
        self.gateway.kill()
        self.gateway.communicate(timeout=3)
        self.assertEqual(self.gateway.returncode, -signal.SIGKILL)
        self.assert_owner_lost_tree_cleaned()

    def cleanup_processes(self):
        # Kill only this test's gateway, recorded worker and exact fixture PIDs;
        # revoke launches before scanning children even when readiness failed.
        if self.gateway.poll() is None:
            self.gateway.kill()
        self.gateway.communicate(timeout=5)
        if self.worker:
            try:
                os.kill(self.worker['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.attempt and (self.attempt / 'supervisor.json').exists():
            record = json.loads((self.attempt / 'supervisor.json').read_text())
            if record.get('pid'):
                try:
                    os.killpg(record['pid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if self.guard:
            if self.guard.poll() is None:
                self.guard.kill()
            self.guard.wait(timeout=3)
        if self.worker:
            Path(self.worker['socket']).unlink(missing_ok=True)
            Path(self.worker['keyfile']).unlink(missing_ok=True)
            try:
                Path(self.worker['socket']).parent.rmdir()
            except OSError:
                pass


if __name__ == '__main__':
    unittest.main()
