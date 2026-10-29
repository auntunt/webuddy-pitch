"""A quality-stage reader must inspect the adopted candidate, never the moving main tree."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform.agents import Runner, git
from tmh.platform import learning as L, learning_decisions as D
from tmh.platform.store import Store


class DeliverySourceRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        (self.root / "value.txt").write_text("candidate contents\n")
        git(self.root, "init", "-q")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "candidate")
        self.commit = git(self.root, "rev-parse", "HEAD").strip()
        (self.root / "value.txt").write_text("main changed after candidate\n")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "later main")
        self.main = git(self.root, "rev-parse", "HEAD").strip()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("PIN", "固定版本检查", str(self.root))
        self.ticket = self.store.create_ticket(self.project["id"], "交付质量检查", "tester", auto=False)
        self.plan = self.store.create_run(self.project["id"], self.ticket["id"], "reader", "plan", "tester", "")
        self.plan_text = "绑定方案原文。" * 1500 + "方案末尾不可丢失。"
        self.store.update_run(self.plan["id"], status="done", exit_code=0, result=self.plan_text)
        self.impl = self.store.create_run(self.project["id"], self.ticket["id"], "reader", "fix", "tester", "")
        self.store.update_run(self.impl["id"], status="done", exit_code=0, decision="accepted:tmh/candidate@" + self.commit[:12])
        self.source = {"commit": self.commit, "implementation_run": self.impl["id"], "plan_run": self.plan["id"]}
        self.ticket = dict(self.ticket, links={"delivery": "test-delivery", "delivery_source": self.source})
        self.runner = Runner(self.store, self.data)
        self.script = self.data / "reader.py"
        self.script.write_text("import json,pathlib,subprocess\nprint(json.dumps({'cwd':str(pathlib.Path.cwd()),'value':pathlib.Path('value.txt').read_text(),'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'branch':subprocess.check_output(['git','rev-parse','--abbrev-ref','HEAD'],text=True).strip()}))\n")
        (self.data / "agents.json").write_text(json.dumps({"reader": {"cmd": [sys.executable, str(self.script)]}}))

    def start(self, **kwargs):
        return self.runner.start(self.project, self.ticket, "reader", "ask", "tester", question="核对实际候选", **kwargs)

    def wait(self, rid):
        end = time.monotonic() + 8
        while time.monotonic() < end:
            run = self.store.run(rid)
            if run["status"] not in ("queued", "running"):
                return run
            time.sleep(.01)
        self.fail("isolated reader did not finish")

    def source_record(self, rid):
        return json.loads((self.data / "runs" / str(rid) / "source.json").read_text())

    def active_policy(self):
        platform = SimpleNamespace(store=self.store, data_dir=self.data)
        revision = L.policy_create(platform, self.project, "main-budget", "主工作区预算", {"context_budget": 8000},
                                   "当前主工作区", "synthetic-human")
        self.store.x("INSERT INTO learning_policy_active VALUES(?,?,?)", (self.project["id"], revision["id"], "synthetic-human-decision"))
        self.assertEqual(D.runtime_policy(self.store, self.project)["status"], "active")
        return revision

    def test_fixed_source_runs_with_main_policy_using_its_actual_checkout_budget(self):
        policy = self.active_policy()
        run = self.wait(self.start()["id"])
        self.assertEqual(run["status"], "done", run["result"])
        result = json.loads(run["result"])
        self.assertEqual(result["commit"], self.commit)
        self.assertEqual(result["value"], "candidate contents\n")
        contexts = json.loads((self.data / "runs" / str(run["id"]) / "context.json").read_text())
        receipt = next(meta for meta in contexts if meta.get("mode") == "learning_policy")
        self.assertEqual(receipt["context_budget"], 6000)
        self.assertEqual(receipt["status"], "stale")
        self.assertEqual(receipt["revision_id"], policy["id"])
        self.assertEqual(Path(receipt["context_root"]), Path(run["workdir"]).resolve())
        self.assertTrue(self.source_record(run["id"])["code_unchanged"])
        self.assertFalse(Path(run["workdir"]).exists())

    def test_fixed_source_policy_receipt_rejects_unowned_context_roots(self):
        self.active_policy()
        foreign = self.data / "unowned-project"
        foreign.mkdir()
        for target in ("main", "foreign", "another-checkout"):
            with self.subTest(target=target):
                with mock.patch("tmh.platform.agents.threading.Thread") as thread:
                    other = self.start() if target == "another-checkout" else None
                    run = self.start()
                    args = thread.call_args.kwargs["args"]
                path = self.data / "runs" / str(run["id"]) / "context.json"
                contexts = json.loads(path.read_text())
                receipt = next(meta for meta in contexts if meta.get("mode") == "learning_policy")
                root = self.root if target == "main" else foreign if target == "foreign" else Path(other["workdir"])
                receipt.update(D.runtime_policy(self.store, dict(self.project, root=str(root))), context_root=str(root.resolve()))
                path.write_text(json.dumps(contexts))
                with mock.patch.object(self.runner, "invoke") as invoke:
                    self.runner._run(*args)
                    invoke.assert_not_called()
                failed = self.store.run(run["id"])
                self.assertEqual(failed["status"], "failed")
                self.assertIn("冻结提示词已停止", failed["result"])
                self.assertTrue(self.source_record(run["id"])["code_unchanged"])
                if other:
                    self.runner._release(other["id"])

    def test_fixed_source_policy_revocation_after_preparation_stops_execution(self):
        policy = self.active_policy()
        with mock.patch("tmh.platform.agents.threading.Thread") as thread:
            run = self.start()
            args = thread.call_args.kwargs["args"]
        platform = SimpleNamespace(store=self.store, data_dir=self.data)
        decision = D.decide(platform, self.project, "revoke", policy["id"], "alice", "stop-policy",
                            policy["id"], "停止使用当前策略")
        self.assertEqual(decision["status"], "applied")
        self.assertEqual(D.runtime_policy(self.store, self.project)["status"], "default")
        with mock.patch.object(self.runner, "invoke") as invoke:
            self.runner._run(*args)
            invoke.assert_not_called()
        failed = self.store.run(run["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("冻结提示词已停止", failed["result"])
        self.assertTrue(self.source_record(run["id"])["code_unchanged"])

    def test_real_process_reads_detached_candidate_and_keeps_provenance(self):
        later = self.store.create_run(self.project["id"], self.ticket["id"], "reader", "plan", "tester", "")
        self.store.update_run(later["id"], status="done", exit_code=0, result="UNRELATED-LATER-PLAN")
        (self.root / "value.txt").write_text("uncommitted user edits\n")
        with mock.patch("tmh.platform.agents.knowledge", side_effect=lambda root, query, **kwargs: "KNOWLEDGE:" + (root / "value.txt").read_text()):
            run = self.wait(self.start()["id"])
        self.assertEqual(run["status"], "done", run["result"])
        observed = json.loads(run["result"])
        self.assertEqual(observed["value"], "candidate contents\n")
        self.assertEqual(observed["commit"], self.commit)
        self.assertEqual(observed["branch"], "HEAD")
        self.assertNotEqual(Path(observed["cwd"]), self.root)
        evidence = self.source_record(run["id"])
        self.assertEqual(evidence["commit"], self.commit)
        self.assertEqual(evidence["actual_commit"], self.commit)
        self.assertEqual(evidence["after_commit"], self.commit)
        self.assertTrue(evidence["code_unchanged"])
        self.assertFalse(evidence["retained_worktree"])
        self.assertEqual(evidence["implementation_run"], self.impl["id"])
        self.assertEqual(evidence["plan_run"], self.plan["id"])
        self.assertEqual(evidence["binding"], self.source)
        self.assertFalse(Path(run["workdir"]).exists())
        self.assertEqual((self.root / "value.txt").read_text(), "uncommitted user edits\n")
        self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), self.main)
        self.assertIn("KNOWLEDGE:candidate contents", run["prompt"])
        self.assertNotIn("uncommitted user edits", run["prompt"])
        self.assertNotIn("UNRELATED-LATER-PLAN", run["prompt"])
        self.assertIn(self.plan_text, run["prompt"])
        self.assertNotIn("delivery_source", self.store.ticket(self.ticket["id"])["links"])

    def test_invalid_or_unowned_bindings_fail_before_starting_a_run(self):
        before = len(self.store.runs(project_id=self.project["id"]))
        blob = git(self.root, "rev-parse", "HEAD:value.txt").strip()
        other = self.store.create_ticket(self.project["id"], "另一工单", "tester", auto=False)
        foreign = self.store.create_run(self.project["id"], other["id"], "reader", "fix", "tester", "")
        self.store.update_run(foreign["id"], status="done", exit_code=0, decision="accepted:x@" + self.commit)
        before += 1
        for patch in ({"commit":"HEAD"}, {"commit":self.commit[:12]}, {"commit":"f"*40}, {"commit":blob},
                      {"commit":self.main}, {"implementation_run":True}, {"implementation_run":foreign["id"]}, {"plan_run":self.impl["id"]}):
            with self.subTest(patch=patch):
                ticket = dict(self.ticket, links=dict(self.ticket["links"], delivery_source=dict(self.source, **patch)))
                with self.assertRaises(ValueError):
                    self.runner.start(self.project, ticket, "reader", "ask", "tester", question="inspect")
        for kwargs in ({"base":"HEAD"}, {"session_id":3}):
            with self.assertRaises(ValueError):
                self.start(**kwargs)
        self.assertEqual(len(self.store.runs(project_id=self.project["id"])), before)
        self.assertEqual(git(self.root, "worktree", "list", "--porcelain").count("worktree "), 1)

    def test_mutating_reader_fails_and_retains_full_dirty_worktree(self):
        self.script.write_text("import pathlib\npathlib.Path('value.txt').write_text('changed by reader\\n')\npathlib.Path('new-evidence.txt').write_text('all unexpected content\\n')\nprint('original model conclusion preserved')\n")
        run = self.wait(self.start()["id"])
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 1)
        self.assertIn("original model conclusion preserved", run["result"])
        evidence = self.source_record(run["id"])
        self.assertFalse(evidence["code_unchanged"])
        self.assertTrue(evidence["retained_worktree"])
        self.assertIn("new-evidence.txt", evidence["after_status"])
        self.assertEqual((Path(run["workdir"]) / "new-evidence.txt").read_text(), "all unexpected content\n")
        self.assertIn("changed by reader", (self.data / "runs" / str(run["id"]) / "source-diff.patch").read_text())
        self.assertEqual((self.root / "value.txt").read_text(), "main changed after candidate\n")

    def test_preparation_failure_never_invokes_agent_or_falls_back_to_main(self):
        with mock.patch("tmh.platform.agents.pinned_view", side_effect=RuntimeError("checkout denied")), \
                mock.patch.object(self.runner, "invoke") as invoke:
            failed = self.start()
            self.assertEqual(failed["status"], "failed")
            self.assertIn("checkout denied", failed["result"])
            invoke.assert_not_called()
        run = self.store.runs(project_id=self.project["id"])[0]
        self.assertEqual(run["status"], "failed")
        evidence = self.source_record(run["id"])
        self.assertFalse(evidence["code_unchanged"])
        self.assertIn("checkout denied", evidence["checkout_error"])

    def test_prepared_checkout_changes_are_rejected_before_invoke(self):
        with mock.patch("tmh.platform.agents.threading.Thread") as thread:
            run = self.start()
            args = thread.call_args.kwargs["args"]
        workdir = Path(run["workdir"])
        (workdir / "value.txt").write_text("changed before invoke\n")
        with mock.patch.object(self.runner, "invoke") as invoke:
            self.runner._run(*args)
            invoke.assert_not_called()
        self.assertEqual(self.store.run(run["id"])["status"], "failed")
        self.assertFalse(self.source_record(run["id"])["code_unchanged"])
        self.assertTrue(workdir.exists())

    def test_concurrent_checks_have_independent_paths_and_caller_packet_is_frozen(self):
        packets = []
        with mock.patch("tmh.platform.agents.threading.Thread") as thread:
            one = self.start()
            packets.append(thread.call_args.kwargs["args"])
            two = self.start()
            packets.append(thread.call_args.kwargs["args"])
        self.assertNotEqual(one["workdir"], two["workdir"])
        self.source["commit"] = self.main
        entered = threading.Barrier(2)
        seen = []
        def inspect(rid, project, ticket, agent, conf, mode, prompt, workdir, *args, **kwargs):
            entered.wait(timeout=5)
            seen.append((rid, Path(workdir), git(Path(workdir), "rev-parse", "HEAD").strip()))
            self.assertTrue(all(Path(r["workdir"]).exists() for r in (one,two)))
            entered.wait(timeout=5)
            return 0, "fixed source inspected"
        with mock.patch.object(self.runner, "invoke", side_effect=inspect):
            threads = [threading.Thread(target=self.runner._run,args=args) for args in packets]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=8)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual({x[2] for x in seen}, {self.commit})
        for run in (one,two):
            self.assertEqual(self.store.run(run["id"])["status"], "done")
            self.assertTrue(self.source_record(run["id"])["code_unchanged"])

    def test_hex_named_branch_does_not_replace_the_requested_commit(self):
        git(self.root, "branch", self.commit[:12], self.main)
        git(self.root, "branch", self.commit, self.main)
        run = self.wait(self.start()["id"])
        self.assertEqual(run["status"], "done", run["result"])
        self.assertEqual(json.loads(run["result"])["commit"], self.commit)


if __name__ == "__main__":
    unittest.main()
