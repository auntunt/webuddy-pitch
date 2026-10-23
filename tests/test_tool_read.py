"""Personal tool reads preserve evidence without invoking live decision paths."""
from contextlib import contextmanager, ExitStack
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates, project_library, tenant_policy, tool_access, tool_read
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.sqlite_snapshot import dump_store as snapshot


def seed_candidate(store, ticket, summary='完整历史\r\n' * 1000):
    run = store.create_run(ticket['project_id'], ticket['id'], 'fixture', 'fix', 'owner', summary)
    store.x("UPDATE runs SET status='done',output=?,result=?,diff=? WHERE id=?", (summary, summary, summary, run['id']))
    cid = store.x('INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (ticket['id'], run['id'], 'agent:fixture', 'a' * 40, 'b' * 40, 'stored-requirement', 'stored-config',
                   json.dumps([{'id': 'A1', 'text': summary}]), summary, 'candidate-' + str(run['id']), 'refs/fixture/' + str(run['id']), 'historical', 'synthetic'))
    return cid, run['id']


@contextmanager
def no_live_effects(store):
    """Audit actual leaf effects; fail even if a caller catches the exception."""
    events, active = [], [True]
    def audit(event, args):
        prohibited = event in ('subprocess.Popen', 'os.system', 'os.kill', 'os.killpg', 'os.posix_spawn', 'os.fork', 'os.forkpty', 'socket.connect', 'socket.getaddrinfo',
                               'fcntl.flock', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir')
        if event == 'open':
            flags = args[2] or 0
            prohibited |= bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if active[0] and prohibited:
            events.append(event)
            raise AssertionError('tool read attempted ' + event)
    sys.addaudithook(audit)
    def authorize(action, first, second, *_):
        # SQLITE_READ/SELECT/FUNCTION/RECURSIVE are the only useful actions for
        # these projections. DDL migration is separately tested at dispatch.
        read_schema = action == 19 and first == 'table_info'
        if action not in (20, 21, 31, 33) and not read_schema:
            events.append('sqlite:' + str(action))
            return 1
        return 0
    store.db.set_authorizer(authorize)
    try:
        yield events
    finally:
        active[0] = False
        store.db.set_authorizer(None)
        if events:
            raise AssertionError('read effects observed: ' + repr(events))


class ToolReadTests(unittest.TestCase):
    def setUp(self):
        from tmh.platform import server  # Module import/cache is startup, not a business read.
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-tool-read-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.st = Store(self.data / 'platform.db')
        self.addCleanup(self.st.db.close)
        agent_api._schema(self.st)
        (self.data / 'app').mkdir()
        (self.data / 'private').mkdir()
        self.p = self.st.add_project('APP', 'visible', str(self.data / 'app'))
        self.other = self.st.add_project('PRIVATE', 'hidden', str(self.data / 'private'))
        self.t = self.st.create_ticket(self.p['id'], 'synthetic', 'owner')
        self.hidden = self.st.create_ticket(self.other['id'], 'hidden', 'owner')
        self.cid, self.rid = seed_candidate(self.st, self.t)
        self.P = SimpleNamespace(store=self.st, data_dir=self.data)
        self.req = SimpleNamespace(user='alice', h=SimpleNamespace(headers={'X-Webuddy-Agent': 'fixture'}))
        self.actor = agent_api.member_actor('alice')
        self.tool = {'scope': 'read', 'project_ids': [self.p['id']], 'user': 'alice', 'tenant': 'synthetic'}
        self.patch = ExitStack()
        self.addCleanup(self.patch.close)
        self.patch.enter_context(patch.object(tenant_policy, 'enabled', return_value=True))
        self.patch.enter_context(patch.object(tenant_policy, 'identity', return_value={'tool_connection': self.tool}))
        self.patch.enter_context(patch.object(tenant_policy, 'visible_projects', return_value=[self.p]))

    def call(self, op, **args):
        from tmh.agent_contract import validate
        return agent_api._execute(self.P, self.req, self.actor, op, validate(op, args))

    def test_all_allowed_read_branches_have_no_live_effects_or_writes(self):
        self.st.x("INSERT INTO agent_requests(agent,request_id,operation,fingerprint,arguments,resource,state,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                  (self.actor, 'pending', 'message_send', 'hash', '{}', 'ticket:' + str(self.t['id']), 'pending', 'old', 'old'))
        cases = {'status': {}, 'projects_list': {}, 'tickets_list': {}, 'ticket_get': {'ticket': self.t['key']},
                 'messages_list': {}, 'request_get': {'request_id': 'pending'}, 'run_get': {'run_id': self.rid},
                 'candidates_list': {'ticket': self.t['key']}, 'candidate_get': {'candidate_id': self.cid},
                 'library_get': {'project': 'APP'}, 'library_search': {'project': 'APP', 'query': 'synthetic'},
                 'library_read': {'project': 'APP', 'revision_id': 'a' * 32, 'path': 'rules.md'},
                 'preview_get': {'ticket': self.t['key']}}
        self.assertEqual(set(cases), set(tool_access.READ_OPERATIONS))
        before = snapshot(self.st)
        # Library schema is initialized at fixture registration, preserving the
        # product migration rather than removing it to satisfy this assertion.
        with no_live_effects(self.st):
            for op, args in cases.items():
                with self.subTest(operation=op):
                    if op == 'library_read':
                        with self.assertRaises(ApiError) as error:
                            self.call(op, **args)
                        self.assertEqual(error.exception.code, 404)
                    else:
                        result = self.call(op, **args)
                        self.assertIsInstance(result, dict)
        self.assertEqual(snapshot(self.st), before)

    def test_candidate_preserves_all_historical_records_and_uses_unknown(self):
        text = '不能截断的原始中文\r\n' * 1200
        self.st.x('INSERT INTO candidate_assessments(candidate_id,author,verification_hash,preview_hash,results,note,created) VALUES(?,?,?,?,?,?,?)',
                  (self.cid, 'reviewer', 'old-v', 'old-p', json.dumps([{'status': 'pass', 'text': text}]), text, 'old'))
        self.st.x('INSERT INTO candidate_decisions(candidate_id,author,decision,evidence_hash,note,created) VALUES(?,?,?,?,?,?)',
                  (self.cid, 'owner', 'accept', 'old-e', text, 'old'))
        folder = self.data / 'runs' / str(self.rid)
        folder.mkdir(parents=True)
        raw = json.dumps({'check': 'pass', 'note': text}, ensure_ascii=False) + '\r\n'
        (folder / 'verify.json').write_bytes(raw.encode())
        with no_live_effects(self.st):
            value = self.call('candidate_get', candidate_id=self.cid)
        for name in ('current', 'verification_passed', 'preview_ready', 'technical_acceptance', 'ready_for_human', 'human_accepted'):
            self.assertIsNone(value[name], name)
        self.assertEqual(value['state'], 'not_checked')
        self.assertEqual(value['preview_url'], '')
        self.assertEqual(value['history']['run']['verification']['raw'], raw)
        self.assertEqual(value['history']['decisions'][0]['note'], text)
        self.assertEqual(value['history']['assessments'][0]['note'], text)
        self.assertEqual(json.loads(value['history']['assessments'][0]['results'])[0]['text'], text)
        self.assertTrue(value['history']['historical'])

    def test_mismatched_run_and_project_are_rejected_before_pagination(self):
        hidden_cid, hidden_run = seed_candidate(self.st, self.hidden)
        self.st.x('UPDATE code_candidates SET run_id=? WHERE id=?', (-1, hidden_cid))
        self.st.x('UPDATE code_candidates SET run_id=? WHERE id=?', (hidden_run, self.cid))
        good, good_run = seed_candidate(self.st, self.t)
        with self.assertRaises(ApiError) as error:
            self.call('candidate_get', candidate_id=self.cid)
        self.assertEqual(error.exception.code, 404)
        page = self.call('candidates_list', ticket=self.t['key'], limit=1)
        self.assertEqual([r['id'] for r in page['items']], [good])
        self.assertFalse(page['has_more'])
        self.assertEqual(page['next_after'], good)
        self.assertEqual(page['items'][0]['run_id'], good_run)
        for op, args in [('candidate_get', {'candidate_id': hidden_cid}), ('candidates_list', {'ticket': self.hidden['key']}),
                         ('run_get', {'run_id': hidden_run})]:
            with self.subTest(op=op), self.assertRaises(ApiError) as error:
                self.call(op, **args)
            self.assertEqual(error.exception.code, 403)

    def test_library_pending_record_is_not_recovered_or_relabelled_failed(self):
        self.st.x("INSERT INTO knowledge_revisions(id,project_id,source_id,commit_sha,root,analyzer,status,stage,created,author) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  ('pending', self.p['id'], 1, 'c' * 40, self.p['root'], 'old', 'building', 'extract', 'old', 'owner'))
        before = snapshot(self.st)
        with no_live_effects(self.st):
            value = self.call('library_get', project='APP')
        self.assertEqual(value['revisions'][0]['status'], 'building')
        self.assertEqual(value['revisions'][0]['runtime_status'], 'not_checked')
        self.assertEqual(snapshot(self.st), before)
        self.assertFalse((self.data / 'project-library').exists())

    def test_pending_request_stays_unknown_and_full_run_history_preserves_since(self):
        self.st.x("INSERT INTO agent_requests(agent,request_id,operation,fingerprint,arguments,resource,state,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                  (self.actor, 'pending', 'message_send', 'hash', '{}', 'ticket:1', 'pending', 'old', 'old'))
        result = self.call('request_get', request_id='pending')
        self.assertEqual(result['state'], 'pending')
        self.assertTrue(result['needs_reconcile'])
        self.assertIsNone(result['result'])
        run = self.st.run(self.rid)
        result = self.call('run_get', run_id=self.rid, since=10)
        self.assertEqual(result['output'], run['output'][10:])
        self.assertEqual(result['history']['run']['output'], run['output'])
        self.assertEqual(result['prompt'], run['prompt'])
        self.assertIsNone(result['can_retry'])

    def test_nested_recheck_wrong_project_or_ticket_cannot_leak(self):
        from tmh.platform import recheck_operations
        self.st.db.executescript(recheck_operations.SCHEMA)
        self.st.db.commit()
        values = [(self.other['id'], self.hidden['id'], 'FOREIGN-PRIVATE-OUTPUT'),
                  (self.p['id'], self.hidden['id'], 'WRONG-TICKET-OUTPUT'),
                  (self.p['id'], self.t['id'], '完整本项目复检\r\n' * 1000)]
        for project, tid, content in values:
            self.st.x('INSERT INTO verification_operations(source_run,project_id,ticket_id,author,status,created,output) VALUES(?,?,?,?,?,?,?)',
                      (self.rid, project, tid, 'fixture', 'done', 'old', content))
        for op, args in [('run_get', {'run_id': self.rid}), ('candidate_get', {'candidate_id': self.cid}),
                         ('ticket_get', {'ticket': self.t['key']})]:
            with self.subTest(op=op), no_live_effects(self.st):
                result = self.call(op, **args)
            encoded = json.dumps(result, ensure_ascii=False)
            self.assertNotIn('FOREIGN-PRIVATE-OUTPUT', encoded)
            self.assertNotIn('WRONG-TICKET-OUTPUT', encoded)
            history = result['history']
            source = history if op == 'run_get' else history['run'] if op == 'candidate_get' else history['runs'][0]
            self.assertEqual(len(source['rechecks']), 1)
            self.assertEqual(source['rechecks'][0]['record']['output'], values[-1][2])

    def test_unreadable_evidence_history_preserves_complete_original_and_crlf(self):
        raw = '{invalid evidence ' + '完整不能省略的内容' * 300 + '\r\n'
        folder = self.data / 'evidence'
        folder.mkdir()
        (folder / (self.t['key'] + '.jsonl')).write_bytes(raw.encode())
        with no_live_effects(self.st):
            result = self.call('ticket_get', ticket=self.t['key'])
        self.assertEqual(result['history']['evidence_original']['raw'], raw)
        self.assertEqual(result['history']['evidence'][0]['raw'], raw)

    def test_nested_probe_source_and_result_bindings_cannot_cross_projects(self):
        from tmh.platform import harness_probes
        harness_probes.schema(self.st)
        hidden_cid, _ = seed_candidate(self.st, self.hidden)
        good = {'candidate_id': self.cid, 'ticket_id': self.t['id'], 'ticket': self.t['key'],
                'project_id': self.p['id'], 'base': 'a' * 40, 'commit': 'b' * 40}
        foreign = dict(good, candidate_id=hidden_cid, ticket_id=self.hidden['id'],
                       ticket=self.hidden['key'], project_id=self.other['id'], criteria=['FOREIGN-CRITERIA'])
        pid = self.st.x('INSERT INTO harness_probe_runs(candidate_id,author,source,status,created) VALUES(?,?,?,?,?)',
                        (self.cid, 'fixture', json.dumps(foreign), 'done', 'old'))
        folder = self.data / 'harness-probes' / str(pid)
        folder.mkdir(parents=True)
        complete = json.dumps({'source': foreign, 'detail': 'FOREIGN-PROBE-RESULT'})
        (folder / 'result.json').write_bytes(complete.encode())
        for label, source, result_source in [('source', foreign, foreign), ('result', good, foreign)]:
            self.st.x('UPDATE harness_probe_runs SET source=? WHERE id=?', (json.dumps(source), pid))
            (folder / 'result.json').write_text(json.dumps({'source': result_source, 'detail': 'FOREIGN-PROBE-RESULT'}))
            for op, args in [('candidate_get', {'candidate_id': self.cid}), ('candidates_list', {'ticket': self.t['key']}),
                             ('ticket_get', {'ticket': self.t['key']})]:
                with self.subTest(binding=label, operation=op), no_live_effects(self.st):
                    with self.assertRaises(ApiError) as error:
                        self.call(op, **args)
                    self.assertEqual(error.exception.code, 409)
                    self.assertNotIn('FOREIGN', str(error.exception))
        # Correct historical source and long CRLF result remain complete.
        text = '完整探测历史\r\n' * 1000
        raw = json.dumps({'source': good, 'detail': text}, ensure_ascii=False) + '\r\n'
        (folder / 'result.json').write_bytes(raw.encode())
        with no_live_effects(self.st):
            result = self.call('candidate_get', candidate_id=self.cid)
        self.assertEqual(result['history']['harness_probes'][0]['result']['raw'], raw)

    def test_adopted_history_binds_run_and_preserves_valid_fix_or_legacy_records(self):
        _, hidden_run = seed_candidate(self.st, self.hidden)
        self.st.event(self.t['id'], 'owner', 'adopt', data={'run': hidden_run, 'commit': 'c' * 40})
        for op in ('preview_get', 'ticket_get'):
            with self.subTest(operation=op), no_live_effects(self.st):
                with self.assertRaises(ApiError) as error:
                    self.call(op, ticket=self.t['key'])
                self.assertEqual(error.exception.code, 404)
        self.st.event(self.t['id'], 'owner', 'adopt', data={'run': self.rid, 'commit': 'b' * 40})
        with no_live_effects(self.st):
            result = self.call('preview_get', ticket=self.t['key'])
        self.assertEqual(result['historical_binding']['run'], self.rid)
        self.st.event(self.t['id'], 'owner', 'adopt', data={'commit': 'a' * 40})
        with no_live_effects(self.st):
            result = self.call('preview_get', ticket=self.t['key'])
        self.assertEqual(result['historical_binding'], {'commit': 'a' * 40})
        self.assertIsNone(result['matches_run'])

    def test_candidate_latest_preview_is_explicit_ticket_history_not_candidate_proof(self):
        from tmh.platform import preview
        cid, rid = seed_candidate(self.st, self.t)
        recorded = {'state': 'up', 'run_id': rid, 'candidate_id': cid, 'commit_full': 'd' * 40,
                    'url': 'https://synthetic.invalid/newer'}
        preview._save(self.data, {self.t['key']: recorded})
        with no_live_effects(self.st):
            result = self.call('candidate_get', candidate_id=self.cid)
        self.assertNotIn('preview', result['history'])
        history = result['history']['ticket_preview']
        self.assertEqual(history['recorded'], recorded)
        self.assertEqual(history['scope'], 'ticket')
        self.assertEqual(history['binding_status'], 'not_checked')
        self.assertTrue(history['historical'])
        self.assertEqual(result['preview_url'], '')
        self.assertIsNone(result['preview_ready'])
        _, private_run = seed_candidate(self.st, self.hidden)
        preview._save(self.data, {self.t['key']: dict(recorded, run_id=private_run)})
        for op, args in [('candidate_get', {'candidate_id': self.cid}), ('preview_get', {'ticket': self.t['key']})]:
            with self.subTest(op=op), self.assertRaises(ApiError) as error:
                self.call(op, **args)
            self.assertEqual(error.exception.code, 404)

    def test_invalid_utf8_is_preserved_losslessly_in_all_saved_readers(self):
        original = b'header\r\n' + b'\xff\x00' * 2000 + b'complete-tail\r\n'
        folder = self.data / 'runs' / str(self.rid)
        folder.mkdir(parents=True)
        for name in ('verify.json', 'lifecycle.json'):
            (folder / name).write_bytes(original)
        evidence = self.data / 'evidence'
        evidence.mkdir()
        (evidence / (self.t['key'] + '.jsonl')).write_bytes(original)
        with no_live_effects(self.st):
            result = self.call('ticket_get', ticket=self.t['key'])
        history = result['history']
        self.assertIsNone(result['requirement_hash'])
        self.assertEqual(result['requirement_status'], 'not_checked')
        for record in (history['evidence_original'], history['runs'][0]['verification'], history['runs'][0]['lifecycle']):
            self.assertEqual(record['record_status'], 'invalid_utf8')
            self.assertEqual(record['encoding'], 'base64')
            self.assertEqual(base64.b64decode(record['raw_base64']), original)
            self.assertEqual(record['sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(record['byte_length'], len(original))
            self.assertIsNone(record['recorded'])

    def test_incomplete_jsonl_never_issues_requirement_digest_and_valid_keeps_identity(self):
        folder = self.data / 'evidence'
        folder.mkdir()
        path = folder / (self.t['key'] + '.jsonl')
        valid = json.dumps({'kind': 'intake', 'data': {'contract': '完整合同\r\n' * 1000}}, ensure_ascii=False) + '\r\n'
        for bad in ('{bad\r\n', 'null\r\n', '[]\r\n', '{}\r\n', valid + '{bad-tail', valid + '0\r\n'):
            path.write_bytes(bad.encode())
            with self.subTest(raw=bad[:25]), no_live_effects(self.st):
                result = self.call('ticket_get', ticket=self.t['key'])
            self.assertEqual(result['history']['evidence_original']['raw'], bad)
            self.assertIsNone(result['requirement_hash'])
            self.assertEqual(result['requirement_status'], 'not_checked')
        path.write_bytes((valid + json.dumps({'kind': 'other', 'body': 'complete'}) + '\r\n').encode())
        expected = agent_api._requirement(self.t, self.st)
        with no_live_effects(self.st):
            result = self.call('ticket_get', ticket=self.t['key'])
        self.assertEqual(result['requirement_hash'], expected)
        self.assertEqual(result['requirement_status'], 'stored_inputs')

    def test_legal_json_unicode_separators_do_not_split_history_records(self):
        folder = self.data / 'evidence'
        folder.mkdir()
        value = {'kind': 'intake', 'body': '合法分隔符：\u2028段落\u2029下一行\u0085完整\r\n尾部'}
        raw = json.dumps(value, ensure_ascii=False) + '\r\n'
        (folder / (self.t['key'] + '.jsonl')).write_bytes(raw.encode())
        with no_live_effects(self.st):
            result = self.call('ticket_get', ticket=self.t['key'])
        self.assertEqual(result['history']['evidence_original']['raw'], raw)
        self.assertEqual(result['history']['evidence'], [value])
        expected = agent_api._requirement(self.t, self.st, contract_records=[value])
        self.assertEqual(result['requirement_hash'], expected)
        self.assertEqual(result['requirement_status'], 'stored_inputs')

    def test_recheck_artifact_declared_operation_and_run_must_match_database(self):
        from tmh.platform import recheck_operations
        self.st.db.executescript(recheck_operations.SCHEMA)
        self.st.db.commit()
        _, hidden_run = seed_candidate(self.st, self.hidden)
        opid = self.st.x('INSERT INTO verification_operations(source_run,project_id,ticket_id,author,status,created) VALUES(?,?,?,?,?,?)',
                         (self.rid, self.p['id'], self.t['id'], 'fixture', 'done', 'old'))
        folder = self.data / 'verification-operations' / 'runs' / str(opid)
        folder.mkdir(parents=True)
        path = folder / 'verification.json'
        for binding in ({'id': opid + 999, 'source_run': self.rid}, {'id': opid, 'source_run': hidden_run},
                        {'id': str(opid), 'source_run': self.rid}, 'malformed'):
            path.write_text(json.dumps({'recheck_operation': binding, 'checked_diff': 'FOREIGN-PRIVATE-ARTIFACT'}))
            for op, args in [('run_get', {'run_id': self.rid}), ('candidate_get', {'candidate_id': self.cid}),
                             ('ticket_get', {'ticket': self.t['key']})]:
                with self.subTest(binding=binding, op=op), no_live_effects(self.st):
                    with self.assertRaises(ApiError) as error:
                        self.call(op, **args)
                    self.assertEqual(error.exception.code, 409)
                    self.assertNotIn('FOREIGN-PRIVATE', str(error.exception))
        body = '完整复检原文\r\n' * 1000
        raw = json.dumps({'recheck_operation': {'id': opid, 'source_run': self.rid}, 'checked_diff': body}, ensure_ascii=False) + '\r\n'
        path.write_bytes(raw.encode())
        with no_live_effects(self.st):
            result = self.call('run_get', run_id=self.rid)
        self.assertEqual(result['history']['rechecks'][0]['verification']['raw'], raw)
        path.write_bytes(json.dumps({'checked_diff': body}, ensure_ascii=False).encode())
        with no_live_effects(self.st):
            result = self.call('run_get', run_id=self.rid)
        self.assertEqual(result['history']['rechecks'][0]['verification']['recorded']['checked_diff'], body)
        self.assertEqual(result['history']['rechecks'][0]['binding_status'], 'not_checked')

    def test_corrupt_shared_preview_is_unknown_not_empty_and_never_returns_foreign_raw(self):
        folder = self.data / 'previews'
        folder.mkdir()
        path = folder / 'state.json'
        for raw in (b'{"PRIVATE-1":{"secret":"FOREIGN-PREVIEW"}', b'\xffFOREIGN-PREVIEW', b'[]', b'{"APP-1":null}'):
            path.write_bytes(raw)
            for op, args in [('preview_get', {'ticket': self.t['key']}), ('candidate_get', {'candidate_id': self.cid}),
                             ('candidates_list', {'ticket': self.t['key']}), ('ticket_get', {'ticket': self.t['key']})]:
                with self.subTest(raw=raw[:20], op=op), no_live_effects(self.st):
                    with self.assertRaises(ApiError) as error:
                        self.call(op, **args)
                    self.assertEqual(error.exception.code, 409)
                    self.assertNotIn('FOREIGN-PREVIEW', str(error.exception))
        own = {'state': 'up', 'record': '完整预览\r\n' * 1000}
        path.write_text(json.dumps({self.t['key']: own, self.hidden['key']: {'secret': 'FOREIGN-PREVIEW'}}))
        with no_live_effects(self.st):
            result = self.call('preview_get', ticket=self.t['key'])
        self.assertEqual(result['preview']['recorded'], own)
        self.assertNotIn('FOREIGN-PREVIEW', json.dumps(result))
        path.unlink()
        with no_live_effects(self.st):
            result = self.call('preview_get', ticket=self.t['key'])
        self.assertEqual(result['preview']['recorded'], {})
        self.assertEqual(result['preview']['state'], 'not_checked')

    def test_run_verify_recheck_copy_rejects_foreign_source_but_preserves_prior_operations(self):
        from tmh.platform import recheck_operations
        self.st.db.executescript(recheck_operations.SCHEMA)
        self.st.db.commit()
        _, hidden_run = seed_candidate(self.st, self.hidden)
        def operation(rid, project, tid):
            return self.st.x('INSERT INTO verification_operations(source_run,project_id,ticket_id,author,status,created) VALUES(?,?,?,?,?,?)',
                             (rid, project, tid, 'fixture', 'done', 'old'))
        old = operation(self.rid, self.p['id'], self.t['id'])
        own = operation(self.rid, self.p['id'], self.t['id'])
        foreign = operation(hidden_run, self.other['id'], self.hidden['id'])
        folder = self.data / 'runs' / str(self.rid)
        folder.mkdir(parents=True)
        path = folder / 'verify.json'
        for binding in ({'id': own, 'source_run': hidden_run}, {'id': foreign, 'source_run': self.rid}):
            path.write_text(json.dumps({'recheck_operation': binding, 'checked_diff': 'FOREIGN-VERIFY-COPY'}))
            for op, args in [('run_get', {'run_id': self.rid}), ('candidate_get', {'candidate_id': self.cid}),
                             ('ticket_get', {'ticket': self.t['key']})]:
                with self.subTest(binding=binding, op=op), no_live_effects(self.st):
                    with self.assertRaises(ApiError) as error:
                        self.call(op, **args)
                    self.assertEqual(error.exception.code, 409)
        record = {'recheck_operation': {'id': own, 'source_run': self.rid},
                  'previous_verifications': [{'recheck_operation': {'id': old, 'source_run': self.rid}}],
                  'checked_diff': '完整本项目复检副本\r\n' * 1000}
        raw = json.dumps(record, ensure_ascii=False) + '\r\n'
        path.write_bytes(raw.encode())
        with no_live_effects(self.st):
            result = self.call('run_get', run_id=self.rid)
        self.assertEqual(result['history']['verification']['raw'], raw)
        record['recheck_operation']['id'] = 999999
        path.write_bytes(json.dumps(record, ensure_ascii=False).encode())
        with no_live_effects(self.st):
            result = self.call('run_get', run_id=self.rid)
        self.assertEqual(result['history']['verification']['recorded'], record)
        self.assertEqual(result['history']['verification']['binding_status'], 'not_checked')

    def test_schema_compatibility_remains_initialized_and_repeated_reads_do_not_write(self):
        self.st.x('ALTER TABLE agent_requests DROP COLUMN principal')
        self.st.x('ALTER TABLE agent_requests DROP COLUMN connection_id')
        self.req.body = {}
        agent_api.dispatch(self.P, self.req, 'status')
        columns = {r['name'] for r in self.st.q('PRAGMA table_info(agent_requests)')}
        self.assertIn('principal', columns)
        self.assertIn('connection_id', columns)
        before = snapshot(self.st)
        agent_api.dispatch(self.P, self.req, 'status')
        self.assertEqual(snapshot(self.st), before)


from tests import test_project_library as library_fixtures


@unittest.skipUnless(os.name == 'posix', 'real local library build uses POSIX supervision')
class ToolFixedLibraryReadTests(unittest.TestCase):
    setUp = library_fixtures.ProjectLibraryTest.setUp
    tearDown = library_fixtures.ProjectLibraryTest.tearDown
    git = library_fixtures.ProjectLibraryTest.git
    project = library_fixtures.ProjectLibraryTest.project
    start = library_fixtures.ProjectLibraryTest.start
    build = library_fixtures.ProjectLibraryTest.build
    wait_terminal = library_fixtures.ProjectLibraryTest.wait_terminal

    def test_successful_fixed_read_and_search_are_complete_without_live_effects(self):
        original = 'Approval 组织知识完整原文\r\n' * 1200
        p = self.project('APP', {'rules.md': original})
        revision = self.build(p)
        P = SimpleNamespace(store=self.store, data_dir=self.store.path.parent)
        req = SimpleNamespace(user='alice')
        from tmh.platform import server
        with patch.object(tenant_policy, 'enabled', return_value=True), \
             patch.object(tenant_policy, 'identity', return_value={'tool_connection': {'scope': 'read'}}), \
             patch.object(tenant_policy, 'visible_projects', return_value=[p]):
            before = snapshot(self.store)
            with no_live_effects(self.store):
                result = agent_api._execute(P, req, 'member:alice', 'library_read',
                    {'project': 'APP', 'revision_id': revision['id'], 'path': 'rules.md'})
                found = agent_api._execute(P, req, 'member:alice', 'library_search',
                    {'project': 'APP', 'query': 'Approval', 'limit': 1, 'offset': 0})
            self.assertEqual(result['content'], original)
            self.assertEqual(result['commit'], revision['commit'])
            self.assertTrue(found['items'])
            self.assertEqual(found['items'][0]['revision_id'], revision['id'])
            self.assertEqual(snapshot(self.store), before)
