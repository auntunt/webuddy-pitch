"""Real ledger/selector preparation; no model or provider is invoked."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import learn, learning as L, learning_eval as E
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.learning_eval_fixture import registered_job


class LessonInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lesson-inputs-')
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.root = self.data / 'repo'
        self.root.mkdir()
        self.store = Store(self.data / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.p = self.store.add_project('APP', 'APP', str(self.root))
        self.card = learn.add_lesson(self.data, dict(project='APP', ticket='APP-1', status='candidate',
            title='重复回调幂等处理', symptom='重复回调', fix='持久保存幂等键', verify='回调只执行一次',
            applicability='重复回调', non_applicability='独立业务事件', cause=None))
        self.capture()
        self.cases = [dict(id=str(i), input='重复回调幂等处理独立场景%d' % i,
            expected=['ORACLE-SENTINEL'], forbidden=['FORBIDDEN-SENTINEL'], validator='contains_all', generation=False) for i in range(3)]

    def capture(self):
        item = L._origin(self.P, self.p, 'lesson:' + self.card['id'])
        self.r = L.capture(self.P, self.p, item['key'], item['fingerprint'], 'writer')

    def options(self, cases=None):
        return E.validate_options(self.P, self.p, self.r, {'max_calls': 12, 'cases': cases or self.cases})

    def run_eval(self, options, calls):
        def step(role, prompt):
            calls.append((role, prompt))
            return 'ORACLE-SENTINEL' if role.endswith(':candidate') else 'unknown'
        return E.run(self.P, self.p, registered_job(self.P, self.p, self.r, options), step)

    def test_new_capture_preserves_missing_null_and_empty(self):
        content = json.loads(self.r['content'])
        self.assertNotIn('anti', content)
        self.assertIsNone(content['cause'])
        self.assertEqual(self.r['source']['lesson_content_schema'], 'lesson-content-v2')

    def test_unselected_candidate_is_not_forced_into_guidance(self):
        cases = [dict(c, input='XYZ-unrelated-only-%d' % i) for i,c in enumerate(self.cases)]
        options = self.options(cases)
        calls = []
        self.run_eval(options, calls)
        candidate_prompts = [p for role,p in calls if role.endswith(':candidate')]
        self.assertTrue(candidate_prompts)
        self.assertTrue(all('持久保存幂等键' not in p for p in candidate_prompts))

    def test_final_prompt_limit_preserves_pair_and_denominator(self):
        cases = [dict(c, input=c['input'] + '界' * 22000) for c in self.cases]
        options = self.options(cases)
        calls = []
        result = self.run_eval(options, calls)
        self.assertEqual(calls, [])
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['cases']), 3)
        self.assertEqual(result['reason'], 'input_limit')
        self.assertTrue(all(not r[s]['executed'] for r in result['cases'] for s in ('baseline','candidate')))

    def test_freeze_full_real_selected_payload_and_prompt(self):
        options = self.options()
        f = options['evaluation']
        self.assertEqual(f['schema'], 'learning-lesson-input-v2')
        for case in self.cases:
            row = f['inputs'][case['id']]
            self.assertTrue(row['intervention']['candidate_selected'])
            self.assertEqual(row['intervention']['kind'], 'incremental_injection')
            for side in ('baseline','candidate'):
                value = row[side]
                self.assertEqual(hashlib.sha256(value['prompt'].encode()).hexdigest(), value['prompt_sha256'])
                self.assertNotIn('ORACLE-SENTINEL', value['prompt'])
                self.assertNotIn('FORBIDDEN-SENTINEL', value['prompt'])
        self.assertFalse(f['evidence_scope']['rsi_qualified'])

    def test_pair_utf8_boundary_and_one_sided_limit(self):
        for size, permitted in ((65535, True), (65536, True), (65537, False)):
            value = E._pair_preflight('a' * size, 'b')
            self.assertEqual(value['execute_pair'], permitted)
            self.assertEqual(value['baseline_bytes'], size)
        self.assertFalse(E._pair_preflight('x', '界' * 21846)['execute_pair'])
        self.assertEqual(E._pair_preflight('界', '😀')['candidate_bytes'], 4)

    def test_preparation_does_not_write_business_ledger_or_tickets(self):
        paths = [self.data / learn.LESSONS, self.data / learn.LOG]
        before = [(p.exists(), p.read_bytes() if p.exists() else None) for p in paths]
        events = self.store.q('SELECT * FROM events')
        with patch.object(learn, 'note_used', side_effect=AssertionError('usage')), \
             patch.object(learn, '_note_once', side_effect=AssertionError('audit')):
            self.options()
        self.assertEqual(before, [(p.exists(), p.read_bytes() if p.exists() else None) for p in paths])
        self.assertEqual(events, self.store.q('SELECT * FROM events'))

    def test_frozen_prompt_and_currentness_ignore_new_cards_and_usage(self):
        options = self.options()
        before = copy.deepcopy(options)
        token = learn.revision_token(self.data, self.card['id'])
        learn._append_log(self.data, [{'kind':'outcome', 'id':self.card['id'], 'passed':True, 'ticket':'APP-2'}])
        self.assertEqual(token, learn.revision_token(self.data, self.card['id']))
        learn.add_lesson(self.data, dict(project='APP', ticket='APP-3', title='FUTURE-SECRET', fix='extra', status='active'))
        self.assertTrue(E.current(self.P, self.p, registered_job(self.P, self.p, self.r, options)))
        calls=[]
        self.run_eval(options,calls)
        self.assertEqual(options,before)
        self.assertTrue(all('FUTURE-SECRET' not in p for _,p in calls))
        # Different usage may change a newly prepared candidate payload, never the existing one.
        new = self.options()
        self.assertNotEqual(new['evaluation']['integrity_sha256'], options['evaluation']['integrity_sha256'])

    def test_any_frozen_prompt_or_contract_tampering_prevents_execution(self):
        original=self.options()
        for mutate in (
            lambda f: f['contract'].update(renderer='future'),
            lambda f: f['inputs']['0']['candidate'].update(prompt='replaced'),
            lambda f: f.update(integrity_sha256='0'*64),
            lambda f: f.update(schema='unknown'),
        ):
            value=copy.deepcopy(original);mutate(value['evaluation']);calls=[]
            with self.assertRaises(ApiError):self.run_eval(value,calls)
            self.assertEqual(calls,[])

    def test_candidate_only_overlay_preserves_attachments_and_null(self):
        # Append raw source fields without normalizing whitespace or duplicate filenames.
        raw=learn._raw(self.data)[0]
        raw.update(note='说明\r\n  ',diff='---\r\n+++\r\n  ',files=['same.py','same.py','last.py'])
        (self.root/'same.py').write_text('same')
        (self.root/'last.py').write_text('last')
        (self.data/learn.LESSONS).write_text(json.dumps(raw,ensure_ascii=True)+'\n')
        self.capture()
        options=self.options()
        row=options['evaluation']['inputs']['0']
        payload=row['candidate']['payloads'][0]
        self.assertEqual(payload['attachments']['files'],raw['files'])
        self.assertEqual(payload['attachments']['note'],raw['note'])
        self.assertIsNone(payload['content']['cause'])
        self.assertNotIn('anti',payload['content'])
        self.assertEqual(learn.lesson(self.data,self.card['id'])['status'],'candidate')

    def test_generation_cases_do_not_prepare_model_input(self):
        options=self.options([dict(c,generation=i==0) for i,c in enumerate(self.cases)])
        self.assertNotIn('0',options['evaluation']['inputs'])
        calls=[];result=self.run_eval(options,calls)
        self.assertEqual(len(calls),4)
        self.assertEqual(result['excluded_generation'],['0'])

    def test_captured_origin_outside_first_500_is_not_inserted(self):
        lines=(self.data/learn.LESSONS).read_text()
        for i in range(501):
            lines+=json.dumps(dict(id='L%d'%(i+2),project='APP',ticket='APP-%d'%(i+2),status='active',title='unrelated',fix='unrelated'))+'\n'
        (self.data/learn.LESSONS).write_text(lines)
        options=self.options()
        row=options['evaluation']['inputs']['0']
        self.assertTrue(row['intervention']['origin_outside_pool'])
        self.assertFalse(row['intervention']['candidate_selected'])
        self.assertEqual(len(options['evaluation']['pool']['local']),500)

    def test_single_candidate_arm_limit_never_calls_shorter_baseline(self):
        self.r = L.propose(self.P, self.p, self.r['id'], L.encoded({'fix':'持久保存幂等键'+'😀'*17000}), 'writer')
        options=self.options();calls=[];result=self.run_eval(options,calls)
        self.assertEqual(calls,[])
        self.assertEqual(result['planned_cases'],3)
        self.assertEqual(result['executed_pairs'],0)
        self.assertEqual(result['not_executed'],['0','1','2'])
        for row in options['evaluation']['inputs'].values():
            self.assertLess(row['preflight']['baseline_bytes'],65536)
            self.assertGreater(row['preflight']['candidate_bytes'],65536)
            self.assertIn('😀'*17000,row['candidate']['prompt'])

    def test_currentness_rejects_same_second_public_take_aba_without_private_leak(self):
        owner=learn.add_lesson(self.data,dict(project='OWNER',ticket='OWNER-1',title='OWNER-PRIVATE',
            fix='PRIVATE-FIX',applicability='PRIVATE-CONDITION',note='PRIVATE-NOTE',status='active'))
        with patch.object(learn,'now',return_value='2026-10-24T00:00:00'):
            learn.set_shared(self.data,owner['id'],True,'alice','重复回调幂等处理',{'fix':'重复回调使用幂等键'})
            learn.take_shared(self.data,owner['id'],'APP',True,'bob')
            options=self.options();f=options['evaluation']
            self.assertNotIn('PRIVATE',json.dumps(f['pool'],ensure_ascii=False))
            job=registered_job(self.P, self.p, self.r, options)
            self.assertTrue(E.current(self.P,self.p,job))
            learn.take_shared(self.data,owner['id'],'UNRELATED',True,'elsewhere')
            self.assertTrue(E.current(self.P,self.p,job))
            learn.take_shared(self.data,owner['id'],'APP',False,'bob')
            learn.take_shared(self.data,owner['id'],'APP',True,'bob')
            self.assertFalse(E.current(self.P,self.p,job))

    def test_invalid_proposed_utf8_is_diagnosed_before_revision_write(self):
        before=self.store.q('SELECT * FROM learning_revisions')
        with self.assertRaises(ApiError) as caught:
            L.propose(self.P,self.p,self.r['id'],json.dumps({'fix':'bad\ud800'}),'writer')
        self.assertEqual(caught.exception.code,400)
        self.assertEqual(before,self.store.q('SELECT * FROM learning_revisions'))

    def test_payload_and_render_receipts_must_agree_even_with_recomputed_outer_digest(self):
        original=self.options()
        for mutate in (
            lambda v:v.update(payload_sha256='f'*64),
            lambda v:v['payloads'][0]['content'].update(fix='unrendered body'),
        ):
            options=copy.deepcopy(original);f=options['evaluation'];mutate(f['inputs']['0']['candidate'])
            f['integrity_sha256']=E._integrity(f);calls=[]
            with self.assertRaises(ApiError):self.run_eval(options,calls)
            self.assertEqual(calls,[])

    def test_selected_unusable_managed_card_is_omitted_without_refill(self):
        cards=[]
        for n in range(4):
            cards.append(learn.add_lesson(self.data,dict(project='APP',ticket='OTHER-%d'%n,status='active',
                title='重复回调幂等处理',symptom='重复回调幂等处理',fix='重复回调幂等处理')))
        latest=cards[-1]
        # A real sealed ledger projection with unavailable DB revision models stale managed evidence.
        learn.project_revision(self.data,'APP',latest['id'],'LR-unavailable',
            {'title':latest['title'],'symptom':latest['symptom'],'fix':latest['fix']},'alice','synthetic-projection',
            learn.revision_token(self.data,latest['id']))
        row=self.options()['evaluation']['inputs']['0']['baseline']
        selected=[item['id'] for item in row['selected']]
        self.assertEqual(selected,[c['id'] for c in reversed(cards[1:])])
        self.assertEqual([item['id'] for item in row['included']],[cards[2]['id'],cards[1]['id']])
        self.assertEqual(row['omissions'],[{'scope':'local','id':latest['id'],'reason':'not_currently_usable'}])
        self.assertNotIn(cards[0]['id'],[p['origin_id'] for p in row['payloads']])

    def test_exact_final_prompt_utf8_limit_not_just_guidance_limit(self):
        original=self.options()['evaluation']['inputs']['0']['candidate']['prompt']
        size=len(original.encode('utf-8'))
        for target,executed in ((65535,True),(65536,True),(65537,False)):
            cases=[dict(c,input=c['input']+'q'*(target-size)) for c in self.cases]
            options=self.options(cases)
            for row in options['evaluation']['inputs'].values():
                self.assertTrue(row['intervention']['candidate_selected'])
                self.assertEqual(len(row['candidate']['prompt'].encode('utf-8')),target)
            calls=[];result=self.run_eval(options,calls)
            self.assertEqual(len(calls),6 if executed else 0)
            self.assertEqual(result['executed_pairs'],3 if executed else 0)
            self.assertEqual(result['planned_cases'],3)

    def test_null_title_kept_in_content_while_registry_label_remains_text(self):
        raw=learn._raw(self.data)[0];raw['title']=None
        (self.data/learn.LESSONS).write_text(json.dumps(raw)+'\n')
        self.capture()
        self.assertIsNone(json.loads(self.r['content'])['title'])
        self.assertEqual(self.r['title'],self.card['id'])

    def test_self_consistent_rewrite_cannot_change_actual_candidate_or_bound_pool(self):
        from tmh.platform import lesson_input as I
        original=self.options()
        rewrites=('payload','pool','candidate','evidence','origin')
        for name in rewrites:
            options=copy.deepcopy(original);f=options['evaluation']
            if name=='payload':
                v=f['inputs']['0']['candidate'];v['payloads'][0]['content']['fix']='NOT-THE-CAPTURED-REVISION'
                rendered=I.render_lessons(v['payloads']);v.update(guidance=rendered['text'],guidance_sha256=E._digest(rendered['text']),payload_sha256=rendered['payload_sha256'])
                v['prompt']=E._assemble_lesson_answer(f['cases'][0]['input'],f['evidence'],v['guidance']);v['prompt_sha256']=E._digest(v['prompt'])
                row=f['inputs']['0'];row['preflight']=E._pair_preflight(row['baseline']['prompt'],row['candidate']['prompt'])
            else:
                if name=='pool':f['pool']['local'][0]['note']='NOT-THE-CAPTURED-ATTACHMENT'
                elif name=='candidate':f['candidate_content']=L.encoded(dict(json.loads(f['candidate_content']),fix='NOT-THE-CAPTURED-REVISION'))
                elif name=='evidence':f['evidence'].append({'path':'injected.txt','content':'NOT-FIXED-EVIDENCE'})
                else:f['candidate_origin_id']='L-unrelated'
                f['inputs']=E._build_lesson_inputs(f['pool'],f['candidate_origin_id'],f['candidate_content'],f['cases'],f['evidence'])
            f['integrity_sha256']=E._integrity(f)
            job=registered_job(self.P, self.p, self.r, original)
            job['options']=options
            with self.subTest(rewrite=name):
                self.assertFalse(E.current(self.P,self.p,job))
                calls=[]
                with self.assertRaises(ApiError):self.run_eval(options,calls)
                self.assertEqual(calls,[])

    def test_v2_baseline_descriptor_is_lossless_while_legacy_keeps_literal_defaults(self):
        learn.set_status(self.data,self.card['id'],'active','alice')
        current=learn.lesson(self.data,self.card['id'])
        baseline=E._baseline(self.P,self.p,self.r)
        self.assertEqual(json.loads(baseline['content']),L.lesson_content(current,L.LESSON_CONTENT_SCHEMA))
        self.assertNotIn('anti',json.loads(baseline['content']))
        self.assertIsNone(json.loads(baseline['content'])['cause'])
        legacy=copy.deepcopy(self.r);legacy['source'].pop('lesson_content_schema')
        old=E._baseline(self.P,self.p,legacy)
        self.assertEqual(json.loads(old['content']),{k:current.get(k,'') for k in L.LESSON_FIELDS})
        self.assertIn('anti',json.loads(old['content']))

    def test_currentness_without_original_regular_lock_fails_without_writing(self):
        options=self.options();job=registered_job(self.P, self.p, self.r, options)
        lock=self.data/'lessons.lock';raw=(self.data/learn.LESSONS).read_bytes()
        self.assertTrue(E.current(self.P,self.p,job))
        lock.unlink()
        self.assertFalse(E.current(self.P,self.p,job))
        self.assertFalse(lock.exists())
        outside=self.data/'unrelated.lock';outside.write_bytes(b'untouched')
        lock.symlink_to(outside)
        self.assertFalse(E.current(self.P,self.p,job))
        self.assertTrue(lock.is_symlink());self.assertEqual(outside.read_bytes(),b'untouched')
        lock.unlink();lock.mkdir()
        self.assertFalse(E.current(self.P,self.p,job))
        self.assertTrue(lock.is_dir())
        self.assertEqual((self.data/learn.LESSONS).read_bytes(),raw)
