"""Offline tests for the local-model RSI baseline harness.

Nothing here runs Ollama: the client takes injectable HTTP transports and
``run_task`` takes an injected client, so parser / metrics / degradation /
tuning-decision behaviour is tested deterministically with fixture responses.
"""
import importlib.util
import json
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BENCH = ROOT / "benchmarks"
sys.path.insert(0, str(ROOT))

# benchmarks/ is not a package: load the module by path so the tests do not need
# to change sys.path in a way that could shadow other modules.
spec = importlib.util.spec_from_file_location("rsi_local_eval", BENCH / "rsi_local_eval.py")
rsi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rsi)

FILES = [
    "src/main/java/com/acme/oa/service/ExpenseService.java",
    "src/main/java/com/acme/oa/service/LeaveService.java",
    "src/main/java/com/acme/oa/controller/LeaveController.java",
    "src/main/resources/mapper/LeaveMapper.xml",
    "pom.xml",
]
TASK = {"id": "t01", "query": "报销单提交金额上限要改",
        "gold": ["src/main/java/com/acme/oa/service/ExpenseService.java", "pom.xml"]}


class FakeClient:
    def __init__(self, content="", error="", error_kind="", latency=1.0, completion=7):
        self.content, self.error, self.error_kind = content, error, error_kind
        self.latency, self.completion = latency, completion
        self.seen = []

    def chat(self, messages, max_tokens=None, think=None):
        self.seen.append({"messages": messages, "max_tokens": max_tokens, "think": think})
        return {"content": self.content, "latency_s": self.latency, "prompt_tokens": 42,
                "completion_tokens": self.completion, "done_reason": "stop",
                "error": self.error, "error_kind": self.error_kind}


class ParserTest(unittest.TestCase):
    def test_bare_json_array_with_full_paths(self):
        files, err = rsi.parse_file_list(json.dumps(TASK["gold"]), FILES)
        self.assertEqual(err, "")
        self.assertEqual(files, TASK["gold"])

    def test_fenced_and_prose_wrapped_array(self):
        text = "分析如下：\n```json\n[\"src/main/java/com/acme/oa/service/ExpenseService.java\"]\n```\n以上。"
        files, err = rsi.parse_file_list(text, FILES)
        self.assertEqual(err, "")
        self.assertEqual(files, ["src/main/java/com/acme/oa/service/ExpenseService.java"])

    def test_object_with_files_key(self):
        files, err = rsi.parse_file_list('{"files": ["pom.xml", "pom.xml"]}', FILES)
        self.assertEqual(err, "")
        self.assertEqual(files, ["pom.xml"], "duplicates must collapse")

    def test_bare_file_name_and_windows_separators_are_resolved(self):
        files, _ = rsi.parse_file_list('["LeaveService.java", "mapper\\\\LeaveMapper.xml"]', FILES)
        self.assertEqual(files, ["src/main/java/com/acme/oa/service/LeaveService.java",
                                 "src/main/resources/mapper/LeaveMapper.xml"])

    def test_unmatched_path_is_kept_as_hallucination(self):
        files, err = rsi.parse_file_list('["src/main/java/com/acme/oa/NoSuchFile.java"]', FILES)
        self.assertEqual(err, "")
        self.assertEqual(files, ["src/main/java/com/acme/oa/NoSuchFile.java"])

    def test_empty_and_malformed_answers_are_counted_not_raised(self):
        self.assertEqual(rsi.parse_file_list(""), ([], "empty"))
        self.assertEqual(rsi.parse_file_list("   "), ([], "empty"))
        self.assertEqual(rsi.parse_file_list("这个需求信息不足，无法判断。", FILES), ([], "parse"))
        self.assertEqual(rsi.parse_file_list('["broken",', FILES), ([], "parse"))

    def test_empty_json_array_is_a_valid_but_empty_answer(self):
        self.assertEqual(rsi.parse_file_list("[]", FILES), ([], ""))


class PromptTest(unittest.TestCase):
    def test_pack_prompt_contains_pack_and_requirement(self):
        messages = rsi.build_messages(TASK, "pack-4000", "知识页：ExpenseService.java")
        self.assertEqual(len(messages), 1)
        content = messages[0]["content"]
        self.assertIn("ExpenseService.java", content)
        self.assertIn(TASK["query"], content)
        self.assertIn("JSON", content)

    def test_cold_prompt_has_no_retrieved_context(self):
        content = rsi.build_messages(TASK, "cold")[0]["content"]
        self.assertIn(TASK["query"], content)
        self.assertNotIn("知识页", content)
        self.assertNotIn("src/main", content)

    def test_unknown_condition_is_rejected(self):
        with self.assertRaises(ValueError):
            rsi.build_messages(TASK, "pack-999")


