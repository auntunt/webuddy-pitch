"""Private original-proof publisher. Never calls a human decision or a model."""
import hashlib
import os
from pathlib import Path

from scripts.rsi import trial_preparation as L, provider_adapter as A, native_bc_report as B
from tmh.platform import learning, learning_runs, native_learning as N, supervised_process as SP
from tmh.platform.store import now


def artifact(path):
    path = Path(path).absolute()
    if path.is_symlink(): raise L.Conflict('original artifact link changed')
    path = path.resolve()
    if not path.is_file(): raise L.Conflict('original artifact path changed')
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


class Jobs:
    def __init__(self, reports):
        self.reports = reports; self.broker = reports.broker; self.ledger = reports.ledger
        self.context = self.broker.context
        if self.context is None: raise L.Conflict('personal tenant context required')

    def publish(self, key, revision_id):
        """Publish actual native assertions for one exact lesson revision.

        This producer does not mark ordinary jobs passed or impersonate a human.
        The published input scope is native fixed-text policy intervention only.
        """
        c = self.ledger.snapshot(key)['contract']
        if c['schema'] != L.FINITE_PROVIDER_VERSION: raise L.Conflict('new finite native root required')
        profile = self.broker._profile(c); self.broker._authority(c, profile)
        context = self.context; project = context.store.project(c['project_id'])
        revision = learning.revision(context, project, revision_id)
        if revision['kind'] != 'lesson' or not learning.revision_current(context, project, revision): raise L.Conflict('current exact lesson revision required')
        report = self.reports.read(key)
        if not report['assertions']['passed']: raise L.Conflict('original native assertions did not pass')
        if hashlib.sha256(A.strict_json(revision['content'])['fix'].encode()).hexdigest() != report['candidate_sha256']: raise L.Conflict('revision changed the complete tested policy')
        job_id = 'NJ'+L.digest([key, report['report_sha256'], revision_id])[:40]
        existing = context.store.one('SELECT id FROM learning_jobs WHERE id=?', (job_id,)) if context.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='learning_jobs'") else None
        if existing:
            job = learning_runs.get(context, project, job_id); N.verify(context, project, job)
            return job
        learning_runs.schema(context.store)
        anchor = self.reports._registration(key)
        observations, frontier, origins = self.reports._observations(key, anchor)
        if frontier != report['frontier'] or origins != report['origins']: raise L.Conflict('report changed before publication')
        paths = {Path(__file__), Path(__file__).with_name('native_d_worker.py'), Path(N.__file__), *B.SOURCES}
        supervised = []
        captures = []
        for case in anchor['spec']['cases']:
            value, _, _ = self.broker.catalog.load('input', case['input_id']); captures.append(value)
            paths.add(self.broker.catalog.files.path/('input-'+case['input_id'])/'record.json')
        for row in context.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=? ORDER BY request_id', (key,)):
            folder = self.reports.adapter._folder(key, row['request_id'])
            paths.update(p for p in folder.rglob('*') if p.is_file())
            owner = self.reports.adapter._owner(key, row['request_id'], row['intent'])
            receipt = SP.read_receipt(folder/'transport', owner)
            supervised.append(dict(folder=str(folder/'transport'), owner=owner, receipt_sha256=L.digest(receipt)))
        intent = self.reports._one(key, 'native_bc_evaluation_intent')
        supervised.append(dict(folder=str(self.reports.root/key), owner=intent['owner'], receipt_sha256=report['evaluator_receipt_sha256']))
        paths.update(p for p in (self.reports.root/key).rglob('*') if p.is_file())
        paths.add(self.reports.adapter.registry.path/(c['provider_binding']['profile_id']+'.json'))
        paths.add(self.reports.adapter.registry.path/(anchor['reference']+'.json'))
        for event in context.store.q("SELECT payload FROM rsi_prepare_events WHERE pool=? AND kind='registered_plan'", (key,)):
            plan = A.strict_json(event['payload'])
            paths.add(self.broker.catalog.files.path/('plan-'+plan['plan_id'])/'record.json')
            paths.add(self.broker.catalog.files.path/('input-'+plan['input_id'])/'record.json')
            captured,_,_=self.broker.catalog.load('input',plan['input_id'])
            if captured not in captures: captures.append(captured)
        loaded = self.reports.adapter.registry.load(c['provider_binding']['profile_id'])
        credential_path = self.reports.adapter.registry.path/'credentials'/profile['credential_ref']
        ledger_schema={v['name']:v['sql'] for v in context.store.q("SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE 'rsi_prepare_%'")}
        proof = dict(ledger_schema=ledger_schema,schema=N.SCHEMA, root_pool=key, contract_sha256=L.digest(c), native_report_sha256=report['report_sha256'],
                     revision=revision, frontier=frontier, captures=captures, observations=observations,
                     supervised=supervised, artifacts=[artifact(p) for p in sorted(paths)],
                     verifier_sha256=hashlib.sha256(Path(N.__file__).read_bytes()).hexdigest(),
                     credential_identity=dict(path=str(credential_path), identity=list(loaded['credential_identity'])))
        raw = L.encoded(proof).encode(); evidence_hash = hashlib.sha256(raw).hexdigest()
        reference = dict(schema=N.SCHEMA, root_pool=key, native_report_sha256=report['report_sha256'])
        result = dict(schema='native-learning-report-v1', passed=True, root_pool=key, native_report_sha256=report['report_sha256'],
                      revision_id=revision_id, candidate_sha256=report['candidate_sha256'], counts=report['assertions']['counts'],
                      scope='native-fixed-text-policy-only', source_mode=profile['mode'], actual_cost=None, rsi_qualified=False)
        base = Path(context.data_dir).resolve()/'native-learning'; base.mkdir(mode=0o700, exist_ok=True)
        folder = base/job_id; folder.mkdir(mode=0o700, exist_ok=True)
        N.folder(context, job_id)
        with self.reports._publication_snapshot(c) as db:
            self.ledger._pool(db, key, dispatch=True)
            self.reports._assert_snapshot(key, anchor, frontier)
            if learning.revision(context, project, revision_id) != revision or not learning.revision_current(context, project, revision): raise L.Conflict('revision changed before job publication')
            old = self.reports._one(key, N.EVENT)
            if old: raise L.Conflict('original root already published its native job')
            file = folder/'evidence.json'
            try:
                fd = os.open(file, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                if N.private_file(file) != raw: raise L.Conflict('orphan publication differs; never replace originals')
            else:
                with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                directory = os.open(folder, os.O_RDONLY|os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
            db.execute("INSERT INTO learning_jobs(id,project_id,kind,revision_id,current_revision_id,request_id,request_hash,actor,status,options,binding,created,ended,deadline,calls,result) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (job_id,project['id'],N.KIND,revision_id,revision_id,'native:'+key,L.digest([key,revision_id,report['report_sha256']]),
                        self.broker.actor,'passed',L.encoded({'native_evaluation':reference}),L.encoded({'native_evaluation':reference}),now(),now(),
                        c['limits']['deadline_us']/1_000_000,len(frontier),L.encoded(result)))
            row = context.store.one('SELECT * FROM learning_jobs WHERE id=?', (job_id,))
            self.ledger._event(db,key,'',N.EVENT,dict(schema=N.SCHEMA, job_id=job_id, job_sha256=L.digest(row), evidence_sha256=evidence_hash))
            N.verify(context,project,learning_runs.get(context,project,job_id))
        return learning_runs.get(context,project,job_id)

    def link(self, key, decision_id, *, followup_request=''):
        """Read one existing person's native job/report reference; never decide."""
        from tmh.platform import learning_decisions as D, signoff
        store = self.context.store
        c = self.ledger._pool(store.db,key) if store.db.in_transaction else self.ledger.snapshot(key)['contract']
        profile = self.broker._profile(c)
        with self.reports._decision_snapshot(c,self.context):
            self.broker._authority(c,profile)
            publication = N.event(self.context,key,N.EVENT)
            project = store.project(c['project_id']); job = learning_runs.get(self.context,project,publication['job_id'])
            row = store.one('SELECT * FROM learning_decisions WHERE id=? AND project_id=?',(decision_id,project['id']))
            if not row or row['action']!='adopt' or row['status']!='applied' or row['kind']!='lesson' or not signoff.human(row['actor']): raise L.Conflict('exact applied personal native decision required')
            payload = A.strict_json(row['payload']); revision = learning.revision(self.context,project,row['revision_id'])
            latest = store.one("SELECT id FROM learning_decisions WHERE project_id=? AND origin_id=? AND status='applied' ORDER BY rowid DESC LIMIT 1",(project['id'],row['origin_id']))
            if (not latest or latest['id']!=row['id'] or payload['request']['job_id']!=job['id'] or job['current_revision_id']!=revision['id']
                    or payload['content']!=revision['content'] or payload['source']!=revision['source'] or not D.adopted_current(self.context,project,revision)):
                raise L.Conflict('current personal decision does not own the native job')
            proof = N.verify(self.context,project,job,reason=payload['request']['reason'],adopted=True,followup_request=followup_request)
        return dict(root_pool=key,decision_id=row['id'],revision_id=revision['id'],job_id=job['id'],
                    report_sha256=L.digest(job['result']),native_report_sha256=proof['native_report_sha256'],
                    job_native_provenance_verified=True,source_mode=profile['mode'],rsi_qualified=False)

    def _selected(self, value, revision):
        content = A.strict_json(revision['content'])
        for meta in value['source']['context']:
            if meta.get('mode')!='learning_lessons': continue
            selected = any(r.get('kind')=='lesson' and r.get('origin_id')==revision['origin_id'] and r.get('revision_id')==revision['id'] and r.get('included') is True for r in meta.get('revisions',[]))
            payload = any(p.get('scope')=='local' and p.get('origin_id')==revision['origin_id'] and p.get('content')==content for p in meta['block']['payloads'])
            if selected and payload: return True
        return False

    def prepare_followup(self, key, plan_id, assertions_reference):
        """Seal one NEW D before its request; the oracle never enters its plan."""
        from scripts.rsi import registered_trial as R
        plan, plan_hash, _ = self.broker.catalog.load('plan',plan_id)
        L.fields(plan,self.broker._fields(plan)); c=self.ledger.snapshot(key)['contract']; profile=self.broker._profile(c)
        value,input_hash,_=self.broker.catalog.load('input',plan['input_id']); R.validate_capture(value)
        if (plan['root_pool']!=key or plan['contract_sha256']!=L.digest(c) or plan['phase']!='followup'
                or plan['source_family']!=c['followup_family'] or plan['input_sha256']!=input_hash
                or plan['kind']!=self.broker.KIND or plan['broker_sha256']!=R.CODE_SHA256): raise L.Conflict('exact finite followup plan required')
        link=self.link(key,plan['adoption']['decision_id']); project=self.context.store.project(c['project_id'])
        if plan['adoption']!={k:link[k] for k in ('decision_id','revision_id','job_id','report_sha256')}: raise L.Conflict('followup changed the personal native reference')
        revision=learning.revision(self.context,project,link['revision_id']);self.broker._capture_current(value)
        if plan['policy']!=A.strict_json(revision['content'])['fix'] or plan['policy_sha256']!=hashlib.sha256(plan['policy'].encode()).hexdigest() or not self._selected(value,revision): raise L.Conflict('new D did not actually select/render the exact adopted policy')
        ticket=value['source']['ticket']
        if not isinstance(ticket,dict) or type(ticket.get('id')) is not int: raise L.Conflict('new D requires an actual task')
        task_sha=self.broker._holdout_identity(value,require_task=True)['task_sha256']
        if any(v['root_pool']!=key and (v['input_sha256']==input_hash or v['task_sha256']==task_sha) for v in self.ledger.native_exposures(c)):
            raise L.Conflict('D task was already exposed in an earlier native root')
        for e in self.context.store.q("SELECT payload FROM rsi_prepare_events WHERE pool=? AND kind='registered_token_input'",(key,)):
            if A.strict_json(e['payload'])['ticket_id']==ticket['id']: raise L.Conflict('D cannot reuse an earlier actual task')
        if input_hash in {v['input_sha256'] for v in c['holdout_cases']}: raise L.Conflict('D cannot reuse sealed BC input')
        raw,_=self.reports.adapter.registry._read(A.opaque(assertions_reference)+'.json'); spec=A.strict_json(raw)
        L.fields(spec,{'schema','root_pool','job_id','input_sha256','validator','expected','forbidden'})
        if (spec['schema']!='native-d-assertion-v1' or spec['root_pool']!=key or spec['job_id']!=link['job_id'] or spec['input_sha256']!=input_hash
                or spec['validator'] not in {'exact','contains_all','json_equal'} or not isinstance(spec['forbidden'],list) or any(not isinstance(v,str) or not v for v in spec['forbidden'])): raise L.Conflict('explicit independent D assertion required')
        if spec['validator']=='exact' and (not isinstance(spec['expected'],str) or not spec['expected'].strip()): raise ValueError('exact D expectation required')
        if spec['validator']=='contains_all' and (not isinstance(spec['expected'],list) or not spec['expected'] or any(not isinstance(v,str) or not v for v in spec['expected'])): raise ValueError('complete D expectations required')
        registration=dict(schema='native-d-registration-v1',root_pool=key,job_id=link['job_id'],native_report_sha256=link['native_report_sha256'],
                          decision_id=link['decision_id'],revision_id=link['revision_id'],request_id=plan['request_id'],plan_id=plan_id,plan_sha256=plan_hash,
                          input_id=plan['input_id'],input_sha256=input_hash,task_id=ticket['id'],source_family=plan['source_family'],
                          assertions_reference=assertions_reference,assertions_sha256=hashlib.sha256(raw).hexdigest())
        with self.reports._publication_snapshot(c) as db:
            self.ledger._pool(db,key,dispatch=True); self.link(key,link['decision_id']); self.broker._capture_current(value)
            old=self.reports._one(key,'native_d_registration')
            if old:
                if old!=registration: raise L.Conflict('the original root already owns its one D')
                return old
            self.ledger._event(db,key,'','native_d_registration',registration)
        return registration

    def followup(self, plan, value, contract, input_hash, profile):
        registration=self.reports._one(plan['root_pool'],'native_d_registration')
        if (not registration or registration['request_id']!=plan['request_id'] or registration['input_sha256']!=input_hash
                or registration['input_id']!=plan['input_id'] or registration['task_id']!=value['source']['ticket']['id']
                or registration['source_family']!=contract['followup_family'] or plan['source_family']!=contract['followup_family']): raise L.Conflict('D is not its original registered new task')
        link=self.link(plan['root_pool'],registration['decision_id'],followup_request=plan['request_id'])
        if plan['adoption']!={k:link[k] for k in ('decision_id','revision_id','job_id','report_sha256')}: raise L.Conflict('D changed its exact native adoption')
        project=self.context.store.project(contract['project_id']);revision=learning.revision(self.context,project,link['revision_id'])
        self.broker._capture_current(value)
        if not self._selected(value,revision) or plan['policy']!=A.strict_json(revision['content'])['fix']: raise L.Conflict('D did not consume the current exact selected policy')
        raw,_=self.reports.adapter.registry._read(A.opaque(registration['assertions_reference'])+'.json')
        if hashlib.sha256(raw).hexdigest()!=registration['assertions_sha256']: raise L.Conflict('original D oracle changed')
        return dict(link,selected=True)

    def _d_context(self, key):
        registration=self.reports._one(key,'native_d_registration')
        if not registration: raise L.Conflict('no original D registration')
        c=self.ledger.snapshot(key)['contract'];profile=self.broker._profile(c)
        plan,plan_hash,_=self.broker.catalog.load('plan',registration['plan_id'])
        value,input_hash,_=self.broker.catalog.load('input',registration['input_id'])
        if plan_hash!=registration['plan_sha256'] or input_hash!=registration['input_sha256']: raise L.Conflict('original D input/plan changed')
        link=self.followup(plan,value,c,input_hash,profile)
        result=self.reports.adapter.reconcile(key,registration['request_id'])
        if result['state']!='settled' or not result['response_complete']: raise L.Conflict('D original response is not complete')
        raw,_=self.reports.adapter.registry._read(A.opaque(registration['assertions_reference'])+'.json')
        if hashlib.sha256(raw).hexdigest()!=registration['assertions_sha256']: raise L.Conflict('D oracle changed')
        spec=A.strict_json(raw);worker_input=dict(case={k:spec[k] for k in ('validator','expected','forbidden')},output=result['response_text'],input_sha256=input_hash)
        attempt=self.context.store.one('SELECT * FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(key,registration['request_id']))
        return dict(contract=c,registration=registration,plan=plan,capture=value,link=link,result=result,worker_input=worker_input,
                    attempt_sha256=L.digest(attempt),fingerprint=L.digest([registration,link,worker_input,L.digest(attempt)]))

    def _d_snapshot(self, ctx):
        c=ctx['contract'];registration=ctx['registration'];key=registration['root_pool']
        link=self.followup(ctx['plan'],ctx['capture'],c,registration['input_sha256'],self.broker._profile(c))
        row=self.context.store.one('SELECT * FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(key,registration['request_id']))
        if link!=ctx['link'] or L.digest(row)!=ctx['attempt_sha256']: raise L.Conflict('D or adoption changed before report commit')

    def evaluate_followup(self, key):
        """One original assertion worker over actual D; no implicit rerun."""
        import sys
        import uuid
        ctx=self._d_context(key);c=ctx['contract'];store=self.context.store
        with self.reports._publication_snapshot(c) as db:
            self.ledger._pool(db,key,dispatch=True);self._d_snapshot(ctx)
            old=self.reports._one(key,'native_d_evaluation_intent')
            if old:
                if old['fingerprint']!=ctx['fingerprint']: raise L.Conflict('original D evaluation binding changed')
            else:
                intent=dict(fingerprint=ctx['fingerprint'],owner=dict(run_id=L.digest(['native-D',key]),token=uuid.uuid4().hex,data_dir=str(self.reports.root)))
                self.ledger._event(db,key,'','native_d_evaluation_intent',intent)
        if old: return self.read_followup(key)
        folder=self.reports.root/key/'D';timeout=min(3,(c['limits']['deadline_us']-self.ledger._time())/1_000_000)
        if timeout<=0: raise L.Conflict('original finite deadline expired')
        SP.run_supervised([sys.executable,'-I','-B',str(Path(__file__).with_name('native_d_worker.py'))],folder=folder,owner=intent['owner'],cwd=self.reports.root,
                          env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},timeout=timeout,stdin=L.encoded(ctx['worker_input']))
        receipt=SP.read_receipt(folder,intent['owner']);raw=(folder/'output.bin').read_bytes()
        from . import native_d_worker as W
        assertion=A.strict_json(raw)
        if not receipt or receipt['returncode']!=0 or not receipt['cleanup']['complete'] or assertion!=W.evaluate(ctx['worker_input']): raise L.Conflict('original D assertion worker is unresolved')
        result=dict(schema='native-d-report-v1',root_pool=key,job_id=ctx['link']['job_id'],revision_id=ctx['link']['revision_id'],decision_id=ctx['link']['decision_id'],
                    native_report_sha256=ctx['link']['native_report_sha256'],input_sha256=ctx['registration']['input_sha256'],task_id=ctx['registration']['task_id'],
                    fingerprint=ctx['fingerprint'],assertions=assertion,receipt_sha256=L.digest(receipt),output_sha256=hashlib.sha256(raw).hexdigest(),
                    attempt_sha256=ctx['attempt_sha256'],original_response_sha256=ctx['result']['response_sha256'],
                    knowledge_selector=ctx['capture']['source']['selector'],knowledge_renderer=ctx['capture']['source']['renderer'],
                    source_mode=self.broker._profile(c)['mode'],rsi_qualified=False,production_equivalent=False)
        with self.reports._publication_snapshot(c) as db:
            self.ledger._pool(db,key,dispatch=True);self._d_snapshot(ctx)
            self.ledger._event(db,key,'','native_d_report',result)
        return dict(result,report_sha256=L.digest(result))

    def read_followup(self, key):
        ctx=self._d_context(key);intent=self.reports._one(key,'native_d_evaluation_intent');report=self.reports._one(key,'native_d_report')
        if not intent or not report or intent['fingerprint']!=ctx['fingerprint'] or report['fingerprint']!=ctx['fingerprint']: raise L.Conflict('D pending/unknown or source changed; do not rerun')
        receipt=SP.read_receipt(self.reports.root/key/'D',intent['owner']);raw=(self.reports.root/key/'D'/'output.bin').read_bytes()
        if (not receipt or receipt['returncode']!=0 or not receipt['cleanup']['complete'] or L.digest(receipt)!=report['receipt_sha256']
                or hashlib.sha256(raw).hexdigest()!=report['output_sha256'] or A.strict_json(raw)!=report['assertions']): raise L.Conflict('D original evaluator changed')
        from . import native_d_worker as W
        if report['assertions']!=W.evaluate(ctx['worker_input']): raise L.Conflict('D original assertion no longer matches')
        with self.reports._decision_snapshot(ctx['contract'],self.context): self._d_snapshot(ctx)
        return dict(report,report_sha256=L.digest(report))
