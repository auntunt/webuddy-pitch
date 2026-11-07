"""Recheck the current member and connection at each managed execution boundary."""
from .errors import ApiError


def require(P, project, p):
    ctx=getattr(P,'tenant_context',None)
    if ctx is None:
        return
    from . import tenant_policy
    from .tool_access import validate_connection
    owner=p.get('execution_owner')
    if not owner:
        raise ApiError(403,'旧计划缺少执行负责人，请从受权入口核对交接')
    # Reconstruct current authority from server records, never a saved credential.
    with ctx.acting(owner):
        who=tenant_policy.identity(P,owner)
        tenant_policy._check(P,who,project,'contributor')
        tenant_policy.require_execution(P,owner)
        if p.get('execution_connection'):
            connection=validate_connection(ctx.registry,ctx.tenant_id,p['execution_connection'],owner)
            if connection['scope'] not in ('execute','develop') or project['id'] not in connection['project_ids']:
                raise ApiError(403,'原工具连接不再授权本项目执行')


def run(runner, project, ticket, *, new_run=False):
    ctx=getattr(runner,'tenant_context',None)
    if not ticket or not ticket.get('links',{}).get('reform'):
        return
    store=ctx.platform.store if ctx is not None else runner.store
    ticket=store.ticket(ticket['id'])
    from . import reform
    reference=ticket['links']['reform']
    p=reform.plan(ctx.platform.data_dir if ctx is not None else runner.data_dir,project['key'],reference['plan'])
    members=p['items']+p.get('integrations',[])
    if (ticket['project_id']!=project['id'] or reference.get('uid')!=p['uid'] or
            not any(i.get('ticket')==ticket['key'] and i.get('batch')==reference.get('batch') for i in members)):
        raise ApiError(409,'运行与当前计划批次归属不一致，不能执行')
    if p.get('archived') or p.get('cancelled'):
        raise ApiError(409,'计划已取消或归档，不再启动新执行步骤；已有代码与历史保留')
    if new_run and p.get('paused'):
        raise ApiError(409,'计划已暂停后续步骤；当前运行继续，新的运行须先从计划核对恢复')
    if ctx is not None:
        require(ctx.platform,project,p)
