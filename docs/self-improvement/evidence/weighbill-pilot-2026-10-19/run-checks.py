from pathlib import Path
import dataclasses
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tmh.platform.process_control import run_process
OUT=Path(__file__).resolve().parent
CLONE=ROOT/'data/external-agents/weighbill-concurrency'
PYTHON='/Users/auntlee/workspace/weighbill-system/.venv/bin/python'
NODE='/Users/auntlee/.nvm/versions/node/v24.16.0/bin/node'
def snapshot():
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=CLONE).decode().split('\0')
    return {name:hashlib.sha256((CLONE/name).read_bytes()).hexdigest() for name in files if name and (CLONE/name).is_file()}
before=snapshot()
env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG') if k in os.environ}
env.update(WB_TEST_STACK='',PYTEST_ADDOPTS='',PYTHONDONTWRITEBYTECODE='1')
checks=[('full-pytest',[PYTHON,'-m','pytest','-q','-p','no:cacheprovider']),
        ('editor-node',[NODE,'tests/client_editor_state.cjs'])]
report=[]
for name,cmd in checks:
    result=run_process(cmd,cwd=str(CLONE),env=env,timeout=180)
    path=OUT/(name+'.log');path.write_bytes(result.output_bytes)
    record={k:v for k,v in dataclasses.asdict(result).items() if k not in ('output','output_bytes')}
    record.update(name=name,command=cmd,output_sha256=hashlib.sha256(result.output_bytes).hexdigest())
    report.append(record)
    print(name,result.returncode,result.reason)
    print(result.output[-2500:])
after=snapshot()
(OUT/'coordinator-checks.json').write_text(json.dumps({'checks':report,'before':before,'after':after,'source_unchanged':before==after},ensure_ascii=False,indent=2)+'\n')
sys.exit(0 if before==after and all(r['returncode']==0 and r['cleanup']['complete'] for r in report) else 1)
