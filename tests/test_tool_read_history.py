"""Nested historical identities must not inherit the outer record's identity."""
import json
import unittest

from tmh.platform import harness_probes, recheck_operations
from tmh.platform.errors import ApiError
from tests import test_tool_read as fixtures
from tests.test_tool_read import no_live_effects, seed_candidate


class NestedToolHistoryTests(unittest.TestCase):
    setUp = fixtures.ToolReadTests.setUp
    call = fixtures.ToolReadTests.call

    def operation(self, run, project, ticket):
        return self.st.x('INSERT INTO verification_operations(source_run,project_id,ticket_id,author,status,created) '
                         'VALUES(?,?,?,?,?,?)', (run, project, ticket, 'fixture', 'done', 'old'))

    def history_fixture(self):
        self.st.db.executescript(recheck_operations.SCHEMA)
        self.st.db.commit()
        _, foreign_run = seed_candidate(self.st, self.hidden)
        old = self.operation(self.rid, self.p['id'], self.t['id'])
        own = self.operation(self.rid, self.p['id'], self.t['id'])
        foreign = self.operation(foreign_run, self.other['id'], self.hidden['id'])
        paths = [self.data / 'runs' / str(self.rid) / 'verify.json',
                 self.data / 'verification-operations' / 'runs' / str(own) / 'verification.json']
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        return old, own, foreign, foreign_run, paths

    def readers(self):
        return [('run_get', {'run_id': self.rid}), ('candidate_get', {'candidate_id': self.cid}),
                ('candidates_list', {'ticket': self.t['key']}), ('ticket_get', {'ticket': self.t['key']})]

    def test_nested_foreign_recheck_binding_is_rejected_in_both_artifact_copies(self):
        old, own, foreign, foreign_run, paths = self.history_fixture()
        bindings = [{'id': foreign, 'source_run': foreign_run}, {'id': foreign, 'source_run': self.rid},
                    {'id': old, 'source_run': foreign_run}, {'id': foreign},
                    {'source_run': foreign_run}, {'id': True, 'source_run': self.rid},
                    {'id': 2 ** 63, 'source_run': self.rid}]
        for path in paths:
            for binding in bindings:
                for wrapped in (False, True):
                    prior = {'recheck_operation': binding, 'checked_diff': 'PRIVATE-NESTED-HISTORY'}
                    # The wrapper is the actual fixloop writer's shape. Also
                    # retain support for older flat snapshots and deeper history.
                    if wrapped:
                        prior = {'diff': 'prior', 'verification': {'previous_verifications': [
                            {'diff': 'earlier', 'verification': prior}]}}
                    record = {'recheck_operation': {'id': own, 'source_run': self.rid},
                              'previous_verifications': [prior]}
                    raw = (json.dumps(record) + '\r\n').encode()
                    path.write_bytes(raw)
                    for op, args in self.readers():
                        with self.subTest(copy=path.name, binding=binding, wrapped=wrapped, op=op), no_live_effects(self.st):
                            with self.assertRaises(ApiError) as error:
                                self.call(op, **args)
                            self.assertEqual(error.exception.code, 409)
                            self.assertNotIn('PRIVATE-NESTED-HISTORY', str(error.exception))
                    self.assertEqual(path.read_bytes(), raw)
            path.unlink()

    def test_own_prior_round_and_unbound_legacy_history_keep_complete_originals(self):
        old, own, foreign, foreign_run, paths = self.history_fixture()
        for binding in ({'id': old, 'source_run': self.rid}, {}, {'id': 987654, 'source_run': self.rid},
                        {'id': 2 ** 63 - 1, 'source_run': self.rid}):
            previous = {'checked_diff': '  完整旧轮次\r\n\u2028\u2029尾\t' * 2000}
            if binding:
                previous['recheck_operation'] = binding
            record = {'recheck_operation': {'id': own, 'source_run': self.rid},
                      'previous_verifications': [{'diff': '完整之前的 diff\r\n', 'verification': previous}]}
            raw = (json.dumps(record, ensure_ascii=False, indent=2).replace('\n', '\r\n') + '\r\n').encode()
            for path in paths:
                path.write_bytes(raw)
            with no_live_effects(self.st):
                result = self.call('run_get', run_id=self.rid)
            history = result['history']
            copies = [history['verification'], next(x for x in history['rechecks'] if x['record']['id'] == own)['verification']]
            for copy in copies:
                self.assertEqual(copy['raw'].encode(), raw)
                self.assertEqual(copy['recorded'], record)
            self.assertIsNone(result['verification'])
            self.assertEqual(result['verification_status'], 'not_checked')
            self.assertEqual(history['verification']['binding_status'], 'stored_match')
            for path in paths:
                self.assertEqual(path.read_bytes(), raw)

    def test_probe_artifact_source_requires_json_type_identity(self):
        self.st.db.executescript(harness_probes.SCHEMA)
        self.st.db.commit()
        source = {'candidate_id': self.cid, 'ticket_id': self.t['id'], 'project_id': self.p['id'], 'ticket': self.t['key']}
        pid = self.st.x('INSERT INTO harness_probe_runs(candidate_id,author,source,status,created) VALUES(?,?,?,?,?)',
                        (self.cid, 'fixture', json.dumps(source), 'done', 'old'))
        path = self.data / 'harness-probes' / str(pid) / 'result.json'
        path.parent.mkdir(parents=True)
        for key in ('candidate_id', 'ticket_id', 'project_id'):
            for bad in (True, float(source[key]), str(source[key])):
                value = {'source': dict(source, **{key: bad}), 'note': 'MISMATCHED-PROBE'}
                path.write_bytes(json.dumps(value).encode())
                for op, args in [('candidate_get', {'candidate_id': self.cid}), ('ticket_get', {'ticket': self.t['key']})]:
                    with self.subTest(key=key, bad=repr(bad), op=op), no_live_effects(self.st):
                        with self.assertRaises(ApiError) as error:
                            self.call(op, **args)
                        self.assertEqual(error.exception.code, 409)
                        self.assertNotIn('MISMATCHED-PROBE', str(error.exception))
        raw = (json.dumps({'source': source, 'note': '完整探测\r\n' * 2000}, ensure_ascii=False) + '\r\n').encode()
        path.write_bytes(raw)
        with no_live_effects(self.st):
            result = self.call('candidate_get', candidate_id=self.cid)
        self.assertEqual(result['history']['harness_probes'][0]['result']['raw'].encode(), raw)

    def test_top_and_nested_declared_project_and_ticket_are_bound(self):
        old, own, foreign, foreign_run, paths = self.history_fixture()
        for path in paths:
            for key, valid, wrong in (('project_id', self.p['id'], self.other['id']),
                                      ('ticket_id', self.t['id'], self.hidden['id'])):
                for bad in (wrong, True, float(valid), str(valid)):
                    for nested in (False, True):
                        binding = {'id': old if nested else own, 'source_run': self.rid, key: bad}
                        record = {'recheck_operation': binding, 'checked_diff': 'FOREIGN-DECLARATION'}
                        if nested:
                            record = {'recheck_operation': {'id': own, 'source_run': self.rid},
                                      'previous_verifications': [{'verification': record}]}
                        raw = json.dumps(record).encode()
                        path.write_bytes(raw)
                        for op, args in self.readers():
                            with self.subTest(key=key, bad=repr(bad), nested=nested, copy=path.name, op=op), no_live_effects(self.st):
                                with self.assertRaises(ApiError) as error:
                                    self.call(op, **args)
                                self.assertEqual(error.exception.code, 409)
                                self.assertNotIn('FOREIGN-DECLARATION', str(error.exception))
                        self.assertEqual(path.read_bytes(), raw)
            path.unlink()
        record = {'recheck_operation': {'id': own, 'source_run': self.rid,
                                       'project_id': self.p['id'], 'ticket_id': self.t['id']},
                  'previous_verifications': [{'verification': {'recheck_operation': {
                      'id': old, 'source_run': self.rid, 'project_id': self.p['id'], 'ticket_id': self.t['id']}}}]}
        raw = json.dumps(record).encode()
        for path in paths:
            path.write_bytes(raw)
        with no_live_effects(self.st):
            result = self.call('run_get', run_id=self.rid)
        self.assertEqual(result['history']['verification']['raw'].encode(), raw)
        self.assertEqual(result['history']['verification']['binding_status'], 'stored_match')

    def test_deep_probe_source_keeps_valid_json_and_checks_leaf_types(self):
        self.st.db.executescript(harness_probes.SCHEMA)
        self.st.db.commit()
        details = {'value': 1}
        for _ in range(520):
            details = {'next': details}
        source = {'candidate_id': self.cid, 'ticket_id': self.t['id'], 'project_id': self.p['id'],
                  'ticket': self.t['key'], 'details': details}
        pid = self.st.x('INSERT INTO harness_probe_runs(candidate_id,author,source,status,created) VALUES(?,?,?,?,?)',
                        (self.cid, 'fixture', json.dumps(source), 'done', 'old'))
        path = self.data / 'harness-probes' / str(pid) / 'result.json'
        path.parent.mkdir(parents=True)
        raw = (json.dumps({'source': source, 'note': '完整深层JSON\r\n'}, ensure_ascii=False) + '\r\n').encode()
        path.write_bytes(raw)
        for op, args in [('candidate_get', {'candidate_id': self.cid}), ('ticket_get', {'ticket': self.t['key']})]:
            with self.subTest(op=op), no_live_effects(self.st):
                result = self.call(op, **args)
                history = result['history']['harness_probes'] if op == 'candidate_get' else result['harness_library']['history']
                self.assertEqual(history[0]['result']['raw'].encode(), raw)
        wrong = json.loads(raw)
        leaf = wrong['source']['details']
        for _ in range(520):
            leaf = leaf['next']
        leaf['value'] = True
        path.write_bytes(json.dumps(wrong).encode())
        for op, args in [('candidate_get', {'candidate_id': self.cid}), ('ticket_get', {'ticket': self.t['key']})]:
            with self.subTest(op=op), no_live_effects(self.st):
                with self.assertRaises(ApiError) as error:
                    self.call(op, **args)
                self.assertEqual(error.exception.code, 409)
