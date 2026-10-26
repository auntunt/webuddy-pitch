"""Actual Registry/Store/SQLite and fixed supervised synthetic targets only."""
from contextlib import contextmanager, closing
import concurrent.futures
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.rsi.codex_ledger import Ledger, Conflict, Stopped
from tests.test_codex_ledger import contract
from tmh.platform import codex_dispatch_probe as X, learn, learning as L, login, tenancy
from tmh.platform.tenant_runtime import TenantContext, TOOL
from tmh.platform.store import Store
from tmh.platform.errors import ApiError


class DispatchProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-dispatch-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.addCleanup(self.retain)
        self.data = self.folder / 'runtime'
        self.data.mkdir()
        login._save_users(self.data, {x: {'pw': 'synthetic-not-for-login'} for x in ('owner', 'alice', 'bob')})
        self.reg = tenancy.Registry(self.data, bootstrap_owner='owner')
        self.addCleanup(self.reg.close)
        self.store = Store(self.data / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.repo = self.folder / 'repo'; self.repo.mkdir()
        self.source = self.repo / 'app.py'; self.source.write_text('审批 = "待审"\n',encoding='utf-8')
        self.empty_template=self.folder/'empty-git';self.empty_template.mkdir()
        subprocess.run(['git','init','-q','--template='+str(self.empty_template),str(self.repo)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Synthetic','-c','user.email=fixture@localhost',
                        '-c','core.hooksPath='+str(self.empty_template),'-c','commit.gpgsign=false','commit','-qm','fixture'],check=True,capture_output=True)
        self.p = self.store.add_project('APP','合成项目',str(self.repo))
        self.context=TenantContext(self.reg,'default')
        self.P=SimpleNamespace(store=self.store,data_dir=self.data,tenant_context=self.context)
        self.context.platform=self.P
        self.t=self.store.create_ticket(self.p['id'],'重复审批回调','owner',body='保留中文、emoji🧪、换行\r\n末尾  '+('完整资料。'*500),auto=False)
        self.card=learn.add_lesson(self.data,{'project':'APP','ticket':'PREVIOUS-1','status':'candidate',
            'title':'重复审批回调','symptom':'重复审批回调','fix':'旧合成规则','cause':None,'files':['app.py']})
        self.base=self.capture()
        learn.edit_lesson(self.data,self.card['id'],{'fix':'新的合成幂等步骤\r\n完整末尾  '},'fixture')
        self.candidate=self.capture()
        self.probe=X.Probe(self.P,'owner')
        self.ledger=self.probe.ledger
        self.spec=contract()
        self.spec.update(tenant='default',project_id=self.p['id'],application_commit=self.probe.build['commit'],
            baseline_sha256=X.C.digest(self.base['content'].encode()),candidate_sha256=X.C.digest(self.candidate['content'].encode()))
        self.spec['limits']['total_timeout_seconds']=30
        self.now=time.time_ns()//1000
        self.ledger.register(self.spec,starts_us=self.now,deadline_us=self.now+30_000_000)
        self.req={'root_id':self.spec['root_id'],'request_id':'synthetic-one','project_id':self.p['id'],'ticket_id':self.t['id'],
                  'baseline_revision_id':self.base['id'],'candidate_revision_id':self.candidate['id'],'arm':'candidate'}
        self.serial=0

    def retain(self):
        destination=os.environ.get('CODEX_PROBE_SCENES')
        if destination and self.folder.exists():
            shutil.copytree(self.folder,Path(destination)/self._testMethodName,symlinks=True)

    def capture(self):
        item=L._origin(self.P,self.p,'lesson:'+self.card['id'])
        return L.capture(self.P,self.p,item['key'],item['fingerprint'],'fixture')

    def change(self,action,**kw):
        self.serial+=1
        return self.reg.dispatch('owner',dict(action=action,tenant='default',revision=self.reg.context('owner')['revision'],request_id='change-'+str(self.serial),**kw))

    def second(self, actor='owner',mode='echo'):
        st=Store(self.store.path);self.addCleanup(st.db.close)
        c=TenantContext(self.reg,'default');p=SimpleNamespace(store=st,data_dir=self.data,tenant_context=c);c.platform=p
        return X.Probe(p,actor,fixture_mode=mode)

    def counts(self):
        with closing(sqlite3.connect(self.store.path)) as db:
            return {table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in
                ('runs','knowledge_run_inputs','codex_learning_attempts','codex_learning_dispatch')}

    def original_files(self):
        return {str(p.relative_to(self.data)):p.read_bytes() for p in (self.data/'runs').rglob('*') if p.is_file()} if (self.data/'runs').exists() else {}

    def assert_no_target(self):
        self.assertEqual(list((self.data/'runs').glob('*/attempts/*/process.json')),[])

    def test_P01_authoritative_request_and_actual_registry(self):
        for key,value in [('actor','owner'),('tenant','default'),('prompt','fake'),('argv',['echo']),('env',{}),('path','/tmp'),('proof_sha256','a'*64),('phase','B')]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.probe.prepare(dict(self.req,**{key:value}))
        other=self.store.add_project('OTHER','其他',str(self.repo))
        with self.assertRaises(Conflict):self.probe.prepare(dict(self.req,project_id=other['id']))
        self.change('project_grant',user='alice',project_id=self.p['id'],role='manager')
        with self.assertRaises(ApiError):self.second('alice').prepare(self.req)
        token=TOOL.set({'user':'owner','tenant':'default','scope':'content','project_ids':[self.p['id']]})
        try:
            with self.assertRaises(ApiError):self.probe.prepare(self.req)
        finally:TOOL.reset(token)
        self.assertEqual(set(self.counts().values()),{0})
        self.probe.prepare(self.req)
        self.assertEqual(set(self.counts().values()),{1})

    def test_P01_cross_tenant_host_context_is_denied_before_slot(self):
        tenant=self.change('tenant_create',name='另一合成租户')['tenant_id']
        context=TenantContext(self.reg,tenant)
        platform=SimpleNamespace(store=self.store,data_dir=self.data,tenant_context=context);context.platform=platform
        other=X.Probe(platform,'owner')
        with self.assertRaises(ApiError):other.prepare(self.req)
        self.assertEqual(set(self.counts().values()),{0})

    def test_P02_borrow_factory_pragmas_close_and_existing_transaction(self):
        factory=self.store.db.row_factory
        pragmas={k:self.store.one('PRAGMA '+k) for k in ('synchronous','journal_mode','foreign_keys')}
        borrowed=Ledger.for_store(self.store)
        self.assertIs(borrowed.db,self.store.db);self.assertIs(borrowed._lock,self.store.lock)
        borrowed.close();self.assertEqual(self.store.one('SELECT 7 AS n')['n'],7)
        self.assertIs(factory,self.store.db.row_factory)
        self.assertEqual(pragmas,{k:self.store.one('PRAGMA '+k) for k in pragmas})
        self.store.db.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(Conflict):Ledger.for_store(self.store)
            with self.assertRaises(Conflict):self.probe.prepare(self.req)
            self.assertTrue(self.store.db.in_transaction)
        finally:self.store.db.rollback()

    def test_P03_real_trigger_failure_rolls_back_entire_T1(self):
        for table in ('runs','knowledge_run_inputs','codex_learning_attempts','codex_learning_events','codex_learning_dispatch'):
            with self.subTest(table=table):
                self.store.x("CREATE TRIGGER deny_write BEFORE INSERT ON "+table+" BEGIN SELECT RAISE(ABORT,'synthetic T1 fault'); END")
                try:
                    with self.assertRaises(sqlite3.IntegrityError):self.probe.prepare(self.req)
                    self.assertFalse(self.store.db.in_transaction)
                    self.assertEqual(set(self.counts().values()),{0})
                finally:self.store.x('DROP TRIGGER deny_write')

    def test_P03_expired_and_generation_lost_before_T1_have_only_stop_writes(self):
        for reason in ('expired','generation_lost'):
            with self.subTest(reason=reason):
                oldwall=self.ledger.wall;oldgen=self.ledger.generation
                if reason=='expired':self.ledger.wall=lambda:self.now+30_000_001
                else:self.ledger.generation='other-generation'
                with self.assertRaisesRegex(Stopped,reason):self.probe.prepare(self.req)
                self.assertEqual(set(self.counts().values()),{0})
                self.assertFalse(self.store.db.in_transaction)
                snap=self.ledger.snapshot(self.req['root_id']);self.assertEqual(snap['root']['status'],reason)
                self.ledger.wall=oldwall;self.ledger.generation=oldgen
                if reason=='expired':
                    # Independent synthetic root, never refreshing the stopped one.
                    self.spec=dict(self.spec,root_id='e'*64)
                    self.req=dict(self.req,root_id=self.spec['root_id'])
                    self.ledger.register(self.spec,starts_us=self.now,deadline_us=self.now+30_000_000)

    def test_P03_late_Stopped_rolls_back_business_before_stop_only(self):
        original=self.store._create_run_in_tx
        def late(*args,**kw):
            rid=original(*args,**kw)
            self.ledger.wall=lambda:self.now+30_000_001
            return rid
        with patch.object(self.store,'_create_run_in_tx',side_effect=late),self.assertRaises(Stopped):self.probe.prepare(self.req)
        self.assertEqual(set(self.counts().values()),{0})
        self.assertEqual(self.ledger.snapshot(self.req['root_id'])['root']['status'],'expired')

    def test_P03_wrong_revision_digest_and_missing_named_lease_reserve_nothing(self):
        with self.assertRaises(Conflict):self.probe.prepare(dict(self.req,baseline_revision_id=self.candidate['id']))
        path=self.data/'lessons.lock';path.rename(path.with_suffix('.retained'))
        with self.assertRaises(FileNotFoundError):self.probe.prepare(self.req)
        self.assertEqual(set(self.counts().values()),{0})

    def test_P03_stop_only_busy_commit_reports_database_error_without_business(self):
        reader=sqlite3.connect(self.store.path);self.addCleanup(reader.close)
        reader.execute('BEGIN');reader.execute('SELECT * FROM codex_learning_roots').fetchall()
        self.store.db.execute('PRAGMA busy_timeout=0')
        self.ledger.wall=lambda:self.now+30_000_001
        with self.assertRaises(sqlite3.OperationalError) as error:self.probe.prepare(self.req)
        self.assertEqual(error.exception.sqlite_errorcode,sqlite3.SQLITE_BUSY)
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual(set(self.counts().values()),{0})
        self.assertEqual(reader.execute('SELECT status FROM codex_learning_roots').fetchone()[0],'open')
        reader.rollback()
        self.assertEqual(self.ledger.reconcile(self.req['root_id'])['root']['status'],'expired')

    def test_P04_T2_real_busy_commit_has_no_ticket_or_target(self):
        self.probe.prepare(self.req)
        reader=sqlite3.connect(self.store.path);self.addCleanup(reader.close)
        self.store.db.execute('PRAGMA busy_timeout=0')
        original=self.probe.runner._control
        def hold(*args,**kw):
            control=original(*args,**kw)
            reader.execute('BEGIN');reader.execute('SELECT * FROM runs').fetchall()
            return control
        with patch.object(self.probe.runner,'_control',side_effect=hold),self.assertRaises(sqlite3.OperationalError) as err:self.probe.launch(self.req)
        self.assertEqual(err.exception.sqlite_errorcode,sqlite3.SQLITE_BUSY)
        self.assertFalse(self.store.db.in_transaction)
        reader.rollback()
        row=self.probe._row(self.req);self.assertEqual(row['launch_claim'],'');self.assertIsNone(row['producer_observation'])
        self.assertEqual(self.ledger._attempt(self.req['root_id'],self.req['request_id'])['state'],'reserved')
        self.assertEqual(set(self.counts().values()),{1});self.assert_no_target();self.assertFalse(self.probe.runner.owners)

    def test_P05_T2_source_change_rejected_not_recaptured(self):
        self.probe.prepare(self.req)
        saved=self.probe._row(self.req)['input']
        self.store.update_ticket(self.t['id'],'owner',body='changed input')
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assertEqual(self.probe._row(self.req)['input'],saved);self.assert_no_target()

    def test_P05_unrelated_member_change_does_not_invalidate(self):
        self.probe.prepare(self.req)
        self.change('project_grant',user='bob',project_id=self.p['id'],role='viewer')
        self.assertIsNotNone(self.probe.launch(self.req)['observation'])

    def test_P05_redundant_admin_project_grant_keeps_effective_authority(self):
        self.probe.prepare(self.req)
        self.change('project_grant',user='owner',project_id=self.p['id'],role='viewer')
        self.assertIsNotNone(self.probe.launch(self.req)['observation'])

    def test_P05_revision_tamper_rejected(self):
        self.probe.prepare(self.req)
        self.store.x('UPDATE learning_revisions SET content=? WHERE id=?',('{}',self.candidate['id']))
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P05_project_root_change_rejected(self):
        self.probe.prepare(self.req)
        moved=self.folder/'different';moved.mkdir()
        self.store.x('UPDATE projects SET root=? WHERE id=?',(str(moved),self.p['id']))
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P05_reference_change_rejected(self):
        self.probe.prepare(self.req)
        source=self.store.add_project('LIB','合成引用',str(self.repo))
        self.store.x("INSERT INTO knowledge_revisions(id,project_id,source_id,commit_sha,root,analyzer,status,stage,created,author,digest) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     ('synthetic-reference',source['id'],1,'a'*40,str(self.repo),'synthetic','ready','complete','now','fixture','b'*64))
        self.store.x('INSERT INTO knowledge_references(project_id,revision_id,scopes,purpose,created,author) VALUES(?,?,?,?,?,?)',
                     (self.p['id'],'synthetic-reference','["docs"]','changed source','now','fixture'))
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P05_route_change_rejected(self):
        self.probe.prepare(self.req)
        (self.data/'agent-routes.json').write_text(json.dumps({'schema':1,'projects':{'APP':{'direct_api':False}}}))
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P05_protocol_change_rejected(self):
        self.probe.prepare(self.req)
        with patch.object(X,'PROTOCOL','synthetic-incompatible-version'),self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P05_related_epoch_changed_before_T2_starts_zero(self):
        self.probe.prepare(self.req)
        self.change('password_reset',user='owner',password='synthetic-reset-not-for-login')
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P06_two_controllers_completed_and_delayed_replays_preserve_originals(self):
        self.probe.prepare(self.req);second=self.second();second.prepare(self.req)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            first=pool.submit(self.probe.launch,self.req)
            result=first.result(timeout=10)
            originals=self.original_files()
            # Contender already saw empty claim, but enters only after first lease release.
            with patch.object(second.runner,'_control',side_effect=AssertionError('recontrol')):
                replay=pool.submit(second.launch,self.req).result(timeout=10)
        self.assertEqual(result,replay);self.assertEqual(originals,self.original_files())
        third=self.second()
        with patch.object(third.runner,'_control',side_effect=AssertionError('recontrol')):
            self.assertEqual(third.run(self.req),result)
        self.assertEqual(originals,self.original_files())
        self.assertEqual(len(list((self.data/'runs').glob('*/attempts/*/process.json'))),1)
        self.assertEqual(self.ledger.snapshot(self.req['root_id'])['reserved_total'],1)

    def test_P07_actual_stdin_is_full_server_input_and_no_knowledge_adoption(self):
        before=(self.data/'lessons.jsonl').read_bytes()
        result=self.probe.run(self.req);row=self.probe._row(self.req)
        payload=json.loads(row['input']);frozen=payload['frozen']
        self.assertEqual(frozen['ticket']['body'],self.t['body'])
        content=json.loads(frozen['candidate_revision']['content'])
        self.assertIsNone(content['cause']);self.assertNotIn('verify',content)
        self.assertEqual(content['fix'],'新的合成幂等步骤\r\n完整末尾  ')
        self.assertEqual(frozen['candidate_revision']['source']['evidence'][0]['content'],self.source.read_text())
        self.assertEqual(result['observation']['stdin_delivery_to_fixed_probe'],{'kind':'synthetic_stdin','bytes':len(row['input']),'sha256':X.C.digest(row['input'])})
        self.assertEqual((self.data/'lessons.jsonl').read_bytes(),before)
        self.assertEqual(learn.lesson(self.data,self.card['id'])['status'],'candidate')
        self.assertEqual(self.store.q('SELECT * FROM learning_decisions'),[])
        processes=result['observation']['processes']
        self.assertEqual(len(set(processes[k] for k in ('controller_pid','supervisor_pid','target_pid'))),3)

    def seed_reference(self):
        library=X.project_library
        source=self.store.add_project('LIB','完整合成引用',str(self.repo))
        rid='1'*32;folder=library._folder(self.store,rid,create=True)
        original=folder/'original';(original/'docs').mkdir(parents=True)
        material={'docs/rule.md':'# 规则\r\n审批🧪完整全文\r\n末尾  '.encode('utf-8'),'docs/raw.dat':b'\xff\xfe\x00full-original'}
        manifest={}
        for name,raw in material.items():
            (original/name).write_bytes(raw);manifest[name]={'sha256':X.C.digest(raw),'size':len(raw)}
        commit=subprocess.check_output(['git','-C',str(self.repo),'rev-parse','HEAD'],text=True).strip()
        result={'commit':commit,'original':'original','source_manifest':manifest,'knowledge_manifest':{}}
        result['digest']=library.digest(result)
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False))
        self.store.x("INSERT INTO knowledge_revisions(id,project_id,source_id,commit_sha,root,analyzer,status,stage,created,author,digest) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (rid,source['id'],1,commit,str(self.repo),'synthetic','ready','complete','now','fixture',result['digest']))
        library.grant(self.store,source,self.p['id'],['docs'],'fixture')
        library.reference(self.store,self.p,rid,['docs'],'完整合成输入','fixture')
        self.candidate=self.capture();self.req['candidate_revision_id']=self.candidate['id']
        return source,material

    def test_P07_authorized_reference_originals_are_lossless_including_binary(self):
        _,material=self.seed_reference()
        result=self.probe.run(self.req)
        raw=self.probe._row(self.req)['input']
        refs=json.loads(raw)['frozen']['referenced_material']
        self.assertEqual(len(refs),1)
        for item in refs[0]['files']:
            decoded=item['content'].encode('utf-8') if item['encoding']=='utf-8' else base64.b64decode(item['content'])
            self.assertEqual(decoded,material[item['path']])
        self.assertEqual(len(refs[0]['files']),len(material))
        self.assertEqual(result['observation']['stdin_delivery_to_fixed_probe']['bytes'],len(raw))

    def test_P05_actual_shared_reference_revocation_after_T1_starts_zero(self):
        source,_=self.seed_reference();self.probe.prepare(self.req)
        self.store.x('DELETE FROM knowledge_grants WHERE source_project=? AND target_project=?',(source['id'],self.p['id']))
        with self.assertRaises(Conflict):self.probe.launch(self.req)
        self.assert_no_target()

    def test_P06_simultaneous_controllers_start_exactly_one_target(self):
        self.probe.prepare(self.req);second=self.second();second.prepare(self.req)
        barrier=threading.Barrier(2)
        entered=threading.Event();release=threading.Event()
        def paused(original):
            def invoke(*args,**kw):
                entered.set()
                self.assertTrue(release.wait(5),'replay did not return while first claim remained active')
                return original(*args,**kw)
            return invoke
        def launch(controller):
            barrier.wait(timeout=5)
            return controller.launch(self.req)
        with patch.object(self.probe.runner,'run_command',side_effect=paused(self.probe.runner.run_command)), \
             patch.object(second.runner,'run_command',side_effect=paused(second.runner.run_command)), \
             concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(launch,p) for p in (self.probe,second)]
            try:
                self.assertTrue(entered.wait(5))
                done,_=concurrent.futures.wait(futures,timeout=5,return_when=concurrent.futures.FIRST_COMPLETED)
                self.assertEqual(len(done),1)
                self.assertIsNone(next(iter(done)).result()['observation'])
            finally:release.set()
            values=[f.result(timeout=10) for f in futures]
        self.assertEqual(sum(v['observation'] is not None for v in values),1)
        self.assertEqual(len(list((self.data/'runs').glob('*/attempts/*/process.json'))),1)
        self.assertEqual(self.ledger.snapshot(self.req['root_id'])['intent_total'],1)

    def test_P06_entry_filelock_excludes_another_real_process(self):
        self.probe.prepare(self.req)
        with self.probe._entry(self.req):
            path=next((self.data/'codex-dispatch-locks').glob('*.lock'))
            code="from tmh.platform import filelock\nimport sys\nwith open(sys.argv[1],'r+b') as f:\n try: filelock.try_lock(f)\n except BlockingIOError: print('busy')\n else: raise AssertionError('entry not locked')\n"
            result=subprocess.run([os.sys.executable,'-c',code,str(path)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,'busy\n')

    def test_P06_controller_cannot_consume_another_slot_or_reset_entry_budget(self):
        self.probe.prepare(self.req)
        begin=self.probe._begin
        self.probe.prepare(self.req)
        self.assertEqual(self.probe._begin,begin)
        with self.assertRaisesRegex(Conflict,'one prepared slot'):self.probe.prepare(dict(self.req,request_id='another'))
        self.assertEqual(self.ledger.snapshot(self.req['root_id'])['reserved_total'],1)

    def test_P06_claim_then_controller_crash_is_not_redispatched(self):
        self.probe.prepare(self.req)
        original=self.probe._check
        def crash(req,owner=None):
            if owner:raise RuntimeError('synthetic crash after durable claim')
            return original(req,owner)
        with patch.object(self.probe,'_check',side_effect=crash),self.assertRaisesRegex(RuntimeError,'synthetic crash'):
            self.probe.launch(self.req)
        saved=self.original_files();second=self.second()
        self.assertTrue(second.run(self.req)['needs_reconcile'])
        self.assertEqual(saved,self.original_files());self.assert_no_target()
        with self.assertRaises(Stopped):self.ledger.reserve(self.req['root_id'],'different',phase='A',input_sha256='1'*64)

    def test_P06_incomplete_control_setup_is_retained_and_never_reclaimed(self):
        self.probe.prepare(self.req)
        with patch.object(self.probe.runner,'_save_lifecycle',side_effect=OSError('synthetic setup seal fault')):
            with self.assertRaisesRegex(OSError,'setup seal fault'):self.probe.launch(self.req)
        self.assertFalse(self.probe.runner.owners)
        saved=self.original_files()
        self.assertTrue(any(name.endswith('owner.json') for name in saved))
        other=self.second()
        with patch.object(other.runner,'_control',side_effect=AssertionError('reclaim incomplete setup')):
            self.assertTrue(other.run(self.req)['needs_reconcile'])
        self.assertEqual(saved,self.original_files());self.assert_no_target()

    def test_P08_cancelled_root_before_control_has_no_owner_or_target(self):
        self.probe.prepare(self.req);self.ledger.cancel(self.req['root_id'])
        with patch.object(self.probe.runner,'_control',side_effect=AssertionError('control after stop')),self.assertRaises(Stopped):self.probe.launch(self.req)
        self.assertEqual(self.original_files(),{});self.assert_no_target()

    def tree_ready(self,controller,future):
        end=time.monotonic()+2  # readiness deadline, not a worker watchdog
        path=self.data/'runs'/str(controller.rid)/'attempts/0001/output.bin'
        while time.monotonic()<end:
            if path.exists():
                lines=path.read_bytes().splitlines()
                for line in lines:
                    try:value=json.loads(line)
                    except ValueError:continue
                    if value.get('kind')=='synthetic_tree_ready':
                        self.assertEqual(len(set(value['pids'])),3)
                        ps=subprocess.run(['ps','-o','pid=,ppid=','-p',','.join(map(str,value['pids']))],capture_output=True,text=True,check=True)
                        pairs={int(a):int(b) for a,b in (x.split() for x in ps.stdout.splitlines())}
                        parent=value['pids'][0];others=set(value['pids'][1:])
                        self.assertEqual(sum(pairs[p]==parent for p in others),1)
                        self.assertEqual(sum(pairs[p] in others for p in others),1)
                        (self.folder/'tree-ready.json').write_text(json.dumps({'ready':value,'ppids':pairs}))
                        return value['pids']
            if future.done():future.result()
            time.sleep(.01)
        self.fail('three real generations not ready within 2 seconds')

    def assert_tree_cleaned(self,controller,pids,reason):
        part=self.data/'runs'/str(controller.rid)/'attempts/0001'
        process=json.loads((part/'process.json').read_text())
        self.assertEqual(process['reason'],reason)
        self.assertTrue(process['cleanup']['complete'])
        self.assertFalse(process['cleanup']['remaining_group'])
        self.assertEqual(len(list(part.parent.iterdir())),1)
        life=X.learning_runs._sealed_run(self.P,controller.rid)
        self.assertEqual(life['owner'],json.loads((part.parents[1]/'owner.json').read_text()))
        for pid in pids:
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_P09_original_deadline_charges_preflight_then_times_out_real_tree(self):
        controller=self.second(mode='tree')
        now=time.time_ns()//1000;spec=dict(self.spec,root_id='9'*64)
        controller.ledger.register(spec,starts_us=now,deadline_us=now+3_000_000)
        req=dict(self.req,root_id=spec['root_id'])
        original=controller._capture
        def delay(*args,**kw):
            time.sleep(.35)
            return original(*args,**kw)
        with patch.object(controller,'_capture',side_effect=delay):controller.prepare(req)
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            f=pool.submit(controller.launch,req)
            try:
                pids=self.tree_ready(controller,f)
                with self.assertRaises(Conflict):f.result(timeout=8)
            finally:
                if not f.done():controller.ledger.cancel(req['root_id'])
        self.assert_tree_cleaned(controller,pids,'timeout')
        process=json.loads((self.data/'runs'/str(controller.rid)/'attempts/0001/process.json').read_text())
        self.assertLess(process['timeout_seconds'],2.65)
        self.assertEqual(controller.ledger.snapshot(req['root_id'])['root']['deadline_us'],now+3_000_000)
        self.assertIsNone(controller._row(req)['producer_observation'])

    def test_P09_running_cancel_cleans_three_real_generations(self):
        controller=self.second(mode='tree');controller.prepare(self.req)
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            f=pool.submit(controller.launch,self.req)
            try:
                pids=self.tree_ready(controller,f)
                controller.ledger.cancel(self.req['root_id'])
                with self.assertRaises(Conflict):f.result(timeout=8)
            finally:
                if not f.done():controller.ledger.cancel(self.req['root_id'])
        self.assert_tree_cleaned(controller,pids,'cancelled')
        self.assertEqual(controller.ledger.snapshot(self.req['root_id'])['attempts'][0]['state'],'unknown')

    def test_P06_same_controller_active_replay_does_not_stop_authority_watch(self):
        controller=self.second(mode='tree');controller.prepare(self.req)
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            f=pool.submit(controller.launch,self.req)
            try:
                pids=self.tree_ready(controller,f)
                self.assertTrue(controller.launch(self.req)['needs_reconcile'])
                self.assertFalse(controller._done.is_set(),'readonly replay disabled active watcher')
                controller.ledger.cancel(self.req['root_id'])
                with self.assertRaises(Conflict):f.result(timeout=8)
            finally:
                if not f.done():
                    controller.ledger.cancel(self.req['root_id'])
                    controller._stop('cancelled')  # fixture cleanup even for a deliberately broken watcher
        self.assert_tree_cleaned(controller,pids,'cancelled')

    def test_P10_durable_owner_change_after_actual_spawn_stops_target(self):
        from tmh.platform import supervised_process
        controller=self.second(mode='tree');controller.prepare(self.req)
        original=supervised_process.run_supervised;spawned=[]
        def invoke(*args,**kw):
            on_spawn=kw['on_spawn']
            def changed(pid,pgid):
                on_spawn(pid,pgid);spawned.append(pid)
                self.store.x("UPDATE codex_learning_dispatch SET launch_claim=?",('{"synthetic_changed_owner":true}',))
            kw['on_spawn']=changed
            return original(*args,**kw)
        with patch.object(supervised_process,'run_supervised',side_effect=invoke),self.assertRaises(Conflict):controller.launch(self.req)
        self.assertEqual(len(spawned),1)
        self.assert_tree_cleaned(controller,spawned,'cancelled')
        self.assertIsNone(controller._row(self.req)['producer_observation'])

    def test_P10_epoch_revocation_after_actual_on_spawn_stops_and_cleans(self):
        from tmh.platform import supervised_process
        controller=self.second(mode='tree');controller.prepare(self.req)
        original=supervised_process.run_supervised;spawned=[]
        def invoke(*args,**kw):
            on_spawn=kw['on_spawn']
            def revoke(pid,pgid):
                on_spawn(pid,pgid);spawned.append(pid)
                self.change('password_reset',user='owner',password='synthetic-reset-not-for-login')
            kw['on_spawn']=revoke
            return original(*args,**kw)
        with patch.object(supervised_process,'run_supervised',side_effect=invoke),self.assertRaises(Conflict):controller.launch(self.req)
        self.assertEqual(len(spawned),1)
        self.assert_tree_cleaned(controller,spawned,'cancelled')
        self.assertIsNone(controller._row(self.req)['producer_observation'])

    def test_P10_owner_loss_cannot_reclaim_between_check_and_run_command(self):
        self.probe.prepare(self.req)
        original=self.probe.runner.run_command
        def lose(*args,**kw):
            self.probe.runner._release(self.probe.rid)
            return original(*args,**kw)
        with patch.object(self.probe.runner,'run_command',side_effect=lose),self.assertRaisesRegex(Conflict,'reclaim forbidden'):
            self.probe.launch(self.req)
        self.assert_no_target()
        self.assertTrue(self.probe._row(self.req)['launch_claim'])

    def test_P10_owner_loss_after_actual_on_spawn_stops_and_cleans(self):
        from tmh.platform import supervised_process
        controller=self.second(mode='tree');controller.prepare(self.req)
        original=supervised_process.run_supervised;spawned=[]
        def invoke(*args,**kw):
            on_spawn=kw['on_spawn']
            def release(pid,pgid):
                on_spawn(pid,pgid);spawned.append(pid)
                controller.runner._release(controller.rid)
            kw['on_spawn']=release
            return original(*args,**kw)
        with patch.object(supervised_process,'run_supervised',side_effect=invoke),self.assertRaises(Conflict):controller.launch(self.req)
        self.assertEqual(len(spawned),1)
        self.assert_tree_cleaned(controller,spawned,'cancelled')
        self.assertEqual(controller.runner.controls[controller.rid]['stopped_reason'],'owner_lost')
        self.assertIsNone(controller._row(self.req)['producer_observation'])

    def assert_fault_replay_preserves(self):
        self.assertIsNone(self.probe._row(self.req)['producer_observation'])
        snap=self.ledger.snapshot(self.req['root_id']);self.assertEqual(snap['reserved_total'],1)
        self.assertIn(snap['attempts'][0]['state'],('intent','unknown'))
        saved=self.original_files();other=self.second()
        with patch.object(other.runner,'_control',side_effect=AssertionError('recontrol after completion fault')):
            self.assertTrue(other.run(self.req)['needs_reconcile'])
        self.assertEqual(saved,self.original_files())
        with self.assertRaises(Conflict):self.ledger.reserve(self.req['root_id'],'next-slot',phase='A',input_sha256='2'*64)

    def test_P10_terminal_row_before_finished_lifecycle_failure_preserves_intent(self):
        self.probe.prepare(self.req)
        original=self.probe.runner._save_lifecycle
        def fail(rid):
            if self.probe.runner.controls[rid]['finished']:raise OSError('synthetic terminal seal fault')
            return original(rid)
        with patch.object(self.probe.runner,'_save_lifecycle',side_effect=fail),self.assertRaisesRegex(OSError,'terminal seal fault'):
            self.probe.launch(self.req)
        self.assertEqual(self.store.run(self.probe.rid)['status'],'done')
        self.assertFalse(json.loads((self.data/'runs'/str(self.probe.rid)/'lifecycle.json').read_text())['finished'])
        self.assert_fault_replay_preserves()

    def test_P10_sealed_files_observation_write_failure_rolls_back_settlement(self):
        self.probe.prepare(self.req)
        self.store.x("CREATE TRIGGER deny_observation BEFORE UPDATE OF producer_observation ON codex_learning_dispatch BEGIN SELECT RAISE(ABORT,'synthetic observation fault'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'observation fault'):self.probe.launch(self.req)
        self.assertTrue(X.learning_runs._sealed_run(self.P,self.probe.rid)['finished'])
        self.assert_fault_replay_preserves()

    def test_P10_sealed_files_real_busy_commit_preserves_unsettled_intent(self):
        self.probe.prepare(self.req)
        reader=sqlite3.connect(self.store.path);self.addCleanup(reader.close)
        self.store.db.execute('PRAGMA busy_timeout=0')
        original=X.learning_runs._sealed_run
        def hold(*args):
            life=original(*args)
            reader.execute('BEGIN');reader.execute('SELECT * FROM runs').fetchall()
            return life
        with patch.object(X.learning_runs,'_sealed_run',side_effect=hold),self.assertRaises(sqlite3.OperationalError) as error:
            self.probe.launch(self.req)
        self.assertEqual(error.exception.sqlite_errorcode,sqlite3.SQLITE_BUSY)
        self.assertFalse(self.store.db.in_transaction);reader.rollback()
        self.assert_fault_replay_preserves()

    def test_P08_cancel_before_control_and_early_stop_during_control_start_zero(self):
        self.probe.prepare(self.req)
        original=self.probe.runner._control
        def early(*args,**kw):
            self.probe._stop('cancelled')
            return original(*args,**kw)
        with patch.object(self.probe.runner,'_control',side_effect=early),self.assertRaises(Stopped):self.probe.launch(self.req)
        self.assertTrue(self.probe.runner.controls[self.probe.rid]['event'].is_set())
        self.assert_no_target();self.assertEqual(self.ledger.snapshot(self.req['root_id'])['reserved_total'],1)

    def test_P11_synthetic_settlement_never_confers_execution_or_adoption(self):
        result=self.probe.run(self.req);snapshot=self.ledger.snapshot(self.req['root_id'])
        self.assertEqual(snapshot['attempts'][0]['state'],'settled')
        for obj in (result,result['observation'],snapshot):
            for key in ('producer_authenticated','execution_admitted','adoptable'):self.assertIs(obj[key],False)
            self.assertIsNone(obj.get('task_acceptance'))
        self.assertIsNone(result['actual_codex_exec_count']);self.assertIsNone(result['actual_cost'])
        self.assertEqual(snapshot['usage']['status'],'unknown')

    def test_P12_namespace_and_no_public_integration(self):
        before={r['name'] for r in self.store.q("SELECT name FROM sqlite_master WHERE name LIKE 'rsi_prepare_%'")}
        self.probe.run(self.req)
        self.assertEqual(before,{r['name'] for r in self.store.q("SELECT name FROM sqlite_master WHERE name LIKE 'rsi_prepare_%'")})
        root=Path(__file__).resolve().parents[1]
        for p in (root/'tmh').rglob('*.py'):
            if p.name=='codex_dispatch_probe.py':continue
            self.assertNotIn('codex_dispatch_probe',p.read_text(),str(p))
