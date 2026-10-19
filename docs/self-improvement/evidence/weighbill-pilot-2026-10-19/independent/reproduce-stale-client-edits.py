"""Real API/SQLite stale-client reproduction; no source or live data writes."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
REPO = Path('/Users/auntlee/workspace/weighbill-system')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient
from weighbill.adapters.vision_scripted import ScriptedVision
from weighbill.bootstrap import build_service
from weighbill.config import Settings
from weighbill.domain import Record
from weighbill.http_api import create_app

SOURCES = ['weighbill/http_api.py', 'weighbill/service.py', 'weighbill/domain.py',
           'weighbill/adapters/store_sqlite.py', 'weighbill/static/report.html']


def manifest():
    return {'head': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
            'status': subprocess.check_output(['git', '-C', str(REPO), 'status', '--short'], text=True),
            'sha256': {p: hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in SOURCES}}


def run_case(name, action):
    folder = OUT / name
    folder.mkdir(exist_ok=False)
    transcript = []
    with tempfile.TemporaryDirectory(prefix='weighbill-review-gap-') as temporary:
        data = Path(temporary)
        vision = ScriptedVision()
        svc = build_service(Settings(data_dir=str(data), record_store='sqlite', blob_store='local',
                                     event_sink='null', reviewers=['reviewer-A', 'reviewer-B']), vision=vision)
        fields = {'客户名': '隔离测试客户', '序号': 'WB202610190001', '日期': '2026-10-19',
                  '入站时间': '08:00', '出站时间': '08:20', '车号': '鲁A12345', '货名': '原料甲',
                  '收费': '', '总重': '11000', '皮重': '10000', '净重': '1000'}
        rec = Record(id='synthetic-concurrent-record', created_at='2026-10-19T08:20:00',
                     uploader='synthetic-uploader', batch_id='synthetic-batch', seq_in_batch=1,
                     orig_key=None, crop_key=None, sig_key=None, fields=fields, warnings=[],
                     weight_ok=1, weight_msg='11000 - 10000 = 1000', status='auto_ok',
                     stage='submitted', submitted_by='synthetic-uploader',
                     submitted_at='2026-10-19T08:20:00', ref_no='JC-20261019-0001')
        svc.store.insert(rec)
        client = TestClient(create_app(svc))
        path = '/api/v1/records/' + rec.id

        def request(actor, method, route, body=None):
            response = client.request(method, route, json=body, headers={'X-Portal-User': actor})
            entry = {'actor': actor, 'method': method, 'path': route, 'request': body,
                     'status': response.status_code, 'response': response.json(),
                     'response_headers': dict(response.headers),
                     'database_version_after': svc.store.get(rec.id).version}
            transcript.append(entry)
            return entry

        def page_payload(snapshot, changes):
            # Matches report.html act(): all form fields and metadata are sent.
            return {'fields': dict(snapshot['fields'], **changes), 'doc_type': snapshot['doc_type'],
                    'customer': snapshot.get('customer') or '', 'origin_id': snapshot.get('origin_id') or ''}

        result = action(request, page_payload, path, rec.id)
        history = request('reviewer-A', 'GET', path + '/history')['response']['history']
        final = request('reviewer-A', 'GET', path)['response']
        result.update(final=final, history=history, scripted_vision_calls=vision.calls)
        source_db = sqlite3.connect(data/'ledger.db')
        destination = sqlite3.connect(folder/'fixture-final.db')
        source_db.backup(destination)
        destination.close()
        source_db.close()
        client.close()
    (folder/'http-transcript.json').write_text(json.dumps(transcript, ensure_ascii=False, indent=2)+'\n')
    (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def stale_edit(request, payload, path, rid):
    a = request('reviewer-A', 'GET', path)['response']
    b = request('reviewer-B', 'GET', path)['response']
    saved_b = request('reviewer-B', 'PATCH', path, payload(b, {'总重': '10900', '净重': '900'}))
    saved_a = request('reviewer-A', 'PATCH', path, payload(a, {'货名': '甲只想改货名'}))
    return {'case': 'two users opened the same old record; B fixes weights; A changes only cargo name',
            'b_status': saved_b['status'], 'a_status': saved_a['status'],
            'a_read_weight': a['fields']['净重'], 'b_saved_weight': saved_b['response']['fields']['净重'],
            'a_final_weight': saved_a['response']['fields']['净重'],
            'silently_overwrote_b': saved_a['status']==200 and saved_a['response']['fields']['净重']=='1000',
            'public_version_present': 'version' in a}


def stale_approve(request, payload, path, rid):
    a = request('reviewer-A', 'GET', path)['response']
    b = request('reviewer-B', 'GET', path)['response']
    saved_b = request('reviewer-B', 'PATCH', path, payload(b, {'总重': '10900', '净重': '900'}))
    approved = request('reviewer-A', 'POST', '/api/v1/records/approve', {'ids': [rid]})
    final = request('reviewer-A', 'GET', path)['response']
    return {'case': 'A reviews old displayed weights; B changes them; A approves by record id',
            'a_observed_weight': a['fields']['净重'], 'b_saved_weight': saved_b['response']['fields']['净重'],
            'approve_status': approved['status'], 'approval': approved['response'],
            'approved_unseen_weight': final['stage']=='approved' and final['fields']['净重']!=a['fields']['净重']}


def retry_after_lost_ack(request, payload, path, rid):
    a = request('reviewer-A', 'GET', path)['response']
    draft = payload(a, {'货名': '甲待重试的货名'})
    first = request('reviewer-A', 'PATCH', path, copy.deepcopy(draft))
    # Model a lost response AFTER the real API committed the update. No extra
    # product exception is injected; the client simply does not use this ACK.
    b = request('reviewer-B', 'GET', path)['response']
    saved_b = request('reviewer-B', 'PATCH', path, payload(b, {'总重': '10900', '净重': '900'}))
    retried = request('reviewer-A', 'PATCH', path, copy.deepcopy(draft))
    return {'case': 'A save commits but its response is lost; B corrects weights; A retries the identical body',
            'transport_scope': 'lost ACK is explicitly modeled; no real browser network drop was injected',
            'first_save_status': first['status'], 'b_save_status': saved_b['status'],
            'retry_status': retried['status'],
            'retry_overwrote_b': retried['status']==200 and retried['response']['fields']['净重']=='1000'}


before = manifest()
(OUT/'source-before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2)+'\n')
results = {name: run_case(name, action) for name, action in
           [('stale-edit', stale_edit), ('stale-approve', stale_approve), ('lost-ack-retry', retry_after_lost_ack)]}
after = manifest()
(OUT/'source-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2)+'\n')
summary = {'source_unchanged': before==after, 'head': before['head'],
           'stale_edit_overwrote_b': results['stale-edit']['silently_overwrote_b'],
           'approved_unseen_weight': results['stale-approve']['approved_unseen_weight'],
           'lost_ack_retry_overwrote_b': results['lost-ack-retry']['retry_overwrote_b']}
(OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if not summary['source_unchanged']:
    raise SystemExit('Source changed during independent reproduction')
if not all(summary[k] for k in ['stale_edit_overwrote_b', 'approved_unseen_weight', 'lost_ack_retry_overwrote_b']):
    raise SystemExit('Expected gap did not reproduce in every scenario')
