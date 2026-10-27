"""Real local SP processes through the carrier seam, never official CLI/model."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from tmh.platform import agents
from tmh.platform.codex_carrier import CarrierLaunch
from tmh.platform.learning_runs import IndependentRunner
from tmh.platform.store import Store
from tmh.platform.supervised_process import read_receipt


CHILD = '''import sys,json,time
prompt=sys.stdin.read()
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':prompt}}),flush=True)
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}),flush=True)
time.sleep(float(sys.argv[1]))
'''


class CodexCarrierTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-carrier-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.data = self.home / "data"
        self.root = self.home / "work"
        self.root.mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("CARRIER", "合成载体", str(self.root))
        self.settings = {"engine": "codex", "bin": sys.executable, "profile": "synthetic",
                         "prompt_transport": "stdin", "resume": False, "retry_busy": False,
                         "timeout": 10, "run_timeout": 10}
        self.contexts = []
        self.verified = []
        self.runners = []
        self.addCleanup(self.cleanup_runners)
        self.addCleanup(self.retain)

    def cleanup_runners(self):
        for runner, rid in self.runners:
            runner._release(rid)

    def retain(self):
        path = os.environ.get("TMH_CARRIER_TEST_SCENES")
        if path:
            dest = Path(path) / self._testMethodName
            shutil.copytree(self.home, dest, ignore=shutil.ignore_patterns("platform.db", "platform.db-wal", "platform.db-shm"))
            saved = sqlite3.connect(dest / "data/platform.db")
            try:
                self.store.db.backup(saved)
            finally:
                saved.close()

    def launch(self, *, sleep=0, verify=None, prepare=None, limit=10):
        def check(context, process, folder):
            self.verified.append((context, process, folder))
            receipt = read_receipt(folder, owner=dict(context.owner))
            self.assertEqual(receipt["returncode"], 0)
            self.assertTrue(receipt["cleanup"]["complete"])
            self.assertEqual((folder / "prompt.md").read_bytes(), context.prompt.encode())
            if verify:
                return verify(context, process, folder)

        def plan(context):
            self.contexts.append(context)
            if prepare:
                alternate = prepare(context)
                if alternate is not None:
                    return alternate
            return CarrierLaunch((sys.executable, "-I", "-S", "-c", CHILD, str(sleep)),
                                 {"PATH": os.defpath, "LANG": "C.UTF-8"}, check)

        runner = IndependentRunner(self.store, self.data, codex_carrier=SimpleNamespace(prepare=plan))
        prompt = "完整输入：\n" + "中文证据与规则\n" * 20000
        run = self.store.create_run(self.project["id"], None, "team-codex", "ask", "synthetic", prompt)
        rid = run["id"]
        self.store.update_run(rid, status="running")
        self.runners.append((runner, rid))
        conf = {"team-codex": dict(self.settings, run_timeout=limit, timeout=limit)}
        return runner, rid, prompt, conf

    def invoke(self, runner, rid, prompt, conf):
        code, result = runner.invoke(rid, self.project, None, "team-codex", conf, "ask", prompt,
                                     self.root, model="synthetic-model")
        return runner.finish_invocation(rid, code, result)

    def attempts(self, rid):
        p = self.data / "runs" / str(rid) / "attempts"
        return sorted(p.iterdir()) if p.exists() else []

    def test_actual_full_stdin_one_original_owner_attempt_and_terminal_parser(self):
        runner, rid, prompt, conf = self.launch()
        original = runner.run_command
        actual = []

        def execute(*args, **kw):
            pair = original(*args, **kw)
            actual.append(pair)
            return pair

        with mock.patch.object(runner, "run_command", side_effect=execute):
            final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["result"], prompt.strip())
        self.assertEqual(len(actual), 1)
        context, process, folder = self.verified[0]
        self.assertIsNot(process, actual[0][0])
        self.assertEqual(process, actual[0][0])
        self.assertEqual(folder, actual[0][1])
        self.assertEqual(context.model, "synthetic-model")
        self.assertRegex(context.launch_nonce, r"\A[0-9a-f]{32}\Z")
        self.assertIs(context.cancel_event, runner.controls[rid]["event"])
        self.assertEqual(dict(context.owner), runner.controls[rid]["owner"])
        self.assertEqual(context.deadline_monotonic, runner.controls[rid]["start"] + 10)
        self.assertEqual(len(self.attempts(rid)), 1)
        record = json.loads((folder / "process.json").read_text())
        self.assertEqual(record["prompt_transport"], ["stdin"])
        self.assertNotIn("--sandbox", record["command"])
        self.assertTrue(record["cleanup"]["complete"])
        self.assertNotIn(rid, runner.owners)

    def test_private_receipt_failure_preserves_raw_success_without_accepting_it(self):
        def reject(*args):
            raise OSError("synthetic private receipt mismatch")
        runner, rid, prompt, conf = self.launch(verify=reject)
        final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["status"], "failed")
        self.assertIn("private receipt mismatch", final["result"])
        self.assertEqual(len(self.attempts(rid)), 1)
        self.assertIn(b'"type": "turn.completed"', (self.attempts(rid)[0] / "output.bin").read_bytes())

    def test_verifier_cannot_replace_original_process_result(self):
        runner, rid, prompt, conf = self.launch(verify=lambda *a: object())
        final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["status"], "failed")
        self.assertEqual(len(self.attempts(rid)), 1)
        self.assertIn("不能替换", final["result"])

    def test_missing_carrier_never_executes_ordinary_command(self):
        runner = IndependentRunner(self.store, self.data)
        with mock.patch.object(runner, "run_command") as execute:
            with self.assertRaisesRegex(OSError, "缺少受信载体"):
                runner._run_model_process(19, ["must-not-run"], self.root,
                    engine="codex", settings=self.settings, model="synthetic")
        execute.assert_not_called()
        self.assertFalse((self.data / "runs/19/attempts").exists())
        sentinel = object()
        with mock.patch.object(runner, "run_command", return_value=sentinel) as ordinary:
            self.assertIs(runner._run_model_process(19, ["ordinary"], self.root,
                engine="claude", settings={}, model=""), sentinel)
        ordinary.assert_called_once_with(19, ["ordinary"], self.root)

    def test_verifier_mutation_cannot_change_original_result_or_published_records(self):
        def mutate(context, process, folder):
            process.elapsed = -123
            process.output = "FORGED RESULT"
            process.output_bytes = b"FORGED BYTES"
            process.cleanup["complete"] = False
        runner, rid, prompt, conf = self.launch(verify=mutate)
        actual = []
        original = runner.run_command
        def capture(*args, **kwargs):
            pair = original(*args, **kwargs)
            actual.append(pair)
            return pair
        with mock.patch.object(runner, "run_command", side_effect=capture):
            final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["result"], prompt.strip())
        process, folder = actual[0]
        self.assertGreaterEqual(process.elapsed, 0)
        self.assertNotEqual(process.output, "FORGED RESULT")
        self.assertNotEqual(process.output_bytes, b"FORGED BYTES")
        self.assertTrue(process.cleanup["complete"])
        self.assertEqual((folder / "output.bin").read_bytes(), process.output_bytes)
        record = json.loads((folder / "process.json").read_text())
        timing = json.loads((folder / "timing.json").read_text())
        self.assertEqual(record["elapsed_seconds"], process.elapsed)
        self.assertEqual(timing["process_seconds"], process.elapsed)
        self.assertTrue(record["cleanup"]["complete"])
        self.assertEqual(len(self.attempts(rid)), 1)

    def test_original_real_deadline_covers_late_receipt_verification(self):
        def late(context, *args):
            time.sleep(max(0, context.deadline_monotonic - time.monotonic()) + .03)
        runner, rid, prompt, conf = self.launch(verify=late, limit=2)
        final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["exit_code"], 124)
        self.assertEqual(runner.controls[rid]["stopped_reason"], "timeout")
        self.assertEqual(len(self.attempts(rid)), 1)
        self.assertEqual(len(self.verified), 1)

    def test_prepare_expiry_starts_no_process_or_fallback(self):
        def expire(context):
            time.sleep(max(0, context.deadline_monotonic - time.monotonic()) + .03)
        runner, rid, prompt, conf = self.launch(prepare=expire, limit=.15)
        final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["exit_code"], 124)
        self.assertEqual(self.attempts(rid), [])
        self.assertEqual(self.verified, [])

    def test_preparation_consumes_original_real_process_timeout(self):
        runner, rid, prompt, conf = self.launch(sleep=30, prepare=lambda c: time.sleep(.1), limit=2)
        final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["exit_code"], 124)
        self.assertEqual(runner.controls[rid]["stopped_reason"], "timeout")
        self.assertEqual(len(self.attempts(rid)), 1)
        folder = self.attempts(rid)[0]
        record = json.loads((folder / "process.json").read_text())
        self.assertLess(record["timeout_seconds"], 1.95)
        self.assertEqual(record["reason"], "timeout")
        self.assertTrue(record["cleanup"]["complete"])
        self.assertIn(b'"type": "turn.completed"', (folder / "output.bin").read_bytes())
        self.assertEqual(self.verified, [])

    def test_changed_limit_or_invalid_launch_cannot_start_or_fallback(self):
        for scenario in ("limit", "plan"):
            with self.subTest(scenario=scenario):
                runner, rid, prompt, conf = self.launch()
                def prepare(context):
                    if scenario == "limit":
                        runner.controls[rid]["timeout_seconds"] += 100
                        return CarrierLaunch((sys.executable,), {}, lambda *a: None)
                    return object()
                runner._codex_carrier.prepare = prepare
                final = self.invoke(runner, rid, prompt, conf)
                self.assertEqual(final["status"], "failed")
                self.assertEqual(self.attempts(rid), [])

    def test_retry_or_partial_input_is_rejected_before_preparation(self):
        runner, rid, prompt, conf = self.launch()
        base = dict(engine="codex", settings=conf["team-codex"], model="synthetic-model",
                    stdin=prompt, prompt=prompt, prompt_transport=["stdin"], kind="model:ask")
        for changed in ({"settings": dict(conf["team-codex"], retry_busy=True)},
                        {"settings": dict(conf["team-codex"], resume=True)},
                        {"stdin": "partial"}, {"prompt_transport": ["argv"]}):
            with self.subTest(changed=list(changed)):
                with self.assertRaisesRegex(OSError, "完整stdin"):
                    runner._run_model_process(rid, ["unused"], self.root, **dict(base, **changed))
        self.assertEqual(self.contexts, [])
        self.assertEqual(self.attempts(rid), [])

    def test_live_cancel_uses_original_event_and_cleans_one_real_process(self):
        runner, rid, prompt, conf = self.launch(sleep=30)
        runner._control(rid, conf, "team-codex")
        seen = threading.Event()
        values = []
        errors = []
        def work():
            try:
                values.append(runner._run_model_process(rid, ["unused-ordinary-command"], self.root,
                    engine="codex", settings=conf["team-codex"], model="synthetic-model",
                    stdin=prompt, prompt=prompt, prompt_transport=["stdin"],
                    on_output=lambda chunk: seen.set(), kind="model:ask"))
            except BaseException as e:
                errors.append(e)
        thread = threading.Thread(target=work)
        thread.start()
        ready = seen.wait(5)
        runner.cancel(rid, "synthetic")
        thread.join(5)
        self.assertTrue(ready, "actual supervised child must emit before cancellation")
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        process, folder = values[0]
        self.assertEqual(process.reason, "cancelled")
        self.assertTrue(process.cleanup["complete"])
        self.assertEqual(self.verified, [])
        self.assertEqual(len(self.attempts(rid)), 1)
        self.assertTrue(self.contexts[0].cancel_event.is_set())
        runner.finish_invocation(rid, process.returncode, process.output)

    def test_owner_change_during_prepare_refuses_without_reclaim_or_process(self):
        runner, rid, prompt, conf = self.launch()
        def changed(context):
            runner.controls[rid]["owner"] = dict(context.owner, token="changed")
        runner._codex_carrier.prepare = lambda context: (changed(context) or CarrierLaunch((sys.executable,), {}, lambda *a: None))
        final = self.invoke(runner, rid, prompt, conf)
        self.assertEqual(final["status"], "failed")
        self.assertEqual(self.attempts(rid), [])
        self.assertIn("所有权", final["result"])

    def test_ordinary_model_hook_forwards_original_arguments(self):
        runner = agents.Runner(self.store, self.data)
        sentinel = object()
        kw = dict(env={"SYNTHETIC": "value"}, stdin="complete", prompt="complete", prompt_transport=["stdin"])
        with mock.patch.object(runner, "run_command", return_value=sentinel) as execute:
            result = runner._run_model_process(9, ["ordinary"], self.root,
                        engine="claude", settings={}, model="", **kw)
        self.assertIs(result, sentinel)
        execute.assert_called_once_with(9, ["ordinary"], self.root, **kw)
