"""Personally authorized verification of a fixed candidate, without host execution.

Commands are operator-provided project settings. Baseline and candidate run in
separate rootless, network-disabled and hard-quota workspaces. The original
source files must remain unchanged, and all workspaces must be removed before
the ordinary verification operation can report a pass.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import threading
import time

from .. import config
from . import candidates, fixloop, project_snapshot, testbox
from .project_authority import capture
from .project_container import Engine, _path
from .project_volume import ProjectVolume
from .project_git import personal_scope
from .project_mcp import BoundJob
from .supervised_process import _atomic_json

MAX_OUTPUT = 2 * 1024 * 1024
MAX_SECONDS = 1200

# The reference is the host's screened snapshot, mounted read-only. Build
# products may be added in /workspace, but every original source file must
# retain the same type, bytes and executable bit after each command.
CHECK_SOURCE = r'''
import os,shutil,stat,subprocess,sys,tempfile
def fail(path,why):
 print(why+': '+path,file=sys.stderr);sys.exit(1)
for root,dirs,files in os.walk('/reference',followlinks=False):
 for name in dirs+files:
  source=os.path.join(root,name);rel=os.path.relpath(source,'/reference');target=os.path.join('/workspace',rel)
  a=os.lstat(source)
  try:b=os.lstat(target)
  except OSError:fail(rel,'原有源码缺失')
  if stat.S_ISDIR(a.st_mode):
   if not stat.S_ISDIR(b.st_mode):fail(rel,'原有目录类型变化')
  elif stat.S_ISREG(a.st_mode):
   if not stat.S_ISREG(b.st_mode) or bool(a.st_mode&0o111)!=bool(b.st_mode&0o111):fail(rel,'原有文件类型或权限变化')
   if a.st_size!=b.st_size:fail(rel,'原有文件大小变化')
   with open(source,'rb') as f,open(target,'rb') as g:
    while True:
     x=f.read(1048576);y=g.read(1048576)
     if x!=y:fail(rel,'原有文件内容变化')
     if not x:break
  else:fail(rel,'不支持的原有文件类型')
added=[]
for root,dirs,files in os.walk('/workspace',followlinks=False):
 for name in list(dirs):
  path=os.path.join(root,name)
  if os.path.islink(path):dirs.remove(name);files.append(name)
 for name in files:
  path=os.path.join(root,name);rel=os.path.relpath(path,'/workspace')
  if not os.path.lexists(os.path.join('/reference',rel)):
   if not stat.S_ISREG(os.lstat(path).st_mode):fail(rel,'新增文件类型不受支持')
   added.append(rel)
if added:
 # Build a fresh Git repository with only the original tracked .gitignore
 # files. Never use newly generated ignore rules, host config, or hooks.
 env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TEMPLATE_DIR='')
 with tempfile.TemporaryDirectory(dir='/tmp',prefix='webuddy-ignore-') as temp:
  base=['git','-c','core.hooksPath=/dev/null','-c','core.excludesFile=/dev/null','-C',temp]
  if subprocess.run(base+['init','-q'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:fail('', '无法核对原始忽略规则')
  for root,dirs,files in os.walk('/reference',followlinks=False):
   if '.gitignore' in files:
    source=os.path.join(root,'.gitignore');rel=os.path.relpath(source,'/reference')
    target=os.path.join(temp,rel);os.makedirs(os.path.dirname(target),exist_ok=True);shutil.copyfile(source,target)
  query=b''.join(os.fsencode(path)+b'\0' for path in added)
  result=subprocess.run(base+['check-ignore','--no-index','-z','--stdin'],input=query,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  if result.returncode not in (0,1):fail('', '无法核对原始忽略规则')
  ignored=set(result.stdout.split(b'\0'))
  for path in added:
   if os.fsencode(path) not in ignored:fail(path,'新增文件未被原始 Git 忽略规则覆盖')
'''


def commands(P, project):
    """Use explicit operator tests; never infer success from a missing test."""
    settings = fixloop.settings(P.data_dir)
    override = settings.get('check')
    if isinstance(override, dict):
        override = override.get(project['key'], override.get('*', ''))
    if override not in ('', None) or testbox.settings(P.data_dir):
        raise ValueError('此项目现有验证配置需要宿主机或外部测试机，暂不支持个人隔离验证')
    value = config.load(Path(project['root'])).get('commands')
    if not isinstance(value, dict):
        raise ValueError('项目验证命令配置无效')
    seq = []
    for kind in ('build', 'test'):
        cmd = value.get(kind, '')
        if not isinstance(cmd, str):
            raise ValueError('项目验证命令配置无效')
        if cmd.strip():
            seq.append((kind, cmd.strip()))
    extras = value.get('extra_checks') or []
    if not isinstance(extras, list) or any(not isinstance(cmd, str) or not cmd.strip() for cmd in extras):
        raise ValueError('项目附加检查配置无效')
    seq.extend(('check', cmd.strip()) for cmd in extras)
    if not all(any(kind == item for kind, _ in seq) for item in ('build', 'test')):
        raise ValueError('请管理员明确配置 build 和 test 命令；隔离验证不会静默跳过原有自动识别检查')
    if len(seq) > 16 or any(len(cmd) > 8192 or '\0' in cmd for _, cmd in seq):
        raise ValueError('项目验证命令超过隔离验证支持范围')
    timeout = settings.get('check_timeout') or MAX_SECONDS
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= MAX_SECONDS:
        raise ValueError('项目验证时限不受支持，请管理员设置 1 至 1200 秒')
    return seq, float(timeout)


def start(P, actor, cid):
    """Start one authenticated person's candidate verification in background.

    Caller handles normal action idempotency and holds the candidate guard.
    """
    row = candidates._row(P, cid)
    ticket = P.store.ticket(row['ticket_id'])
    project = P.store.project(ticket['project_id'])
    authority = capture(P, actor, project)
    with personal_scope(P, actor):
        view = candidates.view(P, cid)
    if not view['current']:
        raise ValueError('；'.join(view['blocked']))
    seq, timeout = commands(P, project)
    operation = P.flow.rechecks.start(row['run_id'], actor, budget=timeout)
    try:
        worker = threading.Thread(target=_run, args=(P, authority, row, project, seq, operation['id']), daemon=True)
        worker.start()
    except BaseException:
        P.flow.rechecks.finish(operation['id'], 125, '隔离验证未启动')
        raise
    return {'started': True, 'run': row['run_id'], 'operation': operation['id']}


def _run(P, authority, row, project, seq, opid):
    operations = P.flow.rechecks
    runner = operations.runner
    folder = operations.folder(opid)
    workspace = folder / 'candidate-workspace'
    job = BoundJob(authority.principal, project['key'], workspace, authority.image)
    root = Path(project['root'])
    run = P.store.run(row['run_id'])
    engine = Engine()
    result_code = 125
    result_message = '隔离验证未完成'
    finished = False

    def stopped():
        return bool(runner.stop_reason(opid)) or not authority.current(job)

    def current():
        if stopped():
            return False
        with personal_scope(P, authority.principal):
            state = candidates.view(P, row['id'])
        if not state['current'] or commands(P, project)[0] != seq:
            return False
        return (project_snapshot.current(authority.image, root, 'HEAD', row['base_commit'], cancel=stopped, engine=engine)
                and project_snapshot.current(authority.image, root, row['ref'], row['commit_sha'], cancel=stopped, engine=engine))

    def check_volume(reference, label):
        receipts = []
        limit = runner.remaining(opid)
        if limit <= 0 or stopped():
            raise ValueError('隔离验证已停止或超过总时限')
        with ProjectVolume(engine, authority.image, reference, limit, stopped) as volume:
            for index, (kind, command) in enumerate(seq, 1):
                if stopped() or not volume.alive():
                    raise ValueError('验证期间项目授权已撤销或临时工作区已停止')
                remaining = runner.remaining(opid)
                if remaining <= 0:
                    raise ValueError('验证总时限已到')
                output = bytearray()
                def collect(chunk):
                    if len(output) + len(chunk) > MAX_OUTPUT:
                        raise ValueError('验证输出超过上限')
                    output.extend(chunk)
                started = time.monotonic()
                receipt = engine.run(volume.spec(['/bin/sh','-c',command], remaining), remaining,
                                     cancel=lambda:stopped() or not volume.alive(), output=collect)
                output_path = folder / ('%s-command-%02d.bin' % (label,index))
                with output_path.open('xb') as raw:
                    raw.write(output)
                if receipt.get('cleanup') is not True:
                    raise ValueError('验证容器未确认回收，不能记录结果')
                if receipt.get('reason') != 'exited':
                    raise ValueError('验证执行未正常结束')
                text = output.decode('utf-8', 'replace')
                receipts.append({'kind':kind, 'command':command, 'exit_code':receipt['returncode'],
                                 'seconds':round(time.monotonic()-started, 1), 'output':text,
                                 'tail':'\n'.join(text.strip().splitlines()[-60:]), 'cleanup':True,
                                 'raw_output':str(output_path.relative_to(P.data_dir)),
                                 'raw_sha256':hashlib.sha256(output).hexdigest()})
                remaining = runner.remaining(opid)
                if remaining <= 0 or stopped() or not volume.alive():
                    raise ValueError('验证期间授权或临时工作区已失效')
                spec=volume.spec(['python3','-I','-c',CHECK_SOURCE],remaining)
                spec['HostConfig']['Mounts'].append({'Type':'bind','Source':_path(reference),
                                                   'Target':'/reference','ReadOnly':True})
                diagnostics=bytearray()
                def diagnostic(chunk):
                    if len(diagnostics)+len(chunk)>MAX_OUTPUT:
                        raise ValueError('源码核对输出超过上限')
                    diagnostics.extend(chunk)
                unchanged=engine.run(spec,remaining,cancel=lambda:stopped() or not volume.alive(),
                                     output=diagnostic,diagnostic=diagnostic)
                (folder/('%s-source-check-%02d.bin' % (label,index))).write_bytes(diagnostics)
                if unchanged.get('cleanup') is not True:
                    raise ValueError('源码一致性检查容器未确认回收')
                if unchanged.get('reason')!='exited' or unchanged.get('returncode')!=0:
                    raise ValueError('验证期间源码变化、出现未知产物或无法核对；不能报告通过：'+
                                     diagnostics.decode('utf-8','replace')[:500])
                if receipt['returncode'] != 0:
                    break
        # ProjectVolume.__exit__ must confirm anchor, volume and janitor cleanup.
        return receipts

    try:
        if not current():
            raise ValueError('验证开始前项目授权、工单或代码版本已变化')
        baseline = folder / 'baseline-workspace'
        baseline_snapshot = project_snapshot.create(authority.image, root, baseline, ref=row['base_commit'], cancel=stopped, engine=engine)
        if baseline_snapshot['commit'] != row['base_commit'] or not current():
            raise ValueError('基线快照与固定版本不一致')
        snapshot = project_snapshot.create(authority.image, root, workspace, ref=row['ref'], cancel=stopped, engine=engine)
        if snapshot['commit'] != row['commit_sha'] or not current():
            raise ValueError('候选快照与固定版本不一致')
        digest = hashlib.sha256(run['diff'].encode('utf-8')).hexdigest()
        operations.bind(opid, {'run':row['run_id'], 'decision':run['decision'], 'commit':row['commit_sha'],
                               'base':row['base_commit'], 'diff_sha256':digest})
        baseline_receipts = check_volume(baseline, 'baseline')
        baseline_ok = len(baseline_receipts)==len(seq) and all(item['exit_code']==0 for item in baseline_receipts)
        receipts = check_volume(workspace, 'candidate') if baseline_ok else []
        if not current():
            raise ValueError('验证结束前项目授权、需求或固定版本已变化')
        check = 'pass' if baseline_ok and len(receipts)==len(seq) and all(item['exit_code']==0 for item in receipts) else 'fail'
        previous = fixloop._verification(P.data_dir, row['run_id'])
        history = list(previous.pop('previous_verifications', []))
        if previous:
            history.append({'diff':run['diff'], 'verification':previous})
        verification = {'check':check, 'verdict':'unknown', 'commands':receipts, 'baseline_commands':baseline_receipts,
                        'baseline_passed':baseline_ok, 'checked_commit':row['commit_sha'],
                        'checked_base':row['base_commit'], 'checked_diff':run['diff'],
                        'recheck_operation':{'id':opid, 'source_run':row['run_id']}, 'verification_current':True,
                        'previous_verifications':history, 'isolation':'分离限额工作区，断网项目容器',
                        'source_archive_sha256':snapshot['archive_sha256'],
                        'baseline_archive_sha256':baseline_snapshot['archive_sha256']}
        result_code = 0 if check == 'pass' else 1
        result_message = ('隔离构建测试通过' if result_code == 0 else
                          '基线构建测试未通过' if not baseline_ok else '候选构建测试未通过')
        # Recheck once under the personal authority and candidate locks before
        # publishing identical evidence in both existing verification locations.
        with P.tenant_context.registry.authorization_guard(), candidates.guard(P, row['ticket_id']):
            if not current():
                raise ValueError('写入验证回执前项目授权、需求或版本已变化')
            _atomic_json(folder/'verification.json', verification)
            target = Path(P.data_dir)/'runs'/str(row['run_id'])/'verify.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_json(target, verification)
            operations.finish(opid, result_code, result_message)
            finished = True
    except Exception as exc:
        result_code = 125
        result_message = '隔离验证未完成：' + str(exc)
    finally:
        if not finished:
            operations.finish(opid, result_code, result_message)
