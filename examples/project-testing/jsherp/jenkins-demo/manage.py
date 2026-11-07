"""Operate only the already provisioned, named local demonstration containers."""
import argparse
import json
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['status', 'start', 'stop'])
args = parser.parse_args()
names = ['webuddy-demo-git', 'webuddy-demo-mysql', 'webuddy-demo-redis',
         'webuddy-demo-jenkins', 'webuddy-demo-jenkins-tls']
for name in names:
    subprocess.run(['docker', 'inspect', name], check=True, stdout=subprocess.DEVNULL)
if args.action != 'status':
    for name in names if args.action == 'start' else reversed(names):
        subprocess.run(['docker', args.action, name], check=True)
for name in names:
    value = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
    print(json.dumps({'name': name, 'running': value['State']['Running'],
                      'status': value['State']['Status'], 'image': value['Config']['Image']}, ensure_ascii=False))
