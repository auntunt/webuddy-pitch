import subprocess
names = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
for name in ('webuddy-erp-build-verified', 'webuddy-erp-app'):
    if name in names:
        subprocess.run(['docker', 'stop', name], check=True)
