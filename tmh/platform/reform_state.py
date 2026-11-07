"""Current reform facts, kept separate from immutable acceptance history."""
from pathlib import Path

from .store import now


def ticket(P, project, t):
    from .fixloop import verified
    from . import candidates, learn
    from .agents import git
    if t.get('links',{}).get('reform',{}).get('role')=='parent':
        from . import reform
        from .reform_integration import current
        p=reform.plan(P.data_dir,project['key'],t['links']['reform']['plan'])
        integration=current(P,project,p)
        ready=integration['state']=='verified' and all(i.get('ticket') and P.store.ticket(i['ticket'])['status']=='closed' for i in p['items'])
        return dict(ticket=t['key'],run_id=None,state='awaiting_acceptance' if ready else 'blocked',
            label=('当前集成版本已整体验收' if t['status']=='closed' else '集成验证通过，待整体验收') if ready else '整体验收尚受阻',next_owner=p.get('execution_owner') or p['by'],
            candidate_commit=integration.get('commit'),evidence_validity='valid' if ready else 'not_checked',
            automatic_verification='passed' if ready else 'not_checked',historical_acceptance=t['status']=='closed',
            integrated_delivery='accepted' if ready and t['status']=='closed' else 'pending',
            next_action=integration['blocked'] or '在整体验收入口核对固定版本',updated=t['updated'])
    runs = P.store.runs(ticket_id=t['id'])
    active = next((r for r in runs if r['status'] in ('queued','running')),None)
    fixes = [r for r in runs if r['mode']=='fix']
    run = fixes[0] if fixes else None
    accepted, adopted_run = learn._adopted(P.store,t['id'])
    commit = (accepted or {}).get('commit')
    result = dict(ticket=t['key'],run_id=(active or run or {}).get('id'),
        state='waiting',label='等待处理',next_owner=t.get('assignee') or t['reporter'],
        candidate_commit=commit,evidence_validity='not_checked',automatic_verification='not_checked',
        historical_acceptance=t['status']=='closed',integrated_delivery='not_checked',
        next_action='查看工单与运行',updated=t['updated'])
    if active:
        result.update(state=active['status'],label='排队中' if active['status']=='queued' else '运行中')
        return result
    ctx=getattr(P,'tenant_context',None)
    if ctx is not None:
        from .tenant_runtime import ACTOR
        if not ctx.runtime_allowed(ACTOR.get()):
            result.update(label='历史已验收；当前证据待核对' if t['status']=='closed' else '当前证据待核对',
                next_action='请由项目执行负责人核对当前版本与验证；此连接不执行版本检查')
            return result
    if run:
        result['state'] = 'code_produced' if run.get('diff_bytes',0) or P.store.run(run['id']).get('diff') else 'execution_ended'
        result['label'] = '已产生代码，证据待核对' if result['state']=='code_produced' else '执行已结束'
        v = verified(P.data_dir,run['id'])
        if v.get('verification_current') is False:
            result.update(evidence_validity='invalid',label='当前验证已失效',next_action=v.get('skip') or '重新验证')
        elif v.get('check')=='fail' or v.get('verdict')=='fail':
            result.update(automatic_verification='failed',label='验证未通过')
        # External candidates already own their complete version/configuration guards.
        row = P.store.one('SELECT name FROM sqlite_master WHERE name=\'code_candidates\'')
        candidate = P.store.one('SELECT id FROM code_candidates WHERE ticket_id=? ORDER BY id DESC LIMIT 1',(t['id'],)) if row else None
        if candidate:
            current = candidates.view(P,candidate['id'],include_probe=False)
            result['candidate_commit'] = current['commit']
            if any(reason!='工单已关闭' for reason in current['blocked']) or current['verification'].get('verification_current') is False:
                result.update(evidence_validity='invalid',label='候选依据已变化',next_action='核对候选与当前需求')
            elif current['verification_passed']:
                result.update(evidence_validity='valid',automatic_verification='passed',state='verified',label='自动验证通过，交付决定待核对',next_action='在团队工作台核对独立复核、负责人合并与业务验收门槛')
        elif commit and v.get('checked_commit')==commit and adopted_run and adopted_run['id']==run['id'] and v.get('verification_contract') and v.get('check')=='pass' and v.get('verdict')=='pass':
            from .project_library import run_current
            full = P.store.run(run['id'])
            root = Path(project['root'])
            actual = git(root,'rev-parse','--verify','--end-of-options',commit+'^{commit}',check=False).strip()
            base = v.get('checked_base')
            if actual == commit and base and run_current(P.store,project,run['id']):
                diff = git(root,'diff',base,commit,check=False)
                if diff == full['diff'] and v.get('checked_diff') == full['diff']:
                    result.update(evidence_validity='valid',automatic_verification='passed',state='awaiting_acceptance',label='自动验证通过，待业务验收')
    if t['status']=='closed':
        result['label'] = '历史已验收；当前证据'+{'valid':'有效','invalid':'已失效','not_checked':'待核对'}[result['evidence_validity']]
    elif t['status']=='verify' and result['evidence_validity']!='valid':
        result['label'] = '待核对代码与当前证据'
    return result


