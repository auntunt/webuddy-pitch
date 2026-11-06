"""Interactive human actions. Password/session stay in this process, outside MCP."""
import getpass
import http.client
from http.cookies import SimpleCookie
import json
import os
import re
import sys
import uuid
from urllib.parse import urlencode, urlsplit
from .workbench_client import ClientError
from . import workbench_credentials as credentials


class HumanClient:
    def __init__(self, endpoint):
        normalized, _ = credentials.endpoint(endpoint)
        self.address = urlsplit(normalized)
        self.origin = self.address.scheme + '://' + self.address.netloc
        self.prefix = self.address.path.rstrip('/')
        self.cookie = ''

    def request(self, method, path, body=None, *, login=False):
        headers = {'Origin':self.origin,'X-TMH':'1'}
        if self.cookie:
            headers['Cookie'] = self.cookie
        data = None
        if body is not None:
            data = urlencode(body).encode() if login else json.dumps(body,ensure_ascii=False).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if login else 'application/json'
        cls = http.client.HTTPSConnection if self.address.scheme == 'https' else http.client.HTTPConnection
        conn = cls(self.address.hostname,self.address.port,timeout=20)
        try:
            conn.request(method,path if login else self.prefix+path,data,headers)
            response=conn.getresponse()
            raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:
                raise ClientError('响应过大，未返回不完整内容','response_too_large')
            if login:
                if response.status != 303:
                    raise ClientError('登录失败，请核对个人账号或登录限制','human_login_failed',response.status)
                cookie=SimpleCookie()
                for name,value in response.getheaders():
                    if name.lower()=='set-cookie':cookie.load(value)
                if 'tmh_session' not in cookie:
                    raise ClientError('未取得个人会话','human_login_failed')
                self.cookie='tmh_session='+cookie['tmh_session'].value
                return None
            try:value=json.loads(raw)
            except ValueError as exc:raise ClientError('响应不是JSON，请检查登录和地址','invalid_response',response.status) from exc
            if not isinstance(value,dict):
                raise ClientError('响应格式不正确，请读取任务核对操作结果','invalid_response',response.status)
            if response.status>=300:
                raise ClientError(value.get('error','请求失败'),'human_request_failed',response.status)
            return value
        finally:conn.close()


def _mutation(client, path, body):
    body=dict(body,request_id=uuid.uuid4().hex)
    print('本次请求编号：'+body['request_id'],flush=True)
    try:
        return client.request('POST',path,body)
    except (OSError,http.client.HTTPException) as exc:
        raise ClientError('请求结果未确认；请读取任务及请求 '+body['request_id']+' 的回执，不能换编号重复提交','result_uncertain') from exc


