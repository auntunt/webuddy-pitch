"""Real personal sessions, project scope and replay of version-bound decisions."""
import json
import concurrent.futures
from contextlib import contextmanager
import socket
import subprocess
from unittest.mock import patch
from urllib.parse import quote
import http.client
from http.server import ThreadingHTTPServer
import threading
from types import SimpleNamespace
import os
from pathlib import Path
import unittest

from tmh.platform import filelock, learn, login, server, tenant_runtime
from tmh.platform.tenancy import Registry
from tmh.platform.store import Store
from tests import test_tenant_gateway as fixture


@unittest.skipUnless(os.name == 'posix', 'tenant gateway requires POSIX Unix sockets')
class LessonDecisionApiTest(unittest.TestCase):
    def setUp(self):
        self.gateway = fixture.TenantGatewayTest('runTest')
        self.addCleanup(self.gateway.doCleanups)
        self.gateway.setUp()
        self.data = Path(self.gateway.reg.one('SELECT path FROM tenants WHERE id=?',
                                             (self.gateway.a,))['path'])
        self.base = '/t/' + self.gateway.a
        self.serial = 0

    def call(self, method, path, body=None, user='alice', headers=None):
        return self.gateway.request(method, self.base + path, user, body,
            token=self.gateway.token(user, self.gateway.a) if user else None,
            headers={'X-TMH': '1', 'X-Webuddy-Lesson-Actor': quote(user or '', safe=''), **(headers or {})})

    def create(self, text='正文 A\r\n第二行  ', project='SAME', user='alice'):
        status, _, card = self.call('POST', '/api/memory', {
            'action': 'lesson_create', 'project': project, 'title': '待确认经验',
            'fields': {'symptom': '提交时检查', 'fix': text}}, user)
        self.assertEqual(status, 200, card)
        self.assertEqual(card['fix'], text)
        return card

    def intent(self, card, action='confirm', **fields):
        self.serial += 1
        return {'action': action, 'expected_token': learn.revision_token(self.data, card['id']),
                'request_id': 'api-' + str(self.serial), **fields}

    def memory(self, card, body, user='alice', headers=None):
        return self.call('POST', '/api/memory', {**body, 'action': 'lesson_' + body['action'],
                         'project': 'SAME', 'lesson_id': card['id']}, user, headers)

    def legacy(self, card, body, user='owner', headers=None):
        return self.call('POST', '/api/projects/SAME/lessons/' + card['id'], body, user, headers)

    def local_legacy_server(self, *, authenticated=True, token=""):
        # A separate personal-session transport exercises the legacy handler
        # without the tenant execution gate masking its partial-write bug.
        store = Store(self.data / 'platform.db')
        self.addCleanup(store.db.close)
        platform = SimpleNamespace(data_dir=self.data, store=store, user='', public_url='',
                                   project=store.project)
        if authenticated:
            login.set_user(self.data, 'owner', 'synthetic-local-password')
        cookie = 'tmh_session=' + login.make_session(self.data, 'owner') if authenticated else ''
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(platform, token=token))
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        def call(card, body, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
            try:
                conn.request('POST', '/api/projects/SAME/lessons/' + card['id'], json.dumps(body),
                    {'Cookie': cookie, 'X-TMH': '1', 'X-Webuddy-Lesson-Actor': 'owner', 'Content-Type': 'application/json', **(headers or {})})
                result = conn.getresponse()
                return result.status, dict(result.getheaders()), json.loads(result.read())
            finally:
                conn.close()
        return call

    def ledger(self):
        # Only synthetic lesson files, never the caller's workspace data.
        return {name: (self.data / name).read_bytes() for name in ('lessons.jsonl', 'lesson_log.jsonl')
                if (self.data / name).exists()}

    def test_stale_body_is_not_confirmed_by_person_who_saw_a(self):
        card = self.create()
        request = self.intent(card)
        self.assertEqual(self.call('GET', '/api/memory?project=SAME')[0], 403)
        status, _, edited = self.memory(card, self.intent(card, 'edit', fields={'fix': '正文 B'}), user='owner')
        self.assertEqual(status, 200, edited)
        before = self.ledger()
        status, _, result = self.memory(card, request)
        self.assertEqual(status, 409, result)
        self.assertEqual(result['code'], 'lesson_changed')
        self.assertEqual(self.ledger(), before)
        self.assertEqual(learn.lesson(self.data, card['id'])['status'], 'candidate')

    def test_corrupt_decision_history_is_a_read_conflict_without_mutation(self):
        card = self.create()
        path = self.data / learn.LOG
        path.write_text(json.dumps({'kind': 'human_decision', 'lesson': card['id']}) + '\n')
        before = self.ledger()
        for endpoint in ('/api/memory?project=SAME&section=lessons', '/api/memory?section=lessons',
                         '/api/projects/SAME/learn', '/api/projects/SAME/lessons/' + card['id']):
            with self.subTest(endpoint=endpoint):
                status, _, result = self.call('GET', endpoint, user='owner')
                self.assertEqual(status, 409, result)
                self.assertEqual(result['code'], 'lesson_history_unreadable')
                self.assertEqual(self.ledger(), before)

    def test_success_replay_after_retire_returns_history_without_reactivation(self):
        card = self.create()
        request = self.intent(card)
        status, _, first = self.memory(card, request)
        self.assertEqual(status, 200, first)
        status, _, retired = self.memory(card, self.intent(card, 'retire', reason='已失效\r\n完整原因  '), user='owner')
        self.assertEqual(status, 200, retired)
        before = self.ledger()
        status, _, replay = self.memory(card, request)
        self.assertEqual(status, 200, replay)
        self.assertEqual(learn.lesson(self.data, card['id'])['status'], 'retired')
        self.assertEqual(self.ledger(), before)
        self.assertEqual(replay['receipt'], first['receipt'])
        self.assertTrue(replay['replayed'])
        self.assertTrue(replay['superseded'])
        self.assertEqual(replay['current']['card']['status'], 'retired')

    def test_legacy_invalid_action_or_reason_never_partially_edits(self):
        local_call = self.local_legacy_server()
        for extra in ({'action': 'unknown'}, {'action': 'retire'},
                      {'action': 'restore', 'why': 4},
                      {'action': 'confirm', 'why': 'A', 'reason': 'B'}):
            with self.subTest(extra=extra):
                card = self.create()
                before = self.ledger()
                status, _, result = local_call(card, self.intent(card, fields={'fix': '不该写入'}, **extra))
                self.assertEqual(status, 400, result)
                self.assertEqual(learn.lesson(self.data, card['id'])['fix'], card['fix'])
                self.assertEqual(self.ledger(), before)

    def test_both_entrypoints_require_complete_personal_version_and_request(self):
        card = self.create()
        for entry in (self.memory, self.legacy):
            for missing in ('expected_token', 'request_id'):
                request = self.intent(card)
                request.pop(missing)
                before = self.ledger()
                status, _, result = entry(card, request)
                self.assertEqual(status, 400, result)
                self.assertEqual(self.ledger(), before)
            for headers in ({'X-Webuddy-Agent': 'fixture'},):
                before = self.ledger()
                status, _, result = entry(card, self.intent(card), headers=headers)
                self.assertEqual(status, 403, result)
                self.assertEqual(self.ledger(), before)

    def test_personal_identity_binding_is_required_and_never_authenticates(self):
        card = self.create()
        for entry in (self.memory, self.legacy):
            for declared, expected in (('',400), ('bad%ZZ',400), ('%ED%A0%80',400), ('another-person',409)):
                with self.subTest(entry=entry.__name__, declared=declared):
                    before = self.ledger()
                    status, _, result = entry(card, self.intent(card),
                                              headers={'X-Webuddy-Lesson-Actor':declared})
                    self.assertEqual(status, expected, result)
                    self.assertEqual(result['code'], 'lesson_identity_changed' if expected==409 else 'invalid_lesson_decision')
                    self.assertEqual(self.ledger(), before)
        # In single-instance mode there is no tenant context token. Replacing
        # the cookie between reading and retrying still cannot change actor.
        local_call = self.local_legacy_server()
        login.set_user(self.data, 'bob', 'synthetic-bob-password')
        cookie = 'tmh_session=' + login.make_session(self.data, 'bob')
        before = self.ledger()
        status, _, result = local_call(card, self.intent(card), {'Cookie':cookie})
        self.assertEqual(status, 409, result)
        self.assertEqual(result['code'], 'lesson_identity_changed')
        self.assertEqual(self.ledger(), before)

    def test_tool_and_shared_tokens_cannot_make_personal_decisions(self):
        card = self.create()
        status, _, grant = self.call('POST', '/api/tool-connections', {
            'action': 'create', 'label': 'synthetic-tool', 'project_ids': [1],
            'scope': 'content', 'expires_days': 1, 'request_id': 'grant-personal-test'})
        self.assertEqual(status, 200, grant)
        before = self.ledger()
        for path, body in (
            ('/api/memory', {**self.intent(card), 'action': 'lesson_confirm',
                             'project': 'SAME', 'lesson_id': card['id']}),
            ('/api/projects/SAME/lessons/' + card['id'], self.intent(card))):
            status, _, result = self.gateway.request('POST', self.base + path, body=body,
                headers={'X-TMH': '1', 'Authorization': 'Bearer ' + grant['token'],
                         'X-Webuddy-Agent': 'owner', 'X-TMH-User': 'owner'})
            self.assertEqual(status, 403, result)
            self.assertEqual(self.ledger(), before)
        call = self.local_legacy_server(authenticated=False, token='synthetic-shared')
        status, _, result = call(card, self.intent(card),
            {'X-TMH-Token': 'synthetic-shared', 'X-TMH-User': 'owner'})
        self.assertEqual(status, 403, result)
        self.assertEqual(self.ledger(), before)

    def test_manager_legacy_combined_decision_and_restore_reason(self):
        card = self.create()
        # An explicit grant, never platform-owner execution privilege.
        self.gateway.change('project_grant', tenant=self.gateway.a, user='alice',
                            project_id=1, role='manager')
        status, _, confirmed = self.legacy(card, self.intent(card, fields={'fix': '完整 B\r\n  '}), user='alice')
        self.assertEqual(status, 200, confirmed)
        self.assertEqual(confirmed['receipt']['actor'], 'alice')
        self.assertEqual(confirmed['current']['card']['fix'], '完整 B\r\n  ')
        status, _, retired = self.legacy(card, self.intent(card, 'retire', reason='完整原因\r\n  '), user='alice')
        self.assertEqual(status, 200, retired)
        for action in ('confirm', 'restore'):
            before = self.ledger()
            status, _, rejected = self.legacy(card, self.intent(card, action), user='alice')
            self.assertEqual(status, 409 if action == 'confirm' else 400, rejected)
            self.assertEqual(self.ledger(), before)
        status, _, restored = self.legacy(card, self.intent(card, 'restore', reason='新事实\r\n  '), user='alice')
        self.assertEqual(status, 200, restored)
        self.assertEqual(restored['receipt']['reason'], '新事实\r\n  ')
        self.assertEqual(restored['current']['card']['status'], 'active')
        before = self.ledger()
        for action in ('share', 'take', 'unknown'):
            status, _, rejected = self.legacy(card, {'action': action}, user='alice')
            self.assertEqual(status, 403, rejected)
            self.assertEqual(self.ledger(), before)

    def test_create_rejects_unencodable_text_before_writing_any_card(self):
        before = self.ledger()
        for fields in ({'title':'坏\ud800字符', 'fields':{'symptom':'场景','fix':'正文'}},
                       {'title':'正常标题', 'fields':{'symptom':'场景','fix':'坏\udfff字符'}}):
            status, _, result = self.call('POST', '/api/memory',
                {'action':'lesson_create', 'project':'SAME', **fields})
            self.assertEqual(status, 400, result)
            self.assertEqual(result['code'], 'invalid_lesson_decision')
            self.assertEqual(self.ledger(), before)

    def test_read_dtos_keep_actual_conditions_and_all_original_sources(self):
        card = learn.add_lesson(self.data, {'project':'SAME', 'status':'candidate',
            'title':'完整条件', 'symptom':'特定场景', 'fix':'正文',
            'applicability':'只限版本 A\r\n保持尾空格  ',
            'non_applicability':'不能用于 B', 'note':'来源原文\r\n末尾  ',
            'files':['src/file-%s.py' % i for i in range(15)],
            'source_extra':{'原始依据':['完整一','完整二']}})
        before = self.ledger()
        for path in ('/api/memory?project=SAME&section=lessons', '/api/projects/SAME/learn'):
            status, _, result = self.call('GET', path, user='owner')
            self.assertEqual(status, 200, result)
            row = next(row for row in result['lessons'] if row['id']==card['id'])
            for key in ('applicability','non_applicability','note','files','source_extra'):
                self.assertEqual(row[key], card[key])
                self.assertEqual(row['snapshot']['card'][key], card[key])
            self.assertEqual(row['snapshot']['expected_token'], learn.revision_token(self.data,card['id']))
            self.assertNotIn('usage_hint',row['snapshot']['card'])
        self.assertEqual(self.ledger(), before)

    def test_narrow_read_preserves_full_card_and_scope(self):
        text = '完整\r\n条件\u2028边界\u2029例外\u0085 ' * 300
        card = self.create(text)
        status, _, snap = self.call('GET', '/api/projects/SAME/lessons/' + card['id'])
        self.assertEqual(status, 200, snap)
        self.assertEqual(snap, card['snapshot'])
        self.assertEqual(snap['card']['fix'], text)
        self.assertEqual(snap['project'], 'SAME')
        self.assertEqual(snap['lesson_id'], card['id'])
        self.assertEqual(snap['expected_token'], learn.revision_token(self.data, card['id']))
        private = self.create('其他项目原文', 'PRIVATE', 'owner')
        for path, user, expected in (
            ('/api/projects/PRIVATE/lessons/' + private['id'], 'alice', 403),
            ('/api/projects/SAME/lessons/' + private['id'], 'alice', 404),
            ('/api/projects/SAME/lessons/L999', 'alice', 404)):
            status, _, result = self.call('GET', path, user=user)
            self.assertEqual(status, expected, result)
            self.assertNotIn('其他项目原文', json.dumps(result, ensure_ascii=False))
        self.assertEqual(self.call('GET', '/api/memory?section=lessons&project=SAME')[0], 403)
        other_base = '/t/' + self.gateway.b + '/api/projects/SAME/lessons/' + card['id']
        self.assertEqual(self.gateway.request('GET', other_base, 'alice')[0], 403)

    def test_roles_remain_distinct_and_receipt_uses_session(self):
        card = self.create()
        before = self.ledger()
        status, _, result = self.legacy(card, self.intent(card), user='alice')
        self.assertEqual(status, 403, result)  # old endpoint remains manager-only
        self.assertEqual(self.ledger(), before)
        status, _, result = self.memory(card, self.intent(card, fields={'fix': '合成后的 B\r\n  '}),
                                        headers={'X-TMH-User': 'owner'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['receipt']['actor'], 'alice')
        self.assertEqual(result['receipt']['reviewed_content']['fix'], '合成后的 B\r\n  ')
        self.assertEqual(result['current']['card']['fix'], '合成后的 B\r\n  ')
        self.assertEqual(result['receipt']['reviewed_content_digest'], result['current']['content_digest'])

    def test_worker_holds_authorization_before_and_after_durable_decision(self):
        parent, child = socket.socketpair()
        parent.settimeout(5)
        self.addCleanup(parent.close)
        self.addCleanup(child.close)
        reader = parent.makefile('rb')
        self.addCleanup(reader.close)
        code = r"""
import json, os, sys
from tmh.platform import learn, tenant_runtime
original = learn.human_decision
fd = BARRIER_FD
def observed(*args, **kwargs):
    if args[6] != 'barrier-confirm':
        return original(*args, **kwargs)
    os.write(fd, (json.dumps({'pid':os.getpid(),'stage':'before','actor':args[3]})+'\n').encode())
    if os.read(fd,1) != b'x':
        raise RuntimeError('barrier closed')
    result = original(*args, **kwargs)
    os.write(fd, (json.dumps({'pid':os.getpid(),'stage':'after','actor':args[3]})+'\n').encode())
    if os.read(fd,1) != b'x':
        raise RuntimeError('barrier closed')
    return result
learn.human_decision = observed
tenant_runtime.worker(*sys.argv[1:])
""".replace('BARRIER_FD', str(child.fileno()))
        launch = subprocess.Popen
        def popen(args, *positional, **kwargs):
            if args[1:3] == ['-m', 'tmh.platform.tenant_runtime']:
                args = [args[0], '-c', code, *args[3:]]
                kwargs['pass_fds'] = (*kwargs.get('pass_fds', ()), child.fileno())
            return launch(args, *positional, **kwargs)
        with patch.object(tenant_runtime.subprocess, 'Popen', side_effect=popen):
            card = self.create()
        child.close()
        request = self.intent(card, request_id='barrier-confirm')
        token = self.gateway.token('alice', self.gateway.a)
        body = {**request, 'action':'lesson_confirm', 'project':'SAME', 'lesson_id':card['id']}
        def call():
            return self.gateway.request('POST', self.base+'/api/memory', 'alice', body,
                                        token=token, headers={'X-TMH':'1', 'X-Webuddy-Lesson-Actor':'alice'})
        def held():
            with (self.gateway.reg.path.parent / 'authorization.lock').open('a+b') as stream:
                with self.assertRaises(BlockingIOError):
                    filelock.try_lock(stream)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(call)
            try:
                marker = json.loads(reader.readline())
                pid = self.gateway.workers.live[self.gateway.a]['proc'].pid
                self.assertEqual(marker, {'pid':pid, 'stage':'before', 'actor':'alice'})
                held()
                revoke = pool.submit(self.gateway.change, 'project_revoke', tenant=self.gateway.a,
                                     user='alice', project_id=1)
                parent.sendall(b'x')
                self.assertEqual(json.loads(reader.readline()), {'pid':pid, 'stage':'after', 'actor':'alice'})
                self.assertEqual(learn.lesson(self.data, card['id'])['status'], 'active')
                held()
                parent.sendall(b'x')
                status, _, result = pending.result(timeout=5)
                self.assertEqual(status, 200, result)
                revoke.result(timeout=5)
            finally:
                parent.sendall(b'xx')
            before = self.ledger()
            self.assertEqual(self.memory(card, request)[0], 403)
            self.assertEqual(self.ledger(), before)

    def test_revocation_linearizes_before_waiting_gateway_request(self):
        card = self.create()
        token = self.gateway.token('alice', self.gateway.a)
        request = self.intent(card)
        body = {**request, 'action':'lesson_confirm', 'project':'SAME', 'lesson_id':card['id']}
        original = Registry.authorization_guard
        attempted = threading.Event()
        main = threading.get_ident()
        @contextmanager
        def observed(registry):
            if threading.get_ident() != main:
                attempted.set()
            with original(registry):
                yield
        before = self.ledger()
        with patch.object(Registry, 'authorization_guard', observed):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                with original(self.gateway.reg):
                    pending = pool.submit(self.gateway.request, 'POST', self.base+'/api/memory', 'alice', body,
                                          token=token, headers={'X-TMH':'1', 'X-Webuddy-Lesson-Actor':'alice'})
                    self.assertTrue(attempted.wait(5), 'gateway never attempted authorization')
                    self.gateway.change('project_revoke', tenant=self.gateway.a, user='alice', project_id=1)
                status, _, result = pending.result(timeout=5)
                self.assertIn(status, (403, 409), result)
                self.assertNotIn('receipt', result)
        self.assertEqual(self.ledger(), before)
        self.assertEqual(learn.lesson(self.data, card['id'])['status'], 'candidate')

    def test_revocation_rejects_success_receipt_and_narrow_read(self):
        card = self.create()
        request = self.intent(card)
        status, _, result = self.memory(card, request)
        self.assertEqual(status, 200, result)
        old_token = self.gateway.token('alice', self.gateway.a)
        self.gateway.change('project_revoke', tenant=self.gateway.a, user='alice', project_id=1)
        before = self.ledger()
        body = {**request, 'action': 'lesson_confirm', 'project': 'SAME', 'lesson_id': card['id']}
        status, _, denied = self.gateway.request('POST', self.base + '/api/memory', 'alice', body,
            token=old_token, headers={'X-TMH': '1', 'X-Webuddy-Lesson-Actor':'alice'})
        self.assertIn(status, (403, 409), denied)
        self.assertNotIn('receipt', denied)
        status, _, denied = self.memory(card, request)
        self.assertEqual(status, 403, denied)
        self.assertNotIn('receipt', denied)
        self.assertEqual(self.call('GET', '/api/projects/SAME/lessons/' + card['id'])[0], 403)
        self.assertEqual(self.ledger(), before)


if __name__ == '__main__':
    unittest.main()
