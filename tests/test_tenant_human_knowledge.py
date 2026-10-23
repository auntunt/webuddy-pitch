"""Real gateway sessions bind knowledge confirmations to the signed-in person."""
import hashlib
from http.server import ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest

from tmh import kb, kbqa
from tmh.platform import server
from tmh.platform.store import Store
from tests import test_tenant_gateway as gateway_fixture


@unittest.skipUnless(os.name == 'posix', 'tenant gateway requires POSIX Unix sockets')
class TenantHumanKnowledgeTest(unittest.TestCase):
    def setUp(self):
        # Compose the existing real HTTP/private-worker fixture; inheritance
        # would recollect all of its unrelated test methods in this module.
        self.gateway = gateway_fixture.TenantGatewayTest('runTest')
        self.addCleanup(self.gateway.doCleanups)
        self.gateway.setUp()
        row = self.gateway.reg.one('SELECT path FROM tenants WHERE id=?', (self.gateway.a,))
        self.root = Path(row['path']) / 'repositories' / 'same'
        self.page = kb.page_path(self.root, 'index')
        self.page.parent.mkdir(parents=True, exist_ok=True)
        self.original = ('---\nid: index\ntitle: 人工确认夹具\nstatus: 待确认\n---\n'
                         '# 完整业务说明\n\n保留原始依据，不从旧的自动采用记录推断人工同意。\n')
        self.page.write_text(self.original, encoding='utf-8')
        kb.save_registry(self.root, {'index': {'title': '人工确认夹具', 'status': kb.STATUS_DRAFT,
            'learning': {'active_revision': 'old-machine-revision', 'pending': '',
                         'confirmed_sha256': '', 'decision_id': ''}}})
        self.question = kbqa.ask(self.root, '已确认业务行为是什么？', ['index'], by='owner')
        self.triage = 'synthetic-triage'
        kbqa._append(self.root, 'triage.jsonl', {'id': self.triage, 'request': '已有能力',
                                               'verdict': '需要人判断'})
        self.base = '/t/' + self.gateway.a + '/api/projects/SAME/kb/'
        status, _, value = self.gateway.request('GET', '/t/' + self.gateway.a + '/api/meta', 'alice')
        self.assertEqual(status, 200, value)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def payloads(self):
        return (('confirm', {'id': 'index', 'note': '已核对完整原文'}),
                ('answer', {'n': self.question, 'text': '业务原文答复'}),
                ('overrule', {'id': self.triage, 'reason': '已检查原始依据', 'verdict': '可以做'}))

    def request(self, action, body, *, user='alice', headers=None):
        return self.gateway.request('POST', self.base + action, user, body,
            token=self.gateway.token('alice', self.gateway.a), headers={'X-TMH': '1', **(headers or {})})

    def test_explicit_agent_requests_cannot_record_any_human_knowledge_fact(self):
        before = self.snapshot()
        for action, body in self.payloads():
            with self.subTest(action=action):
                status, _, result = self.request(action, body, headers={'X-Webuddy-Agent': 'fixture'})
                self.assertEqual(status, 403, result)
                self.assertEqual(self.snapshot(), before)

    def test_display_name_without_real_session_cannot_confirm_answer_or_overrule(self):
        before = self.snapshot()
        for action, body in self.payloads():
            with self.subTest(action=action):
                status, _, result = self.request(action, body, user=None,
                    headers={'X-TMH-User': 'alice', 'X-TMH-Token': 'synthetic-shared-token'})
                self.assertEqual(status, 401, result)
                self.assertEqual(self.snapshot(), before)

    def test_body_cannot_impersonate_another_author_and_rejection_writes_nothing(self):
        before = self.snapshot()
        for action, body in self.payloads():
            with self.subTest(action=action):
                status, _, result = self.request(action, dict(body, by='owner'))
                self.assertEqual(status, 403, result)
                self.assertEqual(self.snapshot(), before)

    def test_legacy_shared_token_admits_transport_but_never_human_confirmation(self):
        store = Store(self.root.parents[1] / 'platform.db')
        self.addCleanup(store.db.close)
        platform = SimpleNamespace(data_dir=self.gateway.data, store=store, user='', public_url='')
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(platform, token='synthetic-shared'))
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        before = self.snapshot()
        for action, body in self.payloads():
            with self.subTest(action=action):
                connection = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
                try:
                    connection.request('POST', '/api/projects/SAME/kb/' + action, json.dumps(body),
                        {'Content-Type': 'application/json', 'X-TMH': '1', 'X-TMH-Token': 'synthetic-shared',
                         'X-TMH-User': 'alice'})
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    self.assertEqual(response.status, 403, result)
                finally:
                    connection.close()
                self.assertEqual(self.snapshot(), before)

    def test_human_confirmation_binds_current_content_and_full_note_to_session(self):
        note = '这是完整人工核对说明。' * 150
        before = self.page.read_text(encoding='utf-8')
        status, _, result = self.request('confirm', {'id': 'index', 'note': note, 'by': 'alice'},
                                         headers={'X-TMH-User': 'owner'})
        self.assertEqual(status, 200, result)
        record = json.loads((self.page.parent / '.pages.json').read_text())['index']
        self.assertEqual(record['status'], kb.STATUS_OK)
        self.assertEqual(record['confirmed_by'], 'alice')
        self.assertEqual(record['confirm_note'], note)
        self.assertEqual(record['learning']['active_revision'], '')
        manual = record['learning']['manual_confirmations'][-1]
        current = self.page.read_text(encoding='utf-8')
        self.assertEqual(manual['by'], 'alice')
        self.assertEqual(manual['note'], note)
        self.assertEqual(manual['before_content'], before)
        self.assertEqual(manual['confirmed_content'], current)
        self.assertEqual(manual['confirmed_sha256'], hashlib.sha256(current.encode()).hexdigest())
        self.assertEqual(manual['previous_active_revision'], 'old-machine-revision')

    def test_human_answer_preserves_original_text_with_real_person_attribution(self):
        text = '业务方原始答复。' * 200 + '\n第二行完整保留。'
        status, _, result = self.request('answer', {'n': self.question, 'text': text},
                                         headers={'X-TMH-User': 'owner'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['pages'], ['index'])
        answer = kbqa.questions(self.root)[0]['answer']
        self.assertTrue(answer.startswith('已答复（alice，'), answer)
        content = self.page.read_text(encoding='utf-8')
        self.assertIn('alice 答复（问题 #', content)
        self.assertIn(text.replace('\n', '\n  '), content)
        events = kbqa._jsonl(self.root, 'questions.jsonl')
        self.assertEqual(events[-1]['ev'], 'answer')
        self.assertEqual(events[-1]['by'], 'alice')

    def test_human_overrule_records_session_person_and_full_reason(self):
        reason = '逐条核对原始依据。' * 200
        status, _, result = self.request('overrule', {'id': self.triage, 'reason': reason,
                                                     'verdict': '可以做', 'by': 'alice'},
                                         headers={'X-TMH-User': 'owner'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['by'], 'alice')
        self.assertEqual(result['reason'], reason)
        self.assertEqual(kbqa._jsonl(self.root, 'triage-overrule.jsonl')[-1], result)


if __name__ == '__main__':
    unittest.main()
