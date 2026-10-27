"""Partial, version-bound JB Vue syntax diagnostic; never a formal check."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time

from . import candidates, project_snapshot
from .project_authority import capture
from .project_container import Engine, specification
from .project_git import personal_scope
from .project_mcp import BoundJob

_lock = threading.Lock()
_LIMIT = 2 * 1024 * 1024
_SECONDS = 120
_SCRIPT = r'''
const fs=require('fs'),path=require('path');
const compiler=require('/opt/webuddy-vue/node_modules/@vue/compiler-sfc');
if(require('/opt/webuddy-vue/node_modules/@vue/compiler-sfc/package.json').version!=='3.5.13') throw Error('Vue compiler version mismatch');
const lock=fs.readFileSync('/workspace/jeecgboot-vue3/pnpm-lock.yaml','utf8');
const integrity='sha512-6VdaljMpD82w6c2749Zhf5T9u5uLBWKnVue6XWxprDobftnletJ8+oel7sexFfM3qIxNmVE7LSFGTpv6obNyaQ==';
if(!lock.includes(integrity)) throw Error('Vue compiler does not match the project lock file');
const base='/workspace/jeecgboot-vue3/src',bad=[],skipped=[];let files=0,templates=0;
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){
 const p=path.join(dir,e.name);if(e.isDirectory())walk(p);
 else if(e.isFile()&&p.endsWith('.vue')){files++;const name=path.relative(base,p);
  const o=compiler.parse(fs.readFileSync(p,'utf8'),{filename:name});
  if(o.errors.length){bad.push(name+' [组件]');continue;}
  if(o.descriptor.template){const t=o.descriptor.template;
   if(t.lang&&t.lang!=='html'){skipped.push(name+' [模板语言 '+t.lang+']');continue;}
   templates++;if(compiler.compileTemplate({source:t.content,filename:name,id:'check-'+files}).errors.length)bad.push(name+' [模板]');}
 }} }
walk(base);console.log(JSON.stringify({vue_files:files,templates_checked:templates,skipped,bad}));
'''


def run(P, row, actor):
    ticket=P.store.ticket(row['ticket_id'])
    project=P.store.project(ticket['project_id'])
    if project['key']!='JB':
        raise ValueError('此部分诊断仅支持已配置的 JB 项目')
    if not _lock.acquire(blocking=False):
        raise ValueError('部分诊断正在运行，请稍后重试')
    try:
        authority=capture(P,actor,project)
        engine=Engine()
        root=Path(project['root'])
        deadline=time.monotonic()+_SECONDS
        with tempfile.TemporaryDirectory(prefix='webuddy-vue-',dir=P.data_dir) as temp:
            workspace=Path(temp)/'source'
            job=BoundJob(actor,project['key'],workspace,authority.image)
            def stopped():
                return time.monotonic()>=deadline or not authority.current(job)
            def current():
                if stopped():return False
                with personal_scope(P,actor):
                    state=candidates.view(P,row['id'])
                return (state['current'] and
                        project_snapshot.current(authority.image,root,'HEAD',row['base_commit'],cancel=stopped,engine=engine) and
                        project_snapshot.current(authority.image,root,row['ref'],row['commit_sha'],cancel=stopped,engine=engine))
            if not current():raise ValueError('候选版本、需求或个人权限已变化')
            snap=project_snapshot.create(authority.image,root,workspace,ref=row['ref'],cancel=stopped,engine=engine)
            if snap['commit']!=row['commit_sha'] or stopped():raise ValueError('候选源码或个人权限已变化')
            out=bytearray()
            def collect(chunk):
                if len(out)+len(chunk)>_LIMIT:raise ValueError('诊断输出超过上限')
                out.extend(chunk)
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('部分诊断超时')
            receipt=engine.run(specification(authority.image,['node','-e',_SCRIPT],workspace,remaining),remaining,cancel=stopped,output=collect)
            if receipt.get('cleanup') is not True:raise ValueError('诊断容器未确认回收')
            if receipt.get('reason')!='exited' or receipt.get('returncode')!=0:raise ValueError('组件诊断未完成；请检查固定工具、项目锁文件或运行状态')
            try: result=json.loads(out.decode('utf-8'))
            except (ValueError,UnicodeError) as exc:raise ValueError('诊断结果不可读取') from exc
            if (not isinstance(result,dict) or set(result)!={'vue_files','templates_checked','skipped','bad'} or
                    type(result['vue_files']) is not int or type(result['templates_checked']) is not int or
                    result['vue_files']<1 or result['templates_checked']<0 or
                    not isinstance(result['skipped'],list) or not isinstance(result['bad'],list) or
                    any(not isinstance(s,str) for s in result['skipped']+result['bad'])):
                raise ValueError('诊断结果不完整')
            if not current():raise ValueError('诊断结束前候选版本、需求或个人权限已变化')
            return {'kind':'partial_vue_diagnostic','candidate_id':row['id'],'commit':row['commit_sha'],
                    'actor':actor,'scope':'Vue 组件与模板语法；不代表完整构建、类型检查或验收',**result}
    finally:
        _lock.release()
