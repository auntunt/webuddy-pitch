"""A submitted comment selects and starts the next authorized task operation."""
import json
from pathlib import Path
import re
import tempfile
import os
from urllib.parse import urlsplit

from .errors import ApiError
from .store import now


def continue_comment(P, ticket, author, event_id, requested_agent=None):
    from .app import _routed_agent
    key = 'comment-run:%s' % event_id
    with P.runner.lock:
        saved = P.store.one('SELECT result FROM idem WHERE key=?', (key,))
        if saved:
            receipt = json.loads(saved['result'])
            existing = P.store.one('SELECT id FROM runs WHERE batch=?', (key,))
            if receipt.get('run') or existing:
                return receipt.get('run') or existing['id']
            raise ApiError(409, '评论已保存，续接登记中断；请检查执行记录，不会重复启动')
        if ticket['status'] == 'closed':
            raise ApiError(409, '评论已保存；工单已关闭，请重新打开后继续')
        project = P.store.project(ticket['project_id'])
        runs = P.store.runs(ticket_id=ticket['id'])
        previous = runs[0] if runs else None
        agent = _routed_agent(P, project, requested_agent or (previous['agent'] if previous else None), 'claude')
        with P.store.lock:
            cursor = P.store.db.execute('INSERT OR IGNORE INTO idem(key,result,ts) VALUES(?,?,?)', (key, '{}', now()))
            P.store.db.commit()
            claimed = cursor.rowcount == 1
        if not claimed:
            return continue_comment(P, ticket, author, event_id, requested_agent)
        try:
            run = P.runner.start(project, ticket, agent, 'continue', author,
                                 target=str(event_id), batch=key,
                                 model=(previous.get('model') or None) if previous else None)
        except ValueError:
            if not P.store.one('SELECT id FROM runs WHERE batch=?', (key,)):
                P.store.x('DELETE FROM idem WHERE key=?', (key,))
            raise
        P.store.x('UPDATE idem SET result=? WHERE key=?', (json.dumps({'run': run['id']}), key))
        return run['id']


def push_target(text, remote, branch):
    """Only the current human comment can authorize a literal push destination."""
    if not isinstance(remote, str) or not isinstance(branch, str) or not remote or not branch:
        raise ValueError('请在评论中提供推送仓库（或 remote 名称）和分支')
    if re.search(r'(?:不要|禁止|暂不|不得|如何|怎么).{0,12}(?:推送|push)|(?:do not|don.t)\s+push', text, re.I) or not re.search(r'推送|\bpush\b', text, re.I):
        raise ValueError('本次评论没有明确的 Git 推送指令')
    # No substring matches: a quoted path embedded in another destination is not consent.
    tokens = re.findall(r'[A-Za-z0-9_./:@~%+\-]+', text)
    if remote not in tokens or branch not in tokens:
        raise ValueError('推送仓库和分支必须在本次评论中明确写出')
    if remote.startswith('-') or branch.startswith('-') or branch.startswith('refs/'):
        raise ValueError('推送目标格式不正确')
    if '://' in remote:
        parsed = urlsplit(remote)
        if parsed.scheme != 'https' or parsed.username or parsed.password:
            raise ValueError('请使用不含凭据的 HTTPS 仓库地址，登录凭据沿用本机配置')
    return remote, branch


