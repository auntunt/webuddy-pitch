"""Read-only developer-machine checks; never fetch, checkout, clean or run models."""
import os
from pathlib import Path
import re
import subprocess
from .workbench_client import ClientError


def repository_identity(url):
    # Reuse the registered repository formats; never return credentials in URLs.
    from .platform.repo_sync import parse
    try:
        value = parse(url)
    except ValueError:
        return None
    if value.get('kind') == 'ssh':
        return (value['host'], value['port'], value['user'], value['path'])
    return (value['host'], value['owner'].lower(), value['repo'].lower())


def inspect(client, ticket, directory):
    if not isinstance(directory, str) or not Path(directory).is_absolute():
        raise ClientError('请传入当前开发目录的绝对路径；不能猜测编辑器目录', 'directory_required')
    # Read through the authenticated gateway before touching local Git.
    state = client.call('development_get', {'ticket': ticket})
    choice = state.get('execution') or {}
    result = {'ticket': ticket, 'directory': str(Path(directory).resolve()), 'ready': False,
              'checks': {}, 'issues': [], 'execution': choice, 'changes': [],
              'notice': '仅核对当前快照，不修改文件、不拉取代码；不是测试通过或人工验收。'}
    issues, checks = result['issues'], result['checks']
    if state.get('state') != 'confirmed' or not choice.get('current') or choice.get('mode') != 'local':
        issues.append('请负责人先确认当前方案并明确选择本地执行')
        return result
    library = client.call('library_get', {'project': choice['project']})
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    # Git environment inherited from an editor must not redirect this check.
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(key, None)
    def git(*args):
        try:
            value = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', directory, *args],
                                   env=env, capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClientError('本地Git检查未完成，请核对目录、Git安装和进程状态', 'git_unavailable') from exc
        if value.returncode:
            raise ClientError('本地Git检查失败；不会把未知结果视为一致', 'git_check_failed')
        return value.stdout.decode('utf-8', errors='surrogateescape').rstrip('\r\n')
    root = git('rev-parse', '--show-toplevel')
    result['git_root'] = root
    result['git_dir'] = git('rev-parse', '--absolute-git-dir')
    result['branch'] = git('rev-parse', '--abbrev-ref', 'HEAD')
    head = git('rev-parse', '--verify', 'HEAD^{commit}')
    result['head'] = head
    base = choice.get('base_commit', '')
    checks['baseline'] = 'match' if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', base) and head == base else 'mismatch'
    if checks['baseline'] != 'match':
        issues.append('当前HEAD与任务固定起点不同；先核对分支/已完成改动，不自动切换或重置')
    expected = repository_identity(choice.get('repository', ''))
    matches = []
    for name in git('remote').splitlines():
        url = git('remote', 'get-url', name)
        if expected and repository_identity(url) == expected:
            matches.append(name)
    result['matching_remotes'] = matches
    checks['repository'] = 'match' if matches else 'unknown' if not expected else 'mismatch'
    if not matches:
        issues.append('登记仓库缺失或本地远端不匹配；不能凭目录名认定当前项目')
    raw = git('status', '--porcelain=v1', '-z', '--untracked-files=all')
    entries = raw.split('\0')
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        change = {'status': entry[:2], 'path': entry[3:]}
        if 'R' in entry[:2] or 'C' in entry[:2]:
            change['original_path'] = entries[index]
            index += 1
        result['changes'].append(change)
    checks['worktree'] = 'dirty' if result['changes'] else 'clean'
    if result['changes']:
        issues.append('存在未提交或未跟踪内容；先由开发人员决定保留/隔离方式，不清理或覆盖')
    revisions = library.get('revisions', [])
    result['knowledge_revisions'] = [{'id': r['id'], 'commit': r.get('commit'),
        'status': r.get('status', r.get('recorded_status'))} for r in revisions]
    result['knowledge_references'] = library.get('references', [])
    checks['knowledge'] = 'match' if any(r.get('commit') == head and r.get('status', r.get('recorded_status')) == 'ready' for r in revisions) else 'not_matched'
    if checks['knowledge'] != 'match':
        issues.append('没有对应当前HEAD的就绪知识修订；知识仅作参考，先核对来源及版本差异')
    # A checkout or new answer during the check invalidates this snapshot.
    after = client.call('development_get', {'ticket': ticket})
    checks['stable'] = after.get('digest') == state.get('digest') and after.get('execution') == choice and after.get('state') == 'confirmed' and git('rev-parse', '--verify', 'HEAD^{commit}') == head and git('status', '--porcelain=v1', '-z', '--untracked-files=all') == raw
    if not checks['stable']:
        issues.append('检查期间任务或工作区发生变化，请重新核对')
    result['ready'] = not issues
    return result
