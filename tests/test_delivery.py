"""A delivery executes one real step; drafts, human review and runtime evidence stay distinct."""
import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform import delivery
from tmh.platform.agents import Runner
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


GOOD_VERIFY = {"check": "pass", "verdict": "pass", "files": ["app.py"], "beyond_plan": [],
               "commands": [{"name": "test", "cmd": "python3 -m unittest", "exit_code": 0, "output": "OK"}]}
DIFF = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"


class RecordingRunner:
    """Persist the real run shape without invoking any model or remote service."""
    def __init__(self, store):
        self.store, self.calls = store, []

    def start(self, project, ticket, agent, mode, by, **kwargs):
        self.calls.append(dict(project=project, ticket=ticket, agent=agent, mode=mode, by=by, **kwargs))
        return self.store.create_run(project["id"], ticket["id"], agent, mode, by, kwargs["question"],
                                     model=kwargs.get("model") or "")


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-delivery-test-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.store.add_project("APP", "应用", str(self.data))
        self.store.add_project("OTHER", "其他项目", str(self.data))
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, runner=RecordingRunner(self.store), project=self.project)
        self.fake = self.data / "fake_agent.py"
        self.fake.write_text("import sys\np=open(sys.argv[2], encoding='utf-8').read()\n"
                             "assert sys.argv[1]=='ask' and '当前只执行交付工作项' in p\n"
                             "print('真实本地进程产物：正文与依据。')\n", encoding="utf-8")
        (self.data / "agents.json").write_text(json.dumps({"local-test": {"cmd": [sys.executable, str(self.fake), "{mode}", "{prompt_file}"]}}))

    def project(self, key):
        p = self.store.project(key)
        if not p:
            raise ApiError(404, "项目不存在")
        return p

    def create(self, stages=None, **extra):
        body = {"project": "APP", "title": "完整业务闭环", "goal": "用户提交后可以查到记录", **extra}
        if stages is not None:
            body["stages"] = stages
        return delivery.create(self.P, body, "Li")["delivery"]["id"]

    def act(self, did, action, stage=None, **body):
        return delivery.act(self.P, did, dict(action=action, stage=stage, **body), "Li")

    def rows(self, did):
        return {r["key"]: r for r in delivery.view(self.P, did)["stages"]}

    def save(self, did, key, body=None):
        return self.act(did, "save_artifact", key, body=body or key + "完整内容")

    def review(self, did, key):
        version = self.rows(did)[key]["artifact"]["version"]
        return self.act(did, "review_artifact", key, version=version, confirm=True, evidence="Li 已逐条核对正文及对应证据")

    def reviewed(self, did, key, body=None):
        self.save(did, key, body)
        return self.review(did, key)

    def assert_error(self, code, fn, *args, **kwargs):
        with self.assertRaises(ApiError) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.code, code, str(cm.exception))
        return str(cm.exception)

    def start(self, did, key, mode=None):
        body = dict(agent="local-test")
        if mode:
            body["mode"] = mode
        return self.act(did, "start", key, **body)["started_run"]

    def finish(self, rid, status="done", exit_code=0, result="运行产物", verify=None, diff=DIFF):
        r = self.store.run(rid)
        self.store.update_run(rid, status=status, exit_code=exit_code, result=result, diff=diff if r["mode"] == "fix" else "")
        if r["mode"] == "fix":
            path = self.data / "runs" / str(rid)
            path.mkdir(parents=True, exist_ok=True)
            (path / "verify.json").write_text(json.dumps(GOOD_VERIFY if verify is None else verify), encoding="utf-8")

    def collected(self, did, key, mode=None, **finish):
        rid = self.start(did, key, mode)
        self.finish(rid, **finish)
        self.act(did, "collect", key, run_id=rid)
        return rid

    def code_ready(self, stages=None):
        did = self.create(stages or ["requirements", "design", "develop", "quality", "security"])
        self.reviewed(did, "requirements", "A1：提交成功后必须能查询。")
        self.reviewed(did, "design", "接口、数据与异常处理的完整设计。")
        return did

    def plan_ready(self):
        did = self.code_ready()
        self.collected(did, "develop", "plan", result="实现方案及 A1 检查命令")
        self.review(did, "develop")
        return did

    def test_catalog_all_types_persist_and_create_does_not_run(self):
        cat = delivery.catalog()
        self.assertEqual(len(cat["stages"]), 8)
        self.assertEqual(len(cat["types"]), 12)
        for kind in cat["types"]:
            did = self.create(type=kind["key"])
            detail = delivery.view(self.P, did)
            ticket = self.store.ticket(detail["delivery"]["ticket_id"])
            self.assertEqual(ticket["links"]["delivery"], did)
            self.assertEqual(ticket["links"]["hold"], "交付工作项:" + did)
            self.assertEqual(bool(ticket["links"].get("greenfield")), kind["key"] == "new_product")
            self.assertEqual([r["key"] for r in detail["stages"]], kind["stages"])
        self.assertEqual(self.P.runner.calls, [])
        self.assertEqual(self.store.runs(), [])
        reopened = Store(self.data / "platform.db")
        self.addCleanup(reopened.db.close)
        p2 = SimpleNamespace(data_dir=self.data, store=reopened)
        self.assertEqual(len(delivery.list_deliveries(p2)["deliveries"]), 12)

    def test_get_and_prompt_reads_do_not_write_business_records(self):
        did = self.create(["requirements", "design"])
        self.reviewed(did, "requirements")
        changes = self.store.db.total_changes
        for _ in range(3):
            delivery.view(self.P, did)
            delivery.list_deliveries(self.P, "APP")
            delivery.prompt_context(self.data, did)
        self.assertEqual(changes, self.store.db.total_changes)
        self.assertEqual(delivery.list_deliveries(self.P, "OTHER")["deliveries"], [])
        self.assertEqual(delivery.view(self.P, did)["delivery"]["state"], "draft")

    def test_invalid_create_is_rejected_before_partial_business_writes(self):
        delivery.list_deliveries(self.P)
        variants = [{"project": "MISSING"}, {"type": "invented"}, {"title": "x" * 161}, {"goal": "x" * 24001},
                    {"stages": ["develop"]}, {"stages": ["research", "research"]}, {"stages": []},
                    {"ticket": []}, {"ticket": 0}, {"ticket": -1}, {"ticket": "bad"}]
        for extra in variants:
            body = {"project": "APP", "title": "x", **extra}
            with self.subTest(extra=extra):
                self.assert_error(404 if extra.get("project") == "MISSING" else 400, delivery.create, self.P, body, "Li")
        self.assertEqual(self.store.tickets(), [])
        self.assertEqual(delivery.list_deliveries(self.P)["deliveries"], [])
        self.assert_error(404, delivery.view, self.P, "not-an-id")
        self.assert_error(404, delivery.view, self.P, "0" * 12)

    def test_artifact_revision_history_and_explicit_human_review(self):
        did = self.create(["research"])
        body = "完整内容" * 10000 + "末尾不丢失"
        self.save(did, "research", body)
        self.assertEqual(self.rows(did)["research"]["state"], "draft")
        for by, evidence, confirm in [("codex", "依据", True), ("agent", "依据", True), ("SYSTEM", "依据", True),
                                      ("local-test", "依据", True), ("Li", "", True), ("Li", "依据", False)]:
            self.assert_error(400, delivery.act, self.P, did, dict(action="review_artifact", stage="research", version=1,
                                                               confirm=confirm, evidence=evidence), by)
        self.review(did, "research")
        self.assertEqual(self.rows(did)["research"]["state"], "approved")
        self.save(did, "research", "新正文")
        row = self.rows(did)["research"]
        self.assertEqual(row["history"][0]["body"], body)
        self.assertIsNone(row["review"])
        self.assertEqual(row["state"], "draft")
        self.assert_error(409, self.act, did, "review_artifact", "research", version=1, confirm=True, evidence="旧版本")
        self.assert_error(400, self.save, did, "research", "x" * (delivery.MAX_BODY + 1))
        self.assertEqual(self.rows(did)["research"]["artifact"]["version"], 2)

    def test_transitive_review_changes_never_resurrect_downstream_review(self):
        did = self.create(["requirements", "design", "release", "feedback"])
        for key in ("requirements", "design", "release", "feedback"):
            self.reviewed(did, key, "唯一内容：" + key)
        old = self.rows(did)
        self.reviewed(did, "requirements", "新验收 A2")
        self.review(did, "design")  # same artifact, new review of the changed requirements
        rows = self.rows(did)
        self.assertEqual(rows["design"]["artifact"]["id"], old["design"]["artifact"]["id"])
        self.assertNotEqual(rows["design"]["review"]["id"], old["design"]["review"]["id"])
        self.assertEqual(rows["release"]["state"], "review")
        self.assertIsNone(rows["feedback"]["review"])
        ctx = delivery.prompt_context(self.data, did)
        self.assertIn("唯一内容：design", ctx)
        self.assertNotIn("唯一内容：release", ctx)
        self.assertNotIn("唯一内容：feedback", ctx)
        self.review(did, "release")
        self.assertEqual(self.rows(did)["feedback"]["state"], "review")
        self.review(did, "feedback")
        self.assertEqual(delivery.view(self.P, did)["delivery"]["state"], "approved")

    def test_plan_review_allows_fix_but_only_verified_fix_review_unlocks_quality(self):
        did = self.code_ready()
        self.assert_error(409, self.start, did, "develop", "fix")
        plan = self.collected(did, "develop", "plan", result="已审核实现方案")
        self.assert_error(409, self.start, did, "develop", "fix")
        self.review(did, "develop")
        rows = self.rows(did)
        self.assertTrue(rows["develop"]["plan_approved"])
        self.assertEqual(rows["develop"]["state"], "draft")
        self.assertEqual(rows["develop"]["allowed_modes"], ["plan", "fix"])
        self.assertFalse(rows["quality"]["can_start"])
        self.assertFalse(rows["security"]["can_start"])
        self.assertEqual(delivery.view(self.P, did)["delivery"]["current_stage"], "develop")
        self.assertIn("方案已复核，尚未实现", delivery.prompt_context(self.data, did))
        fix = self.collected(did, "develop", "fix", result="实际实现结果")
        self.assertFalse(self.rows(did)["quality"]["can_start"])
        self.review(did, "develop")
        rows = self.rows(did)
        self.assertEqual(rows["develop"]["state"], "approved")
        self.assertFalse(rows["develop"]["plan_approved"])
        self.assertTrue(rows["quality"]["can_start"])
        self.assertTrue(rows["security"]["can_start"])
        self.assertEqual(rows["develop"]["runs"][0]["verification"], GOOD_VERIFY)
        self.assertEqual(rows["develop"]["artifact"]["source_run"], fix)
        self.assertEqual(rows["develop"]["history"][0]["source_run"], plan)

    def test_manual_develop_document_cannot_fake_an_implementation(self):
        did = self.code_ready()
        self.save(did, "develop", "我声称已经实现并测试了全部需求")
        row = self.rows(did)["develop"]
        self.assertFalse(row["can_review"])
        self.assert_error(409, self.review, did, "develop")
        self.assertEqual(row["allowed_modes"], ["plan"])
        self.assertFalse(self.rows(did)["quality"]["can_start"])

    def test_fix_pins_the_reviewed_plan_even_if_ticket_has_a_newer_unreviewed_plan(self):
        did = self.plan_ready()
        detail = delivery.view(self.P, did)["delivery"]
        reviewed = self.rows(did)["develop"]["artifact"]["source_run"]
        unrelated = self.store.create_run(self.project("APP")["id"], detail["ticket_id"], "local-test", "plan", "Li", "未复核计划")
        self.finish(unrelated["id"], result="未复核的另一个计划")
        self.assertIn("fix", self.rows(did)["develop"]["allowed_modes"])
        self.start(did, "develop", "fix")
        packet = self.P.runner.calls[-1]["ticket"]
        self.assertEqual(packet["links"]["delivery_plan_run"], reviewed)
        self.assertNotEqual(reviewed, unrelated["id"])
        self.assertNotIn("delivery_plan_run", self.store.ticket(detail["ticket_id"])["links"])

    def test_exit_zero_with_failed_missing_skipped_or_out_of_scope_verification_cannot_pass(self):
        cases = [{}, {**GOOD_VERIFY, "check": "fail"}, {**GOOD_VERIFY, "check": "skip"},
                 {**GOOD_VERIFY, "verdict": "fail"}, {**GOOD_VERIFY, "verdict": "unknown"}, {**GOOD_VERIFY, "files": []},
                 {**GOOD_VERIFY, "commands": []}, {**GOOD_VERIFY, "commands": [{"exit_code": 2}]},
                 {**GOOD_VERIFY, "beyond_plan": ["unplanned.py"]}]
        for verify in cases:
            with self.subTest(verify=verify):
                did = self.plan_ready()
                self.collected(did, "develop", "fix", verify=verify)
                row = self.rows(did)["develop"]
                self.assertEqual(row["state"], "review")
                self.assertFalse(row["can_review"])
                self.assert_error(409, self.review, did, "develop")
                self.assertFalse(self.rows(did)["quality"]["can_start"])
        did = self.plan_ready()
        self.collected(did, "develop", "fix", diff="")
        self.assertFalse(self.rows(did)["develop"]["can_review"])

    def test_recheck_changes_revoke_implementation_and_downstream_reviews(self):
        did = self.plan_ready()
        rid = self.collected(did, "develop", "fix", result="实现证据正文")
        self.review(did, "develop")
        self.reviewed(did, "quality", "质量证据正文")
        changed = copy.deepcopy(GOOD_VERIFY)
        changed["commands"][0]["output"] = "different fresh output; still pass"
        (self.data / "runs" / str(rid) / "verify.json").write_text(json.dumps(changed))
        rows = self.rows(did)
        self.assertIsNone(rows["develop"]["review"])
        self.assertIsNone(rows["quality"]["review"])
        self.assertNotIn("实现证据正文", delivery.prompt_context(self.data, did))
        self.review(did, "develop")
        self.assertIsNone(self.rows(did)["quality"]["review"])
        changed["check"] = "fail"
        (self.data / "runs" / str(rid) / "verify.json").write_text(json.dumps(changed))
        self.assertFalse(self.rows(did)["develop"]["can_review"])

    def test_updated_spec_requires_new_code_run_not_review_of_old_code(self):
        did = self.plan_ready()
        self.collected(did, "develop", "fix")
        self.review(did, "develop")
        self.reviewed(did, "quality")
        self.reviewed(did, "requirements", "更新的验收约定")
        self.review(did, "design")
        self.assert_error(409, self.review, did, "develop")
        self.assertFalse(self.rows(did)["quality"]["can_start"])
        self.assertEqual(self.rows(did)["develop"]["allowed_modes"], ["plan"])

    def test_start_one_stage_collect_full_output_idempotently_without_auto_review(self):
        did = self.create(["research", "requirements"])
        rid = self.start(did, "research")
        call = self.P.runner.calls[0]
        self.assertEqual(call["mode"], "ask")
        self.assertIn("当前只执行交付工作项", call["question"])
        rows = self.rows(did)
        self.assertEqual(rows["research"]["state"], "running")
        self.assertFalse(rows["requirements"]["can_start"])
        self.assertTrue(rows["requirements"]["run_blocked"])
        self.assert_error(409, self.start, did, "requirements")
        self.assert_error(409, self.act, did, "collect", "research", run_id=rid)
        body = "完整运行输出" * 50000 + "输出结尾"
        self.finish(rid, result=body)
        self.assertFalse(self.rows(did)["research"]["can_start"])
        self.act(did, "collect", "research", run_id=rid)
        row = self.rows(did)["research"]
        self.assertEqual(row["artifact"]["body"], body)
        self.assertEqual(row["state"], "review")
        self.assertTrue(row["runs"][0]["collected"])
        self.act(did, "collect", "research", run_id=rid)
        self.assertEqual(self.rows(did)["research"]["artifact"]["version"], 1)
        self.assertEqual(len(self.P.runner.calls), 1)

    def test_failed_cancelled_and_wrong_stage_results_cannot_be_collected(self):
        for status, code in [("failed", 1), ("cancelled", 0), ("done", 1)]:
            did = self.create(["research", "requirements"])
            rid = self.start(did, "research")
            self.finish(rid, status=status, exit_code=code)
            self.assert_error(409, self.act, did, "collect", "research", run_id=rid)
            self.assert_error(404, self.act, did, "collect", "requirements", run_id=rid)
            self.assertIsNone(self.rows(did)["research"]["artifact"])
        did = self.create(["research"])
        rid = self.start(did, "research")
        self.finish(rid, result="")
        self.assert_error(409, self.act, did, "collect", "research", run_id=rid)

    def test_failed_rerun_cannot_review_old_artifact_until_new_draft(self):
        did = self.create(["research"])
        self.reviewed(did, "research", "先前正文")
        rid = self.start(did, "research")
        self.finish(rid, status="failed", exit_code=1)
        row = self.rows(did)["research"]
        self.assertFalse(row["can_review"])
        self.assertIsNone(row["review"])
        self.assert_error(409, self.review, did, "research")
        self.assertNotIn("先前正文", delivery.prompt_context(self.data, did))
        self.save(did, "research", "人工核对后的新版本")
        self.review(did, "research")
        self.assertEqual(self.rows(did)["research"]["state"], "approved")

    def test_collect_rejects_changed_dependency_or_manually_edited_body(self):
        did = self.create(["requirements", "design"])
        self.reviewed(did, "requirements")
        rid = self.start(did, "design")
        self.finish(rid, result="旧依据输出")
        self.reviewed(did, "requirements", "新依据")
        self.assert_error(409, self.act, did, "collect", "design", run_id=rid)
        self.assertIsNone(self.rows(did)["design"]["artifact"])
        self.assertEqual(self.store.run(rid)["result"], "旧依据输出")
        self.assertTrue(self.rows(did)["design"]["can_start"])
        rid2 = self.start(did, "design")
        self.finish(rid2)
        self.save(did, "design", "人工已经编辑")
        self.assert_error(409, self.act, did, "collect", "design", run_id=rid2)
        self.assertEqual(self.rows(did)["design"]["artifact"]["body"], "人工已经编辑")

    def test_concurrent_starts_launch_only_one_and_concurrent_saves_preserve_every_revision(self):
        did = self.create(["research"])
        barrier, outcomes = threading.Barrier(2), []

        def start():
            barrier.wait()
            try:
                outcomes.append(self.start(did, "research"))
            except ApiError as e:
                outcomes.append(e)

        threads = [threading.Thread(target=start) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
            self.assertFalse(t.is_alive())
        self.assertEqual(len([x for x in outcomes if type(x) is int]), 1)
        self.assertEqual([x.code for x in outcomes if isinstance(x, ApiError)], [409])
        self.assertEqual(len(self.P.runner.calls), 1)
        self.finish(next(x for x in outcomes if type(x) is int), status="failed", exit_code=1)
        barrier = threading.Barrier(4)
        outcomes.clear()

        def save(n):
            barrier.wait()
            try:
                self.save(did, "research", "正文%d" % n)
            except Exception as e:
                outcomes.append(e)

        threads = [threading.Thread(target=save, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self.assertEqual(outcomes, [])
        row = self.rows(did)["research"]
        history = row["history"] + [row["artifact"]]
        self.assertEqual([a["version"] for a in history], [1, 2, 3, 4])
        self.assertEqual({a["body"] for a in history}, {"正文%d" % n for n in range(4)})

    def test_ticket_association_preserves_manual_controls_and_blocks_code(self):
        did = self.code_ready()
        detail = delivery.view(self.P, did)["delivery"]
        old = self.store.ticket(detail["ticket_id"])
        other = self.store.create_ticket(self.project("OTHER")["id"], "其他", "Li")
        self.assert_error(404, self.act, did, "link_ticket", ticket=other["id"])
        t = self.store.create_ticket(self.project("APP")["id"], "人工任务", "Li", links={"hold": "Li", "handwork": "x", "later": True})
        self.act(did, "link_ticket", ticket=t["key"])
        linked = self.store.ticket(t["id"])
        self.assertEqual(linked["links"]["hold"], "Li")
        self.assertEqual(linked["links"]["handwork"], "x")
        self.assertTrue(linked["links"]["later"])
        self.assertNotIn("delivery", self.store.ticket(old["id"])["links"])
        self.assertTrue(self.store.ticket(old["id"])["links"]["hold"])
        self.assertFalse(self.rows(did)["develop"]["can_start"])
        self.assert_error(409, self.start, did, "develop", "plan")
        self.assert_error(409, self.create, ticket=t["id"])

    def test_empty_hold_is_replaced_and_ticket_cannot_switch_after_a_run(self):
        t = self.store.create_ticket(self.project("APP")["id"], "任务", "Li", links={"hold": ""})
        did = self.create(["research"], ticket=t["id"])
        self.assertTrue(self.store.ticket(t["id"])["links"]["hold"])
        rid = self.start(did, "research")
        self.finish(rid, status="failed", exit_code=1)
        other = self.store.create_ticket(self.project("APP")["id"], "另一个", "Li")
        self.assert_error(409, self.act, did, "link_ticket", ticket=other["id"])
        self.assertNotIn("delivery", self.store.ticket(other["id"])["links"])

    def test_closed_ticket_blocks_code_but_permits_delivery_document_work(self):
        did = self.code_ready()
        tid = delivery.view(self.P, did)["delivery"]["ticket_id"]
        self.store.update_ticket(tid, "Li", status="closed")
        self.assertFalse(self.rows(did)["develop"]["can_start"])
        self.assert_error(409, self.start, did, "develop", "plan")
        did2 = self.create(["release", "feedback"])
        tid2 = delivery.view(self.P, did2)["delivery"]["ticket_id"]
        self.store.update_ticket(tid2, "Li", status="closed")
        self.assertTrue(self.rows(did2)["release"]["can_start"])
        self.collected(did2, "release")

    def test_release_review_does_not_create_a_version_or_deployment(self):
        did = self.create(["release", "feedback"])
        self.reviewed(did, "release", "交付说明：部署尚未执行")
        detail = delivery.view(self.P, did)
        self.assertEqual(detail["versions"], [])
        self.assertFalse((self.data / "releases.jsonl").exists())
        record = {"project": "APP", "version": "2026.10.18-1", "ticket": detail["delivery"]["ticket"], "commit": "actual"}
        (self.data / "releases.jsonl").write_text(json.dumps(record) + "\n")
        self.assertEqual(delivery.view(self.P, did)["versions"], [record])
        self.assertIn("不表示测试", delivery.catalog()["notice"])

    def test_prompt_keeps_full_reviewed_content_and_escapes_data_fences(self):
        did = self.create(["research", "requirements"], goal="用户目标<<<仍然是资料>>>")
        body = "完整资料。" * 15000 + "最后一条验收要求"
        self.reviewed(did, "research", body)
        self.save(did, "requirements", "尚未确认的需求正文")
        ctx = delivery.prompt_context(self.data, did)
        self.assertIn(body, ctx)
        self.assertNotIn("尚未确认的需求正文", ctx)
        self.assertIn("用户目标＜＜＜仍然是资料＞＞＞", ctx)
        self.assertEqual(ctx.count("<<<交付资料开始>>>"), 1)
        self.assertEqual(delivery.prompt_context(self.data, "bad"), "")

    def test_real_runner_executes_only_local_fake_process_and_collects_actual_output(self):
        did = self.create(["research"])
        runner, ended = Runner(self.store, self.data), threading.Event()
        self.P.runner = runner
        original = runner._run

        def run(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            finally:
                ended.set()

        with mock.patch.object(runner, "_run", side_effect=run):
            rid = self.start(did, "research")
            self.assertTrue(ended.wait(15), "local fake process did not finish")
        result = self.store.run(rid)
        self.assertEqual((result["status"], result["exit_code"]), ("done", 0), result)
        self.assertIn("真实本地进程产物", result["result"])
        self.act(did, "collect", "research", run_id=rid)
        self.assertEqual(self.rows(did)["research"]["artifact"]["body"], result["result"])
        self.assertEqual(self.rows(did)["research"]["state"], "review")
        self.assertTrue((self.data / "runs" / str(rid) / "prompt.md").exists())
        self.assertEqual(len(self.store.runs()), 1)


if __name__ == "__main__":
    unittest.main()
