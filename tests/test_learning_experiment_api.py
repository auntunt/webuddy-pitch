"""Actual request handlers and personal registry; no real model or business data."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.experiment_fixture import ExperimentFixture
from tmh.platform import server, learning_experiments as X, learning_experiment_views as V
from tmh.platform import learning as L, learning_runs as R, tenant_policy as TP, tool_read
from tmh.platform.errors import ApiError


class ExperimentApiTests(ExperimentFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.P.project = self.store.project
        self.P.runner = Mock()
        self.P.flow = Mock()

    def req(self, body=None, actor='owner', query=None, headers=None):
        return server.Req(SimpleNamespace(_who=actor, headers=headers or {}),
                          {k: [str(v)] for k, v in (query or {}).items()}, body or {}, actor)

    def post(self, action, actor='owner', **fields):
        body = dict(action=action, project='APP', request_id=self.request('api'), **fields)
        req = self.req(body, actor)
        TP.authorize(self.P, 'POST', '/api/learning', {}, body, actor)
        return server.api_learning_action(self.P, req)

    def test_create_and_replay_return_only_committed_safe_receipt(self):
        body = dict(action='experiment_create', project='APP', request_id='one-create', contract=self.body())
        req = self.req(body)
        with patch.object(V, 'experiment', side_effect=ApiError(403, 'synthetic revoked during later read')):
            first = server.api_learning_action(self.P, req)
            replay = server.api_learning_action(self.P, req)
        self.assertEqual(set(first), {'receipt'})
        self.assertEqual(set(first['receipt']), {'experiment_id', 'job_id', 'contract_hash', 'state', 'replayed', 'action', 'request_id'})
        self.assertEqual(first['receipt']['experiment_id'], replay['receipt']['experiment_id'])
        self.assertTrue(replay['receipt']['replayed'])
        self.assertEqual(len(self.store.q('SELECT * FROM learning_experiments')), 1)
        self.assertNotIn('保存完整检查回执', json.dumps(first, ensure_ascii=False))

    def test_no_display_header_agent_or_shared_actor_can_create(self):
        body = dict(action='experiment_create', project='APP', request_id='forged', contract=self.body())
        for actor, headers in (('', {}), ('', {'X-Webuddy-User': 'owner'}),
                               ('owner', {'X-Webuddy-Agent': 'claude'})):
            with self.subTest(actor=actor, headers=headers), self.assertRaises(ApiError) as error:
                server.api_learning_action(self.P, self.req(body, actor, headers=headers))
            self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.store.q('SELECT * FROM learning_experiments'), [])

    def test_value_error_after_verified_rollback_preserves_safe_to_replace_code(self):
        with patch.object(X, '_material', side_effect=ValueError('synthetic input rejected')):
            with self.assertRaises(ApiError) as error:
                self.post('experiment_create', contract=self.body())
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(error.exception.reason, 'experiment_not_written')
        self.assertEqual(self.store.q('SELECT * FROM learning_experiments'), [])
        self.assertFalse(self.store.db.in_transaction)
        with patch.object(X, 'create_draft', side_effect=ValueError('unknown pre-transaction error')):
            with self.assertRaises(ApiError) as unknown:
                self.post('experiment_create', contract=self.body())
        self.assertFalse(hasattr(unknown.exception, 'reason'))

    def test_recapture_same_managed_revision_uses_current_personal_view(self):
        self.seal()
        origin = L._origin(self.P, self.p, 'lesson:' + self.card['id'])
        result = self.post('capture', key=origin['key'], expected_fingerprint=origin['fingerprint'])
        self.assertEqual(result['id'], self.revision['id'])
        self.assertTrue(result['managed'])
        self.assertTrue(result['protected'])
        self.assertIsNone(result['content'])
        self.assertEqual(result['source'], {})

    def test_unknown_field_and_body_actor_never_become_authority(self):
        for extra in ({'actor': 'owner'}, {'command': ['arbitrary']}, {'executor': 'claude'}):
            body = dict(action='experiment_create', project='APP', request_id='unknown', contract=self.body(), **extra)
            with self.subTest(extra=extra), self.assertRaises(ApiError) as error:
                server.api_learning_action(self.P, self.req(body))
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.store.q('SELECT * FROM learning_experiments'), [])

    def test_curator_full_and_manager_safe_use_same_current_personal_boundary(self):
        receipt = self.seal()
        query = dict(project='APP', experiment=receipt['experiment_id'])
        manager = server.api_learning(self.P, self.req(query=query))
        curator = server.api_learning(self.P, self.req(actor='curator', query=query))
        self.assertTrue(manager['protected'])
        self.assertFalse(curator['protected'])
        self.assertNotIn('保存完整检查回执', json.dumps(manager, ensure_ascii=False))
        self.assertIn('保存完整检查回执', json.dumps(curator, ensure_ascii=False))
        self.assertFalse(manager['rsi_qualified'])
        self.assertFalse(curator['can_adopt'])
        self.change('project_revoke', user='curator', project_id=self.p['id'])
        with self.assertRaises(ApiError) as error:
            server.api_learning(self.P, self.req(actor='curator', query=query))
        self.assertEqual(error.exception.code, 403)

    def test_project_viewer_cannot_mutate_even_when_named_curator(self):
        receipt = self.seal()
        for action, extra in (('experiment_cancel', {}),
                              ('experiment_expose', {'asset_ids': [], 'expected_hash': receipt['contract_hash']})):
            with self.subTest(action=action), self.assertRaises(ApiError) as error:
                self.post(action, actor='curator', experiment_id=receipt['experiment_id'], **extra)
            self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.exp(receipt['experiment_id'])['state'], 'sealed')

    def test_unisolated_manager_cannot_start_or_claim_execution(self):
        receipt = self.seal()
        with self.assertRaises(ApiError) as error:
            self.post('experiment_start', actor='alice', experiment_id=receipt['experiment_id'])
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.exp(receipt['experiment_id'])['state'], 'sealed')

    def test_managed_run_all_generic_mutations_refuse_before_runner_calls(self):
        worker = self.worker()
        material = self.next_material(worker)
        rid = material['slot']['run_id']
        before = self.snapshot()
        methods = (server.api_cancel, server.api_retry_run, server.api_recover_run, server.api_decide,
                   server.api_recheck, server.api_recheck_recover, server.api_recheck_state)
        for method in methods:
            with self.subTest(method=method.__name__), self.assertRaises(ApiError) as error:
                method(self.P, self.req(), str(rid))
            self.assertEqual(error.exception.code, 409)
        self.assertEqual(self.P.runner.mock_calls, [])
        self.assertEqual(self.P.flow.mock_calls, [])
        self.assertEqual(self.snapshot(), before)

    def test_managed_run_detail_and_tool_read_skip_live_probes(self):
        worker = self.worker()
        material = self.next_material(worker)
        rid = material['slot']['run_id']
        with patch.object(R, 'get', side_effect=AssertionError('raw managed read')):
            ordinary = server.api_run(self.P, self.req(query={'prompt': '1'}), str(rid))
            personal = server.api_run(self.P, self.req(actor='curator', query={'prompt': '1'}), str(rid))
            tool = tool_read.run_get(self.P, rid, 0, [self.p['id']], actor='owner')
        self.assertTrue(ordinary['protected'])
        self.assertFalse(personal['protected'])
        self.assertEqual(personal['prompt'], material['prompt'])
        self.assertTrue(tool['protected'])
        self.assertEqual(self.P.runner.mock_calls, [])
        self.assertEqual(self.P.flow.mock_calls, [])

    def test_managed_revision_and_catalog_classify_before_legacy_live_reads(self):
        self.worker()
        before = self.snapshot()
        with (patch.object(L, 'detail', side_effect=AssertionError('legacy detail before classification')),
              patch.object(L, 'binding', side_effect=AssertionError('live repository binding')),
              patch.object(L, 'revision_current', side_effect=AssertionError('live currentness')),
              patch.object(L, '_jobs', side_effect=AssertionError('unclassified raw jobs')),
              patch.object(R, 'get', side_effect=AssertionError('unclassified job detail'))):
            manager = server.api_learning(self.P, self.req(query={'project': 'APP', 'revision': self.revision['id']}))
            curator = server.api_learning(self.P, self.req(actor='curator', query={'project': 'APP', 'revision': self.revision['id']}))
            catalog = server.api_learning(self.P, self.req(query={'project': 'APP', 'kind': 'lesson'}))
        self.assertTrue(manager['recorded_only'])
        self.assertTrue(manager['protected'])
        self.assertFalse(manager['current'])
        self.assertIsNone(manager['expected_token'])
        self.assertIsNone(manager['revision']['content'])
        self.assertFalse(curator['protected'])
        self.assertEqual(curator['revision']['content'], self.revision['content'])
        item = next(x for x in catalog['items'] if x['revision_id'] == self.revision['id'])
        self.assertTrue(item['managed'])
        self.assertEqual(item['currentness'], 'not_checked')
        self.assertIsNone(item['stale'])
        self.assertEqual(self.snapshot(), before)

    def test_internal_catalog_without_authorized_projection_refuses_managed_revision(self):
        self.seal()
        with patch.object(L, 'binding', side_effect=AssertionError('unclassified live source')):
            with self.assertRaises(ApiError) as error:
                L.catalog(self.P, self.p, 'lesson')
        self.assertEqual(error.exception.code, 409)

    def test_ordinary_revision_keeps_original_detail_and_catalog_behavior(self):
        with patch.object(L, 'detail', wraps=L.detail) as ordinary:
            result = server.api_learning(self.P, self.req(query={'project': 'APP', 'revision': self.revision['id']}))
        ordinary.assert_called_once()
        self.assertEqual(result['revision']['content'], self.revision['content'])
        self.assertNotIn('managed', result['revision'])
        catalog = server.api_learning(self.P, self.req(query={'project': 'APP', 'kind': 'lesson'}))
        item = next(x for x in catalog['items'] if x['revision_id'] == self.revision['id'])
        self.assertFalse(item['stale'])
        self.assertNotIn('managed', item)

    def test_unmanaged_sibling_keeps_manual_controls_with_protected_experiment_history(self):
        candidate = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '受管兄弟独有内容'}), 'owner')
        sibling = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '普通兄弟独有内容'}), 'owner')
        self.seal(self.draft(self.body(candidate_revision_id=candidate['id'])))
        before = self.snapshot()
        with patch.object(L, 'revision_current', wraps=L.revision_current) as current:
            result = server.api_learning(self.P, self.req(query={'project': 'APP', 'revision': sibling['id']}))
        self.assertEqual([call.args[2]['id'] for call in current.call_args_list], [sibling['id']])
        self.assertFalse(result.get('managed', False))
        self.assertTrue(result['current'])
        self.assertIsNotNone(result['expected_token'])
        self.assertEqual(result['revision']['content'], sibling['content'])
        protected = next(x for x in result['history'] if x['id'] == candidate['id'])
        self.assertTrue(protected['managed'])
        self.assertTrue(protected['protected'])
        self.assertIsNone(protected['content'])
        self.assertEqual(self.snapshot(), before)

    def test_catalog_query_matches_original_card_without_exposing_private_candidate(self):
        private = 'PRIVATE_CANDIDATE_SENTINEL_7f4ad'
        candidate = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': private}), 'owner')
        self.seal(self.draft(self.body(candidate_revision_id=candidate['id'])))
        results = {}
        for query in ('合成流程检查', private, 'NO_SUCH_CARD_SENTINEL'):
            results[query] = server.api_learning(self.P, self.req(query={'project': 'APP', 'kind': 'lesson', 'q': query}))
            self.assertNotIn(private, json.dumps(results[query], ensure_ascii=False))
        self.assertEqual(len(results['合成流程检查']['items']), 1)
        self.assertEqual(results[private]['items'], [])
        self.assertEqual(results['NO_SUCH_CARD_SENTINEL']['items'], [])
        curator = server.api_learning(self.P, self.req(actor='curator', query={'project': 'APP', 'revision': candidate['id']}))
        self.assertEqual(curator['revision']['content'], candidate['content'])
        self.assertIn(private, curator['revision']['content'])

    def test_synthetic_run_cannot_inflate_operational_dashboard_counts(self):
        worker = self.worker()
        managed = self.next_material(worker)['slot']['run_id']
        ordinary = self.store.create_run(self.p['id'], None, 'fixture', 'ask', 'owner', 'ordinary task')
        self.assertNotEqual(ordinary['id'], managed)
        self.assertEqual(self.store.stats(self.p['id'])['runs'], {'queued': 1})
        self.assertEqual(self.store.stats()['runs'], {'queued': 1})
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 2)
        other_root = self.home / 'statistics-other'; other_root.mkdir()
        other = self.store.add_project('STATS', 'ordinary other project', str(other_root))
        self.store.create_run(other['id'], None, 'fixture', 'ask', 'owner', 'another ordinary task')
        self.assertEqual(self.store.stats(self.p['id'])['runs'], {'queued': 1})
        self.assertEqual(self.store.stats(other['id'])['runs'], {'queued': 1})
        self.assertEqual(self.store.stats()['runs'], {'queued': 2})
        self.store.x("UPDATE runs SET batch='experiment:broken-relation' WHERE id=?", (ordinary['id'],))
        with self.assertRaises(ApiError):
            self.store.stats()

    def test_cross_project_experiment_never_resolves_by_identifier_only(self):
        receipt = self.seal()
        other_root = self.home / 'other'; other_root.mkdir()
        self.store.add_project('OTHER', 'OTHER', str(other_root))
        with self.assertRaises(ApiError) as error:
            server.api_learning(self.P, self.req(query={'project': 'OTHER', 'experiment': receipt['experiment_id']}))
        self.assertEqual(error.exception.code, 404)