class MetricsTest(unittest.TestCase):
    def sample(self, condition="cold", recall=0.5, precision=0.5, exact=0.0, files=None,
               latency=1.0, parse_error="", completion=10, effective=5):
        files = ["a.py"] if files is None else files
        return {"task_id": "t01", "condition": condition, "query": "q", "gold": ["a.py", "b.py"],
                "files": files, "raw": "", "error": "", "error_kind": "", "parse_error": parse_error,
                "done_reason": "stop", "recall": recall, "precision": precision, "exact": exact,
                "hallucinated": [], "latency_s": latency, "prompt_tokens": 100,
                "completion_tokens": completion, "effective_output_tokens": effective,
                "prompt_estimate_tokens": 90, "pack_chars": 0}

    def test_summarize_counts_failures_and_keeps_them_in_recall(self):
        samples = [self.sample(recall=1.0, exact=1.0),
                   self.sample(recall=0.0, parse_error="empty", files=[]),
                   self.sample(recall=0.5, parse_error="request_timeout", files=[]),
                   self.sample(recall=0.0, files=[])]
        s = rsi.summarize(samples)
        self.assertEqual(s["n"], 4)
        self.assertEqual(s["recall_mean"], 0.375)
        self.assertEqual(s["answered"], 1)
        self.assertEqual(s["failures"], {"empty": 1, "request_timeout": 1})
        self.assertEqual(s["empty_answers"], 1)
        self.assertEqual(s["completion_tokens_mean"], 10.0)
        self.assertEqual(s["effective_output_tokens_mean"], 5.0)

    def test_run_task_scores_files_and_records_real_tokens(self):
        client = FakeClient(content=json.dumps(["src/main/java/com/acme/oa/service/ExpenseService.java"]))
        sample = rsi.run_task(client, TASK, "cold", Path(ROOT), FILES)
        self.assertEqual(sample["parse_error"], "")
        self.assertEqual(sample["recall"], 0.5)
        self.assertEqual(sample["precision"], 1.0)
        self.assertEqual(sample["exact"], 0.0)
        self.assertGreater(sample["effective_output_tokens"], 0)
        self.assertEqual(sample["prompt_tokens"], 42)
        self.assertEqual(sample["completion_tokens"], 7)

    def test_run_task_maps_request_errors(self):
        client = FakeClient(content="", error="timed out", error_kind="timeout")
        sample = rsi.run_task(client, TASK, "cold", Path(ROOT), FILES)
        self.assertEqual(sample["parse_error"], "request_timeout")
        self.assertEqual(sample["recall"], 0.0)
        self.assertEqual(sample["exact"], 0.0)

    def test_compare_applies_the_min_gain_rule(self):
        cold = rsi.summarize([self.sample(condition="cold", recall=0.10, exact=0.0)])
        better = rsi.summarize([self.sample(condition="pack-4000", recall=0.30, exact=0.5)])
        weaker = rsi.summarize([self.sample(condition="pack-8000", recall=0.11, exact=0.0)])
        comp = rsi.compare({"cold": cold, "pack-4000": better, "pack-8000": weaker})
        self.assertTrue(comp["context_helps"])
        self.assertAlmostEqual(comp["best_recall_gain"], 0.2)
        self.assertAlmostEqual(comp["per_condition"]["pack-4000"]["recall_delta_vs_cold"], 0.2)
        comp2 = rsi.compare({"cold": cold, "pack-4000": weaker})
        self.assertFalse(comp2["context_helps"], "0.01 gain is below the 0.05 rule")
        self.assertIn("未带来", comp2["conclusion"])


class ClientDegradationTest(unittest.TestCase):
    def test_available_reports_unreachable_daemon(self):
        def get(url, timeout):
            raise ConnectionError("refused")

        ok, detail = rsi.OllamaClient(get=get).available()
        self.assertFalse(ok)
        self.assertIn("不可达", detail)

    def test_available_reports_missing_model(self):
        ok, detail = rsi.OllamaClient(get=lambda url, timeout: {"models": [{"name": "other:1b"}]}).available()
        self.assertFalse(ok)
        self.assertIn("模型不存在", detail)

    def test_available_accepts_listed_model(self):
        ok, detail = rsi.OllamaClient(get=lambda url, timeout: {"models": [{"name": rsi.MODEL}]}).available()
        self.assertTrue(ok)
        self.assertEqual(detail, "ok")

    def test_chat_timeout_degrades(self):
        def post(url, payload, timeout):
            raise socket.timeout("timed out")

        reply = rsi.OllamaClient(post=post).chat([{"role": "user", "content": "x"}])
        self.assertEqual(reply["error_kind"], "timeout")
        self.assertEqual(reply["content"], "")
        self.assertIn("timed out", reply["error"])

    def test_chat_http_error_degrades(self):
        def post(url, payload, timeout):
            raise urllib.error.HTTPError(url, 500, "boom", {}, None)

        reply = rsi.OllamaClient(post=post).chat([{"role": "user", "content": "x"}])
        self.assertEqual(reply["error_kind"], "http_500")

    def test_chat_parses_native_response_and_forces_measured_parameters(self):
        seen = {}

        def post(url, payload, timeout):
            seen.update(payload)
            return {"message": {"content": '["pom.xml"]', "thinking": ""},
                    "prompt_eval_count": 74, "eval_count": 27, "done_reason": "stop"}

        client = rsi.OllamaClient(post=post)
        reply = client.chat([{"role": "user", "content": "x"}], max_tokens=512)
        self.assertEqual(reply["error"], "")
        self.assertEqual(reply["prompt_tokens"], 74)
        self.assertEqual(reply["completion_tokens"], 27)
        self.assertEqual(seen["think"], False, "thinking must stay off or the whole budget burns on reasoning")
        self.assertEqual(seen["options"]["temperature"], 0.0)
        self.assertEqual(seen["options"]["num_predict"], 512)
        self.assertEqual(seen["stream"], False)


