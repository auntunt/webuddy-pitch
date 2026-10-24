#!/usr/bin/env python3
"""Explicit Linux canary probe; no provider calls or production service changes.

Uses a shared existing test UID, not a provisioned production trial identity.
Requires noninteractive sudo and the two frozen, existing supervisor modules.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import uuid

PROTECTED = {
    'supervised_process.py': '51f60191cd8380517c0398f061fec299446abd772812e4827c327794690d3b12',
    'process_control.py': '44b692746a94b0a3540d021ce72898e56f774fee8dd1df0ac54dc99394830be3',
}

WORKER = r'''
import os,json,socket
from pathlib import Path
result={}
result['different_uid']=os.getuid()==65534 and os.getuid()!=int(__import__('sys').argv[1])
result['public_input_readable']=Path('/input/task.txt').read_text()=='PUBLIC-FIXTURE-INPUT'
try:Path('/sealed/oracle.txt').read_bytes();result['oracle_read_denied']=False
except PermissionError:result['oracle_read_denied']=True
except OSError:result['oracle_read_denied']=False
result['host_root_unmapped']=not Path('/opt/webuddy').exists() and not Path('/home').exists() and not Path('/root').exists()
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
result['capabilities_dropped']=all(int(status.get(k,'1').strip(),16)==0 for k in ('CapEff','CapPrm','CapBnd','CapAmb'))
result['no_new_privileges']=status.get('NoNewPrivs','').strip()=='1'
try:os.setuid(0);result['cannot_regain_root']=False
except PermissionError:result['cannot_regain_root']=True
result['host_parent_proc_hidden']=not Path('/proc/'+__import__('sys').argv[2]+'/cmdline').exists()
try:Path('/proc/1/environ').read_bytes();result['parent_environment_denied']=False
except PermissionError:result['parent_environment_denied']=True
except OSError:result['parent_environment_denied']=False
result['environment_sanitized']=set(os.environ)<={'PATH','LANG','LC_CTYPE'}
result['cwd_inside_root']=os.getcwd()=='/'
mounts={line.split()[4]:set(line.split()[5].split(',')) for line in Path('/proc/self/mountinfo').read_text().splitlines()}
result['system_mounts_readonly']=all('ro' in mounts.get(p,set()) for p in ('/usr','/lib','/lib64'))
result['proc_mount_readonly']='ro' in mounts.get('/proc',set())
targets=[]
for name in os.listdir('/proc/self/fd'):
 try:targets.append(os.readlink('/proc/self/fd/'+name))
 except FileNotFoundError:pass
result['no_inherited_directory_fds']=all(not p.startswith('/') or p=='/dev/null' for p in targets)
s=socket.socket();s.settimeout(.2)
try:s.connect(('1.1.1.1',443));result['network_unreachable']=False
except OSError:result['network_unreachable']=True
finally:s.close()
Path('/work/probe-write').write_text('FIXTURE-WRITE')
result['work_directory_writable']=Path('/work/probe-write').read_text()=='FIXTURE-WRITE'
print(json.dumps(result,sort_keys=True),flush=True)
'''

SETUP = r'''
import os,sys,subprocess,json
from pathlib import Path
root=Path(sys.argv[1]);owner=sys.argv[2];outside=sys.argv[3];worker=sys.argv[4]
def call(a):subprocess.run(a,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
for source,name in [('/usr','usr'),('/lib','lib'),('/lib64','lib64')]:
 if Path(source).exists():
  target=root/name;target.mkdir(exist_ok=True)
  call(['/usr/bin/mount','--bind',source,str(target)])
  call(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(target)])
proc=root/'proc';proc.mkdir(exist_ok=True)
call(['/usr/bin/mount','-t','proc','-o','ro,nosuid,nodev,noexec','proc',str(proc)])
os.chown(root/'work',65534,65534)
command=['/usr/sbin/chroot',str(root),'/usr/bin/env','-i','PATH=/usr/bin:/bin','LANG=C.UTF-8','/usr/bin/setpriv','--reuid=65534','--regid=65534','--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','/usr/bin/python3','-I','-c',worker,owner,outside]
p=subprocess.Popen(command,stdin=subprocess.DEVNULL)
raise SystemExit(p.wait())
'''

ROOT_ENTRY = r'''
import os,sys,json,hashlib,importlib.util
from pathlib import Path
sys.dont_write_bytecode=True;os.umask(0o077)
request=json.load(sys.stdin);root=Path(request['root']);app=Path(request['app'])
if root.is_symlink() or root.parent!=Path('/tmp') or not root.name.startswith('webuddy-holdout-probe-') or root.stat().st_uid!=int(os.environ['SUDO_UID']) or request['owner_uid']!=int(os.environ['SUDO_UID']) or request['owner_gid']!=int(os.environ['SUDO_GID']):raise ValueError('invalid owned fixture root')
if not app.is_absolute() or app.resolve()!=app or not str(app).startswith('/opt/webuddy/releases/'):raise ValueError('fixed release required')
for name,expected in request['protected'].items():
 p=app/'tmh/platform'/name
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('supervisor source mismatch')
sys.path.insert(0,str(app/'tmh/platform'))
spec=importlib.util.spec_from_file_location('probe_supervised',app/'tmh/platform/supervised_process.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
owner={'token':request['nonce'],'run_id':1,'data_dir':str(root)}
command=['/usr/bin/unshare','--mount','--pid','--fork','--net','--propagation','private','--','/usr/bin/python3','-I','-c',request['setup'],str(root),str(request['owner_uid']),str(os.getpid()),request['worker']]
try:
 result=module.run_supervised(command,folder=root/'supervised',owner=owner,cwd=root,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},timeout=20)
 raw=result.output_bytes;oracle=(root/'sealed/oracle.txt').read_bytes()
 try:checks=json.loads(raw)
 except (ValueError,UnicodeError):checks={}
 expected={'different_uid','public_input_readable','oracle_read_denied','host_root_unmapped','capabilities_dropped','no_new_privileges','cannot_regain_root','host_parent_proc_hidden','parent_environment_denied','environment_sanitized','cwd_inside_root','system_mounts_readonly','proc_mount_readonly','no_inherited_directory_fds','network_unreachable','work_directory_writable'}
 passed=result.returncode==0 and result.cleanup.get('complete') is True and set(checks)==expected and all(type(v) is bool and v for v in checks.values()) and oracle not in raw
 report={'probe_passed':passed,'returncode':result.returncode,'reason':result.reason,'cleanup':result.cleanup,'checks':checks,'output_sha256':hashlib.sha256(raw).hexdigest(),'oracle_in_output':oracle in raw,'fixture_root':str(root),'test_uid':65534,'owner_uid':request['owner_uid'],'dedicated_trial_identity':False,'production_qualified':False,'provider_calls':0}
 (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2),flush=True)
finally:
 # Bind mounts existed only in the exited private namespace. Never traverse them there.
 for parent,dirs,files in os.walk(root):
  os.chown(parent,request['owner_uid'],request['owner_gid'])
  for name in files:os.chown(Path(parent)/name,request['owner_uid'],request['owner_gid'])
 root.chmod(0o700)
'''



CHECKS = {'different_uid','public_input_readable','oracle_read_denied','host_root_unmapped','capabilities_dropped','no_new_privileges','cannot_regain_root','host_parent_proc_hidden','parent_environment_denied','environment_sanitized','cwd_inside_root','system_mounts_readonly','proc_mount_readonly','no_inherited_directory_fds','network_unreachable','work_directory_writable'}


def classify(report, root, owner_uid):
    # Structural consistency is not independent verification of a supplied report.
    if not isinstance(report, dict) or report.get('fixture_root') != str(root) or report.get('owner_uid') != owner_uid or report.get('test_uid') != 65534:
        raise ValueError('probe fixture/identity mismatch')
    if report.get('production_qualified') is not False or report.get('dedicated_trial_identity') is not False or type(report.get('provider_calls')) is not int or report['provider_calls'] != 0:
        raise ValueError('probe cannot qualify production or provider evidence')
    if type(report.get('probe_passed')) is not bool:
        raise ValueError('explicit probe outcome required')
    if report['probe_passed']:
        cleanup, checks = report.get('cleanup'), report.get('checks')
        if (type(report.get('returncode')) is not int or report['returncode'] != 0 or report.get('reason') != 'exited'
                or not isinstance(cleanup,dict) or any(cleanup.get(k) is not True for k in ('complete','reaped','output_complete'))
                or cleanup.get('remaining_group') is not False or cleanup.get('errors') != []
                or not isinstance(checks,dict) or set(checks) != CHECKS or any(v is not True for v in checks.values())
                or report.get('oracle_in_output') is not False):
            raise ValueError('contradictory or incomplete passing probe')
    return dict(report,status='passed' if report['probe_passed'] else 'failed')


def run(app):
    if platform.system() != 'Linux' or os.getuid() == 0:
        return {'status': 'unsupported', 'reason': 'Linux non-root caller with sudo required', 'production_qualified': False, 'provider_calls': 0}
    import pwd
    nobody = pwd.getpwnam('nobody')
    if (nobody.pw_uid, nobody.pw_gid) != (65534,65534):
        raise ValueError('fixed test UID unavailable')
    root = Path(tempfile.mkdtemp(prefix='webuddy-holdout-probe-',dir='/tmp'))
    root.chmod(0o755)
    for name,mode in [('input',0o755),('sealed',0o700),('work',0o700)]:
        (root/name).mkdir(mode=mode)
    (root/'input/task.txt').write_text('PUBLIC-FIXTURE-INPUT');(root/'input/task.txt').chmod(0o444)
    oracle=uuid.uuid4().hex+uuid.uuid4().hex
    (root/'sealed/oracle.txt').write_text(oracle);(root/'sealed/oracle.txt').chmod(0o600)
    assert (root/'sealed/oracle.txt').read_text()==oracle
    request={'root':str(root),'app':str(app.resolve()),'owner_uid':os.getuid(),'owner_gid':os.getgid(),'nonce':uuid.uuid4().hex,'protected':PROTECTED,'setup':SETUP,'worker':WORKER}
    # Root supervisor owns root and dropped-UID descendants. An unprivileged
    # supervisor could not reliably terminate the privileged namespace setup.
    p=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','-I','-c',ROOT_ENTRY],input=json.dumps(request).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (root/'root-wrapper.stderr').write_bytes(p.stderr)
    if p.returncode:
        return {'status':'failed','root_wrapper_exit':p.returncode,'fixture_root':str(root),'production_qualified':False,'provider_calls':0}
    report=json.loads(p.stdout)
    return classify(report,root,os.getuid())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Explicitly run only this fixed canary on Linux')
    parser.add_argument('--app',type=Path,default=Path('/opt/webuddy/app'))
    args=parser.parse_args()
    if not args.run:parser.error('--run is required; no implicit privileged execution')
    report=run(args.app)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status']=='passed' else 77 if report['status']=='unsupported' else 1


if __name__=='__main__':raise SystemExit(main())
