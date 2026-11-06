import json,subprocess,time
from pathlib import Path
expected='e96151541794e31b462a86581853b2ae71a2fa60'
required={f'fast gate ({os} / py{v})' for os in ('ubuntu-latest','windows-latest') for v in ('3.11','3.13')}
required|={f'installed distribution ({os} / py3.12)' for os in ('ubuntu-latest','windows-latest')}
required|={f'Windows execution and evidence (py{v})' for v in ('3.11','3.13')}
required|={f'full suite (ubuntu-latest / py{v})' for v in ('3.11','3.13')}
for _ in range(40):
 r=json.loads(subprocess.check_output(['gh','run','view','42282872142','--json','headSha,status,conclusion,jobs']))
 assert r['headSha']==expected
 jobs={j['name']:j for j in r['jobs']}
 assert required<=jobs.keys()
 failed=[n for n in required if jobs[n]['status']=='completed' and jobs[n]['conclusion']!='success']
 if failed:raise RuntimeError(failed)
 remaining=[n for n in required if jobs[n]['status']!='completed']
 print('remaining',remaining,flush=True)
 if not remaining:
  Path('docs/self-improvement/evidence/knowledge-collaboration-20261107/ci.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
  Path('/private/tmp/knowledge-gate-passed.json').write_text(json.dumps({'commit':expected,'run':42282872142,'required':sorted(required)}))
  print('EXACT_COMMIT_REQUIRED_CI_PASSED',flush=True);break
 time.sleep(30)
else:raise TimeoutError('CI still pending')
