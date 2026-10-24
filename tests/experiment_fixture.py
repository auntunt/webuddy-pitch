"""Real personal registry and lesson capture; no service or network fixture."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import uuid

from tmh.platform import learn, learning as L, learning_experiments as X
from tmh.platform import learning_experiment_runs as XR, login, tenant_policy as TP
from tmh.platform.store import Store
from tmh.platform.tenancy import Registry
from tmh.platform.tenant_runtime import TenantContext
from tests.sqlite_snapshot import dump_store


class ExperimentFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-experiment-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.data = self.home / 'runtime'
        self.data.mkdir()
        self.root = self.home / 'project'
        self.root.mkdir()
        password = login.hash_password('synthetic-experiment-password')
        login._save_users(self.data, {name: {'pw': password} for name in
            ('owner', 'alice', 'curator', 'optimizer', 'selector', 'outsider')})
        self.reg = Registry(self.data, bootstrap_owner='owner')
        self.addCleanup(self.reg.close)
        self.store = Store(self.data / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.p = self.store.add_project('APP', '合成闭环', str(self.root))
        self.ctx = TenantContext(self.reg, 'default')
        self.P = SimpleNamespace(store=self.store, data_dir=self.data, tenant_context=self.ctx)
        self.ctx.platform = self.P
        self.seq = 0
        for name in ('curator', 'optimizer', 'selector', 'alice'):
            self.change('project_grant', user=name, project_id=self.p['id'],
                        role='manager' if name == 'alice' else 'viewer')
        self.card = learn.add_lesson(self.data, {
            'project': 'APP', 'ticket': 'APP-1', 'status': 'candidate', 'title': '合成流程检查',
            'symptom': '检查变更交付与回滚', 'fix': '保存完整检查回执\r\n第二行  ',
            'verify': '核对回执', 'applicability': '合成流程', 'non_applicability': '真实生产结论', 'cause': None})
        origin = L._origin(self.P, self.p, 'lesson:' + self.card['id'])
        self.revision = L.capture(self.P, self.p, origin['key'], origin['fingerprint'], 'owner')

    def request(self, prefix='request'):
        self.seq += 1
        return prefix + '-' + str(self.seq)

    def change(self, action, **fields):
        return self.reg.dispatch('owner', dict(action=action, tenant='default',
            revision=self.reg.context('owner')['revision'], request_id=self.request('auth'), **fields))

    def body(self, **changes):
        return {**dict(candidate_revision_id=self.revision['id'], repeats=1, max_calls=6,
            timeout_seconds=120, curator='curator', optimizer='optimizer', selector='selector',
            executor_id=X.EXECUTOR_ID, task_set=X.TASK_SET), **changes}

    def draft(self, body=None, actor='owner', request_id=None):
        return X.create_draft(self.P, self.p, body or self.body(), actor, request_id or self.request('draft'))

    def seal(self, draft=None):
        draft = draft or self.draft()
        return X.seal(self.P, self.p, draft['experiment_id'], draft['contract_hash'], 'owner', self.request('seal'))

    def running(self, **changes):
        value = self.seal(self.draft(self.body(**changes)))
        XR.start_sealed(self.P, self.p, value['experiment_id'], 'owner', self.request('start'), launch=False)
        return value

    def worker(self, **changes):
        value = self.running(**changes)
        eid, token = value['experiment_id'], uuid.uuid4().hex
        with TP.experiment_guard(self.P, 'owner', self.p, 'manager'), L.transaction(self.store) as db:
            exp = X._row(db, self.p, eid)
            db.execute("UPDATE learning_experiments SET owner=?,fence=1,lease_until=? WHERE id=?", (token, time.time()+20, eid))
            db.execute("UPDATE learning_jobs SET status='running',owner=?,lease_until=? WHERE id=?", (token, time.time()+20, exp['job_id']))
            remaining = X.remaining_in_tx(db, exp)
        return XR._Worker(self.P, self.p, eid, 'owner', token, 1, exp['deadline'], remaining)

    def next_material(self, worker):
        row = self.store.one("SELECT id FROM learning_experiment_slots WHERE experiment_id=? AND state='planned' ORDER BY ordinal LIMIT 1", (worker.eid,))
        return worker.register_step(row['id'])

    def exp(self, eid):
        return X.get_internal(self.P, self.p, eid)

    def slots(self, eid):
        return self.store.q('SELECT * FROM learning_experiment_slots WHERE experiment_id=? ORDER BY ordinal', (eid,))

    def snapshot(self):
        return dump_store(self.store)

    @contextmanager
    def fault(self, fragment):
        original = self.store.db
        class Proxy:
            def __getattr__(self, name):
                return getattr(original, name)
            def execute(self, sql, args=()):
                if fragment in sql:
                    raise OSError('synthetic transaction fault: ' + fragment)
                return original.execute(sql, args)
        self.store.db = Proxy()
        try:
            yield
        finally:
            self.store.db = original
