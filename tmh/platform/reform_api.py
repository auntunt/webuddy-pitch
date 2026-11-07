"""Shared typed plan management; the platform database remains the only state source."""
import hashlib
import json
from urllib.parse import quote

from . import reform
from .errors import ApiError
from .store import now


def _encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def packet(P, project, p):
    value = reform.view(P,project,p)
    value.update(plan_id=p['id'],plan_revision=p['revision'],project=project['key'],
        deep_link='#/projects/%s/reforms/%s' % (quote(project['key']),quote(p['id'])),
        status_updated=p.get('updated') or p['created'],
        next_owner=p.get('execution_owner') or p['by'],checkpoint=p.get('checkpoint'))
    return value



def summary(value):
    omitted = ('goal','keep','log','revisions','checkpoints','items')
    result = {key:item for key,item in value.items() if key not in omitted}
    result['scope_ref'] = {'operation':'reform_get','project':value['project'],'plan_id':value['id'],'view':'scope'}
    result['tasks_ref'] = dict(result['scope_ref'],view='tasks')
    result['events_ref'] = {'operation':'reform_events','project':value['project'],'plan_id':value['id']}
    return result

def resume_preview(P, project, p):
    ready = dict(p)
    ready.pop('paused',None)
    blocked = reform._blocked(P,ready)
    from .reform_state import checkpoint_preflight
    checkpoint = checkpoint_preflight(P,project,p)
    blocked = '; '.join(checkpoint['blocked']) or blocked
    runs = []
    ctx=getattr(P,'tenant_context',None)
    from .tenant_runtime import ACTOR
    may_check=ctx is None or ctx.runtime_allowed(ACTOR.get())
    if not may_check:
        blocked='当前连接不具备执行及恢复核对权限；请由项目执行负责人处理'
    for item in p['items']+p.get('integrations',[]):
        if not item.get('ticket'):
            continue
        ticket = P.store.ticket(item['ticket'])
        if not ticket or ticket['project_id'] != project['id']:
            raise ApiError(409,'计划与子任务归属不一致，请核对历史')
        for run in P.store.runs(ticket_id=ticket['id']):
            if run['status'] in ('failed','cancelled') and not may_check:
                runs.append(dict(run_id=run['id'],ticket=ticket['key'],can_retry=None,check_status='not_checked',blocked=['需要当前执行授权核对停止回执与代码']))
            elif run['status'] in ('failed','cancelled'):
                current = P.runner.retry_state(run['id'])
                runs.append(dict(run_id=run['id'],ticket=ticket['key'],can_retry=current['can_retry'],
                    blocked=current['retry_blocked'],retry_run=current.get('retry_run')))
            elif run['status'] in ('running','queued'):
                runs.append(dict(run_id=run['id'],ticket=ticket['key'],can_retry=False,blocked=['原运行仍活跃，不能创建副本']))
    return dict(summary(packet(P,project,p)),recovery_runs=runs,blocked=blocked,
        allowed_actions=[] if not may_check else ['pause','cancel'] if blocked else ['resume' if p.get('paused') else 'start' if not p.get('batch') else 'release_next','pause','cancel'],
        retained='原运行、代码、未验证快照及历史证据保留；不把历史通过当作当前通过',
        revalidation='续跑会形成新证据；集成版本及环境仍须独立核对',
        checkpoint_accessibility=checkpoint['status'],checkpoint_preflight=checkpoint)