def test_configuration(P, project):
    from .candidates import configuration
    from .project_tests import digest, view
    return digest({'candidate_configuration':configuration(P,project),'project_tests':view(P.data_dir,project['key'])['profile']})


def checkpoint(P, project, p, reason):
    """Record only references that exist; this receipt never asserts verification."""
    from .agents import git
    source = p.get('base') or p.get('source_version')
    if not source:
        return None  # Legacy plans have no trustworthy fixed version to checkpoint.
    commits = []
    records = []
    for item in p['items']+p.get('integrations',[]):
        if not item.get('ticket'):
            continue
        t = P.store.ticket(item['ticket'])
        from .reform_integration import accepted_commit
        commit = accepted_commit(P,project,t)
        if not commit:
            from .learn import _adopted
            adopted, _ = _adopted(P.store,t['id'])
            commit = (adopted or {}).get('commit')
        if commit:
            commits.append(commit)
        records.append(dict(ticket=t['key'],batch=item.get('batch'),commit=commit,
            runs=[dict(run_id=r['id'],status=r['status'],stop_receipt='not_checked') for r in P.store.q('SELECT id,status FROM runs WHERE ticket_id=? ORDER BY id',(t['id'],))]))
    root = Path(project['root'])
    available = []
    for sha in dict.fromkeys([source]+commits):
        if sha and git(root,'rev-parse','--verify','--end-of-options',sha+'^{commit}',check=False).strip()==sha:
            git(root,'update-ref','refs/webuddy/reforms/'+p['uid']+'/checkpoints/'+str(len(p.get('checkpoints',[]))+1)+'/'+sha,sha)
            available.append(sha)
    value = dict(id=len(p.get('checkpoints',[]))+1,created=now(),reason=reason,plan_revision=p['revision'],
        source_commit=source,available_commits=available,batch=p.get('batch',0),items=records,
        contract={k:p.get(k) for k in ('goal','keep','scope_mode','domains','criteria','knowledge_revision','target_environment','dependencies','source_version')},
        test_configuration=test_configuration(P,project),verification='not_checked',integrated_delivery='not_checked')
    p.setdefault('checkpoints',[]).append(value)
    p['checkpoint'] = value
    return value


def checkpoint_preflight(P, project, p):
    from .agents import git
    value = p.get('checkpoint')
    if not value:
        return dict(status='missing',blocked=[],retained_commits=[])
    ctx=getattr(P,'tenant_context',None)
    if ctx is not None:
        from .tenant_runtime import ACTOR
        if not ctx.runtime_allowed(ACTOR.get()):
            return dict(status='not_checked',checkpoint_id=value['id'],blocked=['当前连接不具备版本核验条件，请由项目执行负责人核对'],retained_commits=value['available_commits'])
    expected = list(dict.fromkeys([value.get('source_commit')]+[x['commit'] for x in value['items'] if x.get('commit')]))
    missing = [sha for sha in expected if not sha or git(Path(project['root']),'rev-parse','--verify','--end-of-options',sha+'^{commit}',check=False).strip()!=sha]
    changed = [key for key,old in value['contract'].items() if p.get(key)!=old]
    if value.get('test_configuration')!=test_configuration(P,project):
        changed.append('test_configuration')
    return dict(status='blocked' if missing else 'accessible',checkpoint_id=value['id'],
        blocked=['检查点提交不可访问；请核对项目仓库与受保护引用：'+str(sha) for sha in missing],
        changed_inputs=changed,retained_commits=[sha for sha in expected if sha and sha not in missing],
        revalidation='当前代码、验收标准、测试配置与目标环境均须按当前绑定核对；检查点不代表验证通过')
