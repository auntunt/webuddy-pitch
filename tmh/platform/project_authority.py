"""Bind a project run to a current personal grant, including later revocation."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .errors import ApiError
from . import project_git, tenant_policy


@dataclass(frozen=True)
class Authority:
    platform: object
    principal: str
    tenant: str
    project_id: int
    project_key: str
    root: str
    image: str
    epoch: str
    revision: int

    def current(self, job):
        if job.principal != self.principal or job.project != self.project_key or job.image_id != self.image:
            return False
        P=self.platform;ctx=P.tenant_context;reg=ctx.registry
        try:
            with reg.authorization_guard():
                project=P.store.project(self.project_id)
                if not project or project['key']!=self.project_key or project['root']!=self.root:
                    return False
                who=tenant_policy.identity(P,self.principal)
                if who.get('tool_connection') or who['role'] not in ('member','admin'):
                    return False
                tenant_policy.require_member(P,self.principal,project,'contributor')
                account=reg.one('SELECT active,epoch FROM accounts WHERE name=?',(self.principal,))
                settings=project_git.settings(P)
                if (not account or not account['active'] or account['epoch']!=self.epoch or
                        not settings or settings['image']!=self.image or self.project_key not in settings['projects'] or
                        not ctx.workspace_allowed(self.root)):
                    return False
                for row in reg.q('SELECT action,tenant_id,payload FROM access_audit WHERE revision>? ORDER BY id',(self.revision,)):
                    action=row['action']
                    if action in ('tenant_disable','tenant_enable') and row['tenant_id']==self.tenant:
                        return False
                    if action not in ('member_set','member_remove','project_grant','project_revoke',
                                      'account_disable','account_enable','password_reset','account_set','account_remove'):
                        continue
                    try:
                        payload=json.loads(row['payload'])
                    except (TypeError,ValueError):
                        return False
                    if not isinstance(payload,dict):return False
                    if payload.get('user')!=self.principal:continue
                    if action in ('account_disable','account_enable','password_reset','account_set','account_remove'):
                        return False
                    if row['tenant_id']!=self.tenant:continue
                    if action=='member_remove' or action=='member_set' and payload.get('role') not in ('member','admin'):
                        return False
                    if (str(payload.get('project_id'))==str(self.project_id) and
                            (action=='project_revoke' or action=='project_grant' and payload.get('role') not in ('manager','contributor'))):
                        return False
                return True
        except (ApiError,OSError,ValueError,TypeError,KeyError):
            return False


def capture(P, principal, project):
    ctx=getattr(P,'tenant_context',None)
    if ctx is None:
        raise ValueError('项目执行需要租户个人身份')
    reg=ctx.registry
    with reg.authorization_guard():
        who=tenant_policy.identity(P,principal)
        if who.get('tool_connection') or who['role'] not in ('member','admin'):
            raise ValueError('项目执行需要当前个人账号')
        tenant_policy.require_member(P,principal,project,'contributor')
        project=P.store.project(project['id'])
        if not project_git.available(P,project,principal) or not ctx.workspace_allowed(project['root']):
            raise ValueError('此项目尚未配置可用的隔离执行环境')
        account=reg.one('SELECT active,epoch FROM accounts WHERE name=?',(principal,))
        settings=project_git.settings(P)
        if not account or not account['active'] or not isinstance(account['epoch'],str) or not account['epoch']:
            raise ValueError('个人账号当前不可用')
        return Authority(P,principal,ctx.tenant_id,project['id'],project['key'],project['root'],
                         settings['image'],account['epoch'],who['authz_revision'])
