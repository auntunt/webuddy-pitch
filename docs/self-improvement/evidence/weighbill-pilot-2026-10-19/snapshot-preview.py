from pathlib import Path
import http.client
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
state=json.loads((ROOT/'data/product-workbench/previews/state.json').read_text())['WBILL-1']
def get(path):
    c=http.client.HTTPConnection('127.0.0.1',state['port'],timeout=10)
    try:
        c.request('GET',state['prefix']+path)
        r=c.getresponse();raw=r.read()
        if r.status!=200:raise ValueError((path,r.status,raw))
        return json.loads(raw)
    finally:c.close()
records=get('/api/v1/records?stage=&voided=all')['records']
data={'commit':state['commit_full'],'port':state['port'],'prefix':state['prefix'],'records':records,
      'history':{r['id']:get('/api/v1/records/'+r['id']+'/history')['history'] for r in records}, 'health':get('/api/v1/health')}
(OUT/('preview-'+sys.argv[1]+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({r['id']:{'version':r['version'],'stage':r['stage'],'goods':r['fields']['货名'],'net':r['fields']['净重'],'history':len(data['history'][r['id']])} for r in records},ensure_ascii=False))
