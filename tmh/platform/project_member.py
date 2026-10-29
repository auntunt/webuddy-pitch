"""Connect a personally authorized project proposal to the ordinary run record.

This entry is not a grant or an approval. A generated candidate remains
subject to the existing verification, preview and human acceptance gates.
"""
from __future__ import annotations

import codecs
from pathlib import Path

from . import candidates, filelock, project_job, project_snapshot, team
from .agent_api import _requirement
from .agents import StreamParser, learning_context_current, record_session_context, member_route_binding
from .project_mcp import BoundJob
from .project_library import run_current
from .store import now


def execute(runner, rid, project, ticket, prompt, authority, image, binding):
    from .project_git import personal_scope
    with personal_scope(authority.platform,authority.principal):
        return _execute(runner,rid,project,ticket,prompt,authority,image,binding)


def _execute(runner, rid, project, ticket, prompt, authority, image, binding):
    st=runner.store
    if not ticket:
        raise ValueError('隔离执行必须绑定工单')
    current=st.ticket(ticket['id'])
    initial_requirement=binding['requirement_hash']
    if _requirement(current,st)!=initial_requirement:
        raise ValueError('工单需求在运行前已变化，请重新启动')
    folder=runner.data_dir/'runs'/str(rid)
    folder.mkdir(parents=True,exist_ok=True)
    record_session_context(runner.data_dir,rid)
    if not learning_context_current(st,runner.data_dir,project,st.run(rid),running=True):
        raise ValueError('任务知识或授权已变化，请重新启动')
    ref=binding['source_ref']
    base_commit=binding['base_commit']
    workspace=folder/'member-job'/'workspace'
    job=BoundJob(authority.principal,project['key'],workspace,image)
    def stopped():
        return bool(runner.stop_reason(rid)) or not authority.current(job)
    def current_source(commit):
        latest=st.ticket(ticket['id'])
        links=(latest or {}).get('links') or {}
        assignment={k:v for k,v in team.assignment(authority.platform,latest).items()
                    if k in ('assignee','reviewer','revision')} if latest else None
        try:
            route_current = member_route_binding(runner.data_dir, project, binding['agent']) == binding['route_binding']
            from .project_client import provider_binding
            _, _, provider = provider_binding(Path.home()/'.codex'/'config.toml', binding['profile'], binding['model'])
            provider_current = provider == binding['provider_binding']
        except (OSError, ValueError, KeyError, TypeError):
            return False
        if (stopped() or not latest or _requirement(latest,st)!=initial_requirement or
                latest['status']=='closed' or links.get('delivery') or links.get('later') or not links.get('hold') or
                not route_current or not provider_current or assignment!=binding.get('assignment') or candidates.configuration(authority.platform,project)!=binding.get('configuration_hash') or
                not run_current(st,project,rid) or
                not learning_context_current(st,runner.data_dir,project,st.run(rid),running=True)):
            return False
        return project_snapshot.current(image,Path(project['root']),ref,commit,cancel=stopped)
    content=(prompt+
        '\n\n项目执行约束：原任务中记载的项目路径对应 /workspace；/workspace 是已提交版本的隔离副本；平台 .tmh 不在副本内。'
        '任务及已引用知识以本提示词为准，所有项目命令使用 project_exec，其 project 参数必须为 '
        + project['key'] + '。本次只生成候选，不自动进行业务验收、合并或部署。\n')
    decoder=codecs.getincrementaldecoder('utf-8')('replace')
    parser=StreamParser('codex');pending=''
    def output(chunk):
        nonlocal pending
        pending+=decoder.decode(chunk)
        while '\n' in pending:
            line,pending=pending.split('\n',1)
            text=parser.feed(line+'\n')
            if text:st.append_output(rid,text)
    lock_path=runner.data_dir/'member-execution.lock'
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a+b') as lock:
        try:filelock.try_lock(lock)
        except BlockingIOError as exc:raise ValueError('项目隔离执行资源正忙，请稍后重试') from exc
        try:
            if stopped():raise ValueError('个人授权已失效，未启动任务')
            st.update_run(rid,status='running',started=now(),workdir=str(workspace))
            result=project_job.run(principal=authority.principal,project=project['key'],source=Path(project['root']),
                image=image,provider_config=Path.home()/'.codex'/'config.toml',prompt=content,
                folder=folder/'member-job',seconds=runner.remaining(rid),authorize=authority.current,
                profile=binding['profile'],model=binding['model'],expected_binding=binding['provider_binding'],
                source_current=current_source,ref=base_commit,cancel=lambda:bool(runner.stop_reason(rid)),output=output)
            if stopped():raise ValueError('执行期间个人授权已变化，结果仅保留供核对')
            patch=(Path(result['candidate']['artifact_dir'])/'change.patch').read_bytes().decode('utf-8','strict')
            answer=parser.final().strip()
            deleted=result['candidate'].get('deleted_files',[])
            if not isinstance(deleted,list) or any(not isinstance(name,str) for name in deleted):
                raise ValueError('候选删除文件清单不完整')
            deletions=('\n\n完整删除文件清单：\n'+'\n'.join('- '+name for name in deleted)+'\n') if deleted else ''
            from .project_candidates import register
            summary=(answer+'\n\n' if answer else '')+deletions+'已登记固定版本候选；尚未独立验证、预览或业务验收。'
            cid=register(authority.platform,rid,authority,job,binding,result,summary,current_source)
            if cid is None:
                summary=(answer+'\n\n' if answer else '')+deletions+'已生成固定版本提案；缺少可用的已确认验收条件或候选已存在，尚未登记、验证、预览或业务验收。'
                with authority.platform.tenant_context.registry.authorization_guard():
                    if not current_source(base_commit) or not authority.current(job):
                        raise ValueError('写回前个人授权、工单或来源已变化，结果仅保留供核对')
                    with runner.lock:
                        if stopped() or st.run(rid)['status']=='cancelled':
                            raise ValueError('登记前个人授权或运行状态已变化，结果仅保留供核对')
                        st.update_run(rid,status='done',ended=now(),exit_code=0,result=summary,diff=patch)
            runner._finish_event(ticket,rid,st.run(rid)['agent'],'fix','done',summary,bool(patch))
            if cid is not None:
                from .static_preview import auto_verify
                auto_verify(authority.platform, authority.principal, cid)
        finally:
            filelock.unlock(lock)