def run(args):
    if not sys.stdin.isatty():
        raise ClientError('请开发人员本人在交互终端运行；不接受管道或Agent传入确认答案','human_terminal_required')
    key = args.project if args.command == 'ci-config' else args.ticket
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise ClientError('项目或任务编号不正确', 'invalid_key')
    endpoint=args.endpoint or os.environ.get('WEBUDDY_URL') or credentials.site_endpoint()
    if not endpoint and credentials.default_file():endpoint=credentials.load(credentials.default_file())['endpoint']
    if not endpoint:raise ClientError('请使用--endpoint指定工作台租户地址','endpoint_required')
    client=HumanClient(endpoint)
    username=args.user or input('Webuddy个人账号：').strip()
    client.request('POST','/login',{'username':username,'password':getpass.getpass('密码（不保存）：'),'next':client.prefix+'/'},login=True)
    if args.command=='ci-config':
        path='/api/projects/'+args.project+'/ci'
        old=client.request('GET',path)
        value={'repository':args.repository,'required_checks':args.required_check}
        if args.provider or args.connection:
            value.update(provider=args.provider,connection=args.connection)
        print(json.dumps(value,ensure_ascii=False,indent=2))
        if input('输入 SAVE '+args.project+' 保存必需CI配置：').strip()!='SAVE '+args.project:
            return 0
        result=client.request('POST',path,{'revision':old['revision'],'config':value})
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    ticket=args.ticket
    path='/api/tickets/'+ticket+'/development'
    state=client.request('GET',path)
    if args.action=='status':
        print(json.dumps(state,ensure_ascii=False,indent=2));return 0
    if args.action=='ask':
        for question in state.get('pending_questions',[]):
            print('\n'+question['question'])
            for index,choice in enumerate(question['options'],1):print(str(index)+'. '+choice)
            raw=input('选择序号或直接回答；? 表示尚不清楚，回车暂不回答：').strip()
            if not raw:continue
            answer=question['options'][int(raw)-1] if raw.isdecimal() and 1<=int(raw)<=len(question['options']) else raw
            state=_mutation(client,path,{'action':'answer','ticket':ticket,'revision':state['revision'],
                'answers':[{'question_id':question['id'],'answer':answer,'resolved':raw!='?'}]})
        print(json.dumps(state,ensure_ascii=False,indent=2));return 0
    if args.action=='execution':
        print(json.dumps(state,ensure_ascii=False,indent=2))
        if state['state']!='confirmed':
            raise ClientError('请先完成当前方案的人工确认','not_ready')
        mode=args.mode or input('执行方式（system交给系统 / local在当前开发工具执行）：').strip()
        if mode not in ('system','local'):
            raise ClientError('请选择system或local','invalid_mode')
        phrase='EXECUTE '+ticket+' '+mode+' '+state['digest'][:12]
        if input('只记录交接、不会开始开发。输入 '+phrase+'：').strip()!=phrase:return 0
        result=_mutation(client,path,{'action':'execution','ticket':ticket,'revision':state['revision'],'digest':state['digest'],'mode':mode})
    elif args.action=='confirm':
        print(json.dumps(state,ensure_ascii=False,indent=2))
        if state['state']!='awaiting_confirmation':
            raise ClientError('请先完成当前问题并更新确认稿；当前状态：'+state['state'],'not_ready')
        phrase='CONFIRM '+ticket+' '+state['digest'][:12]
        if input('确认需求、设计和测试方案后输入 '+phrase+'：').strip()!=phrase:return 0
        result=_mutation(client,path,{'action':'confirm','ticket':ticket,'revision':state['revision'],'digest':state['digest']})
    else:
        candidate=state.get('work',{}).get('candidate')
        if not candidate or candidate['id']!=args.candidate_id:
            raise ClientError('请选择当前任务的最新候选，不能确认其他版本','candidate_mismatch')
        print(json.dumps(state['work'],ensure_ascii=False,indent=2))
        if args.action=='assess':
            results=[]
            for criterion in candidate['criteria']:
                print('\n'+criterion['id']+' '+criterion['text']+'\n验证方式：'+criterion['check'])
                status=input('实际结果（pass/fail/unknown）：').strip()
                if status not in ('pass','fail','unknown'):
                    raise ClientError('结果必须为pass、fail或unknown，未提交本轮记录','invalid_result')
                evidence=input('实际操作、结果与证据引用：').strip()
                if not evidence:raise ClientError('需要实际证据；没有执行请记录unknown和原因','evidence_required')
                results.append({'id':criterion['id'],'status':status,'evidence':evidence})
            note=input('逐项复核说明：').strip()
            if not note:raise ClientError('需要复核说明','note_required')
            body={'action':'candidate_assess','ticket':ticket,'candidate_id':candidate['id'],
                  'verification_hash':candidate['verification_hash'],'preview_hash':candidate['preview_hash'],
                  'results':results,'note':note}
            print(json.dumps(body,ensure_ascii=False,indent=2))
        if args.action=='merge':
            ci=client.request('GET','/api/tickets/'+ticket+'/ci?candidate_id='+str(candidate['id']))
            print(json.dumps(ci,ensure_ascii=False,indent=2))
            if ci['state']!='pass':raise ClientError('必需CI未通过，不能合并','ci_not_passed')
        phrase=args.action.upper()+' '+ticket+' '+candidate['evidence_hash'][:12]
        if input('核对完整证据后输入 '+phrase+'：').strip()!=phrase:return 0
        if args.action!='assess':
            body={'action':'candidate_merge' if args.action=='merge' else 'review','ticket':ticket,
                  'candidate_id':candidate['id'],'evidence_hash':candidate['evidence_hash']}
        if args.action in ('review','reject'):
            note=input('复核依据：' if args.action=='review' else '退回原因和需要修改的内容：').strip()
            if not note:raise ClientError('需要记录复核依据或退回原因','note_required')
            body.update(decision='accept' if args.action=='review' else 'reject',note=note)
        result=_mutation(client,'/api/team',body)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0
