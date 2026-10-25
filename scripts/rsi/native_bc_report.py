"""Pre-proposal assertion registration and supervised native BC proof.

Private trusted-server API only. No human decision, job fabrication, model call,
new budget or production route. A report is not an adoption or a D result.
"""
from __future__ import annotations
import hashlib
from contextlib import contextmanager, nullcontext
from pathlib import Path
import sys
import uuid

from scripts.rsi import registered_trial as R, trial_preparation as L, provider_adapter as A
from tmh.platform import learn, learning, learning_eval, supervised_process as SP

VERSION='native-bc-registration-v1'
WORKER=Path(__file__).with_name('native_bc_worker.py')
SOURCES=[Path(__file__),WORKER,R.CODE_PATH,Path(learning_eval.__file__),Path(learning.__file__),Path(SP.__file__),*A.SOURCES.values()]


def bundle():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}


class Reports:
    def __init__(self,broker,root):
        self.broker=broker;self.adapter=broker.adapter;self.ledger=self.adapter.ledger
        self.root=Path(root).absolute();self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        A._private(self.root.lstat(),__import__('os').getuid(),directory=True)
        self.code=bundle()

    def _code(self):
        if bundle()!=self.code:raise L.Conflict('native evaluator implementation changed')

    def _one(self,key,kind):
        rows=self.ledger.store.q('SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind=? ORDER BY id',(key,kind))
        if len(rows)>1:raise L.Conflict('duplicate native proof anchor')
        if not rows:return None
        value=A.strict_json(rows[0]['payload'])
        if L.digest(value)!=rows[0]['payload_hash']:raise L.Conflict('corrupt native proof anchor')
        return value

    def _guard(self,c):
        if self.broker.context is None:return nullcontext()
        from tmh.platform import tenant_policy as TP
        return TP.experiment_guard(self.broker.context,self.broker.actor,c['project_id'],'manager')

    def freeze(self,key,reference):
        """Freeze a server-owned specification BEFORE every provider attempt.

        Assertions and thresholds are explicit in that registered file. This
        function does not invent or approve a real trial specification.
        """
        self._code();raw,_=self.adapter.registry._read(A.opaque(reference)+'.json')
        spec=A.strict_json(raw);L.fields(spec,{'schema','root_pool','contract_sha256','authorization_sha256','cases','thresholds'})
        c=self.ledger.snapshot(key)['contract'];profile=self.broker._profile(c)
        authority=self.broker._authority(c,profile)
        if (spec['schema']!=VERSION or spec['root_pool']!=key or spec['contract_sha256']!=L.digest(c)
                or spec['authorization_sha256']!=c['budget']['authorization_sha256']):
            raise L.Conflict('assertions belong to another original authorization/root')
        cases=spec['cases'];seen=set()
        if not isinstance(cases,list) or len(cases)!=len(c['holdout_cases']):raise L.Conflict('exact complete terminal universe required')
        for case in cases:
            L.fields(case,{'input_id','input_sha256','source_family','validator','expected','forbidden'})
            _,digest,_=self.broker.catalog.load('input',case['input_id'])
            if (digest!=case['input_sha256'] or digest in seen
                    or {'input_sha256':digest,'source_family':case['source_family']} not in c['holdout_cases']):
                raise L.Conflict('assertion is not the original sealed input')
            seen.add(digest)
            # Reuse the production validator vocabulary with strict typed specs.
            if case['validator'] not in {'exact','contains_all','json_equal'}:raise ValueError('fixed assertion validator required')
            if case['validator']=='exact' and (not isinstance(case['expected'],str) or not case['expected'].strip()):raise ValueError('nonempty exact expectation required')
            if case['validator']=='contains_all' and (not isinstance(case['expected'],list) or not case['expected'] or any(not isinstance(v,str) or not v.strip() for v in case['expected'])):raise ValueError('complete required fragments required')
            if not isinstance(case['forbidden'],list) or any(not isinstance(v,str) or not v.strip() for v in case['forbidden']):raise ValueError('typed forbidden fragments required')
        t=spec['thresholds'];L.fields(t,{'min_pairs','min_improvement','require_candidate_all','allow_regressions'})
        if (type(t['min_pairs']) is not int or not 3<=t['min_pairs']<=len(cases)
                or type(t['min_improvement']) is not int or not 1<=t['min_improvement']<=len(cases)
                or t['require_candidate_all'] is not True or t['allow_regressions'] is not False):raise ValueError('explicit non-weakened assertion thresholds required')
        anchor={'spec':spec,'reference':reference,'reference_sha256':hashlib.sha256(raw).hexdigest(),'code':self.code,
                'profile_sha256':c['provider_binding']['profile_sha256'],'application_commit':c['application_commit'],'model':c['model']}
        with self._guard(c),learning.transaction(self.ledger.store) as db:
            self.ledger._pool(db,key,dispatch=True)
            old=self._one(key,'native_bc_registration')
            if old:
                if old!=anchor:raise L.Conflict('original assertions cannot be replaced')
                return dict(registration_sha256=L.digest(old),replayed=True)
            if (self.broker._authority(c,profile)!=authority or self.ledger._candidate_binding(db,key,c)
                    or db.execute('SELECT 1 FROM rsi_prepare_attempts WHERE pool=?',(key,)).fetchone()):
                raise L.Conflict('cannot register assertions after proposal or any attempt')
            self.ledger._event(db,key,'','native_bc_registration',anchor)
        return dict(registration_sha256=L.digest(anchor),replayed=False)

    def _registration(self,key):
        self._code();anchor=self._one(key,'native_bc_registration')
        if not anchor or anchor['code']!=self.code:raise L.Conflict('no original matching pre-proposal evaluator registration')
        raw,_=self.adapter.registry._read(A.opaque(anchor['reference'])+'.json')
        if hashlib.sha256(raw).hexdigest()!=anchor['reference_sha256'] or A.strict_json(raw)!=anchor['spec']:
            raise L.Conflict('original assertions or thresholds changed')
        return anchor

    def _observations(self,key,anchor):
        c=self.ledger.snapshot(key)['contract'];profile=self.broker._profile(c)
        if (anchor['spec']['contract_sha256']!=L.digest(c) or anchor['profile_sha256']!=c['provider_binding']['profile_sha256']
                or anchor['application_commit']!=c['application_commit'] or anchor['model']!=c['model']):raise L.Conflict('original application/model/profile differs')
        if self.ledger.inspect(key)['blocked']:raise L.Conflict('unknown root cannot qualify')
        bound=self.adapter._verified_candidate(key)
        frontier=[]
        for row in self.ledger.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=? ORDER BY request_id',(key,)):
            snapshot=self.ledger.snapshot(key,row['request_id']);attempt=snapshot['attempt']
            result=self.adapter.reconcile(key,row['request_id'])
            if result['state']!='settled' or not result['response_complete']:raise L.Conflict('all original attempts must be resolved and complete')
            frontier.append({'request_id':row['request_id'],'body_sha256':L.digest(attempt['body']),
                             'receipt_sha256':L.digest(attempt['receipt']),'response_sha256':result['response_sha256'],
                             'stored_attempt_sha256':L.digest(row)})
        with self.ledger.store.lock:slots=self.broker._arm_slots(self.ledger.store.db,key)
        observations=[];origins=[]
        for case in anchor['spec']['cases']:
            capture,digest,_=self.broker.catalog.load('input',case['input_id'])
            if digest!=case['input_sha256']:raise L.Conflict('original common input changed')
            self.broker._capture_current(capture)
            R.native_pair(capture,'baseline',bound['candidate_text'],profile['protocol'])
            item={k:case[k] for k in ('input_sha256','validator','expected','forbidden')}
            for arm in ('baseline','candidate'):
                request=slots.get((digest,arm))
                if not request:raise L.Conflict('missing original terminal arm')
                result=self.adapter.reconcile(key,request)
                if result['state']!='settled' or not result['response_complete']:raise L.Conflict('unresolved original arm')
                # Independently match the immutable registered plan, not a result
                # string coincidentally equal to an unrelated job's output.
                plans=[]
                for e in self.ledger.store.q("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='registered_plan'",(key,)):
                    p=A.strict_json(e['payload'])
                    if L.digest(p)!=e['payload_hash']:raise L.Conflict('corrupt original plan')
                    if p['request_id']==request:plans.append(p)
                if len(plans)!=1 or plans[0]['input_sha256']!=digest:raise L.Conflict('arm has no unique original input provenance')
                plan,ph,_=self.broker.catalog.load('plan',plans[0]['plan_id'])
                if ph!=plans[0]['plan_sha256'] or plan['phase']!=arm or plan['root_pool']!=key:raise L.Conflict('arm plan changed')
                expected=c['baseline_sha256'] if arm=='baseline' else bound['candidate_sha256']
                if plan['policy_sha256']!=expected:raise L.Conflict('arm changed original policy')
                item[arm]=result['response_text']
                origins.append({'input_sha256':digest,'arm':arm,'request_id':request,'response_sha256':result['response_sha256']})
            observations.append(item)
        return {'cases':observations,'thresholds':anchor['spec']['thresholds']},frontier,origins

    def _assert_snapshot(self,key,anchor,frontier):
        """Read-only revalidation under the caller's DB/lesson snapshot.

        Do not reconcile provider attempts here: their full originals were
        checked before the snapshot, and reconciliation owns transactions.
        """
        if self._registration(key)!=anchor:raise L.Conflict('original native registration changed')
        # Reuse the already-owned transaction/savepoint, never nest Ledger's
        # public snapshot()/inspect() transaction wrappers.
        c=self.ledger._pool(self.ledger.store.db,key)
        if L.digest(c)!=anchor['spec']['contract_sha256']:raise L.Conflict('original root changed')
        rows=self.ledger.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=? ORDER BY request_id',(key,))
        if [L.digest(r) for r in rows]!=[r['stored_attempt_sha256'] for r in frontier]:
            raise L.Conflict('native report frontier changed before the protected snapshot')
        if self.ledger.store.one('SELECT blocked FROM rsi_prepare_pools WHERE pool=?',(key,))['blocked']:
            raise L.Conflict('unknown root cannot qualify')
        self.broker._sealed_inputs(key,c)
        profile=self.broker._profile(c);authority=self.broker._authority(c,profile)
        for case in anchor['spec']['cases']:
            value,digest,_=self.broker.catalog.load('input',case['input_id'])
            if digest!=case['input_sha256']:raise L.Conflict('original common input changed')
            self.broker._capture_current(value)
            if self.broker.context is not None and (value['source']['project']!=authority['project'] or value['source']['binding']!=authority['binding']):
                raise L.Conflict('native input authority/source changed')

    @contextmanager
    def _publication_snapshot(self,c):
        store=self.ledger.store
        with self._guard(c),learning.transaction(store) as db:
            with learn.ledger_lock(store.path.parent,create=False):
                yield db
                # Commit OUR transaction before releasing the lesson lease.
                # learning.transaction's later commit is then a no-op. This
                # retains Registry -> Store/SQLite -> lesson acquisition order.
                db.commit()

    def evaluate(self,key):
        anchor=self._registration(key);value,frontier,origins=self._observations(key,anchor)
        c=self.ledger.snapshot(key)['contract'];fingerprint=L.digest([anchor,frontier,origins])
        with learning.transaction(self.ledger.store) as db:
            self.ledger._pool(db,key,dispatch=True)
            old=self._one(key,'native_bc_evaluation_intent')
            if old:
                if old['fingerprint']!=fingerprint:raise L.Conflict('native evaluation sources changed')
            else:
                intent={'fingerprint':fingerprint,'owner':{'run_id':L.digest(['native-bc',key]),'token':uuid.uuid4().hex,'data_dir':str(self.root)}}
                self.ledger._event(db,key,'','native_bc_evaluation_intent',intent)
        if old:return self.read(key)
        folder=self.root/key
        timeout=min(3,(c['limits']['deadline_us']-self.ledger._time())/1_000_000)
        if timeout<=0:raise L.Conflict('original root deadline expired')
        SP.run_supervised([sys.executable,'-I','-B',str(WORKER)],folder=folder,owner=intent['owner'],cwd=self.root,
                          env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},timeout=timeout,stdin=L.encoded(value))
        receipt=SP.read_receipt(folder,intent['owner'])
        if (receipt is None or receipt['returncode']!=0 or not receipt['cleanup']['complete'] or not receipt['cleanup']['reaped']
                or receipt['cleanup']['remaining_group']):raise L.Conflict('independent assertion process unresolved')
        raw=(folder/'output.bin').read_bytes();assertions=A.strict_json(raw)
        from scripts.rsi.native_bc_worker import evaluate
        if assertions!=evaluate(value):raise L.Conflict('original evaluator output differs from complete assertions')
        self._code();_,current,now_origins=self._observations(key,anchor)
        if current!=frontier or now_origins!=origins:raise L.Conflict('native evidence changed during independent evaluation')
        report={'schema':'native-bc-report-v1','root_pool':key,'contract_sha256':L.digest(c),
                'registration_sha256':L.digest(anchor),'fingerprint':fingerprint,'frontier':frontier,'origins':origins,
                'candidate_sha256':self.ledger.snapshot(key)['candidate_binding']['candidate_sha256'],
                'assertions':assertions,'evaluator_receipt_sha256':L.digest(receipt),'evaluator_output_sha256':hashlib.sha256(raw).hexdigest(),
                'source_mode':self.broker._profile(c)['mode'],'rsi_qualified':False,'human_adoption':False}
        with self._publication_snapshot(c) as db:
            self.ledger._pool(db,key,dispatch=True)
            self._assert_snapshot(key,anchor,frontier)
            self.ledger._event(db,key,'','native_bc_report',report)
        return dict(report,report_sha256=L.digest(report))

    def read(self,key):
        anchor=self._registration(key);report=self._one(key,'native_bc_report');intent=self._one(key,'native_bc_evaluation_intent')
        if not report or not intent:raise L.Conflict('evaluation pending/unknown; do not automatically rerun')
        value,frontier,origins=self._observations(key,anchor)
        if (report['registration_sha256']!=L.digest(anchor) or report['frontier']!=frontier or report['origins']!=origins
                or report['fingerprint']!=L.digest([anchor,frontier,origins]) or intent['fingerprint']!=report['fingerprint']):raise L.Conflict('native report is no longer bound to all original attempts')
        folder=self.root/key;receipt=SP.read_receipt(folder,intent['owner']);raw=(folder/'output.bin').read_bytes()
        if (receipt is None or receipt['returncode']!=0 or not receipt['cleanup']['complete'] or not receipt['cleanup']['reaped']
                or receipt['cleanup']['remaining_group'] or L.digest(receipt)!=report['evaluator_receipt_sha256']
                or hashlib.sha256(raw).hexdigest()!=report['evaluator_output_sha256'] or A.strict_json(raw)!=report['assertions']):raise L.Conflict('native evaluator original changed')
        return dict(report,report_sha256=L.digest(report))

    def decision_link(self,key,decision_id):
        """Verify an existing person's EXACT report reference, never adopt.

        This is a necessary relation, not the native-job execution bridge. The
        ordinary job must still be proven to belong to this root before live D.
        """
        from tmh.platform import learning_decisions as D, learning_runs, signoff
        report=self.read(key)
        if report['assertions']['passed'] is not True:raise L.Conflict('native assertions did not qualify')
        c=self.ledger.snapshot(key)['contract'];profile=self.broker._profile(c)
        if self.broker.context is None:raise L.Conflict('current personal tenant context required')
        context=self.broker.context;store=self.ledger.store
        with self._decision_snapshot(c,context):
            self._assert_snapshot(key,self._registration(key),report['frontier'])
            self.broker._authority(c,profile)
            project=store.project(c['project_id'])
            row=store.one('SELECT * FROM learning_decisions WHERE id=? AND project_id=?',(decision_id,c['project_id']))
            if not row or row['status']!='applied' or row['action']!='adopt' or row['kind']!='lesson' or not signoff.human(row['actor']):
                raise L.Conflict('exact applied personal lesson decision required')
            latest=store.one("SELECT id FROM learning_decisions WHERE project_id=? AND origin_id=? AND kind='lesson' AND status='applied' ORDER BY rowid DESC LIMIT 1",(project['id'],row['origin_id']))
            if not latest or latest['id']!=row['id']:raise L.Conflict('personal decision is no longer the current exact adoption')
            revision=learning.revision(context,project,row['revision_id']);payload=A.strict_json(row['payload'])
            if (payload.get('source')!=revision['source'] or payload.get('content')!=revision['content']
                    or hashlib.sha256(A.strict_json(revision['content'])['fix'].encode()).hexdigest()!=report['candidate_sha256']
                    or not D.adopted_current(context,project,revision)):
                raise L.Conflict('personal adoption is stale or belongs to another policy')
            reference=A.strict_json(payload['request']['reason'])
            L.fields(reference,{'schema','root_pool','native_report_sha256','reason'})
            if (reference['schema']!='native-bc-decision-reference-v1' or reference['root_pool']!=key
                    or reference['native_report_sha256']!=report['report_sha256'] or not isinstance(reference['reason'],str) or not reference['reason'].strip()):
                raise L.Conflict('person did not reference this exact original report/root')
            job=learning_runs.get(context,project,payload['request']['job_id'])
            if (job['kind']!='evaluate' or job['status']!='passed' or job['current_revision_id']!=revision['id']
                    or job['result'].get('passed') is not True or not learning_eval._captured_lesson_input(context,project,job)):
                raise L.Conflict('original personal decision job is not verifiable')
        return {'root_pool':key,'native_report_sha256':report['report_sha256'],'decision_id':row['id'],
                'revision_id':revision['id'],'job_id':job['id'],'job_report_sha256':L.digest(job['result']),
                'reference_verified':True,'source_mode':report['source_mode'],
                'job_native_provenance_verified':False,'live_d_eligible':False,'rsi_qualified':False}

    @contextmanager
    def _decision_snapshot(self,c,context):
        store=self.ledger.store
        with self._guard(c),store.lock,learn.ledger_lock(context.data_dir,create=False):
            store.db.execute('SAVEPOINT native_bc_decision_read')
            try:yield
            finally:store.db.execute('RELEASE native_bc_decision_read')
