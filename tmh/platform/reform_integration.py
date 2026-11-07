"""A batch advances only through an accepted fixed integration version."""
from pathlib import Path
from .store import now


def accepted_commit(P, project, t):
    from .learn import _adopted
    adopted, _ = _adopted(P.store,t['id'])
    events=P.store.events(t['id'])
    accept=max((e['id'] for e in events if e['kind']=='accept'),default=0)
    changed=max((e['id'] for e in events if e['kind'] in ('adopt','reject')),default=0)
    if adopted and accept>changed:
        return adopted['commit']
    # Team business acceptance records the exact external candidate, not a floating branch.
    events = P.store.events(t['id'])
    last = next((e for e in reversed(events) if e['kind'] in ('accept','reject','adopt')),None)
    if not last or last['kind']!='accept':
        return ''
    data = last['data']
    candidate = data.get('candidate')
    if not candidate:
        return ''
    row = P.store.one('SELECT commit_sha,ticket_id FROM code_candidates WHERE id=?',(candidate,))
    return row['commit_sha'] if row and row['ticket_id']==t['id'] and row['commit_sha']==data.get('commit') else ''


def current(P, project, p):
    if p.get('integration_policy')!='serial_batches' or not p.get('batch'):
        return {'state':'not_required','blocked':'','commit':None}
    record = next((x for x in p.get('integrations',[]) if x['batch']==p['batch']),None)
    if not record:
        missing = [i['ticket'] for i in p['items'] if i.get('batch')==p['batch'] and not accepted_commit(P,project,P.store.ticket(i['ticket']))]
        return dict(state='missing',blocked='本批缺少固定验收提交：'+', '.join(missing) if missing else '',commit=None)
    t = P.store.ticket(record['ticket'])
    if not t or t['project_id']!=project['id'] or t['links'].get('reform',{}).get('uid')!=p['uid']:
        return dict(state='blocked',blocked='集成任务归属需要核对',commit=None)
    if t['status']!='closed':
        return dict(state='waiting',blocked='等待本批集成任务 '+t['key']+' 的版本验证与业务决定',ticket=t['key'],commit=None)
    sha = accepted_commit(P,project,t)
    if not sha:
        return dict(state='blocked',blocked='集成任务缺少已验收的固定提交',ticket=t['key'],commit=None)
    from .reform_state import ticket
    evidence = ticket(P,project,t)
    if evidence['evidence_validity']!='valid':
        return dict(state='blocked',blocked='集成版本的当前验证未通过或尚未核对',ticket=t['key'],commit=sha)
    from .agents import git
    import subprocess
    # Use return codes: merge-base has no stdout on either success or failure.
    from .project_git import read
    for parent in [record['base']]+record['inputs']:
        args=['merge-base','--is-ancestor',parent,sha]
        result = read(Path(project['root']),args,text=True)
        if result is None:
            result = subprocess.run(['git','-C',project['root']]+args,capture_output=True,text=True)
        if result.returncode:
            return dict(state='blocked',blocked='集成提交未包含本批固定输入：'+parent,ticket=t['key'],commit=sha)
    return dict(state='verified',blocked='',ticket=t['key'],commit=sha)


def register(P, project, p, by, db):
    """Called in the same plan/ticket transaction; one integration ticket per batch."""
    inputs = [accepted_commit(P,project,P.store.ticket(i['ticket'])) for i in p['items'] if i.get('batch')==p['batch']]
    if not inputs or not all(inputs):
        raise ValueError('本批缺少固定验收提交，不能猜测集成输入')
    body='\n'.join(['## 本批集成',p['goal'],'## 不可变约束',p['keep'],
        '## 固定输入','集成基线：'+p['base']]+['- '+sha for sha in inputs]+[
        '必须保留上述各固定提交的祖先关系，在独立候选分支集成；不得移动原子任务分支。',
        '检查新增与受影响旧场景。冲突、测试未执行、环境缺失或规则分歧必须分别记录，不能冒充通过。',
        '## 整体验收标准']+['- '+text for text in p['criteria']])
    batch=p['batch']
    links={'reform':dict(plan=p['id'],uid=p['uid'],project=project['key'],batch=batch,order=-batch,role='integration'),
           'base':p['base'],'reform_integration_inputs':inputs}
    t=P.store._create_ticket_in_tx(project['id'],'第 %d 批集成：%s'%(batch,p['title']),by,
        body=body,type='change',priority='normal',labels=['改造集成'],links=links)
    db.execute('INSERT INTO reform_dispatch VALUES(?,?,?,?,?,?,?)',(p['uid'],-batch,batch,t['id'],'pending',by,now()))
    p.setdefault('integrations',[]).append(dict(batch=batch,ticket=t['key'],base=p['base'],inputs=inputs,created=now()))
    p['revision']+=1
    from .reform import _log
    _log(p,'登记第 %d 批固定集成任务：%s；下一批等待当前集成版本验证与业务决定'%(batch,t['key']))
    return [t]