class TuningDecisionTest(unittest.TestCase):
    def fake_measure(self, table):
        return lambda params: table[json.dumps(params, sort_keys=True)]

    def test_negative_gain_is_not_adopted(self):
        from tmh.context_quality import tune_lexical

        base = {"recall@5": 0.50, "recall@10": 0.70, "tokens_mean": 100.0}
        flat = {"recall@5": 0.505, "recall@10": 0.70, "tokens_mean": 101.0}
        table = {"{}": base, json.dumps({"length_norm": 0.35}, sort_keys=True): flat}
        res = tune_lexical(Path(ROOT), {"queries": []},
                           grid=({"name": "ln035", "params": {"length_norm": 0.35}},),
                           measure=self.fake_measure(table))
        self.assertFalse(res["decision"]["adopted"])
        self.assertIn("recall@5", "；".join(res["decision"]["reasons"]))

    def test_token_blowup_is_not_adopted(self):
        from tmh.context_quality import tune_lexical

        base = {"recall@5": 0.50, "recall@10": 0.70, "tokens_mean": 100.0}
        fat = {"recall@5": 0.60, "recall@10": 0.80, "tokens_mean": 130.0}
        table = {"{}": base, json.dumps({"length_norm": 0.35}, sort_keys=True): fat}
        res = tune_lexical(Path(ROOT), {"queries": []},
                           grid=({"name": "ln035", "params": {"length_norm": 0.35}},),
                           measure=self.fake_measure(table))
        self.assertFalse(res["decision"]["adopted"])
        self.assertIn("token", "；".join(res["decision"]["reasons"]))

    def test_real_gain_within_budget_is_adopted(self):
        from tmh.context_quality import tune_lexical

        base = {"recall@5": 0.50, "recall@10": 0.70, "tokens_mean": 100.0}
        win = {"recall@5": 0.53, "recall@10": 0.72, "tokens_mean": 104.0}
        table = {"{}": base, json.dumps({"length_norm": 0.35}, sort_keys=True): win}
        res = tune_lexical(Path(ROOT), {"queries": []},
                           grid=({"name": "ln035", "params": {"length_norm": 0.35}},),
                           measure=self.fake_measure(table))
        self.assertTrue(res["decision"]["adopted"])
        self.assertEqual(res["decision"]["winner"], "ln035")
        self.assertTrue(res["configs"][0]["best"])


class DefaultParamsTest(unittest.TestCase):
    def test_search_defaults_are_the_historical_baseline(self):
        from tmh.context import SEARCH_PARAMS

        self.assertEqual(SEARCH_PARAMS["length_norm"], 0.5)
        self.assertEqual(SEARCH_PARAMS["title_hit_boost"], 0.6)
        self.assertEqual(SEARCH_PARAMS["domain_keep"], 1.5)
        self.assertEqual(SEARCH_PARAMS["domain_penalty"], 0.6)
        self.assertEqual(SEARCH_PARAMS["type_weight"]["page"], 1.6)
        self.assertEqual(SEARCH_PARAMS["type_weight"]["flow"], 1.4)
        self.assertEqual(SEARCH_PARAMS["type_weight"]["fn"], 0.8)


class ProjectFilesTest(unittest.TestCase):
    def test_project_files_skips_metadata_directories(self):
        d = Path(tempfile.mkdtemp(prefix="rsi-files-"))
        (d / "a").mkdir()
        (d / "a" / "x.java").write_text("x", encoding="utf-8")
        (d / ".tmh").mkdir()
        (d / ".tmh" / "secret.md").write_text("s", encoding="utf-8")
        (d / ".git").mkdir()
        (d / ".git" / "HEAD").write_text("h", encoding="utf-8")
        self.assertEqual(rsi.project_files(d), ["a/x.java"])


if __name__ == "__main__":
    unittest.main()
