import json
import unittest
from pathlib import Path

from tests.test_rsi_preregistration import M, declared


def v2():
    v = declared();v['schema'] = M.SCHEMA_V2
    v['trial_policy'] = {'selection_mode':'single_candidate_before_BC','terminal_consumption':'once_per_root_family','root_budget_owner':'fixture-root','all_calls_in_root_budget':True,'all_started_denominator':True,'core_revoke_required':True,'fallback':'retain_baseline_without_adoption'}
    v['effect'] = {'mode':'quality_gain','primary_metric':'fixture-quality','metric_unit':'fixture-points','gain_metric':'quality','minimum_gain_micro_units':100,'quality_margin_micro_units':0,'max_cost_micro_cny':1000000,'max_latency_ms':10000,'minimum_samples':3,'evaluator_evidence_sha256':'a'*64,'production_input_equivalence_sha256':'b'*64}
    v['pilot_window'] = {'calendar_start':'2026-11-01T00:00:00+08:00','phase_end':'2026-11-15T00:00:00+08:00','followup_end':'2026-11-29T00:00:00+08:00','minimum_tasks':4,'minimum_cycles':2,'task_universe_sha256':v['pilot']['task_manifest_sha256'],'benefit_metric':'fixture-total-wait','measurement_unit':'milliseconds','minimum_benefit_micro_units':100,'role_cost_shift_limit_micro_units':0,'baseline_comparability_sha256':'c'*64}
    return v


class PreregistrationV2Tests(unittest.TestCase):
    def test_positive_declarations_still_no_scoring_or_execution(self):
        result = M.check(v2())
        self.assertEqual(result['status'], 'declared_complete',result)
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['evidence_verified'])
        self.assertIsNone(result['score'])

    def test_template_is_blocked_without_fabricating_numeric_thresholds(self):
        p=Path(__file__).resolve().parents[1]/'scripts/rsi/preregistration.v2.template.json'
        result=M.check(json.loads(p.read_text()))
        self.assertEqual(result['status'],'blocked',result)
        self.assertEqual(result['errors'],[])
        self.assertTrue(any('minimum_gain' in x for x in result['blockers']))

    def test_bc_cannot_be_used_to_choose_a_winner_or_refresh_root(self):
        for key,bad in [('selection_mode','pick_best_on_BC'),('terminal_consumption','once_per_request'),('all_calls_in_root_budget',False),('all_started_denominator',False),('core_revoke_required',False),('all_calls_in_root_budget',1)]:
            with self.subTest(key=key,bad=bad):
                v=v2();v['trial_policy'][key]=bad
                self.assertEqual(M.check(v)['status'],'invalid')

    def test_comparison_without_minimum_gain_or_full_input_proof_blocks(self):
        for key in ['minimum_gain_micro_units','production_input_equivalence_sha256','evaluator_evidence_sha256']:
            v=v2();v['effect'][key]=None
            self.assertEqual(M.check(v)['status'],'blocked')
        for bad in [0,True,float('nan'),-1]:
            v=v2();v['effect']['minimum_gain_micro_units']=bad
            self.assertEqual(M.check(v)['status'],'invalid')

    def test_mode_and_sample_minimum_cannot_be_weakened(self):
        v=v2();v['effect']['mode']='quality_noninferior_plus_cost_or_time_gain'
        self.assertEqual(M.check(v)['status'],'invalid')
        v['effect']['gain_metric']='total_cost'
        self.assertEqual(M.check(v)['status'],'declared_complete')
        v['effect']['minimum_samples']=2
        self.assertEqual(M.check(v)['status'],'invalid')
        v['effect']['minimum_samples']=4
        self.assertEqual(M.check(v)['status'],'blocked')

    def test_calendar_task_denominator_and_role_cost_bounds(self):
        for key,bad in [('phase_end','2026-11-02T00:00:00+08:00'),('followup_end','2026-11-01T00:00:00+08:00'),('task_universe_sha256','d'*64),('minimum_cycles',1),('minimum_benefit_micro_units',0),('role_cost_shift_limit_micro_units',True)]:
            with self.subTest(key=key):
                v=v2();v['pilot_window'][key]=bad
                self.assertEqual(M.check(v)['status'],'invalid')

    def test_v1_historical_format_remains_declaration_only(self):
        v=declared();self.assertEqual(M.check(v)['status'],'declared_complete')
        v['model']['api_key']='DO-NOT-STORE-CREDENTIALS'
        result=M.check(v);self.assertEqual(result['status'],'invalid')
        self.assertNotIn('DO-NOT-STORE-CREDENTIALS',json.dumps(result))
