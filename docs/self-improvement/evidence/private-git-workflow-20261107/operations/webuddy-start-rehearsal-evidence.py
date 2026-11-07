import os,time,sys
from pathlib import Path
root=Path('/Users/auntlee/Desktop/workspace/运维智能体/部署包/jenkins-erp-demo-20261106')
for _ in range(100):
 if all((root/'proof/git-workflow-20261107'/(v+'-build.json')).exists() for v in ('baseline','candidate')):break
 time.sleep(15)
else:raise TimeoutError('builds not collected')
repo=Path.cwd();py='/private/tmp/webuddy-developer-mcp-venv/bin/python'
os.execve(py,[py,str(repo/'examples/project-testing/jsherp/jenkins-demo/evidence_server.py'),str(root),'--exercise','git-workflow-20261107','--port','18986'],dict(os.environ,PYTHONPATH=str(repo)))
