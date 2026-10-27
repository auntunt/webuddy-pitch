"""Scoped stdio MCP: one server-bound principal, project and staged workspace.

Host integration must provide fresh authorization and trustworthy workspace checks.
A staged workspace must contain no host sockets or secrets and must not be an
unfiltered shared project directory. No credentials or Docker socket are mounted.
"""
from __future__ import annotations
import base64
import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

@dataclass(frozen=True)
class BoundJob:
    principal: str
    project: str
    workspace: Path
    image_id: str

class ProjectMCP:
    MAX_SECONDS=30
    MAX_OUTPUT=2*1024*1024
    MAX_REQUEST=1024*1024
    MAX_CALLS=100
    def __init__(self, job: BoundJob, authorize: Callable, validate_workspace: Callable,
                 engine_factory=None, spec_factory=None, initialize=lambda: True, cancelled=lambda: False,
                 output_log=lambda chunk: None, record=lambda receipt: None, volume=None):
        if not job.principal or not job.project or not job.workspace.is_absolute():
            raise ValueError('A trusted principal, project and absolute workspace are required')
        if not callable(authorize) or not callable(validate_workspace):
            raise ValueError('Host authorization and workspace validators are required')
        if volume is None and engine_factory is None:
            raise ValueError('项目工具需要有硬容量限制的临时工作区')
        if engine_factory is None or spec_factory is None:
            from tmh.platform.project_container import Engine, specification
            engine_factory=engine_factory or Engine
            spec_factory=spec_factory or specification
        self.job=job;self.authorize=authorize;self.validate_workspace=validate_workspace
        self.engine_factory=engine_factory;self.spec_factory=spec_factory
        self.initialize=initialize;self.cancelled=cancelled;self.output_log=output_log;self.record=record;self.calls=0
        self.initialized=False
        self.volume=volume
        self.lock=threading.RLock();self.write_lock=threading.Lock();self.active={};self.out=None

    def _authorized(self):
        try:
            return (not self.cancelled() and (self.volume is None or self.volume.alive())
                    and self.authorize(self.job) is True and self.validate_workspace(self.job) is True)
        except Exception:
            return False

    def _emit(self, value):
        with self.write_lock:
            self.out.write(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
            self.out.flush()

    def _reply(self, ident, result):
        self._emit({'jsonrpc':'2.0','id':ident,'result':result})

    def _error(self, ident, code, message):
        self._emit({'jsonrpc':'2.0','id':ident,'error':{'code':code,'message':message}})

    def _result(self, ident, payload, error=False):
        self._reply(ident, {'content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)}], 'isError':error})

    @staticmethod
    def _valid_args(args):
        if not isinstance(args,dict) or set(args)-{'project','argv','timeout_seconds'}:
            return False
        argv=args.get('argv');timeout=args.get('timeout_seconds',10)
        return (isinstance(args.get('project'),str) and isinstance(argv,list) and 1<=len(argv)<=64
                and all(isinstance(x,str) and 0<len(x)<=4096 and '\x00' not in x for x in argv)
                and sum(map(len,argv))<=16384 and isinstance(timeout,(int,float))
                and not isinstance(timeout,bool) and math.isfinite(timeout) and 0.1<=timeout<=ProjectMCP.MAX_SECONDS)

    def _run(self, ident, args, cancel):
        buf=bytearray(); overflow=False; receipt={}
        try:
            if not self._authorized():
                return self._result(ident,{'status':'denied','message':'项目权限已失效或工作区未获准'},True)
            spec=(self.volume.spec(args['argv'],args.get('timeout_seconds',10)) if self.volume else
                  self.spec_factory(self.job.image_id,args['argv'],self.job.workspace,args.get('timeout_seconds',10),writable=True))
            hc=spec.get('HostConfig',{});mounts=hc.get('Mounts',[])
            expected=({'Type':'volume','Source':self.volume.name,'Target':'/workspace','ReadOnly':False}
                      if self.volume else {'Type':'bind','Source':str(self.job.workspace),'Target':'/workspace','ReadOnly':False})
            if (spec.get('NetworkDisabled') is not True or hc.get('NetworkMode')!='none'
                or mounts != [expected]):
                return self._result(ident,{'status':'denied','message':'容器配置不符合项目隔离要求'},True)
            if not self._authorized() or cancel.is_set():
                return self._result(ident,{'status':'cancelled','message':'权限已失效或请求已取消'},True)
            def output(chunk):
                nonlocal overflow
                self.output_log(chunk)
                if len(buf)+len(chunk)>self.MAX_OUTPUT:
                    overflow=True;raise ValueError('output limit')
                buf.extend(chunk)
            result=self.engine_factory().run(spec,args.get('timeout_seconds',10),
                cancel=lambda: cancel.is_set() or not self._authorized(),output=output,receipt=receipt)
            if not self._authorized():
                return self._result(ident,{'status':'denied','message':'项目权限已撤销，未返回任务输出','cleanup':result.get('cleanup') is True},True)
            if overflow:
                return self._result(ident,{'status':'error','message':'输出超过限制，未返回不完整内容','cleanup':result.get('cleanup') is True},True)
            if result.get('cleanup') is not True:
                return self._result(ident,{'status':'error','message':'任务清理未确认'},True)
            reason=result.get('reason','error');code=result.get('returncode',125)
            try: output_text=buf.decode('utf-8');encoding='utf-8'
            except UnicodeDecodeError: output_text=base64.b64encode(buf).decode('ascii');encoding='base64'
            return self._result(ident,{'status':reason,'exit_code':code,'output':output_text,'output_encoding':encoding,'cleanup':True},reason!='exited' or code!=0)
        except Exception:
            return self._result(ident,{'status':'error','message':'项目工具执行失败，未返回不完整输出','cleanup':receipt.get('cleanup') is True},True)
        finally:
            self.record(dict(receipt))
            with self.lock:self.active.pop(ident,None)

    def serve(self, inp, out):
        """Read newline JSON-RPC; lifecycle owner must close stdin on disconnect."""
        self.out=out;threads=[]
        try:
            while True:
                line=inp.readline(self.MAX_REQUEST+1)
                if not line: break
                if len(line)>self.MAX_REQUEST or not line.endswith('\n'):
                    self._error(None,-32600,'Request too large or incomplete');break
                try: msg=json.loads(line)
                except (ValueError,TypeError):
                    self._error(None,-32700,'Invalid JSON');continue
                if not isinstance(msg,dict):self._error(None,-32600,'Invalid request');continue
                method=msg.get('method');ident=msg.get('id');params=msg.get('params') or {}
                if method=='notifications/cancelled':
                    with self.lock:
                        cancel=self.active.get(params.get('requestId')) if isinstance(params,dict) else None
                        if cancel:cancel.set()
                    continue
                if ident is None:continue
                if isinstance(ident,bool) or not isinstance(ident,(str,int)) or not isinstance(params,dict):
                    self._error(None,-32600,'Invalid request');continue
                if method=='initialize':
                    if self.initialized or not self._authorized() or self.initialize() is not True:
                        self._error(ident,-32001,'Project context unavailable');continue
                    self.initialized=True
                    self._reply(ident,{'protocolVersion':params.get('protocolVersion','2024-11-05'),
                        'capabilities':{'tools':{}},'serverInfo':{'name':'project-executor','version':'0.1'}})
                elif not self.initialized:
                    self._error(ident,-32002,'Initialize project context first')
                elif method=='tools/list':
                    self._reply(ident,{'tools':[{'name':'project_exec','description':'Run a command inside the bound project workspace.',
                        'inputSchema':{'type':'object','properties':{'project':{'type':'string'},
                        'argv':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':64},
                        'timeout_seconds':{'type':'number','minimum':0.1,'maximum':self.MAX_SECONDS}},
                        'required':['project','argv'],'additionalProperties':False},
                        'annotations':{'readOnlyHint':False,'destructiveHint':True}}]})
                elif method=='tools/call':
                    args=params.get('arguments') if isinstance(params,dict) else None
                    if params.get('name')!='project_exec' or not self._valid_args(args):
                        self._error(ident,-32602,'Invalid tool or arguments');continue
                    if args['project']!=self.job.project:
                        self._result(ident,{'status':'denied','message':'请求项目与当前任务不一致'},True);continue
                    with self.lock:
                        if self.calls>=self.MAX_CALLS:
                            self._result(ident,{'status':'denied','message':'项目工具调用次数已达上限'},True);continue
                        if self.active:
                            self._result(ident,{'status':'busy','message':'当前项目任务正在运行'},True);continue
                        self.calls+=1
                        cancel=threading.Event();self.active[ident]=cancel
                    t=threading.Thread(target=self._run,args=(ident,args,cancel));threads.append(t);t.start()
                elif method=='ping':self._reply(ident,{})
                else:self._error(ident,-32601,'Method not found')
        finally:
            with self.lock:
                for event in self.active.values():event.set()
            for t in threads:t.join()
