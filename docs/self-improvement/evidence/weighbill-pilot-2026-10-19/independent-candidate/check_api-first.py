"""Independent real HTTP/SQLite checks; only temporary synthetic data is mutated."""
import argparse
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import traceback

sys.dont_write_bytecode = True
p = argparse.ArgumentParser()
p.add_argument('--repo', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--baseline', action='store_true')
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(a.repo))
from fastapi.testclient import TestClient
from weighbill.adapters.vision_scripted import ScriptedVision
from weighbill.bootstrap import build_service
from weighbill.config import Settings
from weighbill.domain import Record
from weighbill.http_api import create_app

PREFIX = '/pv/INDEPENDENT-1/__commit/' + 'b' * 40
SOURCES = ['weighbill/config.py', 'weighbill/http_api.py', 'weighbill/service.py',
           'weighbill/static/report.html', 'weighbill/static/capture.html', 'weighbill/static/sw.js']
def manifest():
    return {'head': subprocess.check_output(['git','rev-parse','HEAD'], cwd=a.repo, text=True).strip(),
            'sha256': {f:hashlib.sha256((a.repo/f).read_bytes()).hexdigest() for f in SOURCES}}
def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')
def record(i):
    return Record(id=f'synthetic-{i}', created_at='2026-10-19T08:20:00', uploader='synthetic-uploader',
                  batch_id=f'synthetic-batch-{i}', seq_in_batch=1, orig_key=None, crop_key=None,
                  sig_key=None, fields={'序号':f'SYN-{i:04d}', '日期':'2026-10-19',
                  '入站时间':'08:00', '出站时间':'08:20', '车号':f'鲁A{i:05d}',
                  '货名':'原料甲','总重':'11000','皮重':'10000','净重':'1000','备注':'合成完整备注'},
                  warnings=[], weight_ok=1, status='auto_ok', stage='submitted',
                  submitted_by='synthetic-uploader', submitted_at='2026-10-19T08:20:00',
                  ref_no=f'SYN-20261019-{i:04d}')

