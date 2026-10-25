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
from contextlib import contextmanager, nullcontext
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


def native_effective(value, policy, protocol):
    """Use the captured original selector/renderer once; never reselect per arm."""
    if protocol not in P.TOKEN_PROTOCOLS:
        raise ValueError('explicit native text protocol required')
    value=validate_capture(value)
    source=value['source']
    if (source.get('selector')!=lesson_input.SELECTOR_VERSION or source.get('renderer')!=lesson_input.RENDERER_VERSION
            or source.get('lesson_input_sha256')!=sha(Path(lesson_input.__file__).read_bytes())
            or source.get('capture_code_sha256')!=CODE_SHA256
            or source.get('factory_sha256')!=sha(Path(agents.__file__).read_bytes())):
        raise L.Conflict('capture binds another production factory/lesson implementation')
    packet=effective(value,policy)
    packet.update(protocol=protocol,session='fresh-native-'+protocol,
                  equivalence_gaps=['native fixed text has no production CLI tools or implicit session',*GAPS[1:]])
    return packet


def native_pair(value, baseline_policy, candidate_policy, protocol):
    """An exact common capture, with only policy permitted to differ."""
    baseline=native_effective(value,baseline_policy,protocol)
    candidate=native_effective(value,candidate_policy,protocol)
    except_policy={'system','policy_sha256'}
    if {k:v for k,v in baseline.items() if k not in except_policy}!={k:v for k,v in candidate.items() if k not in except_policy}:
        raise L.Conflict('native pair differs outside the frozen policy')
    return {'baseline':baseline,'candidate':candidate,'common_sha256':value['capture_sha256'],
            'production_equivalent':False,'rsi_qualified':False}


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
    KIND='fixture-provider-only'
    PLAN_FIELDS={'schema','kind','input_id','input_sha256','root_pool','contract_sha256','request_id','phase','policy','policy_sha256','broker_sha256'}
    def __init__(self,adapter,catalog):self.adapter,self.catalog=adapter,catalog

    def _profile(self,contract):
        if contract['schema']!=L.PROVIDER_VERSION:
            raise L.Conflict('legacy fixture broker requires its original v2 root')
        profile=self.adapter.registry.load(contract['provider_binding']['profile_id'])['profile']
        if profile['mode']!='fixture' or not self.adapter.registry.fixture:
            raise L.Conflict('isolation admission incomplete; live dispatch disabled')
        return profile

    def _packet(self,value,policy,profile):return effective(value,policy)
    def _fields(self,plan):return self.PLAN_FIELDS
    def _prepare(self,plan,value,contract,input_hash,profile):return None
    def _before_plan(self,db,plan,contract,input_hash,prepared):pass
    def _current(self,prepared,contract,profile):return True
    def _admission(self,prepared,contract,profile):return None
    def _extra(self,prepared):return {}

    def dispatch(self,plan_id,input_id,*,cancel_event=None):
        code_current()
        plan,plan_hash,plan_identity=self.catalog.load('plan',plan_id)
        L.fields(plan,self._fields(plan))
        if plan['schema']!=VERSION or plan['kind']!=self.KIND or plan['input_id']!=input_id:
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
        prepared=self._prepare(plan,value,contract,input_hash,profile)
        packet=self._packet(value,plan['policy'],profile)
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
                self._before_plan(db,plan,contract,input_hash,prepared)
                self.adapter.ledger._event(db,plan['root_pool'],'','registered_plan',binding)
        outer=self
        class Cancel:
            def is_set(self):
                if cancel_event is not None and cancel_event.is_set():return True
                try:
                    code_current()
                    return ((outer.catalog.identity('plan',plan_id),outer.catalog.identity('input',input_id))!=(plan_identity,input_identity)
                            or not outer._current(prepared,contract,profile))
                except (OSError,ValueError,KeyError,TypeError):return True
        kwargs={'system':packet['system'],'messages':packet['messages'],'cancel_event':Cancel()}
        admission=self._admission(prepared,contract,profile)
        if admission is not None:kwargs['dispatch_guard']=admission
        result=self.adapter.dispatch(plan['root_pool'],request,plan['phase'],**kwargs)
        return dict(result,plan_id=plan_id,input_id=input_id,plan_sha256=plan_hash,input_sha256=input_hash,
                    common_sha256=packet['common_sha256'],policy_sha256=packet['policy_sha256'],
                    root_pool=plan['root_pool'],request_id=request,isolated_execution='not_run',oracle_evaluation='not_run',
                    production_equivalent=False,rsi_qualified=False,**self._extra(prepared))