def push(runner, rid, project, ticket, text, remote, branch):
    from .agents import git, worktree_diff
    from .fixloop import verified
    from .project_library import require_run_current
    from .task_preparation import environment, sensitive, stage
    remote, branch = push_target(text, remote, branch)
    root = Path(project['root'])
    git(root, 'check-ref-format', 'refs/heads/' + branch)
    candidate = next((r for r in runner.store.runs(ticket_id=ticket['id']) if r['mode'] == 'fix'), None)
    if not candidate or candidate['status'] != 'done' or candidate.get('exit_code') != 0:
        raise ValueError('当前没有成功完成的开发成果；先修复当前任务后再推送')
    old = runner.store.run(candidate['id'])
    require_run_current(runner.store, project, old['id'])
    stage(runner, rid, '核对推送成果')
    if old.get('decision', '').startswith('accepted:'):
        commit = git(root, 'rev-parse', old['decision'].rsplit('@', 1)[1] + '^{commit}').strip()
    else:
        wt = Path(old['workdir'])
        verification = verified(runner.data_dir, old['id'])
        if (verification.get('verification_current') is False or verification.get('check') != 'pass'
                or verification.get('verdict') != 'pass' or verification.get('beyond_plan')):
            raise ValueError('构建检查和实现诊断尚未通过，不能推送当前改动')
        actual = worktree_diff(wt)
        head = git(wt, 'rev-parse', 'HEAD').strip()
        if actual != old['diff'] or actual != verification.get('checked_diff') or head != verification.get('checked_base'):
            raise ValueError('当前代码与验证记录不同，请先重新验证')
        with tempfile.TemporaryDirectory(prefix='webuddy-push-index-') as temp:
            env = environment(runner.data_dir, rid)
            env.update(GIT_INDEX_FILE=str(Path(temp) / 'index'), GIT_AUTHOR_NAME='Webuddy',
                       GIT_AUTHOR_EMAIL='webuddy@localhost', GIT_COMMITTER_NAME='Webuddy', GIT_COMMITTER_EMAIL='webuddy@localhost')
            def command(*args):
                result, _ = runner.run_command(rid, ['git', '-C', str(wt), *args], wt, env=env, kind='git-push-snapshot')
                if result.returncode:
                    raise RuntimeError(result.output)
                return result.output.strip()
            command('read-tree', 'HEAD')
            command('add', '-A', '--', '.')
            changed = command('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z', 'HEAD')
            for name in changed.split('\0'):
                if name and (Path(name).name.startswith('.env') or sensitive(name, (wt / name).read_bytes())):
                    raise ValueError('改动包含凭据文件，已保留在本地，未推送')
            staged = command('diff', '--cached', 'HEAD')
            if staged != actual.strip():
                raise ValueError('准备推送期间代码发生变化，未推送')
            tree = command('write-tree')
            commit = command('commit-tree', tree, '-p', head, '-m', f'{ticket["key"]}: development result (pending review)')
            command('update-ref', 'refs/webuddy/push/run-%s' % rid, commit)
    stage(runner, rid, '核对推送成果', 'done', commit[:10])
    # Resolve a named remote once, so a later configuration change cannot redirect this operation.
    remotes = git(root, 'remote').splitlines()
    destination = git(root, 'remote', 'get-url', '--push', remote).strip() if remote in remotes else remote
    parsed = urlsplit(destination)
    https = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
    ssh = re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+', destination)
    local = Path(destination).is_absolute() and Path(destination).is_dir()
    if not (https or ssh or local) or '\n' in destination:
        raise ValueError('仓库地址必须是无凭据的 HTTPS、SSH 地址或明确的本地仓库路径')
    stage(runner, rid, '推送开发分支', detail=branch)
    result, _ = runner.run_command(rid, ['git', 'push', '--porcelain', '--', destination, f'{commit}:refs/heads/{branch}'],
                                   root, env=dict(environment(runner.data_dir, rid), GIT_TERMINAL_PROMPT='0'),
                                   timeout=180, kind='git-push', on_output=lambda chunk, final=False: runner.store.append_output(rid, chunk))
    if result.returncode:
        raise RuntimeError('Git 推送失败；原代码和本地提交已保留。\n' + result.output)
    stage(runner, rid, '推送开发分支', 'done', f'{branch} · {commit[:10]}')
    receipt = {'commit': commit, 'remote': remote, 'branch': branch, 'source_run': old['id']}
    (runner.data_dir / 'runs' / str(rid) / 'push.json').write_text(json.dumps(receipt), encoding='utf-8')
    return f'已推送开发成果到 {remote} 的 {branch} 分支。提交 {commit[:10]}。\n任务验收与合并状态保持原样。'