class Case:
    def __init__(self, data, prefix=''):
        self.data, self.prefix = data, prefix
        kw = dict(data_dir=str(data), record_store='sqlite', blob_store='local', event_sink='null',
                  reviewers=['A','B'], local_user='guest')
        if prefix: kw.update(base_path=prefix, local_preview_origins=['http://localhost:9090'])
        self.settings = Settings(**kw)
        self.vision = ScriptedVision()
        self.svc = build_service(self.settings, vision=self.vision)
        for i in range(1,4): self.svc.store.insert(record(i))
        self.client = TestClient(create_app(self.svc), base_url='http://127.0.0.1:8173', client=('127.0.0.1',4000))
        self.transcript=[]
    def req(self, method, suffix, body=None, actor='A', headers=None, client=None):
        r=(client or self.client).request(method,self.prefix+suffix,json=body,headers={'X-Portal-User':actor,**(headers or {})})
        try: content=r.json()
        except ValueError: content={'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'text':r.text if len(r.content)<100000 else None}
        self.transcript.append({'method':method,'path':self.prefix+suffix,'body':copy.deepcopy(body),
                                'actor':actor,'request_headers':headers,'status':r.status_code,
                                'response':content,'response_headers':dict(r.headers)})
        return r
    def get(self, i=1): return self.req('GET',f'/api/v1/records/synthetic-{i}').json()
    def version(self, row):
        # Baseline has no public version. Explicit protocol contrast uses the
        # fixture's actual store version, never an omitted conditional request.
        return row.get('version', self.svc.get(row['id']).version)
    def payload(self, row, **fields):
        return {'expected_version':self.version(row),'fields':{**row['fields'],**fields},
                'doc_type':row['doc_type'],'customer':row.get('customer') or '', 'origin_id':row.get('origin_id') or ''}
    def patch(self, row, **fields): return self.req('PATCH','/api/v1/records/'+row['id'],self.payload(row,**fields))
    def approve(self, ids, versions): return self.req('POST','/api/v1/records/approve',{'ids':ids,'versions':versions})
    def state(self, i=1):
        rid=f'synthetic-{i}'
        return {'view':self.svc.record_view(self.svc.get(rid)), 'version':self.svc.get(rid).version,'history':self.svc.history(rid)}

def stale_save(c):
    old=c.get(); draft=c.payload(old,货名='A 仅改货名');b=c.get()
    assert c.patch(b,总重='10900',净重='900').status_code==200
    before=c.state()
    r=c.req('PATCH','/api/v1/records/synthetic-1',draft)
    assert r.status_code==409, (r.status_code,r.json())
    assert c.state()==before

def stale_approve(c):
    old=c.get();v=c.version(old)
    assert c.patch(c.get(),总重='10900',净重='900').status_code==200
    before=c.state();r=c.approve(['synthetic-1'],{'synthetic-1':v})
    assert r.status_code==200
    assert r.json()['approved']==[],r.json()
    assert r.json()['skipped'][0]['code']=='Conflict'
    assert c.state()==before

def lost_ack(c):
    old=c.get();body=c.payload(old,货名='A ACK 丢失草稿')
    assert c.req('PATCH','/api/v1/records/synthetic-1',body).status_code==200
    assert c.patch(c.get(),总重='10900',净重='900').status_code==200
    before=c.state();r=c.req('PATCH','/api/v1/records/synthetic-1',body)
    assert r.status_code==409,(r.status_code,r.json())
    assert c.state()==before

def reconcile_approve_reopen(c):
    old=c.get();v=c.version(old);draft=c.payload(old,货名='A deliberate goods')
    assert c.patch(c.get(),总重='10900',净重='900').status_code==200
    assert c.req('PATCH','/api/v1/records/synthetic-1',draft).status_code==409
    latest=c.get();r=c.patch(latest,货名='A deliberate goods');assert r.status_code==200
    saved=r.json();assert saved['version']>v and saved['fields']['净重']=='900'
    assert c.approve([saved['id']],{saved['id']:saved['version']}).json()['approved']==[saved['id']]
    approved=c.get();assert approved['stage']=='approved' and approved['approved_by']=='A'
    reopen=c.patch(approved,备注='need review').json()
    assert reopen['stage']=='submitted' and reopen['approved_by'] is None
    history=c.svc.history(saved['id'])
    assert any(h['action']=='审核通过' and h['actor']=='A' for h in history)
    assert any(h['detail'].get('changes',{}).get('货名',{}).get('to')=='A deliberate goods' for h in history),history

def mixed_batch(c):
    rows=[c.get(i) for i in range(1,4)]; versions={r['id']:c.version(r) for r in rows}
    assert c.patch(rows[0],备注='B newer').status_code==200
    versions[rows[1]['id']]=None
    before=[c.state(i) for i in (1,2)]
    res=c.approve([r['id'] for r in rows],versions).json()
    assert res['approved']==['synthetic-3'],res
    assert [x['code'] for x in res['skipped']]==['Conflict','InvalidInput']
    assert [c.state(i) for i in (1,2)]==before

def invalid_conditions(c):
    old=c.state()
    for version in [None,True,False,'0',-1,1.0,[],{}]:
        for prefix in ['/api','/api/v1']:
            r=c.req('PATCH',prefix+'/records/synthetic-1',{'expected_version':version,'fields':{'货名':'bad'}})
            assert r.status_code==422,(version,prefix,r.status_code,r.json())
        r=c.approve(['synthetic-1'],{'synthetic-1':version})
        assert r.json()['approved']==[] and r.json()['skipped'][0]['code']=='InvalidInput'
        assert c.state()==old
    r=c.approve(['synthetic-1'],{})
    assert r.json()['approved']==[] and r.json()['skipped'][0]['code']=='InvalidInput'
    for versions in [None,True,False,'x',0,[]]:
        assert c.approve(['synthetic-1'],versions).status_code==422
        assert c.state()==old

def permissions(c):
    row=c.get();before=c.state()
    r=c.req('PATCH','/api/v1/records/synthetic-1',c.payload(row,货名='forbidden'),actor='not-reviewer')
    assert r.status_code==403
    r=c.req('POST','/api/v1/records/approve',{'ids':[row['id']],'versions':{row['id']:c.version(row)}},actor='not-reviewer')
    assert r.status_code==403 and c.state()==before

def zero_and_compatibility(c):
    row=c.get();assert c.version(row)==0
    r=c.patch(row,货名='first version');assert r.status_code==200
    assert r.json()['version']==1
    # Explicit documented exception: old clients can still omit conditions.
    assert c.req('PATCH','/api/records/synthetic-1',{'fields':{'货名':'legacy'}}).status_code==200
    assert c.req('POST','/api/v1/records/approve',{'ids':['synthetic-1']}).json()['approved']==['synthetic-1']

def concurrent_instances(c):
    other=build_service(c.settings,vision=ScriptedVision())
    other_client=TestClient(create_app(other),base_url='http://127.0.0.1:8173')
    row=c.get();body=c.payload(row,备注='concurrent')
    barrier=threading.Barrier(2)
    for svc in [c.svc,other]:
        original=svc.get
        def get(rid,original=original):
            r=original(rid);barrier.wait(timeout=5);return r
        svc.get=get
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(c.req,'PATCH','/api/v1/records/synthetic-1',body,actor,client=client)
                     for actor,client in [('A',c.client),('B',other_client)]]
            rs=[f.result(timeout=10) for f in futures]
        assert sorted(r.status_code for r in rs)==[200,409],[r.text for r in rs]
    finally:
        # Restore bound methods before subsequent fixture readback.
        del c.svc.get;del other.get;other_client.close()
    assert c.svc.get(row['id']).version==1 and len(c.svc.history(row['id']))==1

