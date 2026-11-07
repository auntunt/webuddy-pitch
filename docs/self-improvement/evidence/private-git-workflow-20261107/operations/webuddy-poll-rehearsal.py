import subprocess,json,time
from pathlib import Path
root=Path('/Users/auntlee/Desktop/workspace/运维智能体/部署包/jenkins-erp-demo-20261106')
cmd=['python','examples/project-testing/jsherp/jenkins-demo/rehearse.py','--root',str(root),'--exercise','git-workflow-20261107']
for i in range(80):
 for version in ('baseline','candidate'):
  if not (root/'proof/git-workflow-20261107'/(version+'-build.json')).exists():
   p=subprocess.run(cmd+['--version',version,'collect'],capture_output=True,text=True)
   print(json.dumps({'time':time.time(),'version':version,'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}),flush=True)
   if p.returncode:raise SystemExit(p.returncode)
 if all((root/'proof/git-workflow-20261107'/(v+'-build.json')).exists() for v in ('baseline','candidate')):break
 time.sleep(30)
else:raise TimeoutError('Jenkins still pending')
