"""Explicit registered-ID broker wiring; no production route or OS launcher.

Captures the real ordinary prompt factory, then dispatches approved fixture
plans through the ORIGINAL root/provider budget. It never executes model tools,
commands or oracles. An isolation result cannot be manufactured from HTTP success.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

from scripts.rsi import provider_adapter as P
from scripts.rsi import trial_preparation as L
from tmh.platform import agents, learn, learning, lesson_input

VERSION = 'registered-trial-v1'
GAPS = ['native Messages has no production CLI tools or implicit session',
        'source/authorization is a capture, not a future execution grant',
        'provider response model is not independent weights attestation',
        'isolated candidate and independent oracle evaluator not yet connected']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def detached(value):
    return json.loads(L.encoded(value))


CODE_PATH=Path(__file__).resolve()
CODE_SHA256=sha(CODE_PATH.read_bytes())


def code_current():
    if sha(CODE_PATH.read_bytes())!=CODE_SHA256:raise L.Conflict("registered broker code changed")


def capture(store, project, ticket, *, tenant_id, mode='analyze', history=None, question='', target=''):
    """Invoke the ORIGINAL factory once, preserving its ordinary read/usage IO.

    Only call in an authorized server context. This is NOT a dry run, and does
    not invent authorization, human adoption, selectors or renderer semantics.
    """
    code_current()
    L.text(tenant_id)
    if history is None:history=[]
    if not isinstance(history,list) or any(not isinstance(m,dict) or not isinstance(m.get('role'),str) or not isinstance(m.get('body'),str) for m in history):
        raise ValueError('complete typed production history required')
    history = detached(history)
    if not isinstance(mode,str) or mode not in agents.MODE_TEXT or not isinstance(question,str) or not isinstance(target,str):
        raise ValueError('supported production prompt arguments required')
    with store.lock:
        if store.db.in_transaction:
            raise L.Conflict('capture cannot commit an existing transaction')
        current = store.project(project['id'])
        if current != project or ticket and ticket.get('project_id') != project['id']:
            raise L.Conflict('project or ticket scope mismatch')
        if ticket and ticket.get('id') and store.ticket(ticket['id']) != ticket:
            raise L.Conflict('ticket snapshot changed')
        context = SimpleNamespace(store=store,data_dir=store.path.parent)
        before = learning.binding(context,project)
        pool_before = learn.lesson_selection_pool(store.path.parent,project['key'],root=Path(project['root']))
        previous = getattr(agents._CTX_META,'meta',None)
        try:
            agents.reset_context_meta()
            prompt = agents.build_prompt(store,project,ticket,mode,target,question,history)
            metadata = detached(agents.take_context_meta())
        finally:
            if previous is None:
                try:del agents._CTX_META.meta
                except AttributeError:pass
            else:agents._CTX_META.meta=previous
        code_current()
        after = learning.binding(context,project)
        if before != after:
            raise L.Conflict('project/reference binding changed during capture')
        pool_after = learn.lesson_selection_pool(store.path.parent,project['key'],root=Path(project['root']))
    value={'schema':VERSION,'scope':{'tenant_id':tenant_id,'project_id':project['id']},
           'source':{'binding':before,'project':detached(project),'ticket':detached(ticket),
                     'history':history,'effective_history':history[-6:], 'mode':mode,'target':target,'question':question,
                     'pool_before':pool_before,'pool_after':pool_after,'context':metadata,
                     'selector':lesson_input.SELECTOR_VERSION,'renderer':lesson_input.RENDERER_VERSION,
                     'factory_sha256':sha(Path(agents.__file__).read_bytes()),'capture_code_sha256':CODE_SHA256,
                     'lesson_input_sha256':sha(Path(lesson_input.__file__).read_bytes())},
           'prompt':prompt,'prompt_sha256':sha(prompt.encode()),
           'production_factory_used':True,'production_equivalent':False,'equivalence_gaps':list(GAPS)}
    return detached(dict(value,capture_sha256=L.digest(value)))


def validate_capture(value):
    L.fields(value,{'schema','scope','source','prompt','prompt_sha256','capture_sha256','production_factory_used','production_equivalent','equivalence_gaps'})
    if (value['schema']!=VERSION or value['production_factory_used'] is not True or value['production_equivalent'] is not False
            or value['equivalence_gaps']!=GAPS or not isinstance(value['prompt'],str)
            or value['prompt_sha256']!=sha(value['prompt'].encode())
            or value['capture_sha256']!=L.digest({k:v for k,v in value.items() if k!='capture_sha256'})):
        raise L.Conflict('unverifiable original capture')
    L.fields(value['scope'],{'tenant_id','project_id'});L.text(value['scope']['tenant_id']);L.integer(value['scope']['project_id'],1)
    return detached(value)


def effective(value, policy):
    """Separate policy from the exact captured common text; never replace quotes."""
    value=validate_capture(value)
    if not isinstance(policy,str):raise ValueError('literal policy required')
    return {'system':policy,'messages':[{'role':'user','content':value['prompt']}],
            'common_sha256':value['capture_sha256'],'policy_sha256':sha(policy.encode()),
            'tools':[],'session':'fresh-native-messages','production_equivalent':False,'equivalence_gaps':list(GAPS)}


def assert_pair(baseline,candidate):
    """Only system/policy digest may differ; every other effective field identical."""
    for item in [baseline,candidate]:
        L.fields(item,{'system','messages','common_sha256','policy_sha256','tools','session','production_equivalent','equivalence_gaps'})
        if (not isinstance(item['system'],str) or item['policy_sha256']!=sha(item['system'].encode())
                or item['tools']!=[] or item['session']!='fresh-native-messages' or item['production_equivalent'] is not False
                or item['equivalence_gaps']!=list(GAPS)):
            raise L.Conflict('policy binding mismatch')
    remove={'system','policy_sha256'}
    if {k:v for k,v in baseline.items() if k not in remove}!={k:v for k,v in candidate.items() if k not in remove}:
        raise L.Conflict('pair differs outside permitted policy')
    return True


class Catalog:
    """Server-owned private IDs. Admission writes are never exposed as a route."""
    def __init__(self,path,*,trusted_uid=0):
        self.files=P.Registry(path,trusted_uid=trusted_uid,allow_test_loopback=True)

    def close(self):self.files.close()

    def _name(self,kind,id):return kind+'-'+P.opaque(id)

    def admit(self,kind,id,value):
        if kind not in {'input','plan'}:raise ValueError('fixed registry kind required')
        raw=L.encoded(value).encode();name=self._name(kind,id);temporary='.admission-'+uuid.uuid4().hex
        os.mkdir(temporary,mode=0o700,dir_fd=self.files.fd)
        folder=os.open(temporary,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.files.fd)
        try:
            fd=os.open('record.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=folder)
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.fsync(folder)
            # Every published directory is nonempty: competing admissions cannot
            # replace it. Readers see the whole record or no admitted directory.
            os.rename(temporary,name,src_dir_fd=self.files.fd,dst_dir_fd=self.files.fd)
            os.fsync(self.files.fd)
        finally:
            os.close(folder)
            try:
                os.unlink(temporary+'/record.json',dir_fd=self.files.fd)
                os.rmdir(temporary,dir_fd=self.files.fd)
            except FileNotFoundError:pass
        return sha(raw)

    def identity(self,kind,id):
        if kind not in {'input','plan'}:raise ValueError('fixed registry kind required')
        current,held=os.lstat(self.files.path),os.fstat(self.files.fd)
        if (current.st_dev,current.st_ino)!=(held.st_dev,held.st_ino):raise L.Conflict('catalog was replaced')
        P._private(current,self.files.uid,directory=True)
        folder=os.open(self._name(kind,id),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.files.fd)
        try:
            parent=os.fstat(folder);P._private(parent,self.files.uid,directory=True)
            fd=os.open('record.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=folder)
            try:st=os.fstat(fd);P._private(st,self.files.uid)
            finally:os.close(fd)
            return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns,
                    parent.st_dev,parent.st_ino,parent.st_mtime_ns,parent.st_ctime_ns)
        finally:os.close(folder)

    def load(self,kind,id):
        before=self.identity(kind,id)
        raw,_=self.files._read('record.json',directory=self._name(kind,id))
        if before!=self.identity(kind,id):raise L.Conflict('catalog entry changed during read')
        return P.strict_json(raw),sha(raw),before


class Broker:
    def __init__(self,adapter,catalog):self.adapter,self.catalog=adapter,catalog

    def _profile(self,contract):
        if contract['schema']!=L.PROVIDER_VERSION:
            raise L.Conflict('legacy fixture broker requires its original v2 root')
        profile=self.adapter.registry.load(contract['provider_binding']['profile_id'])['profile']
        if profile['mode']!='fixture' or not self.adapter.registry.fixture:
            raise L.Conflict('isolation admission incomplete; live dispatch disabled')
        return profile

    def dispatch(self,plan_id,input_id,*,cancel_event=None):
        code_current()
        plan,plan_hash,plan_identity=self.catalog.load('plan',plan_id)
        L.fields(plan,{'schema','kind','input_id','input_sha256','root_pool','contract_sha256','request_id','phase','policy','policy_sha256','broker_sha256'})
        if plan['schema']!=VERSION or plan['kind']!='fixture-provider-only' or plan['input_id']!=input_id:
            raise L.Conflict('registered plan/input mismatch or unsupported execution kind')
        if plan['broker_sha256']!=CODE_SHA256:raise L.Conflict('plan binds another broker version')
        value,input_hash,input_identity=self.catalog.load('input',input_id)
        if input_hash!=L.sha(plan['input_sha256']):raise L.Conflict('registered input changed')
        value=validate_capture(value)
        snap=self.adapter.ledger.snapshot(L.sha(plan['root_pool']))
        contract=snap['contract']
        if (L.digest(contract)!=L.sha(plan['contract_sha256']) or value['scope']!={'tenant_id':contract['tenant_id'],'project_id':contract['project_id']}):
            raise L.Conflict('registered root contract or tenant/project differs')
        # No real paid profile can be enabled by this preliminary broker.
        profile=self._profile(contract)
        packet=effective(value,plan['policy'])
        if packet['policy_sha256']!=L.sha(plan['policy_sha256']):raise L.Conflict('policy changed')
        request=P.opaque(plan['request_id'])
        if plan['phase'] not in L.PHASES:raise ValueError('fixed root phase required')
        binding={'request_id':request,'plan_id':plan_id,'plan_sha256':plan_hash,'input_id':input_id,'input_sha256':input_hash}
        # An input/provenance change with byte-identical prompt must not relabel
        # an older provider receipt. Root events do not alter attempt state.
        with learning.transaction(self.adapter.ledger.store) as db:
            self.adapter.ledger._pool(db,plan['root_pool'])
            anchors=[]
            for event in db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='registered_plan'",(plan['root_pool'],)):
                original=P.strict_json(event['payload'])
                if L.digest(original)!=event['payload_hash']:raise L.Conflict('corrupt registered plan anchor')
                if original.get('request_id')==request:anchors.append(original)
            if anchors:
                if anchors!=[binding]:raise L.Conflict('request cannot be rebound to another registered provenance')
            else:
                if db.execute('SELECT 1 FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(plan['root_pool'],request)).fetchone():
                    raise L.Conflict('historical attempt has no original registered provenance')
                self.adapter.ledger._event(db,plan['root_pool'],'','registered_plan',binding)
        outer=self
        class Cancel:
            def is_set(self):
                if cancel_event is not None and cancel_event.is_set():return True
                try:
                    code_current()
                    return (outer.catalog.identity('plan',plan_id),outer.catalog.identity('input',input_id))!=(plan_identity,input_identity)
                except (OSError,ValueError,KeyError,TypeError):return True
        result=self.adapter.dispatch(plan['root_pool'],request,plan['phase'],system=packet['system'],messages=packet['messages'],cancel_event=Cancel())
        return dict(result,plan_id=plan_id,input_id=input_id,plan_sha256=plan_hash,input_sha256=input_hash,
                    common_sha256=packet['common_sha256'],policy_sha256=packet['policy_sha256'],
                    root_pool=plan['root_pool'],request_id=request,isolated_execution='not_run',oracle_evaluation='not_run',
                    production_equivalent=False,rsi_qualified=False)
