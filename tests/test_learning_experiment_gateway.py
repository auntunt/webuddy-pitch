"""Real signed gateway/worker requests; fixed synthetic executor only."""
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import unittest

from tests import test_tenant_gateway as gateway
from tmh.platform import learn, learning as L, learning_experiments as X
from tmh.platform.store import Store


@unittest.skipUnless(os.name == 'posix', 'private workers require Unix sockets')
class ExperimentGatewayTests(unittest.TestCase):
    def setUp(self):
        gateway.TenantGatewayTest.setUp(self)
        # Expose the original temporary directory to the failure collector;
        # retain the base fixture's cleanup order and process ownership.
        import tempfile
        self.temp = next(fn.__self__ for fn, _, _ in self._cleanups
                         if isinstance(getattr(fn, '__self__', None), tempfile.TemporaryDirectory))
        self.addCleanup(self.verify_worker_cleanup)

    def verify_worker_cleanup(self):
        self.httpd.shutdown()
        workers = list(self.workers.live.values())
        self.workers.close()
        for worker in workers:
            self.assertIsNotNone(worker['proc'].poll())
            self.assertFalse(worker['socket'].exists())
            self.assertFalse(worker['keyfile'].exists())
    change = gateway.TenantGatewayTest.change
    request = gateway.TenantGatewayTest.request
    token = gateway.TenantGatewayTest.token

    def seed(self, tenant='default'):
        data = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (tenant,))['path'])
        root = data / 'repositories' / 'experiment'
        root.mkdir(parents=True, exist_ok=True)
        store = Store(data / 'platform.db')
        try:
            p = store.add_project('EXPERIMENT', '合成流程', str(root))
            platform = SimpleNamespace(store=store, data_dir=data)
            card = learn.add_lesson(data, dict(project=p['key'], ticket='PREVIOUS-1', status='candidate',
                title='检查变更交付与回滚', symptom='检查变更交付与回滚', fix='完整合成改法\r\n保留末尾  ',
                verify='保留完整回执', applicability='合成流程', non_applicability='真实收益'))
            origin = L._origin(platform, p, 'lesson:' + card['id'])
            revision = L.capture(platform, p, origin['key'], origin['fingerprint'], 'owner')
            return p, revision
        finally:
            store.db.close()

    def post(self, body, tenant='default', user='owner'):
        return self.request('POST', '/t/' + tenant + '/api/learning', user, body,
                            token=self.token(user, tenant), headers={'X-TMH': '1'})

    def read(self, eid, tenant='default', user='owner'):
        return self.request('GET', '/t/' + tenant + '/api/learning?project=EXPERIMENT&experiment=' + eid,
                            user, token=self.token(user, tenant))

    def create_seal(self, revision, tenant='default'):
        body = dict(action='experiment_create', project='EXPERIMENT', request_id='create-once', contract=dict(
            candidate_revision_id=revision['id'], repeats=1, max_calls=6, timeout_seconds=120,
            curator='owner', optimizer='owner', selector='owner', executor_id=X.EXECUTOR_ID, task_set=X.TASK_SET))
        created = self.post(body, tenant)
        self.assertEqual(created[0], 200, created)
        self.assertEqual(set(created[2]), {'receipt'})
        receipt = created[2]['receipt']
        replay = self.post(body, tenant)
        self.assertEqual(replay[0], 200, replay)
        self.assertEqual(replay[2]['receipt']['experiment_id'], receipt['experiment_id'])
        self.assertTrue(replay[2]['receipt']['replayed'])
        sealed = self.post(dict(action='experiment_seal', project='EXPERIMENT', request_id='seal-once',
            experiment_id=receipt['experiment_id'], expected_hash=receipt['contract_hash']), tenant)
        self.assertEqual(sealed[0], 200, sealed)
        return receipt['experiment_id']

    def test_fixed_synthetic_cycle_uses_real_worker_and_curator_tool_cannot_read_raw_result(self):
        project, revision = self.seed()
        eid = self.create_seal(revision)
        started = self.post(dict(action='experiment_start', project='EXPERIMENT', request_id='start-once', experiment_id=eid))
        self.assertEqual(started[0], 200, started)
        deadline = time.monotonic() + 30
        while True:
            status, _, result = self.read(eid)
            self.assertEqual(status, 200, result)
            if result['state'] in X.TERMINAL or time.monotonic() >= deadline:
                break
            time.sleep(.05)
        self.assertEqual(result['state'], 'mechanism_passed', result)
        self.assertFalse(result['protected'])
        self.assertEqual(result['planned_slots'], 6)
        self.assertEqual(result['slot_counts']['completed'], 6)
        self.assertEqual(result['budget']['settled_calls'], 6)
        self.assertEqual(result['budget']['reserved_calls'], 0)
        self.assertFalse(result['rsi_qualified'])
        self.assertEqual(result['report']['independent_real_sources'], 0)
        self.assertFalse(result['production_prompt_equivalence'])
        dispatch_events = [event for event in result['events']
                           if event['kind'] in ('reserve_bind', 'dispatch_intent', 'settle')]
        self.assertEqual(len(dispatch_events), 18)
        self.assertEqual({event['actor'] for event in dispatch_events}, {'owner'})
        for slot in result['slots']:
            self.assertTrue(slot['cleanup']['finished'])
            attempts = slot['cleanup']['attempts']
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]['prompt_sha256'], slot['prompt_hash'])
            self.assertTrue(attempts[0]['cleanup']['complete'])
        rid = result['slots'][0]['run_id']
        status, _, ordinary = self.request('GET', '/t/default/api/runs/' + str(rid) + '?prompt=1', 'owner', token=self.token('owner', 'default'))
        self.assertEqual(status, 200, ordinary)
        self.assertFalse(ordinary['protected'])
        self.assertTrue(ordinary['prompt'])
        self.assertEqual(ordinary['author'], 'owner')
        status, _, grant = self.request('POST', '/t/default/api/tool-connections', 'owner',
            dict(action='create', label='synthetic-curator-tool', project_ids=[project['id']], scope='content', expires_days=7, request_id='grant-once'),
            token=self.token('owner', 'default'), headers={'X-TMH': '1'})
        self.assertEqual(status, 200, grant)
        status, _, tool = self.request('POST', '/t/default/api/agent/run_get', body={'run_id': rid},
            headers={'X-TMH': '1', 'Authorization': 'Bearer ' + grant['token'], 'X-Webuddy-Agent': 'owner'})
        self.assertEqual(status, 200, tool)
        self.assertTrue(tool['protected'])
        self.assertEqual(tool['prompt'], '')
        self.assertEqual(tool['output'], '')
        for suffix in ('cancel', 'retry', 'recover', 'decide', 'recheck', 'recheck/recover'):
            rejected = self.request('POST', '/t/default/api/runs/' + str(rid) + '/' + suffix, 'owner', {},
                token=self.token('owner', 'default'), headers={'X-TMH': '1'})
            self.assertEqual(rejected[0], 409, (suffix, rejected))
        self.assertEqual(self.read(eid)[2]['report_hash'], result['report_hash'])

    def test_unisolated_tenant_can_register_but_cannot_dispatch_and_other_tenant_cannot_read(self):
        _, revision = self.seed(self.a)
        eid = self.create_seal(revision, self.a)
        blocked = self.post(dict(action='experiment_start', project='EXPERIMENT', request_id='blocked-start', experiment_id=eid), self.a)
        self.assertEqual(blocked[0], 403, blocked)
        state = self.read(eid, self.a)
        self.assertEqual(state[0], 200, state)
        self.assertEqual(state[2]['state'], 'sealed')
        self.assertEqual(state[2]['budget']['settled_calls'], 0)
        self.assertTrue(all(slot['run_id'] is None for slot in state[2]['slots']))
        _, other = self.seed(self.b)
        denied = self.read(eid, self.b, 'bob')
        self.assertEqual(denied[0], 404, denied)


if __name__ == '__main__':
    unittest.main()
