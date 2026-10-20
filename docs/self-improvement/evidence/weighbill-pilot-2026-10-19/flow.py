from pathlib import Path
import json
import hashlib
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
CLONE=ROOT/'data/external-agents/weighbill-concurrency'

def call(name, args):
    proc=subprocess.run([sys.executable,'-m','tmh.workbench',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=65)
    previous=OUT/(name+'.json')
    if previous.exists() and previous.read_bytes()!=proc.stdout:
        index=len(list(OUT.glob(name+'.previous-*.json')))+1
        (OUT/(name+f'.previous-{index}.json')).write_bytes(previous.read_bytes())
    (OUT/(name+'.json')).write_bytes(proc.stdout)
    (OUT/(name+'.stderr.log')).write_bytes(proc.stderr)
    if proc.returncode:
        print(proc.stdout.decode());print(proc.stderr.decode());raise SystemExit(proc.returncode)
    return json.loads(proc.stdout)

step=sys.argv[1]
if step=='submit':
    task=call('ticket-package',['ticket','WBILL-1','--agent','codex-external'])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=CLONE).decode().strip()
    cfg=hashlib.sha256((OUT/'project-config.json').read_bytes()).hexdigest()[:8]
    value=call('candidate-submitted',['submit','WBILL-1','--agent','codex-external','--base','60d6422ee898959557fc529a8e0335524b5ee2c0',
        '--commit',commit,'--requirement-hash',task['requirement_hash'],'--criteria-file',str(OUT/'criteria.json'),
        '--summary','真实外部Codex实现条件编辑/审核与前缀支持；协调者提供隔离合成预览启动器并实测251通过11外部集成跳过。旧无版本API兼容边界明确；独立复核及浏览器验收继续。',
        '--request-id','weighbill-conditional-submit-'+commit[:12]+'-'+cfg])
else:
    submitted=json.loads((OUT/'candidate-submitted.json').read_text())
    cid=str(submitted['candidate_id'])
    if step=='verify':
        value=call('verification-started',['verify',cid,'--agent','codex-external','--request-id','weighbill-conditional-verify-'+cid+'-'+submitted['commit'][:12]])
    elif step=='preview':
        value=call('preview-started',['candidate-preview',cid,'--agent','codex-external','--request-id','weighbill-conditional-preview-'+cid+'-'+submitted['commit'][:12]])
    elif step=='read':
        value=call('candidate-current',['candidate',cid,'--agent','codex-coordinator'])
    else:raise SystemExit('unknown step')
print(json.dumps({k:value[k] for k in ['id','candidate_id','commit','started','run','operation','state','verification_passed','preview_ready','technical_acceptance','ready_for_human','human_accepted','missing','preview_url'] if k in value},ensure_ascii=False,indent=2))
