from pathlib import Path
import json,subprocess
r=json.loads(Path('/private/tmp/knowledge-gate-passed.json').read_text())
assert r['commit']=='e96151541794e31b462a86581853b2ae71a2fa60' and r['run']==42282872142 and len(r['required'])==10
cmd="test \"$(readlink /opt/webuddy/app)\" = /opt/webuddy/releases/638c256/app && sudo -n bash /tmp/knowledge-activate.sh && sudo -n python3 /tmp/knowledge-health.py"
subprocess.run(['ssh','-i','/Users/auntlee/Downloads/cc-deploy-20260923','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','ubuntu@43.153.76.85',cmd],check=True)