def execute_comment(runner, rid, project, ticket, agent, conf, model):
    from .fixloop import fenced
    from .task_preparation import stage
    record = runner.store.run(rid)
    event = runner.store.one('SELECT * FROM events WHERE id=? AND ticket_id=? AND kind=? AND author=?',
                             (record['target'], ticket['id'], 'comment', record['author']))
    if not event:
        raise ValueError('评论来源与当前任务或提交人不一致')
    text = event['body']
    previous = next((r for r in runner.store.runs(ticket_id=ticket['id']) if r['mode'] != 'continue' and r['id'] < rid), None)
    stage(runner, rid, '理解本次补充')
    root = Path(project['root'])
    root.mkdir(parents=True, exist_ok=True)
    prompt = ('你是任务调度助手，只选择下一步，不运行命令、不修改文件。用户本次评论是新的输入，历史材料仅作上下文。'
              '普通问答或缺少确实必要的信息选answer并给出reply；分析选analyze；明确需要方案选plan；'
              '修改代码、自动准备Git或依赖、修复构建、继续失败开发选fix；明确要求推送且提供仓库和分支选push。'
              '不要让用户手动初始化Git、安装依赖或执行构建，开发流程会自动完成这些准备。'
              '不要承诺已执行。只输出一个tmh-next JSON代码块，action为answer/analyze/plan/fix/push；'
              'answer带reply；push带remote和branch，必须逐字来自本次评论，禁止从历史材料猜测。\n'
              + '任务：' + ticket['title'] + '\n' + (ticket.get('body') or '')
              + '\n最近执行：' + json.dumps(previous, ensure_ascii=False)
              + '\n本次评论全文：\n' + text)
    code, result = runner.invoke(rid, project, ticket, agent, conf, 'ask', prompt, root, model, tag='-intent')
    if code:
        raise RuntimeError(result or '评论理解失败')
    choice = fenced('tmh-next', result)
    if not isinstance(choice, dict) or choice.get('action') not in ('answer', 'analyze', 'plan', 'fix', 'push'):
        raise ValueError('智能体未返回有效的下一步；原评论与输出已保留')
    action = choice['action']
    stage(runner, rid, '理解本次补充', 'done', {'answer':'回答问题','fix':'继续开发','plan':'生成方案','analyze':'分析需求','push':'推送开发分支'}[action])
    if runner.stop_reason(rid):
        raise RuntimeError('已停止处理评论')
    if action == 'answer':
        return 0, str(choice.get('reply') or '请补充任务所需的信息。')
    if action == 'push':
        return 0, push(runner, rid, project, ticket, text, choice.get('remote'), choice.get('branch'))
    with runner.lock:
        if runner.stop_reason(rid):
            raise RuntimeError('已停止处理评论')
        fixes = [r for r in runner.store.runs(ticket_id=ticket['id']) if r['mode'] == 'fix']
        latest = fixes[0] if fixes else None
        if action == 'fix' and latest and not latest.get('decision'):
            following = runner.retry(latest['id'], record['author'], continuation=True)
        else:
            base = latest['decision'].rsplit('@', 1)[1] if action == 'fix' and latest and latest.get('decision', '').startswith('accepted:') else ''
            following = runner.start(project, ticket, agent, action, record['author'], model=model or None, base=base)
    link = {'next_run': following['id'], 'action': action, 'comment': event['id']}
    (runner.data_dir / 'runs' / str(rid) / 'continuation.json').write_text(json.dumps(link), encoding='utf-8')
    stage(runner, rid, '继续任务', 'done', '#%s' % following['id'])
    return 0, '已根据本次评论继续%s，执行记录 #%s。' % ({'fix':'开发','plan':'生成方案','analyze':'分析'}[action], following['id'])
