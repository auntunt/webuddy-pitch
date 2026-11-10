"""Prepare local source and build prerequisites before development starts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from . import filelock
from .store import now

EXCLUDES = ['.tmh/', '.env', '.env.*', '!.env.example', '!.env.sample', '.venv/', 'venv/',
            'node_modules/', 'target/', 'build/', 'dist/', '__pycache__/', '*.pyc', '*.log',
            '*.pem', '*.key', '*.p12', '*.pfx', '*.jks', '.ssh/', '.aws/', '.cursor/',
            '.idea/', '/*.db', '/*.sqlite', '/*.sqlite3']


def stage(runner, rid, name, state='running', detail=''):
    path = runner.data_dir / 'runs' / str(rid) / 'preparation.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'steps': []}
    entry = next((s for s in data['steps'] if s['name'] == name), None)
    if entry is None:
        entry = {'name': name}
        data['steps'].append(entry)
    entry.update(state=state, detail=detail, updated=now())
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
    runner.store.append_output(rid, '\n— %s：%s%s\n' % (name, state, (' · ' + detail) if detail else ''))


def environment(data_dir, rid, inherited=None):
    env = dict(os.environ if inherited is None else inherited)
    path = Path(data_dir) / 'runs' / str(rid) / 'environment.json'
    if not path.exists():
        return env
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    paths = value.get('path', [])
    if not isinstance(paths, list) or any(not isinstance(p, str) or not Path(p).is_absolute() or not Path(p).is_dir() for p in paths):
        raise ValueError('环境准备返回的工具目录无效')
    env['PATH'] = os.pathsep.join(paths + [env.get('PATH', '')])
    if value.get('java_home'):
        home = Path(value['java_home'])
        if not home.is_absolute() or not (home / 'bin').is_dir():
            raise ValueError('环境准备返回的 JAVA_HOME 无效')
        env['JAVA_HOME'] = str(home)
    return env


def sensitive(name, data):
    return bool(re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----', data)
                or re.search(rb'AKIA[0-9A-Z]{16}', data)
                or re.search(rb'(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)["\s]*[=:][\s"\x27]*[A-Za-z0-9_+/=-]{20,}', data))


def baseline(root, *, env=None, cancelled=lambda: False):
    """Create a local first commit, leaving existing history and source bytes alone."""
    root = Path(root).resolve()
    def git(*args, check=True, input=None, git_env=None):
        if cancelled():
            raise RuntimeError('准备已停止')
        result = subprocess.run(['git', '-C', str(root), *args], env=git_env or env,
                                input=input, capture_output=True, timeout=120)
        if check and result.returncode:
            raise RuntimeError('Git 准备失败：' + result.stderr.decode('utf-8', 'replace'))
        return result
    top = git('rev-parse', '--show-toplevel', check=False)
    if top.returncode == 0 and Path(top.stdout.decode().strip()).resolve() != root:
        raise ValueError('项目目录属于上级 Git 仓库，请使用该仓库根目录，避免建立错误基线')
    git('init', '-q')
    gitdir = Path(git('rev-parse', '--absolute-git-dir').stdout.decode().strip())
    with (gitdir / 'webuddy-prepare.lock').open('a+b') as lock:
        filelock.try_lock(lock, blocking=True)
        head = git('rev-parse', '--verify', 'HEAD', check=False)
        if head.returncode == 0:
            return {'commit': head.stdout.decode().strip(), 'created': False, 'excluded': []}
        exclude = gitdir / 'info' / 'exclude'
        exclude.parent.mkdir(exist_ok=True)
        old = exclude.read_text(encoding='utf-8') if exclude.exists() else ''
        with exclude.open('a', encoding='utf-8') as f:
            f.write('\n# Webuddy local runtime and credentials\n' + '\n'.join(EXCLUDES) + '\n')
        index = gitdir / 'index'
        original_index = index.read_bytes() if index.exists() else None
        omitted = []
        try:
            with tempfile.TemporaryDirectory(prefix='webuddy-index-') as temp:
                selected = Path(temp) / 'index'
                local = dict(env or os.environ, GIT_INDEX_FILE=str(selected),
                             GIT_AUTHOR_NAME='Webuddy', GIT_AUTHOR_EMAIL='webuddy@localhost',
                             GIT_COMMITTER_NAME='Webuddy', GIT_COMMITTER_EMAIL='webuddy@localhost')
                # Enumerate working files using the project's ignore rules; never stage secrets.
                names = git('ls-files', '--cached', '--others', '--exclude-standard', '-z').stdout.split(b'\0')
                ignored_names = set(git('check-ignore', '--no-index', '--stdin', '-z', input=b'\0'.join(n for n in names if n)+b'\0', check=False).stdout.split(b'\0'))
                included = []
                for raw in dict.fromkeys(names):
                    if not raw:
                        continue
                    name = os.fsdecode(raw)
                    file = root / name
                    if file.is_symlink() or not file.is_file():
                        omitted.append(name)
                        continue
                    # Tracked entries in an unborn index must obey the same exclusion policy.
                    ignored = raw in ignored_names
                    if ignored or sensitive(name, file.read_bytes()):
                        omitted.append(name)
                        continue
                    included.append(raw)
                if not included:
                    raise ValueError('尚未找到可建立基线的源码；请在任务中提供源码仓库地址')
                git('add', '--pathspec-from-file=-', '--pathspec-file-nul', input=b'\0'.join(included)+b'\0', git_env=local)
                tree = git('write-tree', git_env=local).stdout.decode().strip()
                commit = git('commit-tree', tree, '-m', 'Local source baseline prepared by Webuddy', git_env=local).stdout.decode().strip()
                git('update-ref', 'HEAD', commit, '0' * len(commit))
                if original_index is not None:
                    (gitdir / 'index.before-webuddy-baseline').write_bytes(original_index)
                shutil.copyfile(selected, index)
                if omitted:
                    # Keep omitted local files untracked in later worktrees and commits.
                    with exclude.open('a', encoding='utf-8') as f:
                        for name in omitted:
                            f.write('/' + re.sub(r'([*?\[\]\\#! ])', r'\\\1', name) + '\n')
                return {'commit': commit, 'created': True, 'excluded': omitted}
        except Exception:
            if git('rev-parse', '--verify', 'HEAD', check=False).returncode != 0:
                exclude.write_text(old, encoding='utf-8')
            raise


def prepare(runner, rid, project, ticket, agent, conf, model, *, workdir=None, source=False):
    root = Path(project['root'])
    directory = Path(workdir) if workdir else root
    directory.mkdir(parents=True, exist_ok=True)
    label = '准备源码与 Git 基线' if source else '准备构建环境'
    stage(runner, rid, label)
    receipt = runner.data_dir / 'runs' / str(rid) / 'environment.json'
    tools = runner.data_dir / 'tools'
    context = (ticket or {}).get('body', '')
    comments = [e['body'] for e in runner.store.events(ticket['id']) if e['kind'] == 'comment'] if ticket else []
    task = ('仅在目录没有源码时，根据下面用户明确提供的仓库地址获取源码到此目录；已有源码必须保留。'
            'Git缺失时自动安装便携Git并登记工具目录。不要自行git init或提交，平台会建立本地Git基线。没有地址且没有源码时说明缺少源码地址。'
            if source else
            '读取项目README及构建文件，自动准备运行本次构建所需的依赖和工具。优先项目wrapper、锁文件及已有工具。'
            '缺少JDK、Maven、Node、Python等时，从官方来源安装便携版本到给定工具目录，不要求用户手工安装。'
            '执行版本命令和最小依赖检查；不要启动完整应用或执行全量测试。')
    prompt = (f'你负责已授权开发任务的自动准备。工作目录：{directory}\n工具安装目录：{tools}\n{task}\n'
              '允许下载依赖和运行命令；不改变代理、不注销账号、不修改系统全局配置、不提权。'
              '不要改业务源码，不读取或输出密钥，不推送、不部署、不代人验收。'
              f'如安装了工具，将工具bin绝对目录写入 {receipt}，格式 '
              '{"path":["绝对bin目录"],"java_home":"JDK绝对目录（无需时省略）"}。保留已有有效路径。'
              '报告实际执行结果和真实阻塞，不用一句“完成”替代检查。\n用户任务：\n' + context + '\n用户补充：\n' + '\n'.join(comments))
    try:
        # Existing source plus installed Git needs no model call before the baseline.
        has_source = any(p.name not in ('.tmh', '.git', '.cursor') for p in directory.iterdir())
        if not source or not has_source or not shutil.which('git', path=environment(runner.data_dir, rid).get('PATH')):
            for attempt in range(2):
                code, result = runner.invoke(rid, project, ticket, agent, conf, 'prepare', prompt,
                                             directory, model, tag=('-source' if source else '-environment') + str(attempt))
                if runner.stop_reason(rid):
                    raise RuntimeError(runner.stop_message(rid))
                missing = [] if source else runtime_errors(runner, rid, directory)
                if code == 0 and not missing:
                    break
                if attempt == 1:
                    raise RuntimeError('准备尚未完成：' + ('；'.join(missing) or result))
                prompt += '\n上次实际检查失败，请修复后再检查：\n' + ('；'.join(missing) or result)

        if source:
            result = baseline(root, env=environment(runner.data_dir, rid), cancelled=lambda: bool(runner.stop_reason(rid)))
            (receipt.parent / 'baseline.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            detail = ('已建立本地基线' if result['created'] else '沿用已有 Git 历史') + ' · ' + result['commit'][:10]
            if result['excluded']:
                detail += '；凭据或本地文件保留在原目录，未纳入提交'
        else:
            environment(runner.data_dir, rid)
            if receipt.exists():
                cached = runner.data_dir / 'project-environments' / (str(project['id']) + '.json')
                cached.parent.mkdir(parents=True, exist_ok=True)
                temporary = cached.with_suffix('.%s.tmp' % rid)
                temporary.write_bytes(receipt.read_bytes())
                temporary.replace(cached)
            detail = '准备完成，继续执行实际构建检查'
        stage(runner, rid, label, 'done', detail)
    except Exception as exc:
        stage(runner, rid, label, 'cancelled' if runner.stop_reason(rid) else 'failed', str(exc))
        raise


def view(data_dir, run):
    folder = Path(data_dir) / 'runs' / str(run['id'])
    result = {}
    for key, name in [('preparation', 'preparation.json'), ('continuation', 'continuation.json')]:
        path = folder / name
        if path.exists():
            result[key] = json.loads(path.read_text(encoding='utf-8'))
    if run['status'] in ('failed', 'cancelled'):
        for step in result.get('preparation', {}).get('steps', []):
            if step['state'] == 'running':
                step.update(state=run['status'], detail=run.get('result') or '查看执行日志')
    return result


def runtime_errors(runner, rid, directory):
    """Check the executables the existing build detector will actually invoke."""
    from ..verify import detect_commands
    import shlex
    env = environment(runner.data_dir, rid)
    folders = [directory] + sorted(p for p in directory.iterdir() if p.is_dir() and not p.name.startswith('.'))
    chosen = next(((p, detect_commands(p)) for p in folders if any(detect_commands(p).values())), None)
    if chosen is None:
        return []
    folder, commands = chosen
    required = {shlex.split(c, posix=os.name != 'nt')[0].strip('"') for c in commands.values() if c}
    if (folder / 'pom.xml').exists() or any(folder.glob('*gradle*')):
        required.add('java')
    errors = []
    for tool in sorted(required):
        local = folder / tool
        executable = str(local.resolve()) if local.is_file() else shutil.which(tool, path=env['PATH'])
        if not executable:
            errors.append('缺少构建工具：' + tool)
            continue
        # Wrapper versions may download their pinned distributions; real execution is recorded.
        argv = [executable, '-version' if tool == 'java' else '--version']
        if os.name == 'nt' and executable.lower().endswith(('.cmd', '.bat')):
            argv = ['cmd.exe', '/d', '/c'] + argv
        process, _ = runner.run_command(rid, argv, folder, env=env, timeout=120, kind='environment-check')
        if process.returncode:
            errors.append(tool + ' 版本检查失败：' + process.output)
    return errors


def inherit_environment(data_dir, rid, project):
    receipt = Path(data_dir) / 'runs' / str(rid) / 'environment.json'
    cached = Path(data_dir) / 'project-environments' / (str(project['id']) + '.json')
    if receipt.exists() or not cached.exists():
        return
    value = json.loads(cached.read_text(encoding='utf-8-sig'))
    paths = value.get('path', [])
    # A removed portable installation is prepared again, never injected into PATH.
    if not isinstance(paths, list) or any(not isinstance(p, str) or not Path(p).is_absolute() or not Path(p).is_dir() for p in paths):
        return
    if value.get('java_home') and not (Path(value['java_home']) / 'bin').is_dir():
        return
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_bytes(cached.read_bytes())
