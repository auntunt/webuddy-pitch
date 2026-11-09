"""Authorized aggregate queries use synthetic projects before reading their rows."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import patch

from tmh.platform.server import Platform, api_loop, api_inbox
from tmh.platform.store import Store
from tmh.platform import tenant_policy
from tests.test_tenant_policy import Context


class ScopedBoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        store = Store(root / 'platform.db')
        self.addCleanup(store.db.close)
        self.context = Context(root)
        self.context.people['alice']['project_grants'] = {'ALPHA': 'contributor', 'EMPTY': 'viewer'}
        for key in ('ALPHA', 'EMPTY', 'BETA'):
            (root / key).mkdir()
        projects = {key: store.add_project(key, key, str(root / key)) for key in ('ALPHA', 'EMPTY', 'BETA')}
        self.store, self.projects = store, projects
        for key in ('ALPHA', 'BETA'):
            ticket = store.create_ticket(projects[key]['id'], key + ' private', 'fixture')
            store.create_run(projects[key]['id'], ticket['id'], 'fixture', 'analyze', 'fixture', 'private')
        self.waited = []
        def waiting(p):
            self.waited.append(p['key'])
            return store.tickets(p['id'])
        self.P = SimpleNamespace(store=store, tenant_context=self.context, data_dir=root,
            kb=SimpleNamespace(kb_overview=lambda p: {'built': False}),
            flow=SimpleNamespace(waiting=waiting, autoflow=lambda: {'on': False}, agent=lambda c: ''),
            balance=lambda p: p['id'] * 10, project=store.project, PRI_RANK=Platform.PRI_RANK)
        self.P.loop = MethodType(Platform.loop, self.P)
        self.P.inbox = MethodType(Platform.inbox, self.P)
        self.req = SimpleNamespace(h=SimpleNamespace(_who='alice', headers={}))

    def test_member_aggregate_counts_only_authorized_projects_and_waiting(self):
        tenant_policy.authorize(self.P, 'GET', '/api/projects/*/loop', {}, {}, 'alice')
        data = api_loop(self.P, self.req, '*')
        self.assertEqual((data['total'], data['projects'], data['waiting']), (1, 2, 1))
        self.assertEqual(set(self.waited), {'ALPHA', 'EMPTY'})
        self.assertEqual(data['points'], sum(self.projects[k]['id'] * 10 for k in ('ALPHA', 'EMPTY')))
        self.assertNotIn('BETA', json.dumps(data))
        self.assertEqual(api_loop(self.P, self.req, 'EMPTY')['total'], 0)

    def test_inbox_filters_before_stage_computation_and_counts(self):
        received = []
        def stages(P, rows):
            received.extend(t['key'] for t in rows)
            return {t['key']: {'who': 'person', 'key': 'analyze', 'label': '分析', 'action': '查看'} for t in rows}
        with patch('tmh.platform.stage.compute', stages):
            data = api_inbox(self.P, self.req, '*')
        self.assertEqual(received, ['ALPHA-1'])
        self.assertEqual((data['open'], data['running']), (1, 1))
        self.assertNotIn('BETA', json.dumps(data))
        self.context.people['alice']['project_grants'] = {}
        with patch('tmh.platform.stage.compute', stages):
            empty = api_inbox(self.P, self.req, '*')
        self.assertEqual((empty['mine'], empty['open'], empty['running']), ([], 0, 0))
        self.assertEqual(api_loop(self.P, self.req, '*')['projects'], 0)
