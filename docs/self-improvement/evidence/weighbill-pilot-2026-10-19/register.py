from pathlib import Path
import json
import shlex
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CLONE = ROOT/'data/external-agents/weighbill-concurrency'
PYTHON = '/Users/auntlee/workspace/weighbill-system/.venv/bin/python'
base = 'env -i PATH=/usr/bin:/bin:/opt/homebrew/bin HOME=/Users/auntlee TMPDIR=/tmp LANG=en_US.UTF-8 PYTHONDONTWRITEBYTECODE=1 WB_TEST_STACK= PYTEST_ADDOPTS= ' + shlex.quote(PYTHON)
config = {'version':1, 'project':{'name':'磅单系统：协作编辑试点', 'description':'独立Coding真实历史业务接入；隔离数据，本地验证'},
          'commands':{'build':base+' -m compileall -q weighbill', 'test':base+' -m pytest -q -p no:cacheprovider', 'extra_checks':[]}}
(CLONE/'.tmh').mkdir(exist_ok=True)
(CLONE/'.tmh/config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
(OUT/'project-config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
payload={'key':'WBILL','name':'磅单系统 · 协作编辑','root':str(CLONE),'description':'历史真实需求试点：条件编辑/审核，独立SQLite预览；不改原仓库，不接生产OCR。'}
req=urllib.request.Request('http://127.0.0.1:8791/api/projects', data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8791','X-TMH':'1'},method='POST')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:8791/api/projects',timeout=15) as response:
    existing=json.load(response)
if any(project['key']=='WBILL' for project in existing):
    raise SystemExit('WBILL already exists; reconcile instead of creating again')
with opener.open(req,timeout=15) as res:
    body=res.read()
(OUT/'project-created.json').write_bytes(body)
print(body.decode())
