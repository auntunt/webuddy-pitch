"""Comments retain exact text and one durable receipt across lost replies/restarts."""
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tmh.platform.errors import ApiError
from tmh.platform.server import api_comment, make_handler
from tmh.platform.store import Store


WORKER = r'''
import json, os, sys, time
from pathlib import Path
from types import SimpleNamespace
from tmh.platform.store import Store
from tmh.platform.server import api_comment
p = json.loads(sys.stdin.read())
s = Store(Path(p['database']))
if p.get('gate'):
    gate = Path(p['gate'])
    gate.with_name(gate.name + '.' + str(os.getpid()) + '.ready').write_text('ready')
    until = time.monotonic() + 10
    while not gate.exists():
        if time.monotonic() > until:
            raise RuntimeError('test start barrier timed out')
        time.sleep(0.01)
if p.get('crash_before_receipt'):
    s.db.create_function('crash_comment', 0, lambda: os._exit(91))
    s.x('CREATE TEMP TRIGGER crash_receipt BEFORE INSERT ON comment_receipts BEGIN SELECT crash_comment(); END;')
P = SimpleNamespace(store=s, ticket=s.ticket)
r = api_comment(P, SimpleNamespace(body=p['body'], user=p['user']), p['ticket'])
if p.get('drop_reply'):
    os._exit(0)
print(json.dumps(r, ensure_ascii=False))
s.db.close()
'''


class CommentIdempotencyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-comment-retry-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.database = self.folder / 'platform.db'
        self.store = Store(self.database)
        self.addCleanup(self.store.db.close)
        p = self.store.add_project('COMMENT', '评论回执夹具', str(self.folder))
        self.ticket = self.store.create_ticket(p['id'], '准确保留沟通')
        self.P = SimpleNamespace(store=self.store, ticket=self.store.ticket, data_dir=self.folder, user='fallback')
        self.store.x('CREATE TABLE touch_audit (ticket_id INTEGER)')
        self.store.x('CREATE TRIGGER audit_touch AFTER UPDATE OF updated ON tickets BEGIN INSERT INTO touch_audit VALUES(NEW.id); END;')

    def post(self, body, request_id='retry-request-1', user='alice', ticket=None, **extras):
        data = {'body': body, **extras}
        if request_id is not None:
            data['request_id'] = request_id
        return api_comment(self.P, SimpleNamespace(body=data, user=user), ticket or self.ticket['key'])

    def comments(self):
        return self.store.q("SELECT * FROM events WHERE kind='comment' ORDER BY id")

    def test_same_request_returns_same_receipt_and_touches_once(self):
        text = '  原话第一行\n第二行\t\n'
        first = self.post(text)
        second = self.post(text)
        self.assertEqual(first, second)
        self.assertEqual(len(self.comments()), 1)
        self.assertEqual(self.comments()[0]['body'], text)
        self.assertEqual(first, {'ok': True, 'event_id': self.comments()[0]['id'], 'request_id': 'retry-request-1'})
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [{'ticket_id': self.ticket['id']}])

    def test_legacy_call_keeps_response_and_exact_text_without_deduplication(self):
        text = '\n  legacy full text  \r\n'
        self.assertEqual(self.post(text, request_id=None), {'ok': True})
        self.assertEqual(self.post(text, request_id=None), {'ok': True})
        self.assertEqual([c['body'] for c in self.comments()], [text, text])

    def test_same_request_changed_text_conflicts_without_touching(self):
        self.post('original')
        before = self.store.q('SELECT * FROM touch_audit')
        with self.assertRaises(ApiError) as caught:
            self.post('original ')
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual([c['body'] for c in self.comments()], ['original'])
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), before)

    def test_different_requests_can_intentionally_send_identical_comments(self):
        first = self.post('same words', request_id='one')
        second = self.post('same words', request_id='two')
        self.assertEqual(len(self.comments()), 2)
        self.assertNotEqual(first['event_id'], second['event_id'])

    def test_request_is_scoped_to_real_user_ticket_and_database(self):
        self.post('alice on first ticket', author='body-spoof', user='alice')
        self.post('bob on first ticket', user='bob')
        second_ticket = self.store.create_ticket(self.ticket['project_id'], 'second ticket')
        self.post('alice on second ticket', ticket=second_ticket['key'])
        other = Store(self.folder / 'other.db')
        self.addCleanup(other.db.close)
        project = other.add_project('COMMENT', 'separate workspace', str(self.folder))
        ticket = other.create_ticket(project['id'], 'same key')
        result = api_comment(SimpleNamespace(store=other, ticket=other.ticket),
                             SimpleNamespace(body={'body': 'separate workspace', 'request_id': 'retry-request-1'}, user='alice'), ticket['key'])
        self.assertTrue(result['ok'])
        self.assertEqual([(x['author'], x['ticket_id']) for x in self.comments()],
                         [('alice', self.ticket['id']), ('bob', self.ticket['id']), ('alice', second_ticket['id'])])
        self.assertEqual([x['body'] for x in other.events(ticket['id']) if x['kind'] == 'comment'], ['separate workspace'])

    def test_expected_author_mismatch_is_409_before_any_write_or_replay(self):
        for expected in ('bob', '', None, 42):
            with self.subTest(expected=expected):
                with self.assertRaises(ApiError) as caught:
                    self.post('do not attribute to the switched account', expected_author=expected)
                self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.comments(), [])
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [])
        receipt = self.post('confirmed author', expected_author='alice')
        self.assertTrue(receipt['ok'])
        with self.assertRaises(ApiError) as caught:
            self.post('confirmed author', expected_author='bob')
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(len(self.comments()), 1)

    def test_expected_workspace_mismatch_is_409_without_write_or_replay(self):
        for expected in (str(self.folder / 'other'), '', None, 42):
            with self.subTest(expected=expected):
                with self.assertRaises(ApiError) as caught:
                    self.post('keep old workspace draft', expected_workspace=expected)
                self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.comments(), [])
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [])
        first = self.post('workspace confirmed', expected_workspace=str(self.folder))
        self.assertTrue(first['ok'])
        with self.assertRaises(ApiError) as caught:
            self.post('workspace confirmed', expected_workspace=str(self.folder / 'other'))
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.post('workspace confirmed', expected_workspace=str(self.folder)), first)
        self.assertEqual(len(self.comments()), 1)

    def test_a_page_not_shown_the_path_confirms_the_workspace_by_its_id(self):
        from tmh.platform.server import _workspace_id
        here = _workspace_id(SimpleNamespace(data_dir=self.folder))
        elsewhere = _workspace_id(SimpleNamespace(data_dir=self.folder / 'other'))
        self.assertNotIn(str(self.folder), here)
        with self.assertRaises(ApiError) as caught:
            self.post('stale managed page', expected_workspace=elsewhere)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.comments(), [])
        self.assertTrue(self.post('managed page comment', expected_workspace=here)['ok'])
        self.assertEqual(len(self.comments()), 1)

    def test_old_page_cannot_write_same_ticket_key_after_workspace_switch(self):
        self.post('original workspace comment', expected_workspace=str(self.folder))
        other_folder = self.folder / 'switched-workspace'
        other_folder.mkdir()
        other = Store(other_folder / 'platform.db')
        self.addCleanup(other.db.close)
        project = other.add_project('COMMENT', 'new workspace at same origin', str(other_folder))
        ticket = other.create_ticket(project['id'], 'same key in new workspace')
        self.assertEqual(ticket['key'], self.ticket['key'])
        body = {'body': 'old page retry', 'request_id': 'retry-request-1',
                'expected_author': 'alice', 'expected_workspace': str(self.folder)}
        P = SimpleNamespace(store=other, ticket=other.ticket, data_dir=other_folder)
        before = other.ticket(ticket['id'])
        with self.assertRaises(ApiError) as caught:
            api_comment(P, SimpleNamespace(body=body, user='alice'), ticket['key'])
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(other.ticket(ticket['id']), before)
        self.assertEqual([c for c in other.events(ticket['id']) if c['kind'] == 'comment'], [])
        self.assertEqual(other.q('SELECT * FROM comment_receipts'), [])
        body['expected_workspace'] = str(other_folder)
        self.assertTrue(api_comment(P, SimpleNamespace(body=body, user='alice'), ticket['key'])['ok'])
        self.assertEqual([c['body'] for c in other.events(ticket['id']) if c['kind'] == 'comment'], ['old page retry'])

    def test_invalid_token_or_empty_text_has_no_writes(self):
        for value in ('', '   ', None, 0, False, [], {}):
            with self.subTest(token=value):
                with self.assertRaises(ApiError) as caught:
                    api_comment(self.P, SimpleNamespace(body={'body': 'valid', 'request_id': value}, user='alice'), self.ticket['key'])
                self.assertEqual(caught.exception.code, 400)
        for value in ('', ' \n\t', None, 0, [], {}):
            with self.subTest(body=value):
                with self.assertRaises(ApiError) as caught:
                    self.post(value)
                self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.comments(), [])
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [])

    def worker(self, data=None, drop_reply=False, gate=None, crash_before_receipt=False):
        payload = {'database': str(self.database), 'ticket': self.ticket['key'], 'user': 'alice',
                   'body': data or {'body': 'process durable text', 'request_id': 'durable-token'}, 'drop_reply': drop_reply,
                   'gate': str(gate) if gate else None, 'crash_before_receipt': crash_before_receipt}
        return subprocess.run([sys.executable, '-c', WORKER], input=json.dumps(payload), text=True,
                              cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, timeout=15)

    def test_lost_reply_then_new_process_replays_the_committed_comment(self):
        lost = self.worker(drop_reply=True)
        self.assertEqual(lost.returncode, 0, lost.stderr)
        self.assertEqual(lost.stdout, '')
        self.assertEqual(len(self.comments()), 1)
        recovered = self.worker()
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        reply = json.loads(recovered.stdout)
        self.assertEqual(reply['event_id'], self.comments()[0]['id'])
        self.assertEqual(len(self.comments()), 1)
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [{'ticket_id': self.ticket['id']}])

    def test_separate_processes_racing_same_request_write_one_comment(self):
        gate = self.folder / 'start-race'
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(self.worker, gate=gate) for _ in range(5)]
            until = time.monotonic() + 8
            while len(list(self.folder.glob('start-race.*.ready'))) != 5 and time.monotonic() < until:
                time.sleep(0.01)
            self.assertEqual(len(list(self.folder.glob('start-race.*.ready'))), 5)
            gate.write_text('all five stores are open; start together')
            results = [f.result(timeout=15) for f in futures]
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(r.stdout) for r in results]
        self.assertTrue(all(r == replies[0] for r in replies))
        self.assertEqual(len(self.comments()), 1)
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [{'ticket_id': self.ticket['id']}])

    def test_process_dies_before_receipt_commit_then_retry_has_no_partial_write(self):
        before = self.store.ticket(self.ticket['id'])
        crashed = self.worker(crash_before_receipt=True)
        self.assertEqual(crashed.returncode, 91, crashed.stderr)
        self.assertEqual(crashed.stdout, '')
        self.assertEqual(self.comments(), [])
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [])
        self.assertEqual(self.store.q('SELECT * FROM comment_receipts'), [])
        self.assertEqual(self.store.ticket(self.ticket['id']), before)
        retried = self.worker()
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(json.loads(retried.stdout)['event_id'], self.comments()[0]['id'])
        self.assertEqual(len(self.comments()), 1)
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [{'ticket_id': self.ticket['id']}])

    def test_receipt_failure_rolls_back_comment_and_touch(self):
        self.store.x("CREATE TRIGGER reject_receipt BEFORE INSERT ON comment_receipts BEGIN SELECT RAISE(ABORT, 'fixture receipt failure'); END;")
        before = self.store.ticket(self.ticket['id'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.post('atomic text')
        self.assertEqual(self.comments(), [])
        self.assertEqual(self.store.q('SELECT * FROM touch_audit'), [])
        self.assertEqual(self.store.ticket(self.ticket['id']), before)
        self.assertFalse(self.store.db.in_transaction)
        self.store.x('DROP TRIGGER reject_receipt')
        self.assertTrue(self.post('atomic text')['ok'])
        self.assertEqual(len(self.comments()), 1)

    def test_http_session_author_beats_body_and_header_and_switch_is_rejected(self):
        from tmh.platform import login
        login.set_user(self.folder, 'alice', 'fixture-password')
        login.set_user(self.folder, 'bob', 'fixture-password')
        alice = login.make_session(self.folder, 'alice')
        bob = login.make_session(self.folder, 'bob')
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.P))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        def close():
            httpd.shutdown(); httpd.server_close(); thread.join(3)
        self.addCleanup(close)
        def send(cookie):
            body = {'body': '  authenticated full text\n', 'request_id': 'session-token',
                    'expected_author': 'alice', 'user': 'mallory', 'author': 'mallory'}
            req = urllib.request.Request('http://127.0.0.1:%d/api/tickets/%s/comments' %
                                         (httpd.server_port, self.ticket['key']), data=json.dumps(body).encode(),
                                         headers={'X-TMH': '1', 'Content-Type': 'application/json', 'X-TMH-User': 'mallory',
                                                  'Cookie': 'tmh_session=' + cookie})
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, json.loads(error.read())
        self.assertEqual(send(alice)[0], 200)
        self.assertEqual(send(bob)[0], 409)
        self.assertEqual(send(alice)[0], 200)
        self.assertEqual([(c['author'], c['body']) for c in self.comments()], [('alice', '  authenticated full text\n')])


if __name__ == '__main__':
    unittest.main()
