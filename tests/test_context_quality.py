"""Tests for the context-quality ruler and the optional PPR ranker.

They build a real knowledge base from ``examples/legacy-java-oa`` once (same
recipe as ``tests/test_context_pack.py``) and check three things:

1. the golden set really references ids the knowledge base produces, and is not
   a hand-written list of invented names;
2. the lexical baseline clears a floor derived from a real measurement (the
   numbers in ``tests/fixtures/context_golden.json`` are measured, not aspirational
   — the floors below are that baseline minus a safety margin);
3. PPR is an optional ranker: it computes a real distribution, is switchable on
   ``assemble(..., ranker="ppr")``, and never changes the default output.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tmh import kb  # noqa: E402
from tmh.context import (  # noqa: E402
    PPR_DAMPING, PPR_EDGE_WEIGHT, PPR_LEXICAL_MIX, PPR_MAX_ITER, PPR_MIN_REL,
    PPR_SEED_HITS, PPR_TOL, personalized_pagerank, search,
)
from tmh.context_pack import assemble, collect, rendered_text  # noqa: E402
from tmh.context_quality import (  # noqa: E402
    estimate_tokens, evaluate, known_ids, load_golden, pack_metrics, ranked_ids,
    retrieval_metrics, validate_golden,
)

JAVA = ROOT / "examples" / "legacy-java-oa"
GOLDEN = ROOT / "tests" / "fixtures" / "context_golden.json"

# Measured on this checkout with `benchmarks/run_context_quality.py`
# (lexical: recall@5 0.5866 / recall@10 0.7372 / precision@5 0.3769 / MRR 0.6728).
# The floors leave room for deliberate tuning and for a different machine, while a
# real regression (a whole flow/table dropping out) still fails the test.
FLOOR_RECALL5 = 0.55
FLOOR_RECALL10 = 0.70
FLOOR_PRECISION5 = 0.34
FLOOR_MRR = 0.62
FLOOR_COVERAGE_8K = 0.82
MAX_OMISSION_RATE = 0.02
MAX_TOKENS_MEAN_8K = 3000


def copy_repo(src: Path, prefix: str = "tmh-quality-test-") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    dst = d / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=dst, check=True)
    return dst


class ContextQualityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = copy_repo(JAVA)
        kb.build(cls.repo)
        cls.golden = load_golden(GOLDEN)
        # One full run, shared by the metric tests: 26 queries x 2 rankers x 2 budgets.
        cls.report = evaluate(cls.repo, cls.golden, rankers=("lexical", "ppr"), budgets=(4000, 8000))

    # ---- the golden set is real -----------------------------------------
    def test_golden_set_is_big_enough_and_well_formed(self):
        queries = self.golden["queries"]
        self.assertGreaterEqual(len(queries), 20)
        self.assertLessEqual(len(queries), 30)
        self.assertTrue(any("一" <= ch <= "鿿" for ch in queries[0]["query"]), "queries must be Chinese customer-style text")
        for q in queries:
            self.assertTrue(q["expect"], "every query needs expected ids: %r" % q["query"])
            self.assertGreaterEqual(len(q["expect"]), 2, "one expected id is too easy to game: %r" % q["query"])
            self.assertIn(q.get("budget", 8000), (4000, 8000))

    def test_every_expected_id_exists_in_the_knowledge_base(self):
        self.assertEqual(validate_golden(self.golden, self.repo), [],
                         "golden expectations must point at ids kb.build really produced")
        ids = known_ids(self.repo)
        expected = {eid for q in self.golden["queries"] for eid in q["expect"]}
        self.assertGreaterEqual(len(expected), 20)
        self.assertTrue(expected <= ids)

    def test_golden_set_covers_every_retrievable_kind(self):
        expected = {eid for q in self.golden["queries"] for eid in q["expect"]}
        kinds = {eid.split(":", 1)[0] for eid in expected}
        for kind, least in (("flow", 8), ("tbl", 5), ("fn", 8), ("cls", 1)):
            self.assertGreaterEqual(sum(1 for e in expected if e.startswith(kind + ":")), least,
                                    "golden set is skewed: too few %s ids" % kind)
        self.assertTrue(kinds <= {"flow", "tbl", "fn", "cls"})

    # ---- the lexical baseline is measured, not wished -------------------
    def test_lexical_baseline_clears_the_measured_floor(self):
        lex = self.report["rankers"]["lexical"]
        r = lex["retrieval"]
        self.assertGreaterEqual(r["recall@5"], FLOOR_RECALL5)
        self.assertGreaterEqual(r["recall@10"], FLOOR_RECALL10)
        self.assertGreaterEqual(r["precision@5"], FLOOR_PRECISION5)
        self.assertGreaterEqual(r["mrr"], FLOOR_MRR)
        packs = lex["packs"]["8000"]
        self.assertGreaterEqual(packs["coverage"], FLOOR_COVERAGE_8K)
        self.assertLessEqual(packs["budget_omission_rate"], MAX_OMISSION_RATE)
        self.assertLessEqual(packs["tokens_mean"], MAX_TOKENS_MEAN_8K)
        self.assertGreater(packs["tokens_per_needed_file"], 0)

    def test_metrics_are_per_query_and_deterministic(self):
        row = self.report["per_query"][0]
        self.assertEqual(set(self.report["rankers"]), {"lexical", "ppr"})
        self.assertEqual(row["id"], self.golden["queries"][0]["id"])
        ranks = row["rankers"]["lexical"]["ranks"]
        self.assertEqual(set(ranks), set(self.golden["queries"][0]["expect"]))
        # every rank is either None or a 1-based position; recall@5 is derivable from them
        for rank in ranks.values():
            self.assertTrue(rank is None or rank >= 1)
        derived = retrieval_metrics(ranks)
        self.assertEqual(derived, row["rankers"]["lexical"]["retrieval"])
        # the same query measured twice gives the same ranked ids and the same pack cost
        query = row["query"]
        self.assertEqual(ranked_ids(self.repo, query, limit=20), ranked_ids(self.repo, query, limit=20))
        self.assertEqual(pack_metrics(self.repo, query, row["expect"], budget=4000),
                         pack_metrics(self.repo, query, row["expect"], budget=4000))

    def test_pack_metrics_reflect_the_real_pack(self):
        query = "报销单提交不了，一直提示部门预算不足"
        expect = ["flow:post-expense-submit", "fn:ExpenseService.submit", "tbl:OA_BUDGET"]
        roomy = pack_metrics(self.repo, query, expect, ranker="lexical", budget=8000)
        self.assertEqual(roomy["budget"], 8000)
        self.assertLessEqual(roomy["used"], 8000)
        self.assertGreater(roomy["tokens"], 0)
        self.assertTrue(roomy["covered"], "a generous budget must surface the core ids")
        self.assertGreater(roomy["coverage"], 0)
        self.assertEqual(roomy["omitted"], [])
        tight = pack_metrics(self.repo, query, expect, ranker="lexical", budget=600)
        self.assertLessEqual(tight["used"], 600)
        self.assertGreater(tight["tokens"], 0)
        self.assertGreater(tight["budget_omission_rate"], 0, "a 600-char pack must report omissions")

    def test_token_estimate_is_documented_and_monotone(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("报销"), 2)  # one token per CJK character
        self.assertEqual(estimate_tokens("ExpenseService.submit"), 2)  # identifier part + method part
        self.assertLess(estimate_tokens("报销单"), estimate_tokens("报销单提交预算不足"))

    # ---- PPR is optional, bounded, and does not change the default ------
    def test_ppr_scores_are_a_real_distribution(self):
        seeds = [(d["id"], s) for s, d in search(self.repo, "请假审批通过以后审批人记在哪", limit=10)]
        first = personalized_pagerank(self.repo, seeds)
        self.assertTrue(first)
        self.assertAlmostEqual(sum(first.values()), 1.0, places=6)
        self.assertTrue(all(v >= 0 for v in first.values()))
        for nid, _ in seeds:
            if nid.split(":", 1)[0] in ("flow", "tbl", "fn", "cls", "dom", "mod"):
                self.assertIn(nid, first, "a graph seed must receive rank mass")
        self.assertEqual(first, personalized_pagerank(self.repo, seeds))
        self.assertEqual(personalized_pagerank(self.repo, []), {})
        # parameters are explicit, not magic numbers hidden in the loop
        self.assertEqual(PPR_DAMPING, 0.85)
        self.assertEqual(PPR_LEXICAL_MIX, 0.5)
        self.assertEqual(PPR_SEED_HITS, 10)
        self.assertEqual(PPR_TOL, 1e-9)
        self.assertEqual(PPR_MAX_ITER, 100)
        self.assertEqual(PPR_MIN_REL, 0.005)
        for kind in ("step", "calls", "uses", "in", "reads", "writes", "contains", "handles", "depends"):
            self.assertIn(kind, PPR_EDGE_WEIGHT)

    def test_default_ranker_output_is_identical_to_lexical(self):
        options = {"json_mode": True, "log": False, "budget": 4000}
        default = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                           "报销单财务审核驳回后预算", **options)
        explicit = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                            "报销单财务审核驳回后预算", ranker="lexical", **options)
        self.assertEqual(json.dumps(default, ensure_ascii=False, sort_keys=True),
                         json.dumps(explicit, ensure_ascii=False, sort_keys=True))
        self.assertEqual([i["id"] for i in collect(self.repo, "请假审批")],
                         [i["id"] for i in collect(self.repo, "请假审批", ranker="lexical")])

    def test_ppr_ranker_is_switchable_and_has_an_effect(self):
        lexical = [i["id"] for i in collect(self.repo, "财务审核驳回报销单以后冻结的预算怎么释放", ranker="lexical")]
        ppr = [i["id"] for i in collect(self.repo, "财务审核驳回报销单以后冻结的预算怎么释放", ranker="ppr")]
        self.assertTrue(ppr)
        self.assertNotEqual(lexical[:10], ppr[:10], "ranker=ppr must actually change the ordering")
        res = assemble([{"root": str(self.repo), "label": "oa", "current": True}],
                       "请假审批通过以后审批人记在哪", budget=6000, json_mode=True, log=False, ranker="ppr")
        self.assertTrue(res["items"])
        self.assertLessEqual(res["used"], 6000)
        self.assertTrue(all(i["id"].startswith("oa:") for i in res["items"]))
        self.assertTrue(all(i["full_text"] for i in res["items"]))
        for omission in res["omissions"]:
            self.assertTrue(omission["full_text"], "even PPR omissions keep a full-text handle")
        self.assertGreater(estimate_tokens(rendered_text(res)), 0)

    def test_unknown_ranker_is_rejected(self):
        with self.assertRaises(ValueError):
            collect(self.repo, "报销", ranker="bm25")
        with self.assertRaises(ValueError):
            assemble([{"root": str(self.repo), "label": "oa"}], "报销", ranker="bm25", log=False)


if __name__ == "__main__":
    unittest.main()