class TokenBroker(Broker):
    """Distinct private token entry; no external route or delegated tool grant."""
    KIND='native-fixed-text-token-v1'
    PLAN_FIELDS=Broker.PLAN_FIELDS|{'source_family'}

    def __init__(self,adapter,catalog,*,context=None,actor=''):
        super().__init__(adapter,catalog)
        self.context,self.actor=context,actor

    def _authority(self,contract,profile):
        if self.context is None:
            if profile['mode']=='fixture' and self.adapter.registry.fixture:
                return {'fixture_scope_only':True}
            raise L.Conflict('live token entry requires current server-side tenant authority')
        from tmh.platform import tenant_policy as TP
        context=self.context
        if context.store.path.resolve()!=self.adapter.ledger.store.path.resolve():
            raise L.Conflict('one authoritative Store required')
        with TP.experiment_guard(context,self.actor,contract['project_id'],'manager') as who:
            project=context.store.project(contract['project_id'])
            if not project:raise L.Conflict('current project unavailable')
            TP.require_execution(context,self.actor)
            if who['tenant_id']!=contract['tenant_id']:
                raise L.Conflict('current tenant differs from original root')
            return {'identity':detached(who),'project':detached(project),'binding':learning.binding(context,project)}

    def _profile(self,contract):
        if contract['schema']!=L.TOKEN_PROVIDER_VERSION:
            raise L.Conflict('explicit token provider root required')
        profile=self.adapter.registry.load(contract['provider_binding']['profile_id'])['profile']
        if profile['schema']!=P.TOKEN_VERSION:
            raise L.Conflict('explicit token profile required')
        self._authority(contract,profile)
        return profile

    def _packet(self,value,policy,profile):return native_effective(value,policy,profile['protocol'])

    def _fields(self,plan):
        return self.PLAN_FIELDS|({'adoption'} if isinstance(plan,dict) and plan.get('phase')=='followup' else set())

    def _capture_current(self,value):
        from tmh.platform import lesson_context
        store=self.adapter.ledger.store;project=value['source']['project']
        if store.project(project['id'])!=project:
            raise L.Conflict('captured project is no longer current')
        ticket=value['source']['ticket']
        if ticket is not None and store.ticket(ticket['id'])!=ticket:
            raise L.Conflict('captured task is no longer current')
        for meta in value['source']['context']:
            if meta.get('mode')=='learning_lessons':
                block=meta.get('block')
                if not lesson_context.current(store,project,block) or block['text'] not in value['prompt']:
                    raise L.Conflict('frozen lesson block changed or was revoked')

    def _followup(self,plan,value,contract,input_hash,profile,*,check_arms=True):
        """Read existing human adoption and original selected use, never apply it.

        This proves ordinary adopted use only. The prior human report is not
        yet a qualified BC report for this native root: do not give RSI credit.
        """
        if self.context is None:
            raise L.Conflict('new D requires a current server-side human adoption context')
        if profile['mode']!='fixture':
            raise L.Conflict('live D requires a qualified native BC report-to-decision binding; not enabled')
        from tmh.platform import learning_decisions as D, learning_runs, signoff, tenant_policy as TP
        admission=plan['adoption']
        L.fields(admission,{'decision_id','revision_id','job_id','report_sha256'})
        for field in ('decision_id','revision_id','job_id'):L.text(admission[field])
        L.sha(admission['report_sha256'])
        if plan['source_family']!=contract['followup_family'] or input_hash in {c['input_sha256'] for c in contract['holdout_cases']}:
            raise L.Conflict('new D is not from its distinct original family/input')
        ticket=value['source']['ticket']
        if not isinstance(ticket,dict) or type(ticket.get('id')) is not int:
            raise L.Conflict('new D requires a distinct actual ticket')
        store=self.adapter.ledger.store
        with TP.experiment_guard(self.context,self.actor,contract['project_id'],'manager'),store.lock,learn.ledger_lock(self.context.data_dir,create=False):
            project=store.project(contract['project_id'])
            row=store.one("SELECT * FROM learning_decisions WHERE id=? AND project_id=?",(admission['decision_id'],project['id']))
            if (not row or row['action']!='adopt' or row['status']!='applied' or row['kind']!='lesson'
                    or row['revision_id']!=admission['revision_id'] or not signoff.human(row['actor'])):
                raise L.Conflict('exact applied personal lesson decision required')
            latest=store.one("SELECT id FROM learning_decisions WHERE project_id=? AND kind='lesson' AND origin_id=? AND status='applied' ORDER BY rowid DESC LIMIT 1",(project['id'],row['origin_id']))
            revision=learning.revision(self.context,project,row['revision_id'])
            payload=P.strict_json(row['payload'])
            bound=self.adapter._verified_candidate(plan['root_pool'])
            if (not latest or latest['id']!=row['id'] or revision['kind']!='lesson'
                    or payload.get('content')!=revision['content'] or payload.get('source')!=revision['source']
                    or payload.get('request',{}).get('job_id')!=admission['job_id']
                    or P.strict_json(revision['content']).get('fix')!=bound['candidate_text']
                    or plan['policy']!=bound['candidate_text']
                    or not D.adopted_current(self.context,project,revision)):
                raise L.Conflict('human decision is stale or binds another complete policy')
            job=learning_runs.get(self.context,project,admission['job_id'])
            if (job['status']!='passed' or job['kind']!='evaluate' or job['current_revision_id']!=revision['id']
                    or job.get('result',{}).get('passed') is not True or L.digest(job['result'])!=admission['report_sha256']):
                raise L.Conflict('original adopted evaluation report differs')
            selected=False
            for meta in value['source']['context']:
                if meta.get('mode')!='learning_lessons':continue
                selected|=bool(any(r.get('kind')=='lesson' and r.get('origin_id')==revision['origin_id'] and r.get('revision_id')==revision['id'] and r.get('included') is True for r in meta.get('revisions',[]))
                              and any(p.get('scope')=='local' and p.get('origin_id')==revision['origin_id'] and p.get('content')==P.strict_json(revision['content']) for p in meta['block']['payloads']))
            if not selected:raise L.Conflict('new D did not select/render the exact adopted lesson')
            for event in store.q("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='registered_token_input'",(plan['root_pool'],)):
                old=P.strict_json(event['payload'])
                if L.digest(old)!=event['payload_hash']:raise L.Conflict('corrupt prior input identity')
                if old['ticket_id']==ticket['id'] and (old['request_id']!=plan['request_id'] or old['input_sha256']!=input_hash):
                    raise L.Conflict('new D cannot reuse an earlier task identity')
        if check_arms:
            with store.lock:
                slots=self._arm_slots(store.db,plan['root_pool'])
            for case in contract['holdout_cases']:
                for arm in ('baseline','candidate'):
                    request=slots.get((case['input_sha256'],arm))
                    if not request:raise L.Conflict('all presealed BC arms must finish before D')
                    result=self.adapter.reconcile(plan['root_pool'],request)
                    if result['state']!='settled' or not result['response_complete']:
                        raise L.Conflict('BC original response is unresolved')
        return {'decision_id':row['id'],'revision_id':revision['id'],'origin_id':revision['origin_id'],
                'job_id':job['id'],'report_sha256':admission['report_sha256'],'selected':True,
                'bc_report_relation_verified':False,'rsi_qualified':False}

    def _arm_slots(self,db,key):
        slots={}
        for event in db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='registered_token_arm'",(key,)):
            slot=P.strict_json(event['payload'])
            L.fields(slot,{'input_sha256','phase','request_id'})
            L.sha(slot['input_sha256']);P.opaque(slot['request_id'])
            identity=(slot['input_sha256'],slot['phase'])
            if (L.digest(slot)!=event['payload_hash'] or slot['phase'] not in {'baseline','candidate'} or identity in slots):
                raise L.Conflict('corrupt or duplicate original terminal slot')
            slots[identity]=slot['request_id']
        return slots

    def _prepare(self,plan,value,contract,input_hash,profile):
        authority=self._authority(contract,profile)
        self._capture_current(value)
        if self.context is not None and (value['source']['project']!=authority['project'] or value['source']['binding']!=authority['binding']):
            raise L.Conflict('capture no longer matches current authorized source')
        phase=plan['phase'];family=L.text(plan['source_family'])
        if phase in {'baseline','candidate'}:
            self.adapter._verified_candidate(plan['root_pool'])
            if not any(c=={'input_sha256':input_hash,'source_family':family} for c in contract['holdout_cases']):
                raise L.Conflict('arm input is outside original presealed cases')
        elif phase=='followup':
            adoption=self._followup(plan,value,contract,input_hash,profile)
        elif phase=='terminal':
            raise L.Conflict('native terminal work requires an explicit baseline/candidate arm')
        elif (family!=contract['training_family']
              or input_hash in {c['input_sha256'] for c in contract['holdout_cases']}):
            raise L.Conflict('proposal/judge/probe/retry material requires its frozen training scope')
        return {'authority':authority,'capture':value,'plan':plan,'input_sha256':input_hash,
                'adoption':adoption if phase=='followup' else None,'protocol':profile['protocol']}

    def _before_plan(self,db,plan,contract,input_hash,prepared):
        ticket=prepared['capture']['source']['ticket']
        self.adapter.ledger._event(db,plan['root_pool'],'','registered_token_input',{
            'request_id':plan['request_id'],'input_sha256':input_hash,'ticket_id':ticket.get('id') if isinstance(ticket,dict) else None})
        if prepared['adoption']:
            self.adapter.ledger._event(db,plan['root_pool'],'','registered_token_followup',prepared['adoption'])
        if plan['phase'] not in {'baseline','candidate'}:return
        value={'input_sha256':input_hash,'phase':plan['phase'],'request_id':plan['request_id']}
        if (input_hash,plan['phase']) in self._arm_slots(db,plan['root_pool']):
            raise L.Conflict('terminal input/arm already belongs to its original request')
        self.adapter.ledger._event(db,plan['root_pool'],'','registered_token_arm',value)

    def _current(self,prepared,contract,profile,*,allow_blocked_history=False):
        try:
            if self._authority(contract,profile)!=prepared['authority']:return False
            self._capture_current(prepared['capture'])
            if self.adapter.ledger.inspect(prepared['plan']['root_pool'])['blocked'] and not allow_blocked_history:return False
            if prepared['adoption'] and self._followup(prepared['plan'],prepared['capture'],contract,prepared['input_sha256'],profile,check_arms=False)!=prepared['adoption']:return False
            return True
        except Exception:return False

    @contextmanager
    def _admission(self,prepared,contract,profile):
        from tmh.platform import tenant_policy as TP
        guard=(TP.experiment_guard(self.context,self.actor,contract['project_id'],'manager')
               if self.context is not None else nullcontext())
        # Registry -> Store -> lesson ledger is the original lock order. Keep
        # current lesson validation and reserve/intent indivisible with respect
        # to a concurrent withdrawal; Adapter releases this before its child.
        with guard,self.adapter.ledger.store.lock,learn.ledger_lock(self.adapter.ledger.store.path.parent,create=False):
            old=self.adapter.ledger.store.one('SELECT state FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',
                                             (prepared['plan']['root_pool'],prepared['plan']['request_id']))
            history=bool(old and old['state'] in {'intent','settled','unknown','cancelled'})
            if not self._current(prepared,contract,profile,allow_blocked_history=history):
                raise L.Conflict('authority/source changed before original intent')
            yield

    def _extra(self,prepared):
        return {'native_protocol':prepared['protocol'],'human_adoption':({k:v for k,v in prepared['adoption'].items() if k!='report_sha256'} if prepared['adoption'] else None),
                'qualified_bc_report_verified':False}
