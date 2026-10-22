import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import learning as L, learning_eval as E, learning_runs as R, learn
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.root = self.data / "repo"
        self.root.mkdir()
        self.store = Store(self.data / "db")
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.p = self.store.add_project("APP", "APP", str(self.root))
        self.card = learn.add_lesson(self.data, {"project": "APP", "title": "修复", "symptom": "重复事件", "fix": "使用幂等键",
                                    "verify": "两次事件只执行一次", "applicability": "重复回调", "non_applicability": "独立业务事件",
                                    "status": "candidate", "ticket": "APP-1"})
        self.capture()
        self.cases = [{"id": str(i), "input": "独立的回调场景 %d" % i, "validator": "contains_all", "expected": ["EXACT_ORACLE"],
                       "forbidden": ["WRONG"], "generation": False} for i in range(3)]

    def capture(self):
        item = L.catalog(self.P, self.p)["items"][0]
        self.r = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        return self.r

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def options(self, cases=None):
        return E.validate_options(self.P, self.p, self.r, {"max_calls": 12, "cases": self.cases if cases is None else cases})

    def run_eval(self, f=None, step=None):
        opts = f or self.options()
        def default(role, prompt):
            return "EXACT_ORACLE" if role.endswith(":candidate") else "unknown_text"
        job = {"id": "j", "current_revision_id": self.r["id"], "options": opts}
        return E.run(self.P, self.p, job, step or default)

    def test_actual_assertions_pass_only_candidate_and_no_oracle_in_prompts(self):
        prompts = []
        def step(role, prompt):
            prompts.append((role, prompt))
            self.assertNotIn("EXACT_ORACLE", prompt)
            self.assertNotIn("WRONG", prompt)
            self.assertNotIn("validator", prompt)
            return "EXACT_ORACLE" if role.endswith(":candidate") else "unknown_text"
        result = self.run_eval(step=step)
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"], {"baseline": 0, "candidate": 3})
        self.assertIsNone(result["cost"]["amount"])
        self.assertEqual(len(prompts), 6)

    def test_frozen_inputs_do_not_read_later_active_memories_or_mutated_request(self):
        options = self.options()
        original = json.dumps(options, ensure_ascii=False)
        self.cases[0]["input"] = "later request"
        learn.add_lesson(self.data, {"project": "APP", "title": "FUTURE_SECRET", "fix": "later memory"})
        def step(role, prompt):
            self.assertNotIn("FUTURE_SECRET", prompt)
            self.assertNotIn("later request", prompt)
            return "EXACT_ORACLE" if role.endswith(":candidate") else "unknown_text"
        self.assertTrue(self.run_eval(options, step)["passed"])
        # The caller's raw cases are also frozen, not merely the internal cases list.
        self.assertEqual(json.dumps(options, ensure_ascii=False), original)

    def test_generation_and_insufficient_samples_cannot_qualify(self):
        cases = [dict(c, generation=(i == 0)) for i, c in enumerate(self.cases)]
        result = self.run_eval(self.options(cases))
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "insufficient")
        self.assertEqual(result["excluded_generation"], ["0"])
        self.assertEqual(len(result["cases"]), 2)

    def test_unexecuted_or_empty_output_is_never_success(self):
        self.assertFalse(self.run_eval(step=lambda *_: "")["passed"])
        def fail(*_):
            raise TimeoutError("real invocation failed")
        with self.assertRaises(TimeoutError):
            self.run_eval(step=fail)

    def test_negative_assertion_regression_and_equal_score_do_not_pass(self):
        for output in ("EXACT_ORACLE WRONG", "EXACT_ORACLE"):
            self.assertFalse(self.run_eval(step=lambda *_, value=output: value)["passed"])
        def regresses(role, prompt):
            return "EXACT_ORACLE" if role.endswith(":baseline") else "WRONG"
        result = self.run_eval(step=regresses)
        self.assertEqual(result["reason"], "regression")
        self.assertEqual(len(result["regressions"]), 3)

    def test_cost_limit_still_rejects_unbounded_candidate_output(self):
        result = self.run_eval(step=lambda role, _: "EXACT_ORACLE" * 1000 if role.endswith(":candidate") else "unknown_text")
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "cost_limit")

    def test_missing_generation_duplicate_inputs_and_budget_are_rejected(self):
        for cases in ([{k: v for k, v in self.cases[0].items() if k != "generation"}],
                      [self.cases[0], dict(self.cases[0], id="another")]):
            with self.assertRaises(ApiError):
                self.options(cases)
        with self.assertRaises(ApiError):
            E.validate_options(self.P, self.p, self.r, {"max_calls": 1, "cases": self.cases})

    def test_json_validator_keeps_boolean_numeric_types_distinct(self):
        c = {"validator": "json_equal", "expected": {"done": True}}
        self.assertTrue(E.check(c, '{"done":true}'))
        self.assertFalse(E.check(c, '{"done":1}'))
        self.assertFalse(E.check(c, 'not JSON'))

    def test_baseline_status_or_edit_changes_fail_currentness(self):
        job = {"current_revision_id": self.r["id"], "options": self.options()}
        self.assertTrue(E.current(self.P, self.p, job))
        learn.set_status(self.data, self.card["id"], "active", "human")
        self.assertFalse(E.current(self.P, self.p, job))

    def test_holdout_reservation_blocks_reuse_for_revised_content_and_rolls_back(self):
        options = self.options()
        with L.transaction(self.store) as db:
            E.reserve(self.P, self.p, self.r, options, "first", db)
        old = self.r
        value = json.loads(old["content"])
        value["fix"] += " 后续修订"
        self.r = L.propose(self.P, self.p, old["id"], L.encoded(value), "writer")
        options = self.options()
        with self.assertRaises(ApiError), L.transaction(self.store) as db:
            E.reserve(self.P, self.p, self.r, options, "second", db)
        self.assertEqual(len(self.store.q("SELECT * FROM learning_eval_cases")), 3)
        self.assertEqual({x["revision_id"] for x in self.store.q("SELECT * FROM learning_eval_cases")}, {old["id"]})

    def test_policy_requires_real_context_and_diverse_scenarios(self):
        self.r = L.policy_create(self.P, self.p, "budget", "预算", {"context_budget": 8000}, "问答", "writer")
        with self.assertRaises(ApiError):
            self.options()
        def fake_pack(P, p, q, budget):
            return {"text": "context %s" % budget, "digest": str(budget),
                    "receipt": {"budget": budget, "items": [str(budget)]}}
        with patch.object(E, "_pack", side_effect=fake_pack):
            options = self.options()
            self.assertFalse(self.run_eval(options)["passed"], "同一场景不足以采用策略")
            cases = [dict(c, scenario="failure" if i else "normal") for i, c in enumerate(self.cases)]
            options = self.options(cases)
            self.assertTrue(self.run_eval(options)["passed"])
            self.assertTrue(E.current(self.P, self.p, {"current_revision_id": self.r["id"], "options": options}))
        with patch.object(E, "_pack", return_value={"digest": "changed"}):
            self.assertFalse(E.current(self.P, self.p, {"current_revision_id": self.r["id"], "options": options}))

    def test_policy_pack_uses_runner_preparation_and_binds_revision_receipts(self):
        from tmh.graph import graph_path
        from tmh.platform import agents
        path = graph_path(self.root)
        path.parent.mkdir(parents=True)
        path.touch()
        pack = {"budget": 8000, "items": [{"id": "fact-one", "render": "完整事实正文"}],
                "omissions": [{"id": "fact-two", "reason": "source_or_confirmation_changed",
                               "full_text": "保留的完整读取指令"}], "complete": False}
        revisions = [{"kind": "fact", "revision_id": "r1", "included": True}]
        with patch.object(agents, "prepared_context_pack", return_value=(pack, revisions, "实际 Runner 完整输入")) as prepare:
            first = E._pack(self.P, self.p, "问题", 8000)
        prepare.assert_called_once_with(Path(self.p["root"]), "问题", 8000, store=self.store, project=self.p)
        self.assertEqual(first["text"], "实际 Runner 完整输入")
        self.assertEqual(first["receipt"], dict(pack, learning_revisions=revisions))
        self.assertEqual(first["digest"], L.digest(first["receipt"]))
        self.assertNotIn("learning_revisions", pack)
        changed = [{"kind": "fact", "revision_id": "r1", "included": False}]
        with patch.object(agents, "prepared_context_pack", return_value=(pack, changed, "实际 Runner 完整输入")):
            second = E._pack(self.P, self.p, "问题", 8000)
        self.assertNotEqual(first["digest"], second["digest"])


if __name__ == "__main__":
    unittest.main()