def prefix_and_csrf(c):
    row=c.get();assert row['version']==0
    pages=['/','/report','/static/report.html','/static/capture.html']
    for page in pages:
        r=c.req('GET',page);assert r.status_code==200
        assert '__WB_BASE_PATH__' not in r.text and c.prefix+'/static/app.css' in r.text
    assert c.req('GET','/static/app.css').status_code==200
    sw=c.req('GET','/sw.js');assert sw.status_code==200 and sw.headers['service-worker-allowed']==c.prefix+'/'
    assert c.client.get('/api/v1/records').status_code==404
    for extra in [{'Origin':'http://evil.invalid'},{'Origin':'null'},{'Sec-Fetch-Site':'cross-site'},
                  {'Origin':'http://evil.invalid','X-Forwarded-Host':'evil.invalid'}]:
        assert c.req('PATCH','/api/v1/records/synthetic-1',c.payload(row,备注='bad'),headers=extra).status_code==403
    assert c.req('PATCH','/api/v1/records/synthetic-1',c.payload(row,备注='same origin'),headers={'Origin':'http://127.0.0.1:8173'}).status_code==200
    row=c.get()
    assert c.req('PATCH','/api/v1/records/synthetic-1',c.payload(row,备注='exact preview'),headers={'Origin':'http://localhost:9090'}).status_code==200
    remote=TestClient(c.client.app,base_url='http://127.0.0.1:8173',client=('192.0.2.9',4000))
    assert c.req('POST','/api/v1/records/approve',{'ids':[],'versions':{}},headers={'Origin':'http://localhost:9090'},client=remote).status_code==403
    remote.close()
    assert c.req('GET','/api/v1/records/synthetic-1/history').status_code==200
    assert c.req('GET','/api/v1/export.csv').status_code==200

before=manifest();dump(a.out/'source-before.json',before)
cases=[stale_save,stale_approve,lost_ack,reconcile_approve_reopen,mixed_batch,invalid_conditions,permissions,zero_and_compatibility,concurrent_instances]
if not a.baseline: cases.append(prefix_and_csrf)
results=[]
for case in cases:
    folder=a.out/case.__name__;folder.mkdir()
    with tempfile.TemporaryDirectory(prefix='wb-independent-') as tmp:
        c=Case(Path(tmp),PREFIX if case is prefix_and_csrf else '')
        try: case(c);result={'name':case.__name__,'passed':True}
        except Exception: result={'name':case.__name__,'passed':False,'traceback':traceback.format_exc()}
        dump(folder/'http.json',c.transcript)
        dump(folder/'state.json',{str(i):c.state(i) for i in range(1,4)})
        dump(folder/'vision.json',c.vision.calls)
        source=sqlite3.connect(Path(tmp)/'ledger.db');dest=sqlite3.connect(folder/'synthetic-final.db')
        source.backup(dest);dest.close();source.close();c.client.close()
        dump(folder/'result.json',result);results.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
after=manifest();dump(a.out/'source-after.json',after)
summary={'baseline':a.baseline,'explicit_conditions_in_all_protection_cases':True,
         'baseline_version_fallback':'actual isolated store version because public GET lacks version' if a.baseline else None,
         'passed':sum(r['passed'] for r in results),'total':len(results),'source_unchanged':before==after,'results':results}
dump(a.out/'summary.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) and before==after else 1)
