"""Reuse the epic parent and human acceptance entry for the integrated plan."""
import json
from .store import now


def ensure(P, project, p, by):
    if p.get('parent') or p.get('integration_policy')!='serial_batches':
        return
    spec=dict(goal=p['goal'],keep=p['keep'],out='本计划明确范围以外的业务',evidence='固定集成提交、项目测试与逐项业务验收',
        done=[dict(id='A%d'%(i+1),text=text,check='在固定集成版本按本条业务条件验证',open=False) for i,text in enumerate(p['criteria'])])
    parent=P.store._create_ticket_in_tx(project['id'],'改造整体验收：'+p['title'],by,type='feature',
        body='\n'.join(['## 改造目标',p['goal'],'## 不可变约束',p['keep'],'## 整体验收标准']+['- '+x for x in p['criteria']]),
        links=dict(later='改造计划父单，仅在当前集成版本通过后整体验收',children=[],
            reform=dict(plan=p['id'],uid=p['uid'],project=project['key'],role='parent'),
            epic=dict(spec=spec,wave=p['wave'],auto=False,batch=0,by=by,log=[])))
    p['parent']=parent['key']


def sync(P, project, p, db):
    if not p.get('parent'):
        return
    from .reform_integration import current
    integration=current(P,project,p)
    parent=P.store.ticket(p['parent'])
    children=[i['ticket'] for i in p['items']+p.get('integrations',[]) if i.get('ticket')]
    complete=all(i.get('ticket') and P.store.ticket(i['ticket'])['status']=='closed' for i in p['items'])
    ready=complete and integration['state']=='verified' and not p.get('cancelled')
    links=json.loads(json.dumps(parent['links']))
    links['children']=children
    links['epic']['batch']=p.get('batch',0)
    links['epic']['summary']=[dict(key=key,title=P.store.ticket(key)['title'],version='',verdict='请核对原始验收与当前证据') for key in children]
    links['reform_integration_commit']=integration.get('commit') if ready else None
    status='closed' if parent['status']=='closed' and p.get('overall',{}).get('passed') else 'verify' if ready else 'doing'
    changed=links!=parent['links'] or status!=parent['status']
    # links is decoded independently by Store; persist it in this plan transaction.
    if status!=parent['status']:
        db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'flow',?,?)",
            (parent['id'],now(),P.flow.BY,'改造整体状态更新：'+status,json.dumps({'integration_commit':links['reform_integration_commit']})))
    db.execute('UPDATE tickets SET links=?,status=?,updated=? WHERE id=?',
        (json.dumps(links,ensure_ascii=False),status,now() if changed else parent['updated'],parent['id']))


def guard(P, t, *, passed=True):
    reference=t['links'].get('reform') or {}
    if reference.get('role')!='parent':
        return None
    from . import reform
    from .reform_integration import current
    project=P.store.project(t['project_id'])
    p=reform.plan(P.data_dir,project['key'],reference['plan'])
    if reference.get('uid')!=p['uid'] or p.get('parent')!=t['key']:
        raise ValueError('整体验收工单与计划归属不一致，请核对原始关系')
    if not passed:
        return None
    integration=current(P,project,p)
    if (reference.get('uid')!=p['uid'] or p.get('parent')!=t['key'] or p.get('archived') or p.get('cancelled') or
            integration['state']!='verified' or integration['commit']!=t['links'].get('reform_integration_commit') or
            any(not i.get('ticket') or P.store.ticket(i['ticket'])['status']!='closed' for i in p['items'])):
        raise ValueError('计划尚无当前固定集成版本的完整验证，或子任务仍未完成；请从改造工作区核对')
    return integration['commit']


def outcome(P, project, p, t, passed, note, db):
    if p.get('parent')!=t['key']:
        return []
    events=[e for e in P.store.events(t['id']) if e['kind'] in ('accept','reject')]
    if not events:
        return []
    event=events[-1]
    if event['kind']!=('accept' if passed else 'reject') or p.get('overall',{}).get('event_id')==event['id']:
        return []
    p['overall']=dict(event_id=event['id'],passed=passed,note=note,at=event['ts'],actor=event['author'],
        commit=t['links'].get('reform_integration_commit'))
    p['revision']+=1
    from .reform import _log, _release_in_tx, _blocked
    if passed:
        _log(p,'整体验收已记录；当前有效性仍按固定集成版本检查')
        return []
    order=max(i['order'] for i in p['items'])+1
    p['items'].append(dict(order=order,domain='',title='整体验收返修',body=note,
        repair_of=event['id'],flows=0,tables=0,flow_ids=[],files=[],shared=[],unresolved=0,score=0,risk='高'))
    _log(p,'整体验收退回，登记关联返修：'+note)
    return _release_in_tx(P,project,p,None,P.flow.BY,db) if p.get('auto') and not _blocked(P,p) else []


def parent_outcome(P, project, t, passed, note):
    from . import reform
    ref=t['links']['reform']
    with reform._transaction(P.data_dir,P.store) as db:
        plans=reform._load(P.data_dir,project['key'],db)
        p=next((x for x in plans if x['id']==ref['plan']),None)
        if not p or p['uid']!=ref.get('uid') or p.get('archived'):
            return []
        made=outcome(P,project,p,t,passed,note,db)
        sync(P,project,p,db)
        reform._save(P.data_dir,project['key'],plans,db)
    reform._dispatch(P,project,p['id'],made)
    return [item['key'] for item in made]