def execute(P, req, actor, operation, a):
    project = P.project(a['project'])
    if operation == 'reform_preview':
        return reform.preview(P.kb.atlas(project),a)
    if operation == 'reforms_list':
        rows = reform.plans(P.data_dir,project['key'],include_archived=True,store=P.store)
        rows = [p for p in rows if bool(p.get('archived')) == a.get('archived',False)]
        if a.get('status'):
            rows=[p for p in rows if packet(P,project,p)['state']==a['status']]
        # Array offsets remain opaque to clients; immutable plan identities travel in every row.
        offset,limit = a.get('after',0),a.get('limit',20)
        selected = rows[offset:offset+limit]
        more = len(rows)>offset+len(selected)
        return {'items':[summary(packet(P,project,p)) for p in selected],
                'next_cursor':offset+len(selected) if more else None,'next_after':offset+len(selected),'has_more':more}
    if operation == 'reform_create':
        try:
            p = reform.create(P.data_dir,project['key'],P.kb.atlas(project),a,actor)
        except ValueError as exc:
            raise ApiError(409,str(exc)) from exc
        req.agent_side_effect_started = True
        return dict(packet(P,project,p),operation_id=a['request_id'],request_id=a['request_id'],request_state='succeeded')
    try:
        p = reform.plan(P.data_dir,project['key'],a['plan_id'],store=P.store)
    except KeyError:
        raise ApiError(404,'没有这个项目的改造计划') from None
    if operation == 'reform_get':
        value = packet(P,project,p)
        view = a.get('view','summary')
        if view == 'summary':
            return summary(value)
        if view == 'scope':
            fields = ('goal','keep','kind','title','wave','scope_mode','domains','criteria','dependencies','target','source_version','target_environment','knowledge_revision','revisions')
            scope={key:p.get(key) for key in fields}
            scope['lead']=next(({'title':i['title'],'body':i['body']} for i in p['items'] if i.get('lead')),{'title':'','body':''})
            return dict(summary(value),scope=scope)
        rows = value['items'] if view=='tasks' else p.get('checkpoints',[])
        offset,limit = a.get('after',0),a.get('limit',20)
        selected = rows[offset:offset+limit]
        return dict(summary(value),items=selected,next_cursor=offset+len(selected) if len(rows)>offset+len(selected) else None)
    if operation == 'reform_resume_preview':
        return resume_preview(P,project,p)
    if operation == 'reform_events':
        events = [dict(event,id=index) for index,event in enumerate(p.get('log',[]),1)]
        events = [event for event in events if event['id']>a.get('after',0)]
        limit = a.get('limit',20)
        selected = events[:limit]
        cursor = selected[-1]['id'] if selected else a.get('after',0)
        return {'plan_id':p['id'],'revision':p['revision'],'items':selected,'next_after':cursor,
                'next_cursor':cursor if len(events)>limit else None,'has_more':len(events)>limit,
                'legacy_history_complete':p.get('legacy_history_complete',True)}
    made = []
    fingerprint = hashlib.sha256(_encoded({'operation':operation,'arguments':a}).encode()).hexdigest()
    try:
        with reform._transaction(P.data_dir,P.store) as db:
            ps = reform._load(P.data_dir,project['key'],db)
            p = next(x for x in ps if x['id']==a['plan_id'])
            old = db.execute('SELECT fingerprint,result FROM reform_operations WHERE actor=? AND request_id=?',(actor,a['request_id'])).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ApiError(409,'请求编号已用于不同内容')
                return json.loads(old['result'])
            if p['revision'] != a['expected_revision']:
                raise ApiError(409,'计划修订冲突；请读取当前计划，原修改稿未覆盖')
            if p.get('archived'):
                raise ApiError(409,'计划已归档')
            if operation == 'reform_update':
                if any(item.get('ticket') for item in p['items']):
                    raise ApiError(409,'已经派发的任务契约不能被改写；请使用有关联的新修订与返修')
                changes = a['changes']
                p.setdefault('revisions',[]).append(dict(revision=p['revision'],at=now(),actor=actor,reason=a['reason'],
                    contract={key:p.get(key) for key in ('kind','title','goal','keep','scope_mode','domains','wave','target','source_version','target_environment','criteria','dependencies','knowledge_revision')},items=p['items']))
                if not changes:
                    raise ApiError(400,'请明确要修订的字段')
                body = {k:p.get(k) for k in ('kind','title','goal','keep','scope_mode','domains','wave','target','source_version','target_environment','criteria','dependencies','knowledge_revision')}
                body['lead'] = next(({'title':i['title'],'body':i['body']} for i in p['items'] if i.get('lead')),{'title':'','body':''})
                body.update(changes)
                # Reuse the exact creation validator without starting a second transaction.
                draft = reform.create(P.data_dir,project['key'],P.kb.atlas(project),body,actor,_db=db,_persist=False)
                for field in body:
                    if field != 'lead':
                        p[field] = draft.get(field,body[field])
                p['items'] = draft['items']
                if draft.get('base'):
                    p['base'] = draft['base']
                reform._log(p,'修订范围与约束：'+a['reason'])
            elif operation == 'reform_archive':
                reform.remove(P.data_dir,project['key'],p['id'],_db=db)
                ps = reform._load(P.data_dir,project['key'],db)
                p = next(x for x in ps if x['id']==a['plan_id'])
            elif operation == 'reform_control':
                action = a['action']
                if action in ('pause','cancel'):
                    p['paused'] = '计划已暂停；当前运行继续，后续步骤不再领取'
                    if action == 'cancel':
                        p['cancelled'] = now()
                        p['auto'] = False
                        p['paused'] = '计划已取消后续调度；已派发任务保留，停止运行需核对各自回执'
                    reform._log(p,p['paused'])
                    from .reform_state import checkpoint
                    checkpoint(P,project,p,'受控暂停；当前运行继续，停止回执仍须逐项核对')
                else:
                    if p.get('cancelled'):
                        raise ApiError(409,'计划已取消，不能创建新的执行链')
                    from .reform_state import checkpoint_preflight
                    missing = checkpoint_preflight(P,project,p)['blocked']
                    if missing:
                        raise ApiError(409,'; '.join(missing))
                    if action == 'start' and p.get('batch'):
                        raise ApiError(409,'计划已启动，请读取当前批次后使用release_next或resume')
                    if action == 'release_next' and not p.get('batch'):
                        raise ApiError(409,'计划尚未启动，请先使用start')
                    if action == 'resume':
                        p.pop('paused',None)
                        pending = P.store.q("SELECT ticket_id FROM reform_dispatch WHERE plan_uid=? AND state='pending'",(p['uid'],))
                        uncertain = P.store.one("SELECT ticket_id FROM reform_dispatch WHERE plan_uid=? AND state IN ('claimed','needs_reconcile')",(p['uid'],))
                        made = [] if uncertain else [P.store.ticket(row['ticket_id']) for row in pending]
                    why = reform._blocked(P,p)
                    if why and not made:
                        raise ApiError(409,why)
                    if not made:
                        made = reform._release_in_tx(P,project,p,None,req.user,db)
            else:
                raise ApiError(400,'未知计划操作')
            from .reform_delivery import sync
            sync(P,project,p,db)
            p['revision'] += 1
            p['updated'] = now()
            reform._save(P.data_dir,project['key'],ps,db)
            result = dict(packet(P,project,p),request_id=a['request_id'],operation_id=a['request_id'],
                          request_state='accepted' if made else 'succeeded',opened=[t['key'] for t in made])
            db.execute('INSERT INTO reform_operations VALUES(?,?,?,?,?,?)',
                       (actor,a['request_id'],fingerprint,p['uid'],_encoded(result),now()))
    except ValueError as exc:
        raise ApiError(409,str(exc)) from exc
    req.agent_side_effect_started = True
    reform._dispatch(P,project,p['id'],made)
    return result
