import unittest
from tmh.platform.fixloop import verification_outcome, repair_attempts, failure_signature


class ReliabilityOutcomes(unittest.TestCase):
    def test_blocked_execution_never_becomes_a_code_repair(self):
        self.assertEqual(verification_outcome({'check':'fail','verdict':'fail','commands':[{'verification_state':'blocked'}]}), 'blocked')

    def test_exhausted_budget_is_technical_processing_not_acceptance(self):
        self.assertEqual(verification_outcome({'check':'fail','verdict':'fail','repair_stop':'task_budget'}), 'technical_required')
        self.assertEqual(verification_outcome({'check':'pass','verdict':'pass'}), 'review_required')

    def test_new_run_keeps_same_requirement_budget(self):
        previous = {'verification_contract':'same', 'round_evidence':[{}, {}], 'check':'fail'}
        self.assertEqual(repair_attempts([(2, previous), (1, previous)], 'same'), 4)
        self.assertEqual(repair_attempts([(2, previous)], 'changed'), 0)
        self.assertEqual(repair_attempts([(3,dict(previous,check='pass',verdict='pass')),(2,previous)], 'same'), 0)

    def test_repeated_failure_signature_excludes_timing(self):
        command = {'kind':'test','command':'test','exit_code':1,'output':'wrong total','seconds':1}
        signature = failure_signature([command], {'blocking':[{'ac':'A1','scenario':'wrong total'}]})
        self.assertEqual(signature, failure_signature([dict(command,seconds=20)], {'blocking':[{'ac':'A1','scenario':'wrong total'}]}))
        self.assertNotEqual(signature, failure_signature([dict(command,output='new failure')], {'blocking':[]}))


class CliExecutionEvidence(unittest.TestCase):
    def test_missing_baseline_and_build_only_are_not_complete_validation(self):
        import tempfile, subprocess, sys, shlex
        from pathlib import Path
        from tmh import config
        from tmh.verify import verify, take_baseline
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text("answer = 42\n")
            for args in (["init", "-q"], ["add", "app.py"], ["-c","user.name=test","-c","user.email=test@example.invalid","commit","-qm","base"]):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            cfg = config.load(root)
            cfg["commands"]["build"] = shlex.quote(sys.executable) + " -c " + shlex.quote("print('build completed')")
            config.save(root, cfg)
            first = verify(root)
            self.assertFalse(first["passed"])
            self.assertFalse(first["tests_ran"])
            self.assertEqual(first["commands"][0]["exit_code"], 0)
            take_baseline(root)
            second = verify(root)
            self.assertFalse(second["passed"])
            self.assertFalse(second["tests_ran"])
            self.assertEqual(second["outcome"], "blocked")


class RepairStopIntegration(unittest.TestCase):
    def run_loop(self, previous, rounds):
        import json, tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest import mock
        from tmh.platform.fixloop import FixLoop
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name)
        folder = data / 'runs/77'
        folder.mkdir(parents=True)
        loop = FixLoop.__new__(FixLoop)
        loop.r, loop.rid, loop.t = SimpleNamespace(data_dir=data), 77, None
        loop.p, loop.base, loop.wt = {'key':'fixture'}, 'baseline', data
        loop.set = {'rounds':rounds, 'split_from':3}
        loop.box, loop.nobuild, loop.ok = None, '', True
        loop.remote_testing = False
        loop.brought, loop.log, loop.notes = set(), [], {}
        loop.commands = mock.Mock(return_value=([('test','fixture-check')],''))
        loop.baseline = mock.Mock(return_value='')
        loop.execute = mock.Mock(return_value=[{'kind':'test','command':'fixture-check','exit_code':1,'output':'wrong total'}])
        loop.cancelled = mock.Mock(return_value=False)
        loop.whole, loop.say = mock.Mock(), mock.Mock()
        loop.diagnose = mock.Mock(return_value={'verdict':'fail','blocking':[{'ac':'A1','scenario':'wrong total'}]})
        loop.earlier_fixes = mock.Mock(return_value=previous)
        with mock.patch('tmh.platform.fixloop.worktree_diff',return_value='diff --git a/app.py b/app.py\n+edit'), mock.patch('tmh.platform.fixloop.verification_contract',return_value='contract'), mock.patch('tmh.platform.fixloop.git',return_value='baseline'):
            loop.run()
        return loop, json.loads((folder/'verify.json').read_text())

    def test_restart_with_exhausted_budget_never_calls_writer(self):
        loop, report = self.run_loop([(3,{}),(2,{'verification_contract':'contract','round_evidence':[{},{}]})],1)
        loop.whole.assert_not_called()
        self.assertEqual(report['outcome'],'technical_required')
        self.assertEqual(report['repair_budget']['previous_attempts'],2)

    def test_repeated_failure_stops_before_large_budget(self):
        loop, report = self.run_loop([],8)
        self.assertEqual(loop.whole.call_count,3)
        self.assertEqual(report['repair_stop'],'repeated_failure')
        self.assertEqual(report['outcome'],'technical_required')
        self.assertEqual(len(report['round_evidence']),3)
